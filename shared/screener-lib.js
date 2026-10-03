// ── Screener Lib — registro extensible de screeners técnicos ───────────────
// Cada screener es un grupo de FILTROS independientes y combinables sobre
// los campos que ya devuelve buildQuoteData() (shared/quote-lib.js) — el
// mismo dato exacto que ve el resto del dashboard (Portfolio Tracker,
// Trullás…), sin ningún cálculo nuevo ni duplicado.
//
// screener.filters: array de { id, label, description, rulesText,
// statuses, columns, defaultActive, evaluate(q) }. evaluate(q) devuelve
// siempre { status, pass, sortValue, detail } — el resultado de ESE filtro
// en solitario, exactamente igual que antes. Lo nuevo (pedido 2026-09-22):
// el usuario puede tener VARIOS filtros activos a la vez (checkboxes en
// screeners.html, no un selector de uno solo) — un ticker es candidato del
// screener si cumple TODOS los filtros activos (AND). Añadir un filtro
// nuevo a un screener existente = añadir una entrada a su array `filters`;
// añadir un screener nuevo = una entrada nueva en SCREENERS — ninguno de
// los dos casos requiere tocar screeners.html.
//
// screener.extraFilters (aparte de `filters`): marcas puramente
// informativas con un toggle de vista — NUNCA alteran evaluate()/pass de
// ningún filtro, solo estrechan qué filas se muestran ya evaluadas (ver
// `sma_trend_up` más abajo). Mecanismo distinto a propósito: no todas las
// marcas útiles merecen ser una condición de candidatura con su propio
// status/columnas.
//
// Dual export navegador (funciones/consts globales via <script> plano,
// mismo patrón que shared/flow-score.js) / Node (module.exports) — usado
// tanto desde screeners.html como, si algún screener futuro necesita
// cómputo pesado fuera del navegador, desde un script standalone.

// En el navegador, shared/flow-state-lib.js se carga vía <script> ANTES que
// este archivo (mismo orden que screeners.html) y declara FSL_KONC_BEARISH
// como const de ámbito global compartido entre <script> tags — basta con
// LEER ese identificador más abajo, sin declararlo de nuevo (una segunda
// declaración `var`/`const` con el mismo nombre lanzaría "already declared"
// incluso en un <script> tag distinto, por cómo el navegador comparte el
// entorno léxico global entre scripts clásicos). En Node (require() para
// tests/scripts standalone, sin <script> de por medio) no existe ese
// global compartido, así que aquí se resuelve con un nombre DISTINTO
// (FSL_KONC_BEARISH_REF) para no colisionar con el de flow-state-lib.js.
var _fslNodeCompat = (typeof module !== 'undefined' && module.exports) ? require('./flow-state-lib.js') : null;
var FSL_KONC_BEARISH_REF = _fslNodeCompat ? _fslNodeCompat.FSL_KONC_BEARISH : FSL_KONC_BEARISH;

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
function fmtDelta(v) {
  if (v == null) return '—';
  const arrow = v > 0 ? '↑' : v < 0 ? '↓' : '';
  return `${v >= 0 ? '+' : ''}${v.toFixed(3)} ${arrow}`;
}

// SMA50 > SMA200 ("golden cross" clásico) — null si falta alguna media
// (ticker con poco histórico). Marca informativa + extraFilter opcional del
// lado de la UI (screeners.html) — no confundir con la condición de
// tendencia propia del filtro `line_near_zero_up`, que exige además precio
// > SMA200 (definición histórica más estricta, restaurada tal cual).
function smaTrendUp(q) {
  if (q == null || q.sma50 == null || q.sma200 == null) return null;
  return q.sma50 > q.sma200;
}

// ── Filtro: cruce alcista del histograma, ya confirmado ─────────────────
// Añadido 2026-09-22 a partir de un caso real (META, ver CLAUDE.md): un
// filtro de tendencia SMA obligatorio llegaba sistemáticamente tarde
// porque SMA200 es una media muy lenta. En vez de "a punto de cruzar",
// busca "el cruce del HISTOGRAMA (línea MACD vs su señal EMA9) ya se ha
// producido", sin exigir tendencia, y cuantifica la fuerza de ese cruce.
//
// Magnitud = trayectoria media de los saltos diarios del histograma, antes
// y después del cruce (no el valor puntual de hoy ni solo el salto del día
// exacto del cruce) — decisión explícita del usuario. Cruce reciente
// (ventana de 10 sesiones) para que el filtro siga siendo accionable.
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

// ── Filtro: línea MACD en tendencia alcista, cerca de cruzar el 0 ───────
// Versión original del screener (2026-09-21), restaurada 2026-09-22 como
// filtro independiente y combinable en vez de sustituida — el usuario
// quería conservar ambos enfoques ("cruce ya confirmado" vs "todavía no
// ha cruzado, pero está cerca y en tendencia") como piezas que se puedan
// sumar, no una alternativa excluyente a la otra.
//
// A diferencia de `hist_cross_confirmed`, este filtro SÍ exige tendencia
// (precio > SMA200 y SMA50 > SMA200) como parte de su propia regla —
// aquí es intencional: es justo la condición que define "todavía no ha
// cruzado, pero el terreno de fondo ya es alcista". El caso real de META
// (ver CLAUDE.md, 2026-09-22) mostró que exigir esto SIEMPRE bloqueaba
// movimientos reales — la solución no fue borrar la idea, fue dejar de
// forzarla como único camino: ahora conviven los dos filtros y el usuario
// elige (o combina) según lo que esté buscando.
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

// ── Screener: disciplina de promoción sobre Flow Score ──────────────────
// Añadido 2026-10-02 a partir de una auditoría externa sobre
// market_analysis_llm.jsonl (Sol, el LLM narrador) que encontró un patrón
// real y repetido: Sol etiqueta EARLY/CONFIRMED el mismo día que aparece un
// ΔFlow positivo de un solo día, sin zero-cross real ni persistencia de
// 2-3 sesiones — la auditoría del día siguiente tiene que deshacerlo (ver
// CLAUDE.md "Sol — disciplina de promoción EARLY/CONFIRMED" para el
// detalle completo, casos reales verificados contra datos crudos, y las
// dos relajaciones deliberadas respecto al texto literal de la auditoría).
//
// Los 3 filtros (evalFlowInflexion/evalFlowContinuacion/evalFlowReversion)
// son un ESPEJO de scripts/flow_state_lib.py (mismos umbrales/relajaciones,
// mismo motivo de duplicación ya aceptado en este proyecto que para
// calcCMF/koncorde_alert_conditions.py) — no recalculan nada aquí: leen
// `q._flow`, un objeto ya calculado por screeners.html antes de llamar a
// evaluate() (fetch de portfolio_daily_snapshot.jsonl + cestas de tema de
// portfolio.json + ^GSPC como benchmark), usando shared/flow-state-lib.js.
//
// Mismo motor exacto que da el dato de verdad a Sol en market_analysis_llm.py
// — "candidato del screener" y "columna Mecánico que ve Sol" son
// literalmente el mismo cálculo, solo con una UI distinta encima.

function evalFlowInflexion(q) {
  const f = q && q._flow;
  if (!f || f.dataStatus !== 'ok') return { status: 'no_data', pass: false, sortValue: null, detail: {} };
  const r = f.inflexion;
  let status = 'not_candidate';
  if (r.pass) status = 'candidate';
  else if (FSL_KONC_BEARISH_REF.has(f.konc_alignment)) status = 'vetoed_konc';
  else if (f.theme.blocked) status = 'vetoed_tema';
  const detail = { flow: f.flow, delta5: f.delta5, rsi: f.rsi, theme: f.theme, reasons: r.reasons };
  return { status, pass: r.pass, sortValue: r.pass ? -(f.delta5 ?? 0) : null, detail };
}

function evalFlowContinuacion(q) {
  const f = q && q._flow;
  if (!f || f.dataStatus !== 'ok') return { status: 'no_data', pass: false, sortValue: null, detail: {} };
  const r = f.continuacion;
  let status = 'not_candidate';
  if (r.pass) status = 'candidate';
  else if (r.mature) status = 'mature';
  else if (FSL_KONC_BEARISH_REF.has(f.konc_alignment)) status = 'vetoed_konc';
  const detail = { flow: f.flow, delta5: f.delta5, rsi: f.rsi, relStrength: f.relStrength1m, reasons: r.reasons };
  return { status, pass: r.pass, sortValue: r.pass ? -(f.flow ?? 0) : null, detail };
}

function evalFlowReversion(q) {
  const f = q && q._flow;
  if (!f || f.dataStatus !== 'ok') return { status: 'no_data', pass: false, sortValue: null, detail: {} };
  const r = f.reversion;
  let status = 'not_candidate';
  if (r.pass) status = 'candidate';
  else if (FSL_KONC_BEARISH_REF.has(f.konc_alignment)) status = 'vetoed_konc';
  const detail = { flow: f.flow, delta5: f.delta5, rsi: f.rsi, reasons: r.reasons };
  return { status, pass: r.pass, sortValue: r.pass ? f.rsi ?? 0 : null, detail };
}

const SCREENERS = [
  {
    id: 'flow_state_screener',
    label: 'Flow — Disciplina de promoción',
    shortLabel: 'Flow',
    color: '#0d47a1',
    description: 'Flow es estado, ΔFlow es cambio de estado — ninguno de los dos es señal de entrada por sí solo. 3 filtros independientes y combinables (AND) que exigen persistencia de 2-3 sesiones y ausencia de veto (Koncorde, breadth del tema) antes de contar como candidato. Mismo motor que usa market_analysis_llm.py para dar a Sol el dato de verdad contra el que reconciliar su propia narrativa.',
    filters: [
      {
        id: 'flow_inflexion', label: 'Inflexión temprana', shortLabel: 'Inflexión', defaultActive: true,
        description: 'Flow en zona de transición (-5/+8), con persistencia de ΔFlow hacia cero de 2+ sesiones, RSI 40-58, sin veto de Koncorde ni de breadth del tema, y sin haber estado ya extendido (Flow>15) en las últimas 10 sesiones.',
        rulesText: [
          'Flow entre -5 y +8 — fuera de ahí ya no es "temprano" (por debajo, suelo no confirmado; por encima, ya extendido).',
          'Zero-cross reciente (≤3 sesiones), Flow positivo de antigüedad ≤3 sesiones, O Flow todavía negativo pero con la persistencia de ΔFlow de la regla siguiente ya cumplida (relajación deliberada: un Flow que salta de negativo a muy extendido en una sola sesión, sin pasar por un cruce clásico, debe poder capturarse igual — verificado contra un caso real, ver CLAUDE.md).',
          'ΔFlow (Flow de hoy menos el de hace 5 sesiones) positivo en 2+ sesiones consecutivas.',
          'RSI entre 40 y 58.',
          'Koncorde distinto de distribution_warning/bearish_aligned.',
          'La cesta de tema del ticker (su sección de Portfolio Tracker) no tiene breadth 0 — si ningún miembro de la cesta confirma, el tema entero queda vetado.',
          'Flow no ha superado +15 en las últimas 10 sesiones (si ya lo hizo, es extensión, no inflexión).',
          'ATR% no está en el percentil >80 de su propia ventana de 60 sesiones (si hay menos de 20 sesiones de histórico, no se exige — "sizing reducido", no exclusión).',
        ],
        statuses: {
          candidate:      { label: 'Inflexión temprana',       badge: 'green'   },
          vetoed_konc:    { label: 'Vetado por Koncorde',       badge: 'red'     },
          vetoed_tema:    { label: 'Tema con breadth 0',        badge: 'orange'  },
          not_candidate:  { label: 'No cumple',                 badge: 'neutral' },
          no_data:        { label: 'Histórico insuficiente',    badge: 'neutral' },
        },
        columns: [
          { header: 'Flow',   get: (q, r) => r.detail.flow,    format: v => v == null ? '—' : fmtSigned(v, 1),
            tooltip: 'Flow Score de hoy. Este filtro exige que esté entre -5 y +8.' },
          { header: 'ΔFlow5', get: (q, r) => r.detail.delta5,  format: v => v == null ? '—' : fmtSigned(v, 1),
            tooltip: 'Flow de hoy menos Flow de hace 5 sesiones capturadas. Exige persistencia positiva de 2+ sesiones.' },
          { header: 'RSI14',  get: (q, r) => r.detail.rsi,     format: v => v == null ? '—' : String(v),
            tooltip: 'RSI de 14 sesiones. Este filtro exige 40-58.' },
          { header: 'Tema',   get: (q, r) => (r.detail.theme && r.detail.theme.baskets || []).join(', '), format: v => v || '—',
            tooltip: 'Cesta(s) de tema del ticker (sección de Portfolio Tracker) usada para el veto de breadth.' },
        ],
        evaluate: evalFlowInflexion,
      },
      {
        id: 'flow_continuacion', label: 'Continuación', shortLabel: 'Continuación', defaultActive: false,
        description: 'Tendencia de Flow ya establecida (positiva ≥5 sesiones) que no se está agotando: ΔFlow no negativo en 3 de las últimas 5 sesiones, RSI 55-68, Koncorde bullish_aligned, MACD histograma confirma.',
        rulesText: [
          'Flow positivo durante al menos 5 sesiones.',
          'ΔFlow ≥0 en al menos 3 de las últimas 5 sesiones (se permite una sesión plana, no una racha negativa).',
          'Koncorde en bullish_aligned exactamente — bullish_pending_3d_confirmation NO cuenta (literal de la auditoría: sin confirmación 3D no es continuación confirmada).',
          'RSI entre 55 y 68 — por debajo no es continuación, por encima es extensión.',
          'Fuerza relativa 1 mes positiva (aproximada: retorno del ticker menos el de ^GSPC — el proyecto no tiene un benchmark sectorial por ticker, se usa el índice general).',
          'Histograma MACD no negativo y no decelerando (confirmación, no disparador).',
          'No es un vehículo apalancado (UCO, UVXY, TQQQ…) — esos no heredan la etiqueta de continuación de su subyacente.',
          'Si RSI>70, o si el Flow sigue alto pero el ΔFlow se gira negativo 2 sesiones seguidas: no es "Continuación", es "Madura" (protección de beneficios, no entrada nueva) — estado distinto, no simplemente "no cumple".',
        ],
        statuses: {
          candidate:      { label: 'Continuación activa',       badge: 'green'   },
          mature:         { label: 'Madura — proteger beneficio', badge: 'yellow' },
          vetoed_konc:    { label: 'Vetado por Koncorde',        badge: 'red'     },
          not_candidate:  { label: 'No cumple',                  badge: 'neutral' },
          no_data:        { label: 'Histórico insuficiente',     badge: 'neutral' },
        },
        columns: [
          { header: 'Flow',        get: (q, r) => r.detail.flow,        format: v => v == null ? '—' : fmtSigned(v, 1),
            tooltip: 'Flow Score de hoy. Debe ser positivo y llevar ≥5 sesiones así.' },
          { header: 'ΔFlow5',      get: (q, r) => r.detail.delta5,      format: v => v == null ? '—' : fmtSigned(v, 1),
            tooltip: 'Flow de hoy menos Flow de hace 5 sesiones. Exige ≥0 en 3 de las últimas 5 sesiones.' },
          { header: 'RSI14',       get: (q, r) => r.detail.rsi,         format: v => v == null ? '—' : String(v),
            tooltip: 'RSI de 14 sesiones. Este filtro exige 55-68.' },
          { header: 'F.Rel. 1M',   get: (q, r) => r.detail.relStrength, format: v => v == null ? '—' : fmtSigned(v, 1, '%'),
            tooltip: 'Retorno 1 mes del ticker menos el de ^GSPC — aproximación de fuerza relativa (sin benchmark sectorial por ticker en el proyecto).' },
        ],
        evaluate: evalFlowContinuacion,
      },
      {
        id: 'flow_reversion', label: 'Reversión', shortLabel: 'Reversión', defaultActive: false,
        description: 'Recuperación real desde deterioro previo: Flow estuvo por debajo de -10 en las últimas 10 sesiones, ΔFlow positivo 3 sesiones consecutivas, sin mínimo nuevo de precio, Koncorde saliendo del veto, RSI saliendo de sobreventa.',
        rulesText: [
          'Flow estuvo por debajo de -10 en alguna de las últimas 10 sesiones (si nunca estuvo tan deteriorado, no es "reversión", es otra cosa).',
          'ΔFlow positivo durante 3 sesiones consecutivas — con menos de 3 no se etiqueta.',
          'El precio no ha hecho un mínimo nuevo en esas 3 sesiones.',
          'Koncorde sale de distribution_warning/bearish_aligned (si sigue ahí, no entra).',
          'RSI sale de sobreventa pero sigue por debajo de 55 (si ya está en 55+, ya no es "saliendo de sobreventa").',
        ],
        statuses: {
          candidate:      { label: 'Reversión en curso',        badge: 'green'   },
          vetoed_konc:    { label: 'Vetado por Koncorde',        badge: 'red'     },
          not_candidate:  { label: 'No cumple',                  badge: 'neutral' },
          no_data:        { label: 'Histórico insuficiente',     badge: 'neutral' },
        },
        columns: [
          { header: 'Flow',   get: (q, r) => r.detail.flow,   format: v => v == null ? '—' : fmtSigned(v, 1),
            tooltip: 'Flow Score de hoy.' },
          { header: 'ΔFlow5', get: (q, r) => r.detail.delta5, format: v => v == null ? '—' : fmtSigned(v, 1),
            tooltip: 'Flow de hoy menos Flow de hace 5 sesiones. Exige positivo 3 sesiones consecutivas.' },
          { header: 'RSI14',  get: (q, r) => r.detail.rsi,    format: v => v == null ? '—' : String(v),
            tooltip: 'RSI de 14 sesiones. Este filtro exige que esté saliendo de sobreventa, por debajo de 55.' },
        ],
        evaluate: evalFlowReversion,
      },
    ],
  },
  {
    id: 'macd_screener',
    label: 'MACD',
    shortLabel: 'MACD',
    color: '#1b5e20',
    description: 'Señales basadas en MACD. Los filtros de abajo son independientes y se pueden combinar (activa uno, varios, o todos): un ticker es candidato solo si cumple TODOS los filtros que tengas activos a la vez.',
    filters: [
      {
        id: 'hist_cross_confirmed',
        label: 'Cruce histograma confirmado',
        shortLabel: 'Cruce confirmado',
        defaultActive: true,
        description: 'El histograma MACD (línea vs su señal EMA9) ya ha cruzado a positivo dentro de las últimas 10 sesiones — sin exigir tendencia. Cuantificado por la trayectoria media de los saltos diarios del histograma, antes y después del cruce, normalizada en ATR14.',
        rulesText: [
          'El histograma MACD (macdHist = línea − señal) está en positivo hoy.',
          'El cruce de negativo a positivo ocurrió dentro de las últimas 10 sesiones — si lleva más tiempo en positivo, no cuenta como candidato "reciente" (queda marcado como "cruce antiguo").',
          'Magnitud: media de los saltos diarios del histograma (hist de hoy − hist de ayer, y así sucesivamente) en la ventana que va desde hasta 10 sesiones antes del cruce hasta hoy — cuantifica la fuerza/limpieza del cruce, no solo si ocurrió. Normalizada por ATR14 para comparar entre tickers de precio y volatilidad distintos.',
          'Sin exigir tendencia (SMA50/SMA200) como parte de este filtro — a propósito: exigirla siempre habría bloqueado un caso real (META, ver CLAUDE.md) donde el histograma ya giraba al alza semanas antes de que el precio recuperase su media de 200 sesiones. Si quieres exigirla, combina este filtro con "Línea MACD cerca de cruzar 0" o con la marca opcional SMA50>SMA200 de abajo.',
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
            tooltip: 'Sesiones transcurridas desde que el histograma cruzó de negativo a positivo. 0 = cruzó hoy mismo. Este filtro solo admite candidatos con cruce dentro de las últimas 10 sesiones.' },
          { header: 'Magnitud (ATR)',    get: (q, r) => r.detail.avgJumpAtr,  format: v => v == null ? '—' : fmtSigned(v, 3, '×'),
            tooltip: 'Trayectoria media de los saltos diarios del histograma (antes y después del cruce), normalizada por ATR14 — cuantifica la fuerza/limpieza del cruce. Criterio de orden de la tabla: mayor magnitud primero.' },
          { header: 'Histograma (20 ses.)', kind: 'histbars', get: q => q.macdHistRecent,
            format: v => Array.isArray(v) ? v.slice(-10).map(x => (x >= 0 ? '+' : '') + x.toFixed(2)).join(' ') : '—',
            tooltip: 'Evolución del histograma MACD en las últimas 20 sesiones (la barra de la derecha es hoy). Verde = por encima de la señal, rojo = por debajo; la altura se escala por ticker, así que sirve para ver la forma y la inclinación, no para comparar magnitudes entre filas. Marcada con un punto la sesión del cruce. En el export a LLM se muestran los últimos 10 valores crudos.' },
          { header: 'RSI14',             get: q => q.rsi,                     format: v => v == null ? '—' : String(v),
            tooltip: 'RSI de 14 sesiones (Wilder) — dato de contexto, no forma parte de la regla de este filtro.' },
        ],
        evaluate: evalMacdHistCrossUp,
      },
      {
        id: 'line_near_zero_up',
        label: 'Línea MACD cerca de cruzar 0',
        shortLabel: 'Cerca de 0',
        defaultActive: false,
        description: 'Tendencia alcista (precio y SMA50 por encima de SMA200) + línea MACD (EMA12−EMA26) todavía en negativo pero subiendo, a ≤1×ATR14 de cruzar a positivo.',
        rulesText: [
          'Tendencia alcista: precio > SMA200 y SMA50 > SMA200 — a diferencia de "Cruce histograma confirmado", este filtro SÍ exige tendencia como parte de su propia regla.',
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
            tooltip: 'Distancia de la línea MACD a cero, en múltiplos de ATR14 — normalizada así porque el valor crudo de MACD no es comparable entre tickers de precio muy distinto. Este filtro exige ≤1.0× para considerar el cruce "cercano".' },
          { header: 'Sesiones est.',   get: (q, r) => r.detail.sessionsEst, format: v => v == null ? '—' : '~' + v,
            tooltip: 'Estimación informativa, no forma parte de la regla: al ritmo medio de las últimas 5 sesiones, cuántas sesiones más tardaría en cruzar cero. Extrapolación lineal simple — puede no cumplirse.' },
          { header: 'Tendencia SMA',   get: (q, r) => r.detail.trendUp,   format: fmtBool,
            tooltip: '✓ si precio > SMA200 y SMA50 > SMA200 (tendencia alcista clásica). A diferencia de "Cruce histograma confirmado", este filtro exige esta condición como parte de su propia regla, no como marca opcional.' },
          { header: 'RSI14',           get: q => q.rsi,                   format: v => v == null ? '—' : String(v),
            tooltip: 'RSI de 14 sesiones (Wilder) — dato de contexto, no forma parte de la regla de este filtro.' },
        ],
        evaluate: evalMacdZeroCrossUp,
      },
    ],
    // Marcas opcionales del lado de la UI (screeners.html): NO alteran
    // evaluate()/pass/sortValue de ningún filtro — son un botón "toggle"
    // que el usuario enciende/apaga para estrechar la vista ya evaluada.
    // Mecanismo genérico del registro, reutilizable por screeners futuros.
    extraFilters: [
      { id: 'sma_trend_up', label: 'Solo con SMA50 > SMA200', predicate: q => smaTrendUp(q) === true,
        tooltip: 'Filtro opcional, no forma parte de la regla de ningún filtro de arriba. Actívalo para ver solo candidatos con la SMA50 por encima de la SMA200 (tendencia de fondo confirmada); apágalo para ver todos, incluidos los que giran al alza antes de que esa media lenta lo confirme (como pasó con META).' },
    ],
  },
];

function getScreener(id) {
  return SCREENERS.find(s => s.id === id) || null;
}

function getFilter(screener, filterId) {
  return (screener && screener.filters || []).find(f => f.id === filterId) || null;
}

// Ids de los filtros marcados defaultActive:true de un screener — estado
// inicial al abrir la página o al cambiar de pestaña de screener.
function defaultActiveFilterIds(screener) {
  return new Set((screener && screener.filters || []).filter(f => f.defaultActive).map(f => f.id));
}

// Evalúa los filtros ACTIVOS (activeFilterIds, un Set de filter.id) de un
// screener sobre {ticker: quoteData}. Un ticker es candidato (pass=true)
// solo si TODOS los filtros activos evalúan pass=true (AND) — así es como
// "se suman" los filtros. Sin ningún filtro activo, pass=false para todos
// (nada que mostrar, en vez de mostrar el universo entero sin criterio).
// Devuelve { ticker, q, pass, results, sortValue } por fila — `results` es
// {filterId: {status,pass,sortValue,detail}}, una entrada por filtro activo.
function runScreenerFilters(screener, activeFilterIds, quotesByTicker) {
  const active = (screener.filters || []).filter(f => activeFilterIds.has(f.id));
  return Object.entries(quotesByTicker || {}).map(([ticker, q]) => {
    const results = {};
    let pass = active.length > 0;
    let sortValue = null;
    active.forEach(f => {
      const r = f.evaluate(q);
      results[f.id] = r;
      if (!r.pass) pass = false;
      if (sortValue == null && r.sortValue != null) sortValue = r.sortValue;
    });
    return { ticker, q, pass, results, sortValue };
  });
}

// Export CommonJS opcional — permite require() desde un script Node
// standalone sin romper el uso como <script> plano en el navegador (donde
// `module` no existe), mismo patrón que shared/flow-score.js.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    SCREENERS, getScreener, getFilter, defaultActiveFilterIds, runScreenerFilters,
    evalMacdHistCrossUp, evalMacdZeroCrossUp, smaTrendUp,
    evalFlowInflexion, evalFlowContinuacion, evalFlowReversion,
  };
}
