require("dotenv").config({ path: require("path").join(__dirname, ".env") });
const express = require("express");
const fetch   = require("node-fetch");
const cors    = require("cors");
const path    = require("path");
const fs      = require("fs");
const { exec } = require("child_process");

const app = express();

// ── FRED cache + rate-limit guard ────────────────────────────────────────
// Cache: 10 min TTL (data has 1-day lag anyway).
// Queue: max 1 outgoing FRED call at a time + 200 ms gap to stay under 120 req/min.
const FRED_CACHE = new Map();
const FRED_CACHE_TTL = 10 * 60 * 1000;
function fredCacheGet(key) {
  const entry = FRED_CACHE.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts > FRED_CACHE_TTL) { FRED_CACHE.delete(key); return null; }
  return entry.data;
}
function fredCacheSet(key, data) { FRED_CACHE.set(key, { data, ts: Date.now() }); }

// Pending map: deduplicates concurrent calls for the same key.
const FRED_PENDING = new Map();
let fredQueueRunning = false;
const fredQueue = [];
function enqueueFreddFetch(fn) {
  return new Promise((resolve, reject) => {
    fredQueue.push({ fn, resolve, reject });
    if (!fredQueueRunning) drainFredQueue();
  });
}
async function drainFredQueue() {
  fredQueueRunning = true;
  while (fredQueue.length > 0) {
    const { fn, resolve, reject } = fredQueue.shift();
    try { resolve(await fn()); } catch (e) { reject(e); }
    if (fredQueue.length > 0) await new Promise(r => setTimeout(r, 600));
  }
  fredQueueRunning = false;
}
function fredFetchWithCache(cacheKey, fetchFn) {
  const cached = fredCacheGet(cacheKey);
  if (cached) return Promise.resolve(cached);
  if (FRED_PENDING.has(cacheKey)) return FRED_PENDING.get(cacheKey);
  const promise = enqueueFreddFetch(async () => {
    try {
      const result = await fetchFn();
      fredCacheSet(cacheKey, result);
      return result;
    } finally {
      FRED_PENDING.delete(cacheKey);
    }
  });
  FRED_PENDING.set(cacheKey, promise);
  return promise;
}
app.use(cors());
app.use(express.static(__dirname));

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
  const p = path.join(__dirname, "docs", "data", "koncorde_data.json");
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

app.get("/api/quote/:symbol", async (req, res) => {
  try {
    const { ok, status, result } = await fetchYahooChartFresh(req.params.symbol, "3y", "1d");
    if (!ok) return res.status(status).json({ error: `Yahoo ${status}` });
    if (!result) return res.status(404).json({ error: "No data" });

    const closes     = result.indicators?.quote?.[0]?.close ?? [];
    const timestamps = result.timestamp ?? [];
    while (closes.length && closes[closes.length - 1] == null) { closes.pop(); timestamps.pop(); }
    if (!closes.length) return res.status(404).json({ error: "No closes" });

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

    res.json({
      ticker:   req.params.symbol,
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
      ...calcATR(closes, highs, lows),
      cmf20: calcCMF(closes, highs, lows, volumes, 20),
      ...(getKoncordeData()[req.params.symbol.toUpperCase()] ?? {}),
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
    });
  } catch (err) {
    console.error(req.params.symbol, err.message);
    res.status(500).json({ error: err.message });
  }
});

// ── FRED proxy (single series) ───────────────────────────────────────────
// Historical Yahoo closes for experimental ratio pages.
app.get("/api/history/:symbol", async (req, res) => {
  const range = req.query.range || "3y";
  const interval = req.query.interval || "1d";

  try {
    const { ok, status, result } = await fetchYahooChartFresh(req.params.symbol, range, interval);
    if (!ok) return res.status(status).json({ error: `Yahoo ${status}` });
    if (!result) return res.status(404).json({ error: "No data" });

    const closes = result.indicators?.quote?.[0]?.close ?? [];
    const timestamps = result.timestamp ?? [];
    const series = timestamps
      .map((t, i) => ({ date: new Date(t * 1000).toISOString().slice(0, 10), close: closes[i] }))
      .filter(p => p.close != null && Number.isFinite(p.close));

    if (!series.length) return res.status(404).json({ error: "No closes" });
    res.json({ ticker: req.params.symbol, series });
  } catch (err) {
    console.error(req.params.symbol, err.message);
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/fred/:series", async (req, res) => {
  const key = process.env.FRED_API_KEY;
  if (!key) return res.status(400).json({ error: "FRED_API_KEY no configurada en .env" });

  const isMonthly = req.query.monthly === "1";
  const isWeekly  = req.query.weekly  === "1";
  const cacheKey = `${req.params.series}:${isMonthly}:${isWeekly}`;
  const seriesId = req.params.series;

  try {
    const result = await fredFetchWithCache(cacheKey, async () => {
      const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}&api_key=${key}&sort_order=desc&limit=300&file_type=json`;
      const r = await fetch(url, { headers: { Accept: "application/json" } });
      const data = await r.json();
      if (data.error_message) throw Object.assign(new Error(data.error_message), { fredError: true });
      const obs = (data.observations || []).filter(o => o.value !== ".");
      if (!obs.length) throw Object.assign(new Error("No data"), { notFound: true });
      const val = i => obs[i] ? parseFloat(obs[i].value) : null;
      return {
        series:  seriesId,
        current: val(0),
        date:    obs[0]?.date,
        v1w: isWeekly ? val(1)  : isMonthly ? null    : val(5),
        v1m: isWeekly ? val(4)  : isMonthly ? val(1)  : val(21),
        v3m: isWeekly ? val(13) : isMonthly ? val(3)  : val(65),
        v6m: isWeekly ? val(26) : isMonthly ? val(6)  : val(130),
        v1y: isWeekly ? val(52) : isMonthly ? val(12) : val(252),
        // Compact history for sparklines (last ~90 observations, ascending date order)
        history: obs.slice(0, 90).reverse().map(o => ({ date: o.date, value: parseFloat(o.value) })),
      };
    });
    res.json(result);
  } catch (err) {
    const status = err.notFound ? 404 : 400;
    res.status(status).json({ error: err.message });
  }
});

// ── FRED proxy (multi-series combinado: WALCL - RRPONTSYD - WTREGEN) ────
// Net Liquidity = Fed BS - Reverse Repo - Treasury General Account
// Uses nearest-prior-date lookup so daily (RRPONTSYD) aligns with weekly series.
app.get("/api/fred3", async (req, res) => {
  const key = process.env.FRED_API_KEY;
  if (!key) return res.status(400).json({ error: "FRED_API_KEY no configurada" });
  const seriesIds = (req.query.s || "").split(",").filter(Boolean);
  if (seriesIds.length < 1) return res.status(400).json({ error: "No series" });

  const cacheKey = `fred3:${seriesIds.join(",")}`;

  try {
    const cachedResult = fredCacheGet(cacheKey);
    if (cachedResult) return res.json(cachedResult);

    // Fetch each sub-series sequentially through the shared queue
    const results = [];
    for (const sid of seriesIds) {
      const subKey = `${sid}:desc100`;
      const rows = await fredFetchWithCache(subKey, async () => {
        // desc+limit=100 gets the most recent ~2 years of weekly data; sort asc afterwards for nearestPrior lookup
        const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${sid}&api_key=${key}&sort_order=desc&limit=100&file_type=json`;
        const r = await fetch(url, { headers: { Accept: "application/json" } });
        const data = await r.json();
        return (data.observations || []).filter(o => o.value !== ".").map(o => ({ date: o.date, v: parseFloat(o.value) })).reverse();
      });
      results.push(rows);
    }

    // Build sorted date→value maps for each series (ascending order for binary search)
    const makeSortedMap = arr => arr.sort((a, b) => a.date.localeCompare(b.date));
    const sorted = results.map(makeSortedMap);

    // For a target date, return the most recent value in sorted array that is ≤ target
    function nearestPrior(arr, targetDate) {
      let lo = 0, hi = arr.length - 1, found = null;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (arr[mid].date <= targetDate) { found = arr[mid].v; lo = mid + 1; }
        else hi = mid - 1;
      }
      return found;
    }

    // Use series[0] (WALCL, weekly) dates as anchor; look up nearest prior for others
    const anchor = sorted[0];
    if (!anchor.length) return res.status(404).json({ error: "No data for anchor series" });

    // Build combined newest-first
    const combined = anchor
      .map(({ date, v: v0 }) => {
        const v1 = nearestPrior(sorted[1], date) ?? 0;
        const v2 = sorted[2] ? (nearestPrior(sorted[2], date) ?? 0) : 0;
        return { date, v: v0 - v1 - v2 };
      })
      .reverse();  // newest first

    if (!combined.length) return res.status(404).json({ error: "No data aligned" });

    const val = i => combined[i]?.v ?? null;
    const result = {
      series:  "NET_LIQ",
      current: val(0),
      date:    combined[0].date,
      v1w:  val(1),
      v1m:  val(4),
      v3m:  val(13),
      v6m:  val(26),
      v1y:  val(52),
    };
    fredCacheSet(cacheKey, result);  // cache the combined result too
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── OilPriceAPI proxy — con cache local para deltas ──────────────────────
// Free tier: 1.000 req/mes · https://oilpriceapi.com
// Códigos probados: JKM_LNG_USD | COKING_COAL_USD
// WCS: si falla (no disponible en free tier) se indica en el campo
const ENERGY_CACHE = path.join(__dirname, "energy_cache.json");

function readCache() {
  try { return JSON.parse(fs.readFileSync(ENERGY_CACHE, "utf8")); } catch { return {}; }
}
function writeCache(cache) {
  try { fs.writeFileSync(ENERGY_CACHE, JSON.stringify(cache)); } catch(e) { console.error("cache:", e.message); }
}
// Busca el precio más cercano a (now - targetMs) con tolerancia toleranceMs
function cachedAt(history, targetMs, toleranceMs) {
  if (!history?.length) return null;
  const target = Date.now() - targetMs;
  let best = null, bestDiff = Infinity;
  for (const e of history) {
    const diff = Math.abs(e.ts - target);
    if (diff < bestDiff && diff < toleranceMs) { best = e; bestDiff = diff; }
  }
  return best?.price ?? null;
}

app.get("/api/oilprice/:code", async (req, res) => {
  const key = process.env.OILPRICE_API_KEY;
  if (!key) return res.status(400).json({ error: "sin_clave" });

  const url = `https://api.oilpriceapi.com/v1/prices/latest?by_code=${encodeURIComponent(req.params.code)}`;
  try {
    const r = await fetch(url, {
      headers: { "Authorization": `Token ${key}`, "Content-Type": "application/json" },
    });
    if (r.status === 401) return res.status(401).json({ error: "clave_invalida" });
    if (r.status === 404) return res.status(404).json({ error: "codigo_no_encontrado" });
    if (!r.ok)            return res.status(r.status).json({ error: `api_${r.status}` });

    const data = await r.json();
    if (data.status !== "success") return res.status(400).json({ error: data.error || "api_error" });

    const price = data.data.price;
    const code  = req.params.code;
    const now   = Date.now();
    const day   = 86400 * 1000;

    // Actualizar cache (máximo 1 entrada cada 6 h para ahorrar disco)
    const cache = readCache();
    if (!cache[code]) cache[code] = [];
    const last = cache[code][cache[code].length - 1];
    if (!last || now - last.ts > 6 * 3600 * 1000) {
      cache[code].push({ ts: now, price });
      if (cache[code].length > 500) cache[code] = cache[code].slice(-500);
      writeCache(cache);
    }

    res.json({
      code,
      price,
      currency: data.data.currency,
      date:     data.data.created_at,
      v1w: cachedAt(cache[code], 7   * day, 2  * day),
      v1m: cachedAt(cache[code], 30  * day, 5  * day),
      v1y: cachedAt(cache[code], 365 * day, 20 * day),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── CNN Fear & Greed proxy ────────────────────────────────────────────────
// CNN's endpoint requires a browser-like Referer or it returns 418 ("I'm a
// teapot. You're a bot."). It does send Access-Control-Allow-Origin: * so a
// direct browser fetch would technically work, but proxying server-side
// keeps sentiment.html insulated from CNN's bot-detection flakiness and
// avoids hammering their API on every page load (same rationale as the
// FRED cache above).
let _fearGreedCache = null;
let _fearGreedCacheTs = 0;
const FEAR_GREED_TTL = 15 * 60 * 1000;

app.get("/api/fear-greed", async (_req, res) => {
  if (_fearGreedCache && Date.now() - _fearGreedCacheTs < FEAR_GREED_TTL) {
    return res.json(_fearGreedCache);
  }
  try {
    const r = await fetch("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        "Accept": "application/json, text/plain, */*",
      },
    });
    if (!r.ok) throw new Error(`CNN respondió ${r.status}`);
    const data = await r.json();
    _fearGreedCache = data;
    _fearGreedCacheTs = Date.now();
    res.json(data);
  } catch (err) {
    if (_fearGreedCache) return res.json(_fearGreedCache); // stale-but-served
    res.status(502).json({ error: err.message });
  }
});

// ── Treasury auction results proxy (Fiscal Data API) ─────────────────────
// api.fiscaldata.treasury.gov does NOT publish a when-issued yield, so we
// cannot compute the real auction "tail" (high_yield - WI_yield). Verified
// against a live call: fields available are cusip/security_type/security_term/
// auction_date/high_yield/bid_to_cover_ratio, nothing WI-related. We expose
// auction_high_yield + bid_to_cover plus comparisons vs the trailing average
// of the same tenor, and leave true_tail_bps explicit null rather than
// mislabeling a proxy as the real tail.
//
// 2026-08-10: añadido indirect_pct/dealer_pct/direct_pct (% del total
// aceptado por cada categoría de bidder) — el mismo endpoint auctions_query
// ya trae indirect_bidder_accepted/primary_dealer_accepted/
// direct_bidder_accepted/total_accepted, solo faltaba pedirlos. Indirect
// bajo + dealer alto = demanda externa débil, los dealers absorbiendo lo
// que el mercado no quiso — la señal de estrés de demanda más directa que
// bid-to-cover. Deliberadamente NO se ha metido todavía en
// auction_stress_proxy (fase de observación, mismo criterio que
// extension_risk/Koncorde en su día: exponer primero, calibrar un umbral
// real después de ver datos, no inventarlo ahora).
let _treasuryAuctionsCache = null;
let _treasuryAuctionsCacheTs = 0;
const TREASURY_AUCTIONS_TTL = 6 * 60 * 60 * 1000; // 6h — auctions are weekly/monthly, not intraday
const AUCTION_TENORS = ["10-Year", "30-Year", "2-Year"]; // display priority: 10Y/30Y over 2Y

app.get("/api/treasury-auctions", async (_req, res) => {
  if (_treasuryAuctionsCache && Date.now() - _treasuryAuctionsCacheTs < TREASURY_AUCTIONS_TTL) {
    return res.json(_treasuryAuctionsCache);
  }
  try {
    const fields = "cusip,security_type,security_term,auction_date,high_yield,bid_to_cover_ratio,inflation_index_security,"
      + "indirect_bidder_accepted,primary_dealer_accepted,direct_bidder_accepted,total_accepted";
    const url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
      + `?fields=${fields}&filter=security_term:in:(2-Year,10-Year,30-Year)&sort=-auction_date&page[size]=100`;
    const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0", Accept: "application/json" } });
    if (!r.ok) throw new Error(`Fiscal Data respondió ${r.status}`);
    const json = await r.json();
    const numOrNull = v => (v == null || v === "null" || v === "") ? null : parseFloat(v);
    // security_type dice "Bond" tanto para 30-Year nominal como para 30-Year TIPS —
    // el campo que realmente distingue es inflation_index_security. Sin este filtro,
    // subastas TIPS (yield real ~2.4%) se mezclaban con bonos nominales (~4.7-5%) en
    // el mismo bucket "30-Year", corrompiendo el promedio y el stress proxy.
    const rows = (json.data || [])
      .filter(row => row.inflation_index_security !== "Yes")
      .map(row => {
        const total = numOrNull(row.total_accepted);
        const pctOf = v => (v != null && total) ? (v / total) * 100 : null;
        return {
          cusip: row.cusip,
          security_term: row.security_term,
          auction_date: row.auction_date,
          high_yield: numOrNull(row.high_yield),
          bid_to_cover: numOrNull(row.bid_to_cover_ratio),
          indirect_pct: pctOf(numOrNull(row.indirect_bidder_accepted)),
          dealer_pct: pctOf(numOrNull(row.primary_dealer_accepted)),
          direct_pct: pctOf(numOrNull(row.direct_bidder_accepted)),
        };
      });

    // sort=-auction_date trae también subastas anunciadas pero aún no
    // ejecutadas (auction_date en el futuro) — sus campos numéricos vienen
    // null porque el resultado todavía no existe. Sin filtrar esto, "la más
    // reciente" para 10Y/30Y podía ser una subasta que ni siquiera ha
    // pasado, produciendo "insufficient_data" varios días antes de cada
    // subasta real (encontrado en vivo 2026-08-10: 10Y/30Y anunciadas para
    // 12-13/8 salían como "última" con todo null, mientras la última
    // EJECUTADA con datos reales quedaba más atrás en la lista).
    const todayStr = new Date().toISOString().slice(0, 10);
    const avg = arr => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
    const tenors = {};
    for (const tenor of AUCTION_TENORS) {
      const tenorRows = rows
        .filter(row => row.security_term === tenor && row.auction_date <= todayStr)
        .slice(0, 8); // latest + trailing window
      if (!tenorRows.length) { tenors[tenor] = null; continue; }
      const [latest, ...recent] = tenorRows;
      const avgYield   = avg(recent.map(row => row.high_yield).filter(v => v != null));
      const avgBtc     = avg(recent.map(row => row.bid_to_cover).filter(v => v != null));
      const avgIndirect = avg(recent.map(row => row.indirect_pct).filter(v => v != null));
      const avgDealer   = avg(recent.map(row => row.dealer_pct).filter(v => v != null));
      const high_yield_vs_recent_avg = (latest.high_yield != null && avgYield != null)
        ? +((latest.high_yield - avgYield) * 100).toFixed(1) : null; // bps
      const bid_to_cover_vs_recent_avg = (latest.bid_to_cover != null && avgBtc != null)
        ? +(latest.bid_to_cover - avgBtc).toFixed(2) : null;
      const indirect_pct_vs_recent_avg = (latest.indirect_pct != null && avgIndirect != null)
        ? +(latest.indirect_pct - avgIndirect).toFixed(1) : null; // puntos porcentuales
      const dealer_pct_vs_recent_avg = (latest.dealer_pct != null && avgDealer != null)
        ? +(latest.dealer_pct - avgDealer).toFixed(1) : null;

      let auction_stress_proxy = "insufficient_data";
      if (high_yield_vs_recent_avg != null && bid_to_cover_vs_recent_avg != null) {
        if (high_yield_vs_recent_avg > 3 && bid_to_cover_vs_recent_avg < -0.05) auction_stress_proxy = "weak_demand";
        else if (high_yield_vs_recent_avg < -3 && bid_to_cover_vs_recent_avg > 0.05) auction_stress_proxy = "strong_demand";
        else auction_stress_proxy = "normal";
      }

      tenors[tenor] = {
        auction_date: latest.auction_date,
        cusip: latest.cusip,
        auction_high_yield: latest.high_yield,
        bid_to_cover: latest.bid_to_cover,
        high_yield_vs_recent_avg,
        bid_to_cover_vs_recent_avg,
        indirect_pct: latest.indirect_pct,
        indirect_pct_vs_recent_avg,
        dealer_pct: latest.dealer_pct,
        dealer_pct_vs_recent_avg,
        direct_pct: latest.direct_pct,
        auction_stress_proxy,
        true_tail_bps: null, // no when-issued yield published by this API
      };
    }

    const result = { as_of: new Date().toISOString(), tenors };
    _treasuryAuctionsCache = result;
    _treasuryAuctionsCacheTs = Date.now();
    res.json(result);
  } catch (err) {
    if (_treasuryAuctionsCache) return res.json(_treasuryAuctionsCache); // stale-but-served
    res.status(502).json({ error: err.message });
  }
});

// ── CFTC Commitments of Traders — posicionamiento Managed Money ──────────
// Dataset "Disaggregated Futures Only" (Socrata, publicreporting.cftc.gov,
// id 72hh-3qpy), semanal (viernes, datos del martes anterior). Managed
// Money = la categoría que el mercado llama "specs" en comentarios de
// posicionamiento. Verificado en vivo 2026-08-10 contra la API real:
// GOLD/SILVER/COPPER- #1 tenían datos frescos (2026-08-04) con el nombre
// obvio, pero "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE" (el
// nombre clásico de WTI) llevaba congelado en 2022-02-01 — CFTC renombró
// el contrato principal de WTI a "WTI-PHYSICAL - NEW YORK MERCANTILE
// EXCHANGE" en algún punto intermedio. Usar el nombre viejo habría servido
// un dato de 4+ años de antigüedad en silencio, mismo patrón que el
// mislabeling TIPS-vs-nominal ya documentado para /api/treasury-auctions.
const COT_CONTRACTS = {
  gold:   "GOLD - COMMODITY EXCHANGE INC.",
  silver: "SILVER - COMMODITY EXCHANGE INC.",
  copper: "COPPER- #1 - COMMODITY EXCHANGE INC.",
  wti:    "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
};
const _cotCache = {};
const COT_TTL = 12 * 60 * 60 * 1000; // 12h — el dato es semanal (viernes), no hace falta refrescar más a menudo
const COT_HISTORY_WEEKS = 170; // ~3.3 años — ventana para el percentil (170 obs, algo de margen sobre 156=3y)

app.get("/api/cot/:contract", async (req, res) => {
  const key = req.params.contract.toLowerCase();
  const marketName = COT_CONTRACTS[key];
  if (!marketName) {
    return res.status(404).json({ error: `Contrato desconocido: ${key}. Válidos: ${Object.keys(COT_CONTRACTS).join(", ")}` });
  }

  const cached = _cotCache[key];
  if (cached && Date.now() - cached.ts < COT_TTL) return res.json(cached.data);

  try {
    const url = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
      + `?$limit=${COT_HISTORY_WEEKS}&$order=report_date_as_yyyy_mm_dd DESC`
      + `&market_and_exchange_names=${encodeURIComponent(marketName)}`;
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`CFTC respondió ${r.status}`);
    const rows = await r.json();
    if (!rows.length) return res.status(404).json({ error: "Sin datos" });

    const num = v => (v == null || v === "") ? null : parseFloat(v);
    const series = rows.map(row => {
      const long = num(row.m_money_positions_long_all);
      const short = num(row.m_money_positions_short_all);
      return {
        date: row.report_date_as_yyyy_mm_dd.slice(0, 10),
        open_interest: num(row.open_interest_all),
        mm_long: long, mm_short: short,
        mm_net: (long != null && short != null) ? long - short : null,
        mm_pct_oi_long: num(row.pct_of_oi_m_money_long_all),
        mm_pct_oi_short: num(row.pct_of_oi_m_money_short_all),
      };
    }).reverse(); // ascendente por fecha, para el sparkline y el cálculo de cambio 1w

    const netSeries = series.map(p => p.mm_net).filter(v => v != null);
    const latest = series[series.length - 1];
    const prev = series[series.length - 2];
    const net_change_1w = (latest?.mm_net != null && prev?.mm_net != null) ? latest.mm_net - prev.mm_net : null;

    // Percentil del neto actual dentro de la ventana disponible (no siempre
    // llegan los 170 — algunos contratos tienen menos historial en este
    // dataset; se reporta n_weeks para que quede claro sobre qué ventana
    // se calculó).
    let percentile = null;
    if (latest?.mm_net != null && netSeries.length >= 20) {
      const belowOrEqual = netSeries.filter(v => v <= latest.mm_net).length;
      percentile = Math.round((belowOrEqual / netSeries.length) * 100);
    }

    const result = {
      contract: key, market_name: marketName,
      as_of: latest?.date ?? null,
      mm_net: latest?.mm_net ?? null,
      mm_long: latest?.mm_long ?? null,
      mm_short: latest?.mm_short ?? null,
      open_interest: latest?.open_interest ?? null,
      mm_pct_oi_long: latest?.mm_pct_oi_long ?? null,
      mm_pct_oi_short: latest?.mm_pct_oi_short ?? null,
      net_change_1w,
      percentile: percentile,
      n_weeks: netSeries.length,
      history: series.map(p => ({ date: p.date, mm_net: p.mm_net })),
    };
    _cotCache[key] = { ts: Date.now(), data: result };
    res.json(result);
  } catch (err) {
    if (_cotCache[key]) return res.json(_cotCache[key].data); // stale-but-served
    console.error("cot", key, err.message);
    res.status(500).json({ error: err.message });
  }
});

// ── Portfolio CRUD ────────────────────────────────────────────────────────
const PORTFOLIO_FILE = path.join(__dirname, "portfolio.json");

// ── Signals History ───────────────────────────────────────────────────────
const SIGNALS_FILE = path.join(__dirname, "signals_history.json");

function readSignals() {
  try { return JSON.parse(fs.readFileSync(SIGNALS_FILE, "utf8")); } catch { return []; }
}

app.get("/api/signals", (_req, res) => {
  res.json(readSignals());
});

app.post("/api/signals", express.json(), (req, res) => {
  const incoming = req.body;
  if (!Array.isArray(incoming)) return res.status(400).json({ error: "Expected array" });

  const history  = readSignals();
  const existing = new Set(history.map(e => `${e.date}|${e.ticker}`));
  const toAdd    = incoming.filter(e => !existing.has(`${e.date}|${e.ticker}`));

  if (toAdd.length) {
    try {
      fs.writeFileSync(SIGNALS_FILE, JSON.stringify([...history, ...toAdd], null, 2));
    } catch(e) { return res.status(500).json({ error: e.message }); }
  }
  res.json({ added: toAdd.length });
});

app.get("/api/portfolio", (_req, res) => {
  try {
    const data = fs.existsSync(PORTFOLIO_FILE)
      ? JSON.parse(fs.readFileSync(PORTFOLIO_FILE, "utf8"))
      : { sections: [] };
    res.json(data);
  } catch(err) { res.status(500).json({ error: err.message }); }
});

app.post("/api/portfolio", express.json(), (req, res) => {
  try {
    fs.writeFileSync(PORTFOLIO_FILE, JSON.stringify(req.body, null, 2));
    res.json({ ok: true });
  } catch(err) { res.status(500).json({ error: err.message }); }
});

// ── State persistence (histéresis + flags) ────────────────────────────────
const STATE_FILE = path.join(__dirname, "state.json");
const DEFAULT_STATE = {
  current_regime: null, regime_entered_date: null, previous_regime: null,
  pending_regime: null, pending_since_count: 0,
  flags: {
    CREDIT_COMPLACENCY:  { active: false, streak_weeks: 0 },
    INFLATION_OVERLAY:   { active: false, streak_weeks: 0 },
    TERM_PREMIUM_EXTREME:{ active: false, streak_weeks: 0 },
    EMERGENCY_MODE:      { active: false, activated_at: null, expires_date: null },
  },
  early_rotation_candidates: {},
  macro_score_history: [],
  rotation_history: {},
  regime_coherence_history: [],
};

// ── Stock config YAML (leer / escribir) ──────────────────────────────────
const STOCK_CFG = path.join(__dirname, "backtest/config/individual_stocks.yaml");

function parseStockYaml(text) {
  const clusters = {};
  let currentCluster = null, currentStock = null;
  for (const raw of text.split('\n')) {
    const line = raw.replace(/\r/, '');
    if (!line.trim() || line.trim().startsWith('#')) continue;
    // cluster: "  Name/With-Slash:"
    const clM = line.match(/^  ([\w\/\-]+):\s*$/);
    if (clM) { currentCluster = clM[1]; clusters[currentCluster] = []; currentStock = null; continue; }
    // ticker: "    - ticker: XYZ"
    const tkM = line.match(/^\s+- ticker:\s+(\S+)/);
    if (tkM && currentCluster) { currentStock = { ticker: tkM[1], note: '' }; clusters[currentCluster].push(currentStock); continue; }
    // note: '      note: "..."'  or  '      note: text'
    const ntM = line.match(/^\s+note:\s+"(.*)"\s*$/) || line.match(/^\s+note:\s+(.*)\s*$/);
    if (ntM && currentStock) { currentStock.note = ntM[1]; }
  }
  return clusters;
}

function generateStockYaml(clusters) {
  const lines = [
    '# Acciones individuales por cluster para el stock scanner.',
    '# Añade o quita tickers libremente — el pipeline los descarga automáticamente.',
    '#',
    '# Campos por ticker:',
    '#   ticker : símbolo Yahoo Finance (obligatorio)',
    '#   note   : motivo de inclusión — alta beta, small cap, apalancado, etc. (opcional)',
    '',
    'clusters:',
    '',
  ];
  for (const [cluster, stocks] of Object.entries(clusters)) {
    lines.push(`  ${cluster}:`);
    for (const s of (stocks || [])) {
      const note = (s.note || '').replace(/"/g, '\\"');
      lines.push(`    - ticker: ${s.ticker}`);
      lines.push(`      note: "${note}"`);
    }
    lines.push('');
  }
  return lines.join('\n');
}

app.get("/api/stock-config", (_req, res) => {
  try {
    if (!fs.existsSync(STOCK_CFG)) return res.json({});
    res.json(parseStockYaml(fs.readFileSync(STOCK_CFG, 'utf8')));
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post("/api/stock-config", express.json(), (req, res) => {
  try {
    fs.writeFileSync(STOCK_CFG, generateStockYaml(req.body), 'utf8');
    res.json({ ok: true });
    // Push al config a GitHub en background para que Actions lo recoja
    const rel = path.relative(__dirname, STOCK_CFG).replace(/\\/g, '/');
    const cmd = `git add "${rel}" && git diff --cached --quiet || git commit -m "chore: update individual_stocks.yaml from dashboard" && git push origin master`;
    exec(cmd, { cwd: __dirname }, (err, stdout, stderr) => {
      if (err) console.log("⚠ git push config:", (stderr || err.message).trim());
      else     console.log("✓ git push config:", stdout.trim() || "ok");
    });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.get("/api/stock-candidates", (_req, res) => {
  const p = path.join(__dirname, "backtest/data/processed/stock_candidates.json");
  try {
    if (!fs.existsSync(p)) return res.json({ candidates: [], active_confirmed_rotation_clusters: [], updated: null });
    res.json(JSON.parse(fs.readFileSync(p, "utf8")));
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.get("/api/state", (_req, res) => {
  try { res.json(JSON.parse(fs.readFileSync(STATE_FILE, "utf8"))); }
  catch { res.json(DEFAULT_STATE); }
});
app.post("/api/state", express.json(), (req, res) => {
  try { fs.writeFileSync(STATE_FILE, JSON.stringify(req.body, null, 2)); res.json({ ok: true }); }
  catch (e) { res.status(500).json({ error: e.message }); }
});

// ── Sync GitHub ──────────────────────────────────────────────────────────
let lastPull = null;

function fixGitObjectPerms(done) {
  const fs = require("fs");
  const objDir = path.join(__dirname, ".git", "objects");
  function walk(dir) {
    try {
      for (const entry of fs.readdirSync(dir)) {
        const full = path.join(dir, entry);
        try {
          const stat = fs.statSync(full);
          if (stat.isDirectory()) walk(full);
          else fs.chmodSync(full, 0o644);
        } catch (_) {}
      }
    } catch (_) {}
  }
  walk(objDir);
  done();
}

function gitPull(cb) {
  fixGitObjectPerms(() => {
    exec("git pull --ff-only origin master", { cwd: __dirname, timeout: 60000 }, (err, stdout, stderr) => {
      const msg = err ? (stderr || err.message).trim() : (stdout || "Ya actualizado").trim();
      if (!err) lastPull = new Date().toISOString();
      cb(err, msg);
    });
  });
}

app.get("/api/sync/status", (_req, res) => {
  exec("git log -1 --format=%cd --date=format:'%Y-%m-%d %H:%M'", { cwd: __dirname }, (err, stdout) => {
    res.json({ lastPull, lastCommit: stdout.trim().replace(/'/g, '') });
  });
});

app.post("/api/sync/pull", (_req, res) => {
  gitPull((err, msg) => res.json({ ok: !err, message: msg }));
});

// ── Universe ─────────────────────────────────────────────────────────────
const UNIVERSE_FILE = path.join(__dirname, "docs", "data", "universe.json");

app.get("/api/universe", (_req, res) => {
  try {
    if (!fs.existsSync(UNIVERSE_FILE)) return res.json({ tickers: [] });
    res.json(JSON.parse(fs.readFileSync(UNIVERSE_FILE, "utf8")));
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post("/api/universe/add", express.json(), (req, res) => {
  try {
    const body = req.body || {};
    const ticker = (body.ticker || "").trim().toUpperCase();
    if (!ticker) return res.status(400).json({ error: "ticker required" });

    let data = { tickers: [] };
    if (fs.existsSync(UNIVERSE_FILE))
      data = JSON.parse(fs.readFileSync(UNIVERSE_FILE, "utf8"));

    if (data.tickers.some(t => t.ticker === ticker))
      return res.json({ ok: true, already_exists: true });

    data.tickers.push({
      ticker,
      name:        body.name        || ticker,
      asset_type:  body.asset_type  || "stock",
      tradable:    body.tradable !== false,
      theme:       body.theme       || "",
      subtheme:    body.subtheme    || "",
      region:      body.region      || "US",
      macro_proxy: body.macro_proxy || "",
      theme_proxy: body.theme_proxy || "",
      benchmark:   body.benchmark   || "",
      priority:    body.priority    || "medium",
      notes:       body.notes       || "",
    });
    fs.writeFileSync(UNIVERSE_FILE, JSON.stringify(data, null, 2), "utf8");
    res.json({ ok: true, added: ticker });

    const rel = path.relative(__dirname, UNIVERSE_FILE).replace(/\\/g, "/");
    const cmd = `git add "${rel}" && git diff --cached --quiet || git commit -m "chore: add ${ticker} to universe from dashboard" && git push origin master`;
    exec(cmd, { cwd: __dirname }, (err, stdout, stderr) => {
      if (err) console.log("⚠ git push universe:", (stderr || err.message).trim());
      else     console.log("✓ git push universe:", stdout.trim() || "ok");
    });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post("/api/universe/remove", express.json(), (req, res) => {
  try {
    const ticker = ((req.body || {}).ticker || "").trim().toUpperCase();
    if (!ticker) return res.status(400).json({ error: "ticker required" });

    let data = { tickers: [] };
    if (fs.existsSync(UNIVERSE_FILE))
      data = JSON.parse(fs.readFileSync(UNIVERSE_FILE, "utf8"));

    const before = data.tickers.length;
    data.tickers = data.tickers.filter(t => t.ticker !== ticker);
    if (data.tickers.length === before)
      return res.json({ ok: true, not_found: true });

    fs.writeFileSync(UNIVERSE_FILE, JSON.stringify(data, null, 2), "utf8");
    res.json({ ok: true, removed: ticker });

    const rel = path.relative(__dirname, UNIVERSE_FILE).replace(/\\/g, "/");
    const cmd = `git add "${rel}" && git diff --cached --quiet || git commit -m "chore: remove ${ticker} from universe from dashboard" && git push origin master`;
    exec(cmd, { cwd: __dirname }, (err, stdout, stderr) => {
      if (err) console.log("⚠ git push universe:", (stderr || err.message).trim());
      else     console.log("✓ git push universe:", stdout.trim() || "ok");
    });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.get("*", (req, res) => res.sendFile(path.join(__dirname, "index.html")));

app.listen(3000, () => {
  console.log("✅ Market Tracker → http://localhost:3000");
  // Pull automático al arrancar para tener los datos más recientes de GitHub
  gitPull((err, msg) => {
    if (err) console.log("⚠ git pull al iniciar:", msg);
    else     console.log("✓ git pull al iniciar:", msg);
  });
});
