#!/usr/bin/env node
// ── Informe de rendimiento posterior de los candidatos del Screener ─────────
//
// Lee docs/data/screener_signal_log.jsonl (scripts/screener_signal_log.js) y
// mide, por FILTRO, qué hicieron los candidatos después — usando la serie de
// precios del propio portfolio_daily_snapshot.jsonl (sin ningún fetch).
//
// Decisiones de método (fijadas aquí, no a posteriori sobre los resultados):
//  - Evento independiente = primera aparición de un ticker en un filtro tras
//    ≥10 días naturales sin ser candidato de ESE filtro. Un ticker que lleva
//    una semana seguida marcado es un solo evento, no siete: sin esto el n
//    sale inflado y cualquier intervalo de confianza engaña (mismo criterio
//    que el resto del proyecto, que ya se quemó con filas duplicadas en CFL).
//  - Horizontes en días NATURALES (7/14/30): el snapshot tiene filas también
//    en fin de semana, con el último cierre repetido. Un horizonte solo
//    cuenta si ya ha madurado (existe una fila en o después de fecha+h).
//  - Referencia = mediana del retorno de TODO el universo de ese día al mismo
//    horizonte (no SPY: universo propio, sin dependencia externa). "Exceso" =
//    retorno del evento − esa mediana.
//  - Con n pequeño no se concluye nada: por debajo de MIN_N eventos
//    madurados el informe lo marca "no concluyente" y no calcula veredicto.
//  - NO se corrige por comparaciones múltiples ni se separa dev/test: este es
//    un seguimiento descriptivo, no una validación. Para promover un filtro a
//    algo operativo haría falta preregistro (ver wiki/PREREGISTRO_*).
//
// CLI:
//   node scripts/screener_signal_report.js          # imprime y escribe docs/data/screener_signal_report.json
//   node scripts/screener_signal_report.js --no-write

const fs   = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const SNAPSHOT = path.join(ROOT, 'docs', 'data', 'portfolio_daily_snapshot.jsonl');
const LOG = path.join(ROOT, 'docs', 'data', 'screener_signal_log.jsonl');
const STATE = path.join(ROOT, 'docs', 'data', 'screener_signal_log_state.json');
const OUT = path.join(ROOT, 'docs', 'data', 'screener_signal_report.json');
const FIRED_LOG = path.join(ROOT, 'docs', 'data', 'special_situations_fired.jsonl');

const HORIZONS = [7, 14, 30];
const COOLDOWN_DAYS = 10;
const MIN_N = 30;

function readJsonl(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(Boolean);
}
const dayMs = 86400000;
const addDays = (d, n) => new Date(Date.parse(d) + n * dayMs).toISOString().slice(0, 10);
const daysBetween = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / dayMs);
const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
const r2 = v => v == null ? null : Math.round(v * 100) / 100;

// Herramientas de retorno posterior sobre la serie de precios del snapshot.
// Exportadas: scripts/ibkr_decision_journal.js usa exactamente las mismas, para
// que "retorno a 7/14/30 días" signifique lo mismo en el informe del screener
// y en el diario de operaciones reales.
function makeTools(snap) {
  const lastDate = snap.reduce((d, r) => (r.date > d ? r.date : d), '');

  // price[ticker] = [{date, price}] asc
  const series = {};
  snap.forEach(r => { if (r.ticker && r.date && typeof r.price === 'number' && r.price > 0) (series[r.ticker] = series[r.ticker] || []).push({ date: r.date, price: r.price }); });
  Object.values(series).forEach(a => a.sort((x, y) => x.date.localeCompare(y.date)));

  // Precio en la fecha (última fila ≤ fecha) y precio al horizonte (primera fila ≥ fecha+h).
  const priceAt = (tk, date) => { const a = series[tk]; if (!a) return null; let p = null; for (const x of a) { if (x.date <= date) p = x; else break; } return p ? p.price : null; };
  const priceAtOrAfter = (tk, date) => { const a = series[tk]; if (!a) return null; for (const x of a) if (x.date >= date) return x; return null; };
  // Retorno % del ticker entre `date` y `date+h` (solo si el horizonte ha madurado).
  const fwd = (tk, date, h) => {
    const target = addDays(date, h);
    if (target > lastDate) return null;
    const p0 = priceAt(tk, date); const x1 = priceAtOrAfter(tk, target);
    if (p0 == null || !x1 || daysBetween(target, x1.date) > 4) return null;   // hueco de datos > 4 días → no se fabrica
    return (x1.price / p0 - 1) * 100;
  };

  // Mediana del universo por (fecha, horizonte): se calcula bajo demanda y se cachea.
  const tickersByDate = {};
  snap.forEach(r => { (tickersByDate[r.date] = tickersByDate[r.date] || []).push(r.ticker); });
  const uniCache = {};
  const universeMedian = (date, h) => {
    const k = date + '|' + h;
    if (k in uniCache) return uniCache[k];
    const v = (tickersByDate[date] || []).map(t => fwd(t, date, h)).filter(x => x != null);
    return (uniCache[k] = v.length >= 20 ? median(v) : null);   // menos de 20 tickers → sin referencia fiable
  };
  return { lastDate, series, priceAt, priceAtOrAfter, fwd, tickersByDate, universeMedian };
}

// ── Retorno EJECUTABLE ───────────────────────────────────────────────────────
// El retorno "legado" (fwd) parte del precio de la fila del día de la señal, que es el CIERRE en el que
// se evaluó el filtro: no se puede comprar ahí. Además el snapshot se captura antes de que cierre la sesión
// en EE.UU. y a veces con retraso, así que la fecha de captura (`date`) NO es la fecha de la barra: el campo
// `asOf` sí lo es y puede ir 1-2 sesiones por detrás. Aquí se indexa por fecha de BARRA real y la entrada es
// el cierre de la sesión siguiente a la barra de la señal (la apertura no está en el snapshot; el cierre
// siguiente es conservador y no tiene look-ahead). Horizonte en días naturales desde la barra de entrada.
function makeExecTools(snap) {
  const barSeries = {};                 // ticker -> [{bar, price}] asc, una por fecha de barra
  const barOf = {};                     // "ticker|captureDate" -> fecha de barra de esa fila
  snap.forEach(r => {
    if (!r.ticker || !r.date || !r.asOf || typeof r.price !== 'number' || !(r.price > 0)) return;
    const bar = String(r.asOf).slice(0, 10);
    barOf[r.ticker + '|' + r.date] = bar;
    (barSeries[r.ticker] = barSeries[r.ticker] || []).push({ bar, price: r.price, cap: r.date });
  });
  Object.keys(barSeries).forEach(tk => {
    const byBar = {};
    barSeries[tk].sort((a, b) => a.cap.localeCompare(b.cap)).forEach(x => { byBar[x.bar] = x; });   // la captura más tardía de esa barra
    barSeries[tk] = Object.values(byBar).sort((a, b) => a.bar.localeCompare(b.bar));
  });
  const lastBar = Object.values(barSeries).reduce((d, a) => { const b = a[a.length - 1]?.bar || ''; return b > d ? b : d; }, '');
  const entryOf = (tk, date) => {
    const sigBar = barOf[tk + '|' + date]; const a = barSeries[tk];
    if (!sigBar || !a) return null;
    return a.find(x => x.bar > sigBar) || null;                    // primera barra POSTERIOR a la de la señal
  };
  const fwdExec = (tk, date, h) => {
    const e = entryOf(tk, date); if (!e) return null;
    const target = addDays(e.bar, h);
    if (target > lastBar) return null;
    const x1 = barSeries[tk].find(x => x.bar >= target);
    if (!x1 || daysBetween(target, x1.bar) > 4) return null;
    return (x1.price / e.price - 1) * 100;
  };
  const dates = {};
  snap.forEach(r => { (dates[r.date] = dates[r.date] || new Set()).add(r.ticker); });
  const uniCache = {};
  const universeMedianExec = (date, h) => {
    const k = date + '|' + h;
    if (k in uniCache) return uniCache[k];
    const v = [...(dates[date] || [])].map(t => fwdExec(t, date, h)).filter(x => x != null);
    return (uniCache[k] = v.length >= 20 ? median(v) : null);
  };
  return { fwdExec, universeMedianExec, lastBar };
}

function buildReport() {
  const snap = readJsonl(SNAPSHOT);
  const log = readJsonl(LOG);
  let state = {};
  try { state = JSON.parse(fs.readFileSync(STATE, 'utf8')); } catch (e) { /* sin estado */ }
  const { lastDate, fwd, tickersByDate, universeMedian } = makeTools(snap);
  const ex = makeExecTools(snap);

  // Eventos independientes por filtro.
  const byFilter = {};
  log.forEach(r => { (byFilter[r.filter] = byFilter[r.filter] || []).push(r); });
  const filters = {};
  Object.entries(byFilter).forEach(([filter, rows]) => {
    rows.sort((a, b) => a.date.localeCompare(b.date));
    const lastSeen = {};
    const events = [];
    rows.forEach(r => {
      const prev = lastSeen[r.ticker];
      lastSeen[r.ticker] = r.date;
      if (prev && daysBetween(prev, r.date) < COOLDOWN_DAYS) return;     // continuación del mismo evento
      events.push(r);
    });

    const cov = Object.entries(state.coverage || {}).filter(([, f]) => (f[filter] || 0) > 0).map(([d]) => d).sort();
    const horizons = {}, horizonsExec = {};
    HORIZONS.forEach(h => {
      const rets = [], excess = [];
      events.forEach(e => {
        const ret = fwd(e.ticker, e.date, h); const ref = universeMedian(e.date, h);
        if (ret == null || ref == null) return;
        rets.push(ret); excess.push(ret - ref);
      });
      const n = rets.length;
      // misma medición pero con entrada ejecutable (cierre de la sesión siguiente) — ver makeExecTools
      const erets = [], eexcess = [];
      events.forEach(e => {
        const ret = ex.fwdExec(e.ticker, e.date, h); const ref = ex.universeMedianExec(e.date, h);
        if (ret == null || ref == null) return;
        erets.push(ret); eexcess.push(ret - ref);
      });
      const en = erets.length;
      horizonsExec[h + 'd'] = {
        n_matured: en,
        mean_ret: r2(mean(erets)), median_ret: r2(median(erets)),
        mean_excess: r2(mean(eexcess)), median_excess: r2(median(eexcess)),
        hit_rate_excess: en ? r2(eexcess.filter(x => x > 0).length / en * 100) : null,
        conclusive: en >= MIN_N,
      };
      horizons[h + 'd'] = {
        n_matured: n,
        mean_ret: r2(mean(rets)), median_ret: r2(median(rets)),
        mean_excess: r2(mean(excess)), median_excess: r2(median(excess)),
        hit_rate_excess: n ? r2(excess.filter(x => x > 0).length / n * 100) : null,
        conclusive: n >= MIN_N,
      };
    });
    filters[filter] = {
      screener: rows[0].screener,
      evaluable_from: cov[0] || null,
      evaluable_days: cov.length,
      candidate_rows: rows.length,
      independent_events: events.length,
      tickers: new Set(events.map(e => e.ticker)).size,
      horizons,
      horizons_executable: horizonsExec,
    };
  });

  // Base: el universo en conjunto (referencia para ver si el mercado ayudó o no).
  const baseline = {};
  HORIZONS.forEach(h => {
    const v = [];
    Object.keys(tickersByDate).sort().forEach(d => { const m = universeMedian(d, h); if (m != null) v.push(m); });
    baseline[h + 'd'] = { dates_with_reference: v.length, mean_of_daily_median_ret: r2(mean(v)) };
  });

  // Situaciones Especiales / alertas compuestas DISPARADAS (check_koncorde_alerts.py
  // las registra al dispararse; son one-shot, así que cada fila es un evento).
  // Mismo método que los filtros: retorno a 7/14/30 días vs mediana del universo.
  // Aquí el sentido es siempre "alcista" (las situaciones del usuario se arman
  // para entrar); si algún día hay una bajista, habrá que añadir el sesgo.
  const fired = readJsonl(FIRED_LOG);
  const firedHorizons = {};
  HORIZONS.forEach(h => {
    const rets = [], excess = [];
    fired.forEach(e => {
      const ret = fwd(e.ticker, e.date, h); const ref = universeMedian(e.date, h);
      if (ret == null || ref == null) return;
      rets.push(ret); excess.push(ret - ref);
    });
    const n = rets.length;
    firedHorizons[h + 'd'] = { n_matured: n, mean_ret: r2(mean(rets)), median_ret: r2(median(rets)),
      mean_excess: r2(mean(excess)), hit_rate_excess: n ? r2(excess.filter(x => x > 0).length / n * 100) : null, conclusive: n >= MIN_N };
  });
  const special_situations = { fired_total: fired.length, tickers: new Set(fired.map(e => e.ticker)).size,
    first_fired: fired.length ? fired.map(e => e.date).sort()[0] : null, horizons: firedHorizons };

  return { generated_at: new Date().toISOString(), snapshot_last_date: lastDate, min_n_conclusive: MIN_N,
    cooldown_days: COOLDOWN_DAYS, horizons_days: HORIZONS, baseline, filters, special_situations };
}

function print(rep) {
  console.log(`Informe de candidatos del Screener — datos hasta ${rep.snapshot_last_date}`);
  console.log(`Evento independiente = ≥${rep.cooldown_days} días sin ser candidato · "concluyente" solo con ≥${rep.min_n_conclusive} eventos madurados\n`);
  Object.entries(rep.filters).forEach(([f, d]) => {
    console.log(`■ ${f}  (${d.screener}) — evaluable desde ${d.evaluable_from} (${d.evaluable_days} días) · ${d.independent_events} eventos independientes en ${d.tickers} tickers`);
    Object.entries(d.horizons).forEach(([h, x]) => {
      if (!x.n_matured) { console.log(`   ${h.padEnd(4)} sin eventos madurados todavía`); return; }
      console.log(`   ${h.padEnd(4)} n=${String(x.n_matured).padStart(3)}  ret medio ${String(x.mean_ret).padStart(6)}%  mediana ${String(x.median_ret).padStart(6)}%  | exceso vs universo: medio ${String(x.mean_excess).padStart(6)}  mediana ${String(x.median_excess).padStart(6)}  aciertos ${x.hit_rate_excess}%  ${x.conclusive ? '' : '⚠ no concluyente (n<' + rep.min_n_conclusive + ')'}   [entrada = cierre de la señal, no ejecutable]`);
      const y = d.horizons_executable?.[h];
      if (y && y.n_matured) console.log(`   ${' '.repeat(4)} n=${String(y.n_matured).padStart(3)}  ret medio ${String(y.mean_ret).padStart(6)}%  mediana ${String(y.median_ret).padStart(6)}%  | exceso vs universo: medio ${String(y.mean_excess).padStart(6)}  mediana ${String(y.median_excess).padStart(6)}  aciertos ${y.hit_rate_excess}%   [entrada = cierre de la sesión SIGUIENTE, ejecutable]`);
    });
  });
  const ss = rep.special_situations;
  console.log(`\n■ Situaciones Especiales disparadas: ${ss.fired_total} (${ss.tickers} tickers${ss.first_fired ? ', desde ' + ss.first_fired : ''})`);
  if (!ss.fired_total) console.log('   ninguna registrada todavía (el registro empezó el 2026-10-03)');
  Object.entries(ss.horizons).forEach(([h, x]) => { if (x.n_matured) console.log(`   ${h.padEnd(4)} n=${String(x.n_matured).padStart(3)}  ret medio ${x.mean_ret}%  exceso medio ${x.mean_excess}  aciertos ${x.hit_rate_excess}%  ${x.conclusive ? '' : '⚠ no concluyente'}`); });
  console.log('\nReferencia (media de la mediana diaria del universo): ' + Object.entries(rep.baseline).map(([h, b]) => `${h}: ${b.mean_of_daily_median_ret}%`).join('  '));
}

if (require.main === module) {
  const rep = buildReport();
  print(rep);
  if (!process.argv.includes('--no-write')) { fs.writeFileSync(OUT, JSON.stringify(rep, null, 2)); console.log('\nEscrito ' + path.relative(ROOT, OUT)); }
}
module.exports = { buildReport, makeTools, makeExecTools, readJsonl, HORIZONS, addDays, daysBetween, median, mean, r2 };
