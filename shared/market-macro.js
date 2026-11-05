// ── Market Tracker — macro reading + uranium regime score ────────────────
// Extracted 2026-09-13 so scripts/market_daily_snapshot.js (daily capture in
// the pipeline, independent of whether index.html is open) can classify
// macro readings and the uranium regime score with the exact same logic the
// dashboard shows — mismo motivo que ya llevó computeFlowScore/
// computeEarlyFlowScore a shared/flow-score.js: sin esto, cualquier
// recálculo en el script correría el riesgo de divergir silenciosamente de
// lo que ve el usuario (ver el incidente ya documentado de calcCMF
// duplicado y desincronizado en CLAUDE.md).
//
// Loaded by index.html via <script src="/shared/market-macro.js"> (before
// the page's own Babel script) and required directly from Node scripts.

// ── HY spread: escala única del proyecto (2026-11-06) ────────────────────
// Antes había 7 criterios distintos para el mismo dato (ver CLAUDE.md, «HY —
// concordancia entre módulos»). Esta pestaña llamaba «Normal» a 300-400 pb y
// el MacroScore (rotacion.html + backtest/src/macro/components.py) a 300-375:
// el nivel usa ahora los cortes del MacroScore (probados en backtest), no se
// toca el MacroScore. Además se añade la DIRECCIÓN con los umbrales de Cava
// (scripts/cava_mapping.py, calibrados sobre 2024-2026: ±20 pb en 4 semanas
// fuera del rango intercuartílico, +75 pb = ruptura). Sin dirección, la
// lectura dijo «Normal» seis semanas mientras el spread subía de 270 a 340 pb.
// Aquí se usa la variación a 1 mes (dM) que ya calcula la página, ≈ 4 semanas.
const HY_LEVEL_BPS = { compressed: 300, normal: 375, elevated: 475, high: 600 };
const HY_MOVE_BPS  = { significant: 20, breaking: 75 };

function hyReading(v, dW, dM) {
  if (v == null) return null;
  const b = v * 100;
  const lvl = b < HY_LEVEL_BPS.compressed ? ['Comprimido', 0]
            : b < HY_LEVEL_BPS.normal     ? ['Normal', 1]
            : b < HY_LEVEL_BPS.elevated   ? ['Elevado', 2]
            : b < HY_LEVEL_BPS.high       ? ['Alto', 3]
            :                               ['Crisis de crédito', 4];
  const mBps = dM != null ? dM * 100 : null;
  const dir = mBps == null ? null
            : mBps >= HY_MOVE_BPS.breaking     ? 'ruptura'
            : mBps >= HY_MOVE_BPS.significant  ? 'ampliándose'
            : mBps <= -HY_MOVE_BPS.significant ? 'estrechándose'
            : null;
  const label = dir ? `${lvl[0]} · ${dir} (${mBps > 0 ? '+' : ''}${Math.round(mBps)} pb 1M)` : lvl[0];
  // Color: por nivel; ampliarse sube un escalón el aviso visual (que no
  // vuelva a quedarse en gris mientras el crédito se deteriora).
  const sev = Math.min(4, lvl[1] + (dir === 'ruptura' ? 2 : dir === 'ampliándose' ? 1 : 0));
  const COLORS = [['#c8e6c9','#1b5e20'], ['#f0f0f0','#555'], ['#fff9c4','#e65100'], ['#ffe0b2','#bf360c'], ['#ffcdd2','#b71c1c']];
  return [label, COLORS[sev][0], COLORS[sev][1]];
}

const STATUS = {
  vix:        v => v<15?['Complacencia','#c8e6c9','#1b5e20']:v<20?['Calma','#dcedc8','#33691e']:v<25?['Cautela','#fff9c4','#e65100']:v<35?['Estrés','#ffe0b2','#bf360c']:['Pánico','#ffcdd2','#b71c1c'],
  hy_spread:  hyReading,
  ig_spread:  v => { const b=v*100; return b<80?['Muy comprimido','#c8e6c9','#1b5e20']:b<130?['Normal','#f0f0f0','#555']:b<200?['Stress leve','#ffe0b2','#bf360c']:['Stress elevado','#ffcdd2','#b71c1c']; },
  curve_pct:  v => v>1?['Empinada – expansión','#c8e6c9','#1b5e20']:v>0?['Normal','#f0f0f0','#555']:v>-0.5?['Aplanada','#fff9c4','#e65100']:v>-1?['Invertida – ciclo tardío','#ffe0b2','#bf360c']:['Invertida – riesgo recesión','#ffcdd2','#b71c1c'],
  pmi:        v => v>103?['Expansión fuerte','#c8e6c9','#1b5e20']:v>100?['Expansión','#dcedc8','#33691e']:v>=98?['Contracción leve','#fff9c4','#e65100']:['Contracción','#ffcdd2','#b71c1c'],
  breakeven:  v => v<2?['Riesgo deflación','#e3f2fd','#1565c0']:v<2.5?['Inflación controlada','#c8e6c9','#1b5e20']:v<3?['Inflación elevada','#ffe0b2','#bf360c']:['Riesgo stagflación','#ffcdd2','#b71c1c'],
  net_liq:    v => v>7e6?['Liquidez abundante','#c8e6c9','#1b5e20']:v>5.5e6?['Liquidez normal','#f0f0f0','#555']:v>4e6?['Liquidez ajustada','#ffe0b2','#bf360c']:['Liquidez restringida','#ffcdd2','#b71c1c'],
  yield_10y:      v => v<3.0?['Tipos largos bajos','#e3f2fd','#1565c0']:v<4.0?['Tipos largos normales','#f0f0f0','#555']:v<4.75?['Tipos largos restrictivos','#fff9c4','#e65100']:['Estrés por tipos largos','#ffe0b2','#bf360c'],
  real_yield_10y: v => v<0?['Tipos reales acomodaticios','#c8e6c9','#1b5e20']:v<1.0?['Tipos reales neutros','#f0f0f0','#555']:v<2.0?['Tipos reales restrictivos','#fff9c4','#e65100']:['Tipos reales muy restrictivos','#ffe0b2','#bf360c'],
  short_rate: v => v<2.5?['Política acomodaticia','#e3f2fd','#1565c0']:v<3.5?['Política neutral','#f0f0f0','#555']:v<4.75?['Política restrictiva','#fff9c4','#e65100']:['Política muy restrictiva','#ffe0b2','#bf360c'],
  dxy: (v, dW, dM) => {
    if (v == null) return null;
    if (v >= 106) return dM > 0 ? ['Dólar muy fuerte y subiendo','#ffcdd2','#b71c1c'] : ['Dólar muy fuerte, moderando','#fff9c4','#e65100'];
    if (v >= 100) return dM > 1 ? ['Dólar fuerte y subiendo','#fff9c4','#e65100']    : ['Dólar fuerte','#fff3e0','#e65100'];
    if (v >=  95) return ['Dólar neutral','#f0f0f0','#555'];
    return ['Dólar débil','#c8e6c9','#1b5e20'];
  },
  m2: (v, dW, dM, dY) => {
    if (v == null || dY == null) return null;
    const prev = v - dY; if (!prev) return null;
    const yoy = (dY / prev) * 100;
    return yoy > 6  ? ['Expansión M2 fuerte','#c8e6c9','#1b5e20']
         : yoy > 2  ? ['Expansión M2 moderada','#dcedc8','#33691e']
         : yoy > -2 ? ['M2 estable','#f0f0f0','#555']
         : yoy > -6 ? ['Contracción M2','#fff9c4','#e65100']
                    : ['Contracción M2 severa','#ffcdd2','#b71c1c'];
  },
  fed_bs: (v, dW, dM, dY) => {
    if (v == null || dY == null) return null;
    const prev = v - dY; if (!prev) return null;
    const yoy = (dY / prev) * 100;
    return yoy > 3  ? ['Balance Fed expandiéndose','#c8e6c9','#1b5e20']
         : yoy > -3 ? ['Balance Fed estable','#f0f0f0','#555']
         : yoy > -8 ? ['Balance Fed contrayéndose','#fff9c4','#e65100']
                    : ['Contracción fuerte del balance','#ffe0b2','#bf360c'];
  },
};

function computeUraniumScore(rows) {
  const urnm = rows['URNM'], uuto = rows['U-U.TO'], ccj = rows['CCJ'];
  let score = 0, pts = [];
  if (urnm?.ytd  > 0)        { score++; pts.push('URNM YTD+'); }
  if (uuto?.ytd  > 0)        { score++; pts.push('U-U.TO YTD+'); }
  if (ccj?.ytd   > 0)        { score++; pts.push('CCJ YTD+'); }
  if (urnm && urnm.fromHigh != null && urnm.fromHigh >= -10) { score++; pts.push('URNM ≤10% de máx'); }
  if (uuto && uuto.fromHigh != null && uuto.fromHigh >= -10) { score++; pts.push('U-U.TO ≤10% de máx'); }
  const label = score <= 1 ? 'Débil (0–1)' : score <= 3 ? 'Neutral / Acumulación (2–3)' : 'Bull claro (4–5)';
  const bg    = score <= 1 ? '#ffcdd2' : score <= 3 ? '#fff9c4' : '#c8e6c9';
  const fg    = score <= 1 ? '#b71c1c' : score <= 3 ? '#e65100' : '#1b5e20';
  return { score, label, bg, fg, pts };
}

// Export CommonJS opcional — mismo patrón que shared/flow-score.js.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { STATUS, computeUraniumScore, HY_LEVEL_BPS, HY_MOVE_BPS };
}
