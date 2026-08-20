#!/usr/bin/env node
// ── Portfolio Daily Snapshot ─────────────────────────────────────────────
// Captura TODOS los datos diarios que portfolio.html enseña por ticker
// (precio, RSI, MACD, ATLAS Mini, ATR%, CMF, Koncorde D/3D/W, insider
// activity, SMAs, OBV, Flow Score, Early Flow Score) para el universo
// completo de docs/data/../portfolio.json — de forma independiente de si
// alguien abre el dashboard ese día. Pensado para correr como paso del
// pipeline de GitHub Actions (2×/día), así el registro queda completo para
// poder evaluar/backtestear estas señales a posteriori.
//
// Antes de esto, la única captura existía en un useEffect de portfolio.html
// (signals_history.json) que solo se disparaba con el navegador abierto, y
// que además solo guardaba una fila si computeFlowScore()/computeEarlyFlowScore()
// no salían null — perdiendo ATR%/MACD/etc. enteros ese día si faltaba un
// solo input de Flow Score. Este script no tiene esa puerta: escribe la fila
// cruda de buildQuoteData() siempre que el fetch a Yahoo funcione, añadiendo
// flowScore/earlyFlow como campos extra cuando se pueden calcular.
//
// Reutiliza shared/quote-lib.js (buildQuoteData — misma función que usa
// /api/quote/:symbol en server.js) y shared/flow-score.js
// (computeFlowScore/computeEarlyFlowScore — mismas fórmulas que
// portfolio.html) para que esta captura nunca pueda divergir del dashboard.
//
// Salida: docs/data/portfolio_daily_snapshot.jsonl — una fila por
// ticker/día natural (UTC), dedup por date+ticker (si ya existe una fila de
// hoy para un ticker, se omite — así el pipeline puede correr 2×/día sin
// duplicar). Formato JSONL (no un array JSON grande) para poder
// leerse/streamearse fila a fila en scripts de análisis futuros, mismo
// patrón que shadow_picks.jsonl / koncorde_signals_history.jsonl.
//
// CLI:
//   node scripts/portfolio_daily_snapshot.js                # captura real
//   node scripts/portfolio_daily_snapshot.js --dry-run       # no escribe nada
//   node scripts/portfolio_daily_snapshot.js --tickers=AAPL,NVDA  # subset
//   node scripts/portfolio_daily_snapshot.js --report        # resume el jsonl existente

const fs   = require("fs");
const path = require("path");
const { buildQuoteData } = require("../shared/quote-lib.js");
const { computeFlowScore, computeEarlyFlowScore } = require("../shared/flow-score.js");

const REPO_ROOT     = path.join(__dirname, "..");
const PORTFOLIO_FILE = path.join(REPO_ROOT, "portfolio.json");
const SNAPSHOT_FILE  = path.join(REPO_ROOT, "docs", "data", "portfolio_daily_snapshot.jsonl");

const BATCH_SIZE   = 8;    // llamadas concurrentes a Yahoo
const BATCH_GAP_MS = 300;  // pausa entre lotes — buen ciudadano con Yahoo

const args = process.argv.slice(2);
const DRY_RUN     = args.includes("--dry-run");
const REPORT_ONLY = args.includes("--report");
const tickersArg  = args.find(a => a.startsWith("--tickers="));
const TICKERS_OVERRIDE = tickersArg
  ? tickersArg.slice("--tickers=".length).split(",").map(t => t.trim().toUpperCase()).filter(Boolean)
  : null;

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function readJsonlRows(file) {
  if (!fs.existsSync(file)) return [];
  const text = fs.readFileSync(file, "utf8");
  const rows = [];
  for (const line of text.split("\n")) {
    const t = line.trim();
    if (!t) continue;
    try { rows.push(JSON.parse(t)); } catch { /* línea corrupta — se ignora, no rompe el resto */ }
  }
  return rows;
}

function loadPortfolioTickers() {
  const data = JSON.parse(fs.readFileSync(PORTFOLIO_FILE, "utf8"));
  const tickers = new Set();
  (data.sections || []).forEach(s => (s.items || []).forEach(i => { if (i.ticker) tickers.add(i.ticker); }));
  return [...tickers];
}

// Última fila registrada estrictamente antes de hoy, por ticker — mismo
// criterio que buildPrevSessionMap() en portfolio.html, pero leído del
// propio snapshot (no de portfolio.json.lastSessionSnapshot) para que este
// script sea autosuficiente y no dependa de que el navegador haya corrido.
function buildPrevRowMap(rows, today) {
  const map = {};
  for (const r of rows) {
    if (!r.ticker || !r.date || r.date >= today) continue;
    const cur = map[r.ticker];
    if (!cur || r.date > cur.date) map[r.ticker] = r;
  }
  return map;
}

function printReport() {
  const rows = readJsonlRows(SNAPSHOT_FILE);
  if (!rows.length) { console.log("Sin datos todavía en", SNAPSHOT_FILE); return; }
  const dates = [...new Set(rows.map(r => r.date))].sort();
  const tickers = new Set(rows.map(r => r.ticker));
  const withFlow = rows.filter(r => r.flowScore != null).length;
  console.log(`portfolio_daily_snapshot.jsonl — ${rows.length} filas`);
  console.log(`  rango de fechas: ${dates[0]} -> ${dates[dates.length - 1]} (${dates.length} días distintos)`);
  console.log(`  tickers distintos: ${tickers.size}`);
  console.log(`  filas con flowScore no-null: ${withFlow}/${rows.length} (${(withFlow / rows.length * 100).toFixed(1)}%)`);
}

async function main() {
  if (REPORT_ONLY) { printReport(); return; }

  const today = todayISO();
  const tickers = TICKERS_OVERRIDE ?? loadPortfolioTickers();
  console.log(`portfolio_daily_snapshot: ${tickers.length} tickers, fecha=${today}, dry_run=${DRY_RUN}`);

  const existingRows = readJsonlRows(SNAPSHOT_FILE);
  const existingKeys = new Set(existingRows.map(r => `${r.date}|${r.ticker}`));
  const prevByTicker = buildPrevRowMap(existingRows, today);

  const pending = tickers.filter(t => !existingKeys.has(`${today}|${t}`));
  const alreadyDone = tickers.length - pending.length;
  if (alreadyDone > 0) console.log(`  ${alreadyDone} tickers ya capturados hoy — se omiten (dedup)`);

  const newRows = [];
  const failures = [];

  for (let i = 0; i < pending.length; i += BATCH_SIZE) {
    const batch = pending.slice(i, i + BATCH_SIZE);
    const results = await Promise.allSettled(batch.map(t => buildQuoteData(t)));
    results.forEach((res, idx) => {
      const ticker = batch[idx];
      if (res.status === "rejected") {
        failures.push({ ticker, error: res.reason?.message ?? String(res.reason) });
        return;
      }
      const data = res.value;
      const prev = prevByTicker[ticker] ?? null;
      const flowScore = computeFlowScore(data);
      const earlyFlow = computeEarlyFlowScore(data, prev);
      newRows.push({ date: today, ticker, ...data, flowScore, earlyFlow });
    });
    if (i + BATCH_SIZE < pending.length) await new Promise(r => setTimeout(r, BATCH_GAP_MS));
  }

  console.log(`  capturados: ${newRows.length}/${pending.length}`);
  if (failures.length) {
    console.log(`  fallidos: ${failures.length}`);
    failures.forEach(f => console.log(`    ${f.ticker}: ${f.error}`));
  }

  if (DRY_RUN) {
    console.log("--dry-run: no se ha escrito nada.");
    return;
  }
  if (!newRows.length) { console.log("Nada nuevo que escribir."); return; }

  fs.mkdirSync(path.dirname(SNAPSHOT_FILE), { recursive: true });
  const lines = newRows.map(r => JSON.stringify(r)).join("\n") + "\n";
  fs.appendFileSync(SNAPSHOT_FILE, lines);
  console.log(`Escritas ${newRows.length} filas nuevas en ${path.relative(REPO_ROOT, SNAPSHOT_FILE)}`);
}

main().catch(err => {
  console.error("portfolio_daily_snapshot: fallo no controlado:", err);
  process.exit(1);
});
