'use strict';
// Huellas del preregistro v2 firmado (giro de sectores deprimidos).
//   node research/sector_turnaround_v2/freeze.js          -> escribe freeze.json
//   node research/sector_turnaround_v2/freeze.js --verify -> comprueba que nada ha cambiado
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const ROOT = path.join(__dirname, '..', '..');
const FILES = [
  'wiki/PREREGISTRO_GIRO_SECTORES_REZAGADOS_V2.md',
  'scripts/sector_turn/lib.js',
  'scripts/sector_turn/cycle_copy.js',
  'research/sector_turnaround_v2/counts.js',
  'research/sector_turnaround_v2/counts.json',
];
const CACHE = 'research/sector_turnaround_v2/_work/prices_max.json';   // no se sube a git (precios de Yahoo)
const OUT = path.join(__dirname, 'freeze.json');
// Texto con saltos de línea normalizados a LF: la huella es la del contenido en git, en cualquier equipo.
const sha = f => {
  let b = fs.readFileSync(path.join(ROOT, f));
  if (!f.endsWith('prices_max.json')) b = Buffer.from(b.toString('utf8').replace(/\r\n/g, '\n'), 'utf8');
  return crypto.createHash('sha256').update(b).digest('hex');
};
const now = Object.fromEntries([...FILES, CACHE].map(f => [f, sha(f)]));
if (process.argv.includes('--verify')) {
  const ref = JSON.parse(fs.readFileSync(OUT, 'utf8')).sha256;
  const bad = Object.keys(ref).filter(f => ref[f] !== now[f]);
  if (bad.length) { console.error('CAMBIADO: ' + bad.join(', ')); process.exit(1); }
  console.log('freeze OK (' + Object.keys(ref).length + ' ficheros)');
} else {
  if (fs.existsSync(OUT)) { console.error('freeze.json ya existe: no se reescribe'); process.exit(1); }
  fs.writeFileSync(OUT, JSON.stringify({ signed: '2026-11-28', signed_by: 'usuario', frozen_utc: new Date().toISOString(),
    note: 'Preregistro v2 firmado. El caché de precios (descargado el 2026-11-28 para el recuento) es la fuente de los bloques A y A′.',
    sha256: now }, null, 1) + '\n');
  console.log(JSON.stringify(now, null, 1));
}
