// ── Flow State Lib — espejo JS de scripts/flow_state_lib.py ────────────────
// Mismos umbrales/constantes, misma lógica — duplicación deliberada entre
// Python (market_analysis_llm.py, que da el dato de verdad a Sol) y JS
// (screeners.html, 3 screeners discrecionales: Inflexión/Continuación/
// Reversión), mismo patrón ya aceptado en este proyecto para calcCMF/
// koncorde_alert_conditions.py+su espejo en portfolio.html — ver CLAUDE.md
// "Sol — disciplina de promoción EARLY/CONFIRMED" para el porqué completo
// y las dos relajaciones deliberadas (documentadas también en el .py).
//
// A diferencia del motor Python (que lee portfolio_daily_snapshot.jsonl +
// market_equities_daily_snapshot.jsonl directamente del disco), aquí el
// historial se pasa ya construido (fetch client-side de esos mismos
// ficheros estáticos, hecho una sola vez en screeners.html) — este módulo
// solo contiene las funciones puras de cálculo, sin I/O.

const FSL_EXCLUDED_BASKET_SECTIONS = new Set([
  'Cartera', 'Watchlist', 'Opciones',
  'MAJOR INDICES', 'MAG 6', 'BONDS / COMMODITIES',
]);
const FSL_KONC_BEARISH = new Set(['distribution_warning', 'bearish_aligned']);
const FSL_KONC_BULLISH_CONFIRMED = 'bullish_aligned';
const FSL_LEVERAGED_TICKERS = new Set(['UCO', 'UVXY', 'TQQQ', 'SOXL', 'TNA', 'SPXL', 'BTCC-B.TO']);

const FSL_DELTA_WINDOW = 5;
const FSL_EARLY_PERSIST_SESSIONS = 2;
const FSL_FLOW_MIN = -5.0, FSL_FLOW_MAX = 8.0;
const FSL_RSI_INFLEXION = [40.0, 58.0];
const FSL_RSI_CONTINUACION = [55.0, 68.0];
const FSL_RSI_EXTENDED = 70.0;
const FSL_RSI_REVERSION_MAX = 55.0;
const FSL_ATR_PCTILE_WINDOW = 60;
const FSL_ATR_PCTILE_MIN_ROWS = 20;
const FSL_ATR_PCTILE_BLOCK = 80.0;
const FSL_FLOW_EXTENDED_LOOKBACK = 10;
const FSL_FLOW_EXTENDED_THRESHOLD = 15.0;
const FSL_REVERSION_DEEP_NEGATIVE = -10.0;
const FSL_REVERSION_LOOKBACK = 10;
const FSL_CONTINUACION_MIN_ABOVE_ZERO_DAYS = 5;

// ── Cestas de tema (portfolio.json únicamente — universo de screeners.html) ─

function fslBuildBasketMembership(portfolioSections) {
  const membership = {};
  (portfolioSections || []).forEach(sec => {
    if (FSL_EXCLUDED_BASKET_SECTIONS.has(sec.name)) return;
    (sec.items || []).forEach(item => {
      if (!item.ticker) return;
      if (!membership[item.ticker]) membership[item.ticker] = new Set();
      membership[item.ticker].add(sec.name);
    });
  });
  return membership;
}

function fslBasketToTickers(membership) {
  const out = {};
  Object.entries(membership).forEach(([tk, baskets]) => {
    baskets.forEach(b => {
      if (!out[b]) out[b] = new Set();
      out[b].add(tk);
    });
  });
  return out;
}

function fslComputeThemeBreadth(ticker, membership, basketToTickers, flowToday, koncToday) {
  const baskets = membership[ticker];
  if (!baskets || baskets.size === 0) {
    return { baskets: [], breadthPct: null, confirmed: null, total: null, blocked: false };
  }
  const peers = new Set([ticker]);
  baskets.forEach(b => (basketToTickers[b] || new Set()).forEach(t => peers.add(t)));
  let confirmed = 0, total = 0;
  peers.forEach(p => {
    const f = flowToday[p];
    if (f == null) return;
    total++;
    if (f > 0 && !FSL_KONC_BEARISH.has(koncToday[p])) confirmed++;
  });
  if (total === 0) return { baskets: [...baskets].sort(), breadthPct: null, confirmed: null, total: null, blocked: false };
  return { baskets: [...baskets].sort(), breadthPct: +(confirmed / total).toFixed(3), confirmed, total, blocked: confirmed === 0 };
}

// ── Métricas derivadas de la serie ───────────────────────────────────────

function fslComputeSeriesMetrics(rowsAsc) {
  const flows = rowsAsc.map(r => r.flowScore);
  const out = rowsAsc.map((r, i) => {
    const f = flows[i];
    const fPrev = i >= 1 ? flows[i - 1] : null;
    const fBack = i >= FSL_DELTA_WINDOW ? flows[i - FSL_DELTA_WINDOW] : null;
    const delta5 = (f != null && fBack != null) ? +(f - fBack).toFixed(3) : null;
    const zeroCrossUp = f != null && fPrev != null && fPrev <= 0 && f > 0;
    const zeroCrossDown = f != null && fPrev != null && fPrev >= 0 && f < 0;
    return { ...r, delta5, zeroCrossUp, zeroCrossDown };
  });

  for (let i = 0; i < out.length; i++) {
    let up = 0, j = i;
    while (j >= 0 && out[j].delta5 != null && out[j].delta5 > 0) { up++; j--; }
    out[i].delta5PersistUp = up;

    let nonneg = 0; j = i;
    while (j >= 0 && out[j].delta5 != null && out[j].delta5 >= 0) { nonneg++; j--; }
    out[i].delta5PersistNonneg = nonneg;

    let above = 0; j = i;
    while (j >= 0 && out[j].flowScore != null && out[j].flowScore > 0) { above++; j--; }
    out[i].flowAboveZeroDays = above;

    let daysSinceCross = null;
    for (let k = i; k >= 0; k--) {
      if (out[k].zeroCrossUp) { daysSinceCross = i - k; break; }
    }
    out[i].daysSinceZeroCrossUp = daysSinceCross;
  }
  return out;
}

function fslAtrPercentileToday(rowsAsc) {
  const vals = rowsAsc.slice(-FSL_ATR_PCTILE_WINDOW).map(r => r.atrPct).filter(v => v != null);
  if (vals.length < FSL_ATR_PCTILE_MIN_ROWS) return null;
  const today = vals[vals.length - 1];
  const rank = vals.filter(v => v <= today).length / vals.length;
  return +(rank * 100).toFixed(1);
}

// ── Los 3 filtros (mismos umbrales y relajaciones que flow_state_lib.py) ──

function fslEvaluateInflexion(today, rowsAsc, atrPctile, theme) {
  const flow = today.flowScore;
  const reasons = [];
  let ok = true;
  if (flow == null) return { pass: false, reasons: ['sin dato de Flow'], sizingReduced: atrPctile == null };

  if (!(flow >= FSL_FLOW_MIN && flow <= FSL_FLOW_MAX)) { ok = false; reasons.push(`Flow ${flow} fuera del rango de inflexión [-5, +8]`); }

  const persistUp = today.delta5PersistUp || 0;
  const recentCross = today.daysSinceZeroCrossUp != null && today.daysSinceZeroCrossUp <= 3;
  const recentPositive = flow > 0 && (today.flowAboveZeroDays || 0) <= 3;
  const approaching = flow <= 0 && persistUp >= FSL_EARLY_PERSIST_SESSIONS;
  if (!(recentCross || recentPositive || approaching)) { ok = false; reasons.push('sin zero-cross reciente, Flow positivo reciente ni persistencia de ΔFlow hacia cero'); }
  if (persistUp < FSL_EARLY_PERSIST_SESSIONS) { ok = false; reasons.push(`ΔFlow no lleva ${FSL_EARLY_PERSIST_SESSIONS} sesiones consecutivas positivo`); }

  const rsi = today.rsi;
  if (rsi == null || !(rsi >= FSL_RSI_INFLEXION[0] && rsi <= FSL_RSI_INFLEXION[1])) { ok = false; reasons.push(`RSI ${rsi} fuera de 40-58`); }

  const konc = today.konc_alignment;
  if (FSL_KONC_BEARISH.has(konc)) { ok = false; reasons.push(`Koncorde en veto (${konc})`); }

  if (theme.blocked) { ok = false; reasons.push('tema con breadth 0 (ningún miembro de la cesta confirma)'); }

  const recent10 = rowsAsc.slice(-FSL_FLOW_EXTENDED_LOOKBACK).map(r => r.flowScore).filter(v => v != null);
  if (recent10.length && Math.max(...recent10) > FSL_FLOW_EXTENDED_THRESHOLD) { ok = false; reasons.push(`Flow ya superó ${FSL_FLOW_EXTENDED_THRESHOLD} en las últimas ${FSL_FLOW_EXTENDED_LOOKBACK} sesiones (extensión, no inflexión)`); }

  const sizingReduced = atrPctile == null;
  if (atrPctile != null && atrPctile > FSL_ATR_PCTILE_BLOCK) { ok = false; reasons.push(`ATR% en percentil ${atrPctile} (>80, extensión)`); }

  return { pass: ok, reasons, sizingReduced };
}

function fslEvaluateContinuacion(today, rowsAsc, relStrength, ticker) {
  const flow = today.flowScore;
  const reasons = [];
  let ok = true;

  if (!(flow > 0)) { ok = false; reasons.push('Flow no positivo'); }
  if ((today.flowAboveZeroDays || 0) < FSL_CONTINUACION_MIN_ABOVE_ZERO_DAYS) { ok = false; reasons.push(`Flow no lleva ${FSL_CONTINUACION_MIN_ABOVE_ZERO_DAYS} sesiones por encima de cero`); }

  const last5 = rowsAsc.slice(-5);
  const deltas = last5.map(r => r.delta5).filter(d => d != null);
  const nonnegCount = deltas.filter(d => d >= 0).length;
  if (deltas.length < 3 || nonnegCount < 3) { ok = false; reasons.push('ΔFlow no es ≥0 en al menos 3 de las últimas 5 sesiones'); }

  const konc = today.konc_alignment;
  if (konc !== FSL_KONC_BULLISH_CONFIRMED) { ok = false; reasons.push(`Koncorde no bullish_aligned (${konc})`); }

  const rsi = today.rsi;
  const extended = rsi != null && rsi > FSL_RSI_EXTENDED;
  if (rsi == null || !(rsi >= FSL_RSI_CONTINUACION[0] && rsi <= FSL_RSI_CONTINUACION[1])) { ok = false; reasons.push(`RSI ${rsi} fuera de 55-68`); }

  if (relStrength == null || relStrength <= 0) { ok = false; reasons.push('fuerza relativa 1M no positiva (aproximada: m1 del ticker − m1 de ^GSPC)'); }

  const hist = today.macdHist, histDelta = today.macdHistDelta1;
  const histDecel = histDelta != null && histDelta < 0;
  if (hist == null || hist < 0 || histDecel) { ok = false; reasons.push('histograma MACD no confirma (negativo o decelerando)'); }

  if (FSL_LEVERAGED_TICKERS.has(ticker)) { ok = false; reasons.push('vehículo apalancado — no hereda la etiqueta de continuación del subyacente'); }

  const last2 = rowsAsc.slice(-2).map(r => r.delta5);
  const deltaFlipHigh = flow > 0 && last2.length === 2 && last2.every(d => d != null && d < 0);
  const mature = extended || deltaFlipHigh || (histDecel && flow > FSL_FLOW_EXTENDED_THRESHOLD);

  return { pass: ok && !mature, mature: !!mature, reasons };
}

function fslEvaluateReversion(today, rowsAsc) {
  const reasons = [];
  let ok = true;

  const window10 = rowsAsc.slice(-FSL_REVERSION_LOOKBACK);
  const hadDeepNegative = window10.some(r => r.flowScore != null && r.flowScore < FSL_REVERSION_DEEP_NEGATIVE);
  if (!hadDeepNegative) { ok = false; reasons.push(`Flow no estuvo por debajo de ${FSL_REVERSION_DEEP_NEGATIVE} en las últimas ${FSL_REVERSION_LOOKBACK} sesiones`); }

  const last3 = rowsAsc.slice(-3);
  const deltas = last3.map(r => r.delta5);
  if (last3.length < 3 || deltas.some(d => d == null || d <= 0)) { ok = false; reasons.push('ΔFlow no es positivo en las 3 últimas sesiones consecutivas'); }

  const prices = last3.map(r => r.price);
  if (prices.length === 3 && !prices.some(p => p == null) && rowsAsc.length >= 6) {
    const priorWindow = rowsAsc.slice(-6, -3);
    const priorPrices = priorWindow.map(r => r.price).filter(p => p != null);
    if (priorPrices.length && Math.min(...prices) < Math.min(...priorPrices)) { ok = false; reasons.push('el precio ha hecho un mínimo nuevo en esas 3 sesiones'); }
  }

  const konc = today.konc_alignment;
  if (FSL_KONC_BEARISH.has(konc)) { ok = false; reasons.push(`Koncorde sigue en veto (${konc})`); }

  const rsi = today.rsi;
  if (rsi == null || rsi >= FSL_RSI_REVERSION_MAX) { ok = false; reasons.push(`RSI ${rsi} no está saliendo de sobreventa por debajo de ${FSL_RSI_REVERSION_MAX}`); }

  return { pass: ok, reasons };
}

// ── API de alto nivel ────────────────────────────────────────────────────

function fslEvaluateTicker(ticker, ctx) {
  const rowsAscRaw = ctx.history[ticker] || [];
  if (rowsAscRaw.length < 6) return { ticker, dataStatus: 'insufficient_data' };

  const rowsAsc = fslComputeSeriesMetrics(rowsAscRaw);
  const today = rowsAsc[rowsAsc.length - 1];

  const flowToday = {}, koncToday = {};
  Object.entries(ctx.history).forEach(([tk, rows]) => {
    if (!rows.length) return;
    const last = rows[rows.length - 1];
    if (last.flowScore != null) flowToday[tk] = last.flowScore;
    koncToday[tk] = last.konc_alignment;
  });
  const theme = fslComputeThemeBreadth(ticker, ctx.membership, ctx.basketToTickers, flowToday, koncToday);

  const atrPctile = fslAtrPercentileToday(rowsAsc);
  let relStrength = null;
  if (ctx.benchmarkM1 != null && today.m1 != null) relStrength = +(today.m1 - ctx.benchmarkM1).toFixed(2);

  const inflexion = fslEvaluateInflexion(today, rowsAsc, atrPctile, theme);
  const continuacion = fslEvaluateContinuacion(today, rowsAsc, relStrength, ticker);
  const reversion = fslEvaluateReversion(today, rowsAsc);

  return {
    ticker, date: today.date, dataStatus: 'ok',
    flow: today.flowScore, delta5: today.delta5, zeroCrossUp: today.zeroCrossUp,
    daysSinceZeroCrossUp: today.daysSinceZeroCrossUp, flowAboveZeroDays: today.flowAboveZeroDays,
    rsi: today.rsi, konc_alignment: today.konc_alignment, atrPctile, relStrength1m: relStrength,
    theme, inflexion, continuacion, reversion,
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    fslBuildBasketMembership, fslBasketToTickers, fslComputeThemeBreadth,
    fslComputeSeriesMetrics, fslAtrPercentileToday,
    fslEvaluateInflexion, fslEvaluateContinuacion, fslEvaluateReversion, fslEvaluateTicker,
    FSL_KONC_BEARISH, FSL_EXCLUDED_BASKET_SECTIONS,
  };
}
