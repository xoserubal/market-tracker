/*
 * tags_fs_guard.js — guardia de aislamiento (se carga con `node -r ./scripts/tags_fs_guard.js ...`).
 * Hace que CUALQUIER lectura/apertura de ficheros de etiquetas lance una excepción, también las indirectas
 * (require de JSON, streams, promesas). Se usa en las pruebas de invariancia para demostrar que los motores
 * de inversión nunca leen la taxonomía.
 */
'use strict';
const fs = require('fs');
const FORBIDDEN = /ticker[_-]?tags|ticker_yahoo_meta/i;

class TagReadDetected extends Error { constructor(p) { super('LECTURA DE FICHERO DE ETIQUETAS: ' + p); this.name = 'TagReadDetected'; } }
const check = (p) => { if (p !== undefined && p !== null && typeof p !== 'number' && FORBIDDEN.test(String(p).replace(/\\/g, '/'))) throw new TagReadDetected(String(p)); };

for (const name of ['readFileSync', 'openSync', 'createReadStream', 'readFile', 'open', 'readSync']) {
  const real = fs[name]; if (typeof real !== 'function') continue;
  fs[name] = function (p, ...rest) { check(p); return real.call(this, p, ...rest); };
}
if (fs.promises) for (const name of ['readFile', 'open']) {
  const real = fs.promises[name]; if (typeof real !== 'function') continue;
  fs.promises[name] = function (p, ...rest) { check(p); return real.call(this, p, ...rest); };
}
const Module = require('module');
const realLoad = Module._load;
Module._load = function (request, ...rest) { check(request); return realLoad.call(this, request, ...rest); };

module.exports = { TagReadDetected, FORBIDDEN };
