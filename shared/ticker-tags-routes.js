/*
 * ticker-tags-routes.js — rutas HTTP de las etiquetas del Portfolio (línea A).
 * Las monta server.js y también el servidor de pruebas (scripts/tags_test_server.js), de modo que las pruebas
 * HTTP ejercitan exactamente este código.
 *
 *   GET  /api/ticker-tags          estado + modo (read_write | read_only) + motivo del bloqueo
 *   GET  /api/ticker-tags/status   revisión, integridad, copias en conflicto y estado de git
 *   GET  /api/ticker-tags/events   últimos eventos (auditoría)
 *   POST /api/ticker-tags/op       { op, args, base_revision }  — una operación validada
 *   POST /api/ticker-tags/publish  commit de SOLO los dos ficheros de etiquetas + push
 */
'use strict';
const Tags = require('./ticker-tags-lib');
const { StoreError } = require('./ticker-tags-store');

function mountTagRoutes(app, express, store) {
  const fail = (res, e) => {
    if (e instanceof StoreError) return res.status(e.status).json({ error: e.code, message: e.message, details: e.details });
    console.log('⚠ ticker-tags:', (e && e.stack) || e);
    return res.status(500).json({ error: 'internal', message: String((e && e.message) || e) });
  };
  app.get('/api/ticker-tags', (_req, res) => { try { res.json(store.snapshot()); } catch (e) { fail(res, e); } });
  app.get('/api/ticker-tags/status', async (_req, res) => { try { res.json(await store.status()); } catch (e) { fail(res, e); } });
  app.get('/api/ticker-tags/events', (req, res) => {
    try { res.json({ events: store.readEvents(Math.min(parseInt(req.query.limit, 10) || 50, 500)) }); } catch (e) { fail(res, e); }
  });
  app.post('/api/ticker-tags/op', express.json({ limit: '1mb' }), async (req, res) => {
    try {
      const { op, args, base_revision } = req.body || {};
      if (!Tags.OP_NAMES.includes(op)) return res.status(400).json({ error: 'unknown_op', message: 'operación desconocida', details: { allowed: Tags.OP_NAMES } });
      const r = await store.apply(op, args, { baseRevision: Number.isInteger(base_revision) ? base_revision : null, actor: 'dashboard' });
      res.json({ ok: true, ...r });
    } catch (e) { fail(res, e); }
  });
  app.post('/api/ticker-tags/publish', async (_req, res) => { try { res.json(await store.publish()); } catch (e) { fail(res, e); } });
}

module.exports = { mountTagRoutes };
