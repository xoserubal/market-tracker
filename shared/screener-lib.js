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
// (ej. "más cerca de cruzar", o magnitud invertida para que "más fuerte"
// quede primero); puede quedar null si no aplica.
//
// Dual export navegador (funciones/consts globales via <script> plano,
// mismo patrón que shared/flow-score.js) / Node (module.exports) — usado
// tanto desde screeners.html como, si algún screener futuro necesita
// cómputo pesado fuera del navegador, desde un script standalone.

function fmtNum(v, decimals) {
  if (v == null) return '—';
  return v.toFixed(decimals != null ? decimals : 4);
}
function fmtBool(v) {
  return v == null ? '—' : (v ? '✓' : '✗');
}
function fmtSigned(v, decimals, suffix) {
  if (v == null) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(decimals != null ? decimals : 3) + (suffix || '');
}

// SMA50 > SMA200 ("golden cross" clásico) — null si falta alguna media
// (ticker con poco histórico). Deliberadamente NO es un filtro del screener
// (ver comentario de evalMacdHistCrossUp más abajo, y CLAUDE.md 2026-09-22:
// exigirlo bloqueaba el caso real de META) — se expone solo como marca
// informativa + filtro opcional del lado de la UI (screeners.html), nunca
// como parte de evaluate()/pass.
function smaTrendUp(q) {
  if (q == null || q.sma50 == null || q.sma200 == null) return null;
  return q.sma50 > q.sma200;
}

// ── Screener: MACD — cruce alcista del histograma, ya confirmado ───────────
// Rediseñado 2026-09-22 a partir de una petición explícita del usuario tras
// comprobar en un caso real (META, ver CLAUDE.md) que la versión anterior
// (línea MACD a punto de cruzar cero + filtro de tendencia SMA50>SMA200)
// no habría detectado ese movimiento: el filtro de tendencia (un "cruce de
// medias" tipo golden cross) llegaba sistemáticamente tarde porque SMA200
// es una media muy lenta. Este screener cambia de enfoque por completo:
// en vez de "a punto de cruzar", busca "el cruce del HISTOGRAMA (línea MACD
// vs su señal EMA9) ya se ha producido", sin ningún filtro de tendencia de
// fondo, y cuantifica la fuerza de ese cruce.
//
// Tres decisiones tomadas explícitamente con el usuario (no supuestos
// míos): (1) magnitud = trayectoria media de los saltos diarios del
// histograma, tomados tanto antes como después del cruce — no el valor
// puntual de hoy ni solo el salto del día exacto del cruce; (2) el cruce
// tiene que ser reciente (ventana de 10 sesiones) para que el screener siga
// siendo accionable, no una lista de todo lo que lleva en verde desde hace
// meses; (3) sin filtro de tendencia adicional (ni SMA50/SMA200 ni ningún
// otro) — a propósito, para no repetir el fallo detectado con META.
//
// HIST_CROSS_LOOKBACK (10 sesiones) gobierna dos cosas a la vez: cuán
// reciente debe ser el cruce para contar como candidato, y cuánto se mira
// "hacia atrás" desde el cruce para promediar los saltos previos —
// deliberado, un solo número en vez de dos umbrales sin relación entre sí.
// Sin calibrar contra rendimiento posterior — primera pasada, fase de
// observación, mismo criterio que el resto de umbrales nuevos del proyecto.
const HIST_CROSS_LOOKBACK = 10;

function evalMacdHistCrossUp(q) {
  const h = q && q.macdHistRecent;
  if (!Array.isArray(h) || h.length < 2) {
    return { status: 'no_data', pass: false, sortValue: null, detail: {} };
  }
  const n = h.length;

  if (h[n - 1] < 0) {
    return { status: 'not_bullish', pass: false, sortValue: null, detail: {} };
  }

  // Retrocede desde hoy mientras el histograma siga en verde — crossIdx
  // queda en el primer día de la racha alcista actual (el día del cruce).
  let crossIdx = n - 1;
  while (crossIdx > 0 && h[crossIdx - 1] >= 0) crossIdx--;

  const sessionsAgo = (n - 1) - crossIdx; // 0 = cruzó hoy mismo
  const insufficientHistory = crossIdx === 0 && h.length < HIST_CROSS_LOOKBACK + 1;
  if (insufficientHistory) {
    return { status: 'no_data', pass: false, sortValue: null, detail: {} };
  }
  if (crossIdx === 0 || sessionsAgo > HIST_CROSS_LOOKBACK) {
    // O bien toda la ventana disponible (30 barras) ya estaba en verde —
    // el cruce real es más antiguo de lo que podemos ver aquí — o lo
    // localizamos pero cae fuera de la ventana de recencia.
    return { status: 'cross_too_old', pass: false, sortValue: null, detail: { crossSessionsAgo: sessionsAgo } };
  }

  // Trayectoria media de los saltos diarios del histograma: tramo "antes"
  // (hasta HIST_CROSS_LOOKBACK sesiones antes del cruce, recortado si hay
  // menos margen en el array) + tramo "después" (del cruce a hoy).
  const beforeStart = Math.max(1, crossIdx - HIST_CROSS_LOOKBACK);
  const jumps = [];
  for (let i = beforeStart; i <= n - 1; i++) jumps.push(h[i] - h[i - 1]);
  const avgJump = jumps.reduce((a, b) => a + b, 0) / jumps.length;
  const avgJumpAtr = q.atrAbs ? avgJump / q.atrAbs : null;

  const detail = {
    crossSessionsAgo: sessionsAgo,
    avgJump: +avgJump.toPrecision(4),
    avgJumpAtr: avgJumpAtr != null ? +avgJumpAtr.toPrecision(3) : null,
    histNow: h[n - 1],
  };
  // Orden: magnitud (en ATR si hay dato, si no cruda) descendente = cruce
  // más fuerte primero. sortValue se invierte porque el resto del sistema
  // ordena ascendente (menor = mejor).
  const magnitude = avgJumpAtr != null ? avgJumpAtr : avgJump;
  return { status: 'candidate', pass: true, sortValue: -magnitude, detail };
}

const SCREENERS = [
  {
    id: 'macd_hist_cross_up',
    label: 'MACD — cruce alcista del histograma confirmado',
    shortLabel: 'MACD hist ↑',
    color: '#1b5e20',
    description: 'El histograma MACD (línea vs su señal EMA9) ya ha cruzado a positivo dentro de las últimas 10 sesiones — sin filtro de tendencia. Cuantificado por la trayectoria media de los saltos diarios del histograma, antes y después del cruce, normalizada en ATR14.',
    rulesText: [
      'El histograma MACD (macdHist = línea − señal) está en positivo hoy.',
      'El cruce de negativo a positivo ocurrió dentro de las últimas 10 sesiones — si lleva más tiempo en positivo, no cuenta como candidato "reciente" (queda marcado como "cruce antiguo").',
      'Magnitud: media de los saltos diarios del histograma (hist de hoy − hist de ayer, y así sucesivamente) en la ventana que va desde hasta 10 sesiones antes del cruce hasta hoy — cuantifica la fuerza/limpieza del cruce, no solo si ocurrió. Normalizada por ATR14 para comparar entre tickers de precio y volatilidad distintos.',
      'Sin filtro de tendencia adicional (sin SMA50/SMA200 ni ningún otro) — a propósito: la versión anterior de este screener exigía precio y SMA50 por encima de SMA200, y ese filtro habría bloqueado un caso real (META, ver CLAUDE.md) donde el histograma ya giraba al alza semanas antes de que el precio recuperase su media de 200 sesiones.',
    ],
    statuses: {
      candidate:      { label: 'Cruce reciente confirmado', badge: 'green'   },
      cross_too_old:  { label: 'En verde, cruce antiguo',   badge: 'blue'    },
      not_bullish:    { label: 'Histograma en negativo',    badge: 'neutral' },
      no_data:        { label: 'Histórico insuficiente',    badge: 'neutral' },
    },
    columns: [
      { header: 'Histograma hoy',    get: q => q.macdHist,                format: v => fmtNum(v, 3),
        tooltip: 'Histograma MACD hoy (línea EMA12−EMA26 menos su señal EMA9). Positivo = por encima de la señal (alcista); cuanto mayor, más separación actual.' },
      { header: 'Sesiones cruce',    get: (q, r) => r.detail.crossSessionsAgo, format: v => v == null ? '—' : String(v),
        tooltip: 'Sesiones transcurridas desde que el histograma cruzó de negativo a positivo. 0 = cruzó hoy mismo. Este screener solo admite candidatos con cruce dentro de las últimas 10 sesiones.' },
      { header: 'Magnitud (ATR)',    get: (q, r) => r.detail.avgJumpAtr,  format: v => v == null ? '—' : fmtSigned(v, 3, '×'),
        tooltip: 'Trayectoria media de los saltos diarios del histograma (antes y después del cruce), normalizada por ATR14 — cuantifica la fuerza/limpieza del cruce. Criterio de orden de la tabla: mayor magnitud primero.' },
      { header: 'RSI14',             get: q => q.rsi,                     format: v => v == null ? '—' : String(v),
        tooltip: 'RSI de 14 sesiones (Wilder) — dato de contexto, no forma parte de la regla de este screener.' },
      { header: 'SMA50>200',         get: q => smaTrendUp(q),             format: fmtBool,
        tooltip: 'SMA50 por encima de SMA200 ("golden cross" clásico) — marca informativa, NO forma parte de la regla de este screener (pedido explícitamente 2026-09-22: quitarlo como filtro obligatorio fue lo que corrigió el fallo con META). Actívalo como filtro opcional con el botón de arriba si solo quieres ver candidatos con tendencia de fondo confirmada.' },
    ],
    // Filtros opcionales del lado de la UI (screeners.html): NO alteran
    // evaluate()/pass/sortValue — son un botón "toggle" que el usuario
    // enciende/apaga para estrechar la vista sin tocar la regla real del
    // screener. Mecanismo genérico del registro, reutilizable por
    // screeners futuros (no específico de MACD).
    extraFilters: [
      { id: 'sma_trend_up', label: 'Solo con SMA50 > SMA200', predicate: q => smaTrendUp(q) === true,
        tooltip: 'Filtro opcional, no forma parte de la regla del screener. Actívalo para ver solo los candidatos que además tienen la SMA50 por encima de la SMA200 (tendencia de fondo confirmada); apágalo para ver todos, incluidos los que giran al alza antes de que esa media lenta lo confirme (como pasó con META).' },
    ],
    evaluate: evalMacdHistCrossUp,
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
  module.exports = { SCREENERS, getScreener, runScreener, evalMacdHistCrossUp, smaTrendUp };
}
