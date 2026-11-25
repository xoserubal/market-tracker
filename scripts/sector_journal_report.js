#!/usr/bin/env node
// ── Informe del diario sectorial (/sector en Telegram) ────────────────────────
//
// Origen (2026-11-25): el usuario recorre Cycle → Flujos & Rotación → Relative Flow
// y a veces "ve" un sector girar (Salud aún abajo pero girando, Real Estate, Staples…)
// sin hacer nada. La confluencia mecánica de esas pestañas ya se probó y no funciona
// (research/sector_confluence_v1), pero lo que el usuario ve no es exactamente esa
// regla. Este informe mide SUS lecturas, apuntadas antes de saber cómo acaban, para
// no depender de lo que recuerda después (sesgo de memoria).
//
// ENTRADA: docs/data/sector_journal.jsonl (lo escribe telegram_portfolio_bot.py).
//
// MEDICIÓN (fijada antes de tener ninguna lectura):
//   - Sesión de entrada = la primera sesión de EE.UU. cuyo cierre (16:00 ET) es
//     posterior al momento en que se apuntó la lectura. Se mide desde ese cierre.
//   - Barra de la señal = la sesión anterior (la última cerrada cuando se apuntó):
//     de ahí sale el contexto de RFL (ratio TICKER/SPY con shared/relative-lib.js,
//     el mismo cálculo que relative.html) y el puesto del sector por fuerza a 3 meses.
//   - Horizontes: 5, 20 y 60 sesiones del propio ticker.
//   - Exceso frente a SPY y frente a la media simple de los 11 sectores SPDR en las
//     mismas fechas. En lecturas "baja" el exceso se cambia de signo (+ = acertó).
//   - Lectura independiente = sin otra del mismo ticker y dirección en las 20
//     sesiones anteriores.
//   - Descriptivo. Concluyente solo con n >= 30 lecturas independientes maduradas.
//
// CLI:
//   node scripts/sector_journal_report.js            # escribe docs/data/sector_journal_report.json
//   node scripts/sector_journal_report.js --dry-run  # imprime el resumen sin escribir

const fs = require('fs');
const path = require('path');
const lib = require('../shared/relative-lib.js');
const { fetchYahooChartFresh } = require('../shared/quote-lib.js');

const ROOT = path.join(__dirname, '..');
const IN_JOURNAL = process.env.SECTOR_JOURNAL_IN || path.join(ROOT, 'docs', 'data', 'sector_journal.jsonl');
const OUT_REPORT = process.env.SECTOR_JOURNAL_OUT || path.join(ROOT, 'docs', 'data', 'sector_journal_report.json');   // env: solo para pruebas

const HORIZONS = [5, 20, 60];
const INDEP_GAP = 20;
const MIN_N_CONCLUSIVE = 30;
const SECTORS = ['XLK', 'XLF', 'XLV', 'XLY', 'XLP', 'XLE', 'XLI', 'XLB', 'XLRE', 'XLC', 'XLU'];
const BENCH = 'SPY';
const DRY = process.argv.includes('--dry-run');

const r2 = (x, d = 2) => (x == null || !Number.isFinite(x)) ? null : +x.toFixed(d);
const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
function tstat(a) {
  if (a.length < 3) return null;
  const m = mean(a); const sd = Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1));
  return sd > 0 ? m / (sd / Math.sqrt(a.length)) : null;
}

function readJournal() {
  if (!fs.existsSync(IN_JOURNAL)) return [];
  return fs.readFileSync(IN_JOURNAL, 'utf8').split('\n').filter(l => l.trim())
    .map((l, i) => { try { return { num: i + 1, ...JSON.parse(l) }; } catch (e) { return null; } })
    .filter(e => e && e.ts && Array.isArray(e.tickers) && (e.direction === 'up' || e.direction === 'down'));
}

async function fetchSeries(ticker, range) {
  const { ok, result } = await fetchYahooChartFresh(ticker, range, '1d');
  if (!ok || !result) throw new Error('sin datos');
  const closes = result.indicators?.quote?.[0]?.close ?? [];
  const series = (result.timestamp ?? []).map((t, i) => ({ date: new Date(t * 1000).toISOString().slice(0, 10), close: closes[i] }))
    .filter(p => p.close != null && Number.isFinite(p.close));
  // Barra de hoy parcial (EE.UU. abierto): fuera hasta ~21 UTC, igual que relative_signal_log.js.
  const now = new Date();
  if (series.length && series[series.length - 1].date === now.toISOString().slice(0, 10) && now.getUTCHours() < 21) series.pop();
  if (!series.length) throw new Error('sin cierres');
  return series;
}

// Fecha (YYYY-MM-DD) y hora en Nueva York de un timestamp ISO.
function nyParts(iso) {
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', hour12: false });
  const p = Object.fromEntries(f.formatToParts(new Date(iso)).map(x => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, hour: +p.hour % 24 };
}

// Cierre a fecha (el último disponible en o antes de `date`).
function closeAtOrBefore(series, date) {
  let lo = 0, hi = series.length - 1, ans = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (series[m].date <= date) { ans = m; lo = m + 1; } else hi = m - 1; }
  return ans >= 0 ? series[ans].close : null;
}

function retBetween(series, d0, d1) {
  const a = closeAtOrBefore(series, d0), b = closeAtOrBefore(series, d1);
  return a && b ? (b / a - 1) * 100 : null;
}

async function main() {
  const journal = readJournal();
  const report = { generated_at: new Date().toISOString(), horizons: HORIZONS, min_n_conclusive: MIN_N_CONCLUSIVE, n_readings: journal.length, rows: [], summary: {}, failed: [] };
  if (!journal.length) {
    console.log('Diario sectorial vacío: informe sin lecturas.');
    if (!DRY) fs.writeFileSync(OUT_REPORT, JSON.stringify(report, null, 1));
    return;
  }

  const earliest = journal.map(e => e.ts).sort()[0];
  const yearsBack = (Date.now() - Date.parse(earliest)) / (365.25 * 864e5);
  const range = yearsBack > 3 ? '10y' : '5y';   // RFL necesita ~1 año antes de la primera lectura
  const tickers = [...new Set([BENCH, ...SECTORS, ...journal.flatMap(e => e.tickers)])];
  const hist = {};
  for (let i = 0; i < tickers.length; i += 8) {
    await Promise.all(tickers.slice(i, i + 8).map(async t => {
      try { hist[t] = await fetchSeries(t, range); } catch (e) { report.failed.push(t); }
    }));
  }
  if (!hist[BENCH]) { console.error('Sin datos de SPY'); process.exit(1); }
  const cal = hist[BENCH].map(p => p.date);   // calendario de sesiones de EE.UU.

  // Lecturas independientes: sin otra del mismo ticker+dirección en las INDEP_GAP sesiones previas.
  const lastSeen = {};

  const sorted = [...journal].sort((a, b) => a.ts.localeCompare(b.ts));
  for (const e of sorted) {
    const ny = nyParts(e.ts);
    const afterClose = ny.hour >= 16;
    const entryIdx = cal.findIndex(d => afterClose ? d > ny.date : d >= ny.date);
    const signalDate = entryIdx > 0 ? cal[entryIdx - 1] : (entryIdx === -1 ? cal[cal.length - 1] : null);
    const entryDate = entryIdx >= 0 ? cal[entryIdx] : null;

    // Puesto de cada sector por fuerza a 3 meses en la barra de la señal (1 = el más fuerte).
    const r3 = {};
    if (signalDate) for (const s of SECTORS) {
      const ser = hist[s]; if (!ser) continue;
      const i = ser.findIndex(p => p.date > signalDate) - 1;
      const iEnd = i === -2 ? ser.length - 1 : i;
      if (iEnd >= 63) r3[s] = (ser[iEnd].close / ser[iEnd - 63].close - 1) * 100;
    }
    const rankOrder = Object.entries(r3).sort((a, b) => b[1] - a[1]).map(x => x[0]);

    for (const t of e.tickers) {
      const ser = hist[t];
      const row = { num: e.num, ts: e.ts, ticker: t, direction: e.direction, sources: e.sources || [], note: e.note || '',
                    signal_date: signalDate, entry_date: null, context: null, horizons: {} };
      if (!ser) { row.error = 'sin datos'; report.rows.push(row); continue; }

      // Contexto RFL (TICKER/SPY) en la barra de la señal.
      if (signalDate && t !== BENCH) {
        const ratio = lib.alignRatio(ser, hist[BENCH]).filter(p => p.date <= signalDate);
        const rr = lib.buildRowFromRatio({ a: t, b: BENCH }, ratio);
        if (!rr.error) row.context = {
          rfl_score: r2(rr.score, 1), rfl_signal: lib.classify(rr).label, rfl_flow_change: r2(rr.flowChange),
          rfl_trend: rr.trend, rel_1m: r2(rr.r1m), rel_3m: r2(rr.r3m), rel_from_high_52w: r2(rr.fromHigh),
          sector_rank_3m: SECTORS.includes(t) && rankOrder.includes(t) ? rankOrder.indexOf(t) + 1 : null,
          sectors_ranked: rankOrder.length,
        };
      }

      // Entrada en el calendario del propio ticker (primera sesión >= la de entrada).
      const ei = entryDate ? ser.findIndex(p => p.date >= entryDate) : -1;
      if (ei < 0) { row.pending = true; report.rows.push(row); continue; }
      row.entry_date = ser[ei].date;
      row.entry_close = r2(ser[ei].close, 4);
      const sign = e.direction === 'down' ? -1 : 1;
      for (const h of HORIZONS) {
        const xi = ei + h;
        const exit = xi < ser.length ? ser[xi] : null;
        const last = ser[ser.length - 1];
        const d1 = exit ? exit.date : last.date;
        const ret = (( exit ? exit.close : last.close) / ser[ei].close - 1) * 100;
        const spy = retBetween(hist[BENCH], row.entry_date, d1);
        const secRets = SECTORS.map(s => hist[s] && hist[s][0].date <= row.entry_date ? retBetween(hist[s], row.entry_date, d1) : null).filter(x => x != null);
        const secMean = mean(secRets);
        row.horizons[h] = {
          matured: !!exit, sessions: exit ? h : ser.length - 1 - ei, exit_date: d1,
          ret: r2(ret), vs_spy: spy == null ? null : r2(sign * (ret - spy)),
          vs_sectors: secMean == null ? null : r2(sign * (ret - secMean)),
        };
      }

      const key = `${t}|${e.direction}`;
      const prev = lastSeen[key];
      const curIdx = cal.indexOf(entryDate);
      row.independent = prev == null || curIdx - prev > INDEP_GAP;
      lastSeen[key] = curIdx;
      report.rows.push(row);
    }
  }

  // Resumen: por dirección y por pestaña citada, solo lecturas maduradas.
  const groups = { all: r => true, up: r => r.direction === 'up', down: r => r.direction === 'down',
                   cycle: r => r.sources.includes('cycle'), flujos: r => r.sources.includes('flujos'),
                   rfl: r => r.sources.includes('rfl'), sin_pestana: r => !r.sources.length };
  for (const [g, fn] of Object.entries(groups)) {
    report.summary[g] = {};
    for (const h of HORIZONS) {
      const mk = rows => {
        const m = rows.filter(r => fn(r) && r.horizons[h]?.matured && r.horizons[h].vs_sectors != null);
        const xs = m.map(r => r.horizons[h].vs_sectors), xsp = m.map(r => r.horizons[h].vs_spy).filter(x => x != null);
        return { n: m.length, mean_vs_sectors: r2(mean(xs)), hit_rate: m.length ? r2(xs.filter(x => x > 0).length / m.length * 100, 0) : null,
                 t: r2(tstat(xs)), mean_vs_spy: r2(mean(xsp)) };
      };
      const all = mk(report.rows), indep = mk(report.rows.filter(r => r.independent));
      report.summary[g][h] = { all, independent: indep, conclusive: indep.n >= MIN_N_CONCLUSIVE };
    }
  }

  const s = report.summary.all;
  console.log(`Diario sectorial: ${journal.length} lecturas, ${report.rows.length} ticker-lecturas` + (report.failed.length ? `; sin datos: ${report.failed.join(', ')}` : ''));
  for (const h of HORIZONS) console.log(`  ${h} ses.: n=${s[h].all.n} (indep ${s[h].independent.n})  vs sectores ${s[h].all.mean_vs_sectors ?? '—'}  acierto ${s[h].all.hit_rate ?? '—'}%`);
  if (!DRY) fs.writeFileSync(OUT_REPORT, JSON.stringify(report, null, 1));
}

main().catch(e => { console.error(e); process.exit(1); });
