'use strict';
// Giro de sectores deprimidos — cálculo común (preregistro v2, borrador 2026-11-28).
// Lo usan el registro semanal prospectivo (registry.js) y el recuento histórico (research/sector_turnaround_v2).
// Funciones puras salvo fetchDaily. Ninguna mira datos posteriores a la sesión de decisión.

const { fetchYahooChartRaw } = require('../../shared/quote-lib');

const LIB_VERSION = 'sector-turn-lib-1';

// ── Universo ─────────────────────────────────────────────────────────────────
const BENCH = 'SPY';
const SECTORS = ['XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY'];
// ETFs de industria de las listas del libro (Navarro, tabla 14-2). exposed=true: ya usados en el proyecto
// (auditoría research/sector_turnaround_v2/exposure_audit.json): solo prospectivo, fuera de la muestra histórica.
const INDUSTRIES = [
  { t: 'IYT',  book: 'Transportation', pos: 1, exposed: true },
  { t: 'XTN',  book: 'Transportation', pos: 1, exposed: false },
  { t: 'SMH',  book: 'Technology', pos: 2, exposed: true },
  { t: 'XSD',  book: 'Technology', pos: 2, exposed: false },
  { t: 'PAVE', book: 'Capital goods', pos: 3, exposed: false },
  { t: 'XME',  book: 'Basic industries & materials', pos: 4, exposed: true },
  { t: 'SLX',  book: 'Basic industries & materials', pos: 4, exposed: true },
  { t: 'XOP',  book: 'Energy', pos: 5, exposed: true },
  { t: 'OIH',  book: 'Energy', pos: 5, exposed: false },
  { t: 'XES',  book: 'Energy', pos: 5, exposed: false },
  { t: 'FCG',  book: 'Energy', pos: 5, exposed: false },
  { t: 'IHE',  book: 'Consumer staples & health care', pos: 6, exposed: false },
  { t: 'IHI',  book: 'Consumer staples & health care', pos: 6, exposed: false },
  { t: 'XHS',  book: 'Consumer staples & health care', pos: 6, exposed: false },
  { t: 'IBB',  book: 'Consumer staples & health care', pos: 6, exposed: false },
  { t: 'PBJ',  book: 'Consumer staples & health care', pos: 6, exposed: false },
  { t: 'IYZ',  book: 'Utilities', pos: 7, exposed: false },
  { t: 'KBE',  book: 'Financials, consumer cyclicals', pos: 8, exposed: false },
  { t: 'IAT',  book: 'Financials, consumer cyclicals', pos: 8, exposed: false },
  { t: 'KRE',  book: 'Financials, consumer cyclicals', pos: 8, exposed: true },
  { t: 'ITB',  book: 'Financials, consumer cyclicals', pos: 8, exposed: false },
  { t: 'XHB',  book: 'Financials, consumer cyclicals', pos: 8, exposed: true },
  { t: 'XRT',  book: 'Financials, consumer cyclicals', pos: 8, exposed: false },
  { t: 'CARZ', book: 'Financials, consumer cyclicals', pos: 8, exposed: false },
  { t: 'IYR',  book: 'Financials, consumer cyclicals', pos: 8, exposed: false },
];

// ── Posiciones narrativas ───────────────────────────────────────────────────
// Las 10 fases de Cycle (campo `order` de CYCLE_MAP) → 8 posiciones del libro. Petróleo y gas (5), uranio (6) y
// carbón (7) comparten la posición 5: no son siguientes unas de otras. Siguiente posición = pos % 8 + 1 (8 → 1).
const ORDER_TO_POS = { 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 5, 7: 5, 8: 6, 9: 7, 10: 8 };
const POS_LABEL = { 1: 'Early bull', 2: 'Early → mid bull', 3: 'Mid → late bull', 4: 'Late bull',
  5: 'Late bull → top', 6: 'Early bear', 7: 'Approaching late bear', 8: 'Late bear' };
const nextPos = p => (p % 8) + 1;

// Posición → sectores SPDR. Tabla principal = Cycle (XLRE sin fase, igual que la pestaña: ninguno de sus valores es
// inmobiliario). Variante con XLRE en la posición 8 = tabla del libro a nivel de sector (prospectiva; exposición
// declarada). XLC sin fase en ambas. La posición 1 (transporte) no tiene sector SPDR: XLI solo representa bienes
// de equipo (posición 3).
const SECTOR_POS_CYCLE = { XLK: 2, XLI: 3, XLB: 4, XLE: 5, XLP: 6, XLV: 6, XLU: 7, XLF: 8, XLY: 8 };
const SECTOR_POS_WITH_XLRE = { ...SECTOR_POS_CYCLE, XLRE: 8 };
const MAPPINGS = { cycle: SECTOR_POS_CYCLE, cycle_plus_xlre: SECTOR_POS_WITH_XLRE };

// ── Reglas D y G (congeladas en el preregistro) ─────────────────────────────
const D_LOOKBACK = 756;     // sesiones (3 años), incluida la de decisión
const D_DEPTH = -0.20;      // ratio ≥ 20 % por debajo de su máximo
const G_SMA = 50;           // media de 50 sesiones del ratio
const INDEP_WEEKS = 8;      // sin otro D∧G del mismo ETF en las 8 semanas de decisión anteriores

// ── Datos ────────────────────────────────────────────────────────────────────
// Barras diarias con la fecha local de la bolsa. close = cierre ajustado por splits (el que usa /api/quote);
// adj = cierre ajustado por splits y dividendos (para los ratios D/G).
function barsFromChart(result) {
  const ts = result?.timestamp ?? [];
  const q = result?.indicators?.quote?.[0] ?? {};
  const adj = result?.indicators?.adjclose?.[0]?.adjclose ?? [];
  const off = result?.meta?.gmtoffset ?? 0;
  const out = [];
  for (let i = 0; i < ts.length; i++) {
    const c = q.close?.[i];
    if (c == null || !(c > 0)) continue;
    const date = new Date((ts[i] + off) * 1000).toISOString().slice(0, 10);
    const a = adj[i] != null && adj[i] > 0 ? adj[i] : null;
    if (out.length && out[out.length - 1].date === date) out[out.length - 1] = { date, close: c, adj: a };
    else out.push({ date, close: c, adj: a });
  }
  return out;
}

async function fetchDaily(symbol, range = '5y', tries = 3) {
  let last;
  for (let k = 0; k < tries; k++) {
    try {
      const r = await fetchYahooChartRaw(symbol, range, '1d');
      if (r.ok && r.result) return { symbol, bars: barsFromChart(r.result), meta: { currency: r.result.meta?.currency,
        exchangeTimezoneName: r.result.meta?.exchangeTimezoneName, firstTradeDate: r.result.meta?.firstTradeDate } };
      last = new Error(`Yahoo ${r.status}`);
    } catch (e) { last = e; }
    await new Promise(res => setTimeout(res, 1500 * (k + 1)));
  }
  throw last;
}

// Historia diaria completa (range=max devuelve barras mensuales: hay que pedir el periodo con fechas).
async function fetchDailyFull(symbol, tries = 3) {
  let last;
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&period1=0` +
    `&period2=${Math.floor(Date.now() / 1000)}&includePrePost=false&events=div%2Csplit`;
  for (let k = 0; k < tries; k++) {
    try {
      const r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', Accept: 'application/json' } });
      if (r.ok) { const res = (await r.json())?.chart?.result?.[0]; if (res) return { symbol, bars: barsFromChart(res) }; }
      last = new Error(`Yahoo ${r.status}`);
    } catch (e) { last = e; }
    await new Promise(res => setTimeout(res, 1500 * (k + 1)));
  }
  throw last;
}

const cutBars = (bars, cutoff) => bars.filter(b => b.date <= cutoff);

// ── Semanas ─────────────────────────────────────────────────────────────────
function isoWeek(date) {                       // 'YYYY-Www' (semana ISO, lunes a domingo)
  const d = new Date(date + 'T00:00:00Z');
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day + 3);
  const y = d.getUTCFullYear();
  const jan4 = new Date(Date.UTC(y, 0, 4));
  const w = 1 + Math.round(((d - jan4) / 86400000 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  return `${y}-W${String(w).padStart(2, '0')}`;
}

// Índices de la última sesión de cada semana (solo semanas cuya última sesión es ≤ lastCompleteDate).
function weekEnds(dates, lastCompleteDate) {
  const out = [];
  for (let i = 0; i < dates.length; i++) {
    if (dates[i] > lastCompleteDate) break;
    const nextSameWeek = i + 1 < dates.length && dates[i + 1] <= lastCompleteDate && isoWeek(dates[i + 1]) === isoWeek(dates[i]);
    if (!nextSameWeek) out.push(i);
  }
  return out;
}

// ── Ratio y reglas ──────────────────────────────────────────────────────────
function ratioSeries(barsA, barsB) {
  const m = new Map(barsB.filter(b => b.adj).map(b => [b.date, b.adj]));
  const out = [];
  for (const b of barsA) {
    const d = m.get(b.date);
    if (b.adj && d) out.push({ date: b.date, r: b.adj / d });
  }
  return out;
}

function sma(vals, i, n) {
  if (i + 1 < n) return null;
  let s = 0;
  for (let k = i - n + 1; k <= i; k++) s += vals[k];
  return s / n;
}

// Métricas en el índice i (sesión de decisión) e iPrev (última sesión de la semana anterior).
function evalAt(ratio, i, iPrev) {
  const vals = ratio.map(x => x.r);
  const r = vals[i];
  const out = { date: ratio[i].date, ratio: r, n_hist: i + 1 };
  if (i + 1 >= D_LOOKBACK) {
    let mx = -Infinity;
    for (let k = i - D_LOOKBACK + 1; k <= i; k++) if (vals[k] > mx) mx = vals[k];
    out.max756 = mx;
    out.dist_max756 = r / mx - 1;
    out.D = out.dist_max756 <= D_DEPTH;
  } else { out.max756 = null; out.dist_max756 = null; out.D = null; }
  const s = sma(vals, i, G_SMA);
  out.sma50 = s;
  out.above_sma50 = s == null ? null : r > s;
  if (iPrev != null && iPrev >= 0) {
    const sp = sma(vals, iPrev, G_SMA);
    out.prev_week_date = ratio[iPrev].date;
    out.prev_above_sma50 = sp == null ? null : vals[iPrev] > sp;
  } else out.prev_above_sma50 = null;
  out.G = out.above_sma50 == null || out.prev_above_sma50 == null ? null : (out.above_sma50 && !out.prev_above_sma50);
  out.DG = out.D == null || out.G == null ? null : out.D && out.G;
  return out;
}

// Serie semanal completa de un ratio hasta lastCompleteDate: [{week, ...evalAt}] + independencia.
function weeklyEvents(ratio, lastCompleteDate) {
  const ends = weekEnds(ratio.map(x => x.date), lastCompleteDate);
  const rows = ends.map((i, k) => ({ week: isoWeek(ratio[i].date), ...evalAt(ratio, i, k > 0 ? ends[k - 1] : null) }));
  for (let k = 0; k < rows.length; k++) {
    if (!rows[k].DG) { rows[k].independent = null; continue; }
    let prior = false;
    for (let j = Math.max(0, k - INDEP_WEEKS); j < k; j++) if (rows[j].DG) prior = true;
    rows[k].independent = !prior;
  }
  return rows;
}

// ── Cycle simplificado (solo ETFs/valores con role "proxy" de la tabla de Cycle) ───────────────────────────
// Misma fórmula que calcPhaseScores de cycle.html, con los retornos de /api/quote: entero de
// (cierre_t / cierre_{t-21|63} − 1) × 100 sobre el cierre ajustado por splits; α = 0,7·(m3−SPYm3) + 0,3·(m1−SPYm1);
// puntuación de fase = media de α de los proxies disponibles. NO es la pestaña real (que promedia también las
// acciones elegidas en 2026): es la reconstrucción histórica posible.
function quoteRets(bars) {                    // bars ya cortadas en la fecha de decisión
  const n = bars.length; if (!n) return null;
  const price = bars[n - 1].close;
  const pct = (a, b) => b ? Math.round((a - b) / Math.abs(b) * 100) : null;
  const ret = d => { const i = n - 1 - d; return i >= 0 && bars[i].close ? pct(price, bars[i].close) : null; };
  return { m1: ret(21), m3: ret(63), last: bars[n - 1].date };
}

function simplifiedPhaseScores(cycleMap, barsByTicker, cutoff) {
  const spyB = cutBars(barsByTicker[BENCH] || [], cutoff);
  const spy = quoteRets(spyB);
  return cycleMap.map(ph => {
    const proxies = ph.sectors.flatMap(s => s.tickers).filter(t => t.role === 'proxy').map(t => t.ticker);
    const used = [];
    for (const t of proxies) {
      const b = cutBars(barsByTicker[t] || [], cutoff);
      if (!b.length || b[b.length - 1].date !== spy?.last) continue;       // sin dato de esa sesión: no cuenta
      const q = quoteRets(b);
      if (!q || q.m3 == null || spy?.m3 == null) continue;
      let relM1 = q.m1 != null && spy.m1 != null ? q.m1 - spy.m1 : null;
      const relM3 = q.m3 - spy.m3;
      if (relM1 == null) relM1 = relM3;
      used.push({ ticker: t, alpha: 0.7 * relM3 + 0.3 * relM1 });
    }
    const score = used.length ? used.reduce((a, s) => a + s.alpha, 0) / used.length : null;
    return { order: ph.order, phase: ph.phase, pos: ORDER_TO_POS[ph.order], proxies, used: used.map(u => u.ticker), score };
  });
}

// Fase dominante = mayor puntuación (empate: la primera en el orden de la tabla, igual que el sort estable de la
// pestaña). Devuelve también la posición y la siguiente.
function dominantOf(scored) {
  const s = scored.filter(p => p.score != null);
  if (!s.length) return null;
  const top = [...s].sort((a, b) => b.score - a.score)[0];
  const pos = ORDER_TO_POS[top.order];
  return { order: top.order, phase: top.phase, score: top.score, pos, next_pos: nextPos(pos), n_scored: s.length };
}

function concordance(ticker, nextPosition, mapping) {
  const p = mapping[ticker];
  if (p == null) return { mapped: false, concordant: null };
  return { mapped: true, pos: p, concordant: p === nextPosition };
}

module.exports = {
  LIB_VERSION, BENCH, SECTORS, INDUSTRIES, ORDER_TO_POS, POS_LABEL, nextPos, SECTOR_POS_CYCLE,
  SECTOR_POS_WITH_XLRE, MAPPINGS, D_LOOKBACK, D_DEPTH, G_SMA, INDEP_WEEKS,
  barsFromChart, fetchDaily, fetchDailyFull, cutBars, isoWeek, weekEnds, ratioSeries, sma, evalAt, weeklyEvents,
  quoteRets, simplifiedPhaseScores, dominantOf, concordance,
};
