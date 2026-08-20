// ── Quote building — shared calculation + fetch logic ──────────────────────
// Extraído de server.js (2026-08-20) para que /api/quote/:symbol y el
// script standalone scripts/portfolio_daily_snapshot.js llamen exactamente
// a la misma función buildQuoteData() — evita que la lógica de indicadores
// pueda desincronizarse entre el endpoint HTTP y la captura diaria en el
// pipeline (mismo criterio que llevó a centralizar HARD_RULES/
// compact_candidate en scripts/ai_shared.py). CommonJS puro, sin
// dependencia de Express — requerible tanto desde server.js como desde un
// script Node standalone sin arrancar ningún servidor.
const path  = require("path");
const fs    = require("fs");
const fetch = require("node-fetch");

const REPO_ROOT = path.join(__dirname, "..");

// ── RSI (Wilder) ─────────────────────────────────────────────────────────
function calcRSI(closes, period = 14) {
  const c = closes.filter(x => x != null);
  if (c.length < period + 1) return null;
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const d = c[i] - c[i - 1];
    if (d > 0) avgGain += d / period; else avgLoss += -d / period;
  }
  for (let i = period + 1; i < c.length; i++) {
    const d = c[i] - c[i - 1];
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
  }
  if (avgLoss === 0) return 100;
  return Math.round(100 - 100 / (1 + avgGain / avgLoss));
}

// ── Koncorde Plus (OskarGallard, MPL 2.0) — pre-computed by Python ───────
// Pre-computed by scripts/koncorde_calculator.py (Step 9b in the pipeline).
// Cache refreshes every 10 minutes so the display stays current without
// restarting the server between pipeline runs.
let _konccordeCache = null;
let _koncordeCacheTs = 0;
function getKoncordeData() {
  if (Date.now() - _koncordeCacheTs < 10 * 60 * 1000 && _konccordeCache) {
    return _konccordeCache;
  }
  const p = path.join(REPO_ROOT, "docs", "data", "koncorde_data.json");
  try {
    if (fs.existsSync(p)) {
      const data = JSON.parse(fs.readFileSync(p, "utf8"));
      _konccordeCache = data.tickers || {};
      _koncordeCacheTs = Date.now();
      return _konccordeCache;
    }
  } catch (e) {
    console.warn("koncorde_data.json read error:", e.message);
  }
  return {};
}

// ── Insider Activity (Form4API) — pre-computed by Python ────────────────
// Pre-computed by scripts/update_insider_activity.py (morning-only step in
// the pipeline). Same 10-min cache pattern as getKoncordeData() above.
let _insiderActivityCache = null;
let _insiderActivityCacheTs = 0;
function getInsiderActivityData() {
  if (Date.now() - _insiderActivityCacheTs < 10 * 60 * 1000 && _insiderActivityCache) {
    return _insiderActivityCache;
  }
  const p = path.join(REPO_ROOT, "docs", "data", "insider_activity_snapshot.json");
  try {
    if (fs.existsSync(p)) {
      const data = JSON.parse(fs.readFileSync(p, "utf8"));
      _insiderActivityCache = data.tickers || {};
      _insiderActivityCacheTs = Date.now();
      return _insiderActivityCache;
    }
  } catch (e) {
    console.warn("insider_activity_snapshot.json read error:", e.message);
  }
  return {};
}

// ── MACD (12, 26, 9) ─────────────────────────────────────────────────────
function calcMACD(closes) {
  const c = closes.filter(x => x != null);
  if (c.length < 35) return { macdHist: null, macdBull: null };

  // EMA series usando SMA como semilla
  const emaFull = (data, period) => {
    const k = 2 / (period + 1);
    let e = data.slice(0, period).reduce((a, b) => a + b, 0) / period;
    const arr = [e];
    for (let i = period; i < data.length; i++) { e = data[i] * k + e * (1 - k); arr.push(e); }
    return arr;
  };

  const ema12 = emaFull(c, 12); // arr[0] = EMA en c[11]
  const ema26 = emaFull(c, 26); // arr[0] = EMA en c[25]
  // ema12[14] y ema26[0] corresponden ambos a c[25]
  const macdLine = ema26.map((v, i) => ema12[i + 14] - v);
  if (macdLine.length < 9) return { macdHist: null, macdBull: null };

  // Señal: EMA(9) del MACD line
  const k9 = 2 / 10;
  let signal = macdLine.slice(0, 9).reduce((a, b) => a + b, 0) / 9;
  for (let i = 9; i < macdLine.length; i++) signal = macdLine[i] * k9 + signal * (1 - k9);

  const hist = macdLine[macdLine.length - 1] - signal;
  return { macdHist: +hist.toPrecision(4), macdBull: hist >= 0 };
}

// ── ATLAS Mini (Blai5) — estrechamiento significativo de Bollinger Bands ──
// Fórmula pública (ProRealCode "Blai5 ATLAS Mini"), verbatim:
//   dbb    = sqrt((BBupper20 - BBlower20) / BBupper20) * 20
//   dbbmed = EMA(dbb, 120)
//   factor = dbbmed * 4/5
//   atl    = dbb - factor
//   señal  = atl <= 0   (compresión relevante — no da dirección, solo avisa
//                        de que puede venir un movimiento brusco)
// No es alcista/bajista por sí solo — se combina visualmente con MACD (a su
// izquierda en la tabla) para dirección.
function calcAtlasMini(closes, period = 20, medLen = 120) {
  const c = closes.filter(x => x != null);
  if (c.length < period + medLen) return { atlasSignal: null, atlasDbb: null, atlasAtl: null };

  // Bollinger(20, mult=2) rolling sobre toda la serie -> un dbb por barra.
  const dbb = [];
  for (let i = period - 1; i < c.length; i++) {
    const win  = c.slice(i - period + 1, i + 1);
    const mean = win.reduce((a, b) => a + b, 0) / period;
    const variance = win.reduce((a, b) => a + (b - mean) ** 2, 0) / period; // población, no muestral
    const std   = Math.sqrt(variance);
    const upper = mean + 2 * std, lower = mean - 2 * std;
    dbb.push(upper > 0 ? Math.sqrt((upper - lower) / upper) * 20 : null);
  }
  const dbbClean = dbb.filter(x => x != null);
  if (dbbClean.length < medLen) return { atlasSignal: null, atlasDbb: null, atlasAtl: null };

  // EMA(120) de dbb, semilla = SMA de los primeros 120 valores.
  const k = 2 / (medLen + 1);
  let e = dbbClean.slice(0, medLen).reduce((a, b) => a + b, 0) / medLen;
  for (let i = medLen; i < dbbClean.length; i++) e = dbbClean[i] * k + e * (1 - k);
  const dbbmed = e;

  const factor  = dbbmed * 4 / 5;
  const lastDbb = dbbClean[dbbClean.length - 1];
  const atl     = lastDbb - factor;

  return {
    atlasSignal: atl <= 0,
    atlasDbb:    +lastDbb.toFixed(2),
    atlasFactor: +factor.toFixed(2),
    atlasAtl:    +atl.toFixed(2),
  };
}

// ── ATR normalizado (ATR14 / precio × 100) ───────────────────────────────
function calcATR(closes, highs, lows, period = 14) {
  const n = closes.length;
  if (n < period + 1) return { atrPct: null, atrAbs: null };

  const trs = [];
  for (let i = 1; i < n; i++) {
    const h = highs[i], l = lows[i], pc = closes[i - 1];
    if (h == null || l == null || pc == null) continue;
    trs.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
  }
  if (trs.length < period) return { atrPct: null, atrAbs: null };

  let atr = trs.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < trs.length; i++) atr = (atr * (period - 1) + trs[i]) / period;

  const price = closes[n - 1];
  return price
    ? { atrPct: +((atr / price * 100).toFixed(1)), atrAbs: +atr.toPrecision(5) }
    : { atrPct: null, atrAbs: null };
}

// ── SMA simple ────────────────────────────────────────────────────────────
function calcSMA(arr, period) {
  const clean = arr.filter(x => x != null);
  if (clean.length < period) return null;
  const slice = clean.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

// ── CMF(20) — Chaikin Money Flow ─────────────────────────────────────────
// MFM = ((Close-Low)-(High-Close)) / (High-Low), 0 if High==Low
// MFV = MFM * Volume ; CMF(20) = sum(MFV, 20) / sum(Volume, 20)
function calcCMF(closes, highs, lows, volumes, period = 20) {
  const n = closes.length;
  if (n < period) return null;
  let mfvSum = 0, volSum = 0;
  for (let i = n - period; i < n; i++) {
    const h = highs[i], l = lows[i], c = closes[i], v = volumes[i] ?? 0;
    if (h == null || l == null || c == null) continue;
    const hl  = h - l;
    const mfm = hl !== 0 ? ((c - l) - (h - c)) / hl : 0;
    mfvSum += mfm * v;
    volSum += v;
  }
  return volSum !== 0 ? +(mfvSum / volSum).toFixed(4) : 0;
}

// ── OBV + SMA50(OBV) ──────────────────────────────────────────────────────
function calcOBV(closes, volumes) {
  let obv = 0;
  const obvArr = [];
  for (let i = 0; i < closes.length; i++) {
    if (i > 0 && closes[i] != null && closes[i - 1] != null) {
      const v = volumes[i] ?? 0;
      if (closes[i] > closes[i - 1])      obv += v;
      else if (closes[i] < closes[i - 1]) obv -= v;
    }
    obvArr.push(obv);
  }
  const obvSma50 = calcSMA(obvArr, 50);
  return { obv, obvAboveSma50: obvSma50 != null ? obv > obvSma50 : null };
}

// ── Yahoo Finance proxy ──────────────────────────────────────────────────
async function fetchYahooChartRaw(symbol, range, interval) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}&range=${encodeURIComponent(range)}&includePrePost=false`;
  const r = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "application/json",
    },
  });
  if (!r.ok) return { ok: false, status: r.status, result: null };
  const data = await r.json();
  return { ok: true, status: 200, result: data?.chart?.result?.[0] ?? null };
}

// Combina el rango pedido (largo, para históricos/medias) con uno corto
// (5d) y añade cualquier cierre del corto que sea MÁS RECIENTE que el
// último punto del largo. Necesario porque la caché de rango largo de la
// API de gráficos de Yahoo puede tener un hueco reciente que el rango corto
// no tiene — visto en vivo con ^MOVE el 2026-08-09: range=3y se quedaba
// clavado en 2026-07-17 mientras range=5d ya traía el cierre real del
// 2026-08-07 (72.03, confirmado también en Yahoo web/Investing.com). Sin
// esto, `/api/quote` y `/api/history` heredan ese hueco de Yahoo en
// silencio — el símbolo simplemente parece "sin actualizar" cuando el dato
// sí existe, solo que en otro rango de la misma API.
async function fetchYahooChartFresh(symbol, range, interval) {
  const long = await fetchYahooChartRaw(symbol, range, interval);
  if (!long.ok || !long.result) return long;
  const result = long.result;
  const timestamps = result.timestamp ?? [];
  const q = result.indicators?.quote?.[0] ?? {};
  q.close ??= []; q.volume ??= []; q.high ??= []; q.low ??= [];
  const lastLongTs = timestamps.length ? timestamps[timestamps.length - 1] : 0;

  if (range !== "5d") {
    try {
      const short = await fetchYahooChartRaw(symbol, "5d", interval);
      if (short.ok && short.result) {
        const sTs = short.result.timestamp ?? [];
        const sq = short.result.indicators?.quote?.[0] ?? {};
        for (let i = 0; i < sTs.length; i++) {
          if (sq.close?.[i] == null || sTs[i] <= lastLongTs) continue;
          timestamps.push(sTs[i]);
          q.close.push(sq.close[i]);
          q.volume.push(sq.volume?.[i] ?? null);
          q.high.push(sq.high?.[i] ?? null);
          q.low.push(sq.low?.[i] ?? null);
        }
      }
    } catch { /* el rango corto es un extra — si falla, seguimos con el largo tal cual */ }
  }
  return long;
}

// ── buildQuoteData — assembly exacto de la respuesta de /api/quote/:symbol ─
// Único lugar donde se construye el objeto de "todo lo que se ve por
// ticker" — tanto la ruta Express como scripts/portfolio_daily_snapshot.js
// llaman a esta misma función, para que la captura diaria del pipeline no
// pueda divergir de lo que muestra el dashboard en vivo. Lanza un Error con
// `.httpStatus` en los casos que antes mapeaban a un status HTTP concreto;
// el llamador decide qué hacer con eso (responder HTTP, o solo loguear y
// seguir con el siguiente ticker en el script standalone).
async function buildQuoteData(symbol) {
  const { ok, status, result } = await fetchYahooChartFresh(symbol, "3y", "1d");
  if (!ok) { const e = new Error(`Yahoo ${status}`); e.httpStatus = status; throw e; }
  if (!result) { const e = new Error("No data"); e.httpStatus = 404; throw e; }

  const closes     = result.indicators?.quote?.[0]?.close ?? [];
  const timestamps = result.timestamp ?? [];
  while (closes.length && closes[closes.length - 1] == null) { closes.pop(); timestamps.pop(); }
  if (!closes.length) { const e = new Error("No closes"); e.httpStatus = 404; throw e; }

  const volumes = (result.indicators?.quote?.[0]?.volume ?? []).slice(0, closes.length);
  const highs   = (result.indicators?.quote?.[0]?.high   ?? []).slice(0, closes.length);
  const lows    = (result.indicators?.quote?.[0]?.low    ?? []).slice(0, closes.length);

  const price   = closes[closes.length - 1];
  const now     = Date.now(), oneYrMs = 365 * 86400 * 1000;
  const yrClose = closes.filter((c, i) => c != null && timestamps[i] * 1000 >= now - oneYrMs);
  const w52Low  = Math.min(...yrClose), w52High = Math.max(...yrClose);
  const pct     = (a, b) => b ? Math.round((a - b) / Math.abs(b) * 100) : null;
  const ret     = d => { const i = closes.length - 1 - d; return i >= 0 && closes[i] ? pct(price, closes[i]) : null; };
  const ytdIdx  = timestamps.findIndex(t => t >= new Date(new Date().getFullYear(), 0, 1).getTime() / 1000);
  const absAt   = d => closes[closes.length - 1 - d] ?? null;

  const recent3m = volumes.slice(-63).filter(v => v != null && v > 0);
  const avg3m    = recent3m.length ? recent3m.reduce((a,b)=>a+b,0) / recent3m.length : null;
  const volPct   = d => { const i = volumes.length - 1 - d; return (i >= 0 && volumes[i] != null && avg3m) ? Math.round(volumes[i] / avg3m * 100) : null; };

  return {
    ticker:   symbol,
    asOf:     new Date(timestamps[timestamps.length - 1] * 1000).toISOString(),
    price:    +price.toPrecision(6),
    fromLow:  pct(price, w52Low),
    fromHigh: pct(price, w52High),
    d1: ret(1), d2: ret(2), d3: ret(3),
    w1: ret(5), m1: ret(21), m3: ret(63), m6: ret(126),
    ytd: ytdIdx >= 0 ? pct(price, closes[ytdIdx]) : null,
    y1: ret(252), y3: ret(756),
    // Valores absolutos históricos (para deltas macro)
    v1w: absAt(5), v1m: absAt(21), v3m: absAt(63), v6m: absAt(126), v1y: absAt(252),
    // Volumen vs media 3 meses
    vol1d: volPct(0), vol2d: volPct(1), vol3d: volPct(2),
    // RSI, MACD, ATR, Koncorde Plus
    rsi: calcRSI(closes.slice(-100)),
    ...calcMACD(closes),
    ...calcAtlasMini(closes),
    ...calcATR(closes, highs, lows),
    cmf20: calcCMF(closes, highs, lows, volumes, 20),
    ...(getKoncordeData()[symbol.toUpperCase()] ?? {}),
    insider: getInsiderActivityData()[symbol.toUpperCase()] ?? null,
    // ── v2: SMAs, OBV, volumen, anti-extensión ──
    sma20:  calcSMA(closes, 20)  ? +calcSMA(closes, 20).toPrecision(6)  : null,
    sma50:  calcSMA(closes, 50)  ? +calcSMA(closes, 50).toPrecision(6)  : null,
    sma200: calcSMA(closes, 200) ? +calcSMA(closes, 200).toPrecision(6) : null,
    closeAboveSma200: calcSMA(closes, 200) != null ? price > calcSMA(closes, 200) : null,
    ...calcOBV(closes, volumes),
    volRatio: (() => {
      const v20 = volumes.slice(-20).filter(v => v != null && v > 0);
      const v60 = volumes.slice(-60).filter(v => v != null && v > 0);
      const a20 = v20.length ? v20.reduce((a,b)=>a+b,0)/v20.length : null;
      const a60 = v60.length ? v60.reduce((a,b)=>a+b,0)/v60.length : null;
      return (a20 && a60) ? +(a20/a60).toFixed(2) : null;
    })(),
    antiExt: (() => {
      const s20 = calcSMA(closes, 20);
      const { atrAbs } = calcATR(closes, highs, lows);
      if (s20 == null || atrAbs == null) return null;
      return price > s20 ? (price - s20) / atrAbs < 1.5 : false;
    })(),
  };
}

module.exports = {
  calcRSI, calcMACD, calcAtlasMini, calcATR, calcSMA, calcCMF, calcOBV,
  getKoncordeData, getInsiderActivityData,
  fetchYahooChartRaw, fetchYahooChartFresh,
  buildQuoteData,
};
