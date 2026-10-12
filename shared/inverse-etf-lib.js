// ── ETFs inversos/apalancados: clasificación de estado (venta de prima) ──────
// Fuente única para inversos.html (navegador) y scripts/inverse_etf_alert.js
// (Node) — mismo patrón dual que shared/flow-score.js. Solo observación: no es
// señal de compra/venta. Umbrales de PRIMERA PASADA, sin calibrar.
//
// Idea (tuit de reversión del VIX con UVXY): el ETF con decay estructural se
// dispara por un pánico del subyacente; cuando éste empieza a enfriarse, la
// prima de las opciones está cara y el decay juega a favor del vendedor.
//
// `sign`: +1 si el ETF sube cuando sube el subyacente (UVXY↔VIX, BOIL↔gas),
// -1 si sube cuando el subyacente baja (SQQQ↔QQQ, GLL↔oro). "Enfriándose" =
// el subyacente se mueve en contra del ETF más de `coolW1` % en la semana.

const INVERSE_ETFS = [
  {
    ticker: 'UVXY', name: 'ProShares Ultra VIX Short-Term Futures (1,5x)',
    under: '^VIX', sign: +1, coolW1: null, minLevel: 25, color: '#6a1b9a',
    // Regla calibrada con research/uvxy_spike_fade_v1 (5 años, 2026-10-12): el
    // nivel del VIX es lo que discrimina; exigir UVXY "extendido" no aportaba
    // (misma regla con 1,0 a 2,5 ATR) y el -10% semanal del VIX dejaba n=2.
    // spike = VIX >= minLevel; fading = además UVXY gira a la baja (1D<0 y
    // Δhist MACD<0). Con ese criterio (VIX>=25 + giro): 20 eventos, UVXY baja el
    // 95-100% a 42-63 sesiones; entrando tras el giro de 12 picos reales, mediana
    // -17% a 21s y -28% a 63s, pero P(subida>=30%) = 17% a 21s y 27% a 63s.
    rule: 'vix_level',
    strategy: {
      title: 'Estructura acordada (UVXY)',
      lines: [
        'Put (o put spread) a 2-3 meses: es la pieza que aprovecha el decay; riesgo limitado a la prima.',
        'Call: vender call spread (con ala comprada lejos) o una call a ~30 días que se va rodando. Evitar la call naked a 3 meses: la probabilidad de tocar +30% sube de 17% (21 sesiones) a 27% (63 sesiones) en los picos de referencia.',
        'Antes de operar: comparar IV a 1 mes vs 3 meses (en spike la curva suele estar invertida, la put a 3 meses sale más barata por unidad) y el carry implícito de la cadena (el decay puede estar ya en el precio vía coste de préstamo).',
        'Comprobar el margen real en IBKR (simulación de orden) y que no haya reverse split anunciado.',
      ],
    },
    decay: 'Contango al rotar futuros del VIX + apalancamiento diario. El decay es el más fuerte del grupo.',
    notes: [
      'El VIX spot debe estar alto (≥25) para que haya algo que desvanecer; con VIX bajo el decay no compensa el riesgo de spike.',
      'Riesgo de cola: gaps de +50-100% en un día (feb-2018, ago-2024, abr-2025). Una call vendida naked puede perder varias veces el capital.',
      'Reverse splits frecuentes: los strikes se reajustan, revisa la cadena antes de operar.',
    ],
  },
  {
    ticker: 'SQQQ', name: 'ProShares UltraPro Short QQQ (-3x)',
    under: 'QQQ', sign: -1, coolW1: 2.5, color: '#1565c0',
    decay: 'Solo volatility drag del reapalancamiento diario (sin contango). Mucho más lento que UVXY y grande en mercados laterales/volátiles.',
    notes: [
      'Se dispara cuando el Nasdaq cae; el aviso exige que QQQ ya esté recuperando.',
      'En un crash sostenido SQQQ puede seguir subiendo semanas: el decay no protege al vendedor de la tendencia.',
      'Opciones líquidas (suele haber vencimientos semanales).',
    ],
  },
  {
    ticker: 'GLL', name: 'ProShares UltraShort Gold (-2x)',
    under: 'GLD', sign: -1, coolW1: 2, color: '#b8860b',
    decay: 'Volatility drag del -2x diario sobre el oro (sin contango). Decay moderado.',
    notes: [
      'Se dispara cuando el oro cae; el aviso exige que el oro (GLD) ya esté recuperando.',
      'Cadena de opciones fina: pocos vencimientos y spreads amplios; el spread bid-ask puede comerse el edge.',
    ],
  },
  {
    ticker: 'BOIL', name: 'ProShares Ultra Bloomberg Natural Gas (2x)',
    under: 'NG=F', sign: +1, coolW1: 8, color: '#37474f',
    decay: 'Contango fuerte del gas natural al rotar futuros + apalancamiento 2x. Decay alto y volatilidad extrema.',
    notes: [
      'El gas tiene picos estacionales y de clima muy bruscos; los movimientos de 20-30% en pocos días son normales.',
      'Cadena de opciones a menudo fina: revisa spreads y open interest antes de nada.',
    ],
  },
];

const INV_EXT_ATR = 1.5;   // distancia a SMA20 en ATR14
const INV_EXT_M1 = 25;     // o subida de 1 mes en %

// Distancia del precio a su SMA20 en ATR14. /api/quote no siempre trae
// distance_to_sma20_atr (p. ej. SQQQ/GLL/BOIL), así que se recalcula con
// sma20 y atrAbs, que sí vienen.
function invDistAtr(q) {
  if (!q) return null;
  if (q.distance_to_sma20_atr != null) return q.distance_to_sma20_atr;
  if (q.price != null && q.sma20 != null && q.atrAbs) return +((q.price - q.sma20) / q.atrAbs).toFixed(2);
  return null;
}

function invGetEtf(ticker) {
  return INVERSE_ETFS.find(e => e.ticker === ticker) || null;
}

// q = quote del ETF, u = quote del subyacente (o null).
// Devuelve { state, extended, rolling, cooling, levelOk, missing[] }.
//   fading : extendido + girando + subyacente enfriándose → ventana de venta de prima
//   spike  : extendido, pero aún no gira o el subyacente no cede → vigilar, no vender aún
//   calm   : sin spike → sin setup
//   no_data: faltan datos para decidir
function classifyInverseEtf(etf, q, u) {
  const missing = [];
  if (!q || q.error) return { state: 'no_data', extended: null, rolling: null, cooling: null, levelOk: null, checks: [], missing: ['quote ETF'] };
  const rolling0 = (q.d1 != null && q.macdHistDelta1 != null) ? (q.d1 < 0 && q.macdHistDelta1 < 0) : null;

  // UVXY: regla por nivel del VIX (calibrada). spike = VIX alto; fading = VIX alto + UVXY girando.
  if (etf.rule === 'vix_level') {
    const vixOk = (u && !u.error && u.price != null) ? u.price >= etf.minLevel : null;
    const checks = [
      { label: `${etf.under} ≥ ${etf.minLevel}`, v: vixOk },
      { label: `${etf.ticker} girando a la baja`, v: rolling0 },
    ];
    let state;
    if (vixOk == null) state = 'no_data';
    else if (!vixOk) state = 'calm';
    else if (rolling0) state = 'fading';
    else state = 'spike';
    return { state, extended: vixOk, rolling: rolling0, cooling: null, levelOk: vixOk, checks,
             missing: vixOk == null ? ['subyacente'] : [] };
  }

  const dist = invDistAtr(q);
  const extended = (dist != null || q.m1 != null)
    ? ((dist != null && dist >= INV_EXT_ATR) || (q.m1 != null && q.m1 >= INV_EXT_M1))
    : null;
  if (extended == null) missing.push('extensión');
  const rolling = (q.d1 != null && q.macdHistDelta1 != null) ? (q.d1 < 0 && q.macdHistDelta1 < 0) : null;
  if (rolling == null) missing.push('giro');
  let cooling = null, levelOk = null;
  if (u && !u.error && u.w1 != null) {
    cooling = etf.sign * u.w1 <= -etf.coolW1;
    levelOk = etf.minLevel == null || (u.price != null && u.price >= etf.minLevel);
  } else missing.push('subyacente');

  let state;
  if (extended == null) state = 'no_data';
  else if (!extended) state = 'calm';
  else if (rolling && cooling && levelOk) state = 'fading';
  else state = 'spike';
  const checks = [
    { label: 'Extendido', v: extended },
    { label: 'Girando a la baja', v: rolling },
    { label: 'Subyacente enfría', v: cooling },
  ];
  if (etf.minLevel != null) checks.push({ label: `${etf.under} ≥ ${etf.minLevel}`, v: levelOk });
  return { state, extended, rolling, cooling, levelOk, checks, missing };
}

const INV_STATE_META = {
  fading:  { label: 'Ventana de venta de prima', short: 'VENTANA', rank: 2, badge: 'green',
             desc: 'Se cumplen las condiciones de venta de prima (ver las marcas de la tarjeta). Revisa IV por plazo, skew y spreads de la cadena antes de operar.' },
  spike:   { label: 'Spike en curso',            short: 'SPIKE',   rank: 1, badge: 'orange',
             desc: 'Condición de spike activa, pero aún no se cumple el giro. Vigilar; vender prima ahora es ir contra el movimiento.' },
  calm:    { label: 'Sin spike',                 short: 'CALMA',   rank: 0, badge: 'neutral',
             desc: 'Sin spike activo. Sin setup: la prima suele estar barata y el riesgo de spike no está pagado.' },
  no_data: { label: 'Sin datos',                 short: 'S/D',     rank: -1, badge: 'neutral',
             desc: 'Faltan datos para clasificar.' },
};

// Lectura de opciones desde la última fila de inverse_etf_options_summary.jsonl
// del ticker (puede no existir aún). Usa el primer vencimiento con >=14 DTE.
// Umbrales de primera pasada: IV/RV >= 1,2 = prima rica; spread > 15% = ilíquido.
function summarizeOptions(summaryRow) {
  if (!summaryRow || !Array.isArray(summaryRow.expiries)) return null;
  const e = summaryRow.expiries.find(x => x.dte >= 14 && x.atm_iv != null) || summaryRow.expiries.find(x => x.atm_iv != null);
  if (!e) return null;
  const ivRv = summaryRow.rv20 ? e.atm_iv / summaryRow.rv20 : null;
  return {
    date: summaryRow.date, expiry: e.expiry, dte: e.dte, atmIv: e.atm_iv, rv20: summaryRow.rv20, rv60: summaryRow.rv60,
    ivRv, skew: e.call_put_skew, spread: e.rel_spread_near_atm, oiCalls: e.oi_calls, oiPuts: e.oi_puts,
    rich: ivRv != null ? ivRv >= 1.2 : null,
    illiquid: e.rel_spread_near_atm != null ? e.rel_spread_near_atm > 0.15 : null,
    term: termStructure(summaryRow.expiries),
  };
}

// Estructura de plazos para la jugada acordada: put a 2-3 meses (~90 DTE) y
// call corta (~30 DTE). Elige el vencimiento más cercano a cada plazo (con
// tolerancia) y devuelve IV ATM de cada uno, ratio 3m/1m (<1 = curva invertida:
// la put a 3 meses sale más barata por unidad de vol que la de 1 mes), IV de la
// put al 80% del spot a ~90 DTE y de la call al 120% a ~30 DTE.
function termStructure(expiries) {
  const pick = (target, tol) => {
    const c = expiries.filter(x => x.atm_iv != null && Math.abs(x.dte - target) <= tol);
    return c.length ? c.reduce((a, b) => Math.abs(b.dte - target) < Math.abs(a.dte - target) ? b : a) : null;
  };
  const f = pick(30, 15), l = pick(90, 30);
  if (!f && !l) return null;
  return {
    front: f ? { expiry: f.expiry, dte: f.dte, atmIv: f.atm_iv, ivCall120: f.iv_call_120 } : null,
    long: l ? { expiry: l.expiry, dte: l.dte, atmIv: l.atm_iv, ivPut80: l.iv_put_80 } : null,
    ratio: (f && l) ? +(l.atm_iv / f.atm_iv).toFixed(2) : null,
    inverted: (f && l) ? l.atm_iv < f.atm_iv : null,
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { invDistAtr, INVERSE_ETFS, INV_STATE_META, invGetEtf, classifyInverseEtf, summarizeOptions };
}
