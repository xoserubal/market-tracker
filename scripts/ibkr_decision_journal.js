#!/usr/bin/env node
// ── Diario de decisiones: operaciones reales de IBKR × contexto de señales ──
// SOLO LOCAL. Lee tus operaciones reales (private/ibkr/ibkr_trades.jsonl) y las
// cruza con lo que mostraba el sistema ese día (portfolio_daily_snapshot.jsonl
// + screener_signal_log.jsonl). Salida en private/ibkr/ (en .gitignore): el
// repo es público y esto son operaciones reales.
//
// Pregunta que responde: "cuando abrí posiciones, ¿qué decían las señales, y
// qué hizo el subyacente después, comparado con el universo?" — la misma
// disciplina que ya se aplica a las carteras automáticas, pero sobre tus
// decisiones discrecionales.
//
// LÍMITES — leer antes de sacar conclusiones:
//  - El contexto de señales solo existe desde 2026-08-20 (arranque de
//    portfolio_daily_snapshot.jsonl). Las operaciones anteriores se listan
//    sin contexto: no se reconstruye nada retroactivamente aquí.
//  - Una opción o una acción puede ser cobertura, spread o parte de una
//    estructura: el "sesgo" (alcista/bajista) se INFIERE del lado de la
//    operación (comprar call / vender put = alcista…) y puede no ser la
//    intención real. Un spread cuenta como dos operaciones de sesgo opuesto.
//  - n es pequeño (decenas): no concluyente hasta acumular mucho más.
//  - El retorno medido es el del SUBYACENTE, no el P&L de la opción.
//
// CLI:
//   node scripts/ibkr_decision_journal.js            # reconstruye y resume
//   node scripts/ibkr_decision_journal.js --no-write

const fs   = require('fs');
const path = require('path');
const { ibkrTrackerTicker, ibkrUnderlying } = require('../shared/ibkr-map.js');
const { makeTools, readJsonl, HORIZONS, addDays, daysBetween, median, mean, r2 } = require('./screener_signal_report.js');

const ROOT = path.join(__dirname, '..');
const PRIVATE_DIR = process.env.IBKR_PRIVATE_DIR || path.join(ROOT, 'private', 'ibkr');
const TRADES = path.join(PRIVATE_DIR, 'ibkr_trades.jsonl');
const OUT_JOURNAL = path.join(PRIVATE_DIR, 'decision_journal.jsonl');
const OUT_SUMMARY = path.join(PRIVATE_DIR, 'decision_journal_summary.json');
const SNAPSHOT = path.join(ROOT, 'docs', 'data', 'portfolio_daily_snapshot.jsonl');
const SCREENER_LOG = path.join(ROOT, 'docs', 'data', 'screener_signal_log.jsonl');
const PORTFOLIO = path.join(ROOT, 'portfolio.json');

const CONTEXT_MAX_STALE_DAYS = 3;     // fila de snapshot más cercana ≤ 3 días antes de la operación
const SCREENER_LOOKBACK_DAYS = 3;     // candidato ese día o en los 3 anteriores
const MIN_N = 30;

const CONTEXT_FIELDS = ['flowScore', 'earlyFlow', 'konc_d_state', 'konc_3d_state', 'konc_w_state', 'konc_alignment',
  'rsi', 'macdBull', 'macdHistDelta1', 'atlasSignal', 'atrPct', 'm1', 'fromHigh'];

// Sesgo inferido del lado de la operación de APERTURA. null = no inferible.
function inferBias(t) {
  const buy = String(t.side).toUpperCase().startsWith('B');
  const pc = String(t.put_call || '').toUpperCase();
  if (t.asset_class === 'STK' || t.asset_class === 'WAR') return buy ? 1 : -1;
  if (t.asset_class === 'OPT') {
    if (pc === 'C') return buy ? 1 : -1;
    if (pc === 'P') return buy ? -1 : 1;   // comprar put = bajista, vender put = alcista
  }
  return null;
}

// ── Notas manuales por DECISIÓN ─────────────────────────────────────────────
// Una decisión = todas las patas abiertas el mismo día sobre el mismo subyacente
// (un spread o una cobertura son UNA decisión con varias operaciones). Clave:
// "YYYY-MM-DD|SUBYACENTE". Texto libre del usuario: tesis, disparador e
// invalidación — escritos ANTES de saber cómo acaba, esa es la gracia. Fichero
// privado (decision_notes.json, en private/): son decisiones reales.
const NOTES_FILE = path.join(PRIVATE_DIR, 'decision_notes.json');
const NOTE_FIELDS = ['thesis', 'trigger', 'invalidation'];
const NOTE_MAX_LEN = 2000;
const KEY_RE = /^\d{4}-\d{2}-\d{2}\|[A-Za-z0-9.\-^_]{1,20}$/;

function decisionKey(t) { return t.date + '|' + ibkrUnderlying(t).toUpperCase(); }

function readNotes() {
  try { return JSON.parse(fs.readFileSync(NOTES_FILE, 'utf8')); } catch (e) { return {}; }
}

function saveNote(key, fields) {
  if (!KEY_RE.test(String(key || ''))) throw new Error('clave de decisión no válida');
  const notes = readNotes();
  const clean = {};
  NOTE_FIELDS.forEach(f => { clean[f] = String((fields || {})[f] ?? '').trim().slice(0, NOTE_MAX_LEN); });
  if (!NOTE_FIELDS.some(f => clean[f])) delete notes[key];       // todo vacío → se borra la nota
  else notes[key] = { ...clean, updated_at: new Date().toISOString() };
  fs.mkdirSync(PRIVATE_DIR, { recursive: true });
  fs.writeFileSync(NOTES_FILE, JSON.stringify(notes, null, 2));
  return notes[key] || null;
}

function legLabel(t) {
  const und = ibkrUnderlying(t);
  if (t.asset_class !== 'OPT' && t.asset_class !== 'FOP') return und;
  const e = t.expiry ? `${t.expiry.slice(8, 10)}/${t.expiry.slice(5, 7)}/${t.expiry.slice(2, 4)}` : '?';
  return `${und} ${e} ${t.strike ?? '?'} ${t.put_call ?? ''}`.trim();
}

// Decisiones recientes (aperturas de los últimos `days` días) con su nota.
function getDecisionGroups(days = 60) {
  const trades = readJsonl(TRADES).filter(t => t.open_close === 'O' && t.asset_class !== 'CASH');
  const since = addDays(new Date().toISOString().slice(0, 10), -days);
  const portfolio = JSON.parse(fs.readFileSync(PORTFOLIO, 'utf8'));
  const trackerTickers = new Set((portfolio.sections || []).flatMap(s => (s.items || []).map(i => i.ticker)));
  const notes = readNotes();
  const groups = new Map();
  trades.filter(t => t.date >= since).forEach(t => {
    const key = decisionKey(t);
    if (!groups.has(key)) groups.set(key, { key, date: t.date, underlying: ibkrUnderlying(t), tracker_ticker: ibkrTrackerTicker(t, trackerTickers), legs: [] });
    groups.get(key).legs.push({ label: legLabel(t), side: t.side, quantity: t.quantity, price: t.price, asset_class: t.asset_class });
  });
  return [...groups.values()].map(g => ({ ...g, note: notes[g.key] || null }))
    .sort((a, b) => b.date.localeCompare(a.date) || a.underlying.localeCompare(b.underlying));
}

function buildJournal() {
  const trades = readJsonl(TRADES);
  if (!trades.length) throw new Error('Sin operaciones: sincroniza primero (node scripts/ibkr_flex_sync.js)');
  const snap = readJsonl(SNAPSHOT);
  const screener = readJsonl(SCREENER_LOG);
  const portfolio = JSON.parse(fs.readFileSync(PORTFOLIO, 'utf8'));
  const trackerTickers = new Set((portfolio.sections || []).flatMap(s => (s.items || []).map(i => i.ticker)));
  const tools = makeTools(snap);
  const snapStart = snap.reduce((d, r) => (!d || r.date < d ? r.date : d), '');

  const snapByTicker = {};
  snap.forEach(r => { (snapByTicker[r.ticker] = snapByTicker[r.ticker] || []).push(r); });
  Object.values(snapByTicker).forEach(a => a.sort((x, y) => x.date.localeCompare(y.date)));
  const flagsByTicker = {};
  screener.forEach(r => { (flagsByTicker[r.ticker] = flagsByTicker[r.ticker] || []).push(r); });

  const openings = trades.filter(t => t.open_close === 'O' && t.asset_class !== 'CASH');
  const allNotes = readNotes();
  const rows = openings.map(t => {
    const tk = ibkrTrackerTicker(t, trackerTickers);
    const bias = inferBias(t);
    const row = {
      trade_id: t.trade_id, date: t.date, symbol: String(t.symbol).trim(), tracker_ticker: tk,
      asset_class: t.asset_class, side: t.side, quantity: t.quantity, price: t.price, currency: t.currency,
      put_call: t.put_call ?? null, strike: t.strike ?? null, expiry: t.expiry ?? null,
      inferred_bias: bias, context_available: false, context: null, screener_flags: [], fwd: {},
      decision_key: decisionKey(t), note: allNotes[decisionKey(t)] || null,
    };
    if (!tk) { row.note = 'sin ticker equivalente en Portfolio Tracker'; return row; }
    if (t.date < snapStart) { row.note = `anterior al snapshot diario (${snapStart})`; return row; }

    // contexto: última fila del snapshot ≤ fecha de la operación
    const rowsT = snapByTicker[tk] || [];
    let ctxRow = null;
    for (const r of rowsT) { if (r.date <= t.date) ctxRow = r; else break; }
    if (!ctxRow || daysBetween(ctxRow.date, t.date) > CONTEXT_MAX_STALE_DAYS) { row.note = 'sin fila de snapshot cercana'; return row; }
    row.context_available = true;
    row.context_date = ctxRow.date;
    row.context = {};
    CONTEXT_FIELDS.forEach(k => { row.context[k] = ctxRow[k] !== undefined ? ctxRow[k] : null; });

    const from = addDays(t.date, -SCREENER_LOOKBACK_DAYS);
    row.screener_flags = [...new Set((flagsByTicker[tk] || []).filter(f => f.date >= from && f.date <= t.date).map(f => f.filter))];

    HORIZONS.forEach(h => {
      const ret = tools.fwd(tk, t.date, h);
      const ref = tools.universeMedian(t.date, h);
      if (ret == null || ref == null) return;
      row.fwd[h + 'd'] = { ret: r2(ret), excess: r2(ret - ref), signed_ret: bias == null ? null : r2(bias * ret), signed_excess: bias == null ? null : r2(bias * (ret - ref)) };
    });
    return row;
  });

  // Realizado por subyacente (toda la ventana de 365 días, con o sin contexto):
  // P&L realizado en divisa base de las operaciones de CIERRE.
  const realized = {};
  trades.filter(t => t.open_close === 'C' && typeof t.realized_pnl === 'number').forEach(t => {
    const tk = ibkrTrackerTicker(t, trackerTickers) || String(t.symbol).trim().split(/\s+/)[0];
    realized[tk] = (realized[tk] || 0) + t.realized_pnl * (t.fx_to_base ?? 1);
  });

  // Resumen
  const withCtx = rows.filter(r => r.context_available);
  const summarize = list => {
    const out = {};
    HORIZONS.forEach(h => {
      const v = list.map(r => r.fwd[h + 'd']).filter(Boolean);
      const sr = v.map(x => x.signed_ret).filter(x => x != null);
      const se = v.map(x => x.signed_excess).filter(x => x != null);
      out[h + 'd'] = { n: se.length, mean_signed_ret: r2(mean(sr)), mean_signed_excess: r2(mean(se)), median_signed_excess: r2(median(se)),
        hit_rate: se.length ? r2(se.filter(x => x > 0).length / se.length * 100) : null, conclusive: se.length >= MIN_N };
    });
    return out;
  };
  const flagged = withCtx.filter(r => r.screener_flags.length);
  const unflagged = withCtx.filter(r => !r.screener_flags.length);
  const summary = {
    generated_at: new Date().toISOString(), snapshot_start: snapStart,
    trades_total: trades.length, openings_total: openings.length, openings_with_context: withCtx.length,
    openings_without_context: openings.length - withCtx.length,
    flagged_by_screener: flagged.length, unflagged: unflagged.length,
    decisions_total: new Set(rows.map(r => r.decision_key)).size,
    decisions_with_note: new Set(rows.filter(r => r.note).map(r => r.decision_key)).size,
    all_with_context: summarize(withCtx), with_screener_flag: summarize(flagged), without_screener_flag: summarize(unflagged),
    realized_pnl_base_by_underlying: Object.fromEntries(Object.entries(realized).map(([k, v]) => [k, r2(v)]).sort((a, b) => a[1] - b[1])),
    caveats: ['sesgo inferido del lado de la operación (puede ser cobertura/spread)', 'retorno del subyacente, no P&L de la opción',
      'contexto solo desde ' + snapStart, 'n pequeño — no concluyente por debajo de ' + MIN_N],
  };
  return { rows, summary };
}

function print(summary) {
  console.log(`Diario de decisiones — ${summary.openings_total} aperturas en ${summary.trades_total} operaciones`);
  console.log(`Con contexto de señales (desde ${summary.snapshot_start}): ${summary.openings_with_context} · sin contexto: ${summary.openings_without_context}`);
  console.log(`De las que tienen contexto: ${summary.flagged_by_screener} coincidían con un candidato del screener (hoy o ≤${SCREENER_LOOKBACK_DAYS} días antes), ${summary.unflagged} no\n`);
  const show = (label, s) => {
    console.log(label);
    Object.entries(s).forEach(([h, x]) => console.log(`   ${h.padEnd(4)} n=${String(x.n).padStart(3)}  ret firmado medio ${String(x.mean_signed_ret).padStart(6)}%  exceso firmado medio ${String(x.mean_signed_excess).padStart(6)} (mediana ${x.median_signed_excess})  aciertos ${x.hit_rate}%  ${x.conclusive ? '' : '⚠ no concluyente'}`));
  };
  show('■ Todas las aperturas con contexto (retorno del subyacente × sesgo inferido):', summary.all_with_context);
  show('■ Las que coincidían con un candidato del screener:', summary.with_screener_flag);
  show('■ Las que NO coincidían:', summary.without_screener_flag);
  const rz = Object.entries(summary.realized_pnl_base_by_underlying);
  if (rz.length) {
    console.log('\nP&L realizado (365 días, divisa base) — peores y mejores subyacentes:');
    console.log('   peores: ' + rz.slice(0, 5).map(([k, v]) => `${k} ${v}`).join(' · '));
    console.log('   mejores: ' + rz.slice(-5).reverse().map(([k, v]) => `${k} ${v}`).join(' · '));
    console.log('   total: ' + r2(rz.reduce((a, [, v]) => a + v, 0)));
  }
}

function writeJournal() {
  const { rows, summary } = buildJournal();
  fs.mkdirSync(PRIVATE_DIR, { recursive: true });
  fs.writeFileSync(OUT_JOURNAL, rows.map(r => JSON.stringify(r)).join('\n') + '\n');
  fs.writeFileSync(OUT_SUMMARY, JSON.stringify(summary, null, 2));
  return { rows, summary };
}

function readSummary() {
  try { return JSON.parse(fs.readFileSync(OUT_SUMMARY, 'utf8')); } catch (e) { return null; }
}

if (require.main === module) {
  if (process.argv.includes('--no-write')) {
    print(buildJournal().summary);
  } else {
    const { summary } = writeJournal();
    print(summary);
    console.log('\nEscrito private/ibkr/decision_journal.jsonl y decision_journal_summary.json');
  }
}
module.exports = { buildJournal, writeJournal, readSummary, inferBias, getDecisionGroups, saveNote, readNotes, decisionKey };
