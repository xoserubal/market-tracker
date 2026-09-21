// ── Screener Lib — registro extensible de screeners técnicos ───────────────
// Cada screener es una regla pura sobre los campos que ya devuelve
// buildQuoteData() (shared/quote-lib.js) — el mismo dato exacto que ve el
// resto del dashboard (Portfolio Tracker, Trullás…), sin ningún cálculo
// nuevo ni duplicado. Añadir un screener nuevo = añadir una entrada al
// array SCREENERS con su propia evaluate() + columnas — no requiere tocar
// screeners.html ni ningún pipeline.
//
// evaluate(q) devuelve siempre:
//   { status: '<id de estado propio del screener>', pass: bool,
//     sortValue: number|null, detail: {...} }
// `pass` = el ticker coincide con el screener (aparece como candidato).
// `sortValue` = para ordenar los candidatos que sí pasan, menor = mejor
// (ej. "más cerca de cruzar"); puede quedar null si no aplica.
//
// Dual export navegador (funciones/consts globales via <script> plano,
// mismo patrón que shared/flow-score.js) / Node (module.exports) — usado
// tanto desde screeners.html como, si algún screener futuro necesita
// cómputo pesado fuera del navegador, desde un script standalone.

function fmtNum(v, decimals) {
  if (v == null) return '—';
  return v.toFixed(decimals != null ? decimals : 4);
}
function fmtDelta(v) {
  if (v == null) return '—';
  const arrow = v > 0 ? '↑' : v < 0 ? '↓' : '';
  return `${v >= 0 ? '+' : ''}${v.toFixed(3)} ${arrow}`;
}
function fmtBool(v) {
  return v == null ? '—' : (v ? '✓' : '✗');
}

// ── Screener 1: MACD cruzando el 0 al alza ──────────────────────────────
// Pedido por el usuario 2026-09-21: tendencia alcista + línea MACD
// (EMA12−EMA26, calcMACD().macdLine en quote-lib.js — distinta del
// histograma que ya usa macdBull) todavía negativa pero subiendo, cerca de
// cruzar a positivo. "Cerca" se normaliza en unidades de ATR14 (mismo
// criterio ya usado en el proyecto para distancias — dist_sma20_atr en
// pcs_calculator.py, extension_risk) en vez de un valor absoluto de MACD,
// que no es comparable entre tickers de precio muy distinto.
//
// Umbral de proximidad (≤1×ATR) y ventana de tendencia (macdLineDelta5,
// ya calculado en quote-lib.js) sin calibrar contra rendimiento posterior
// — primera pasada, fase de observación, mismo criterio que el resto de
// señales nuevas de este proyecto (extension_risk, Koncorde, ATLAS Mini…).
function evalMacdZeroCrossUp(q) {
  if (q == null || q.macdLine == null || q.macdLineBull == null) {
    return { status: 'no_data', pass: false, sortValue: null, detail: {} };
  }

  const trendUp = q.closeAboveSma200 === true && q.sma50 != null && q.sma200 != null && q.sma50 > q.sma200;
  const rising  = q.macdLineDelta5 != null && q.macdLineDelta5 > 0;
  const distAtr = q.atrAbs ? +(Math.abs(q.macdLine) / q.atrAbs).toFixed(2) : null;
  const detail  = { trendUp, rising, distAtr };

  if (q.macdLineBull) {
    return { status: 'already_crossed', pass: false, sortValue: null, detail };
  }
  if (!trendUp) {
    return { status: 'no_uptrend', pass: false, sortValue: distAtr, detail };
  }
  if (!rising) {
    return { status: 'not_rising', pass: false, sortValue: distAtr, detail };
  }
  if (distAtr == null || distAtr > 1.0) {
    return { status: 'too_far', pass: false, sortValue: distAtr, detail };
  }

  // Estimación informativa (no forma parte del gate): a qué ritmo medio de
  // las últimas 5 sesiones, cuántas sesiones más para cruzar el 0 — pura
  // extrapolación lineal, puede no cumplirse.
  const paceEst     = q.macdLineDelta5 / 5;
  const sessionsEst = paceEst > 0 ? Math.max(1, Math.ceil(Math.abs(q.macdLine) / paceEst)) : null;
  detail.sessionsEst = sessionsEst;

  return { status: 'candidate', pass: true, sortValue: distAtr, detail };
}

const SCREENERS = [
  {
    id: 'macd_zero_cross_up',
    label: 'MACD cruzando el 0 al alza',
    shortLabel: 'MACD → 0 ↑',
    color: '#0d47a1',
    description: 'Tendencia alcista (precio y SMA50 por encima de SMA200) + línea MACD (EMA12−EMA26) todavía en negativo pero subiendo, a ≤1×ATR14 de cruzar a positivo.',
    rulesText: [
      'Tendencia alcista: precio > SMA200 y SMA50 > SMA200.',
      'Línea MACD (no el histograma) todavía negativa: macdLine < 0.',
      'Con impulso: la línea MACD sube respecto a hace 5 sesiones (macdLineDelta5 > 0).',
      'Próxima al cruce: distancia a cero ≤ 1×ATR14 (|macdLine| / ATR14 abs ≤ 1.0) — normalizado en ATR porque el valor crudo de MACD no es comparable entre tickers de precio distinto.',
    ],
    statuses: {
      candidate:        { label: 'Candidato',             badge: 'green'   },
      too_far:          { label: 'Sube, lejos de 0',       badge: 'yellow'  },
      not_rising:       { label: 'Sin impulso alcista',     badge: 'neutral' },
      no_uptrend:       { label: 'Sin tendencia alcista',   badge: 'neutral' },
      already_crossed:  { label: 'Ya cruzó (MACD > 0)',     badge: 'blue'    },
      no_data:          { label: 'Histórico insuficiente',  badge: 'neutral' },
    },
    columns: [
      { header: 'MACD línea',      get: q => q.macdLine,              format: v => fmtNum(v, 4),
        tooltip: 'Línea MACD (EMA12 − EMA26) — distinta del histograma clásico (línea vs su señal EMA9). Negativa = todavía por debajo de cero; positiva = ya cruzó.' },
      { header: 'Δ5 sesiones',     get: q => q.macdLineDelta5,        format: fmtDelta,
        tooltip: 'Cambio de la línea MACD respecto a hace 5 sesiones. Positivo (↑) = subiendo hacia cero; negativo (↓) = alejándose o bajando.' },
      { header: 'Dist. a 0 (ATR)', get: (q, r) => r.detail.distAtr,   format: v => v == null ? '—' : v.toFixed(2) + '×',
        tooltip: 'Distancia de la línea MACD a cero, en múltiplos de ATR14 — normalizada así porque el valor crudo de MACD no es comparable entre tickers de precio muy distinto. Este screener exige ≤1.0× para considerar el cruce "cercano".' },
      { header: 'Sesiones est.',   get: (q, r) => r.detail.sessionsEst, format: v => v == null ? '—' : '~' + v,
        tooltip: 'Estimación informativa, no forma parte de la regla: al ritmo medio de las últimas 5 sesiones, cuántas sesiones más tardaría en cruzar cero. Extrapolación lineal simple — puede no cumplirse.' },
      { header: 'Tendencia',       get: (q, r) => r.detail.trendUp,   format: fmtBool,
        tooltip: '✓ si precio > SMA200 y SMA50 > SMA200 (tendencia alcista clásica); ✗ si no se cumple alguna de las dos.' },
      { header: 'RSI14',           get: q => q.rsi,                   format: v => v == null ? '—' : String(v),
        tooltip: 'RSI de 14 sesiones (Wilder) — dato de contexto, no forma parte de la regla de este screener.' },
    ],
    evaluate: evalMacdZeroCrossUp,
  },
];

function getScreener(id) {
  return SCREENERS.find(s => s.id === id) || null;
}

// Evalúa un screener sobre {ticker: quoteData} y devuelve las filas
// resultantes con ticker/status/pass/sortValue/detail — sin ordenar
// (el llamador decide criterio de orden, normalmente pass primero y
// sortValue ascendente).
function runScreener(screener, quotesByTicker) {
  return Object.entries(quotesByTicker || {}).map(([ticker, q]) => {
    const r = screener.evaluate(q);
    return { ticker, q, ...r };
  });
}

// Export CommonJS opcional — permite require() desde un script Node
// standalone sin romper el uso como <script> plano en el navegador (donde
// `module` no existe), mismo patrón que shared/flow-score.js.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { SCREENERS, getScreener, runScreener, evalMacdZeroCrossUp };
}
