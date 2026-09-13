#!/usr/bin/env node
// ── Market Tracker Daily Snapshot ────────────────────────────────────────
// Captura TODOS los datos que index.html ("Market Tracker") muestra —
// indicadores macro/ciclo + universo amplio de índices/sectores/regiones/
// materias primas — de forma independiente de si alguien abre el dashboard
// ese día. Mismo motivo y mismo patrón que portfolio_daily_snapshot.js
// (2026-08-20): antes de esto, la única "captura" era el propio navegador
// generando el bundle para LLM manualmente.
//
// Reutiliza shared/quote-lib.js (buildQuoteData), shared/flow-score.js
// (computeFlowScore/computeEarlyFlowScore) y shared/market-macro.js
// (STATUS/computeUraniumScore) — las mismas funciones que index.html carga
// como <script> — para que esta captura nunca pueda divergir del dashboard.
// FRED se llama directamente (mismo endpoint/lógica que /api/fred/:series y
// /api/fred3 en server.js, duplicado a propósito porque este script corre
// standalone en el pipeline, sin un server.js activo al que pedírselo).
//
// Dos ficheros de salida (universos distintos, misma razón que separar
// portfolio_daily_snapshot.jsonl de shadow_picks.jsonl):
//   docs/data/market_equities_daily_snapshot.jsonl — una fila por
//     ticker/día, dedup por (date, ticker). Mismo shape que
//     portfolio_daily_snapshot.jsonl (buildQuoteData crudo + flowScore/
//     earlyFlow), pero para el universo de SECTIONS (índices, sectores,
//     regiones, uranio, energía) en vez de portfolio.json.
//   docs/data/market_macro_daily_snapshot.jsonl — una fila por
//     indicador/día, dedup por (date, id). Incluye los 13 MACRO_ITEMS +
//     2 derivados (uranium_regime_score, brent_wti_spread).
//
// Fuera de alcance a propósito (documentado, no descartado en silencio):
// los 5 campos manuales/OilPriceAPI de las secciones de energía
// (u3o8_spot, uranium_lt, wcs_spot, jkm, hcc_benchmark) — u3o8_spot/
// uranium_lt viven SOLO en localStorage del navegador del usuario, sin
// fuente server-side alguna; wcs_spot/jkm/hcc_benchmark necesitarían
// OILPRICE_API_KEY como GitHub Secret (hoy solo está en el .env local, no
// wireado a ningún step del pipeline) — añadir esa pieza queda para si se
// decide que aporta valor al análisis automatizado.
//
// CLI:
//   node scripts/market_daily_snapshot.js              # captura real
//   node scripts/market_daily_snapshot.js --dry-run     # no escribe nada
//   node scripts/market_daily_snapshot.js --report      # resume los jsonl existentes

const fs    = require("fs");
const path  = require("path");
require("dotenv").config({ path: path.join(__dirname, "..", ".env") });
const fetch = require("node-fetch");
const { buildQuoteData } = require("../shared/quote-lib.js");
const { computeFlowScore, computeEarlyFlowScore } = require("../shared/flow-score.js");
const { STATUS, computeUraniumScore } = require("../shared/market-macro.js");

const REPO_ROOT    = path.join(__dirname, "..");
const EQUITY_FILE  = path.join(REPO_ROOT, "docs", "data", "market_equities_daily_snapshot.jsonl");
const MACRO_FILE   = path.join(REPO_ROOT, "docs", "data", "market_macro_daily_snapshot.jsonl");

const FRED_API_KEY = process.env.FRED_API_KEY;
const BATCH_SIZE    = 8;
const BATCH_GAP_MS  = 300;
const FRED_GAP_MS   = 300;

const args = process.argv.slice(2);
const DRY_RUN     = args.includes("--dry-run");
const REPORT_ONLY = args.includes("--report");

// ── Datos — copiados literalmente de MACRO_ITEMS/SECTIONS en index.html.
// Mismo riesgo de drift que cualquier duplicación en este proyecto (ver
// calcCMF) — si se añade/quita un ticker o macro item en index.html, hay
// que replicarlo aquí. No se extrajo a un módulo compartido porque estos
// arrays mezclan funciones de formato JSX-friendly (fmt/dFmt) que no
// aportan nada a un script de captura — solo se necesitan id/ticker/series/
// fetch/type/src/monthly/weekly, que sí se copian tal cual.
const MACRO_ITEMS = [
  { id:"vix",   name:"VIX (Fear Index)",        src:"Yahoo", type:"vix",            fetch:"yahoo", ticker:"^VIX" },
  { id:"dxy",   name:"Dollar Index (DXY)",      src:"Yahoo", type:"dxy",            fetch:"yahoo", ticker:"DX-Y.NYB" },
  { id:"tnx",   name:"10Y Treasury Yield",      src:"Yahoo", type:"yield_10y",      fetch:"yahoo", ticker:"^TNX" },
  { id:"dfii10",name:"10Y TIPS Real Yield",     src:"FRED",  type:"real_yield_10y", fetch:"fred",  series:"DFII10" },
  { id:"irx",   name:"3M T-Bill Yield",         src:"Yahoo", type:"short_rate",     fetch:"yahoo", ticker:"^IRX" },
  { id:"c3m",   name:"Yield Curve (10Y-3M)",    src:"FRED",  type:"curve_pct",      fetch:"fred",  series:"T10Y3M" },
  { id:"c2y",   name:"Yield Curve (10Y-2Y)",    src:"FRED",  type:"curve_pct",      fetch:"fred",  series:"T10Y2Y" },
  { id:"hy",    name:"HY Credit Spread",        src:"FRED",  type:"hy_spread",      fetch:"fred",  series:"BAMLH0A0HYM2" },
  { id:"ig",    name:"IG Credit Spread",        src:"FRED",  type:"ig_spread",      fetch:"fred",  series:"BAMLC0A0CM" },
  { id:"bei",   name:"5Y Breakeven Inflation",  src:"FRED",  type:"breakeven",      fetch:"fred",  series:"T5YIE" },
  { id:"pmi",   name:"Prod. Industrial (INDPRO)", src:"FRED", type:"pmi",           fetch:"fred",  series:"INDPRO", monthly:true },
  { id:"m2",    name:"US M2 Money Supply",      src:"FRED",  type:"m2",             fetch:"fred",  series:"WM2NS",  weekly:true },
  { id:"walcl", name:"Fed Balance Sheet",       src:"FRED",  type:"fed_bs",         fetch:"fred",  series:"WALCL",  weekly:true },
  { id:"netliq",name:"Fed Net Liquidity*",      src:"FRED",  type:"net_liq",        fetch:"fred3", series:["WALCL","RRPONTSYD","WTREGEN"] },
];

const SECTIONS = [
  { id: "MAJOR INDICES", items: [
    { name: "S&P 500", ticker: "^GSPC" }, { name: "MSCI World", ticker: "URTH" },
    { name: "NASDAQ Composite", ticker: "^IXIC" }, { name: "Euro STOXX 50", ticker: "FEZ" },
    { name: "MSCI Emerging Markets", ticker: "EEM" }, { name: "Russell 2000", ticker: "IWM" },
    { name: "S&P 500 Equal Weight", ticker: "RSP" },
  ]},
  { id: "MAG 6", items: [
    { name: "NVIDIA", ticker: "NVDA" }, { name: "Apple", ticker: "AAPL" },
    { name: "Alphabet", ticker: "GOOGL" }, { name: "Microsoft", ticker: "MSFT" },
    { name: "Amazon", ticker: "AMZN" }, { name: "Meta Platforms", ticker: "META" },
  ]},
  { id: "BONDS / COMMODITIES", items: [
    { name: "Long Duration US Bonds", ticker: "TLT" }, { name: "Oil (Brent)", ticker: "BZ=F" },
    { name: "Gold", ticker: "GC=F" }, { name: "Silver", ticker: "SI=F" },
    { name: "Bitcoin", ticker: "BTC-USD" },
  ]},
  { id: "EUROPE", items: [
    { name: "United Kingdom (FTSE 100)", ticker: "^FTSE" }, { name: "France (CAC 40)", ticker: "^FCHI" },
    { name: "Germany (DAX)", ticker: "^GDAXI" }, { name: "Netherlands (AEX)", ticker: "^AEX" },
    { name: "Spain (IBEX 35)", ticker: "^IBEX" }, { name: "Italy (FTSE MIB)", ticker: "FTSEMIB.MI" },
  ]},
  { id: "ASIA", items: [
    { name: "Japan", ticker: "EWJ" }, { name: "South Korea", ticker: "EWY" },
    { name: "India", ticker: "INDA" }, { name: "China", ticker: "MCHI" }, { name: "Hong Kong", ticker: "EWH" },
  ]},
  { id: "LATAM", items: [
    { name: "Brazil", ticker: "EWZ" }, { name: "Mexico", ticker: "EWW" }, { name: "Argentina", ticker: "ARGT" },
  ]},
  { id: "US SECTORS", items: [
    { name: "Technology", ticker: "XLK" }, { name: "Healthcare", ticker: "XLV" },
    { name: "Financials", ticker: "XLF" }, { name: "Consumer Discretionary", ticker: "XLY" },
    { name: "Communication Services", ticker: "XLC" }, { name: "Industrials", ticker: "XLI" },
    { name: "Consumer Staples", ticker: "XLP" }, { name: "Energy", ticker: "XLE" },
    { name: "Utilities", ticker: "XLU" }, { name: "Real Estate", ticker: "XLRE" },
  ]},
  { id: "EU SECTORS", items: [
    { name: "EU Banks", ticker: "EXV1.DE" }, { name: "EU Healthcare", ticker: "IQQH.DE" },
    { name: "EU Industrials", ticker: "EXV6.DE" }, { name: "EU Energy", ticker: "EXH1.DE" },
    { name: "EU Technology", ticker: "EXH4.DE" }, { name: "EU Consumer Staples", ticker: "EXV5.DE" },
    { name: "EU Telecoms", ticker: "EXV2.DE" }, { name: "EU Utilities", ticker: "EXH7.DE" },
    { name: "EU Materials", ticker: "EXH8.DE" }, { name: "EU Real Estate", ticker: "IPRP.AS" },
  ]},
  { id: "URANIO", items: [
    { name: "Sprott Uranium Miners ETF (URNM)", ticker: "URNM" }, { name: "Uranium One Group (U-U.TO)", ticker: "U-U.TO" },
    { name: "Cameco Corp (CCJ)", ticker: "CCJ" }, { name: "NexGen Energy (NXE)", ticker: "NXE" },
    { name: "Denison Mines (DNN)", ticker: "DNN" }, { name: "Centrus Energy (LEU)", ticker: "LEU" },
  ]},
  { id: "ENERGÍA FÍSICA / SPREADS", items: [
    { name: "Brent Crude — BZ=F (front month)", ticker: "BZ=F" }, { name: "WTI Crude — CL=F (front month)", ticker: "CL=F" },
  ]},
  { id: "GAS NATURAL", items: [
    { name: "Natural Gas Henry Hub — NG=F", ticker: "NG=F" }, { name: "TTF Natural Gas (ICE) — TTF=F", ticker: "TTF=F" },
  ]},
  { id: "CARBÓN MET (PROXIES)", items: [
    { name: "Warrior Met Coal (HCC)", ticker: "HCC" }, { name: "Alpha Metallurgical (AMR)", ticker: "AMR" },
    { name: "Peabody Energy (BTU)", ticker: "BTU" },
  ]},
];

// ── FRED — mismo endpoint/lógica que /api/fred/:series y /api/fred3 en
// server.js, duplicado aquí porque este script corre standalone.
async function fetchFred(seriesId, { monthly = false, weekly = false } = {}) {
  if (!FRED_API_KEY) throw new Error("FRED_API_KEY no configurada");
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}&api_key=${FRED_API_KEY}&sort_order=desc&limit=300&file_type=json`;
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await r.json();
  if (data.error_message) throw new Error(data.error_message);
  const obs = (data.observations || []).filter(o => o.value !== ".");
  if (!obs.length) throw new Error("No data");
  const val = i => obs[i] ? parseFloat(obs[i].value) : null;
  return {
    current: val(0), date: obs[0]?.date,
    v1w: weekly ? val(1)  : monthly ? null    : val(5),
    v1m: weekly ? val(4)  : monthly ? val(1)  : val(21),
    v3m: weekly ? val(13) : monthly ? val(3)  : val(65),
    v6m: weekly ? val(26) : monthly ? val(6)  : val(130),
    v1y: weekly ? val(52) : monthly ? val(12) : val(252),
  };
}

async function fetchFred3(seriesIds) {
  if (!FRED_API_KEY) throw new Error("FRED_API_KEY no configurada");
  const perSeries = [];
  for (const sid of seriesIds) {
    const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${sid}&api_key=${FRED_API_KEY}&sort_order=desc&limit=100&file_type=json`;
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await r.json();
    const rows = (data.observations || []).filter(o => o.value !== ".")
      .map(o => ({ date: o.date, v: parseFloat(o.value) })).reverse();
    perSeries.push(rows);
    await new Promise(res => setTimeout(res, FRED_GAP_MS));
  }
  const sorted = perSeries.map(arr => [...arr].sort((a, b) => a.date.localeCompare(b.date)));
  function nearestPrior(arr, targetDate) {
    let lo = 0, hi = arr.length - 1, found = null;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid].date <= targetDate) { found = arr[mid].v; lo = mid + 1; } else hi = mid - 1;
    }
    return found;
  }
  const anchor = sorted[0];
  if (!anchor.length) throw new Error("No data for anchor series");
  const combined = anchor.map(({ date, v: v0 }) => {
    const v1 = nearestPrior(sorted[1], date) ?? 0;
    const v2 = sorted[2] ? (nearestPrior(sorted[2], date) ?? 0) : 0;
    return { date, v: v0 - v1 - v2 };
  }).reverse();
  const val = i => combined[i]?.v ?? null;
  return { current: val(0), date: combined[0].date, v1w: val(1), v1m: val(4), v3m: val(13), v6m: val(26), v1y: val(52) };
}

function readJsonlRows(file) {
  if (!fs.existsSync(file)) return [];
  const rows = [];
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const t = line.trim();
    if (!t) continue;
    try { rows.push(JSON.parse(t)); } catch { /* línea corrupta — se ignora */ }
  }
  return rows;
}

function appendJsonl(file, rows) {
  if (!rows.length) return;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.appendFileSync(file, rows.map(r => JSON.stringify(r)).join("\n") + "\n");
}

function todayISO() { return new Date().toISOString().slice(0, 10); }

// Última fila registrada estrictamente antes de hoy, por ticker — mismo
// criterio que portfolio_daily_snapshot.js, para earlyFlow.
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
  const eq = readJsonlRows(EQUITY_FILE);
  const macro = readJsonlRows(MACRO_FILE);
  if (!eq.length && !macro.length) { console.log("Sin datos todavía."); return; }
  if (eq.length) {
    const dates = [...new Set(eq.map(r => r.date))].sort();
    const tickers = new Set(eq.map(r => r.ticker));
    console.log(`market_equities_daily_snapshot.jsonl — ${eq.length} filas, ${tickers.size} tickers, ` +
      `${dates[0]} -> ${dates[dates.length - 1]} (${dates.length} días)`);
  }
  if (macro.length) {
    const dates = [...new Set(macro.map(r => r.date))].sort();
    const ids = new Set(macro.map(r => r.id));
    console.log(`market_macro_daily_snapshot.jsonl — ${macro.length} filas, ${ids.size} indicadores, ` +
      `${dates[0]} -> ${dates[dates.length - 1]} (${dates.length} días)`);
  }
}

async function main() {
  if (REPORT_ONLY) { printReport(); return; }

  const today = todayISO();

  const tickerMeta = new Map(); // ticker -> {name, sections: []}
  SECTIONS.forEach(sec => sec.items.forEach(({ name, ticker }) => {
    if (!tickerMeta.has(ticker)) tickerMeta.set(ticker, { name, sections: [] });
    tickerMeta.get(ticker).sections.push(sec.id);
  }));
  const macroYahooTickers = [...new Set(MACRO_ITEMS.filter(i => i.fetch === "yahoo").map(i => i.ticker))];
  const allTickers = [...new Set([...tickerMeta.keys(), ...macroYahooTickers])];

  console.log(`market_daily_snapshot: ${allTickers.length} tickers (equities+macro), fecha=${today}, dry_run=${DRY_RUN}`);

  const quoteMap = {};
  const quoteFailures = [];
  for (let i = 0; i < allTickers.length; i += BATCH_SIZE) {
    const batch = allTickers.slice(i, i + BATCH_SIZE);
    const results = await Promise.allSettled(batch.map(t => buildQuoteData(t)));
    results.forEach((res, idx) => {
      const ticker = batch[idx];
      if (res.status === "rejected") quoteFailures.push({ ticker, error: res.reason?.message ?? String(res.reason) });
      else quoteMap[ticker] = res.value;
    });
    if (i + BATCH_SIZE < allTickers.length) await new Promise(r => setTimeout(r, BATCH_GAP_MS));
  }
  console.log(`  quotes: ${Object.keys(quoteMap).length}/${allTickers.length} ok`);
  if (quoteFailures.length) quoteFailures.forEach(f => console.log(`    fallo quote ${f.ticker}: ${f.error}`));

  // ── Equity rows ──────────────────────────────────────────────────────
  const existingEquityRows = readJsonlRows(EQUITY_FILE);
  const existingEquityKeys = new Set(existingEquityRows.map(r => `${r.date}|${r.ticker}`));
  const prevByTicker = buildPrevRowMap(existingEquityRows, today);

  const newEquityRows = [];
  for (const [ticker, meta] of tickerMeta) {
    if (existingEquityKeys.has(`${today}|${ticker}`)) continue;
    const data = quoteMap[ticker];
    if (!data) continue; // fallo de quote, ya logueado arriba
    const prev = prevByTicker[ticker] ?? null;
    const flowScore = computeFlowScore(data);
    const earlyFlow = computeEarlyFlowScore(data, prev);
    newEquityRows.push({ date: today, ticker, name: meta.name, sections: meta.sections, ...data, flowScore, earlyFlow });
  }
  console.log(`  equity rows nuevas: ${newEquityRows.length}`);

  // ── Macro rows ───────────────────────────────────────────────────────
  const existingMacroRows = readJsonlRows(MACRO_FILE);
  const existingMacroKeys = new Set(existingMacroRows.map(r => `${r.date}|${r.id}`));

  const newMacroRows = [];
  const macroFailures = [];
  for (const item of MACRO_ITEMS) {
    if (existingMacroKeys.has(`${today}|${item.id}`)) continue;
    try {
      let raw;
      if (item.fetch === "yahoo") {
        const data = quoteMap[item.ticker];
        if (!data) throw new Error("quote no disponible");
        raw = { current: data.price, date: data.asOf ? data.asOf.slice(0, 10) : null,
                 v1w: data.v1w, v1m: data.v1m, v3m: data.v3m, v6m: data.v6m, v1y: data.v1y };
      } else if (item.fetch === "fred") {
        raw = await fetchFred(item.series, { monthly: !!item.monthly, weekly: !!item.weekly });
        await new Promise(r => setTimeout(r, FRED_GAP_MS));
      } else if (item.fetch === "fred3") {
        raw = await fetchFred3(item.series);
      } else {
        throw new Error(`fetch type desconocido: ${item.fetch}`);
      }
      const cur = raw.current;
      const dW  = item.monthly ? null : (cur != null && raw.v1w != null ? cur - raw.v1w : null);
      const dM  = cur != null && raw.v1m != null ? cur - raw.v1m : null;
      const dM3 = cur != null && raw.v3m != null ? cur - raw.v3m : null;
      const dM6 = cur != null && raw.v6m != null ? cur - raw.v6m : null;
      const dY  = cur != null && raw.v1y != null ? cur - raw.v1y : null;
      const st  = cur != null && STATUS[item.type] ? STATUS[item.type](cur, dW, dM, dY) : null;
      newMacroRows.push({
        date: today, id: item.id, name: item.name, source: item.src, value: cur,
        value_date: raw.date ?? null,
        delta_1w: dW, delta_1m: dM, delta_3m: dM3, delta_6m: dM6, delta_1y: dY,
        reading: st ? st[0] : null,
      });
    } catch (e) {
      macroFailures.push({ id: item.id, error: e.message });
    }
  }

  // Derivados — uranium_regime_score / brent_wti_spread, mismo espacio de
  // dedup (date, id) que el resto de filas macro.
  if (!existingMacroKeys.has(`${today}|uranium_regime_score`)) {
    const u = computeUraniumScore(quoteMap);
    if (u) {
      newMacroRows.push({ date: today, id: "uranium_regime_score", name: "Uranium Regime Score", source: "derived",
        value: u.score, value_date: today, delta_1w: null, delta_1m: null, delta_3m: null, delta_6m: null, delta_1y: null,
        reading: u.label, factors: u.pts });
    }
  }
  if (!existingMacroKeys.has(`${today}|brent_wti_spread`)) {
    const brent = quoteMap["BZ=F"], wti = quoteMap["CL=F"];
    if (brent?.price != null && wti?.price != null) {
      newMacroRows.push({ date: today, id: "brent_wti_spread", name: "Brent - WTI Spread", source: "derived",
        value: +(brent.price - wti.price).toFixed(2), value_date: today,
        delta_1w: null, delta_1m: null, delta_3m: null, delta_6m: null, delta_1y: null, reading: null });
    }
  }

  console.log(`  macro rows nuevas: ${newMacroRows.length}`);
  if (macroFailures.length) macroFailures.forEach(f => console.log(`    fallo macro ${f.id}: ${f.error}`));

  if (DRY_RUN) { console.log("--dry-run: no se ha escrito nada."); return; }

  appendJsonl(EQUITY_FILE, newEquityRows);
  appendJsonl(MACRO_FILE, newMacroRows);
  console.log(`Escritas ${newEquityRows.length} filas en ${path.relative(REPO_ROOT, EQUITY_FILE)} ` +
    `y ${newMacroRows.length} filas en ${path.relative(REPO_ROOT, MACRO_FILE)}`);
}

main().catch(err => {
  console.error("market_daily_snapshot: fallo no controlado:", err);
  process.exit(1);
});
