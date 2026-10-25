#!/usr/bin/env node
/*
 * test_ticker_tags_store.js — persistencia segura, recuperación, escritor único y publicación a git.
 *   node scripts/test_ticker_tags_store.js          (usa git y directorios temporales; sin red, sin tocar el repo)
 *
 *   F3  atomicidad y recuperación: cada tipo de fallo deja un estado coherente
 *   F4  auditoría: cada operación deja su evento con antes/después
 *   F9  publicación: commit de SOLO los dos ficheros, rechazos de push, rebase seguro, red caída, rama equivocada
 *   F10 escritor único: hostname, no configurado, otra máquina, copias en conflicto de Dropbox
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const T = require('../shared/ticker-tags-lib');
const { createStore, canon, STATE_FILE, EVENTS_FILE } = require('../shared/ticker-tags-store');

const results = [];
const check = (name, ok, detail) => results.push({ name, ok: !!ok, detail: ok ? '' : String(detail || '') });
const tmps = [];
const mkTmp = () => { const d = fs.mkdtempSync(path.join(os.tmpdir(), 'tags-test-')); tmps.push(d); return d; };
const rm = (d) => { try { fs.rmSync(d, { recursive: true, force: true }); } catch (_) { /* Windows: archivo en uso */ } };

let clock = Date.parse('2026-10-26T10:00:00Z');
const now = () => new Date(clock += 1000);

function newStore(extra) {
  const root = mkTmp(); const dataDir = path.join(root, 'docs', 'data'); fs.mkdirSync(dataDir, { recursive: true });
  const st = createStore(Object.assign({ dataDir, repoRoot: root, hostname: 'TEST_WRITER_HOST', writerHost: 'test_writer_host', now }, extra || {}));
  return { root, dataDir, st, state: path.join(dataDir, STATE_FILE), events: path.join(dataDir, EVENTS_FILE) };
}
const mkOps = [
  ['create_tag', { tag: 'commodity:gold', label: 'Oro' }], ['create_tag', { tag: 'commodity:copper', label: 'Cobre' }],
  ['create_tag', { tag: 'industry:mining', label: 'Minería' }],
];
async function seed(s) { return s.st.applyBatch(mkOps.map(([op, args]) => ({ op, args }))); }
async function addIssuer(s, name, ticker) {
  const r = await s.st.apply('create_issuer', { legal_name: name }); const iss = r.result.id;
  await s.st.apply('create_instrument', { ticker, issuer_id: iss }); return iss;
}
const readEv = (s) => fs.readFileSync(s.events, 'utf8').split('\n').filter(Boolean).map(JSON.parse);
const readState = (s) => JSON.parse(fs.readFileSync(s.state, 'utf8'));
const consistent = (s) => canon(T.replay(readEv(s))) === canon(readState(s));
async function rejectsWith(name, p, code, status) {
  let err = null; try { await p; } catch (e) { err = e; }
  check(name, err && err.code === code && (!status || err.status === status), err ? `${err.code}/${err.status}: ${err.message}` : 'no lanzó error');
}

// ── escritura básica, 409, validación sin escribir ─────────────────────────
async function basics() {
  const s = newStore(); await seed(s);
  check('F3 la escritura crea eventos y estado, y replay == estado', consistent(s) && readState(s).revision === 3 && readEv(s).length === 3);
  const iss = await addIssuer(s, 'Minera SA', 'MIN.TO');
  const rev = readState(s).revision;
  const evBefore = fs.readFileSync(s.events, 'utf8'), stBefore = fs.readFileSync(s.state, 'utf8');
  await rejectsWith('F1 una operación inválida devuelve 400', s.st.apply('assign', { issuer_id: iss, tag: 'commodity:nope', relation: 'direct', intensity: 'high', source: 'manual', confidence: 'low' }), 'validation', 400);
  check('F1 …y no escribe nada (ni evento ni estado)', fs.readFileSync(s.events, 'utf8') === evBefore && fs.readFileSync(s.state, 'utf8') === stBefore);
  await rejectsWith('F1 emisor inexistente → 404', s.st.apply('assign', { issuer_id: 'iss_9999', tag: 'commodity:gold', relation: 'direct', intensity: 'high', source: 'manual', confidence: 'low' }), 'not_found', 404);
  const a = await s.st.apply('assign', { issuer_id: iss, tag: 'commodity:gold', relation: 'direct', intensity: 'high', nav_primary: true, source: 'manual', confidence: 'high', review_status: 'confirmed' }, { baseRevision: rev });
  check('F3 revisión base correcta → aplica y sube la revisión', a.revision === rev + 1);
  await rejectsWith('F3 revisión base obsoleta → 409', s.st.apply('review', { issuer_id: iss, aid: a.result.id, review_status: 'rejected' }, { baseRevision: rev }), 'stale_revision', 409);
  // F4 auditoría
  const aid = a.result.id;
  await s.st.apply('update_assignment', { issuer_id: iss, aid, changes: { intensity: 'low' } });
  await s.st.apply('review', { issuer_id: iss, aid, review_status: 'rejected' });
  await s.st.apply('retire_assignment', { issuer_id: iss, aid });
  const ev = readEv(s);
  const upd = ev.find(e => e.op === 'update_assignment'), rv = ev.find(e => e.op === 'review'), rt = ev.find(e => e.op === 'retire_assignment');
  check('F4 update_assignment guarda antes y después', upd.before.intensity === 'high' && upd.after.intensity === 'low');
  check('F4 review guarda antes/después y quién lo hizo', rv.before.review_status === 'confirmed' && rv.after.review_status === 'rejected' && rv.actor === 'dashboard');
  check('F4 retire_assignment guarda removed_at', rt.before.removed_at === null && typeof rt.after.removed_at === 'string');
  check('F4 los eventos de creación guardan el id generado', ev.find(e => e.op === 'create_issuer').id === iss);
  check('F4 seq contiguas y ts crecientes', ev.every((e, i) => e.seq === i + 1) && ev.every((e, i) => i === 0 || e.ts > ev[i - 1].ts));
  check('F4 tras la secuencia completa replay == estado', consistent(s));
  // concurrencia dentro del proceso
  const s2 = newStore(); await seed(s2);
  const iss2 = await addIssuer(s2, 'Concurrente', 'CON.TO');
  const many = await Promise.all(Array.from({ length: 25 }, (_, i) => s2.st.apply('assign', Object.assign({ issuer_id: iss2, tag: i % 2 ? 'commodity:copper' : 'commodity:gold' }, i < 2 ? { relation: 'direct', intensity: 'low', source: 'manual', confidence: 'low' } : { relation: 'direct', intensity: 'low', source: 'manual', confidence: 'low' })).then(() => 'ok', e => e.code)));
  const okN = many.filter(x => x === 'ok').length;
  check('F3 25 escrituras concurrentes se serializan sin corromper (2 válidas, el resto duplicados rechazados)', okN === 2 && many.filter(x => x === 'validation').length === 23 && consistent(s2), many.join());
  // dos instancias del almacén (dos procesos) sobre los mismos ficheros
  const s3 = newStore(); await seed(s3);
  const other = createStore({ dataDir: s3.dataDir, repoRoot: s3.root, hostname: 'TEST_WRITER_HOST', writerHost: 'TEST_WRITER_HOST', now });
  await s3.st.apply('create_issuer', { legal_name: 'A' }); await other.apply('create_issuer', { legal_name: 'B' }); await s3.st.apply('create_issuer', { legal_name: 'C' });
  const ids = Object.keys(readState(s3).issuers);
  check('F3 dos instancias sobre los mismos ficheros no pisan ids ni eventos', ids.join() === 'iss_0001,iss_0002,iss_0003' && consistent(s3), ids.join());
}

// ── F3: recuperación ────────────────────────────────────────────────────────
async function recovery() {
  const mk = async () => { const s = newStore(); await seed(s); await addIssuer(s, 'Uno', 'UNO.TO'); return s; };
  const lastLine = (s) => fs.readFileSync(s.events, 'utf8').trimEnd().split('\n').pop();

  { // a) evento escrito pero JSON no actualizado (caída entre 1 y 2)
    const s = await mk(); const n = readEv(s).length; const st0 = fs.readFileSync(s.state, 'utf8');
    const ev = { seq: n + 1, ts: '2026-10-26T12:00:00.000Z', op: 'create_issuer', actor: 'dashboard', args: { legal_name: 'Fantasma' }, id: 'iss_0002' };
    fs.appendFileSync(s.events, JSON.stringify(ev) + '\n');
    const snap = s.st.snapshot();
    check('F3 JSON por detrás del registro → se regenera y se avisa', snap.revision === n + 1 && snap.recovery.includes('state_behind_regenerated') && Object.values(snap.state.issuers).some(i => i.legal_name === 'Fantasma'));
    check('F3 …y el fichero queda reparado en disco', readState(s).revision === n + 1 && consistent(s) && fs.readFileSync(s.state, 'utf8') !== st0);
  }
  { // b) última línea truncada (caída durante el append)
    const s = await mk(); const n = readEv(s).length;
    fs.appendFileSync(s.events, '{"seq":' + (n + 1) + ',"ts":"2026-10-26T12:00:00.0');
    const snap = s.st.snapshot();
    check('F3 línea final truncada → descartada', snap.revision === n && snap.recovery.includes('truncated_tail_dropped'));
    check('F3 …el registro queda sin basura y se puede seguir escribiendo', readEv(s).length === n && (await s.st.apply('create_issuer', { legal_name: 'Tras recuperar' })).revision === n + 1 && consistent(s));
  }
  { // c) última línea válida pero sin salto de línea (no llegó a confirmarse)
    const s = await mk(); const n = readEv(s).length;
    fs.appendFileSync(s.events, JSON.stringify({ seq: n + 1, ts: '2026-10-26T12:00:00.000Z', op: 'create_issuer', actor: 'x', args: { legal_name: 'Sin confirmar' }, id: 'iss_0002' }));
    const snap = s.st.snapshot();
    check('F3 última línea sin \\n final (no confirmada) → descartada', snap.revision === n && snap.recovery.includes('unterminated_tail_dropped') && !Object.values(snap.state.issuers).some(i => i.legal_name === 'Sin confirmar'));
  }
  { // d) JSON por delante del registro
    const s = await mk(); const st = readState(s); st.revision += 5; fs.writeFileSync(s.state, JSON.stringify(st));
    const snap = s.st.snapshot();
    check('F3 JSON por delante del registro → solo lectura con motivo', snap.mode === 'read_only' && snap.write_block === 'state_ahead_of_events');
    await rejectsWith('F3 …y las escrituras se rechazan (423)', s.st.apply('create_issuer', { legal_name: 'X' }), 'read_only', 423);
  }
  { // e) mismo número de revisión pero contenido distinto
    const s = await mk(); const st = readState(s); st.issuers[Object.keys(st.issuers)[0]].legal_name = 'ADULTERADO'; fs.writeFileSync(s.state, JSON.stringify(st));
    const snap = s.st.snapshot();
    check('F3 estado distinto de replay(eventos) con igual revisión → solo lectura (diverged)', snap.mode === 'read_only' && snap.write_block === 'diverged');
    check('F3 …sin sobrescribir el fichero sospechoso', readState(s).issuers[Object.keys(st.issuers)[0]].legal_name === 'ADULTERADO');
  }
  { // f) JSON corrupto
    const s = await mk(); fs.writeFileSync(s.state, '{"revision": 3, "tags":');
    const snap = s.st.snapshot();
    check('F3 JSON corrupto → se regenera desde los eventos', snap.revision === readEv(s).length && snap.recovery.some(n => n.startsWith('state_corrupt')) && consistent(s));
  }
  { // g) JSON ausente
    const s = await mk(); fs.unlinkSync(s.state);
    check('F3 JSON ausente → se regenera', s.st.snapshot().revision === readEv(s).length && fs.existsSync(s.state) && consistent(s));
  }
  { // h) línea intermedia inválida
    const s = await mk(); const lines = fs.readFileSync(s.events, 'utf8').trimEnd().split('\n'); lines[1] = 'BASURA'; fs.writeFileSync(s.events, lines.join('\n') + '\n');
    const snap = s.st.snapshot();
    check('F3 línea intermedia inválida → solo lectura (no se inventa nada)', snap.mode === 'read_only' && snap.write_block === 'invalid_events');
  }
  { // i) seq no contigua
    const s = await mk(); const lines = fs.readFileSync(s.events, 'utf8').trimEnd().split('\n'); lines.splice(1, 1); fs.writeFileSync(s.events, lines.join('\n') + '\n');
    check('F3 seq no contigua → solo lectura', s.st.snapshot().write_block === 'invalid_events');
  }
  { // j) vacío total
    const s = newStore(); const snap = s.st.snapshot();
    check('F3 sin ficheros → estado vacío en revisión 0, escritura posible', snap.revision === 0 && snap.mode === 'read_write' && (await seed(s)).revision === 3);
  }
  { // k) fallo del rename atómico: el JSON anterior queda íntegro y el sistema se recupera solo
    const s = await mk(); const n = readEv(s).length; const st0 = fs.readFileSync(s.state, 'utf8');
    const realRename = fs.renameSync; let calls = 0;
    fs.renameSync = (...a) => { calls++; throw Object.assign(new Error('EPERM simulado'), { code: 'EPERM' }); };
    let err = null; try { await s.st.apply('create_issuer', { legal_name: 'Falla el rename' }); } catch (e) { err = e; } finally { fs.renameSync = realRename; }
    check('F3 rename que falla → error y el JSON previo queda intacto', err && fs.readFileSync(s.state, 'utf8') === st0 && calls >= 1);
    check('F3 …no quedan ficheros temporales', fs.readdirSync(s.dataDir).filter(f => f.includes('.tmp-')).length === 0, fs.readdirSync(s.dataDir).join());
    const snap = s.st.snapshot();
    check('F3 …el evento sí quedó (es la fuente de verdad) y la siguiente carga lo regenera: estado coherente', snap.revision === n + 1 && consistent(s));
  }
}

// ── F10 escritor único ──────────────────────────────────────────────────────
async function writer() {
  const none = newStore({ writerHost: '' });
  await rejectsWith('F10 sin TICKER_TAGS_WRITER_HOST → 403 not_writer', none.st.apply('create_tag', { tag: 'commodity:gold', label: 'Oro' }), 'not_writer', 403);
  check('F10 …pero la lectura funciona y avisa del motivo', none.st.snapshot().mode === 'read_only' && none.st.snapshot().write_block === 'writer_not_configured');
  const other = newStore({ writerHost: 'TEST_READONLY_HOST' });
  await rejectsWith('F10 hostname distinto del escritor → 403', other.st.apply('create_tag', { tag: 'commodity:gold', label: 'Oro' }), 'not_writer', 403);
  check('F10 …motivo other_host con el nombre del escritor', other.st.snapshot().write_block === 'other_host' && other.st.snapshot().writer.writer === 'TEST_READONLY_HOST');
  check('F10 un rechazo no crea ficheros', !fs.existsSync(other.events) && !fs.existsSync(other.state));
  const ok = newStore({ hostname: 'TEST_WRITER_HOST', writerHost: ' test_writer_host ' });
  check('F10 coincidencia de hostname sin distinguir mayúsculas ni espacios', (await ok.st.apply('create_tag', { tag: 'commodity:gold', label: 'Oro' })).revision === 1);
  // copias en conflicto de Dropbox
  const cc = newStore(); await seed(cc);
  const conflict = path.join(cc.dataDir, 'ticker_tags (Copia en conflicto de TEST_READONLY_HOST 2026-10-26).json');
  fs.writeFileSync(conflict, '{}');
  await rejectsWith('F10 copia en conflicto de Dropbox → escritura bloqueada (423)', cc.st.apply('create_issuer', { legal_name: 'X' }), 'conflict_copies', 423);
  const sn = cc.st.snapshot();
  check('F10 …se informa del fichero y la lectura sigue funcionando', sn.write_block === 'conflict_copies' && sn.conflict_copies.length === 1 && sn.revision === 3);
  await rejectsWith('F10 …y la publicación también se bloquea', cc.st.publish(), 'conflict_copies', 423);
  fs.unlinkSync(conflict);
  check('F10 al resolver el conflicto se puede volver a escribir', (await cc.st.apply('create_issuer', { legal_name: 'X' })).revision === 4);
  const enUS = newStore(); await seed(enUS); fs.writeFileSync(path.join(enUS.dataDir, 'ticker_tags_events (conflicted copy).jsonl'), '');
  check('F10 también detecta "conflicted copy" en inglés', enUS.st.snapshot().conflict_copies.length === 1);
}

// ── F9 publicación a git ────────────────────────────────────────────────────
const G = (cwd, ...a) => execFileSync('git', ['-c', 'core.autocrlf=false', ...a], { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
function mkRepo() {
  const base = mkTmp(); const remote = path.join(base, 'remote.git'); const work = path.join(base, 'work');
  G(base, 'init', '-q', '--bare', '-b', 'master', remote);
  G(base, 'clone', '-q', remote, work);
  for (const [k, v] of [['user.name', 'test'], ['user.email', 't@t'], ['core.autocrlf', 'false']]) G(work, 'config', k, v);
  fs.mkdirSync(path.join(work, 'docs', 'data'), { recursive: true });
  fs.writeFileSync(path.join(work, 'portfolio.json'), '{"sections":[]}\n'); fs.writeFileSync(path.join(work, 'other.txt'), 'x\n'); fs.writeFileSync(path.join(work, 'docs', 'data', 'keep.txt'), 'k\n');
  G(work, 'add', '-A'); G(work, 'commit', '-q', '-m', 'init'); G(work, 'branch', '-M', 'master'); G(work, 'push', '-q', '-u', 'origin', 'master');
  const dataDir = path.join(work, 'docs', 'data');
  const st = createStore({ dataDir, repoRoot: work, hostname: 'H', writerHost: 'H', now });
  const other = path.join(base, 'other'); G(base, 'clone', '-q', remote, other);
  for (const [k, v] of [['user.name', 'otro'], ['user.email', 'o@o'], ['core.autocrlf', 'false']]) G(other, 'config', k, v);
  return { base, remote, work, st, other, dataDir };
}
const filesIn = (cwd, ref) => G(cwd, 'show', '--name-only', '--format=', ref).split('\n').filter(Boolean).sort();

async function publish() {
  const r = mkRepo();
  await r.st.applyBatch(mkOps.map(([op, args]) => ({ op, args })));
  // ruido ajeno: un fichero staged, uno modificado sin stage y uno sin seguimiento
  fs.writeFileSync(path.join(r.work, 'other.txt'), 'cambiado y staged\n'); G(r.work, 'add', 'other.txt');
  fs.writeFileSync(path.join(r.work, 'portfolio.json'), '{"sections":[{"x":1}]}\n');
  fs.writeFileSync(path.join(r.work, 'nuevo.txt'), 'sin seguimiento\n');
  const st0 = await r.st.status();
  check('F9 status: hay cambios sin publicar (fichero sin commit y eventos nuevos)', st0.git && st0.git.uncommitted === true && st0.git.unpublished_events === 3, JSON.stringify(st0.git));
  const p = await r.st.publish();
  check('F9 publicar → ok, commit y push', p.ok === true && p.committed === true && p.pushed === true, JSON.stringify(p));
  check('F9 el commit contiene SOLO los dos ficheros de etiquetas', filesIn(r.work, 'HEAD').join() === 'docs/data/ticker_tags.json,docs/data/ticker_tags_events.jsonl', filesIn(r.work, 'HEAD').join());
  check('F9 el cambio ajeno staged sigue staged (no se arrastró al commit)', G(r.work, 'diff', '--cached', '--name-only').trim() === 'other.txt');
  check('F9 el cambio ajeno sin stage y el fichero sin seguimiento siguen como estaban',
    G(r.work, 'status', '--porcelain').split('\n').filter(Boolean).some(l => l.includes('portfolio.json')) && fs.existsSync(path.join(r.work, 'nuevo.txt')));
  check('F9 el remoto tiene el commit', G(r.remote, 'log', '--format=%s', '-1').includes('taxonomía de etiquetas'));
  const st1 = await r.st.status();
  check('F9 tras publicar no quedan eventos sin publicar', st1.git.uncommitted === false && st1.git.unpublished_events === 0 && st1.git.unpushed_commits === 0, JSON.stringify(st1.git));
  const again = await r.st.publish();
  check('F9 publicar sin cambios → nothing', again.ok === true && again.nothing === true);

  // push rechazado: el remoto avanza con un cambio ajeno que NO toca ficheros sucios → rebase seguro
  await r.st.apply('create_issuer', { legal_name: 'Segundo' });
  G(r.other, 'pull', '-q', '--rebase', 'origin', 'master');
  fs.writeFileSync(path.join(r.other, 'remoto.txt'), 'avance del pipeline\n'); G(r.other, 'add', '-A'); G(r.other, 'commit', '-q', '-m', 'pipeline'); G(r.other, 'push', '-q', 'origin', 'master');
  const p2 = await r.st.publish();
  check('F9 push rechazado + incoming no toca ficheros sucios → rebase --autostash y push', p2.ok === true && p2.rebased === true, JSON.stringify(p2));
  check('F9 historial lineal en el remoto (sin merge commits) y con ambos cambios', G(r.remote, 'log', '--format=%s', '--no-merges', '-3').split('\n').filter(Boolean).length === 3 && G(r.remote, 'rev-list', '--merges', '--count', 'master').trim() === '0');
  check('F9 tras el autostash los cambios locales ajenos conservan su CONTENIDO (git no restaura el estado staged)', fs.readFileSync(path.join(r.work, 'portfolio.json'), 'utf8').includes('"x":1') && fs.readFileSync(path.join(r.work, 'other.txt'), 'utf8').includes('cambiado y staged') && G(r.work, 'status', '--porcelain').includes('other.txt'));

  // push rechazado y el remoto toca un fichero con cambios locales → NO se toca el árbol
  await r.st.apply('create_issuer', { legal_name: 'Tercero' });
  G(r.other, 'pull', '-q', '--rebase', 'origin', 'master');
  fs.writeFileSync(path.join(r.other, 'portfolio.json'), '{"sections":[{"remoto":true}]}\n'); G(r.other, 'add', '-A'); G(r.other, 'commit', '-q', '-m', 'toca portfolio'); G(r.other, 'push', '-q', 'origin', 'master');
  const headBefore = G(r.work, 'rev-parse', 'HEAD').trim(); const portBefore = fs.readFileSync(path.join(r.work, 'portfolio.json'), 'utf8');
  const p3 = await r.st.publish();
  check('F9 incoming toca un fichero con cambios locales → needs_manual_sync, commit local', p3.ok === false && p3.reason === 'needs_manual_sync' && p3.committed_local === true && p3.files.includes('portfolio.json'), JSON.stringify(p3));
  check('F9 …el árbol de trabajo NO se tocó (sin rebase, sin stash)', fs.readFileSync(path.join(r.work, 'portfolio.json'), 'utf8') === portBefore && G(r.work, 'stash', 'list').trim() === '' && !fs.existsSync(path.join(r.work, '.git', 'rebase-merge')));
  check('F9 …y el commit de etiquetas queda local, sin publicar', G(r.work, 'rev-list', '--count', 'origin/master..HEAD').trim() === '1' && G(r.work, 'rev-parse', 'HEAD~1').trim() === headBefore);
  check('F9 status refleja 1 commit sin publicar', (await r.st.status()).git.unpushed_commits === 1);

  // el remoto cambia los MISMOS ficheros de etiquetas → conflicto: se informa, no se fuerza
  const q = mkRepo();
  await q.st.applyBatch(mkOps.map(([op, args]) => ({ op, args }))); await q.st.publish();
  G(q.other, 'pull', '-q', 'origin', 'master'); fs.writeFileSync(path.join(q.other, 'docs', 'data', 'ticker_tags_events.jsonl'), 'otra escritura\n'); G(q.other, 'add', '-A');
  try { G(q.other, 'commit', '-q', '-m', 'otro escritor'); G(q.other, 'push', '-q', 'origin', 'master'); } catch (_) { /* nada que commitear */ }
  await q.st.apply('create_issuer', { legal_name: 'Local' });
  const p4 = await q.st.publish();
  check('F9 el remoto cambió los ficheros de etiquetas → no se fuerza ni se resuelve a ciegas', p4.ok === false && (p4.reason === 'needs_manual_sync' || p4.reason === 'rebase_conflict') && p4.committed_local === true, JSON.stringify(p4));
  check('F9 …y no queda un rebase a medias', !fs.existsSync(path.join(q.work, '.git', 'rebase-merge')) && !fs.existsSync(path.join(q.work, '.git', 'rebase-apply')));

  // red caída
  const n = mkRepo();
  await n.st.applyBatch(mkOps.map(([op, args]) => ({ op, args })));
  G(n.work, 'remote', 'set-url', 'origin', path.join(n.base, 'no-existe.git'));
  const p5 = await n.st.publish();
  check('F9 remoto inaccesible → network, commit local, sin excepción', p5.ok === false && p5.reason === 'network' && p5.committed_local === true, JSON.stringify(p5));
  check('F9 …el commit local existe y contiene solo los dos ficheros', filesIn(n.work, 'HEAD').join() === 'docs/data/ticker_tags.json,docs/data/ticker_tags_events.jsonl');
  G(n.work, 'remote', 'set-url', 'origin', n.remote);
  const p6 = await n.st.publish();
  check('F9 al volver la red, reintentar publica el commit pendiente (sin crear otro)', p6.ok === true && p6.pushed === true && p6.committed === false, JSON.stringify(p6));

  // rama equivocada y no escritor
  const w = mkRepo(); await w.st.applyBatch(mkOps.map(([op, args]) => ({ op, args }))); G(w.work, 'checkout', '-q', '-b', 'otra');
  const p7 = await w.st.publish();
  check('F9 rama distinta de master → wrong_branch, no commitea', p7.ok === false && p7.reason === 'wrong_branch' && G(w.work, 'rev-list', '--count', 'HEAD').trim() === '1');
  const nw = createStore({ dataDir: w.dataDir, repoRoot: w.work, hostname: 'OTRA', writerHost: 'H', now });
  await rejectsWith('F10 un no escritor no puede publicar (403)', nw.publish(), 'not_writer', 403);
}

async function main() {
  const suites = [basics, recovery, writer, publish];
  for (const fn of suites) { try { await fn(); } catch (e) { check(`${fn.name} (excepción)`, false, e.stack.split('\n').slice(0, 4).join(' | ')); } }
  const bad = results.filter(r => !r.ok);
  for (const r of results) console.log((r.ok ? '  ok   ' : '  FAIL ') + r.name + (r.detail ? '\n         ' + r.detail : ''));
  console.log(`\n${results.length - bad.length}/${results.length} passed`);
  tmps.forEach(rm);
  process.exit(bad.length ? 1 : 0);
}
main();
