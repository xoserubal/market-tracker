'use strict';
// Recuento previo al preregistro v2 (giro de sectores deprimidos). NO calcula ningún resultado posterior a las
// señales: solo cuántas observaciones, semanas y comparaciones son identificables, la cobertura de Cycle simplificado y
// una única cifra de dispersión INCONDICIONAL (exceso a 40 sesiones de todos los sector-semana, sin distinguir señales)
// para el efecto mínimo detectable.
//   node research/sector_turnaround_v2/counts.js [--refresh]
const fs = require('fs');
const path = require('path');
const L = require('../../scripts/sector_turn/lib');
const copy = require('../../scripts/sector_turn/cycle_copy');

const HIST_END = '2026-08-28';        // última semana del bloque histórico; sep-nov 2026 = ventana expuesta (casos motivadores)
const WORK = path.join(__dirname, '_work');
const CACHE = path.join(WORK, 'prices_max.json');
const OUT = path.join(__dirname, 'counts.json');

const UNEXPOSED_IND = L.INDUSTRIES.filter(x => !x.exposed);
const PROXIES = [...new Set(copy.CYCLE_MAP.flatMap(p => p.sectors.flatMap(s => s.tickers.filter(t => t.role === 'proxy').map(t => t.ticker))))];
const ALL = [...new Set([L.BENCH, ...L.SECTORS, ...L.INDUSTRIES.map(x => x.t), ...PROXIES])];

async function load(refresh) {
  if (!refresh && fs.existsSync(CACHE)) return JSON.parse(fs.readFileSync(CACHE, 'utf8'));
  fs.mkdirSync(WORK, { recursive: true });
  const out = {};
  for (const t of ALL) { const r = await L.fetchDailyFull(t); out[t] = r.bars; process.stdout.write(`${t}:${r.bars.length} `); }
  fs.writeFileSync(CACHE, JSON.stringify(out));
  console.log();
  return out;
}

const quarter = d => d.slice(0, 4) + 'Q' + (Math.floor((+d.slice(5, 7) - 1) / 3) + 1);

function universeRows(prices, tickers) {
  const spy = prices[L.BENCH];
  const rows = [];
  for (const t of tickers) {
    const ratio = L.ratioSeries(prices[t] || [], spy);
    for (const r of L.weeklyEvents(ratio, HIST_END)) rows.push({ ticker: t, ...r });
  }
  return rows;
}

function summarize(rows, label, posMap) {
  const ev = rows.filter(r => r.D != null && r.G != null);
  const byWeek = new Map();
  for (const r of ev) { if (!byWeek.has(r.week)) byWeek.set(r.week, []); byWeek.get(r.week).push(r); }
  const dg = ev.filter(r => r.DG), ind = dg.filter(r => r.independent);
  const weeksDG = [...byWeek.values()].filter(w => w.some(r => r.DG));
  const weeksDGandDnotG = weeksDG.filter(w => w.some(r => r.D && !r.G));
  const weeksIndDGandDnotG = [...byWeek.values()].filter(w => w.some(r => r.DG && r.independent) && w.some(r => r.D && !r.G));
  // Emparejamiento descriptivo: para cada D∧G independiente, ¿hay un D sin G de otro ETF en ±4 semanas con
  // profundidad a ±5 pp?
  const dnotg = ev.filter(r => r.D && !r.G);
  const wIdx = new Map([...byWeek.keys()].sort().map((w, i) => [w, i]));
  let matched = 0;
  for (const e of ind) {
    const wi = wIdx.get(e.week);
    if (dnotg.some(c => c.ticker !== e.ticker && Math.abs(wIdx.get(c.week) - wi) <= 4 && Math.abs(c.dist_max756 - e.dist_max756) <= 0.05)) matched++;
  }
  const perTicker = {}; for (const r of ind) perTicker[r.ticker] = (perTicker[r.ticker] || 0) + 1;
  const perYear = {}; for (const r of ind) perYear[r.date.slice(0, 4)] = (perYear[r.date.slice(0, 4)] || 0) + 1;
  const first = {}; for (const r of ev) if (!first[r.ticker]) first[r.ticker] = r.date;
  return { label, etfs: [...new Set(ev.map(r => r.ticker))].length, first_evaluable_week: first,
    etf_weeks_evaluable: ev.length, weeks_evaluable: byWeek.size,
    D_weeks: ev.filter(r => r.D).length, G_weeks: ev.filter(r => r.G).length,
    DG_events: dg.length, DG_independent: ind.length, weeks_with_independent_DG: new Set(ind.map(r => r.week)).size, quarters_with_independent_DG: new Set(ind.map(r => quarter(r.date))).size,
    weeks_with_DG: weeksDG.length, weeks_with_DG_and_DnotG: weeksDGandDnotG.length,
    weeks_with_independentDG_and_DnotG: weeksIndDGandDnotG.length,
    independent_DG_with_depth_match_pm4w: matched,
    independent_per_etf: perTicker, independent_per_year: perYear,
    _ind: ind.map(r => ({ ticker: r.ticker, week: r.week, date: r.date, dist: r.dist_max756 })) };
}

// Cycle simplificado en cada semana de decisión (fase dominante con los proxies disponibles a esa fecha).
function cycleByWeek(prices, weeks) {
  const out = new Map();
  for (const [week, date] of weeks) {
    const sc = L.simplifiedPhaseScores(copy.CYCLE_MAP, prices, date);
    out.set(week, { date, dom: L.dominantOf(sc), scored: sc.filter(p => p.score != null).map(p => p.order) });
  }
  return out;
}

function h2(indEvents, cyc, posMap, label) {
  const res = { label, independent_DG: indEvents.length, mapped: 0, concordant: 0, non_concordant: 0, unmapped: 0, no_cycle: 0,
    weeks_with_both: 0, quarters_with_concordant: 0, quarters_with_both: 0, concordant_per_etf: {} };
  const byWeek = new Map(), qC = new Set(), qN = new Set();
  for (const e of indEvents) {
    const c = cyc.get(e.week);
    if (!c?.dom) { res.no_cycle++; continue; }
    const p = posMap(e.ticker);
    if (p == null) { res.unmapped++; continue; }
    res.mapped++;
    const k = p === c.dom.next_pos;
    if (k) { res.concordant++; qC.add(quarter(e.date)); res.concordant_per_etf[e.ticker] = (res.concordant_per_etf[e.ticker] || 0) + 1; }
    else { res.non_concordant++; qN.add(quarter(e.date)); }
    if (!byWeek.has(e.week)) byWeek.set(e.week, new Set()); byWeek.get(e.week).add(k);
  }
  res.weeks_with_both = [...byWeek.values()].filter(s => s.size === 2).length;
  res.quarters_with_concordant = qC.size;
  res.quarters_with_both = [...qC].filter(q => qN.has(q)).length;
  return res;
}

// Dispersión incondicional del exceso a 40 sesiones (sector − media de sectores disponibles), todas las semanas.
function unconditionalSd(prices, tickers, h = 40) {
  const dates = prices[L.BENCH].map(b => b.date).filter(d => d <= HIST_END);
  const idx = new Map(dates.map((d, i) => [d, i]));
  const adj = {}; for (const t of tickers) adj[t] = new Map((prices[t] || []).filter(b => b.adj).map(b => [b.date, b.adj]));
  const ends = L.weekEnds(dates, HIST_END);
  const xs = [];
  for (const i of ends) {
    const j = i + 1 + h; if (j >= dates.length) break;
    const d0 = dates[i + 1], d1 = dates[j];
    const rets = tickers.map(t => (adj[t].get(d0) && adj[t].get(d1)) ? adj[t].get(d1) / adj[t].get(d0) - 1 : null).filter(x => x != null);
    if (rets.length < 5) continue;
    const m = rets.reduce((a, b) => a + b, 0) / rets.length;
    for (const r of rets) xs.push(r - m);
  }
  const mu = xs.reduce((a, b) => a + b, 0) / xs.length;
  return { n: xs.length, sd: Math.sqrt(xs.reduce((a, b) => a + (b - mu) ** 2, 0) / xs.length) };
}

(async () => {
  const prices = await load(process.argv.includes('--refresh'));
  const coverage = {};
  for (const t of ALL) { const b = prices[t] || []; coverage[t] = { first: b[0]?.date ?? null, last: b[b.length - 1]?.date ?? null, sessions: b.length }; }

  const secRows = universeRows(prices, L.SECTORS);
  const indRows = universeRows(prices, UNEXPOSED_IND.map(x => x.t));
  const sec = summarize(secRows, 'sectores SPDR (EE.UU., exploratorio)');
  const ind = summarize(indRows, 'industrias no expuestas (EE.UU., generalización)');

  const weeks = new Map(); for (const r of [...secRows, ...indRows]) if (r.D != null) weeks.set(r.week, r.date);
  const cyc = cycleByWeek(prices, [...weeks.entries()].sort());
  const covCycle = {};
  for (const [w, c] of cyc) { const k = c.scored.length; covCycle[k] = (covCycle[k] || 0) + 1; }
  const firstFull = [...cyc.entries()].find(([, c]) => c.scored.length === 10)?.[1].date ?? null;

  const bookPos = Object.fromEntries(L.INDUSTRIES.map(x => [x.t, x.pos]));
  const H2 = {
    sectors_cycle: h2(sec._ind, cyc, t => L.SECTOR_POS_CYCLE[t], 'sectores, tabla Cycle (sin XLRE)'),
    sectors_cycle_plus_xlre: h2(sec._ind, cyc, t => L.SECTOR_POS_WITH_XLRE[t], 'sectores, tabla Cycle + XLRE'),
    industries_book: h2(ind._ind, cyc, t => bookPos[t], 'industrias, tabla del libro'),
  };
  const sdSec = unconditionalSd(prices, L.SECTORS);
  const sdInd = unconditionalSd(prices, UNEXPOSED_IND.map(x => x.t));
  // Efecto mínimo detectable (exceso medio a 40 sesiones), potencia 80 %, bilateral. n efectivo = trimestres con
  // eventos independientes (las observaciones de un mismo trimestre se tratan como un bloque).
  const z = { a05: 1.96, a025: 2.241, a0167: 2.394, pow80: 0.8416 };
  const mde = (sd, n, za) => n > 0 ? +((za + z.pow80) * sd / Math.sqrt(n)).toFixed(4) : null;
  const power = {
    note: 'Dispersión incondicional de todos los sector-semana (no de los eventos). n efectivo = trimestres con eventos.',
    sectors: { sd40: +sdSec.sd.toFixed(4), n_obs_sd: sdSec.n, n_events: sec.DG_independent, n_eff_quarters: sec.quarters_with_independent_DG,
      mde_alpha05_events: mde(sdSec.sd, sec.DG_independent, z.a05), mde_alpha05_quarters: mde(sdSec.sd, sec.quarters_with_independent_DG, z.a05) },
    industries: { sd40: +sdInd.sd.toFixed(4), n_obs_sd: sdInd.n, n_events: ind.DG_independent, n_eff_quarters: ind.quarters_with_independent_DG,
      mde_alpha05_events: mde(sdInd.sd, ind.DG_independent, z.a05), mde_alpha05_quarters: mde(sdInd.sd, ind.quarters_with_independent_DG, z.a05) },
    h2_sectors_concordant: { n: H2.sectors_cycle.concordant, quarters: H2.sectors_cycle.quarters_with_concordant,
      mde_alpha05_quarters: mde(sdSec.sd * Math.SQRT2, H2.sectors_cycle.quarters_with_concordant, z.a05) },
  };
  const prospective_rate = { sectors_per_year: +(sec.DG_independent / ((Date.parse(HIST_END) - Date.parse('2001-12-01')) / 3.156e10)).toFixed(2) };
  const pooledWeeks = new Set([...sec._ind, ...ind._ind].map(r => r.week)).size;
  const pooledQuarters = new Set([...sec._ind, ...ind._ind].map(r => quarter(r.date))).size;
  const secWeeks = new Set(sec._ind.map(r => r.week));
  const indSameWeekAsSector = ind._ind.filter(r => secWeeks.has(r.week)).length;
  const pooled = { events: sec._ind.length + ind._ind.length, weeks: pooledWeeks, quarters: pooledQuarters,
    industry_events_in_weeks_with_sector_event: indSameWeekAsSector };
  for (const s of [sec, ind]) delete s._ind;
  const out = { generated_utc: new Date().toISOString(), hist_end: HIST_END, rules: { D_LOOKBACK: L.D_LOOKBACK, D_DEPTH: L.D_DEPTH,
    G_SMA: L.G_SMA, INDEP_WEEKS: L.INDEP_WEEKS }, coverage, sectors: sec, industries: ind,
    cycle_simplified: { weeks: cyc.size, phases_scored_distribution: covCycle, first_week_all_10_phases: firstFull }, H2, power, prospective_rate, pooled_A_plus_Aprime: pooled };
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  console.log(JSON.stringify({ sectors: { ...sec, independent_per_etf: undefined, independent_per_year: undefined, first_evaluable_week: undefined },
    industries: { ...ind, independent_per_year: undefined, first_evaluable_week: undefined }, cycle: out.cycle_simplified, pooled, prospective_rate }, null, 1));
})();
