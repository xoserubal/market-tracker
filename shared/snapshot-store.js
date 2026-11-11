// Lectura de los snapshots diarios repartidos en fichero vivo + archivo mensual (solo Node).
// Espejo de scripts/snapshot_store.py (mantener sincronizados): el fichero vivo guarda los últimos 75 días y lo
// anterior vive en docs/data/archive/<nombre>/AAAA-MM.jsonl. readLines() concatena archivo (meses en orden) + vivo
// y descarta líneas idénticas repetidas (posible solo si el reparto se interrumpe a medias).
// Las páginas del navegador no usan esto: leen solo el fichero vivo.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function archiveDir(file) {
  return path.join(path.dirname(file), 'archive', path.basename(file).replace(/\.jsonl$/, ''));
}

function archiveFiles(file) {
  const d = archiveDir(file);
  if (!fs.existsSync(d)) return [];
  return fs.readdirSync(d).filter(f => f.endsWith('.jsonl')).sort().map(f => path.join(d, f));
}

function readLines(file) {
  const out = [];
  const seen = new Set();
  for (const f of archiveFiles(file)) {
    for (const l of fs.readFileSync(f, 'utf8').split('\n')) {
      if (!l.trim()) continue;
      seen.add(crypto.createHash('md5').update(l).digest('base64'));
      out.push(l);
    }
  }
  if (fs.existsSync(file)) {
    for (const l of fs.readFileSync(file, 'utf8').split('\n')) {
      if (!l.trim()) continue;
      if (seen.size && seen.has(crypto.createHash('md5').update(l).digest('base64'))) continue;
      out.push(l);
    }
  }
  return out;
}

function readRows(file) {
  const out = [];
  for (const l of readLines(file)) {
    try { out.push(JSON.parse(l)); } catch (e) { /* línea ilegible: se ignora */ }
  }
  return out;
}

module.exports = { archiveDir, archiveFiles, readLines, readRows };
