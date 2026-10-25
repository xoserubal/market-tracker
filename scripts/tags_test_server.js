#!/usr/bin/env node
/*
 * tags_test_server.js — servidor mínimo SOLO para pruebas de las etiquetas (no es server.js).
 * Sirve la raíz del repo (como server.js), monta las MISMAS rutas de etiquetas y simula con respuestas vacías
 * el resto de APIs que consulta portfolio.html, sin red, sin git pull y sin tocar el servidor real (puerto 3000).
 *
 *   TAGS_DATA_DIR   carpeta con ticker_tags*.{json,jsonl}   (por defecto docs/data; los tests usan una copia temporal)
 *   TAGS_REPO_ROOT  raíz git para publicar                   (por defecto la raíz del repo)
 *   TAGS_WRITER     hostname escritor ('' = solo lectura; 'auto' = este equipo)
 *   PORT            puerto (por defecto 3100; 0 = efímero)
 */
'use strict';
const express = require('express');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { createStore } = require('../shared/ticker-tags-store');
const { mountTagRoutes } = require('../shared/ticker-tags-routes');

function createApp(opts) {
  const o = Object.assign({
    root: path.resolve(__dirname, '..'),
    dataDir: process.env.TAGS_DATA_DIR || path.resolve(__dirname, '..', 'docs', 'data'),
    repoRoot: process.env.TAGS_REPO_ROOT || path.resolve(__dirname, '..'),
    writer: process.env.TAGS_WRITER === 'auto' ? os.hostname() : (process.env.TAGS_WRITER || ''),
    hostname: os.hostname(),
  }, opts || {});
  const app = express();
  const store = createStore({ dataDir: o.dataDir, repoRoot: o.repoRoot, hostname: o.hostname, writerHost: o.writer });
  app.use('/private', (_req, res) => res.status(404).end());
  mountTagRoutes(app, express, store);
  const pf = () => JSON.parse(fs.readFileSync(path.join(o.root, 'portfolio.json'), 'utf8'));
  app.get('/api/portfolio', (_req, res) => res.json(pf()));
  app.get('/api/stock-config', (_req, res) => res.json({}));
  app.get('/api/universe', (_req, res) => res.json({ tickers: [] }));
  app.get('/api/portfolio-history', (_req, res) => res.json({ rows: [] }));
  app.get('/api/special-situations', (_req, res) => res.json({ situations: [] }));
  app.get('/api/quote/:symbol', (_req, res) => res.status(503).json({ error: 'sin red en el servidor de pruebas' }));
  app.get('/api/*', (_req, res) => res.json({}));
  app.use(express.static(o.root));
  return { app, store, options: o };
}

if (require.main === module) {
  const { app } = createApp();
  const port = process.env.PORT === undefined ? 3100 : parseInt(process.env.PORT, 10);
  const srv = app.listen(port, '127.0.0.1', () => console.log(`tags_test_server en http://127.0.0.1:${srv.address().port}`));
}
module.exports = { createApp };
