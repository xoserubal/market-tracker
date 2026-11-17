// Pruebas de las funciones puras de maquetación del visor.  node research/microstructure_v1/tests/test_lab_layout.js
'use strict';
const assert = require('assert');
const L = require('../lab/app.js');
let n = 0;
const t = (name, fn) => { fn(); n++; };

t('fmtVol', () => {
  assert.strictEqual(L.fmtVol(950), '950');
  assert.strictEqual(L.fmtVol(1500), '1.5K');
  assert.strictEqual(L.fmtVol(25000), '25K');
  assert.strictEqual(L.fmtVol(-2500000), '-2.5M');
  assert.strictEqual(L.fmtVol(12000000), '12M');
});
t('priceToY: precios altos arriba y un nivel ocupa rowH píxeles', () => {
  const v = { top: 10, pMax: 151, step: 0.1, rowH: 20, offY: 0 };
  assert.strictEqual(L.priceToY(151, v), 10);
  assert.ok(Math.abs(L.priceToY(150.9, v) - 30) < 1e-6);
  assert.ok(L.priceToY(149, v) > L.priceToY(150, v));
  assert.strictEqual(L.priceToY(151, { ...v, offY: 5 }), 5);
});
t('barX', () => {
  const v = { left: 64, barW: 100, offX: 0 };
  assert.strictEqual(L.barX(0, v), 64);
  assert.strictEqual(L.barX(3, v), 364);
  assert.strictEqual(L.barX(3, { ...v, offX: 50 }), 314);
});
t('cellAlpha crece con |delta| y está acotado', () => {
  assert.strictEqual(L.cellAlpha(0, 0), 0);
  assert.ok(L.cellAlpha(10, 100) < L.cellAlpha(50, 100));
  assert.ok(L.cellAlpha(-100, 100) <= 0.85 && L.cellAlpha(-100, 100) > 0.8);
});
t('detailLevel: números solo si caben', () => {
  assert.strictEqual(L.detailLevel(120, 16), 'text');
  assert.strictEqual(L.detailLevel(40, 16), 'heat');
  assert.strictEqual(L.detailLevel(120, 6), 'heat');
});
t('priceRange incluye el último paso', () => {
  const r = L.priceRange([{ p: 149.8 }, { p: 150.5 }, { p: 150.1 }], 0.1);
  assert.strictEqual(r.lo, 149.8);
  assert.ok(Math.abs(r.hi - 150.6) < 1e-9);
});
t('nyTime en hora de Nueva York', () => {
  assert.strictEqual(L.nyTime(Date.parse('2026-11-12T14:30:00Z')).slice(0, 5), '09:30');
  assert.strictEqual(L.nyTime(Date.parse('2026-07-01T13:30:00Z')).slice(0, 5), '09:30');   // horario de verano
});
console.log(`OK ${n} pruebas de maquetación`);
