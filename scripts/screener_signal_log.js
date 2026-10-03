#!/usr/bin/env node
// ── Registro diario de candidatos del Screener (+ backfill) ─────────────────
//
// Origen (2026-10-03): el Screener y los filtros se usan a diario pero nada
// medía si sus candidatos acababan funcionando — misma situación que tenía el
// PCS antes del diagnóstico de CFL. Este script guarda, por fecha y por FILTRO
// INDIVIDUAL (no por combinación: cada filtro se evalúa en solitario, así se
// puede ver cuál aporta), qué tickers eran candidatos. El análisis de
// rendimiento posterior vive en scripts/screener_signal_report.js y sale de
// la propia serie de precios de portfolio_daily_snapshot.jsonl — no hace falta
// ningún fetch extra por candidato.
//
// Reutiliza EXACTAMENTE el mismo motor que screeners.html (shared/screener-lib.js
// + shared/flow-state-lib.js): una fila del snapshot diario es la misma salida
// de buildQuoteData() que sirve /api/quote/:symbol, y `_flow` se calcula con
// el historial hasta esa fecha. Así el registro no puede divergir de lo que
// el usuario ve en pantalla.
//
// Backfill: la primera ejecución procesa todas las fechas del snapshot
// (desde 2026-08-20). Después, solo las fechas nuevas. Estado en
// docs/data/screener_signal_log_state.json (distingue "fecha sin candidatos"
// de "fecha no procesada").
//
// Fuerza relativa de "Continuación": necesita m1 de ^GSPC en cada fecha. Se
// calcula de la serie diaria de Yahoo; si no se puede obtener, el filtro de
// Continuación se OMITE ese día (nunca se evalúa con benchmark nulo, que lo
// haría fallar siempre y registraría "ningún candidato" falsamente).
//
// CLI:
//   node scripts/screener_signal_log.js            # procesa fechas pendientes
//   node scripts/screener_signal_log.js --dry-run  # no escribe nada
//   node scripts/screener_signal_log.js --rebuild  # reprocesa todo desde cero

const fs   = require('fs');
const path = require('path');
const { SCREENERS, runScreenerFilters } = require('../shared/screener-lib.js');
const fsl = require('../shared/flow-state-lib.js');
const { fetchYahooChartRaw } = require('../shared/quote-lib.js');

const ROOT = path.join(__dirname, '..');
const SNAPSHOT = path.join(ROOT, 'docs', 'data', 'portfolio_daily_snapshot.jsonl');
const PORTFOLIO = path.join(ROOT, 'portfolio.json');
const OUT = path.join(ROOT, 'docs', 'data', 'screener_signal_log.jsonl');
const STATE = path.join(ROOT, 'docs', 'data', 'screener_signal_log_state.json');

// Mismos campos que screeners.html (FLOW_HISTORY_FIELDS): lo que necesita
// shared/flow-state-lib.js para reconstruir la serie por ticker.
const FLOW_HISTORY_FIELDS = ['date', 'flowScore', 'rsi', 'konc_alignment', 'macdHist', 'macdHistDelta1', 'atrPct', 'price', 'm1',
  'konc_d_state', 'konc_3d_state', 'konc_w_state'];

const args = process.argv.slice(2);
const DRY = args.includes('--dry-run');
const REBUILD = args.includes('--rebuild');

function readJsonl(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(Boolean);
}

// m1 de ^GSPC por fecha (misma definición que quote-lib: ret(21) sobre cierres).
async function benchmarkM1ByDate() {
  try {
    const r = await fetchYahooChartRaw('^GSPC', '2y', '1d');
    const res = r.result;
    if (!r.ok || !res?.timestamp) return null;
    const closes = res.indicators.quote[0].close;
    const dates = res.timestamp.map(t => new Date(t * 1000).toISOString().slice(0, 10));
    const clean = [];
    dates.forEach((d, i) => { if (closes[i] != null) clean.push({ d, c: closes[i] }); });
    return d => {
      let idx = -1;
      for (let i = clean.length - 1; i >= 0; i--) { if (clean[i].d <= d) { idx = i; break; } }
      if (idx < 21) return null;
      return +((clean[idx].c / clean[idx - 21].c - 1) * 100).toFixed(2);
    };
  } catch (e) { return null; }
}

async function main() {
  const rows = readJsonl(SNAPSHOT);
  if (!rows.length) { console.error('Snapshot vacío'); process.exit(1); }
  const portfolio = JSON.parse(fs.readFileSync(PORTFOLIO, 'utf8'));
  const membership = fsl.fslBuildBasketMembership(portfolio.sections || []);
  const basketToTickers = fsl.fslBasketToTickers(membership);

  const byTicker = {};
  rows.forEach(r => {
    if (!r.ticker || !r.date) return;
    (byTicker[r.ticker] = byTicker[r.ticker] || []).push(r);
  });
  Object.values(byTicker).forEach(a => a.sort((x, y) => x.date.localeCompare(y.date)));
  const allDates = [...new Set(rows.map(r => r.date))].sort();

  let state = { processed_dates: [], skipped: {}, coverage: {} };
  if (!REBUILD && fs.existsSync(STATE)) { try { state = JSON.parse(fs.readFileSync(STATE, 'utf8')); } catch (e) { /* estado ilegible → reprocesa */ } }
  const done = new Set(state.processed_dates);
  const pending = allDates.filter(d => !done.has(d));
  if (!pending.length) { console.log('Nada pendiente. Fechas procesadas:', done.size); return; }

  const bm = await benchmarkM1ByDate();
  if (!bm) console.log('⚠ no se pudo obtener ^GSPC: el filtro de Continuación se omite en estas fechas');

  const existing = REBUILD ? [] : readJsonl(OUT);
  const seen = new Set(existing.map(r => `${r.date}|${r.filter}|${r.ticker}`));
  const newRows = [];
  const skipped = { ...(state.skipped || {}) };
  const coverage = { ...(state.coverage || {}) };  // coverage[date][filtro] = nº de tickers EVALUABLES ese día

  for (const date of pending) {
    // Historial por ticker hasta `date` (inclusive), una fila por fecha.
    const history = {};
    const quotes = {};
    Object.entries(byTicker).forEach(([tk, arr]) => {
      const upto = arr.filter(r => r.date <= date);
      if (!upto.length || upto[upto.length - 1].date !== date) return; // sin fila ese día → no está en el universo de esa fecha
      history[tk] = upto.map(r => { const o = {}; FLOW_HISTORY_FIELDS.forEach(k => { o[k] = r[k] !== undefined ? r[k] : null; }); return o; });
      quotes[tk] = { ...upto[upto.length - 1] };
    });
    const benchmarkM1 = bm ? bm(date) : null;
    const ctx = { membership, basketToTickers, history, benchmarkM1 };
    Object.keys(quotes).forEach(tk => { quotes[tk]._flow = fsl.fslEvaluateTicker(tk, ctx); });

    let n = 0;
    for (const screener of SCREENERS) {
      for (const f of screener.filters) {
        if (f.id === 'flow_continuacion' && benchmarkM1 == null) {
          (skipped[date] = skipped[date] || []).push(f.id);
          continue;
        }
        const all = runScreenerFilters(screener, new Set([f.id]), quotes);
        // Evaluables = tickers con dato suficiente para el filtro ese día. Campos
        // que no existían aún en las filas antiguas (ej. macdHistRecent, añadido el
        // 2026-09-22) dan 'no_data': el filtro NO PUDO evaluarse, que no es lo mismo
        // que 'sin candidatos'. Se guarda la cobertura para que el informe no
        // confunda una cosa con la otra.
        const evaluable = all.filter(r => r.results[f.id].status !== 'no_data').length;
        (coverage[date] = coverage[date] || {})[f.id] = evaluable;
        if (evaluable === 0) { (skipped[date] = skipped[date] || []).push(f.id + ':sin_datos'); continue; }
        const res = all.filter(r => r.pass);
        for (const r of res) {
          const key = `${date}|${f.id}|${r.ticker}`;
          if (seen.has(key)) continue;
          seen.add(key);
          const fr = r.results[f.id];
          newRows.push({ date, screener: screener.id, filter: f.id, ticker: r.ticker, status: fr.status,
            sort_value: fr.sortValue ?? null, price: quotes[r.ticker].price ?? null, universe_n: Object.keys(quotes).length });
          n++;
        }
      }
    }
    done.add(date);
    console.log(`  ${date}: universo ${Object.keys(quotes).length} · candidatos registrados ${n}${benchmarkM1 == null ? ' (sin benchmark)' : ''}`);
  }

  if (DRY) { console.log(`[dry-run] se escribirían ${newRows.length} filas`); return; }
  const all = existing.concat(newRows);
  fs.writeFileSync(OUT, all.map(r => JSON.stringify(r)).join('\n') + (all.length ? '\n' : ''));
  fs.writeFileSync(STATE, JSON.stringify({ processed_dates: [...done].sort(), skipped, coverage, updated_at: new Date().toISOString() }, null, 2));
  console.log(`OK — ${newRows.length} filas nuevas (${all.length} en total), ${done.size} fechas procesadas`);
}

main().catch(e => { console.error(e); process.exit(1); });
