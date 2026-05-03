require("dotenv").config();
const express = require("express");
const fetch   = require("node-fetch");
const cors    = require("cors");
const path    = require("path");
const fs      = require("fs");

const app = express();
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

// ── Koncorde (Blai5) ──────────────────────────────────────────────────────
// Verde ≈ Estocástico %K(2) − 50        → dinero minorista (nerviosismo)
// Azul  ≈ CMF(20) × 50                  → dinero institucional (flujo real)
// Señal combinada: Acumulación / Alza / Distribución / Baja
function calcKoncorde(closes, volumes, highs, lows) {
  const stochPeriod = 2;
  const cmfPeriod   = 20;
  const n = closes.length;
  if (n < cmfPeriod + 1) return { konVerde: null, konAzul: null, konSignal: null };

  // Verde: Estocástico %K(2) − 50
  const slH = highs.slice(-stochPeriod).filter(x => x != null);
  const slL = lows.slice(-stochPeriod).filter(x => x != null);
  const stH = slH.length ? Math.max(...slH) : null;
  const stL = slL.length ? Math.min(...slL) : null;
  const verde = (stH != null && stL != null && stH !== stL)
    ? Math.round((closes[n - 1] - stL) / (stH - stL) * 100 - 50)
    : 0;

  // Azul: CMF(20) × 50
  // CMF = Σ[ ((Close - Low) - (High - Close)) / (High - Low) × Volume ] / Σ Volume
  let mfvSum = 0, volSum = 0;
  for (let i = n - cmfPeriod; i < n; i++) {
    const h = highs[i], l = lows[i], c = closes[i], v = volumes[i];
    if (h == null || l == null || c == null || v == null || v === 0) continue;
    const range = h - l;
    const mfm = range !== 0 ? ((c - l) - (h - c)) / range : 0;
    mfvSum += mfm * v;
    volSum += v;
  }
  const cmf = volSum > 0 ? mfvSum / volSum : 0;
  const azul = Math.round(cmf * 50);

  // Señal combinada
  let konSignal;
  if      (azul >= 0 && verde <  0) konSignal = 'Acumulac.';
  else if (azul >= 0 && verde >= 0) konSignal = 'Alza';
  else if (azul <  0 && verde >= 0) konSignal = 'Distribuc.';
  else                              konSignal = 'Baja';

  return { konVerde: verde, konAzul: azul, konSignal };
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
app.get("/api/quote/:symbol", async (req, res) => {
  const sym = encodeURIComponent(req.params.symbol);
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?interval=1d&range=3y&includePrePost=false`;
  try {
    const r = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
      },
    });
    if (!r.ok) return res.status(r.status).json({ error: `Yahoo ${r.status}` });
    const data = await r.json();
    const result = data?.chart?.result?.[0];
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
      price:    +price.toPrecision(6),
      fromLow:  pct(price, w52Low),
      fromHigh: pct(price, w52High),
      d1: ret(1), d2: ret(2), d3: ret(3),
      w1: ret(5), m1: ret(21), m3: ret(63),
      ytd: ytdIdx >= 0 ? pct(price, closes[ytdIdx]) : null,
      y1: ret(252), y3: ret(756),
      // Valores absolutos históricos (para deltas macro)
      v1w: absAt(5), v1m: absAt(21), v1y: absAt(252),
      // Volumen vs media 3 meses
      vol1d: volPct(0), vol2d: volPct(1), vol3d: volPct(2),
      // RSI, MACD, ATR, Koncorde
      rsi: calcRSI(closes.slice(-100)),
      ...calcMACD(closes),
      ...calcATR(closes, highs, lows),
      ...calcKoncorde(closes, volumes, highs, lows),
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
  const sym = encodeURIComponent(req.params.symbol);
  const range = req.query.range || "3y";
  const interval = req.query.interval || "1d";
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?interval=${encodeURIComponent(interval)}&range=${encodeURIComponent(range)}&includePrePost=false`;

  try {
    const r = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
      },
    });
    if (!r.ok) return res.status(r.status).json({ error: `Yahoo ${r.status}` });
    const data = await r.json();
    const result = data?.chart?.result?.[0];
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
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${req.params.series}&api_key=${key}&sort_order=desc&limit=300&file_type=json`;

  try {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await r.json();
    if (data.error_message) return res.status(400).json({ error: data.error_message });
    const obs = (data.observations || []).filter(o => o.value !== ".");
    if (!obs.length) return res.status(404).json({ error: "No data" });

    const val = i => obs[i] ? parseFloat(obs[i].value) : null;

    res.json({
      series:  req.params.series,
      current: val(0),
      date:    obs[0]?.date,
      v1w: isMonthly ? null    : val(5),
      v1m: isMonthly ? val(1)  : val(21),
      v3m: isMonthly ? val(3)  : val(65),
      v1y: isMonthly ? val(12) : val(252),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
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

  try {
    const results = await Promise.all(seriesIds.map(async sid => {
      const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${sid}&api_key=${key}&sort_order=asc&limit=500&file_type=json`;
      const r = await fetch(url, { headers: { Accept: "application/json" } });
      const data = await r.json();
      return (data.observations || []).filter(o => o.value !== ".").map(o => ({ date: o.date, v: parseFloat(o.value) }));
    }));

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
    res.json({
      series:  "NET_LIQ",
      current: val(0),
      date:    combined[0].date,
      v1w:  val(1),
      v1m:  val(4),
      v13w: val(13),
      v1y:  val(52),
    });
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
  current_regime: null, regime_entered_date: null,
  pending_regime: null, pending_since_count: 0,
  flags: {
    CREDIT_COMPLACENCY:  { active: false, streak_weeks: 0 },
    INFLATION_OVERLAY:   { active: false, streak_weeks: 0 },
    TERM_PREMIUM_EXTREME:{ active: false, streak_weeks: 0 },
    EMERGENCY_MODE:      { active: false, activated_at: null, expires_date: null },
  },
  early_rotation_candidates: {},
};

app.get("/api/stock-candidates", (_req, res) => {
  const p = path.join(__dirname, "backtest/data/processed/stock_candidates.json");
  try {
    if (!fs.existsSync(p)) return res.json({ candidates: [], active_rot_temprana_clusters: [], updated: null });
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

app.get("*", (req, res) => res.sendFile(path.join(__dirname, "index.html")));
app.listen(3000, () => console.log("✅ Market Tracker → http://localhost:3000"));
