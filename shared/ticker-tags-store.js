/*
 * ticker-tags-store.js — persistencia segura de la taxonomía de etiquetas (solo Node).
 *
 * Garantías (wiki/DISENO_PORTFOLIO_TAGS_DEFINITIVO.md v2, §8):
 *   · UN solo servidor escritor: las escrituras exigen hostname == TICKER_TAGS_WRITER_HOST. Sin configurar
 *     o en otra máquina → solo lectura. (El repo vive en Dropbox y dos servidores no se coordinan.)
 *   · Cada escritura valida contra el estado actual y su `base_revision` (409 si cambió).
 *   · Orden de escritura: 1) evento(s) al registro + fsync  2) ticker_tags.json atómico (tmp → fsync → rename).
 *     El registro es la fuente de verdad; el JSON es el estado materializado.
 *   · Recuperación al cargar (sin intervención): JSON por detrás del registro → se regenera; última línea del
 *     registro truncada → se descarta; JSON por delante o distinto de replay(eventos) → solo lectura + aviso.
 *   · Copias en conflicto de Dropbox sobre estos ficheros → escritura bloqueada.
 *   · Publicación: commit de SOLO estos dos ficheros; sin rebase automático salvo que sea mecánicamente seguro.
 *
 * Nada de aquí lee ni escribe ficheros de motores de inversión.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');
const Tags = require('./ticker-tags-lib');

const STATE_FILE = 'ticker_tags.json';
const EVENTS_FILE = 'ticker_tags_events.jsonl';

class StoreError extends Error {
  constructor(code, status, message, details) {
    super(message); this.name = 'StoreError'; this.code = code; this.status = status; this.details = details || null;
  }
}

const canon = (o) => JSON.stringify(o, (k, v) => (v && typeof v === 'object' && !Array.isArray(v))
  ? Object.keys(v).sort().reduce((a, key) => { a[key] = v[key]; return a; }, {}) : v);

function sleepSync(ms) { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms); }

function writeAtomic(file, text) {
  const tmp = `${file}.tmp-${process.pid}-${Date.now()}`;
  const fd = fs.openSync(tmp, 'w');
  try { fs.writeSync(fd, text); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  let lastErr;
  for (let i = 0; i < 6; i++) {            // Windows/Dropbox pueden tener el destino abierto un instante
    try { fs.renameSync(tmp, file); return; } catch (e) { lastErr = e; sleepSync(60 * (i + 1)); }
  }
  try { fs.unlinkSync(tmp); } catch (_) { /* ya no existe */ }
  throw lastErr;
}

function appendDurable(file, text) {
  const fd = fs.openSync(file, 'a');
  try { fs.writeSync(fd, text); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
}

function defaultGit(args, cwd) {
  return new Promise((resolve) => {
    execFile('git', args, { cwd, timeout: 60000, maxBuffer: 8 * 1024 * 1024, windowsHide: true }, (err, stdout, stderr) => {
      resolve({ ok: !err, code: err ? (err.code === undefined ? 1 : err.code) : 0, stdout: String(stdout || ''), stderr: String(stderr || '') });
    });
  });
}

function createStore(opts) {
  const o = Object.assign({
    dataDir: null, repoRoot: null, branch: 'master', remote: 'origin',
    hostname: os.hostname(), writerHost: process.env.TICKER_TAGS_WRITER_HOST || '',
    now: () => new Date(), git: defaultGit,
  }, opts || {});
  if (!o.dataDir) throw new Error('dataDir obligatorio');
  const repoRoot = o.repoRoot || path.resolve(o.dataDir, '..', '..');
  const stateFile = path.join(o.dataDir, STATE_FILE);
  const eventsFile = path.join(o.dataDir, EVENTS_FILE);
  const relFiles = [stateFile, eventsFile].map(f => path.relative(repoRoot, f).split(path.sep).join('/'));

  let queue = Promise.resolve();           // exclusión mutua dentro del proceso
  const locked = (fn) => { const run = queue.then(fn, fn); queue = run.catch(() => {}); return run; };

  function writerStatus() {
    const w = (o.writerHost || '').trim();
    if (!w) return { enabled: false, reason: 'writer_not_configured', host: o.hostname };
    if (w.toLowerCase() !== String(o.hostname).toLowerCase()) return { enabled: false, reason: 'other_host', host: o.hostname, writer: w };
    return { enabled: true, host: o.hostname };
  }

  function conflictCopies() {
    try {
      return fs.readdirSync(o.dataDir).filter(f => /ticker_tags/i.test(f) && /conflict|conflicto/i.test(f));
    } catch (_) { return []; }
  }

  // ── lectura + recuperación ───────────────────────────────────────────────
  function readEventsRaw() {
    let text = '';
    try { text = fs.readFileSync(eventsFile, 'utf8'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    const endsClean = text === '' || text.endsWith('\n');
    const lines = text.split('\n'); if (lines[lines.length - 1] === '') lines.pop();
    const events = []; const notes = []; let fatal = null; let droppedTail = false;
    for (let i = 0; i < lines.length; i++) {
      let ev = null;
      try { ev = JSON.parse(lines[i]); } catch (_) { ev = null; }
      const isLast = i === lines.length - 1;
      if (!ev || typeof ev.seq !== 'number') {
        if (isLast) { droppedTail = true; notes.push('truncated_tail_dropped'); break; }
        fatal = { code: 'invalid_events', message: `línea ${i + 1} del registro de eventos no es válida` }; break;
      }
      if (ev.seq !== events.length + 1) { fatal = { code: 'invalid_events', message: `seq no contigua en la línea ${i + 1}` }; break; }
      if (isLast && !endsClean) { droppedTail = true; notes.push('unterminated_tail_dropped'); break; }   // sin \n final: no se confirmó
      events.push(ev);
    }
    return { events, notes, fatal, droppedTail };
  }

  function loadFromDisk(allowRepair) {
    const meta = { mode: 'rw', reason: null, notes: [] };
    const raw = readEventsRaw();
    meta.notes.push(...raw.notes);
    let state;
    if (raw.fatal) {
      return { state: Tags.emptyState(), events: [], meta: { mode: 'ro', reason: raw.fatal.code, message: raw.fatal.message, notes: meta.notes } };
    }
    try { state = Tags.replay(raw.events); }
    catch (e) { return { state: Tags.emptyState(), events: raw.events, meta: { mode: 'ro', reason: 'replay_failed', message: e.message, notes: meta.notes } }; }

    let disk = null; let diskErr = null;
    try { disk = JSON.parse(fs.readFileSync(stateFile, 'utf8')); }
    catch (e) { diskErr = e.code === 'ENOENT' ? 'missing' : 'corrupt'; }

    const n = raw.events.length;
    const needRegen = diskErr || disk.revision < n;
    if (!diskErr && disk.revision > n) {
      return { state: disk, events: raw.events, meta: { mode: 'ro', reason: 'state_ahead_of_events', message: 'ticker_tags.json va por delante del registro de eventos', notes: meta.notes } };
    }
    if (!diskErr && disk.revision === n && canon(disk) !== canon(state)) {
      return { state: disk, events: raw.events, meta: { mode: 'ro', reason: 'diverged', message: 'ticker_tags.json no coincide con replay(eventos)', notes: meta.notes } };
    }
    if (needRegen) {
      meta.notes.push(diskErr ? `state_${diskErr}_regenerated` : 'state_behind_regenerated');
      if (allowRepair) writeAtomic(stateFile, JSON.stringify(state, null, 1) + '\n');
    }
    if (raw.droppedTail && allowRepair) {
      writeAtomic(eventsFile, raw.events.map(e => JSON.stringify(e)).join('\n') + (raw.events.length ? '\n' : ''));
    }
    return { state, events: raw.events, meta };
  }

  function canRepair() { return writerStatus().enabled && conflictCopies().length === 0; }

  // ── API ───────────────────────────────────────────────────────────────────
  function snapshot() {
    const loaded = loadFromDisk(canRepair());
    const w = writerStatus(); const cc = conflictCopies();
    let writeBlock = null;
    if (!w.enabled) writeBlock = w.reason;
    else if (cc.length) writeBlock = 'conflict_copies';
    else if (loaded.meta.mode === 'ro') writeBlock = loaded.meta.reason;
    return {
      state: loaded.state, revision: loaded.state.revision, events_total: loaded.events.length,
      mode: writeBlock ? 'read_only' : 'read_write', write_block: writeBlock,
      writer: w, conflict_copies: cc, recovery: loaded.meta.notes, integrity: loaded.meta.mode === 'ro' ? { reason: loaded.meta.reason, message: loaded.meta.message } : null,
    };
  }

  function applyBatch(ops, ctx) {
    const c = Object.assign({ baseRevision: null, actor: 'dashboard', skipWriterCheck: false }, ctx || {});
    return locked(() => {
      if (!c.skipWriterCheck) {
        const w = writerStatus();
        if (!w.enabled) throw new StoreError('not_writer', 403, w.reason === 'writer_not_configured'
          ? 'Edición deshabilitada: TICKER_TAGS_WRITER_HOST no está configurado en esta máquina' : `Edición deshabilitada: esta máquina (${w.host}) no es el escritor (${w.writer})`, w);
      }
      const cc = conflictCopies();
      if (cc.length) throw new StoreError('conflict_copies', 423, 'Hay copias en conflicto de Dropbox de los ficheros de etiquetas; resuélvelas antes de editar', { files: cc });
      const loaded = loadFromDisk(true);
      if (loaded.meta.mode === 'ro') throw new StoreError('read_only', 423, 'Almacén en solo lectura: ' + loaded.meta.message, { reason: loaded.meta.reason });
      if (c.baseRevision != null && c.baseRevision !== loaded.state.revision)
        throw new StoreError('stale_revision', 409, 'El fichero ha cambiado desde que lo cargaste; recarga', { current: loaded.state.revision, base: c.baseRevision });
      if (!Array.isArray(ops) || !ops.length) throw new StoreError('validation', 400, 'ops vacío');

      const working = Tags.clone(loaded.state);
      const lines = []; const results = [];
      let seq = working.revision;
      try {
        for (const { op, args } of ops) {
          const ts = o.now().toISOString();
          const r = Tags.applyOp(working, op, args, ts);
          seq += 1; working.revision = seq;
          const ev = { seq, ts, op, actor: c.actor, args };
          if (r.id !== undefined) ev.id = r.id;
          if (r.before !== undefined) ev.before = r.before;
          if (r.after !== undefined && !r.id) ev.after = r.after;
          lines.push(JSON.stringify(ev)); results.push({ op, id: r.id, before: r.before, after: r.after });
        }
      } catch (e) {
        if (e instanceof Tags.TagError) {
          const status = e.code === 'not_found' ? 404 : 400;
          throw new StoreError(e.code, status, e.message, e.details);
        }
        throw e;
      }
      const problems = Tags.validateState(working);
      if (problems.length) throw new StoreError('validation', 400, 'El estado resultante no cumple las invariantes', { problems });

      appendDurable(eventsFile, lines.join('\n') + '\n');                 // 1) evento(s)
      writeAtomic(stateFile, JSON.stringify(working, null, 1) + '\n');    // 2) estado materializado
      return { revision: working.revision, results };
    });
  }

  const apply = (op, args, ctx) => applyBatch([{ op, args }], ctx).then(r => ({ revision: r.revision, result: r.results[0] }));

  function readEvents(limit) {
    const { events } = readEventsRaw();
    return limit ? events.slice(-limit) : events;
  }

  // ── publicación a git ─────────────────────────────────────────────────────
  async function gitStatus() {
    const st = await o.git(['status', '--porcelain', '--', ...relFiles], repoRoot);
    const ahead = await o.git(['rev-list', '--count', `${o.remote}/${o.branch}..HEAD`, '--', ...relFiles], repoRoot);
    const remoteEvents = await o.git(['show', `${o.remote}/${o.branch}:${relFiles[1]}`], repoRoot);
    const remoteLines = remoteEvents.ok ? remoteEvents.stdout.split('\n').filter(Boolean).length : 0;
    const local = readEventsRaw().events.length;
    return {
      uncommitted: st.ok && st.stdout.trim().length > 0,
      unpushed_commits: ahead.ok ? parseInt(ahead.stdout.trim() || '0', 10) : null,
      unpublished_events: Math.max(0, local - remoteLines),
    };
  }

  function publish() {
    return locked(async () => {
      const w = writerStatus();
      if (!w.enabled) throw new StoreError('not_writer', 403, 'Solo la máquina escritora puede publicar', w);
      const cc = conflictCopies();
      if (cc.length) throw new StoreError('conflict_copies', 423, 'Hay copias en conflicto de Dropbox; resuélvelas antes de publicar', { files: cc });
      const br = await o.git(['rev-parse', '--abbrev-ref', 'HEAD'], repoRoot);
      if (!br.ok || br.stdout.trim() !== o.branch)
        return { ok: false, reason: 'wrong_branch', message: `La rama activa es ${br.stdout.trim() || '?'}; solo se publica desde ${o.branch}` };

      const before = await gitStatus();
      let committed = false;
      if (before.uncommitted) {
        const n = before.unpublished_events || 0;
        const add = await o.git(['add', '--', ...relFiles], repoRoot);
        if (!add.ok) return { ok: false, reason: 'git_add_failed', message: add.stderr.trim() };
        const msg = `chore(tags): taxonomía de etiquetas del Portfolio (${n} evento${n === 1 ? '' : 's'})`;
        const cm = await o.git(['commit', '--only', '-m', msg, '--', ...relFiles], repoRoot);
        if (!cm.ok) return { ok: false, reason: 'git_commit_failed', message: (cm.stderr || cm.stdout).trim() };
        committed = true;
      }
      const stAfter = await gitStatus();
      if (!committed && !(stAfter.unpushed_commits > 0)) return { ok: true, nothing: true, message: 'No hay cambios sin publicar' };

      let push = await o.git(['push', o.remote, `HEAD:${o.branch}`], repoRoot);
      if (push.ok) return { ok: true, committed, pushed: true };

      // push rechazado o sin red: nunca se toca el árbol de trabajo salvo que sea mecánicamente seguro
      const fetch = await o.git(['fetch', o.remote, o.branch], repoRoot);
      if (!fetch.ok) return { ok: false, committed_local: true, reason: 'network', message: 'No se pudo contactar con el remoto; el commit queda local', stderr: push.stderr.trim() };
      const mb = await o.git(['merge-base', 'HEAD', `${o.remote}/${o.branch}`], repoRoot);
      const incoming = mb.ok ? (await o.git(['diff', '--name-only', mb.stdout.trim(), `${o.remote}/${o.branch}`], repoRoot)).stdout.split('\n').filter(Boolean) : [];
      const dirty = (await o.git(['status', '--porcelain', '--untracked-files=no'], repoRoot)).stdout.split('\n').filter(Boolean).map(l => l.slice(3).trim());
      const clash = incoming.filter(f => dirty.includes(f) || relFiles.includes(f));
      if (clash.length) return { ok: false, committed_local: true, reason: 'needs_manual_sync', message: 'origin avanzó y toca ficheros con cambios locales; actualiza a mano (git pull --rebase) y vuelve a publicar', files: clash };
      const rb = await o.git(['rebase', '--autostash', `${o.remote}/${o.branch}`], repoRoot);
      if (!rb.ok) {
        await o.git(['rebase', '--abort'], repoRoot);
        return { ok: false, committed_local: true, reason: 'rebase_conflict', message: 'El rebase no se pudo completar; se ha abortado y el commit queda local', stderr: rb.stderr.trim() };
      }
      push = await o.git(['push', o.remote, `HEAD:${o.branch}`], repoRoot);
      if (push.ok) return { ok: true, committed, pushed: true, rebased: true };
      return { ok: false, committed_local: true, reason: 'push_failed', message: 'El push sigue fallando tras actualizar', stderr: push.stderr.trim() };
    });
  }

  async function status() {
    const s = snapshot();
    let git = null;
    try { git = await gitStatus(); } catch (_) { git = null; }
    return { revision: s.revision, events_total: s.events_total, mode: s.mode, write_block: s.write_block, writer: s.writer,
      conflict_copies: s.conflict_copies, recovery: s.recovery, integrity: s.integrity, git };
  }

  return { snapshot, apply, applyBatch, readEvents, publish, status, writerStatus, files: { stateFile, eventsFile, relFiles }, StoreError };
}

module.exports = { createStore, StoreError, STATE_FILE, EVENTS_FILE, canon };
