'use strict';
// Contrastes históricos del preregistro v2 (wiki/PREREGISTRO_GIRO_SECTORES_REZAGADOS_V2.md, firmado 2026-11-28):
// bloque A (11 sectores SPDR, exploratorio), bloque A′ (18 industrias no expuestas, generalización) y su combinación
// E_amp (referencia exploratoria de H1-ampliada). Más comparadores, robustez, sensibilidades, H2 descriptivo con el
// Cycle simplificado (§7.6) y reparto por etapas de Pring (§8).
//
//   node research/sector_turnaround_v2/historical.js --placebo   resultados con precios simulados (solo para depurar)
//   node research/sector_turnaround_v2/historical.js --final     ejecución única; se niega si ya existe el resultado
//
// Las señales (D, G, independencia) salen de scripts/sector_turn/lib.js sin cambios. Fuente de precios: el caché del
// recuento (research/sector_turnaround_v2/_work/prices_max.json, huella en freeze.json).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const L = require('../../scripts/sector_turn/lib');
const copy = require('../../scripts/sector_turn/cycle_copy');

const HIST_END = '2026-08-28';     // fin de los bloques A y A′; la ventana 2026-08-29 → 2026-11-27 queda fuera
const WORK = path.join(__dirname, '_work');
const CACHE = path.join(WORK, 'prices_max.json');
const PRING_CACHE = path.join(WORK, 'pring_series.json');
const OUT_FINAL = path.join(__dirname, 'historical_results.json');
const OUT_PLACEBO = path.join(WORK, 'placebo_results.json');
const PLACEBO = process.argv.includes('--placebo');
const FINAL = process.argv.includes('--final');
if (PLACEBO === FINAL) { console.error('usa --placebo o --final'); process.exit(2); }

const B = 10000;                    // remuestras bootstrap
const H_MAIN = 40, H_SEC = [20, 60];
const COST = { sector: 0.0010, industry: 0.0020 };
const THR_H1 = 0.01;
const EXPECTED = { sector: { events: 148, weeks: 134, quarters: 74 }, industry: { events: 409, weeks: 289, quarters: 86 } };
const MIN = { single: { events: 30, quarters: 10 }, amp: { events: 60, perLevel: 10, quarters: 12 } };
const NOT_IN_BOOK_LIST = ['IBB', 'IHI', 'XHS'];

const UNEXPOSED = L.INDUSTRIES.filter(x => !x.exposed);
const BOOK_POS = Object.fromEntries(L.INDUSTRIES.map(x => [x.t, x.pos]));
const LEVELS = { sector: L.SECTORS, industry: UNEXPOSED.map(x => x.t) };

// ── utilidades ──────────────────────────────────────────────────────────────
const quarterOf = d => d.slice(0, 4) + 'Q' + (Math.floor((+d.slice(5, 7) - 1) / 3) + 1);
const semesterOf = d => d.slice(0, 4) + 'S' + (+d.slice(5, 7) <= 6 ? 1 : 2);
const yearOf = d => d.slice(0, 4);
const BLOCKS = { quarter: quarterOf, semester: semesterOf, year: yearOf };
const mean = a => a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
const sd = a => { const m = mean(a); return a.length > 1 ? Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)) : null; };
const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const k = s.length >> 1; return s.length % 2 ? s[k] : (s[k - 1] + s[k]) / 2; };
const pct = (sorted, p) => { const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo); };
function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const seedOf = s => parseInt(crypto.createHash('sha256').update(s).digest('hex').slice(0, 8), 16);
const r4 = x => x == null ? null : +x.toFixed(5);

// ── precios ─────────────────────────────────────────────────────────────────
const prices = JSON.parse(fs.readFileSync(CACHE, 'utf8'));
const calendar = prices[L.BENCH].map(b => b.date);
const calIdx = new Map(calendar.map((d, i) => [d, i]));
const adjReal = {};
for (const t of Object.keys(prices)) adjReal[t] = new Map(prices[t].filter(b => b.adj).map(b => [b.date, b.adj]));

// Placebo: los resultados se calculan con paseos aleatorios (mismas fechas, volatilidad diaria 1,5 %); las señales
// siguen siendo las reales. Sirve para comprobar el código sin ver ningún resultado real.
function placeboAdj() {
  const out = {};
  for (const t of Object.keys(adjReal)) {
    const r = rng(seedOf('placebo:' + t)); let p = 100; const m = new Map();
    for (const d of [...adjReal[t].keys()]) { const z = Math.sqrt(-2 * Math.log(r() || 1e-12)) * Math.cos(2 * Math.PI * r()); p *= Math.exp(0.015 * z); m.set(d, p); }
    out[t] = m;
  }
  return out;
}
const adjOut = PLACEBO ? placeboAdj() : adjReal;

// ── observaciones ETF-semana ───────────────────────────────────────────────
function outcome(t, level, date, h) {
  const i = calIdx.get(date); if (i == null) return null;
  const e = i + 1, f = e + h;
  if (f >= calendar.length || calendar[f] > HIST_END) return { complete: false };
  const d0 = calendar[e], d1 = calendar[f];
  const a0 = adjOut[t].get(d0), a1 = adjOut[t].get(d1);
  if (!a0 || !a1) return { complete: false };
  const rets = [];
  for (const u of LEVELS[level]) { const b0 = adjOut[u]?.get(d0), b1 = adjOut[u]?.get(d1); if (b0 && b1) rets.push(b1 / b0 - 1); }
  const ret = a1 / a0 - 1;
  let mae = 0;
  if (h === H_MAIN) for (let k = e; k <= f; k++) { const a = adjOut[t].get(calendar[k]); if (a) mae = Math.min(mae, a / a0 - 1); }
  return { complete: true, entry: d0, end: d1, ret, gross: ret - mean(rets), n_cmp: rets.length, mae: h === H_MAIN ? mae : undefined };
}

function observations(level) {
  const out = [];
  for (const t of LEVELS[level]) {
    const ratio = L.ratioSeries(prices[t] || [], prices[L.BENCH]);
    const rIdx = new Map(ratio.map((x, i) => [x.date, i]));
    for (const row of L.weeklyEvents(ratio, HIST_END)) {
      if (row.D == null || row.G == null) continue;
      const i = rIdx.get(row.date);
      const rs63 = i >= 63 ? ratio[i].r / ratio[i - 63].r - 1 : null;
      const ci = calIdx.get(row.date);
      const a = adjReal[t].get(row.date), a21 = ci >= 21 ? adjReal[t].get(calendar[ci - 21]) : null;
      const mom21 = a && a21 ? a / a21 - 1 : null;
      const o = { ticker: t, level, week: row.week, date: row.date, q: quarterOf(row.date), D: row.D, G: row.G,
        DG: row.DG, indep: row.DG && row.independent, depth: row.dist_max756, rs63, mom21, out: {} };
      for (const h of [H_MAIN, ...H_SEC]) o.out[h] = outcome(t, level, row.date, h);
      out.push(o);
    }
  }
  return out;
}

const exc = (o, h = H_MAIN, costMult = 1) => o.out[h].gross - COST[o.level] * costMult;
const isComplete = (o, h = H_MAIN) => !!o.out[h]?.complete;

// ── estimandos ──────────────────────────────────────────────────────────────
// Media semanal de un nivel: media de las medias por semana. e.wk distingue copias de un mismo bloque en el bootstrap.
function weeklyMean(evs, val) {
  const g = new Map();
  for (const e of evs) { const k = e.wk ?? e.week; if (!g.has(k)) g.set(k, []); g.get(k).push(val(e)); }
  return g.size ? mean([...g.values()].map(mean)) : null;
}
const eAmp = (evs, val) => {
  const s = weeklyMean(evs.filter(e => e.level === 'sector'), val), i = weeklyMean(evs.filter(e => e.level === 'industry'), val);
  return s == null || i == null ? null : 0.5 * s + 0.5 * i;
};
function eAmpOldRule(evs, val) {           // regla anterior: cada semana igual, 50/50 dentro de la semana si hay ambos
  const g = new Map();
  for (const e of evs) { const k = e.wk ?? e.week; if (!g.has(k)) g.set(k, { sector: [], industry: [] }); g.get(k)[e.level].push(val(e)); }
  return mean([...g.values()].map(w => w.sector.length && w.industry.length ? 0.5 * mean(w.sector) + 0.5 * mean(w.industry) : mean(w.sector.length ? w.sector : w.industry)));
}
const perEvent = (evs, val) => mean(evs.map(val));

// Bootstrap por bloques (trimestre, semestre o año de la decisión).
function bootstrap(evs, stat, block = 'quarter', seedKey = 'x', reps = B) {
  const f = BLOCKS[block];
  const groups = new Map();
  for (const e of evs) { const k = f(e.date); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(e); }
  const keys = [...groups.keys()];
  const r = rng(seedOf(seedKey + ':' + block));
  const vals = [];
  for (let b = 0; b < reps; b++) {
    const sample = [];
    for (let k = 0; k < keys.length; k++) {
      const key = keys[Math.floor(r() * keys.length)];
      for (const e of groups.get(key)) sample.push({ ...e, wk: (e.wk ?? e.week) + '#' + k });
    }
    const v = stat(sample);
    if (v != null && Number.isFinite(v)) vals.push(v);
  }
  vals.sort((a, b) => a - b);
  return { n_blocks: keys.length, valid_reps: vals.length, ci95: [pct(vals, 0.025), pct(vals, 0.975)] };
}

const verdict = (est, lo, hi, thr = THR_H1) => est == null ? 'NO EVALUABLE' : (est >= thr && lo > 0 ? 'FAVORABLE' : hi < thr ? 'DESFAVORABLE' : 'INCONCLUYENTE');

// ── regresión (MCO ponderados, con una pizca de ridge para columnas vacías del bootstrap) ─────────────────────
function wls(X, y, w) {
  const p = X[0].length, A = Array.from({ length: p }, () => new Array(p).fill(0)), bv = new Array(p).fill(0);
  for (let i = 0; i < X.length; i++) for (let a = 0; a < p; a++) { bv[a] += w[i] * X[i][a] * y[i]; for (let c = 0; c < p; c++) A[a][c] += w[i] * X[i][a] * X[i][c]; }
  for (let a = 0; a < p; a++) A[a][a] += 1e-10;
  for (let c = 0; c < p; c++) {                 // eliminación gaussiana con pivote
    let m = c; for (let r = c + 1; r < p; r++) if (Math.abs(A[r][c]) > Math.abs(A[m][c])) m = r;
    [A[c], A[m]] = [A[m], A[c]]; [bv[c], bv[m]] = [bv[m], bv[c]];
    if (Math.abs(A[c][c]) < 1e-14) return null;
    for (let r = 0; r < p; r++) if (r !== c) { const f = A[r][c] / A[c][c]; for (let k = c; k < p; k++) A[r][k] -= f * A[c][k]; bv[r] -= f * bv[c]; }
  }
  return bv.map((v, i) => v / A[i][i]);
}

// Efectos fijos por semana: se restan las medias de semana y se estima sin constante. Devuelve el coeficiente de x0.
function feCoef(obs, cols) {
  const g = new Map();
  for (const o of obs) { const k = o.wk ?? o.week; if (!g.has(k)) g.set(k, []); g.get(k).push(o); }
  const X = [], y = [];
  for (const arr of g.values()) {
    if (arr.length < 2) continue;
    const my = mean(arr.map(o => o.y)), mx = cols.map(c => mean(arr.map(o => o[c])));
    for (const o of arr) { y.push(o.y - my); X.push(cols.map((c, j) => o[c] - mx[j])); }
  }
  if (X.length < cols.length + 2) return null;
  const b = wls(X, y, y.map(() => 1));
  return b ? b[0] : null;
}

// ── comparadores ────────────────────────────────────────────────────────────
function comparators(level, obs, events) {
  const comp = obs.filter(o => isComplete(o)).map(o => ({ ...o, y: exc(o) }));
  const byWeek = new Map(); for (const o of comp) { if (!byWeek.has(o.week)) byWeek.set(o.week, []); byWeek.get(o.week).push(o); }
  const evWeeks = new Set(events.map(e => e.week));
  const res = {};

  // B0: D∧G (independiente) frente a D sin G, semanas con ambos, controles profundidad y fuerza relativa 63.
  const b0obs = comp.filter(o => o.D && (o.indep || !o.G) && o.rs63 != null).map(o => ({ ...o, dg: o.indep ? 1 : 0 }));
  const b0w = new Set([...new Set(b0obs.map(o => o.week))].filter(w => { const a = b0obs.filter(o => o.week === w); return a.some(o => o.dg) && a.some(o => !o.dg); }));
  const b0s = b0obs.filter(o => b0w.has(o.week));
  const b0 = feCoef(b0s, ['dg', 'depth', 'rs63']);
  res.B0 = { question: '¿Aporta el giro sobre estar deprimido? (D∧G − D sin G, efectos fijos de semana)', weeks_with_both: b0w.size,
    n_obs: b0s.length, n_DG: b0s.filter(o => o.dg).length, evaluable: b0 != null && b0w.size >= 10,
    estimate: r4(b0), ...(b0 != null ? { ci95: bootstrap(b0s, s => feCoef(s, ['dg', 'depth', 'rs63']), 'quarter', 'B0' + level).ci95.map(r4) } : {}) };
  res.B0.positive = res.B0.evaluable ? res.B0.ci95[0] > 0 : null;

  // B0′: emparejamiento descriptivo (D sin G de otro ETF a ±4 semanas y ±5 pp de profundidad; el más cercano).
  const weeksSorted = [...new Set(obs.map(o => o.week))].sort(), wI = new Map(weeksSorted.map((w, i) => [w, i]));
  const dng = comp.filter(o => o.D && !o.G);
  const pairs = [];
  for (const e of events) {
    const c = dng.filter(o => o.ticker !== e.ticker && Math.abs(wI.get(o.week) - wI.get(e.week)) <= 4 && Math.abs(o.depth - e.depth) <= 0.05)
      .sort((a, b) => Math.abs(wI.get(a.week) - wI.get(e.week)) - Math.abs(wI.get(b.week) - wI.get(e.week)) || Math.abs(a.depth - e.depth) - Math.abs(b.depth - e.depth))[0];
    if (c) pairs.push({ ...e, d: exc(e) - c.y });
  }
  res.B0prime = { question: 'Emparejamiento descriptivo D∧G − D sin G', matched: pairs.length, of: events.length,
    estimate: r4(perEvent(pairs, p => p.d)), ci95: pairs.length ? bootstrap(pairs, s => perEvent(s, p => p.d), 'quarter', 'B0p' + level).ci95.map(r4) : null };

  // B1: azar, mismo número de ETFs del nivel en cada semana de evento.
  const actual = weeklyMean(events, e => exc(e));
  const r = rng(seedOf('B1' + level)); const draws = [];
  const kByWeek = new Map(); for (const e of events) kByWeek.set(e.week, (kByWeek.get(e.week) || 0) + 1);
  for (let b = 0; b < B; b++) {
    const wm = [];
    for (const [w, k] of kByWeek) {
      const pool = [...(byWeek.get(w) || [])];
      const pick = [];
      for (let j = 0; j < Math.min(k, pool.length); j++) { const m = Math.floor(r() * pool.length); pick.push(pool[m].y); pool.splice(m, 1); }
      if (pick.length) wm.push(mean(pick));
    }
    draws.push(mean(wm));
  }
  draws.sort((a, b) => a - b);
  res.B1 = { question: 'Azar: mismo número de ETFs del nivel en las mismas semanas', random_mean: r4(mean(draws)),
    random_ci95: [r4(pct(draws, 0.025)), r4(pct(draws, 0.975))], actual_percentile: +(100 * draws.filter(x => x < actual).length / draws.length).toFixed(1) };

  // B2: momentum (tercio superior por fuerza relativa a 63 sesiones), mismas semanas; diferencia semanal emparejada.
  const momByWeek = new Map();
  for (const w of evWeeks) {
    const pool = (byWeek.get(w) || []).filter(o => o.rs63 != null).sort((a, b) => b.rs63 - a.rs63);
    if (pool.length) momByWeek.set(w, mean(pool.slice(0, Math.ceil(pool.length / 3)).map(o => o.y)));
  }
  const evB2 = events.filter(e => momByWeek.has(e.week));
  const diffStat = s => weeklyMean(s, e => exc(e) - momByWeek.get(e.week));
  res.B2 = { question: 'Momentum: D∧G − tercio superior por fuerza relativa 63 de las mismas semanas', momentum_mean: r4(mean([...momByWeek.values()])),
    diff: r4(diffStat(evB2)), ci95: bootstrap(evB2, diffStat, 'quarter', 'B2' + level).ci95.map(r4) };

  // B3: ¿importa estar deprimido? D∧G (independiente) frente a G sin D, semanas con ambos.
  const b3obs = comp.filter(o => o.G && (o.indep || !o.D) && o.rs63 != null).map(o => ({ ...o, dg: o.indep ? 1 : 0 }));
  const b3w = new Set([...new Set(b3obs.map(o => o.week))].filter(w => { const a = b3obs.filter(o => o.week === w); return a.some(o => o.dg) && a.some(o => !o.dg); }));
  const b3s = b3obs.filter(o => b3w.has(o.week));
  const b3 = feCoef(b3s, ['dg', 'rs63']);
  res.B3 = { question: '¿Importa estar deprimido? (D∧G − G sin D, efectos fijos de semana)', weeks_with_both: b3w.size, n_obs: b3s.length,
    estimate: r4(b3), ...(b3 != null ? { ci95: bootstrap(b3s, s => feCoef(s, ['dg', 'rs63']), 'quarter', 'B3' + level).ci95.map(r4) } : {}) };
  return res;
}

// ── robustez operativa (§6.7) ───────────────────────────────────────────────
function robustness(events, stat, kind) {
  const triple = stat(events, e => exc(e, H_MAIN, 3));
  const top5 = new Set([...events].sort((a, b) => exc(b) - exc(a)).slice(0, 5).map(e => e.ticker + e.week));
  const noTop5 = stat(events.filter(e => !top5.has(e.ticker + e.week)), e => exc(e));
  const loo = [];
  for (const t of [...new Set(events.map(e => e.ticker))].sort()) {
    const s = events.filter(e => e.ticker !== t);
    const q = new Set(s.map(e => e.q)).size;
    const ok = kind === 'amp'
      ? s.length >= MIN.amp.events && q >= MIN.amp.quarters && ['sector', 'industry'].every(l => s.filter(e => e.level === l).length >= MIN.amp.perLevel)
      : s.length >= MIN.single.events && q >= MIN.single.quarters;
    loo.push({ excluded: t, evaluable: ok, estimate: ok ? r4(stat(s, e => exc(e))) : null });
  }
  const ev = loo.filter(x => x.evaluable);
  const share = ev.length ? ev.filter(x => x.estimate > 0).length / ev.length : null;
  const tests = { triple_cost: { estimate: r4(triple), pass: triple > 0 }, without_top5: { estimate: r4(noTop5), pass: noTop5 > 0 },
    leave_one_etf_out: { evaluable: ev.length, share_positive: share == null ? null : +share.toFixed(3), pass: share != null && share >= 0.75, detail: loo } };
  return { ...tests, label: tests.triple_cost.pass && tests.without_top5.pass && tests.leave_one_etf_out.pass ? 'ROBUSTA' : 'NO ROBUSTA' };
}

// Solape de ventanas entre bloques contiguos (§6.3).
function overlap(events, block) {
  const f = BLOCKS[block];
  let crosses = 0, crossOverlap = 0;
  for (const e of events) {
    const end = e.out[H_MAIN].end, b = f(e.date);
    if (f(end) === b) continue;
    crosses++;
    if (events.some(o => f(o.date) > b && o.out[H_MAIN].entry <= end)) crossOverlap++;
  }
  return { events: events.length, window_enters_next_block: crosses, and_overlaps_event_of_later_block: crossOverlap,
    share: events.length ? +(crossOverlap / events.length).toFixed(3) : null };
}

// ── H1: un estimando completo (principal + bloques alternativos + secundarios + robustez) ───────────────────
function h1(name, events, stat, kind, statusLabel) {
  const est = stat(events, e => exc(e));
  const ci = {};
  for (const bl of Object.keys(BLOCKS)) ci[bl] = bootstrap(events, s => stat(s, e => exc(e)), bl, name);
  const lo = ci.quarter.ci95[0], hi = ci.quarter.ci95[1];
  const v = verdict(est, lo, hi);
  const alt = Object.fromEntries(Object.entries(ci).map(([bl, c]) => [bl, verdict(est, c.ci95[0], c.ci95[1])]));
  const levelStats = l => {
    const s = events.filter(e => l == null || e.level === l);
    const x = s.map(e => exc(e));
    return { events: s.length, weeks: new Set(s.map(e => e.week)).size, quarters: new Set(s.map(e => e.q)).size,
      mean_abs_return: r4(mean(s.map(e => e.out[H_MAIN].ret))), mean_cost: r4(mean(s.map(e => COST[e.level]))),
      sd_excess: r4(sd(x)), share_positive: s.length ? +(x.filter(y => y > 0).length / s.length).toFixed(3) : null,
      mae_mean: r4(mean(s.map(e => e.out[H_MAIN].mae))), mae_median: r4(median(s.map(e => e.out[H_MAIN].mae))),
      mae_worst: r4(Math.min(...s.map(e => e.out[H_MAIN].mae))), min_comparison_etfs: Math.min(...s.map(e => e.out[H_MAIN].n_cmp)) };
  };
  const secondary = {};
  for (const h of H_SEC) {
    const s = events.filter(e => isComplete(e, h));
    secondary['h' + h] = { events: s.length, estimate: r4(stat(s, e => exc(e, h))), ci95: bootstrap(s, x => stat(x, e => exc(e, h)), 'quarter', name + h).ci95.map(r4) };
  }
  const cost = {};
  for (const m of [2, 3]) cost['x' + m] = { estimate: r4(stat(events, e => exc(e, H_MAIN, m))), ci95: bootstrap(events, s => stat(s, e => exc(e, H_MAIN, m)), 'quarter', name + 'c' + m).ci95.map(r4) };
  return {
    status: statusLabel, estimate: r4(est), ci95_quarter: [r4(lo), r4(hi)], verdict: v,
    lower_bound_reaches_threshold: lo >= THR_H1,
    block_sensitivity: Object.fromEntries(Object.entries(ci).map(([bl, c]) => [bl, { n_blocks: c.n_blocks, ci95: c.ci95.map(r4), verdict: alt[bl] }])),
    sensitive_to_temporal_dependence: Object.values(alt).some(x => x !== v),
    overlap: Object.fromEntries(Object.keys(BLOCKS).map(bl => [bl, overlap(events, bl)])),
    descriptive: kind === 'amp' ? { sector: levelStats('sector'), industry: levelStats('industry'), all: levelStats(null) } : levelStats(null),
    robustness: robustness(events, stat, kind), secondary_horizons: secondary, cost_sensitivity: cost,
  };
}

// ── H2 descriptivo (§7.6) ───────────────────────────────────────────────────
const cycleCache = new Map();
function nextPosAt(date) {
  if (!cycleCache.has(date)) cycleCache.set(date, L.dominantOf(L.simplifiedPhaseScores(copy.CYCLE_MAP, prices, date)));
  return cycleCache.get(date);
}
function h2Weights(s, perEventW) {
  if (perEventW) return s.map(() => 1);
  const levels = [...new Set(s.map(e => e.level))];
  const nW = {}, nWE = new Map();
  for (const e of s) { const k = e.level + '|' + (e.wk ?? e.week); nWE.set(k, (nWE.get(k) || 0) + 1); }
  for (const l of levels) nW[l] = new Set(s.filter(e => e.level === l).map(e => e.wk ?? e.week)).size;
  return s.map(e => (1 / levels.length) / nW[e.level] / nWE.get(e.level + '|' + (e.wk ?? e.week)));
}
function h2Beta(s, perEventW = false) {
  if (!s.length || !s.some(e => e.conc) || !s.some(e => !e.conc)) return null;
  const years = [...new Set(s.map(e => yearOf(e.date)))].sort().slice(1);
  const twoLevels = new Set(s.map(e => e.level)).size === 2;
  const X = s.map(e => [1, e.conc ? 1 : 0, e.depth, e.rs63, e.mom21, ...(twoLevels ? [e.level === 'industry' ? 1 : 0] : []), ...years.map(y => yearOf(e.date) === y ? 1 : 0)]);
  const b = wls(X, s.map(e => exc(e)), h2Weights(s, perEventW));
  return b ? b[1] : null;
}
const corr = (a, b) => { const ma = mean(a), mb = mean(b); let n = 0, da = 0, db = 0; for (let i = 0; i < a.length; i++) { n += (a[i] - ma) * (b[i] - mb); da += (a[i] - ma) ** 2; db += (b[i] - mb) ** 2; } return da && db ? n / Math.sqrt(da * db) : null; };
function h2(name, events, posOf) {
  const s = events.filter(e => e.rs63 != null && e.mom21 != null).map(e => {
    const dom = nextPosAt(e.date), p = posOf(e);
    return dom && p != null ? { ...e, conc: p === dom.next_pos, dom_phase: dom.order, n_phases: dom.n_scored } : null;
  }).filter(Boolean);
  const c = s.filter(e => e.conc), n = s.filter(e => !e.conc);
  const qc = new Set(c.map(e => e.q)).size, qn = new Set(n.map(e => e.q)).size;
  const beta = h2Beta(s);
  return { sample: name, status: 'descriptivo (Cycle simplificado, §7.6)', events_with_position: s.length, unmapped: events.length - s.length,
    concordant: c.length, non_concordant: n.length, quarters_concordant: qc, quarters_non_concordant: qn,
    evaluability_met: c.length >= 30 && n.length >= 30 && qc >= 10 && qn >= 10,
    raw_mean_concordant: r4(mean(c.map(e => exc(e)))), raw_mean_non_concordant: r4(mean(n.map(e => exc(e)))),
    beta: r4(beta), ci95_quarter: beta != null ? bootstrap(s, x => h2Beta(x), 'quarter', 'H2' + name).ci95.map(r4) : null,
    beta_per_event_weights: r4(h2Beta(s, true)),
    corr_concordance_with: Object.fromEntries(['depth', 'rs63', 'mom21'].map(k => [k, r4(corr(s.map(e => e.conc ? 1 : 0), s.map(e => e[k])))])) };
}

// ── Pring (§8): solo reparto de eventos por etapa ──────────────────────────
async function pringSeries() {
  if (fs.existsSync(PRING_CACHE)) return JSON.parse(fs.readFileSync(PRING_CACHE, 'utf8'));
  const out = {};
  for (const t of ['^TNX', '^SPGSCI']) { try { out[t] = (await L.fetchDailyFull(t)).bars.map(b => ({ date: b.date, close: b.close })); } catch (e) { out[t] = { error: String(e.message) }; } }
  fs.writeFileSync(PRING_CACHE, JSON.stringify(out));
  return out;
}
function pringStages(events, series) {
  const bull = (bars, date, invert) => {
    if (!Array.isArray(bars)) return null;
    let i = -1; for (let k = 0; k < bars.length && bars[k].date <= date; k++) i = k;
    if (i < 251) return null;
    let s = 0; for (let k = i - 251; k <= i; k++) s += bars[k].close;
    return invert ? bars[i].close < s / 252 : bars[i].close > s / 252;
  };
  const spy = prices[L.BENCH].map(b => ({ date: b.date, close: b.close }));
  const table = { 'true,false,false': 'I', 'true,true,false': 'II', 'true,true,true': 'III', 'false,true,true': 'IV', 'false,false,true': 'V', 'false,false,false': 'VI' };
  const dist = {};
  for (const e of events) {
    const b = bull(series['^TNX'], e.date, true), a = bull(spy, e.date, false), m = bull(series['^SPGSCI'], e.date, false);
    const st = b == null || a == null || m == null ? 'sin dato' : (table[[b, a, m].join()] ?? 'sin etapa');
    dist[e.level] ??= {}; dist[e.level][st] = (dist[e.level][st] || 0) + 1;
  }
  return { status: 'descriptivo, solo reparto (§8)', series_first: { TNX: series['^TNX']?.[0]?.date ?? series['^TNX']?.error, SPGSCI: series['^SPGSCI']?.[0]?.date ?? series['^SPGSCI']?.error }, distribution: dist };
}

// ── principal ───────────────────────────────────────────────────────────────
(async () => {
  if (FINAL && fs.existsSync(OUT_FINAL)) { console.error('historical_results.json ya existe: los contrastes se ejecutan una sola vez'); process.exit(1); }
  execFileSync(process.execPath, [path.join(__dirname, 'freeze.js'), '--verify'], { stdio: 'inherit' });

  const obs = { sector: observations('sector'), industry: observations('industry') };
  const registered = {}, ev = {};
  for (const l of ['sector', 'industry']) {
    registered[l] = obs[l].filter(o => o.indep);
    ev[l] = registered[l].filter(o => isComplete(o));
    const got = { events: registered[l].length, weeks: new Set(registered[l].map(o => o.week)).size, quarters: new Set(registered[l].map(o => o.q)).size };
    for (const k of Object.keys(got)) if (got[k] !== EXPECTED[l][k]) throw new Error(`recuento distinto del preregistro en ${l}.${k}: ${got[k]} ≠ ${EXPECTED[l][k]}`);
  }
  const indNoBook = ev.industry.filter(e => !NOT_IN_BOOK_LIST.includes(e.ticker));
  const secWeeks = new Set(ev.sector.map(e => e.week));
  const both = [...ev.sector, ...ev.industry];

  const res = {
    generated_utc: new Date().toISOString(), mode: PLACEBO ? 'PLACEBO (precios simulados: no son resultados)' : 'final',
    preregistration: 'wiki/PREREGISTRO_GIRO_SECTORES_REZAGADOS_V2.md',
    script_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename, 'utf8').replace(/\r\n/g, '\n')).digest('hex'),
    freeze: JSON.parse(fs.readFileSync(path.join(__dirname, 'freeze.json'), 'utf8')).sha256,
    conventions: {
      hist_end: HIST_END, analysis_date: HIST_END,
      complete_outcome: 'entrada (sesión siguiente a la decisión) y las h sesiones posteriores dentro del bloque (≤ hist_end)',
      excess: 'retorno ajustado del ETF − media de los ETFs del nivel con precio en entrada y salida (incluido él), menos coste',
      mom21: 'retorno propio del ETF a 21 sesiones (interpretación de «momentum a 21 sesiones», distinto de la fuerza relativa a 63)',
      leave_one_out: 'se quitan los eventos de ese ETF; la media del nivel no cambia', bootstrap_reps: B, ci: '95 % percentil, bloques de trimestre (principal)',
    },
    counts: Object.fromEntries(['sector', 'industry'].map(l => [l, { registered: registered[l].length, complete: ev[l].length }])),
    level_overlap: { industry_events: ev.industry.length, in_week_with_sector_event: ev.industry.filter(e => secWeeks.has(e.week)).length },
    H1: {
      A_sectores: h1('A', ev.sector, weeklyMean, 'single', 'exploratorio'),
      Aprime_industrias: h1('Ap', ev.industry, weeklyMean, 'single', 'generalización, exploratorio'),
      Aprime_sin_IBB_IHI_XHS: { estimate: r4(weeklyMean(indNoBook, e => exc(e))), ci95: bootstrap(indNoBook, s => weeklyMean(s, e => exc(e)), 'quarter', 'ApNB').ci95.map(r4), events: indNoBook.length },
      E_amp_A_mas_Aprime: h1('Amp', both, eAmp, 'amp', 'exploratorio (referencia para H1-ampliada)'),
      E_amp_sensitivities: {
        old_rule: { estimate: r4(eAmpOldRule(both, e => exc(e))), ci95: bootstrap(both, s => eAmpOldRule(s, e => exc(e)), 'quarter', 'AmpOld').ci95.map(r4) },
        per_event: { estimate: r4(perEvent(both, e => exc(e))), ci95: bootstrap(both, s => perEvent(s, e => exc(e)), 'quarter', 'AmpEv').ci95.map(r4) },
        without_IBB_IHI_XHS: { estimate: r4(eAmp([...ev.sector, ...indNoBook], e => exc(e))), ci95: bootstrap([...ev.sector, ...indNoBook], s => eAmp(s, e => exc(e)), 'quarter', 'AmpNB').ci95.map(r4) },
      },
    },
    comparators: { A_sectores: comparators('sector', obs.sector, ev.sector), Aprime_industrias: comparators('industry', obs.industry, ev.industry) },
  };
  res.attribution_to_G = Object.fromEntries(Object.entries(res.comparators).map(([k, c]) => [k,
    c.B0.evaluable && c.B0.positive ? 'B0 evaluable y positivo: la ventaja puede atribuirse al giro'
      : 'B0 no positivo o no evaluable: una eventual ventaja no puede atribuirse específicamente al giro']));
  res.H2_descriptive = {
    sectors_cycle: h2('sectores, tabla Cycle', ev.sector, e => L.SECTOR_POS_CYCLE[e.ticker]),
    sectors_cycle_plus_xlre: h2('sectores, Cycle + XLRE', ev.sector, e => L.SECTOR_POS_WITH_XLRE[e.ticker]),
    industries_book: h2('industrias A′, tabla del libro', ev.industry, e => BOOK_POS[e.ticker]),
    industries_book_without_IBB_IHI_XHS: h2('industrias A′ sin IBB/IHI/XHS', indNoBook, e => BOOK_POS[e.ticker]),
    combined: h2('sectores (Cycle + XLRE) + industrias (libro), 50/50 por nivel', both, e => e.level === 'sector' ? L.SECTOR_POS_WITH_XLRE[e.ticker] : BOOK_POS[e.ticker]),
  };
  res.pring = pringStages(both, await pringSeries());
  res.events = both.map(e => ({ ticker: e.ticker, level: e.level, week: e.week, date: e.date, depth: r4(e.depth), rs63: r4(e.rs63),
    ret40: r4(e.out[H_MAIN].ret), excess40: r4(exc(e)), mae40: r4(e.out[H_MAIN].mae), n_cmp: e.out[H_MAIN].n_cmp }));

  fs.mkdirSync(WORK, { recursive: true });
  const out = FINAL ? OUT_FINAL : OUT_PLACEBO;
  fs.writeFileSync(out, JSON.stringify(res, null, 1) + '\n');
  const H = res.H1;
  console.log(res.mode);
  for (const [k, v] of Object.entries({ A: H.A_sectores, Aprime: H.Aprime_industrias, E_amp: H.E_amp_A_mas_Aprime }))
    console.log(`${k}: est ${v.estimate} IC ${v.ci95_quarter} → ${v.verdict} · ${v.robustness.label}${v.sensitive_to_temporal_dependence ? ' · sensible a la dependencia temporal' : ''}`);
  console.log('escrito', path.relative(process.cwd(), out));
})().catch(e => { console.error(e); process.exit(1); });
