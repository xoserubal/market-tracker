'use strict';
// Registro semanal prospectivo de giros sectoriales (preregistro v2, aprobado por el usuario 2026-11-28).
//
// Cada semana bursátil completa genera UN registro inmutable con lo que Market Tracker veía al cierre de su última
// sesión: ratios D/G de los 11 sectores SPDR y de las 25 industrias del libro, Cycle real (pestaña, verificado contra
// cycle.html) y Cycle simplificado, concordancias y versiones. Se registran todas las semanas, haya o no señales.
//
// Reconstrucción exacta: los datos de entrada de cada semana (ventana de 900 sesiones de cada ETF, cierres base de
// Cycle) se guardan en inputs/<semana>.json.gz y el registro lleva el sha256 de su JSON canónico. La lectura se
// calcula SIEMPRE a partir de ese fichero (computeReading), así que `verify --deep` la recalcula y debe salir
// idéntica aunque Yahoo revise después sus precios ajustados.
//
// Integridad
// - records.jsonl solo se amplía. Cada línea lleva prev_hash y hash = sha256 del JSON canónico del registro sin hash.
// - Publicación (comando publish, después de guardar en el almacenamiento privado): huella, fecha y anterior en
//   docs/data/sector_turn_anchors.jsonl (repositorio público) y por Telegram. anchored_late = el anclaje se hizo
//   después de la apertura de la sesión siguiente (on_time_deadline_utc). El contenido no se publica.
// - verify detecta registros alterados, cadena rota, duplicados, semanas omitidas, cola cortada, ficheros de entrada
//   ausentes o alterados, anclajes que no casan y anclajes sin registro; avisa de cambios de versión de Cycle.
// - Si cycle.html cambia, la captura se detiene. Una nueva versión de Cycle exige autorización, una copia nueva
//   (COPY_VERSION distinto) y abre una serie nueva: el análisis separa por versión.
//
// Uso:
//   node scripts/sector_turn/registry.js capture [--now ISO]
//   node scripts/sector_turn/registry.js publish
//   node scripts/sector_turn/registry.js run-weekly --private-git      (pipeline: capture → push privado → publish)
//   node scripts/sector_turn/registry.js verify [--deep] [--require-anchors]
//   node scripts/sector_turn/registry.js status
//   node scripts/sector_turn/registry.js supplement --week 2026-W48   (entradas de un registro de esquema 1)
// Almacenamiento privado: SECTOR_TURN_PRIVATE_DIR (por defecto <repo>/private/sector_turn_registry, fuera de git).
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');
const L = require('./lib');
const check = require('./cycle_check');
const cycleCopy = require('./cycle_copy');

const SCHEMA = 'sector-turn-registry-2';
const SCHEMAS_OK = new Set(['sector-turn-registry-1', SCHEMA]);
const REPO = path.join(__dirname, '..', '..');
const START_WEEK = '2026-W48';                 // primera semana registrada (sesión 2026-11-27)
const LATE_LIMIT_DAYS = 14;
const SUPP_TOL = 1e-4;                       // tolerancia relativa de un suplemento aproximado
const INPUT_BARS = 900;                        // sesiones guardadas por ETF: 756 (D) + 8 semanas (independencia) + margen
const ANCHORS_DEFAULT = path.join(REPO, 'docs', 'data', 'sector_turn_anchors.jsonl');
const anchorsPath = () => process.env.SECTOR_TURN_ANCHORS || ANCHORS_DEFAULT;
const privDir = () => process.env.SECTOR_TURN_PRIVATE_DIR || path.join(REPO, 'private', 'sector_turn_registry');
const recordsPath = () => path.join(privDir(), 'records.jsonl');
const inputsDir = () => path.join(privDir(), 'inputs');
const pendingSupplementsPath = () => path.join(privDir(), 'pending_supplements.json');

// ── utilidades ──────────────────────────────────────────────────────────────
function canonical(v) {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().filter(k => v[k] !== undefined)
    .map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
  if (typeof v === 'number' && !Number.isFinite(v)) return 'null';
  return JSON.stringify(v);
}
const sha = s => crypto.createHash('sha256').update(s).digest('hex');
const fileSha = f => sha(fs.readFileSync(f));
function hashRecord(rec) { const { hash, ...rest } = rec; return sha(canonical(rest)); }

function nyOffsetMin(dateStr) {                 // minutos de diferencia NY − UTC ese día (DST incluido)
  const d = new Date(dateStr + 'T12:00:00Z');
  const p = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', hourCycle: 'h23', day: '2-digit' })
    .formatToParts(d).reduce((a, x) => (a[x.type] = x.value, a), {});
  let diff = (+p.hour - 12) * 60;
  if (+p.day !== d.getUTCDate()) diff -= 24 * 60;
  return diff;
}
function nyToUtc(dateStr, hh, mm) {
  return new Date(Date.parse(dateStr + 'T00:00:00Z') + ((hh * 60 + mm) - nyOffsetMin(dateStr)) * 60000);
}
function addDays(dateStr, n) { const d = new Date(dateStr + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
function weekFriday(week) {                     // viernes de la semana ISO
  const [y, w] = week.split('-W').map(Number);
  const jan4 = new Date(Date.UTC(y, 0, 4));
  const mon = new Date(jan4); mon.setUTCDate(jan4.getUTCDate() - ((jan4.getUTCDay() + 6) % 7) + (w - 1) * 7);
  return addDays(mon.toISOString().slice(0, 10), 4);
}
const nextWeek = week => L.isoWeek(addDays(weekFriday(week), 7));

// ── almacenamiento ──────────────────────────────────────────────────────────
function readRecords(file = recordsPath()) {
  if (!fs.existsSync(file)) return { records: [], partialTail: null };
  const raw = fs.readFileSync(file, 'utf8');
  const lines = raw.split('\n');
  const records = []; let partialTail = null;
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (!ln) continue;
    try { records.push(JSON.parse(ln)); } catch {
      if (i === lines.length - 1) partialTail = ln;          // escritura cortada al final
      else throw new Error(`records.jsonl: línea ${i + 1} ilegible (no es la última): alteración`);
    }
  }
  if (!partialTail && raw.length && !raw.endsWith('\n')) partialTail = lines[lines.length - 1];
  return { records, partialTail };
}

function appendLine(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const fd = fs.openSync(file, 'a');
  try { fs.writeSync(fd, canonical(obj) + '\n'); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
}
const appendRecord = (rec, file = recordsPath()) => appendLine(file, rec);
const appendAnchor = a => appendLine(anchorsPath(), a);
function readAnchors(file = anchorsPath()) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
}

// Ficheros de entrada: el contenido de referencia es el JSON canónico (la huella no depende de la compresión).
function writeInputs(name, blob) {
  const txt = canonical(blob);
  const h = sha(txt);
  fs.mkdirSync(inputsDir(), { recursive: true });
  const f = path.join(inputsDir(), name);
  if (fs.existsSync(f)) {                       // nunca se sobrescribe: si ya existe tiene que ser idéntico
    if (sha(zlib.gunzipSync(fs.readFileSync(f)).toString('utf8')) !== h) throw new Error(`${name} ya existe con otro contenido`);
  } else {
    const tmp = f + '.tmp';
    fs.writeFileSync(tmp, zlib.gzipSync(Buffer.from(txt, 'utf8'), { level: 9 }));
    fs.renameSync(tmp, f);
  }
  return { file: `inputs/${name}`, sha256: h, bytes_json: Buffer.byteLength(txt) };
}
function readInputs(ref) {
  const f = path.join(privDir(), ref.file);
  if (!fs.existsSync(f)) return { ok: false, why: 'missing' };
  const txt = zlib.gunzipSync(fs.readFileSync(f)).toString('utf8');
  if (sha(txt) !== ref.sha256) return { ok: false, why: 'altered' };
  return { ok: true, blob: JSON.parse(txt) };
}

// ── unidades y cálculo de la lectura (a partir del fichero de entradas) ────────
const UNITS = () => [
  ...L.SECTORS.map(t => ({ ticker: t, kind: 'sector', exposed: true })),
  ...L.INDUSTRIES.map(x => ({ ticker: x.t, kind: 'industry', exposed: x.exposed, book_pos: x.pos, book_category: x.book })),
];
const PROXIES = () => [...new Set(cycleCopy.CYCLE_MAP.flatMap(p => p.sectors.flatMap(s => s.tickers.filter(t => t.role === 'proxy').map(t => t.ticker))))];
const DAILY_TICKERS = () => [...new Set([L.BENCH, ...UNITS().map(u => u.ticker), ...PROXIES()])];

const barsOf = blob => t => {
  const d = blob.daily[t];
  return d ? d.dates.map((date, i) => ({ date, adj: d.adj[i], close: d.close[i] })) : [];
};

// La lectura de una semana. Función pura del fichero de entradas: la usan la captura y la verificación.
function computeReading(blob) {
  const session = blob.session_date;
  const get = barsOf(blob);
  const spy = get(L.BENCH);
  const units = [], missing = [];
  for (const u of UNITS()) {
    const bars = get(u.ticker);
    const last = bars[bars.length - 1];
    if (!last || last.date !== session) { missing.push(u.ticker); units.push({ ...u, status: 'missing_session', last_date: last?.date ?? null }); continue; }
    const ratio = L.ratioSeries(bars, spy);
    if (!ratio.length || ratio[ratio.length - 1].date !== session) { missing.push(u.ticker); units.push({ ...u, status: 'missing_ratio' }); continue; }
    const wk = L.weeklyEvents(ratio, session);
    const cur = wk[wk.length - 1];
    if (!cur || cur.date !== session || cur.D == null) { units.push({ ...u, status: 'not_evaluable' }); continue; }
    const prior = wk.slice(Math.max(0, wk.length - 1 - L.INDEP_WEEKS), wk.length - 1).filter(r => r.DG).map(r => r.week);
    units.push({ ...u, status: 'ok', ratio: cur.ratio, max756: cur.max756, dist_max756: cur.dist_max756, sma50: cur.sma50,
      above_sma50: cur.above_sma50, prev_week_date: cur.prev_week_date ?? null, prev_above_sma50: cur.prev_above_sma50,
      D: cur.D, G: cur.G, DG: cur.DG, dg_prior_8w_from_history: prior, independent_from_history: cur.DG ? prior.length === 0 : null });
  }

  // Cycle real: lo que usa la pestaña son m1/m3 de /api/quote; se calculan original (cycle.html) y copia.
  const rows = {};
  for (const [t, q] of Object.entries(blob.quotes)) rows[t] = { ticker: t, m1: q.m1, m3: q.m3 };
  const both = check.computeBoth(rows);
  const cyclePhases = both.phases.map(p => ({ order: p.order, phase: p.phase, pos: L.ORDER_TO_POS[p.order], score: p.score,
    breadth: p.breadth, dispersion: p.dispersion, acceleration: p.acceleration, loaded: p.loaded, total: p.total }));
  const dom = L.dominantOf(cyclePhases);
  const staleQuotes = Object.entries(blob.quotes).filter(([, q]) => q.as_of !== session).map(([t, q]) => `${t}:${q.as_of}`);
  const inconsistentQuotes = Object.entries(blob.quotes).filter(([, q]) => q.bases_consistent === false).map(([t]) => t);

  // Cycle simplificado (solo proxies): la misma reconstrucción que el estudio histórico.
  const dailyBars = {}; for (const t of Object.keys(blob.daily)) dailyBars[t] = get(t);
  const simp = L.simplifiedPhaseScores(cycleCopy.CYCLE_MAP, dailyBars, session);
  const simpDom = L.dominantOf(simp);

  const nextReal = dom?.next_pos ?? null, nextSimp = simpDom?.next_pos ?? null;
  const conc = (u, next) => u.kind === 'sector'
    ? { cycle: L.concordance(u.ticker, next, L.SECTOR_POS_CYCLE), cycle_plus_xlre: L.concordance(u.ticker, next, L.SECTOR_POS_WITH_XLRE) }
    : { book: u.book_pos == null || next == null ? { mapped: false, concordant: null } : { mapped: true, pos: u.book_pos, concordant: u.book_pos === next } };
  const ok = units.filter(u => u.status === 'ok');
  const events = ok.filter(u => u.DG).map(u => ({ ticker: u.ticker, kind: u.kind, exposed: u.exposed,
    independent_from_history: u.independent_from_history, dist_max756: u.dist_max756,
    concordance_real_cycle: conc(u, nextReal), concordance_simplified_cycle: conc(u, nextSimp) }));
  const inNext = (u, next) => u.kind === 'sector' ? L.SECTOR_POS_WITH_XLRE[u.ticker] === next : u.book_pos === next;
  const lists = {
    D: ok.filter(u => u.D).map(u => u.ticker), G: ok.filter(u => u.G).map(u => u.ticker), DG: events.map(e => e.ticker),
    D_not_G: ok.filter(u => u.D && u.G === false).map(u => u.ticker), G_not_D: ok.filter(u => u.G && u.D === false).map(u => u.ticker),
    // Caso C (vigilancia, no señal): deprimido, en la posición siguiente según Cycle real (tabla con XLRE), sin giro.
    caseC_watch: ok.filter(u => u.D && !u.G && nextReal != null && inNext(u, nextReal)).map(u => u.ticker),
  };
  return {
    data_quality: { missing_units: missing, quote_errors: blob.quote_errors || {}, stale_quotes: staleQuotes, inconsistent_quote_bases: inconsistentQuotes },
    units,
    cycle_real: { original_sha256: both.original_sha256, copy_version: cycleCopy.COPY_VERSION, original_equals_copy: both.equal,
      diffs: both.diffs.slice(0, 20), dominant_matches_summary: dom?.phase === (both.summary?.dominant ?? null),
      phases: cyclePhases, dominant: dom, next_pos_label: nextReal ? L.POS_LABEL[nextReal] : null,
      next_pos_sectors_cycle: Object.keys(L.SECTOR_POS_CYCLE).filter(t => L.SECTOR_POS_CYCLE[t] === nextReal),
      next_pos_sectors_with_xlre: Object.keys(L.SECTOR_POS_WITH_XLRE).filter(t => L.SECTOR_POS_WITH_XLRE[t] === nextReal) },
    cycle_simplified: { phases: simp.map(p => ({ order: p.order, pos: p.pos, score: p.score, used: p.used })), dominant: simpDom },
    events, lists,
  };
}

// Fichero de entradas de una semana a partir de los datos descargados.
function buildInputs({ week, session, daily, quotes, quoteBases, quoteErrors }) {
  const d = {};
  for (const t of DAILY_TICKERS()) {
    const b = L.cutBars(daily[t] || [], session).slice(-INPUT_BARS);
    d[t] = { dates: b.map(x => x.date), adj: b.map(x => x.adj), close: b.map(x => x.close) };
  }
  const q = {};
  for (const [t, x] of Object.entries(quotes)) {
    const base = quoteBases?.[t] || {};
    q[t] = { as_of: x.asOf?.slice(0, 10) ?? null, m1: x.m1 ?? null, m3: x.m3 ?? null, price: base.price ?? null,
      base21_date: base.base21_date ?? null, base21_close: base.base21_close ?? null,
      base63_date: base.base63_date ?? null, base63_close: base.base63_close ?? null,
      bases_consistent: base.price == null ? null : (base.m1 === (x.m1 ?? null) && base.m3 === (x.m3 ?? null)) };
  }
  return { schema: 'sector-turn-inputs-1', week, session_date: session, input_bars: INPUT_BARS, daily: d, quotes: q,
    quote_errors: quoteErrors || {},
    sources: { daily: 'Yahoo chart v8 1d (period1/period2 o range=5y): date local de la bolsa, close ajustado por splits, adjclose por splits y dividendos',
      quotes: 'shared/quote-lib.js buildQuoteData con cutoffDate (lo que /api/quote sirve a la pestaña Cycle); bases leídas de la misma serie' } };
}

function makeRecord({ week, session, capturedUtc, status, deadlineUtc, inputsRef, reading, prev, versions, supplements }) {
  const rec = {
    schema: SCHEMA, seq: prev ? prev.seq + 1 : 1, prev_hash: prev ? prev.hash : 'GENESIS',
    kind: 'week', week, session_date: session, captured_utc: capturedUtc, capture_status: status,
    on_time_deadline_utc: deadlineUtc, versions, cycle_series: cycleCopy.COPY_VERSION,
    rules: { D_LOOKBACK: L.D_LOOKBACK, D_DEPTH: L.D_DEPTH, G_SMA: L.G_SMA, INDEP_WEEKS: L.INDEP_WEEKS, INPUT_BARS,
      order_to_pos: L.ORDER_TO_POS, sector_pos_cycle: L.SECTOR_POS_CYCLE, sector_pos_with_xlre: L.SECTOR_POS_WITH_XLRE,
      industries: L.INDUSTRIES },
    inputs: inputsRef, supplements: supplements || [],
    ...reading,
  };
  rec.hash = hashRecord(rec);
  return rec;
}

function gapRecord({ week, capturedUtc, prev, reason }) {
  const rec = { schema: SCHEMA, seq: prev ? prev.seq + 1 : 1, prev_hash: prev ? prev.hash : 'GENESIS', kind: 'gap', week,
    session_date: null, captured_utc: capturedUtc, capture_status: 'gap', cycle_series: cycleCopy.COPY_VERSION, reason };
  rec.hash = hashRecord(rec);
  return rec;
}

// ── verificación ────────────────────────────────────────────────────────────
const COMPARE_UNIT = ['status', 'ratio', 'max756', 'dist_max756', 'sma50', 'above_sma50', 'prev_above_sma50', 'D', 'G', 'DG',
  'dg_prior_8w_from_history', 'independent_from_history'];
// tol = diferencia relativa admitida en los campos numéricos de los ETFs (0 = exacto). Señales, listas y Cycle real
// (que sale de m1/m3 enteros) siempre exactos.
const NUM_FIELDS = new Set(['ratio', 'max756', 'dist_max756', 'sma50']);
function compareReading(rec, reading, tol = 0) {
  const diffs = [];
  let maxRel = 0;
  const ru = new Map(rec.units.map(u => [u.ticker, u]));
  for (const u of reading.units) {
    const a = ru.get(u.ticker);
    if (!a) { diffs.push(`${u.ticker}: no está en el registro`); continue; }
    if (a.status !== 'ok' && u.status !== 'ok') continue;
    for (const k of COMPARE_UNIT) {
      const x = a[k] ?? null, y = u[k] ?? null;
      if (NUM_FIELDS.has(k) && typeof x === 'number' && typeof y === 'number') {
        const rel = Math.abs(x - y) / Math.max(Math.abs(x), 1e-12);
        if (rel > maxRel) maxRel = rel;
        if (rel > tol) diffs.push(`${u.ticker}.${k}: ${x} ≠ ${y}`);
      } else if (!check.same(x, y)) diffs.push(`${u.ticker}.${k}: ${JSON.stringify(x)} ≠ ${JSON.stringify(y)}`);
    }
  }
  const pa = rec.cycle_real.phases.map(p => [p.order, p.score]), pb = reading.cycle_real.phases.map(p => [p.order, p.score]);
  if (!check.same(pa, pb)) diffs.push('Cycle real: puntuaciones distintas');
  if (rec.cycle_real.dominant?.phase !== reading.cycle_real.dominant?.phase) diffs.push('Cycle real: fase dominante distinta');
  if (!check.same(rec.cycle_simplified.phases.map(p => p.score), reading.cycle_simplified.phases.map(p => p.score))) diffs.push('Cycle simplificado distinto');
  if (!check.same(rec.lists, reading.lists)) diffs.push('listas D/G distintas');
  diffs.maxRel = maxRel;
  return diffs;
}

function verify({ file = recordsPath(), anchorsFile = anchorsPath(), requireAnchors = false, requireAnchorsFromSeq = null, deep = false } = {}) {
  const problems = [], warnings = [];
  let records = [];
  try {
    const r = readRecords(file);
    records = r.records;
    if (r.partialTail) problems.push({ kind: 'partial_tail', detail: 'última línea incompleta (escritura cortada)' });
  } catch (e) { problems.push({ kind: 'unreadable', detail: e.message }); return { ok: false, problems, warnings, n: 0 }; }
  let prev = 'GENESIS';
  const seenWeeks = new Map();
  const supplementOf = new Map();
  records.forEach((rec, i) => {
    if (!SCHEMAS_OK.has(rec.schema)) problems.push({ kind: 'schema', at: i + 1, schema: rec.schema });
    if (rec.seq !== i + 1) problems.push({ kind: 'seq', at: i + 1, found: rec.seq });
    if (rec.prev_hash !== prev) problems.push({ kind: 'chain_break', at: i + 1, week: rec.week });
    if (hashRecord(rec) !== rec.hash) problems.push({ kind: 'altered', at: i + 1, week: rec.week });
    if (seenWeeks.has(rec.week)) problems.push({ kind: 'duplicate_week', week: rec.week, seqs: [seenWeeks.get(rec.week), rec.seq] });
    seenWeeks.set(rec.week, rec.seq);
    if (i > 0 && rec.week !== nextWeek(records[i - 1].week)) problems.push({ kind: 'omitted_weeks', after: records[i - 1].week, next: rec.week });
    if (i === 0 && rec.week !== START_WEEK) problems.push({ kind: 'bad_start', week: rec.week });
    const series = rec.cycle_series || rec.cycle_real?.copy_version;
    const prevSeries = i > 0 ? (records[i - 1].cycle_series || records[i - 1].cycle_real?.copy_version) : series;
    if (series && prevSeries && series !== prevSeries) warnings.push({ kind: 'cycle_series_change', at: rec.week, from: prevSeries, to: series });
    for (const s of rec.supplements || []) supplementOf.set(s.week, s);
    const refs = [];
    if (rec.inputs?.file) refs.push({ ref: rec.inputs, rec });
    for (const s of rec.supplements || []) refs.push({ ref: s, rec: records.find(r => r.week === s.week), supplement: true });
    for (const { ref, rec: target, supplement } of refs) {
      const got = readInputs(ref);
      if (!got.ok) { problems.push({ kind: `inputs_${got.why}`, week: target?.week ?? ref.week, file: ref.file }); continue; }
      if (deep && target) {
        const diffs = compareReading(target, computeReading(got.blob), supplement && ref.exact === false ? ref.tolerance : 0);
        if (diffs.length) problems.push({ kind: 'reconstruction_mismatch', week: target.week, supplement: !!supplement, diffs: diffs.slice(0, 10) });
      }
    }
    prev = rec.hash;
  });
  for (const rec of records) if (rec.kind === 'week' && !rec.inputs?.file && !supplementOf.has(rec.week)) warnings.push({ kind: 'no_inputs_file', week: rec.week });
  const anchors = readAnchors(anchorsFile);
  const bySeq = new Map(records.map(r => [r.seq, r]));
  for (const a of anchors) {
    const r = bySeq.get(a.seq);
    if (!r) problems.push({ kind: 'anchor_without_record', seq: a.seq, week: a.week });
    else if (r.hash !== a.hash || r.prev_hash !== a.prev_hash || r.week !== a.week) problems.push({ kind: 'anchor_mismatch', seq: a.seq, week: a.week });
  }
  const anchored = new Set(anchors.map(a => a.seq));
  const unanchored = records.filter(r => !anchored.has(r.seq));
  const must = unanchored.filter(r => requireAnchors || (requireAnchorsFromSeq != null && r.seq >= requireAnchorsFromSeq));
  const soft = unanchored.filter(r => !must.includes(r));
  if (must.length) problems.push({ kind: 'unanchored', weeks: must.map(r => r.week) });
  if (soft.length) warnings.push({ kind: 'unanchored', weeks: soft.map(r => r.week) });
  return { ok: problems.length === 0, problems, warnings, n: records.length, last: records[records.length - 1] || null };
}

// ── versiones ───────────────────────────────────────────────────────────────
function versions() {
  const f = n => path.join(__dirname, n);
  return {
    schema: SCHEMA, lib: L.LIB_VERSION,
    lib_sha256: fileSha(f('lib.js')), registry_sha256: fileSha(f('registry.js')), cycle_check_sha256: fileSha(f('cycle_check.js')),
    cycle_copy_sha256: fileSha(f('cycle_copy.js')), cycle_copy_version: cycleCopy.COPY_VERSION,
    cycle_original_fragments_sha256: check.staticCheck().original_sha256,
    cycle_html_sha256: fileSha(path.join(REPO, 'cycle.html')),
    quote_lib_sha256: fileSha(path.join(REPO, 'shared', 'quote-lib.js')),
    node: process.version,
  };
}

// ── Telegram ────────────────────────────────────────────────────────────────
async function telegram(text) {
  const token = process.env.TELEGRAM_BOT_TOKEN, chat = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chat) { console.log('[Telegram no configurado]', text); return false; }
  try {
    const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chat_id: chat, text: text.slice(0, 3900) }) });
    return r.ok;
  } catch { return false; }
}

// ── descarga ────────────────────────────────────────────────────────────────
async function fetchAll(range = '5y') {
  const daily = {};
  for (const t of DAILY_TICKERS()) { try { daily[t] = (await L.fetchDaily(t, range)).bars; } catch { daily[t] = []; } }
  return daily;
}
// Cierres base de m1/m3 leídos de la misma serie y con la misma lógica de índices que buildQuoteData.
async function quoteBase(symbol, cutoff) {
  const { fetchYahooChartFresh } = require('../../shared/quote-lib');
  const { ok, result } = await fetchYahooChartFresh(symbol, '3y', '1d');
  if (!ok || !result) return null;
  const closes = [...(result.indicators?.quote?.[0]?.close ?? [])], ts = [...(result.timestamp ?? [])];
  const off = result.meta?.gmtoffset ?? 0;
  const barDate = t => new Date((t + off) * 1000).toISOString().slice(0, 10);
  while (ts.length && barDate(ts[ts.length - 1]) > cutoff) { closes.pop(); ts.pop(); }
  while (closes.length && closes[closes.length - 1] == null) { closes.pop(); ts.pop(); }
  if (!closes.length) return null;
  const n = closes.length, price = closes[n - 1];
  const pct = (a, b) => b ? Math.round((a - b) / Math.abs(b) * 100) : null;
  const at = d => { const i = n - 1 - d; return i >= 0 ? { date: barDate(ts[i]), close: closes[i] } : { date: null, close: null }; };
  const b21 = at(21), b63 = at(63);
  return { price, base21_date: b21.date, base21_close: b21.close, base63_date: b63.date, base63_close: b63.close,
    m1: b21.close ? pct(price, b21.close) : null, m3: b63.close ? pct(price, b63.close) : null };
}
async function fetchQuotes(session) {
  const { buildQuoteData } = require('../../shared/quote-lib');
  const quotes = {}, quoteErrors = {}, quoteBases = {};
  for (const t of check.allTickers()) {
    try { quotes[t] = await buildQuoteData(t, { cutoffDate: session }); } catch (e) { quoteErrors[t] = e.message; continue; }
    try { quoteBases[t] = await quoteBase(t, session); } catch { quoteBases[t] = null; }
  }
  return { quotes, quoteErrors, quoteBases };
}

// ── captura ─────────────────────────────────────────────────────────────────
function dueWeeks(lastWeek, now) {
  const out = [];
  let w = lastWeek ? nextWeek(lastWeek) : START_WEEK;
  for (let k = 0; k < 60; k++) {
    if (now < nyToUtc(weekFriday(w), 16, 15)) break;      // la semana aún no ha terminado
    out.push(w); w = nextWeek(w);
  }
  return out;
}

function readPendingSupplements() {
  const p = pendingSupplementsPath();
  return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : [];
}

async function capture({ dryRun = false, now = new Date(), provider = null } = {}) {
  const { records, partialTail } = readRecords();
  if (partialTail) throw new Error('records.jsonl termina en una línea incompleta: revisar a mano antes de seguir (no se repara solo)');
  const v0 = verify();
  if (!v0.ok) throw new Error('el registro no supera la verificación: ' + JSON.stringify(v0.problems).slice(0, 500));
  const st = check.staticCheck();
  if (!st.ok) throw new Error('Cycle ha cambiado desde la copia verificada: ' + st.problems.join('; ') + '. Registro detenido hasta verificar la equivalencia y autorizar una versión nueva.');

  let prev = records[records.length - 1] || null;
  const due = dueWeeks(prev?.week, now);
  if (!due.length) return { done: [], note: 'ninguna semana pendiente' };
  const prov = provider || { daily: () => fetchAll(), quotes: s => fetchQuotes(s) };
  const daily = await prov.daily();
  const spyDates = (daily[L.BENCH] || []).map(b => b.date);
  const done = [];
  let supplements = readPendingSupplements();
  for (const week of due) {
    const fri = weekFriday(week);
    const session = spyDates.filter(d => d >= addDays(fri, -4) && d <= fri).pop() || null;
    const nextOpen = nyToUtc(addDays(fri, 3), 9, 30);            // lunes siguiente 09:30 ET
    const lateLimit = new Date(nyToUtc(fri, 16, 15).getTime() + LATE_LIMIT_DAYS * 86400000);
    if (now > lateLimit) {                                           // demasiado tarde: hueco explícito
      const g = gapRecord({ week, capturedUtc: now.toISOString(), prev, reason: `sin captura en ${LATE_LIMIT_DAYS} días tras el cierre` });
      if (!dryRun) appendRecord(g);
      done.push({ week, status: 'gap', hash: g.hash }); prev = g; continue;
    }
    if (!session) throw new Error(`${week}: SPY no tiene ninguna sesión esa semana (¿datos de Yahoo sin actualizar?)`);
    // Si la última sesión no es el viernes puede ser festivo o que Yahoo aún no tenga el viernes: hasta el sábado a
    // mediodía (UTC) no se da por buena; la siguiente pasada lo confirma.
    if (session !== fri && now < new Date(addDays(fri, 1) + 'T12:00:00Z')) {
      done.push({ week, status: 'waiting', note: `última sesión ${session} ≠ viernes ${fri}: espero a confirmar` });
      break;
    }
    const { quotes, quoteErrors, quoteBases } = await prov.quotes(session);
    const blob = buildInputs({ week, session, daily, quotes, quoteBases, quoteErrors });
    const reading = computeReading(blob);
    const nSectorsMissing = reading.units.filter(u => u.kind === 'sector' && u.status !== 'ok').length;
    if (nSectorsMissing >= 2) throw new Error(`${week}: faltan datos de ${nSectorsMissing} sectores para ${session}; se reintenta en la siguiente pasada`);
    if (!reading.cycle_real.original_equals_copy || !reading.cycle_real.dominant_matches_summary)
      throw new Error(`${week}: el cálculo original de Cycle y la copia no coinciden con estos datos: ${JSON.stringify(reading.cycle_real.diffs).slice(0, 300)}`);
    const inputsRef = dryRun ? { file: `inputs/${week}.json.gz`, sha256: sha(canonical(blob)) } : writeInputs(`${week}.json.gz`, blob);
    const rec = makeRecord({ week, session, capturedUtc: now.toISOString(), status: now <= nextOpen ? 'on_time' : 'late_recovered',
      deadlineUtc: nextOpen.toISOString(), inputsRef, reading, prev, versions: versions(), supplements });
    if (!dryRun) {
      appendRecord(rec);
      if (supplements.length) { fs.unlinkSync(pendingSupplementsPath()); supplements = []; }
    }
    done.push({ week, session, status: rec.capture_status, hash: rec.hash, DG: rec.lists.DG, dominant: rec.cycle_real.dominant?.phase });
    prev = rec;
  }
  if (!dryRun) {
    const v1 = verify({ deep: true });
    if (!v1.ok) throw new Error('verificación tras escribir: ' + JSON.stringify(v1.problems).slice(0, 500));
  }
  return { done };
}

// ── publicación de huellas ──────────────────────────────────────────────────
function anchorOf(rec, now) {
  // Tardío si se ancla después de la apertura de la sesión siguiente. Los registros de esquema 1 (capturados en local
  // antes de existir el almacenamiento privado y la publicación) se anclan siempre como tardíos (decisión 2026-11-28).
  const late = rec.schema === 'sector-turn-registry-1' ? true
    : rec.on_time_deadline_utc ? now > new Date(rec.on_time_deadline_utc) : null;
  return { seq: rec.seq, week: rec.week, session_date: rec.session_date, captured_utc: rec.captured_utc,
    capture_status: rec.capture_status, hash: rec.hash, prev_hash: rec.prev_hash, schema: rec.schema,
    anchored_utc: now.toISOString(), anchored_late: late };
}
async function publish({ now = new Date() } = {}) {
  const v = verify({ deep: true });
  if (!v.ok) throw new Error('no se publica: el registro no supera la verificación: ' + JSON.stringify(v.problems).slice(0, 400));
  const { records } = readRecords();
  const anchored = new Set(readAnchors().map(a => a.seq));
  const todo = records.filter(r => !anchored.has(r.seq));
  const out = [];
  for (const r of todo) { const a = anchorOf(r, now); appendAnchor(a); out.push(a); }
  if (out.length) {
    const lines = out.map(a => `${a.week} (${a.session_date ?? 'hueco'}) · ${a.capture_status === 'on_time' ? 'a tiempo' : a.capture_status === 'gap' ? 'HUECO' : 'RECUPERADA CON RETRASO'}` +
      `${a.anchored_late ? ' · anclada tarde' : ''}\nhuella ${a.hash}\nanterior ${a.prev_hash}`);
    const last = todo[todo.length - 1];
    await telegram(`🔗 Registro giros sectoriales\n${lines.join('\n')}` +
      (last.kind === 'week' ? `\nD∧G: ${last.lists.DG.join(', ') || 'ninguno'} · Cycle: ${last.cycle_real.dominant?.phase ?? '—'}` : ''));
  }
  const v2 = verify({ requireAnchors: true });
  if (!v2.ok) throw new Error('verificación tras publicar: ' + JSON.stringify(v2.problems).slice(0, 400));
  return out.map(a => ({ week: a.week, anchored_late: a.anchored_late }));
}

// ── suplemento de entradas para un registro de esquema 1 (sin fichero de entradas) ───────────────────────────────
async function supplement({ week, now = new Date(), provider = null }) {
  const { records } = readRecords();
  const rec = records.find(r => r.week === week);
  if (!rec || rec.kind !== 'week') throw new Error(`${week} no está en el registro`);
  if (rec.inputs?.file) throw new Error(`${week} ya tiene fichero de entradas`);
  const prov = provider || { daily: () => fetchAll(), quotes: s => fetchQuotes(s) };
  const daily = await prov.daily();
  const { quotes, quoteErrors, quoteBases } = await prov.quotes(rec.session_date);
  const blob = { ...buildInputs({ week, session: rec.session_date, daily, quotes, quoteBases, quoteErrors }),
    supplement: { for_seq: rec.seq, for_hash: rec.hash, created_utc: now.toISOString(),
      note: 'descargado después de la captura: reproduce la lectura del registro original (comprobado), no la sustituye' } };
  // Primero exacto. Si Yahoo ha movido los decimales de los precios ajustados desde la captura (pasa entre consultas),
  // se admite como APROXIMADO solo si señales, listas y Cycle son idénticos y los decimales difieren < SUPP_TOL.
  const reading = computeReading(blob);
  let diffs = compareReading(rec, reading, 0), exact = true;
  if (diffs.length) {
    exact = false;
    diffs = compareReading(rec, reading, SUPP_TOL);
    if (diffs.length) throw new Error(`el suplemento no reproduce ${week}: ${diffs.slice(0, 5).join('; ')}`);
  }
  const maxRel = compareReading(rec, reading, 1).maxRel;
  const ref = writeInputs(`${week}.supplement.json.gz`, blob);
  const entry = { week, ...ref, created_utc: now.toISOString(), reproduces_hash: rec.hash, exact,
    tolerance: exact ? 0 : SUPP_TOL, max_rel_diff: maxRel,
    note: exact ? 'reproduce exactamente la lectura' : 'reproduce señales, listas y Cycle; decimales de los ratios con diferencias < tolerancia (Yahoo varía los precios ajustados entre consultas)' };
  const pend = readPendingSupplements().filter(s => s.week !== week).concat([entry]);
  fs.writeFileSync(pendingSupplementsPath(), JSON.stringify(pend, null, 1));
  return entry;
}

// ── almacenamiento privado (git) ─────────────────────────────────────────────
function git(dir, args, opts = {}) {
  const { execFileSync } = require('child_process');
  return execFileSync('git', ['-C', dir, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], ...opts }).trim();
}
// Añade y sube records.jsonl e inputs/ al repositorio privado. Reintenta con fetch + rebase si otro commit llegó antes;
// un conflicto real se aborta y falla en voz alta (nunca se resuelve a ciegas).
function pushPrivate({ dir = privDir(), message = 'registro semanal', tries = 5 } = {}) {
  git(dir, ['add', '-A']);                      // records.jsonl, inputs/ y el alta o baja de pending_supplements.json
  const staged = git(dir, ['diff', '--cached', '--name-only']);
  if (staged) git(dir, ['-c', 'user.name=market-tracker-bot', '-c', 'user.email=bot@users.noreply.github.com', 'commit', '-m', message]);
  const branch = git(dir, ['rev-parse', '--abbrev-ref', 'HEAD']);
  for (let k = 1; k <= tries; k++) {
    try { git(dir, ['push', 'origin', `HEAD:${branch}`]); return { pushed: true, attempts: k, committed: !!staged }; } catch (e) {
      if (k === tries) throw new Error(`push al repositorio privado fallido tras ${tries} intentos: ${e.stderr || e.message}`);
      git(dir, ['fetch', 'origin', branch]);
      try { git(dir, ['rebase', `origin/${branch}`]); } catch (e2) {
        try { git(dir, ['rebase', '--abort']); } catch { /* nada */ }
        throw new Error(`conflicto real con el repositorio privado (no se resuelve a ciegas): ${e2.stderr || e2.message}`);
      }
    }
  }
}

// Orquestador del pipeline: capturar → guardar en el repositorio privado → publicar huellas. Cualquier fallo avisa.
async function runWeekly({ privateGit = false, now = new Date(), provider = null } = {}) {
  const res = await capture({ now, provider });
  if (privateGit) pushPrivate({ message: `registro semanal ${res.done.map(d => d.week).join(', ') || '(sin semanas nuevas)'}` });
  const published = await publish({ now });
  return { ...res, published };
}

module.exports = { canonical, hashRecord, readRecords, appendRecord, verify, computeReading, buildInputs, makeRecord, gapRecord,
  dueWeeks, capture, publish, supplement, pushPrivate, runWeekly, readInputs, compareReading,
  weekFriday, nextWeek, nyToUtc, START_WEEK, recordsPath, anchorsPath, privDir };

if (require.main === module) {
  const argv = process.argv.slice(2);
  const cmd = argv[0];
  const flag = f => argv.includes(f);
  const val = f => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : null; };
  const now = val('--now') ? new Date(val('--now')) : new Date();
  const fail = async e => { console.error('ERROR:', e.message); if (flag('--alert')) await telegram(`⚠️ Registro de giros sectoriales: ${e.message}`.slice(0, 1500)); process.exit(1); };
  (async () => {
    try {
      if (cmd === 'verify') {
        const v = verify({ requireAnchors: flag('--require-anchors'), deep: flag('--deep') });
        console.log(JSON.stringify({ ...v, last: v.last && { seq: v.last.seq, week: v.last.week, hash: v.last.hash } }, null, 1));
        process.exit(v.ok ? 0 : 1);
      }
      if (cmd === 'status') {
        const { records } = readRecords();
        const an = new Map(readAnchors().map(a => [a.seq, a]));
        for (const r of records) console.log(r.seq, r.week, r.session_date, r.capture_status, r.hash.slice(0, 12),
          an.has(r.seq) ? (an.get(r.seq).anchored_late ? 'anclada tarde' : 'anclada') : 'sin anclar',
          '| D∧G:', (r.lists?.DG || []).join(',') || '—', '| Cycle:', r.cycle_real?.dominant?.phase ?? '—');
        console.log('pendientes:', dueWeeks(records[records.length - 1]?.week, new Date()).join(', ') || 'ninguna');
        return;
      }
      if (cmd === 'capture') return console.log(JSON.stringify(await capture({ now, dryRun: flag('--dry-run') }), null, 1));
      if (cmd === 'publish') return console.log(JSON.stringify(await publish({ now }), null, 1));
      if (cmd === 'supplement') return console.log(JSON.stringify(await supplement({ week: val('--week'), now }), null, 1));
      if (cmd === 'run-weekly') return console.log(JSON.stringify(await runWeekly({ privateGit: flag('--private-git'), now }), null, 1));
      console.log('uso: registry.js capture|publish|run-weekly|verify|status|supplement'); process.exit(2);
    } catch (e) { await fail(e); }
  })();
}
