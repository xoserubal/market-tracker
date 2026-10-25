#!/usr/bin/env node
/*
 * test_ticker_tags_http.js — capa HTTP de las etiquetas (rutas reales, datos en un directorio temporal).
 *   node scripts/test_ticker_tags_http.js
 *   Comprueba códigos de estado, cuerpo de error, 409 por revisión obsoleta, 403 sin escritor, 423 con copias en
 *   conflicto, e INVARIANCIA: ninguna operación modifica ficheros ajenos a las etiquetas (portfolio.json, universe.json…).
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { createApp } = require('./tags_test_server');

const ROOT = path.resolve(__dirname, '..');
const results = [];
const check = (name, ok, detail) => results.push({ name, ok: !!ok, detail: ok ? '' : String(detail || '') });

const sha = (f) => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const GUARDED = ['portfolio.json', 'docs/data/universe.json', 'docs/data/ai_candidates.json', 'docs/data/ai_picks.json', 'docs/data/koncorde_data.json',
  'docs/data/portfolio_daily_snapshot.jsonl', 'backtest/config/individual_stocks.yaml', 'docs/data/stock_candidates.json'].map(f => path.join(ROOT, f)).filter(f => fs.existsSync(f));

async function run() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tags-http-'));
  const data = path.join(tmp, 'docs', 'data'); fs.mkdirSync(data, { recursive: true });
  for (const f of ['ticker_tags.json', 'ticker_tags_events.jsonl']) fs.copyFileSync(path.join(ROOT, 'docs', 'data', f), path.join(data, f));
  const before = Object.fromEntries(GUARDED.map(f => [f, sha(f)]));

  const mk = (writer) => new Promise(res => { const { app } = createApp({ dataDir: data, repoRoot: tmp, writer, hostname: 'LAWNMOWER' }); const srv = app.listen(0, '127.0.0.1', () => res(srv)); });
  const call = async (srv, method, url, body) => {
    const r = await fetch(`http://127.0.0.1:${srv.address().port}${url}`, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    let j = null; try { j = await r.json(); } catch (_) { /* cuerpo no JSON */ }
    return { status: r.status, body: j };
  };

  // ── sin escritor ─────────────────────────────────────────────────────────
  const ro = await mk('');
  let r = await call(ro, 'GET', '/api/ticker-tags');
  check('GET /api/ticker-tags → 200 con estado, modo y motivo', r.status === 200 && r.body.state && r.body.mode === 'read_only' && r.body.write_block === 'writer_not_configured' && r.body.revision === 889, JSON.stringify({ s: r.status, m: r.body && r.body.mode }));
  check('GET devuelve las invariantes del estado (130 instrumentos, 129 emisores)', Object.keys(r.body.state.instruments).length === 130 && Object.keys(r.body.state.issuers).length === 129);
  r = await call(ro, 'POST', '/api/ticker-tags/op', { op: 'create_tag', args: { tag: 'theme:nuevo', label: 'Nuevo' }, base_revision: 889 });
  check('POST sin escritor configurado → 403 not_writer con mensaje', r.status === 403 && r.body.error === 'not_writer' && /TICKER_TAGS_WRITER_HOST/.test(r.body.message), JSON.stringify(r));
  r = await call(ro, 'POST', '/api/ticker-tags/publish');
  check('publicar sin escritor → 403', r.status === 403);
  r = await call(ro, 'GET', '/api/ticker-tags/events?limit=3');
  check('GET events → los 3 últimos eventos', r.status === 200 && r.body.events.length === 3 && r.body.events[2].seq === 889);
  r = await call(ro, 'GET', '/api/ticker-tags/status');
  check('GET status → revisión, modo y bloqueo', r.status === 200 && r.body.revision === 889 && r.body.mode === 'read_only');
  ro.close();

  // ── con escritor ─────────────────────────────────────────────────────────
  const rw = await mk('lawnmower');
  r = await call(rw, 'GET', '/api/ticker-tags');
  check('con escritor: modo read_write', r.body.mode === 'read_write' && r.body.write_block === null);
  const st = r.body.state;
  const iss = Object.values(st.instruments).find(i => i.ticker === 'NVDA').issuer_id;
  const bad = [
    ['operación desconocida', { op: 'borrar_todo', args: {} }, 400, 'unknown_op'],
    ['sin args', { op: 'assign' }, 400, null],
    ['etiqueta inexistente', { op: 'assign', args: { issuer_id: iss, tag: 'theme:no_existe', relation: 'direct', intensity: 'high', source: 'manual', confidence: 'low' } }, 400, 'validation'],
    ['exposure en industry', { op: 'assign', args: { issuer_id: iss, tag: 'industry:banks', relation: 'direct', intensity: 'high', source: 'manual', confidence: 'low' } }, 400, 'validation'],
    ['emisor inexistente', { op: 'assign', args: { issuer_id: 'iss_9999', tag: 'theme:space', relation: 'direct', intensity: 'high', source: 'manual', confidence: 'low' } }, 404, 'not_found'],
    ['campo no editable', { op: 'update_assignment', args: { issuer_id: iss, aid: st.issuers[iss].assignments[0].aid, changes: { tag: 'theme:space' } } }, 400, 'validation'],
    ['campo extra no permitido en JSON', { op: 'create_tag', args: { tag: 'Mal Formato', label: 'x' } }, 400, 'validation'],
  ];
  const sizeBefore = fs.statSync(path.join(data, 'ticker_tags_events.jsonl')).size;
  for (const [name, body, status, code] of bad) {
    r = await call(rw, 'POST', '/api/ticker-tags/op', body);
    check(`POST inválido (${name}) → ${status}${code ? ' ' + code : ''}`, r.status === status && (!code || r.body.error === code), JSON.stringify(r));
  }
  check('…ninguna operación inválida escribió nada', fs.statSync(path.join(data, 'ticker_tags_events.jsonl')).size === sizeBefore);
  r = await call(rw, 'POST', '/api/ticker-tags/op', { op: 'assign', args: { issuer_id: iss, tag: 'theme:space', relation: 'narrative', intensity: null, nav_primary: false, source: 'manual', confidence: 'medium', review_status: 'confirmed', note: 'prueba http' }, base_revision: 889 });
  check('POST válido → 200 con nueva revisión e id', r.status === 200 && r.body.ok === true && r.body.revision === 890 && /^a_\d+$/.test(r.body.result.id), JSON.stringify(r));
  const aid = r.body.result.id;
  r = await call(rw, 'POST', '/api/ticker-tags/op', { op: 'review', args: { issuer_id: iss, aid, review_status: 'rejected' }, base_revision: 889 });
  check('POST con revisión obsoleta → 409 stale_revision', r.status === 409 && r.body.error === 'stale_revision' && r.body.details.current === 890, JSON.stringify(r));
  r = await call(rw, 'POST', '/api/ticker-tags/op', { op: 'review', args: { issuer_id: iss, aid, review_status: 'rejected' }, base_revision: 890 });
  check('…y con la revisión actual sí aplica', r.status === 200 && r.body.revision === 891);
  r = await call(rw, 'POST', '/api/ticker-tags/op', { op: 'retire_assignment', args: { issuer_id: iss, aid } });
  check('POST sin base_revision también se admite', r.status === 200 && r.body.revision === 892);
  r = await call(rw, 'POST', '/api/ticker-tags/op', { op: 'review', args: { issuer_id: iss, aid, review_status: 'confirmed' } });
  check('operar sobre una asignación retirada → 400', r.status === 400);
  const ev = (await call(rw, 'GET', '/api/ticker-tags/events?limit=3')).body.events;
  check('la auditoría registra actor y antes/después', ev[1].op === 'review' && ev[1].actor === 'dashboard' && ev[1].before.review_status === 'confirmed' && ev[1].after.review_status === 'rejected');

  // copias en conflicto de Dropbox
  fs.writeFileSync(path.join(data, 'ticker_tags (Copia en conflicto de DESPACHOB 2026-10-26).json'), '{}');
  r = await call(rw, 'POST', '/api/ticker-tags/op', { op: 'create_tag', args: { tag: 'theme:otro', label: 'Otro' } });
  check('copia en conflicto → 423 conflict_copies', r.status === 423 && r.body.error === 'conflict_copies');
  r = await call(rw, 'GET', '/api/ticker-tags');
  check('…la lectura sigue funcionando e informa del bloqueo', r.status === 200 && r.body.write_block === 'conflict_copies' && r.body.conflict_copies.length === 1);
  fs.unlinkSync(path.join(data, 'ticker_tags (Copia en conflicto de DESPACHOB 2026-10-26).json'));
  rw.close();

  // ── invariancia: ningún fichero ajeno cambió ───────────────────────────
  const after = Object.fromEntries(GUARDED.map(f => [f, sha(f)]));
  const changed = GUARDED.filter(f => before[f] !== after[f]).map(f => path.relative(ROOT, f));
  check(`INVARIANCIA: ${GUARDED.length} ficheros de motores/datos no cambian tras ${bad.length + 5} operaciones`, changed.length === 0, changed.join(', '));
  const written = fs.readdirSync(data).sort();
  check('solo se escribieron los dos ficheros de etiquetas (sin temporales)', written.join() === 'ticker_tags.json,ticker_tags_events.jsonl', written.join());
  fs.rmSync(tmp, { recursive: true, force: true });
}

run().catch(e => check('excepción', false, e.stack)).finally(() => {
  const bad = results.filter(r => !r.ok);
  for (const r of results) console.log((r.ok ? '  ok   ' : '  FAIL ') + r.name + (r.detail ? '\n         ' + r.detail : ''));
  console.log(`\n${results.length - bad.length}/${results.length} passed`);
  process.exit(bad.length ? 1 : 0);
});
