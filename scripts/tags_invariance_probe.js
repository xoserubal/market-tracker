#!/usr/bin/env node
/*
 * tags_invariance_probe.js — ejecuta los motores JS (Flow, espejo de Flow Screener) sobre datos de una raíz
 * temporal y escribe una huella determinista por stdout. Se lanza con la guardia de lectura:
 *     node -r ./scripts/tags_fs_guard.js scripts/tags_invariance_probe.js <inputRoot>
 * Variable TAGS_ENGINE_ROOT: de dónde se cargan los motores (por defecto, este repo).
 */
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const inputRoot = process.argv[2];
const engineRoot = process.env.TAGS_ENGINE_ROOT || path.resolve(__dirname, '..');
const fsl = require(path.join(engineRoot, 'shared', 'flow-state-lib.js'));
const fscore = require(path.join(engineRoot, 'shared', 'flow-score.js'));

const portfolio = JSON.parse(fs.readFileSync(path.join(inputRoot, 'portfolio.json'), 'utf8'));
const membership = fsl.fslBuildBasketMembership(portfolio.sections);
const baskets = fsl.fslBasketToTickers(membership);
const norm = (m) => Object.fromEntries(Object.keys(m).sort().map(k => [k, [...m[k]].sort()]));

// últimas filas por ticker de la captura diaria → Flow Score / Early Flow (mismas fórmulas que el dashboard)
const lastRow = {};
for (const line of fs.readFileSync(path.join(inputRoot, 'docs', 'data', 'portfolio_daily_snapshot.jsonl'), 'utf8').split('\n')) {
  if (!line) continue;
  const r = JSON.parse(line);
  if (!lastRow[r.ticker] || r.date >= lastRow[r.ticker].date) lastRow[r.ticker] = r;
}
const scores = {};
for (const tk of Object.keys(lastRow).sort()) {
  const r = lastRow[tk];
  let f = null, e = null;
  try { f = fscore.computeFlowScore(r); } catch (_) { f = 'err'; }
  try { e = fscore.computeEarlyFlowScore(r, null); } catch (_) { e = 'err'; }
  scores[tk] = [f, e];
}
const out = { membership: norm(membership), baskets: norm(baskets), scores };
const text = JSON.stringify(out);
process.stdout.write(JSON.stringify({ hash: crypto.createHash('sha256').update(text).digest('hex'),
  n_membership: Object.keys(membership).length, n_scores: Object.keys(scores).length }) + '\n');
