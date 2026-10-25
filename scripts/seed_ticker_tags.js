#!/usr/bin/env node
/*
 * seed_ticker_tags.js — siembra / actualiza la taxonomía de etiquetas del Portfolio (línea A).
 *
 * Entrada:  scripts/ticker_tags_seed.json   (vocabulario + 130 tickers; generado del Anexo A v2 del diseño)
 *           docs/data/ticker_yahoo_meta.json (nombre legal provisional; solo referencia)
 * Salida:   docs/data/ticker_tags.json + ticker_tags_events.jsonl (vía el almacén) y docs/analysis/ticker_tags_review.md
 *
 * Reglas de fusión (nunca pierde trabajo humano):
 *   · Solo AÑADE lo que falta. No modifica, re-añade ni borra una asignación que esté confirmed, rejected,
 *     retirada o cuyo `source` no sea el de la siembra ('assistant').
 *   · Una propuesta pendiente de la misma fuente SÍ se actualiza si el seed cambia.
 *   · Una asignación rechazada o retirada no vuelve a proponerse.
 *   · Idempotente: una segunda ejecución no genera operaciones.
 *   · Todas las identidades se siembran `provisional` (Yahoo solo nunca da `verified`).
 *
 * Uso:   node scripts/seed_ticker_tags.js [--dry-run] [--allow-any-host] [--no-report]
 */
'use strict';

const fs = require('fs');
const path = require('path');
const Tags = require('../shared/ticker-tags-lib');
const { createStore } = require('../shared/ticker-tags-store');

const ROOT = path.resolve(__dirname, '..');
const SEED_SOURCE = 'assistant';

/** Plan determinista de operaciones. `state` no se modifica (se simula sobre una copia). */
function planSeedOps(state, seed, yahoo, now) {
  const ts = (now || new Date()).toISOString();
  const checkedAt = ((yahoo && yahoo.fetched_at) || ts).slice(0, 10);
  const work = Tags.clone(state);
  const ops = [];
  const stats = { tags: 0, issuers: 0, instruments: 0, assigned: 0, updated: 0, skipped_protected: 0 };

  const push = (op, args) => { const r = Tags.applyOp(work, op, args, ts); ops.push({ op, args }); return r; };

  for (const t of seed.vocabulary) {
    if (!work.tags[t.tag]) { push('create_tag', { tag: t.tag, label: t.label, parent: t.parent || undefined }); stats.tags++; }
  }

  const issuerByKey = {};
  const yMeta = (tk) => (yahoo && yahoo.tickers && yahoo.tickers[tk]) || {};

  for (const row of seed.tickers) {
    let found = Tags.resolveInstrument(work, row.ticker);
    let issuerId;
    if (found) issuerId = found.inst.issuer_id;
    else {
      issuerId = issuerByKey[row.issuer_key];
      if (!issuerId) {
        const sibling = seed.tickers.filter(x => x.issuer_key === row.issuer_key).map(x => x.ticker);
        const sources = [];
        for (const tk of sibling) if (yMeta(tk).longName) sources.push({ type: 'yahoo', ref: `quoteSummary ${tk}`, checked_at: checkedAt });
        sources.push({ type: 'assistant', ref: 'DISENO_PORTFOLIO_TAGS_DEFINITIVO v2 · Anexo A', checked_at: ts.slice(0, 10) });
        const legal = yMeta(row.ticker).longName || row.annex_name;
        const r = push('create_issuer', { legal_name: legal, identity_status: 'provisional', identity_sources: sources, notes: row.note || '' });
        issuerId = r.id; issuerByKey[row.issuer_key] = issuerId; stats.issuers++;
      }
      push('create_instrument', { ticker: row.ticker, issuer_id: issuerId, role: row.role, leveraged: !!row.leveraged });
      stats.instruments++;
    }
    issuerByKey[row.issuer_key] = issuerId;

    const wanted = [];
    if (row.industry) wanted.push({ tag: row.industry });
    if (row.stage) wanted.push({ tag: row.stage });
    if (row.asset_class) wanted.push({ tag: row.asset_class });
    for (const a of row.assignments) wanted.push(a);

    for (const w of wanted) {
      const issuer = work.issuers[issuerId];
      const existing = issuer.assignments.find(a => a.tag === w.tag);
      const want = { relation: w.relation || null, intensity: w.intensity || null, nav_primary: !!w.nav_primary, confidence: row.confidence };
      if (!existing) {
        push('assign', { issuer_id: issuerId, tag: w.tag, relation: want.relation, intensity: want.intensity, nav_primary: want.nav_primary,
          source: SEED_SOURCE, confidence: want.confidence, review_status: 'pending', note: '' });
        stats.assigned++;
        continue;
      }
      if (existing.removed_at || existing.review_status !== 'pending' || existing.source !== SEED_SOURCE) { stats.skipped_protected++; continue; }
      const changes = {};
      for (const k of ['relation', 'intensity', 'confidence']) if (existing[k] !== want[k]) changes[k] = want[k];
      if (Object.keys(changes).length) { push('update_assignment', { issuer_id: issuerId, aid: existing.aid, changes }); stats.updated++; }
      if (existing.nav_primary !== want.nav_primary && (want.nav_primary || existing.nav_primary)) {
        push('set_nav_primary', { issuer_id: issuerId, aid: existing.aid, value: want.nav_primary }); stats.updated++;
      }
    }
  }
  return { ops, stats, finalState: work };
}

// ── informe de revisión ──────────────────────────────────────────────────────
function buildReport(state, seed, yahoo) {
  const lines = [];
  const L = (s) => lines.push(s === undefined ? '' : s);
  const bySeed = Object.fromEntries(seed.tickers.map(t => [t.ticker, t]));
  const all = Object.values(state.instruments).map(i => i.ticker).sort();
  const ass = (tk) => (Tags.view(state, tk) || { assignments: [] }).assignments;
  const counts = { pending: 0, confirmed: 0, rejected: 0 };
  for (const is of Object.values(state.issuers)) for (const a of is.assignments.filter(x => !x.removed_at)) counts[a.review_status]++;
  L('# Revisión de etiquetas del Portfolio'); L();
  L('_Generado por `scripts/seed_ticker_tags.js`. Todas las asignaciones sembradas son **propuestas** (`source: assistant`, `review_status: pending`)._'); L();
  L(`- Instrumentos: **${all.length}** · emisores: **${Object.keys(state.issuers).length}** · etiquetas en el vocabulario: **${Object.keys(state.tags).length}**`);
  L(`- Asignaciones activas: pendientes **${counts.pending}** · confirmadas **${counts.confirmed}** · rechazadas **${counts.rejected}**`);
  L(`- Identidades: ${Object.values(state.issuers).filter(i => i.identity_status === 'provisional').length} provisionales, ${Object.values(state.issuers).filter(i => i.identity_status === 'verified').length} verificadas (Yahoo solo nunca verifica).`); L();
  L('## Revisar primero'); L();
  L('Tickers con confianza baja o media en alguna asignación. La columna Yahoo es solo referencia (no prueba de identidad).'); L();
  L('| Ticker | Empresa (Yahoo) | Confianza | Industria propuesta | Sector / industria Yahoo | Nota |'); L('|---|---|---|---|---|---|');
  for (const tk of all) {
    const row = bySeed[tk]; if (!row || row.confidence === 'high') continue;
    const y = (yahoo.tickers || {})[tk] || {};
    const ind = row.industry ? Tags.tagLabel(state, row.industry) : (row.asset_class ? Tags.tagLabel(state, row.asset_class) : '—');
    L(`| ${tk} | ${y.longName || row.annex_name} | ${row.confidence === 'low' ? '🔴 baja' : '🟠 media'} | ${ind} | ${[y.sector, y.industry].filter(Boolean).join(' / ') || '—'} | ${row.note || ''} |`);
  }
  L(); L('## Casos donde Yahoo y la propuesta difieren mucho'); L();
  L('Yahoo describe el sector contable; la propuesta describe la exposición económica. Estos casos son los esperables:'); L();
  const notable = ['MSTR', 'VFF', 'ASTS', 'GLEN.L', 'AFM.V', 'COIN', 'CORZ', 'HFG.DE', 'SE'];
  L('| Ticker | Yahoo | Propuesta (exposición principal) |'); L('|---|---|---|');
  for (const tk of notable) {
    const y = (yahoo.tickers || {})[tk]; const v = Tags.view(state, tk); if (!y || !v) continue;
    const prim = v.assignments.filter(a => a.nav_primary).map(a => Tags.tagLabel(state, a.tag)).join(', ') || '—';
    L(`| ${tk} | ${[y.sector, y.industry].filter(Boolean).join(' / ')} | ${prim} |`);
  }
  L(); L('## Grupos que nacen pequeños'); L();
  const sizes = {};
  for (const tk of all) for (const a of ass(tk)) if (a.relation && a.relation !== 'narrative') sizes[a.tag] = (sizes[a.tag] || new Set()).add(tk);
  const small = Object.entries(sizes).filter(([t, s]) => s.size <= 2 && (t.startsWith('theme:') || t.startsWith('commodity:'))).sort();
  for (const [t, s] of small) L(`- ${Tags.tagLabel(state, t)} (\`${t}\`): ${[...s].join(', ')}`);
  L(); L('## Cómo revisar'); L();
  L('Abre `portfolio.html`, agrupa por la dimensión que quieras y confirma o rechaza las asignaciones desde el botón 🏷 de cada fila. '
    + 'Las confirmadas, rechazadas o editadas a mano **no se vuelven a tocar** al re-sembrar.');
  return lines.join('\n') + '\n';
}

function main() {
  const argv = process.argv.slice(2);
  const dry = argv.includes('--dry-run');
  const dataDir = path.join(ROOT, 'docs', 'data');
  const seed = JSON.parse(fs.readFileSync(path.join(__dirname, 'ticker_tags_seed.json'), 'utf8'));
  let yahoo = { tickers: {} };
  try { yahoo = JSON.parse(fs.readFileSync(path.join(dataDir, 'ticker_yahoo_meta.json'), 'utf8')); } catch (_) { /* sin Yahoo: se usa el nombre del Anexo */ }
  const store = createStore({ dataDir, repoRoot: ROOT });
  const snap = store.snapshot();
  if (snap.integrity) { console.error('Almacén con problemas de integridad:', snap.integrity.message); return 1; }
  const plan = planSeedOps(snap.state, seed, yahoo);
  console.log(`Plan: ${plan.ops.length} operaciones`, JSON.stringify(plan.stats));
  const problems = Tags.validateState(plan.finalState);
  if (problems.length) { console.error('El estado resultante no cumple las invariantes:\n - ' + problems.join('\n - ')); return 1; }
  if (dry || !plan.ops.length) {
    if (!plan.ops.length) console.log('Nada que hacer (idempotente).');
  } else {
    if (!argv.includes('--allow-any-host') && !store.writerStatus().enabled) {
      console.error('Esta máquina no es el escritor. Define TICKER_TAGS_WRITER_HOST o usa --allow-any-host (solo para la siembra inicial).');
      return 1;
    }
    store.applyBatch(plan.ops, { actor: 'seed', skipWriterCheck: true }).then(r => {
      console.log(`Aplicadas ${plan.ops.length} operaciones → revisión ${r.revision}`);
      if (!argv.includes('--no-report')) writeReport(store, seed, yahoo);
    }).catch(e => { console.error('Error:', e.code || '', e.message, e.details ? JSON.stringify(e.details).slice(0, 400) : ''); process.exitCode = 1; });
    return 0;
  }
  if (!argv.includes('--no-report') && !dry) writeReport(store, seed, yahoo);
  return 0;
}

function writeReport(store, seed, yahoo) {
  const dir = path.join(ROOT, 'docs', 'analysis'); fs.mkdirSync(dir, { recursive: true });
  const out = path.join(dir, 'ticker_tags_review.md');
  fs.writeFileSync(out, buildReport(store.snapshot().state, seed, yahoo), 'utf8');
  console.log('Informe →', path.relative(ROOT, out));
}

if (require.main === module) process.exitCode = main();
module.exports = { planSeedOps, buildReport };
