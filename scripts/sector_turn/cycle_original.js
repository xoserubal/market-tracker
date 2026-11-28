'use strict';
// Ejecuta el cálculo ORIGINAL de cycle.html (no una copia): extrae del fichero de la pestaña los fragmentos
// CYCLE_MAP, accelInfo, stdev, calcPhaseScores y computeCycleSummary y los evalúa en un contexto aislado.
// La huella de esos fragmentos identifica la versión del algoritmo; si cambia, el registro se detiene
// (ver registry.js) hasta que se vuelva a verificar la equivalencia con la copia (cycle_copy.js).
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');

const CYCLE_HTML = path.join(__dirname, '..', '..', 'cycle.html');
const FUNCS = ['accelInfo', 'stdev', 'calcPhaseScores', 'computeCycleSummary'];

function sliceFunction(src, name) {
  const a = src.indexOf(`\nfunction ${name}(`);
  if (a < 0) throw new Error(`cycle.html: no encuentro function ${name}`);
  const b = src.indexOf('\n}\n', a);
  if (b < 0) throw new Error(`cycle.html: fin de ${name} no encontrado`);
  return src.slice(a + 1, b + 2);
}

function extract(file = CYCLE_HTML) {
  const src = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  const a = src.indexOf('const CYCLE_MAP = [');
  const b = src.indexOf('const OFFCYCLE_THEMES = [');
  if (a < 0 || b < 0 || b < a) throw new Error('cycle.html: no encuentro CYCLE_MAP');
  const parts = { CYCLE_MAP: src.slice(a, b).trimEnd() };
  for (const f of FUNCS) parts[f] = sliceFunction(src, f);
  const h = crypto.createHash('sha256');
  for (const k of ['CYCLE_MAP', ...FUNCS]) h.update(`${k}\n${parts[k]}\n`);
  return { parts, sha256: h.digest('hex'), file_sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') };
}

function load(file = CYCLE_HTML) {
  const ex = extract(file);
  const code = ['CYCLE_MAP', ...FUNCS].map(k => ex.parts[k]).join('\n\n') +
    '\n;({ CYCLE_MAP, accelInfo, stdev, calcPhaseScores, computeCycleSummary });';
  const ctx = vm.createContext({ console: { debug() {}, log() {}, warn() {}, error() {} }, Math, Number, Object, Array, isNaN });
  const api = vm.runInContext(code, ctx, { filename: 'cycle.html#extract', timeout: 5000 });
  return { ...api, sha256: ex.sha256, file_sha256: ex.file_sha256 };
}

module.exports = { extract, load, CYCLE_HTML };
