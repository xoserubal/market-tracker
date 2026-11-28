'use strict';
// Ejecuta el cálculo ORIGINAL (extraído de cycle.html) y la COPIA congelada sobre los mismos datos y compara, fase a
// fase, todo lo que la pestaña muestra: puntuación, amplitud, dispersión, aceleración, ranking por ticker, cargados,
// total, y la fase dominante (computeCycleSummary). Lo usan las pruebas y cada captura semanal del registro.
const original = require('./cycle_original');
const copy = require('./cycle_copy');

const FIELDS = ['phase', 'order', 'score', 'breadth', 'dispersion', 'acceleration', 'tickerRanks', 'loaded', 'total'];

function pick(p) {
  const o = {};
  for (const k of FIELDS) o[k] = p[k] === undefined ? null : p[k];
  return o;
}

// Igualdad exacta (mismos números en coma flotante), con NaN = NaN.
function same(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a === b || (Number.isNaN(a) && Number.isNaN(b));
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return a === b;
  const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
  if (ka.length !== kb.length || ka.some((k, i) => k !== kb[i])) return false;
  return ka.every(k => same(a[k], b[k]));
}

let _orig = null;
function loadOriginal() { if (!_orig) _orig = original.load(); return _orig; }

// rows: { TICKER: { m1, m3, ... } } con el mismo formato que /api/quote (lo que usa la pestaña).
function computeBoth(rows) {
  const o = loadOriginal();
  const po = o.calcPhaseScores(o.CYCLE_MAP, rows).map(pick);
  const pc = copy.calcPhaseScores(copy.CYCLE_MAP, rows).map(pick);
  const diffs = [];
  if (po.length !== pc.length) diffs.push({ kind: 'n_phases', original: po.length, copy: pc.length });
  for (let i = 0; i < Math.min(po.length, pc.length); i++) {
    for (const k of FIELDS) if (!same(po[i][k], pc[i][k])) diffs.push({ phase: po[i].phase, field: k, original: po[i][k], copy: pc[i][k] });
  }
  const so = o.computeCycleSummary(o.calcPhaseScores(o.CYCLE_MAP, rows));
  const sc = copy.computeCycleSummary(copy.calcPhaseScores(copy.CYCLE_MAP, rows));
  const dom = s => s ? { dominant: s.dominant?.phase ?? null, dominant_order: s.dominant?.order ?? null,
    losing: s.losing?.phase ?? null, mostAccel: s.mostAccel?.phase ?? null, mostDecel: s.mostDecel?.phase ?? null } : null;
  if (!same(dom(so), dom(sc))) diffs.push({ kind: 'summary', original: dom(so), copy: dom(sc) });
  return { equal: diffs.length === 0, diffs, phases: pc, summary: dom(sc), original_sha256: o.sha256 };
}

// Comprobación estática: la huella de los fragmentos de cycle.html sigue siendo la de la copia, y la tabla copiada
// (fases, orden, tickers y papeles) coincide con la original.
function staticCheck() {
  const o = loadOriginal();
  const problems = [];
  if (o.sha256 !== copy.ORIGINAL_SHA256) problems.push(`huella de cycle.html ${o.sha256} ≠ la de la copia ${copy.ORIGINAL_SHA256}`);
  const norm = m => m.map(p => [p.phase, p.order, p.category, p.sectors.map(s => [s.name, s.tickers.map(t => [t.ticker, t.role])])]);
  if (JSON.stringify(norm(o.CYCLE_MAP)) !== JSON.stringify(norm(copy.CYCLE_MAP))) problems.push('la tabla de fases de cycle.html no coincide con la copia');
  return { ok: problems.length === 0, problems, original_sha256: o.sha256, copy_version: copy.COPY_VERSION };
}

const allTickers = () => [...new Set(['SPY', ...copy.CYCLE_MAP.flatMap(p => p.sectors.flatMap(s => s.tickers.map(t => t.ticker)))])];

module.exports = { computeBoth, staticCheck, same, allTickers, FIELDS };
