'use strict';
// Genera cycle_copy.js desde cycle.html. Solo se ejecuta con autorización (cambio del algoritmo de Cycle):
//   node scripts/sector_turn/make_cycle_copy.js
// Después hay que pasar test_cycle_equivalence.js y anotar la nueva huella en el registro.
const fs = require('fs');
const path = require('path');
const o = require('./cycle_original');

const ex = o.extract();
const api = o.load();
const table = api.CYCLE_MAP.map(p => ({
  phase: p.phase, short: p.short, order: p.order, category: p.category,
  sectors: p.sectors.map(s => ({ name: s.name, tickers: s.tickers.map(t => ({ ticker: t.ticker, role: t.role, name: t.name })) })),
}));
const DEBUG_BLOCK = '    if (fallbackTickers.length) {\n      console.debug(\'[cycle] relM1→relM3 fallback applied:\', phase.phase, fallbackTickers);\n    }\n';
let fn = ['accelInfo', 'stdev', 'calcPhaseScores', 'computeCycleSummary'].map(k => ex.parts[k]).join('\n');
if (!fn.includes(DEBUG_BLOCK)) throw new Error('no encuentro el bloque console.debug esperado: revisar a mano');
fn = fn.replace(DEBUG_BLOCK, '    // (aquí cycle.html escribe en la consola de depuración los tickers en fallback; no cambia el resultado)\n');
if (fn.includes('console.')) throw new Error('quedan llamadas a console');

const out = `'use strict';
// COPIA CONGELADA del cálculo de Cycle (cycle.html) para el registro semanal de giros sectoriales.
// Generada el ${new Date().toISOString().slice(0, 10)} por make_cycle_copy.js desde cycle.html (huella de fragmentos ${ex.sha256}).
// No editar a mano. Si cycle.html cambia, el registro se detiene (registry.js) hasta verificar de nuevo la
// equivalencia (test_cycle_equivalence.js) y regenerar esta copia con autorización.
// Tabla: solo los campos que usa el cálculo (fase, orden, categoría, tickers y su papel).

const ORIGINAL_SHA256 = ${JSON.stringify(ex.sha256)};
const COPY_VERSION = 'cycle-copy-1';

const CYCLE_MAP = ${JSON.stringify(table, null, 1)};

${fn}
module.exports = { CYCLE_MAP, accelInfo, stdev, calcPhaseScores, computeCycleSummary, ORIGINAL_SHA256, COPY_VERSION };
`;
fs.writeFileSync(path.join(__dirname, 'cycle_copy.js'), out);
console.log('cycle_copy.js generado; huella original', ex.sha256);
