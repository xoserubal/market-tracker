// ── Motor de scoring de Relative Flow Lab (fuente única) ────────────────────
//
// Extraído de relative.html (2026-10-16) para que la página y el registro diario
// de señales (scripts/relative_signal_log.js) usen EXACTAMENTE el mismo cálculo.
// Antes esto vivía inline en la página; un script de pipeline que lo reimplementara
// habría acabado divergiendo (mismo riesgo ya vivido con calcCMF).
//
// Dual export: en el navegador se carga con <script src> y deja las funciones como
// globals (las usa el JSX tal cual); en Node se usa con require().
// NO cambiar fórmulas aquí sin pensar que cambia lo que muestra relative.html.

const avg = arr => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
const sma = (values, len) => values.length >= len ? avg(values.slice(-len)) : null;

const ret = (arr, bars) => {
  if (!arr || arr.length <= bars) return null;
  const last = arr[arr.length - 1]?.value, prev = arr[arr.length - 1 - bars]?.value;
  return last && prev ? (last / prev - 1) * 100 : null;
};
const retWindow = (arr, endOffset, bars) => {
  if (!arr || arr.length <= endOffset + bars) return null;
  const end = arr[arr.length - 1 - endOffset]?.value, start = arr[arr.length - 1 - endOffset - bars]?.value;
  return end && start ? (end / start - 1) * 100 : null;
};

function calcRSI(values, period = 14) {
  const v = values.filter(x => x != null);
  if (v.length < period + 1) return null;
  let gain = 0, loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = v[i] - v[i - 1];
    if (d > 0) gain += d / period; else loss += -d / period;
  }
  for (let i = period + 1; i < v.length; i++) {
    const d = v[i] - v[i - 1];
    gain = (gain * (period - 1) + Math.max(d, 0)) / period;
    loss = (loss * (period - 1) + Math.max(-d, 0)) / period;
  }
  if (loss === 0) return 100;
  return 100 - 100 / (1 + gain / loss);
}

function alignRatio(aSeries, bSeries) {
  const bMap = Object.fromEntries((bSeries || []).map(p => [p.date, p.close]));
  return (aSeries || [])
    .filter(p => bMap[p.date] != null && p.close != null)
    .map(p => ({ date: p.date, value: p.close / bMap[p.date] }))
    .filter(p => Number.isFinite(p.value));
}

// Núcleo: calcula la fila a partir de la serie del ratio ya alineada. Separado de
// buildRow para que el registro de señales pueda evaluar "el estado a fecha X" con
// ratio.slice(0, i + 1) sin realinear las dos patas cada vez.
function buildRowFromRatio(pair, ratio) {
  if (ratio.length < 70) return { ...pair, error: true, ratio };

  const values = ratio.map(p => p.value);
  const last = values[values.length - 1];
  const s20 = sma(values, 20);
  const s63 = sma(values, 63);
  const r1w = ret(ratio, 5);
  const r1m = ret(ratio, 21);
  const r3m = ret(ratio, 63);
  const r6m = ret(ratio, 126);
  const flowNow  = retWindow(ratio, 0, 5);
  const flowPrev = retWindow(ratio, 5, 5);
  const flowChange = flowNow != null && flowPrev != null ? flowNow - flowPrev : null;
  const rsi = calcRSI(values);
  const high52 = Math.max(...values.slice(-252));
  const fromHigh = high52 ? (last / high52 - 1) * 100 : null;
  const trend = last > s20 && s20 > s63 ? "Up" : last < s20 && s20 < s63 ? "Down" : "Mixed";
  const trendAdj = trend === "Up" ? 2 : trend === "Down" ? -2 : 0;
  const rsiAdj = rsi > 65 ? 1.5 : rsi > 55 ? 0.8 : rsi < 35 ? -1.5 : rsi < 45 ? -0.8 : 0;
  const flowChangeAdj = flowChange == null ? 0 : Math.max(-3, Math.min(3, flowChange * 0.4));
  const score = Math.round((((r1w ?? 0) * 0.5) + ((r1m ?? 0) * 0.7) + ((r3m ?? 0) * 0.25) + trendAdj + rsiAdj + flowChangeAdj) * 10) / 10;
  return { ...pair, ratio, last, r1w, r1m, r3m, r6m, flowNow, flowPrev, flowChange, rsi, fromHigh, trend, score };
}

function buildRow(pair, history) {
  const a = history[pair.a]?.series;
  const b = history[pair.b]?.series;
  return buildRowFromRatio(pair, alignRatio(a, b));
}

function classify(row) {
  if (!row || row.error) return { label: "No data", bg: "#f0f0f0", fg: "#888" };
  if (row.score >= 8)  return { label: "Leader",    bg: "#c8e6c9", fg: "#1b5e20" };
  if (row.score >= 3)  return { label: "Improving",  bg: "#d0e8ff", fg: "#0d2e6e" };
  if (row.score <= -8) return { label: "Laggard",    bg: "#ffcdd2", fg: "#b71c1c" };
  if (row.score <= -3) return { label: "Weakening",  bg: "#fff0cc", fg: "#8a5200" };
  return { label: "Neutral", bg: "#f0f0f0", fg: "#555" };
}

// Top 3 Flow In/Out (Fase 4 RFL v2): flowChange, score y trend deben apuntar en la
// misma dirección.
//   Entrantes: flowChange > 0  AND score >= 0  AND trend !== "Down"
//   Salientes: flowChange < 0  AND score <= 0  AND trend !== "Up"
function coherentFlowDirection(row) {
  if (!row || row.error || row.flowChange == null || row.score == null) return null;
  if (row.flowChange > 0 && row.score >= 0 && row.trend !== "Down") return "in";
  if (row.flowChange < 0 && row.score <= 0 && row.trend !== "Up") return "out";
  return null;
}

// Orden de "calidad" de clasificación — para UPGRADED/DOWNGRADED y transiciones.
const RATIO_SIGNAL_RANK = { "Leader": 5, "Improving": 4, "Neutral": 3, "Weakening": 2, "Laggard": 1, "No data": 0 };

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { avg, sma, ret, retWindow, calcRSI, alignRatio, buildRowFromRatio, buildRow, classify, coherentFlowDirection, RATIO_SIGNAL_RANK };
}
