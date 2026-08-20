// ── Flow Score / Early Flow Detector — shared calculation logic ────────────
// Loaded by both index.html (Market Tracker) and portfolio.html (Portfolio
// Tracker) via <script src="/shared/flow-score.js">. Keep this file the
// single source of truth: it was previously duplicated in both pages and
// diverged (index.html kept the old single-timeframe konSignal scheme after
// koncorde_calculator.py moved the API to konc_d/3d/w_state).
// Presentation (colors, badges) stays local to each page — only the scoring
// math and state-label lookup live here.

function koncStateLbl(s) {
  return ({ accumulation: 'Acumul.', up: 'Alza', distribution: 'Distrib.', down: 'Baja' })[s] ?? '—';
}

// ── Flow Score ───────────────────────────────────────────────────────────
function computeFlowScore(d) {
  if (!d) return null;
  // Momentum: w1 * 0.6 + m1 * 0.4
  const m = ((d.w1 ?? 0) * 0.6) + ((d.m1 ?? 0) * 0.4);
  // RSI + MACD
  let r = 0;
  if (d.rsi != null) { if (d.rsi > 65) r += 2; else if (d.rsi > 55) r += 1; }
  if (d.macdBull === true) r += 1; else if (d.macdBull === false) r -= 1;
  // ATR
  const atr = d.atrPct ?? 0;
  const a = (atr >= 1 && atr <= 3) ? 1 : (atr > 3 && atr <= 6) ? 0.5 : atr > 6 ? -0.5 : 0;
  // Koncorde (D confirms, W confirms or dampens up to ±1)
  const kmap = { up: 2, accumulation: 1, distribution: -1, down: -2 };
  const kD = kmap[d.konc_d_state] ?? 0;
  const kW = kmap[d.konc_w_state] ?? 0;
  const k  = kD + (kW * 0.5);
  // Trend (from 52W high)
  const fh = d.fromHigh ?? 0;
  const t = (fh >= -10 && fh <= 0) ? 1 : (fh >= -25 && fh < -10) ? 0 : -1;
  return Math.round(((m * 2) + r + a + k + t) * 100) / 100;
}
function classifyFlow(score) {
  if (score == null) return null;
  if (score >= 8) return 'Lider';
  if (score >= 4) return 'Transicion';
  return 'Debil';
}

// ── Early Flow Detector ───────────────────────────────────────────────────
function computeEarlyFlowScore(d, prev) {
  if (!d) return null;
  let score = 0;

  // A) Giro Koncorde D (requiere histórico)
  if (prev?.konc_d_state && d.konc_d_state) {
    const pk = prev.konc_d_state, ck = d.konc_d_state;
    if      (pk === 'down'         && ck === 'accumulation') score += 3;
    else if (pk === 'distribution' && ck === 'accumulation') score += 2;
    else if (pk === 'accumulation' && ck === 'up')           score += 1;
    else if (ck === 'down' || ck === 'distribution')         score -= 1;
  } else if (d.konc_d_state === 'down' || d.konc_d_state === 'distribution') {
    score -= 1;
  }

  // A2) Alineación multi-TF: 3D y W confirman o amortiguan la señal diaria
  const bullK = s => s === 'up' || s === 'accumulation';
  const bearK = s => s === 'down' || s === 'distribution';
  const ck   = d.konc_d_state;
  const ck3d = d.konc_3d_state;
  const ckw  = d.konc_w_state;
  if (ck && bullK(ck)) {
    if (ck3d && bullK(ck3d)) score += 1;   // 3D alineado: confirmación media
    if (ckw  && bullK(ckw))  score += 1;   // W alineado: confirmación fuerte
    if (ckw  && bearK(ckw))  score -= 1;   // W en contra: señal D menos fiable
  } else if (ck && bearK(ck)) {
    if (ck3d && bearK(ck3d)) score -= 1;   // 3D también débil
    if (ckw  && bearK(ckw))  score -= 1;   // W también débil
  }
  // Giro en 3D (señal intermedia)
  if (prev?.konc_3d_state && ck3d && prev.konc_3d_state === 'down' && ck3d === 'accumulation') score += 1;

  // B) Compresión de volatilidad (requiere histórico)
  if (prev?.atrPct != null && d.atrPct != null && prev.atrPct > 0) {
    const r = d.atrPct / prev.atrPct;
    if (r < 0.9) score += 2;
    else if (r < 1.0) score += 1;
    else if (r > 1.2) score -= 1;
  }

  // C) Posición respecto al máximo 52W
  const fh = d.fromHigh ?? 0;
  if      (fh >= -15 && fh <= -5)  score += 2;
  else if (fh >= -25 && fh < -15)  score += 1;
  else if (fh < -30)               score -= 1;

  // D) RSI en zona de recuperación
  const rsi = d.rsi;
  if (rsi != null) {
    if      (rsi >= 45 && rsi <= 58) score += 2;
    else if (rsi >= 40 && rsi < 45)  score += 1;
    else if (rsi < 35)               score -= 1;
  }

  // E) Momentum todavía modesto
  const w1 = d.w1 ?? 0, m1 = d.m1 ?? 0;
  if      (w1 >= 0 && w1 <= 4 && m1 >= -5  && m1 <= 5)  score += 2;
  else if (w1 >= 0 && w1 <= 6 && m1 >= -8  && m1 <= 8)  score += 1;
  else if (w1 > 8 || m1 > 10)                            score += 0.5;
  else if (w1 < -5 && m1 < -8)                           score -= 1;

  return Math.round(score * 100) / 100;
}
function classifyEarlyFlow(score) {
  if (score == null) return null;
  if (score >= 7) return 'Fuerte';
  if (score >= 4) return 'Interesante';
  return 'Sin setup';
}

function matrixReading(early, flow) {
  if (early >= 7 && flow >= 8)  return 'Activación potente — setup + flujo confirmado';
  if (early >= 7 && flow >= 4)  return 'Setup activo — breakout en marcha';
  if (early >= 7)               return 'Setup temprano — vigilar / comprar parcial';
  if (early >= 4 && flow >= 8)  return 'Transición a tendencia madura';
  if (early < 4  && flow >= 8)  return 'Tendencia madura — llegas tarde';
  return null;
}

// Export CommonJS opcional — permite `require()` desde scripts Node
// standalone (ej. scripts/portfolio_daily_snapshot.js) sin romper el uso
// como <script> plano en el navegador, donde `module` no existe.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    koncStateLbl, computeFlowScore, classifyFlow,
    computeEarlyFlowScore, classifyEarlyFlow, matrixReading,
  };
}
