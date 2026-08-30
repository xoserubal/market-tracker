// One-off reconstruction script for the AI Picks Lab external audit
// (wiki/ASESOR_EXTERNO_AUDITORIA_CARTERAS_IA.md). NOT part of the pipeline.
//
// Computes RSI/MACD/ATR%/w1/m1/fromHigh/Flow Score/Early Flow Score for each
// trade window, reusing shared/quote-lib.js and shared/flow-score.js
// verbatim (same functions the live dashboard uses) so this reconstruction
// can never diverge from what portfolio.html actually shows. Koncorde
// D/3D/W states come from koncorde_windowed.jsonl (Python reconstruction,
// scripts/koncorde_calculator.py's real functions, see reconstruct step).
//
// Input:  ohlcv_long_history.json (68 tickers, 2022-06 -> today)
//         koncorde_windowed.jsonl (date,ticker -> konc_d/3d/w state+blue+trend_ma)
//         trades_windows.json (147 trades: portfolio/ticker/entry/close)
// Output: trade_review_signals.jsonl — one row per (ticker,date) within
//         each trade's window (entry-25d .. close+40d), with all fields.

const fs = require("fs");
const path = require("path");
const { calcRSI, calcMACD, calcATR } = require("../../shared/quote-lib.js");
const { computeFlowScore, computeEarlyFlowScore } = require("../../shared/flow-score.js");

const DIR = __dirname;
const ohlcv = JSON.parse(fs.readFileSync(path.join(DIR, "ohlcv_long_history.json"), "utf8"));
const trades = JSON.parse(fs.readFileSync(path.join(DIR, "trades_windows.json"), "utf8"));

// Load Koncorde windowed rows -> Map ticker -> Map date -> {konc_d_state, konc_3d_state, konc_w_state, ...}
const koncByTicker = {};
for (const line of fs.readFileSync(path.join(DIR, "koncorde_windowed.jsonl"), "utf8").split("\n")) {
  const t = line.trim();
  if (!t) continue;
  const r = JSON.parse(t);
  (koncByTicker[r.ticker] ??= {})[r.date] = r;
}

const TODAY = "2026-08-30";
function pct(a, b) { return b ? Math.round((a - b) / Math.abs(b) * 100) : null; }

function addDays(dateStr, days) {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// Union window per ticker (same padding as the Python step, so both sides agree).
const windows = {};
for (const t of trades) {
  if (!ohlcv[t.ticker] || !t.entry_date) continue;
  const s = addDays(t.entry_date, -25);
  const e = addDays(t.close_date || TODAY, 40);
  const w = windows[t.ticker];
  if (!w) windows[t.ticker] = [s, e];
  else { windows[t.ticker][0] = s < w[0] ? s : w[0]; windows[t.ticker][1] = e > w[1] ? e : w[1]; }
}

const outRows = [];
let tickersDone = 0;
for (const [ticker, [wStart, wEnd]] of Object.entries(windows)) {
  const data = ohlcv[ticker];
  const dates = data.dates;
  const closes = data.close, highs = data.high, lows = data.low;

  let prevD = null;
  for (let i = 0; i < dates.length; i++) {
    const date = dates[i];
    if (date < wStart || date > wEnd) { continue; }
    const closesUpTo = closes.slice(0, i + 1);
    const highsUpTo = highs.slice(0, i + 1);
    const lowsUpTo = lows.slice(0, i + 1);

    const price = closes[i];
    const w1 = i >= 5 ? pct(price, closes[i - 5]) : null;
    const m1 = i >= 21 ? pct(price, closes[i - 21]) : null;
    const trailWin = closesUpTo.slice(-252).filter(v => v != null);
    const w52High = trailWin.length ? Math.max(...trailWin) : null;
    const fromHigh = w52High ? pct(price, w52High) : null;

    const rsi = calcRSI(closesUpTo.slice(-100));
    const { macdHist, macdBull } = calcMACD(closesUpTo);
    const { atrPct } = calcATR(closesUpTo, highsUpTo, lowsUpTo);

    const k = (koncByTicker[ticker] || {})[date] || {};

    const d = {
      w1, m1, rsi, macdBull, atrPct, fromHigh,
      konc_d_state: k.konc_d_state ?? null,
      konc_3d_state: k.konc_3d_state ?? null,
      konc_w_state: k.konc_w_state ?? null,
    };

    const flowScore = computeFlowScore(d);
    const earlyFlow = computeEarlyFlowScore(d, prevD);

    outRows.push({
      date, ticker, price: +price.toPrecision(6),
      rsi, macdHist, macdBull, atrPct, w1, m1, fromHigh,
      konc_d_blue: k.konc_d_blue ?? null, konc_d_trend_ma: k.konc_d_trend_ma ?? null, konc_d_state: k.konc_d_state ?? null,
      konc_3d_blue: k.konc_3d_blue ?? null, konc_3d_trend_ma: k.konc_3d_trend_ma ?? null, konc_3d_state: k.konc_3d_state ?? null,
      konc_w_blue: k.konc_w_blue ?? null, konc_w_trend_ma: k.konc_w_trend_ma ?? null, konc_w_state: k.konc_w_state ?? null,
      flowScore, earlyFlow,
    });
    prevD = d;
  }
  tickersDone++;
}

const outPath = path.join(DIR, "trade_review_signals.jsonl");
fs.writeFileSync(outPath, outRows.map(r => JSON.stringify(r)).join("\n") + "\n", "utf8");
console.log(`tickers processed: ${tickersDone}/${Object.keys(windows).length}`);
console.log(`rows written: ${outRows.length} -> ${outPath}`);

// sanity check
const pltr828 = outRows.find(r => r.ticker === "PLTR" && r.date === "2026-08-28");
console.log("sanity PLTR 2026-08-28:", pltr828);
