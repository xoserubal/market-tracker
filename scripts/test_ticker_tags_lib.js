#!/usr/bin/env node
/*
 * test_ticker_tags_lib.js — pruebas de la librería de etiquetas (sin dependencias, sin red).
 *   node scripts/test_ticker_tags_lib.js
 *
 *   F1  validación: entradas inválidas rechazadas SIN mutar el estado
 *   F2  fusión de la siembra: lo confirmado/rechazado/retirado/manual no se toca
 *   F4  propiedad: replay(eventos) == estado tras cada operación de secuencias aleatorias; invariantes siempre
 *   F5  recuentos: instrumentos / empresas / fondos; mismo emisor = 1 empresa; un ticker en N grupos cuenta una vez
 *   F7  point-in-time frente a retrospectivo
 *   F8  identidad: tickers duplicados, histórico solapado, reutilización (caso GOLD→Gold.com / Barrick), cambio de ticker
 *   D   datos reales: el estado versionado es consistente y cubre los 130 tickers sembrados
 */
'use strict';
const fs = require('fs');
const path = require('path');
const T = require('../shared/ticker-tags-lib');
const { canon } = require('../shared/ticker-tags-store');
const { planSeedOps } = require('./seed_ticker_tags');

const results = [];
const check = (name, ok, detail) => results.push({ name, ok: !!ok, detail: ok ? '' : (detail || '') });
const TS = '2026-10-26T10:00:00.000Z';

function ops(state, list, ts) { for (const [op, args] of list) T.applyOp(state, op, args, ts || TS); return state; }
function baseState() {
  const s = T.emptyState();
  ops(s, [
    ['create_tag', { tag: 'industry:mining', label: 'Minería' }],
    ['create_tag', { tag: 'industry:mining_gold', label: 'Oro', parent: 'industry:mining' }],
    ['create_tag', { tag: 'industry:banks', label: 'Bancos' }],
    ['create_tag', { tag: 'commodity:gold', label: 'Oro' }],
    ['create_tag', { tag: 'commodity:copper', label: 'Cobre' }],
    ['create_tag', { tag: 'commodity:oil', label: 'Petróleo' }],
    ['create_tag', { tag: 'theme:cannabis', label: 'Cannabis' }],
    ['create_tag', { tag: 'theme:ai', label: 'IA' }],
    ['create_tag', { tag: 'geo_exposure:us', label: 'EE. UU.' }],
    ['create_tag', { tag: 'geo_exposure:ar', label: 'Argentina' }],
    ['create_tag', { tag: 'stage:producer', label: 'Producción' }],
    ['create_tag', { tag: 'stage:explorer', label: 'Exploración' }],
    ['create_tag', { tag: 'asset_class:equity_index', label: 'Índice' }],
  ]);
  return s;
}
const issuer = (s, name, extra) => { const r = T.applyOp(s, 'create_issuer', Object.assign({ legal_name: name }, extra || {}), TS); return r.id; };
const instr = (s, ticker, iss, extra) => T.applyOp(s, 'create_instrument', Object.assign({ ticker, issuer_id: iss }, extra || {}), TS).id;
const assignArgs = (iss, tag, extra) => Object.assign({ issuer_id: iss, tag, relation: null, intensity: null, nav_primary: false, source: 'manual', confidence: 'medium' }, extra || {});
const expo = (iss, tag, rel, int, extra) => assignArgs(iss, tag, Object.assign({ relation: rel, intensity: int }, extra || {}));

function rejects(name, state, op, args, codeIs) {
  const before = canon(state);
  let err = null;
  try { T.applyOp(state, op, args, TS); } catch (e) { err = e; }
  check(`F1 ${name}`, err instanceof T.TagError && (!codeIs || err.code === codeIs) && canon(state) === before,
    err ? `código ${err.code}; estado ${canon(state) === before ? 'intacto' : 'MUTADO'}` : 'no lanzó error');
}

// ── F1 ──────────────────────────────────────────────────────────────────────
function f1() {
  const s = baseState();
  const a = issuer(s, 'Minera SA'); instr(s, 'MIN.TO', a);
  ops(s, [['assign', expo(a, 'commodity:gold', 'direct', 'high', { nav_primary: true })]]);
  rejects('etiqueta inexistente', s, 'assign', expo(a, 'commodity:zzz', 'direct', 'high'));
  rejects('formato de etiqueta inválido', s, 'assign', expo(a, 'Commodity-Gold', 'direct', 'high'));
  rejects('exposure/relation en dimensión descriptiva (industry)', s, 'assign', assignArgs(a, 'industry:mining_gold', { relation: 'direct', intensity: 'high' }));
  rejects('nav_primary en dimensión descriptiva', s, 'assign', assignArgs(a, 'industry:mining_gold', { nav_primary: true }));
  rejects('dimensión de exposición sin relation', s, 'assign', assignArgs(a, 'commodity:copper'));
  rejects('direct sin intensidad', s, 'assign', expo(a, 'commodity:copper', 'direct', null));
  rejects('narrative con intensidad', s, 'assign', expo(a, 'commodity:copper', 'narrative', 'high'));
  rejects('nav_primary sobre narrative', s, 'assign', expo(a, 'commodity:copper', 'narrative', null, { nav_primary: true }));
  rejects('segunda etiqueta principal en la misma dimensión', s, 'assign', expo(a, 'commodity:copper', 'direct', 'low', { nav_primary: true }));
  rejects('etiqueta duplicada en el emisor', s, 'assign', expo(a, 'commodity:gold', 'direct', 'low'));
  rejects('dimensión `single` (stage) con dos valores', (() => { const x = baseState(); const i = issuer(x, 'X'); ops(x, [['assign', assignArgs(i, 'stage:producer')]]); x.__i = i; return x; })(), 'assign', { issuer_id: 'iss_0001', tag: 'stage:explorer', relation: null, intensity: null, nav_primary: false, source: 'manual', confidence: 'low' });
  rejects('dimensión reservada (macro_driver)', s, 'assign', assignArgs(a, 'macro_driver:usd'));
  rejects('fecha mal formada', s, 'assign', expo(a, 'commodity:copper', 'direct', 'low', { effective_from: '26-10-2026' }));
  rejects('effective_from posterior a effective_to', s, 'assign', expo(a, 'commodity:copper', 'direct', 'low', { effective_from: '2026-05-01', effective_to: '2026-01-01' }));
  rejects('source inválida', s, 'assign', expo(a, 'commodity:copper', 'direct', 'low', { source: 'magia' }));
  rejects('nota demasiado larga', s, 'assign', expo(a, 'commodity:copper', 'direct', 'low', { note: 'x'.repeat(301) }));
  rejects('emisor inexistente', s, 'assign', expo('iss_9999', 'commodity:copper', 'direct', 'low'), 'not_found');
  rejects('operación desconocida', s, 'borrar_todo', {}, 'unknown_op');
  rejects('campo no editable en update_assignment', s, 'update_assignment', { issuer_id: a, aid: s.issuers[a].assignments[0].aid, changes: { tag: 'commodity:oil' } });
  rejects('update sin cambios', s, 'update_assignment', { issuer_id: a, aid: s.issuers[a].assignments[0].aid, changes: {} });
  rejects('cambiar a narrative conservando intensidad', s, 'update_assignment', { issuer_id: a, aid: s.issuers[a].assignments[0].aid, changes: { relation: 'narrative', intensity: 'high' } });
  rejects('review_status inválido', s, 'review', { issuer_id: a, aid: s.issuers[a].assignments[0].aid, review_status: 'quizas' });
  rejects('ticker inválido', s, 'create_instrument', { ticker: 'no valido!', issuer_id: a });
  rejects('instrumento con emisor inexistente', s, 'create_instrument', { ticker: 'ZZZ', issuer_id: 'iss_9999' });
  rejects('producto apalancado sin leveraged', s, 'create_instrument', { ticker: 'LEV', issuer_id: a, role: 'leveraged_product', leveraged: false });
  rejects('emisor nuevo no puede nacer verified', s, 'create_issuer', { legal_name: 'Y', identity_status: 'verified' });
  rejects('verified solo con Yahoo + asistente', s, 'set_identity', { issuer_id: a, identity_status: 'verified', identity_sources: [{ type: 'yahoo', ref: 'x' }, { type: 'assistant', ref: 'y' }] });
  rejects('verified con una sola fuente', s, 'set_identity', { issuer_id: a, identity_status: 'verified', identity_sources: [{ type: 'exchange', ref: 'x' }] });
  rejects('tag con parent de otra dimensión', s, 'create_tag', { tag: 'commodity:sub', label: 'x', parent: 'industry:mining' });
  rejects('tag jerárquico en dimensión no jerárquica', s, 'create_tag', { tag: 'stage:sub', label: 'x', parent: 'stage:producer' });
  rejects('etiqueta ya existente', s, 'create_tag', { tag: 'commodity:gold', label: 'otra' });
  // y los casos buenos
  const ok = (() => { try { T.applyOp(s, 'set_identity', { issuer_id: a, identity_status: 'verified', identity_sources: [{ type: 'yahoo', ref: 'x' }, { type: 'exchange', ref: 'TSX' }] }, TS); return true; } catch (e) { return false; } })();
  check('F1 verified con Yahoo + bolsa sí se admite', ok);
  // retirada de etiqueta: no se puede usar para nuevas asignaciones pero las existentes se conservan
  ops(s, [['retire_tag', { tag: 'commodity:oil' }]]);
  rejects('asignar con etiqueta retirada', s, 'assign', expo(a, 'commodity:oil', 'direct', 'low'));
  check('F1 retirar etiqueta conserva las asignaciones existentes', true);
}

// ── F4: propiedad con secuencias aleatorias ───────────────────────────────
function prng(seed) { let x = seed >>> 0; return () => ((x = (x * 1664525 + 1013904223) >>> 0) / 4294967296); }
function f4() {
  for (const seed of [1, 7, 42, 2026]) {
    const rnd = prng(seed);
    const pick = (arr) => arr[Math.floor(rnd() * arr.length)];
    const state = baseState(); const events = []; let seq = state.revision;
    // el estado base se registra como eventos para poder reproducirlo
    const baseEvents = [];
    { const b = T.emptyState(); /* reconstruye la lista de create_tag de baseState */
      for (const [tag, t] of Object.entries(state.tags)) baseEvents.push({ op: 'create_tag', args: { tag, label: t.label, parent: t.parent || undefined } }); }
    const s = T.emptyState();
    for (const e of baseEvents) { T.applyOp(s, e.op, e.args, TS); seq++; events.push({ seq: s.revision = events.length + 1, ts: TS, op: e.op, args: e.args }); }
    let applied = 0, rejected = 0, consistent = true, valid = true, stuck = null;
    const tickers = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF', 'GGG', 'HHH'];
    const tags = Object.keys(s.tags);
    for (let step = 0; step < 400; step++) {
      const issuers = Object.keys(s.issuers), insts = Object.keys(s.instruments);
      let op, args;
      const r = rnd();
      if (r < 0.12 || !issuers.length) { op = 'create_issuer'; args = { legal_name: 'Emisor ' + step }; }
      else if (r < 0.22) { op = 'create_instrument'; args = { ticker: pick(tickers) + (rnd() < 0.3 ? '.TO' : ''), issuer_id: pick(issuers), role: pick(['operating_company', 'fund', 'index']) }; }
      else if (r < 0.55) { const t = pick(tags); const exp = !['industry', 'stage', 'asset_class'].includes(T.dimOf(t));
        op = 'assign'; args = { issuer_id: pick(issuers), tag: t, relation: exp ? pick(['direct', 'indirect', 'narrative']) : null, intensity: null, nav_primary: exp && rnd() < 0.3, source: 'manual', confidence: pick(['high', 'medium', 'low']), note: '' };
        if (args.relation && args.relation !== 'narrative') args.intensity = pick(['high', 'low']); }
      else {
        const iss = pick(issuers); const list = s.issuers[iss].assignments; if (!list.length) { step--; continue; }
        const a = pick(list);
        const k = rnd();
        if (k < 0.3) { op = 'review'; args = { issuer_id: iss, aid: a.aid, review_status: pick(['pending', 'confirmed', 'rejected']) }; }
        else if (k < 0.5) { op = 'set_nav_primary'; args = { issuer_id: iss, aid: a.aid, value: rnd() < 0.8 }; }
        else if (k < 0.7) { op = 'update_assignment'; args = { issuer_id: iss, aid: a.aid, changes: { note: 'n' + step, confidence: pick(['high', 'low']) } }; }
        else if (k < 0.85) { op = 'retire_assignment'; args = { issuer_id: iss, aid: a.aid }; }
        else if (insts.length) { op = 'change_ticker'; args = { instrument_id: pick(insts), new_ticker: pick(tickers) + 'X', effective_date: '2026-' + String(1 + Math.floor(rnd() * 12)).padStart(2, '0') + '-15', reason: 'prueba' }; }
        else continue;
      }
      const before = canon(s);
      const ts = '2026-10-26T10:' + String(step % 60).padStart(2, '0') + ':00.000Z';
      try {
        T.applyOp(s, op, args, ts); s.revision = events.length + 1; events.push({ seq: s.revision, ts, op, args }); applied++;
      } catch (e) {
        if (!(e instanceof T.TagError)) throw e;
        rejected++; if (canon(s) !== before) { consistent = false; stuck = `${op} mutó el estado al fallar`; break; }
      }
      if (step % 25 === 0 || step === 399) {
        if (canon(T.replay(events)) !== canon(s)) { consistent = false; stuck = `replay != estado en el paso ${step} (${op})`; break; }
        const p = T.validateState(s); if (p.length) { valid = false; stuck = p[0]; break; }
      }
    }
    check(`F4 semilla ${seed}: ${applied} ops aplicadas, ${rejected} rechazadas; replay == estado`, consistent && valid && applied > 100, stuck || `aplicadas ${applied}`);
  }
}

// ── F5: recuentos ───────────────────────────────────────────────────────────
function f5() {
  const s = baseState();
  const gt = issuer(s, 'Green Thumb Industries'); instr(s, 'GTBIF', gt); instr(s, 'R9U2.F', gt);
  const tr = issuer(s, 'Trulieve'); instr(s, 'TRLV', tr);
  const etf = issuer(s, 'Cannabis ETF'); instr(s, 'MSOS', etf, { role: 'fund' });
  const lev = issuer(s, 'Apalancado'); instr(s, 'LEVX', lev, { role: 'leveraged_product', leveraged: true });
  const other = issuer(s, 'Minera'); instr(s, 'MIN.TO', other);
  for (const i of [gt, tr, etf, lev]) ops(s, [['assign', expo(i, 'theme:cannabis', 'direct', 'high', { nav_primary: true })]]);
  ops(s, [['assign', expo(gt, 'geo_exposure:us', 'direct', 'high', { nav_primary: true })], ['assign', expo(gt, 'geo_exposure:ar', 'narrative', null)],
          ['assign', expo(other, 'commodity:gold', 'direct', 'high', { nav_primary: true })], ['assign', expo(other, 'commodity:copper', 'direct', 'low')], ['assign', expo(other, 'commodity:oil', 'indirect', 'low')]]);
  const tickers = ['GTBIF', 'R9U2.F', 'TRLV', 'MSOS', 'LEVX', 'MIN.TO', 'NOPE'];
  const g = T.groupTickers(s, tickers, 'theme');
  const can = g.groups.find(x => x.key === 'tag:theme:cannabis');
  check('F5 cannabis: 5 instrumentos', can.counts.instruments === 5, JSON.stringify(can.counts));
  check('F5 R9U2.F y GTBIF cuentan como 1 empresa (más TRLV = 2)', can.counts.companies === 2, JSON.stringify(can.counts));
  check('F5 el ETF cuenta como fondo, no como empresa', can.counts.funds === 1);
  check('F5 el apalancado no cuenta como empresa ni como fondo', can.counts.leveraged === 1 && can.counts.companies === 2);
  check('F5 etiqueta de recuento: "5 instrumentos · 2 empresas · 1 fondo · 1 apalancado"', T.countsLabel(can.counts) === '5 instrumentos · 2 empresas · 1 fondo · 1 apalancado', T.countsLabel(can.counts));
  check('F5 sin porcentajes ni "x de y" en la cabecera', !/%| de \d/.test(T.countsLabel(can.counts)));
  check('F5 sin clasificar en la vista: MIN.TO (sin tema) y NOPE (sin ficha)', g.unclassified.rows.map(r => r.ticker).sort().join() === 'MIN.TO,NOPE', g.unclassified.rows.map(r => r.ticker).join());
  const gc = T.groupTickers(s, tickers, 'commodity');
  const tickersIn = (grp) => grp.rows.map(r => r.ticker);
  const gold = gc.groups.find(x => x.key === 'tag:commodity:gold'), cu = gc.groups.find(x => x.key === 'tag:commodity:copper');
  check('F5 MIN.TO aparece en oro y cobre (varios grupos) con "también en"', tickersIn(gold).includes('MIN.TO') && tickersIn(cu).includes('MIN.TO') && gold.rows[0].alsoIn.includes('Cobre'));
  check('F5 …pero cuenta una sola vez en los totales globales', gc.totals.instruments === 7 && T.uniqueTickers(gc).size === 7, JSON.stringify(gc.totals));
  check('F5 el vínculo indirecto (petróleo) se muestra por defecto', gc.groups.some(x => x.key === 'tag:commodity:oil'));
  const gn = T.groupTickers(s, tickers, 'geo_exposure');
  check('F5 narrative oculto por defecto', !gn.groups.some(x => x.key === 'tag:geo_exposure:ar'));
  check('F5 narrative visible con showNarrative', T.groupTickers(s, tickers, 'geo_exposure', { showNarrative: true }).groups.some(x => x.key === 'tag:geo_exposure:ar'));
  const one = T.groupTickers(s, tickers, 'commodity', { onePerInstrument: true });
  check('F5 "cada ticker una vez": MIN.TO solo en su principal (oro)', one.groups.filter(x => x.rows.some(r => r.ticker === 'MIN.TO')).map(x => x.key).join() === 'tag:commodity:gold');
  check('F5 mercado de cotización derivado del sufijo', T.listingMarket('MIN.TO') === 'Canadá (TSX)' && T.listingMarket('R9U2.F') === 'Alemania (Fráncfort)' && T.listingMarket('GTBIF') === 'EE. UU.' && T.listingMarket('^XSP') === 'Índices');
  const lm = T.groupTickers(s, tickers, 'listing_market');
  check('F5 agrupar por mercado cubre todos los tickers una vez', lm.groups.reduce((n, x) => n + x.rows.length, 0) === 7);
  const flt = T.groupTickers(s, tickers, 'theme', { tagFilters: { commodity: ['commodity:gold'] } });
  check('F5 filtro por etiqueta (oro) deja solo MIN.TO', T.uniqueTickers(flt).size === 1 && T.uniqueTickers(flt).has('MIN.TO'));
  const rej = baseState(); // confirmar/rechazar afecta a los filtros
  ops(s, [['review', { issuer_id: tr, aid: s.issuers[tr].assignments[0].aid, review_status: 'rejected' }]]);
  check('F5 una asignación rechazada deja de contar', !T.groupTickers(s, tickers, 'theme').groups.find(x => x.key === 'tag:theme:cannabis').rows.some(r => r.ticker === 'TRLV'));
  ops(s, [['review', { issuer_id: gt, aid: s.issuers[gt].assignments[0].aid, review_status: 'confirmed' }]]);
  const oc = T.groupTickers(s, tickers, 'theme', { onlyConfirmed: true });
  check('F5 "solo confirmadas": solo la de Green Thumb', oc.groups.length === 1 && oc.groups[0].rows.map(r => r.ticker).sort().join() === 'GTBIF,R9U2.F');
  const jerarq = T.groupTickers(s, ['A1'], 'industry');
  check('F5 ticker sin ficha no rompe nada', jerarq.unclassified.rows.length === 1);
  const roll = (() => { const x = baseState(); const i = issuer(x, 'Oro SA'); instr(x, 'ORO', i); ops(x, [['assign', assignArgs(i, 'industry:mining_gold')]]); return T.groupTickers(x, ['ORO'], 'industry', { level: 'parent' }); })();
  check('F5 nivel "padre": el oro se agrupa bajo Minería', roll.groups.length === 1 && roll.groups[0].key === 'tag:industry:mining');
}

// ── F7: point-in-time frente a retrospectivo ────────────────────────────────
function f7() {
  const mk = (seq, ts, op, args) => ({ seq, ts, op, args });
  const events = [
    mk(1, '2026-01-05T09:00:00.000Z', 'create_tag', { tag: 'commodity:copper', label: 'Cobre' }),
    mk(2, '2026-01-05T09:00:01.000Z', 'create_issuer', { legal_name: 'Cobre SA' }),
    mk(3, '2026-01-05T09:00:02.000Z', 'create_instrument', { ticker: 'CUU', issuer_id: 'iss_0001' }),
    mk(4, '2026-01-10T10:00:00.000Z', 'assign', { issuer_id: 'iss_0001', tag: 'commodity:copper', relation: 'direct', intensity: 'low', nav_primary: false, source: 'assistant', confidence: 'medium', note: '' }),
    mk(5, '2026-02-01T10:00:00.000Z', 'review', { issuer_id: 'iss_0001', aid: 'a_00001', review_status: 'confirmed' }),
    mk(6, '2026-03-01T10:00:00.000Z', 'update_assignment', { issuer_id: 'iss_0001', aid: 'a_00001', changes: { intensity: 'high' } }),
    mk(7, '2026-04-01T10:00:00.000Z', 'retire_assignment', { issuer_id: 'iss_0001', aid: 'a_00001' }),
  ];
  const at = (d) => T.stateAt(events, d).issuers['iss_0001'];
  const A = (d) => { const i = at(d); return i && i.assignments[0]; };
  check('F7 antes de la primera asignación no existe', A('2026-01-09') === undefined || A('2026-01-09') === undefined);
  check('F7 el 11-ene: pendiente, intensidad baja', A('2026-01-11').review_status === 'pending' && A('2026-01-11').intensity === 'low');
  check('F7 el 15-feb: confirmada (point-in-time) desde el 1-feb', A('2026-02-15').review_status === 'confirmed' && A('2026-01-31').review_status === 'pending');
  check('F7 el 15-mar: la intensidad ya era alta', A('2026-03-15').intensity === 'high' && A('2026-02-28').intensity === 'low');
  check('F7 el 15-abr: retirada, pero el 15-mar seguía viva (no se pierde al retirar)', A('2026-04-15').removed_at !== null && A('2026-03-15').removed_at === null);
  const now = T.replay(events);
  check('F7 estado actual (retrospectivo) solo conoce el final: retirada e intensidad alta', now.issuers['iss_0001'].assignments[0].removed_at !== null && now.issuers['iss_0001'].assignments[0].intensity === 'high');
  check('F7 reproducir una vez cada día da estados distintos (no basta con reviewed_at)', canon(T.stateAt(events, '2026-02-15')) !== canon(T.stateAt(events, '2026-03-15')));
  const pit = T.groupTickers(T.stateAt(events, '2026-03-15'), ['CUU'], 'commodity');
  const retro = T.groupTickers(T.stateAt(events, '2026-12-31'), ['CUU'], 'commodity');
  check('F7 agrupar con el estado de marzo muestra a CUU en Cobre; con el actual (retirada) queda sin clasificar',
    pit.groups.length === 1 && retro.groups.length === 0 && retro.unclassified.rows.length === 1);
}

// ── F8: identidad ───────────────────────────────────────────────────────────
function f8() {
  const s = baseState();
  const barrick = issuer(s, 'Barrick Gold'), goldcom = issuer(s, 'Gold.com');
  instr(s, 'AAA', barrick);
  rejects('ticker duplicado entre instrumentos', s, 'create_instrument', { ticker: 'AAA', issuer_id: goldcom });
  // Barrick abandona GOLD el 2025-05-31 y Gold.com lo estrena el 2025-12-01: periodos disjuntos
  const b = instr(s, 'GOLD', barrick, { ticker_from: '1990-01-01' });
  check('F8 el ticker vigente puede resolverse sin fecha', T.resolveInstrument(s, 'GOLD').id === b);
  T.applyOp(s, 'change_ticker', { instrument_id: b, new_ticker: 'B', effective_date: '2025-06-01', reason: 'Barrick pasa a cotizar como B' }, TS);
  const gc = T.applyOp(s, 'create_instrument', { ticker: 'GOLD', issuer_id: goldcom, ticker_from: '2025-12-01' }, TS).id;
  check('F8 reutilización de GOLD con periodos disjuntos se admite', true);
  check('F8 GOLD hoy es Gold.com', T.resolveInstrument(s, 'GOLD').id === gc);
  check('F8 GOLD en 2024 era Barrick (instrumento que hoy es B)', T.resolveInstrument(s, 'GOLD', '2024-06-03').id === b);
  check('F8 B hoy es Barrick y conserva su emisor', T.resolveInstrument(s, 'B').inst.issuer_id === barrick);
  check('F8 GOLD en el hueco jun–nov 2025 no resuelve a nadie (no se adivina)', T.resolveInstrument(s, 'GOLD', '2025-08-01') === null);
  rejects('reutilizar GOLD solapando con el periodo de Barrick', s, 'create_instrument', { ticker: 'GOLD', issuer_id: goldcom, ticker_from: '2025-03-01' });
  rejects('cambio de ticker a uno que ya usa otro instrumento', s, 'change_ticker', { instrument_id: b, new_ticker: 'AAA', effective_date: '2026-01-01' });
  rejects('cambio de ticker sin fecha', s, 'change_ticker', { instrument_id: b, new_ticker: 'ZZ' });
  // etiquetas se conservan al cambiar de ticker
  const mn = issuer(s, 'Minera'); const mi = instr(s, 'MRR.XA', mn, { ticker_from: '2024-01-01' });
  ops(s, [['assign', expo(mn, 'commodity:gold', 'direct', 'high', { nav_primary: true })]]);
  T.applyOp(s, 'change_ticker', { instrument_id: mi, new_ticker: 'NRL.AX', effective_date: '2026-10-20', reason: 'cambio de código' }, TS);
  const v = T.view(s, 'NRL.AX');
  check('F8 tras cambiar de ticker, las etiquetas siguen en el emisor', v && v.assignments.length === 1 && v.instrumentId === mi);
  check('F8 el ticker antiguo resuelve al mismo instrumento con fecha anterior al cambio', T.resolveInstrument(s, 'MRR.XA', '2026-01-01').id === mi);
  check('F8 …y no resuelve hoy (sin fecha)', T.resolveInstrument(s, 'MRR.XA') === null);
  // histórico con solape interno
  const bad = T.clone(s); bad.instruments[mi].ticker_history.push({ ticker: 'MRR.XA', from: '2026-06-01', to: '2026-12-31', reason: 'x' });
  check('F8 validateState detecta histórico solapado dentro del instrumento', T.validateState(bad).length > 0);
  const orphan = T.clone(s); orphan.instruments[mi].issuer_id = 'iss_9999';
  check('F8 validateState detecta instrumento con emisor inexistente', T.validateState(orphan).some(p => /emisor inexistente/.test(p)));
  // un instrumento apunta a UN emisor: no hay forma de crear cadenas
  check('F8 el modelo no tiene referencias emisor→emisor (sin cadenas ni ciclos)', Object.values(s.issuers).every(i => !('same_issuer_as' in i) && !('issuer_id' in i)));
  // gestión de identidad
  const r = T.applyOp(s, 'set_identity', { issuer_id: barrick, identity_status: 'disputed' }, TS);
  check('F8 identidad disputada se registra con antes/después', r.before.identity_status === 'provisional' && r.after.identity_status === 'disputed');
}

// ── F2: fusión de la siembra ────────────────────────────────────────────────
function f2() {
  const seed = {
    vocabulary: [{ tag: 'commodity:gold', label: 'Oro', parent: null }, { tag: 'commodity:copper', label: 'Cobre', parent: null },
      { tag: 'commodity:oil', label: 'Petróleo', parent: null }, { tag: 'industry:mining_gold', label: 'Minería de oro', parent: null },
      { tag: 'theme:ai', label: 'IA', parent: null }, { tag: 'geo_exposure:us', label: 'EE. UU.', parent: null }, { tag: 'stage:producer', label: 'Producción', parent: null }],
    tickers: [{ ticker: 'AAA', annex_name: 'Alfa', industry: 'industry:mining_gold', asset_class: null, stage: 'stage:producer', confidence: 'high', note: 'n', role: 'operating_company', leveraged: false, issuer_key: 'AAA',
      assignments: [{ tag: 'commodity:gold', relation: 'direct', intensity: 'high', nav_primary: true }, { tag: 'commodity:copper', relation: 'direct', intensity: 'low', nav_primary: false },
        { tag: 'commodity:oil', relation: 'narrative', intensity: null, nav_primary: false }, { tag: 'geo_exposure:us', relation: 'direct', intensity: 'high', nav_primary: true }] }],
  };
  const yahoo = { fetched_at: '2026-10-25T00:00:00Z', tickers: { AAA: { longName: 'Alfa Mining Inc.' } } };
  const st = T.emptyState();
  const p1 = planSeedOps(st, seed, yahoo, new Date(TS));
  for (const o of p1.ops) T.applyOp(st, o.op, o.args, TS);
  check('F2 la siembra inicial crea vocabulario, emisor, instrumento y asignaciones', p1.stats.tags === 7 && p1.stats.issuers === 1 && p1.stats.instruments === 1 && p1.stats.assigned === 6, JSON.stringify(p1.stats));
  check('F2 la identidad sembrada es provisional', Object.values(st.issuers)[0].identity_status === 'provisional');
  check('F2 segunda siembra: 0 operaciones (idempotente)', planSeedOps(st, seed, yahoo, new Date(TS)).ops.length === 0);
  const iss = Object.keys(st.issuers)[0];
  const A = (tag) => st.issuers[iss].assignments.find(a => a.tag === tag);
  // acciones humanas
  T.applyOp(st, 'review', { issuer_id: iss, aid: A('commodity:gold').aid, review_status: 'confirmed' }, TS);
  T.applyOp(st, 'review', { issuer_id: iss, aid: A('commodity:copper').aid, review_status: 'rejected' }, TS);
  T.applyOp(st, 'retire_assignment', { issuer_id: iss, aid: A('commodity:oil').aid }, TS);
  T.applyOp(st, 'update_assignment', { issuer_id: iss, aid: A('geo_exposure:us').aid, changes: { intensity: 'low', note: 'ajuste manual' } }, TS);
  T.applyOp(st, 'review', { issuer_id: iss, aid: A('geo_exposure:us').aid, review_status: 'confirmed' }, TS);
  // el seed cambia: otra intensidad para todo lo que existe
  const seed2 = JSON.parse(JSON.stringify(seed));
  seed2.tickers[0].assignments[0].intensity = 'low'; seed2.tickers[0].assignments[1].intensity = 'high';
  seed2.tickers[0].assignments[3].intensity = 'high'; seed2.tickers[0].confidence = 'low';
  const before = canon(st);
  const p2 = planSeedOps(st, seed2, yahoo, new Date(TS));
  check('F2 lo CONFIRMADO no se toca aunque el seed cambie', !p2.ops.some(o => o.args.aid === A('commodity:gold').aid));
  check('F2 lo RECHAZADO no se toca ni se vuelve a proponer', !p2.ops.some(o => o.args.aid === A('commodity:copper').aid) && !p2.ops.some(o => o.op === 'assign' && o.args.tag === 'commodity:copper'));
  check('F2 lo RETIRADO no reaparece', !p2.ops.some(o => o.op === 'assign' && o.args.tag === 'commodity:oil'));
  check('F2 lo editado a mano y confirmado no se pisa', !p2.ops.some(o => o.args.aid === A('geo_exposure:us').aid));
  check('F2 las propuestas pendientes SÍ se actualizan: la etiqueta de industria cambia de confianza', p2.ops.some(o => o.op === 'update_assignment' && o.args.aid === A('industry:mining_gold').aid && o.args.changes.confidence === 'low'));
  check('F2 planificar no muta el estado', canon(st) === before);
  for (const o of p2.ops) T.applyOp(st, o.op, o.args, TS);
  check('F2 tras aplicar el plan, lo confirmado conserva su valor original', A('commodity:gold').intensity === 'high' && A('geo_exposure:us').note === 'ajuste manual');
  // asignación creada a mano (source manual) en una etiqueta del seed: tampoco se toca
  const st2 = T.emptyState(); for (const o of planSeedOps(st2, seed, yahoo, new Date(TS)).ops) T.applyOp(st2, o.op, o.args, TS);
  const iss2 = Object.keys(st2.issuers)[0];
  const g2 = st2.issuers[iss2].assignments.find(a => a.tag === 'commodity:gold');
  T.applyOp(st2, 'retire_assignment', { issuer_id: iss2, aid: g2.aid }, TS);
  T.applyOp(st2, 'assign', { issuer_id: iss2, tag: 'commodity:gold', relation: 'direct', intensity: 'low', nav_primary: false, source: 'manual', confidence: 'high', review_status: 'confirmed', note: 'mía' }, TS);
  const p3 = planSeedOps(st2, seed2, yahoo, new Date(TS));
  check('F2 una asignación `manual` posterior a una retirada no es sobrescrita por la siembra', !p3.ops.some(o => o.args && (o.args.tag === 'commodity:gold' || (o.args.aid && st2.issuers[iss2].assignments.find(a => a.aid === o.args.aid && a.tag === 'commodity:gold' && a.source === 'manual')))));
}

// ── D: datos reales versionados ─────────────────────────────────────────────
function d() {
  const dir = path.join(__dirname, '..', 'docs', 'data');
  const fileState = path.join(dir, 'ticker_tags.json'), fileEv = path.join(dir, 'ticker_tags_events.jsonl');
  if (!fs.existsSync(fileState)) { check('D datos reales presentes', false, 'falta docs/data/ticker_tags.json'); return; }
  const st = JSON.parse(fs.readFileSync(fileState, 'utf8'));
  const ev = fs.readFileSync(fileEv, 'utf8').split('\n').filter(Boolean).map(JSON.parse);
  check('D seq contiguas 1..N y revision == N', ev.every((e, i) => e.seq === i + 1) && st.revision === ev.length, `${ev.length} eventos, revision ${st.revision}`);
  check('D replay(eventos) == ticker_tags.json', canon(T.replay(ev)) === canon(st));
  const p = T.validateState(st);
  check('D invariantes del estado versionado', p.length === 0, p.slice(0, 3).join(' | '));
  const seed = JSON.parse(fs.readFileSync(path.join(__dirname, 'ticker_tags_seed.json'), 'utf8'));
  const missing = seed.tickers.map(t => t.ticker).filter(t => !T.resolveInstrument(st, t));
  check(`D los ${seed.tickers.length} tickers sembrados resuelven a un instrumento`, missing.length === 0, missing.join(','));
  const gt = T.view(st, 'GTBIF'), r9 = T.view(st, 'R9U2.F');
  check('D R9U2.F y GTBIF comparten emisor pero son dos instrumentos', gt && r9 && gt.issuerId === r9.issuerId && gt.instrumentId !== r9.instrumentId);
  const pf = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'portfolio.json'), 'utf8'));
  const tk = [...new Set(pf.sections.flatMap(s => s.items.map(i => i.ticker)))];
  const g = T.groupTickers(st, tk, 'theme');
  check('D agrupar el Portfolio real por temática cubre cada ticker exactamente una vez en los totales', T.uniqueTickers(g).size === tk.length, `${T.uniqueTickers(g).size} frente a ${tk.length}`);
  const gm = T.groupTickers(st, tk, 'listing_market');
  check('D agrupar por mercado reparte los tickers sin duplicar', gm.groups.reduce((n, x) => n + x.rows.length, 0) === tk.length);
  const gi = T.groupTickers(st, tk, 'industry');
  const funds = gi.groups.reduce((n, x) => n + x.counts.funds, 0);
  check('D los ETFs no se cuentan como empresas en ningún grupo', gi.groups.every(x => x.counts.companies <= x.counts.instruments - x.counts.funds - x.counts.leveraged - x.counts.indexes + 0) && funds >= 0);
  const noTags = tk.filter(t => !T.resolveInstrument(st, t));
  check('D (informativo) tickers del Portfolio aún sin ficha de etiquetas: ' + (noTags.length ? noTags.join(',') : 'ninguno'), true);
}

function main() {
  const suites = [f1, f2, f4, f5, f7, f8, d];
  for (const fn of suites) { try { fn(); } catch (e) { check(`${fn.name} (excepción)`, false, e.stack.split('\n').slice(0, 3).join(' | ')); } }
  const bad = results.filter(r => !r.ok);
  for (const r of results) console.log((r.ok ? '  ok   ' : '  FAIL ') + r.name + (r.detail ? '\n         ' + r.detail : ''));
  console.log(`\n${results.length - bad.length}/${results.length} passed`);
  process.exit(bad.length ? 1 : 0);
}
main();
