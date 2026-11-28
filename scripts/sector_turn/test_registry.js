'use strict';
// Pruebas del registro semanal (sin red, datos sintéticos, directorios temporales).
//   node scripts/sector_turn/test_registry.js
const fs = require('fs');
const os = require('os');
const path = require('path');
const zlib = require('zlib');
const { execFileSync } = require('child_process');

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'sector_turn_test_'));
process.env.SECTOR_TURN_PRIVATE_DIR = path.join(TMP, 'private');
process.env.SECTOR_TURN_ANCHORS = path.join(TMP, 'anchors.jsonl');
delete process.env.TELEGRAM_BOT_TOKEN;
const R = require('./registry');
const L = require('./lib');
const check = require('./cycle_check');
const copy = require('./cycle_copy');
const log = console.log; console.log = (...a) => { if (!String(a[0]).startsWith('[Telegram')) log(...a); };

let pass = 0, fail = 0;
const ok = (c, msg) => { if (c) pass++; else { fail++; log('FALLO:', msg); } };
async function throws(fn, re, msg) {
  try { await fn(); ok(false, msg + ' (no lanzó error)'); } catch (e) { ok(re.test(e.message), `${msg}: ${e.message}`); }
}
const git = (dir, args) => execFileSync('git', ['-C', dir, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
const gitId = ['-c', 'user.name=t', '-c', 'user.email=t@t'];

// ── datos sintéticos ──
const HOLIDAYS = new Set(['2026-11-26', '2026-12-25', '2027-01-01']);
function sessions(from, to) {
  const out = []; const d = new Date(from + 'T00:00:00Z');
  while (d.toISOString().slice(0, 10) <= to) {
    const s = d.toISOString().slice(0, 10), wd = d.getUTCDay();
    if (wd > 0 && wd < 6 && !HOLIDAYS.has(s)) out.push(s);
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}
function rnd(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32); }
const TICKERS = [...new Set([L.BENCH, ...L.SECTORS, ...L.INDUSTRIES.map(x => x.t), ...check.allTickers()])];
function makeDaily(until, dropOn = {}) {
  const ds = sessions('2021-01-04', until);
  const daily = {};
  TICKERS.forEach((t, k) => {
    const r = rnd(1000 + k); let p = 50 + 50 * r();
    const drift = t === 'XLV' ? -0.0009 : 0;                     // XLV cae: un sector deprimido
    daily[t] = ds.filter(d => !(dropOn[t] || []).includes(d)).map(d => {
      p *= 1 + drift + (r() - 0.5) * 0.03;
      if (t === 'XLV' && d >= '2026-11-16') p *= 1.012;              // y gira al final
      return { date: d, close: p, adj: p };
    });
  });
  return daily;
}
function provider(daily) {
  return {
    daily: async () => daily,
    quotes: async session => {
      const quotes = {}, quoteBases = {};
      for (const t of check.allTickers()) {
        const b = L.cutBars(daily[t] || [], session); if (!b.length) continue;
        const q = L.quoteRets(b); quotes[t] = { ticker: t, asOf: q.last + 'T21:00:00.000Z', m1: q.m1, m3: q.m3 };
        const n = b.length;
        quoteBases[t] = { price: b[n - 1].close, base21_date: b[n - 22].date, base21_close: b[n - 22].close,
          base63_date: b[n - 64].date, base63_close: b[n - 64].close, m1: q.m1, m3: q.m3 };
      }
      return { quotes, quoteErrors: {}, quoteBases };
    },
  };
}

(async () => {
  const daily = makeDaily('2027-01-29');
  const P = provider(daily);
  const recFile = R.recordsPath();
  const priv = R.privDir();

  // 0. Almacenamiento privado = clon de un repositorio «remoto» (bare) local
  const bare = path.join(TMP, 'remote.git');
  execFileSync('git', ['init', '--bare', '-b', 'main', bare]);
  execFileSync('git', ['clone', bare, priv], { stdio: 'ignore' });
  fs.writeFileSync(path.join(priv, 'README.md'), 'registro\n');
  git(priv, ['add', '.']); git(priv, [...gitId, 'commit', '-m', 'init']); git(priv, ['push', 'origin', 'HEAD:main']);

  // 1. Captura de la primera semana a tiempo, con fichero de entradas
  let res = await R.capture({ now: new Date('2026-11-28T08:00:00Z'), provider: P });
  ok(res.done.length === 1 && res.done[0].week === '2026-W48' && res.done[0].status === 'on_time', 'W48 a tiempo: ' + JSON.stringify(res.done));
  let { records } = R.readRecords();
  const r0 = records[0];
  ok(r0.session_date === '2026-11-27' && R.hashRecord(r0) === r0.hash, 'sesión 2026-11-27 y huella recalculable');
  ok(r0.inputs?.file === 'inputs/2026-W48.json.gz' && fs.existsSync(path.join(priv, r0.inputs.file)), 'fichero de entradas guardado');
  ok(r0.cycle_real.original_equals_copy === true && r0.cycle_series === copy.COPY_VERSION, 'Cycle original = copia; serie de Cycle registrada');
  ok(R.verify({ deep: true }).ok, 'verify --deep: la lectura se reconstruye idéntica desde las entradas');

  // 2. Reconstrucción independiente de Yahoo: la lectura sale de las entradas guardadas, no de datos nuevos
  const blob = R.readInputs(r0.inputs).blob;
  ok(R.compareReading(r0, R.computeReading(blob)).length === 0, 'computeReading(entradas) = registro');
  ok(blob.daily.XLV.dates.length === 900 && blob.quotes.SPY.base63_close != null, 'entradas: 900 sesiones y cierres base de Cycle');

  // 3. Publicar: anclaje a tiempo (antes del lunes) y luego otro tardío
  let pub = await R.publish({ now: new Date('2026-11-29T10:00:00Z') });
  ok(pub.length === 1 && pub[0].anchored_late === false, 'W48 anclada a tiempo: ' + JSON.stringify(pub));
  ok(R.verify({ requireAnchors: true }).ok, 'todo anclado');
  res = await R.capture({ now: new Date('2026-12-05T08:00:00Z'), provider: P });
  pub = await R.publish({ now: new Date('2026-12-08T10:00:00Z') });
  ok(pub.length === 1 && pub[0].week === '2026-W49' && pub[0].anchored_late === true, 'W49 capturada a tiempo pero anclada tras el lunes: anchored_late');

  // 4. Repetir no duplica; semana con retraso; hueco; viernes festivo (25-dic)
  res = await R.capture({ now: new Date('2026-12-06T08:00:00Z'), provider: P });
  ok(res.done.length === 0, 'una segunda pasada no añade nada');
  res = await R.capture({ now: new Date('2026-12-30T10:00:00Z'), provider: P });
  const st = Object.fromEntries(res.done.map(d => [d.week, d]));
  ok(st['2026-W50']?.status === 'gap', 'W50 queda como hueco (más de 14 días)');
  ok(st['2026-W51']?.status === 'late_recovered', 'W51 recuperada con retraso');
  ok(st['2026-W52']?.status === 'late_recovered' && st['2026-W52']?.session === '2026-12-24', 'W52: viernes festivo, sesión el jueves 24');
  ok(R.verify({ deep: true }).ok, 'verify --deep ok con hueco');

  // 5. Viernes sin dato antes del sábado a mediodía: espera; dos sectores sin dato: aborta sin escribir
  res = await R.capture({ now: new Date('2027-01-01T23:00:00Z'), provider: P });
  ok(res.done.some(d => d.week === '2026-W53' && d.status === 'waiting'), 'W53 con viernes festivo antes del sábado: espera');
  res = await R.capture({ now: new Date('2027-01-02T13:00:00Z'), provider: P });
  ok(res.done.some(d => d.week === '2026-W53' && d.session === '2026-12-31'), 'W53 (año ISO de 53 semanas) registrada con la sesión del jueves 31');
  const nBefore = R.readRecords().records.length;
  await throws(() => R.capture({ now: new Date('2027-01-09T08:00:00Z'), provider: provider(makeDaily('2027-01-29', { XLB: ['2027-01-08'], XLK: ['2027-01-08'] })) }),
    /faltan datos de 2 sectores/, 'dos sectores ausentes abortan');
  ok(R.readRecords().records.length === nBefore && !fs.existsSync(path.join(priv, 'inputs', '2027-W01.json.gz')), 'el aborto no escribe nada');
  res = await R.capture({ now: new Date('2027-01-08T23:00:00Z'), provider: provider(makeDaily('2027-01-29', { [L.BENCH]: ['2027-01-08'] })) });
  ok(res.done.some(d => d.status === 'waiting'), 'sin la sesión del viernes antes del sábado: espera');
  res = await R.capture({ now: new Date('2027-01-09T08:00:00Z'), provider: provider(makeDaily('2027-01-29', { XLB: ['2027-01-08'] })) });
  ({ records } = R.readRecords());
  ok(records[records.length - 1].units.find(u => u.ticker === 'XLB').status === 'missing_session', 'un sector sin dato queda anotado');

  // 6. Alteraciones del registro y de las entradas
  const good = fs.readFileSync(recFile, 'utf8');
  const lines = good.trim().split('\n');
  const alter = (txt, kind) => { fs.writeFileSync(recFile, txt); const v = R.verify(); ok(!v.ok && v.problems.some(p => p.kind === kind), `detecta ${kind}: ${JSON.stringify(v.problems).slice(0, 160)}`); };
  alter(good.replace('"session_date":"2026-11-27"', '"session_date":"2026-11-26"'), 'altered');
  alter([lines[0], ...lines.slice(2)].join('\n') + '\n', 'chain_break');
  alter([...lines, lines[lines.length - 1]].join('\n') + '\n', 'duplicate_week');
  alter(good + lines[0].slice(0, 40), 'partial_tail');
  fs.writeFileSync(recFile, good + lines[0].slice(0, 40));
  await throws(() => R.capture({ now: new Date('2027-01-16T08:00:00Z'), provider: P }), /línea incompleta/, 'con la cola cortada no escribe');
  fs.writeFileSync(recFile, good);
  const inF = path.join(priv, 'inputs', '2026-W49.json.gz');
  const inBuf = fs.readFileSync(inF);
  const b49 = JSON.parse(zlib.gunzipSync(inBuf).toString()); b49.daily.XLV.adj[100] *= 1.0001;
  fs.writeFileSync(inF, zlib.gzipSync(Buffer.from(JSON.stringify(b49))));
  ok(R.verify().problems.some(p => p.kind === 'inputs_altered'), 'entradas alteradas: detectado');
  fs.unlinkSync(inF);
  ok(R.verify().problems.some(p => p.kind === 'inputs_missing'), 'entradas borradas: detectado');
  fs.writeFileSync(inF, inBuf);
  ok(R.verify({ deep: true }).ok, 'restaurado: verify --deep ok');

  // 7. Anclajes alterados o sin registro
  const aTxt = fs.readFileSync(R.anchorsPath(), 'utf8');
  fs.writeFileSync(R.anchorsPath(), aTxt.replace(/"hash":"[0-9a-f]{4}/, '"hash":"0000'));
  ok(R.verify().problems.some(p => p.kind === 'anchor_mismatch'), 'anclaje alterado detectado');
  fs.writeFileSync(R.anchorsPath(), aTxt);
  fs.writeFileSync(recFile, lines.slice(0, 1).join('\n') + '\n');
  ok(R.verify().problems.some(p => p.kind === 'anchor_without_record'), 'registro borrado tras anclarlo: detectado');
  fs.writeFileSync(recFile, good);

  // 8. Suplemento para un registro antiguo sin fichero de entradas (esquema 1)
  {
    const SAVE = process.env.SECTOR_TURN_PRIVATE_DIR, SAVEA = process.env.SECTOR_TURN_ANCHORS;
    process.env.SECTOR_TURN_PRIVATE_DIR = path.join(TMP, 'private_s1');
    process.env.SECTOR_TURN_ANCHORS = path.join(TMP, 'anchors_s1.jsonl');
    const prev = null;
    const bl = R.buildInputs({ week: '2026-W48', session: '2026-11-27', daily, ...(await P.quotes('2026-11-27')) });
    const reading = R.computeReading(bl);
    const old = R.makeRecord({ week: '2026-W48', session: '2026-11-27', capturedUtc: '2026-11-28T08:00:00Z', status: 'on_time',
      deadlineUtc: '2026-11-30T14:30:00.000Z', inputsRef: { note: 'esquema 1: sin fichero' }, reading, prev, versions: {} });
    R.appendRecord(old);
    ok(R.verify().warnings.some(w => w.kind === 'no_inputs_file'), 'registro sin entradas: aviso');
    const sup = await R.supplement({ week: '2026-W48', provider: P, now: new Date('2026-11-28T12:00:00Z') });
    ok(sup.reproduces_hash === old.hash, 'suplemento reproduce la lectura');
    await R.capture({ now: new Date('2026-12-05T08:00:00Z'), provider: P });
    const rs = R.readRecords().records;
    ok(rs[1].supplements.length === 1 && rs[1].supplements[0].week === '2026-W48', 'el suplemento queda encadenado en el registro siguiente');
    ok(R.verify({ deep: true }).ok && !R.verify().warnings.some(w => w.kind === 'no_inputs_file'), 'verify --deep valida el suplemento');
    process.env.SECTOR_TURN_PRIVATE_DIR = SAVE; process.env.SECTOR_TURN_ANCHORS = SAVEA;
  }

  // 9. Repositorio privado: push normal, push con otro commit remoto (rebase), conflicto real (no publica)
  let p1 = R.pushPrivate({ message: 'prueba' });
  ok(p1.pushed && git(bare, ['log', '--oneline', 'main']).split('\n').length === 2, 'push al repositorio privado');
  const other = path.join(TMP, 'other'); execFileSync('git', ['clone', bare, other], { stdio: 'ignore' });
  fs.writeFileSync(path.join(other, 'NOTE.md'), 'otra máquina\n'); git(other, ['add', '.']); git(other, [...gitId, 'commit', '-m', 'otro']); git(other, ['push']);
  await R.capture({ now: new Date('2027-01-16T08:00:00Z'), provider: P });
  p1 = R.pushPrivate({ message: 'W02' });
  ok(p1.pushed && p1.attempts === 2, 'push con rebase tras un commit ajeno: ' + JSON.stringify(p1));
  git(other, ['pull', '--ff-only']);
  fs.appendFileSync(path.join(other, 'records.jsonl'), '{"falso":1}\n'); git(other, ['add', '.']); git(other, [...gitId, 'commit', '-m', 'conflicto']); git(other, ['push']);
  const anchorsBefore = fs.readFileSync(R.anchorsPath(), 'utf8');
  await throws(() => R.runWeekly({ privateGit: true, now: new Date('2027-01-23T08:00:00Z'), provider: P }), /conflicto real|push al repositorio privado/, 'conflicto en el privado: falla');
  ok(fs.readFileSync(R.anchorsPath(), 'utf8') === anchorsBefore, 'si el push privado falla no se publica ninguna huella');

  // 10. Cycle cambiado: la captura se detiene
  const orig = check.staticCheck;
  check.staticCheck = () => ({ ok: false, problems: ['huella distinta (simulado)'] });
  await throws(() => R.capture({ now: new Date('2027-01-30T08:00:00Z'), provider: P }), /Cycle ha cambiado/, 'Cycle cambiado detiene el registro');
  check.staticCheck = orig;
  ok(R.canonical({ b: 1, a: [2, { d: 3, c: 4 }] }) === R.canonical({ a: [2, { c: 4, d: 3 }], b: 1 }), 'JSON canónico estable');

  log(`\n${pass} pasadas, ${fail} fallidas`);
  fs.rmSync(TMP, { recursive: true, force: true });
  process.exit(fail ? 1 : 0);
})().catch(e => { log('ERROR', e); process.exit(1); });
