#!/usr/bin/env node
// ── Registro diario de señales de Relative Flow Lab (+ backfill) e informe ───
//
// Origen (2026-10-16): el Screener ya mide qué hicieron sus candidatos después
// (scripts/screener_signal_log.js + screener_signal_report.js). RFL detecta
// entradas (p. ej. Healthcare hace unos días) pero nada medía si esas señales
// acababan funcionando. Este script hace lo mismo para RFL.
//
// Por qué un script de pipeline y no guardar en la pestaña: relative_flow_history
// (state.json) es local y solo se escribe cuando alguien abre la página. Aquí la
// captura corre sola 2×/día (Step 9g1c).
//
// Mismo motor que la página: shared/relative-lib.js (buildRowFromRatio/classify/
// coherentFlowDirection) y shared/relative-ratio-registry.js. Si cambia el scoring
// de relative.html, cambia aquí a la vez porque es el mismo archivo.
//
// EVENTOS (señales de ENTRADA y sus espejos de salida, para ver si discriminan):
//   to_leader / to_improving      entra en Leader / en Improving desde un estado inferior
//   upgrade_1w                    sube de clasificación vs 5 sesiones antes (badge UPGRADED)
//   flow_in_top3                  Top 3 Flow In del día (filtro de coherencia de la Fase 4)
//   to_laggard / to_weakening / downgrade_1w / flow_out_top3   los espejos (direction=out)
//   flow_jump_up / flow_jump_down  SALTO DIARIO del flow change (lo que mira el usuario en la página):
//                                  Δ = flowChange(hoy) − flowChange(ayer), en puntos. Se registra si |Δ|>=4 o si
//                                  |z|>=2.5 (z = Δ / media del |Δ| de las 126 sesiones previas del propio ratio).
//                                  El informe lo parte en tramos abs4/6/8, z25/z35, cross0 (cruza por cero), coh.
//
// MEDICIÓN: el ratio A/B ya es retorno relativo, así que el retorno posterior del
// evento es el retorno del propio ratio. Entrada ejecutable = cierre de la sesión
// SIGUIENTE a la barra de la señal (la del cierre en que se detecta no se puede
// comprar). Horizontes en SESIONES: 1/3/5/10/21. Exceso = retorno − mediana de todos
// los ratios esa misma fecha de entrada. Evento independiente = sin otro evento del
// mismo ratio+tipo en las 10 sesiones previas. Concluyente solo con n ≥ 30.
// Descriptivo: sin corrección por comparaciones múltiples ni dev/test.
//
// Backfill: la primera ejecución recorre ~10 años de historia (source=backfill). Lo
// capturado después es source=live. OJO: el backfill NO es fuera de muestra (las
// reglas se diseñaron mirando este mismo tipo de datos); solo el live lo es.
//
// CLI:
//   node scripts/relative_signal_log.js              # log incremental + informe
//   node scripts/relative_signal_log.js --dry-run    # no escribe nada
//   node scripts/relative_signal_log.js --rebuild    # borra log y estado, rehace backfill
//   node scripts/relative_signal_log.js --report-only

const fs   = require('fs');
const path = require('path');
const REG = require('../shared/relative-ratio-registry.js');
const lib = require('../shared/relative-lib.js');
const { fetchYahooChartFresh } = require('../shared/quote-lib.js');

const ROOT = path.join(__dirname, '..');
const OUT_LOG = path.join(ROOT, 'docs', 'data', 'relative_signal_log.jsonl');
const OUT_STATE = path.join(ROOT, 'docs', 'data', 'relative_signal_log_state.json');
const OUT_REPORT = path.join(ROOT, 'docs', 'data', 'relative_signal_report.json');

const HORIZONS = [1, 3, 5, 10, 21];       // sesiones desde la entrada ejecutable
const COOLDOWN_BARS = 10;
const MIN_N_CONCLUSIVE = 30;
const MIN_BARS = 70;                       // mismo mínimo que buildRowFromRatio
const RECENT_DAYS = 20;
const RANGE = '10y';   // 10 anios: con 5 el regimen (SMA200 de SPY) solo existe desde ~ago-2022 y el bajista de 2022 queda fuera
// "Contra el mercado" = ratios cuyo denominador es un indice amplio (SPY, URTH). Son los que el usuario
// vigila para saltos del flow change; el resto (AMR/BTU, JPY/Nikkei...) son pares intra-tema, otra cosa.
const MARKET_BENCH = new Set(['SPY', 'URTH']);
const isMarketPair = pair => MARKET_BENCH.has(pair[1]);
// Salto diario del flow change (lo que el usuario mira en la página). Se registra si |Δ| >= JUMP_LOG_ABS pp
// o |z| >= JUMP_LOG_Z, donde z = Δ / media(|Δ| de las JUMP_SCALE_BARS sesiones previas DEL PROPIO RATIO)
// (sin mirar al futuro). Los tramos del informe (abs4/6/8, z2.5/3.5…) se derivan de lo guardado.
const JUMP_LOG_ABS = 4, JUMP_LOG_Z = 2.5, JUMP_SCALE_BARS = 126, JUMP_SCALE_MIN = 60;

const args = process.argv.slice(2);
const DRY = args.includes('--dry-run');
const REBUILD = args.includes('--rebuild');
const REPORT_ONLY = args.includes('--report-only');

const RANK = lib.RATIO_SIGNAL_RANK;
const rk = l => RANK[l] ?? 0;
const r2 = (x, d = 2) => (x == null || !Number.isFinite(x)) ? null : +x.toFixed(d);

function readJsonl(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(Boolean);
}
const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
function tstat(a) {
  if (a.length < 3) return null;
  const m = mean(a); const sd = Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1));
  return sd > 0 ? m / (sd / Math.sqrt(a.length)) : null;
}

async function fetchSeries(ticker) {
  const { ok, result } = await fetchYahooChartFresh(ticker, RANGE, '1d');
  if (!ok || !result) throw new Error('sin datos');
  const closes = result.indicators?.quote?.[0]?.close ?? [];
  const ts = result.timestamp ?? [];
  const series = ts.map((t, i) => ({ date: new Date(t * 1000).toISOString().slice(0, 10), close: closes[i] }))
    .filter(p => p.close != null && Number.isFinite(p.close));
  if (!series.length) throw new Error('sin cierres');
  return series;
}

async function loadHistories(tickers) {
  const out = {}; const failed = [];
  for (let i = 0; i < tickers.length; i += 8) {
    await Promise.all(tickers.slice(i, i + 8).map(async t => {
      try { out[t] = await fetchSeries(t); } catch (e) { failed.push(t); }
    }));
    await new Promise(r => setTimeout(r, 300));
  }
  return { out, failed };
}

async function main() {
  const entries = REG.RATIO_REGISTRY.filter(r => r.enabled !== false).map(e => ({ ...e, a: e.pair[0], b: e.pair[1] }));
  const tickers = [...new Set(entries.flatMap(e => e.pair))];
  const { out: hist, failed } = await loadHistories(tickers);
  if (failed.length) console.log('⚠ sin datos:', failed.join(', '));
  if (!Object.keys(hist).length) { console.error('Ningún ticker cargó'); process.exit(1); }

  // ratios alineados (una sola vez)
  const R = {};
  for (const e of entries) {
    if (!hist[e.a] || !hist[e.b]) continue;
    const ratio = lib.alignRatio(hist[e.a], hist[e.b]);
    // La barra de HOY puede ser parcial (Yahoo sirve el precio intradía si el mercado de EE.UU.
    // sigue abierto; cierra ~20-21 UTC). Un evento calculado sobre una vela a medias podría no
    // existir al cierre y el dedup lo dejaría registrado para siempre → se descarta hasta ~21 UTC.
    const now = new Date();
    if (ratio.length && ratio[ratio.length - 1].date === now.toISOString().slice(0, 10) && now.getUTCHours() < 21) ratio.pop();
    if (ratio.length < MIN_BARS + 1) continue;
    R[e.id] = { entry: e, ratio, idx: Object.fromEntries(ratio.map((p, i) => [p.date, i])) };
  }

  let state = { watermark: {} };
  if (!REBUILD && fs.existsSync(OUT_STATE)) { try { state = JSON.parse(fs.readFileSync(OUT_STATE, 'utf8')); } catch (e) { /* reprocesa */ } }
  state.watermark = state.watermark || {};
  let existing = REBUILD ? [] : readJsonl(OUT_LOG);
  let newRows = [];

  if (!REPORT_ONLY) {
    const seen = new Set(existing.map(r => `${r.date}|${r.ratio_id}|${r.event}`));
    const flowCands = {};                      // date -> {in:[], out:[]}
    const evBase = [];                         // eventos de transición (sin top3)
    const newWatermark = { ...state.watermark };

    for (const [id, { entry, ratio }] of Object.entries(R)) {
      const wm = state.watermark[id] || null;
      const source = wm ? 'live' : 'backfill';
      const n = ratio.length;
      let ni = wm ? ratio.findIndex(p => p.date > wm) : MIN_BARS - 1;
      if (ni === -1) { newWatermark[id] = ratio[n - 1].date; continue; }
      ni = Math.max(ni, MIN_BARS - 1);
      const from = Math.max(MIN_BARS - 1, ni - 5 - JUMP_SCALE_BARS - 1);   // 5 para upgrade_1w + ventana de escala del salto
      const rows = {};
      for (let j = from; j < n; j++) {
        const row = lib.buildRowFromRatio(entry, ratio.slice(0, j + 1));
        rows[j] = { row, label: lib.classify(row).label, dir: lib.coherentFlowDirection(row) };
      }
      for (let i = ni; i < n; i++) {
        const cur = rows[i], prev = rows[i - 1], p5 = rows[i - 5];
        if (!cur || cur.row.error) continue;
        const date = ratio[i].date;
        // Fila compacta: pair/type se derivan del registro al construir el informe (no se guardan).
        const base = {
          date, ratio_id: id, source,
          label: cur.label, score: r2(cur.row.score, 1), flow_change: r2(cur.row.flowChange, 2),
        };
        const push = (event, direction, extra) => evBase.push({ ...base, event, direction, ...(extra || {}) });
        if (prev && !prev.row.error) {
          const L = cur.label, P = prev.label;
          if (L === 'Leader' && P !== 'Leader') push('to_leader', 'in');
          if (L === 'Improving' && rk(P) < 4) push('to_improving', 'in');
          if (L === 'Laggard' && P !== 'Laggard') push('to_laggard', 'out');
          if (L === 'Weakening' && rk(P) > 2) push('to_weakening', 'out');
        }
        if (p5 && !p5.row.error) {
          if (rk(cur.label) >= 4 && rk(cur.label) > rk(p5.label) && rk(p5.label) > 0) push('upgrade_1w', 'in');
          if (rk(cur.label) <= 2 && rk(cur.label) > 0 && rk(cur.label) < rk(p5.label)) push('downgrade_1w', 'out');
        }
        // Salto diario del flow change
        const fcAt = j => rows[j]?.row?.flowChange ?? null;
        const f1 = fcAt(i), f0 = fcAt(i - 1);
        if (f1 != null && f0 != null) {
          const dFC = f1 - f0;
          let sum = 0, cnt = 0;
          for (let k = i - JUMP_SCALE_BARS; k < i; k++) {
            const a = fcAt(k), b = fcAt(k - 1);
            if (a != null && b != null) { sum += Math.abs(a - b); cnt++; }
          }
          const z = cnt >= JUMP_SCALE_MIN && sum > 0 ? dFC / (sum / cnt) : null;
          if (Math.abs(dFC) >= JUMP_LOG_ABS || (z != null && Math.abs(z) >= JUMP_LOG_Z)) {
            const up = dFC > 0;
            const cross0 = up ? (f0 <= 0 && f1 > 0) : (f0 >= 0 && f1 < 0);
            push(up ? 'flow_jump_up' : 'flow_jump_down', up ? 'in' : 'out',
              { d_flow: r2(dFC, 2), z: r2(z, 1), cross0, coherent: cur.dir === (up ? 'in' : 'out') });
          }
        }
        if (cur.dir) {
          (flowCands[date] = flowCands[date] || { in: [], out: [] })[cur.dir].push({ ...base, flow_change: cur.row.flowChange });
        }
      }
      newWatermark[id] = ratio[n - 1].date;
    }
    // Top 3 por fecha (mismo criterio que el panel: |flowChange| dentro de cada dirección)
    for (const [date, c] of Object.entries(flowCands)) {
      c.in.sort((x, y) => y.flow_change - x.flow_change).slice(0, 3).forEach((b, k) =>
        evBase.push({ ...b, flow_change: r2(b.flow_change, 2), event: 'flow_in_top3', direction: 'in', rank: k + 1 }));
      c.out.sort((x, y) => x.flow_change - y.flow_change).slice(0, 3).forEach((b, k) =>
        evBase.push({ ...b, flow_change: r2(b.flow_change, 2), event: 'flow_out_top3', direction: 'out', rank: k + 1 }));
    }
    for (const ev of evBase) {
      const key = `${ev.date}|${ev.ratio_id}|${ev.event}`;
      if (seen.has(key)) continue;
      seen.add(key); newRows.push(ev);
    }
    newRows.sort((x, y) => x.date.localeCompare(y.date) || x.ratio_id.localeCompare(y.ratio_id));
    state.watermark = newWatermark;
    console.log(`Ratios evaluados: ${Object.keys(R).length}/${entries.length} · eventos nuevos: ${newRows.length}`
      + ` (live ${newRows.filter(r => r.source === 'live').length}, backfill ${newRows.filter(r => r.source === 'backfill').length})`);
  }

  const allEvents = existing.concat(newRows);
  const report = buildReport(R, allEvents, hist);

  if (DRY) { console.log('[dry-run] no se escribe nada'); printSummary(report); return; }
  if (!REPORT_ONLY) {
    fs.writeFileSync(OUT_LOG, allEvents.map(r => JSON.stringify(r)).join('\n') + (allEvents.length ? '\n' : ''));
    fs.writeFileSync(OUT_STATE, JSON.stringify({ watermark: state.watermark, updated_at: new Date().toISOString() }, null, 2));
  }
  fs.writeFileSync(OUT_REPORT, JSON.stringify(report));
  printSummary(report);
  console.log(`OK — log ${allEvents.length} filas, informe escrito`);
}

// ── Informe ─────────────────────────────────────────────────────────────────
function buildReport(R, events, hist) {
  // Retornos posteriores desde una barra de entrada e: ratio[e+h]/ratio[e]-1 (%)
  const fwd = (ratio, e, h) => (e + h < ratio.length) ? (ratio[e + h].value / ratio[e].value - 1) * 100 : null;

  // Regimen de mercado en la fecha de la senal, segun SPY (sin mirar al futuro):
  //   bajista = cierre < SMA200 · alcista = cierre >= SMA200, cierre >= SMA50 y SMA50 >= SMA200
  //   lateral = por encima de SMA200 pero sin ese alineamiento (debajo de SMA50 o SMA50 < SMA200)
  // not_bear = alcista + lateral ("alcista o como mucho lateral").
  const spy = (hist['SPY'] || []).slice();
  { const now = new Date();   // misma regla que los ratios: la barra de hoy puede ser parcial hasta ~21 UTC
    if (spy.length && spy[spy.length - 1].date === now.toISOString().slice(0, 10) && now.getUTCHours() < 21) spy.pop(); }
  const regimeByDate = {};
  { let s50 = 0, s200 = 0;
    for (let k = 0; k < spy.length; k++) {
      s50 += spy[k].close; if (k >= 50) s50 -= spy[k - 50].close;
      s200 += spy[k].close; if (k >= 200) s200 -= spy[k - 200].close;
      if (k < 199) continue;                      // SMA200 necesita 200 barras
      const c = spy[k].close, m50 = s50 / 50, m200 = s200 / 200;
      regimeByDate[spy[k].date] = c < m200 ? 'bear' : (c >= m50 && m50 >= m200 ? 'bull' : 'lateral');
    } }
  const regimeAt = date => {                       // fecha exacta o la ultima anterior (ratios con calendario distinto)
    if (regimeByDate[date]) return regimeByDate[date];
    for (let k = spy.length - 1; k >= 0; k--) if (spy[k].date <= date) return regimeByDate[spy[k].date] || null;
    return null;
  };

  // Universo: por (h, fecha de entrada) la lista de retornos de todos los ratios
  const uni = Object.fromEntries(HORIZONS.map(h => [h, {}]));
  const uniM = Object.fromEntries(HORIZONS.map(h => [h, {}]));   // solo ratios contra el mercado
  const pooled = Object.fromEntries(HORIZONS.map(h => [h, { n: 0, sum: 0, pos: 0 }]));
  for (const { ratio, entry } of Object.values(R)) {
    const mk = isMarketPair(entry.pair);
    for (let e = 0; e < ratio.length; e++) {
      for (const h of HORIZONS) {
        const x = fwd(ratio, e, h); if (x == null) continue;
        (uni[h][ratio[e].date] = uni[h][ratio[e].date] || []).push(x);
        if (mk) (uniM[h][ratio[e].date] = uniM[h][ratio[e].date] || []).push(x);
        const p = pooled[h]; p.n++; p.sum += x; if (x > 0) p.pos++;
      }
    }
  }
  const medCache = {};
  const uniMedian = (h, date) => { const k = h + '|' + date; if (!(k in medCache)) medCache[k] = median(uni[h][date] || []); return medCache[k]; };
  const medCacheM = {};
  const uniMedianM = (h, date) => { const k = h + '|' + date; if (!(k in medCacheM)) medCacheM[k] = median(uniM[h][date] || []); return medCacheM[k]; };

  // Cada evento -> entrada ejecutable e = i+1 y sus retornos
  // Un evento de salto del flow change se expande en tramos (cada uno es una "señal" distinta con su
  // propia independencia): abs = puntos absolutos de la página; z = relativo a la volatilidad propia
  // del ratio; cross0 = el salto cruza el flow change por cero; coh = coincide con el filtro de
  // coherencia de la página (score/trend de acuerdo).
  const variantsOf = ev => {
    if (ev.event !== 'flow_jump_up' && ev.event !== 'flow_jump_down') return [ev.event];
    const b = ev.event, out = [], ad = Math.abs(ev.d_flow ?? 0), az = ev.z == null ? 0 : Math.abs(ev.z);
    if (ad >= 4) out.push(b + '_abs4'); if (ad >= 6) out.push(b + '_abs6'); if (ad >= 8) out.push(b + '_abs8');
    if (az >= 2.5) out.push(b + '_z25'); if (az >= 3.5) out.push(b + '_z35');
    if (ev.cross0) out.push(b + '_cross0');
    if (ev.coherent) out.push(b + '_coh');
    return out;
  };
  const evs = [];            // eventos expandidos (para las tablas por señal)
  const evsBase = [];        // eventos base, uno por fila del log (para "recientes")
  const lastIdxByKey = {};
  const sorted = [...events].sort((a, b) => a.date.localeCompare(b.date));
  for (const ev0 of sorted) {
    const rr = R[ev0.ratio_id]; if (!rr) continue;
    const ev = { ...ev0, pair: `${rr.entry.a}/${rr.entry.b}`, type: rr.entry.type };
    const i = rr.idx[ev.date]; if (i == null) continue;
    const e = i + 1;
    const entryDate = e < rr.ratio.length ? rr.ratio[e].date : null;
    const sign = ev.direction === 'in' ? 1 : -1;
    const per = {};
    for (const h of HORIZONS) {
      const x = entryDate ? fwd(rr.ratio, e, h) : null;
      if (x == null) { per[h] = null; continue; }
      const m = uniMedian(h, entryDate);
      const mm = uniMedianM(h, entryDate);
      per[h] = { raw: x, signed: sign * x, excess: sign * (x - (m ?? 0)), excess_m: sign * (x - (mm ?? 0)) };
    }
    const market = isMarketPair(rr.entry.pair), regime = regimeAt(ev.date);
    evsBase.push({ ev, entryDate, per, i, e, rr, market, regime });
    for (const v of variantsOf(ev)) {
      const key = ev.ratio_id + '|' + v;
      const independent = !(key in lastIdxByKey) || (i - lastIdxByKey[key] > COOLDOWN_BARS);
      lastIdxByKey[key] = i;
      evs.push({ ev: { ...ev, event: v }, independent, entryDate, per, i, e, rr, market, regime });
    }
  }

  const stats = (rows, h, useM) => {
    const m = rows.map(r => r.per[h]).filter(Boolean);
    if (!m.length) return { n_matured: 0 };
    const sg = m.map(x => x.signed), ex = m.map(x => useM ? x.excess_m : x.excess);
    return {
      n_matured: m.length,
      mean_signed: r2(mean(sg)), median_signed: r2(median(sg)),
      mean_excess: r2(mean(ex)), median_excess: r2(median(ex)),
      hit_rate: r2(sg.filter(x => x > 0).length / m.length * 100, 0),
      hit_rate_excess: r2(ex.filter(x => x > 0).length / m.length * 100, 0),
      t_excess: r2(tstat(ex), 1),
      conclusive: m.length >= MIN_N_CONCLUSIVE,
    };
  };
  const agg = (rows, useM) => ({
    independent_events: rows.length,
    from: rows.length ? rows.reduce((a, r) => r.ev.date < a ? r.ev.date : a, rows[0].ev.date) : null,
    horizons: Object.fromEntries(HORIZONS.map(h => [h, stats(rows, h, useM)])),
  });

  const indep = evs.filter(x => x.independent);
  const names = [...new Set(evs.map(x => x.ev.event))];
  const event_direction = Object.fromEntries(names.map(nm => [nm, evs.find(x => x.ev.event === nm).ev.direction]));
  // groups[universo][regimen][fuente][evento]: universo all|market, regimen all|bull|lateral|bear|not_bear,
  // fuente all|live|backfill. En 'market' el exceso se mide contra la mediana de los ratios contra el mercado.
  const REGIME_SETS = { all: null, bull: ['bull'], lateral: ['lateral'], bear: ['bear'], not_bear: ['bull', 'lateral'] };
  const groups = {};
  for (const uni_ of ['all', 'market']) {
    const useM = uni_ === 'market';
    const base = indep.filter(x => !useM || x.market);
    for (const [rg, set] of Object.entries(REGIME_SETS)) {
      const inReg = base.filter(x => !set || (x.regime && set.includes(x.regime)));
      for (const src of ['all', 'live', 'backfill']) {
        const inSrc = inReg.filter(x => src === 'all' || x.ev.source === src);
        const bucket = {};
        for (const nm of names) {
          const rows = inSrc.filter(x => x.ev.event === nm);
          if (rows.length) bucket[nm] = agg(rows, useM);
        }
        if (Object.keys(bucket).length) {
          groups[uni_] = groups[uni_] || {};
          groups[uni_][rg] = groups[uni_][rg] || {};
          groups[uni_][rg][src] = bucket;
        }
      }
    }
  }
  // Compat. con el resumen de consola y el analisis rapido (universo completo, todo regimen/fuente)
  const by_event = {}, by_event_type = {};
  for (const nm of names) {
    by_event[nm] = { ...(groups.all?.all?.all?.[nm] || agg([])), direction: event_direction[nm] };
    for (const tp of [...new Set(indep.filter(x => x.ev.event === nm).map(x => x.ev.type))]) {
      (by_event_type[nm] = by_event_type[nm] || {})[tp] = agg(indep.filter(x => x.ev.event === nm && x.ev.type === tp));
    }
  }
  const regimeDays = {}; Object.values(regimeByDate).forEach(r => { regimeDays[r] = (regimeDays[r] || 0) + 1; });
  const lastSpy = spy.length ? spy[spy.length - 1].date : null;

  // Eventos recientes con lo que llevan hecho hasta hoy (todos, no solo independientes)
  const cutoff = new Date(Date.now() - RECENT_DAYS * 86400000).toISOString().slice(0, 10);
  // Evolución del flow change (el de la tabla de la página) desde la barra de la señal hasta hoy,
  // para el sparkline. Se cachea por ratio+barra: varios eventos del mismo ratio comparten barras.
  const fcCache = {};
  const flowAt = (rr, j) => {
    const k = rr.entry.id + '|' + j;
    if (!(k in fcCache)) { const row = lib.buildRowFromRatio(rr.entry, rr.ratio.slice(0, j + 1)); fcCache[k] = row.error ? null : r2(row.flowChange, 1); }
    return fcCache[k];
  };
  const recent = evsBase.filter(x => x.ev.date >= cutoff).map(x => {
    const ratio = x.rr.ratio;
    const flow_path = []; for (let j = x.i; j < ratio.length; j++) flow_path.push(flowAt(x.rr, j));
    const toDate = x.e < ratio.length ? (ratio[ratio.length - 1].value / ratio[x.e].value - 1) * 100 : null;
    return {
      date: x.ev.date, ratio_id: x.ev.ratio_id, pair: x.ev.pair, type: x.ev.type, event: x.ev.event, direction: x.ev.direction,
      vs_market: x.market, regime: x.regime, source: x.ev.source, label: x.ev.label, score: x.ev.score, flow_change: x.ev.flow_change ?? null, d_flow: x.ev.d_flow ?? null, z: x.ev.z ?? null, entry_date: x.entryDate, flow_path,
      bars_since_entry: x.e < ratio.length ? ratio.length - 1 - x.e : null,
      ret_to_date: r2(toDate), signed_to_date: r2(toDate == null ? null : (x.ev.direction === 'in' ? 1 : -1) * toDate),
      by_horizon: Object.fromEntries(HORIZONS.map(h => [h, x.per[h] ? r2(x.per[h].signed) : null])),
    };
  }).sort((a, b) => b.date.localeCompare(a.date) || a.ratio_id.localeCompare(b.ratio_id));

  const lastDate = Object.values(R).map(r => r.ratio[r.ratio.length - 1].date).sort().pop();
  return {
    generated_at: new Date().toISOString(), last_bar_date: lastDate,
    horizons_sessions: HORIZONS, cooldown_bars: COOLDOWN_BARS, min_n_conclusive: MIN_N_CONCLUSIVE,
    n_ratios: Object.keys(R).length, n_events_logged: events.length,
    live_events: events.filter(e => e.source === 'live').length,
    baseline_all_ratio_days: Object.fromEntries(HORIZONS.map(h => [h, {
      n: pooled[h].n, mean: r2(pooled[h].sum / pooled[h].n, 3), hit_rate: r2(pooled[h].pos / pooled[h].n * 100, 0),
    }])),
    event_direction, groups, by_event, by_event_type, recent_events: recent,
    market_bench: [...MARKET_BENCH], n_ratios_vs_market: Object.values(R).filter(r => isMarketPair(r.entry.pair)).length,
    regime_definition: 'SPY: bajista = cierre < SMA200 · alcista = cierre >= SMA200 y >= SMA50 y SMA50 >= SMA200 · lateral = resto por encima de SMA200',
    regime_days: regimeDays, current_regime: lastSpy ? regimeAt(lastSpy) : null,
  };
}

function printSummary(rep) {
  console.log(`\nInforme (barras hasta ${rep.last_bar_date}, ${rep.n_ratios} ratios, ${rep.n_events_logged} eventos, ${rep.live_events} live)`);
  for (const [nm, d] of Object.entries(rep.by_event)) {
    const cell = h => { const x = d.horizons[h]; return x.n_matured ? `${x.mean_excess >= 0 ? '+' : ''}${x.mean_excess}/${x.hit_rate_excess}%(n${x.n_matured})` : '—'; };
    console.log(`  ${nm.padEnd(14)} [${d.direction}] indep ${String(d.independent_events).padStart(5)} | 1s ${cell(1)} | 5s ${cell(5)} | 21s ${cell(21)}`);
  }
}

main().catch(e => { console.error(e); process.exit(1); });
