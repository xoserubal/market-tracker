'use strict';
// Prueba de equivalencia entre el cálculo ORIGINAL de cycle.html (ejecutado, no copiado) y la copia congelada.
//   node scripts/sector_turn/test_cycle_equivalence.js            # sintéticas + mutaciones
//   node scripts/sector_turn/test_cycle_equivalence.js --live AAAA-MM-DD [--server http://localhost:3000]
// --live usa datos reales de Yahoo con fecha de corte (buildQuoteData, la misma función que sirve /api/quote a la
// pestaña) y, si se indica --server, comprueba además que esos datos coinciden con lo que /api/quote devuelve.
const fs = require('fs');
const os = require('os');
const path = require('path');
const check = require('./cycle_check');
const original = require('./cycle_original');
const copy = require('./cycle_copy');

let pass = 0, fail = 0;
const ok = (c, msg) => { if (c) pass++; else { fail++; console.log('FALLO:', msg); } };

// Generador determinista (para poder repetir exactamente las pruebas).
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32); }

function randomRows(r, opts = {}) {
  const rows = {};
  for (const t of check.allTickers()) {
    if (r() < (opts.pMissing ?? 0.1)) continue;                        // ticker sin datos
    const d = { ticker: t, m3: Math.round((r() - 0.45) * 80), m1: Math.round((r() - 0.45) * 30) };
    if (r() < (opts.pNoM1 ?? 0.08)) d.m1 = null;                        // fallback relM1 → relM3
    if (r() < (opts.pNoM3 ?? 0.05)) d.m3 = null;                        // ticker cargado pero sin 3M
    rows[t] = d;
  }
  if (opts.noSpy) delete rows.SPY;
  if (opts.spyNoM1 && rows.SPY) rows.SPY.m1 = null;
  return rows;
}

// 1. Estática
const st = check.staticCheck();
ok(st.ok, 'comprobación estática: ' + st.problems.join('; '));

// 2. Casos sintéticos (incluye ausencias, fallbacks, sin SPY, todo vacío y empates)
const r = rng(20261128);
const cases = [];
for (let i = 0; i < 400; i++) cases.push(randomRows(r));
for (let i = 0; i < 50; i++) cases.push(randomRows(r, { pMissing: 0.6, pNoM1: 0.4, pNoM3: 0.3 }));
for (let i = 0; i < 25; i++) cases.push(randomRows(r, { noSpy: true }));
for (let i = 0; i < 25; i++) cases.push(randomRows(r, { spyNoM1: true }));
cases.push({});
cases.push({ SPY: { m1: 1, m3: 2 } });
const tie = {}; for (const t of check.allTickers()) tie[t] = { m1: 0, m3: 0 }; cases.push(tie);    // todas empatadas
let nDiff = 0;
for (const rows of cases) { const res = check.computeBoth(rows); if (!res.equal) { nDiff++; if (nDiff <= 3) console.log(JSON.stringify(res.diffs).slice(0, 600)); } }
ok(nDiff === 0, `casos sintéticos con diferencias: ${nDiff} de ${cases.length}`);
console.log(`casos sintéticos: ${cases.length}, diferencias: ${nDiff}`);

// 3. Mutaciones: la comprobación tiene que detectar un cambio real del original (si no, no prueba nada).
function mutated(transform) {
  const src = fs.readFileSync(original.CYCLE_HTML, 'utf8');
  const out = transform(src);
  if (out === src) throw new Error('la mutación no cambió nada');
  const f = path.join(os.tmpdir(), `cycle_mut_${process.pid}_${Math.random().toString(36).slice(2)}.html`);
  fs.writeFileSync(f, out);
  try { return original.load(f); } finally { fs.unlinkSync(f); }
}
function differs(api, rows) {
  const a = api.calcPhaseScores(api.CYCLE_MAP, rows).map(p => [p.phase, p.score, p.loaded, p.total]);
  const b = copy.calcPhaseScores(copy.CYCLE_MAP, rows).map(p => [p.phase, p.score, p.loaded, p.total]);
  return !check.same(a, b);
}
const probe = randomRows(rng(7), { pMissing: 0, pNoM1: 0, pNoM3: 0 });
const muts = {
  'peso 0,7 → 0,6': s => s.replace('alpha: relM3 * 0.7 + relM1 * 0.3', 'alpha: relM3 * 0.6 + relM1 * 0.4'),
  'quitar un ticker de la tabla': s => s.replace('ticker: "UNP", role: "leader",', 'ticker: "UNPX", role: "leader",'),
  'fallback distinto': s => s.replace('if (usedFallback) relM1 = relM3;', 'if (usedFallback) relM1 = 0;'),
};
for (const [name, fn] of Object.entries(muts)) {
  const api = mutated(fn);
  ok(api.sha256 !== copy.ORIGINAL_SHA256, `mutación «${name}»: la huella no cambió`);
  const rows = name === 'fallback distinto' ? randomRows(rng(9), { pMissing: 0, pNoM1: 0.5, pNoM3: 0 }) : probe;
  ok(differs(api, rows), `mutación «${name}»: el resultado no cambió`);
}
// Un cambio fuera de los fragmentos (p. ej. un estilo) no altera la huella.
{
  const api = mutated(s => s.replace('MARKET CYCLE PHASE ESTIMATOR', 'MARKET CYCLE PHASE ESTIMATOR '));
  ok(api.sha256 === copy.ORIGINAL_SHA256, 'un cambio de presentación alteró la huella');
}

// 4. Datos reales con fecha de corte (opcional)
async function live(cutoff, server) {
  const { buildQuoteData } = require('../../shared/quote-lib');
  const rows = {}, missing = [];
  for (const t of check.allTickers()) {
    try { rows[t] = await buildQuoteData(t, { cutoffDate: cutoff }); } catch (e) { missing.push(`${t}: ${e.message}`); }
  }
  const res = check.computeBoth(rows);
  ok(res.equal, `datos reales ${cutoff}: diferencias ${JSON.stringify(res.diffs).slice(0, 400)}`);
  const stale = Object.values(rows).filter(d => d.asOf.slice(0, 10) !== cutoff).map(d => `${d.ticker} ${d.asOf.slice(0, 10)}`);
  console.log(`datos reales ${cutoff}: ${Object.keys(rows).length} tickers, sin dato: ${missing.length}, vela distinta del corte: ${stale.length} ${stale.slice(0, 6).join(', ')}`);
  console.log('fase dominante:', res.summary?.dominant, '| puntuaciones:', res.phases.map(p => `${p.order}:${p.score == null ? '—' : p.score.toFixed(2)}`).join(' '));
  if (server) {
    let mism = 0, n = 0;
    for (const t of Object.keys(rows)) {
      try {
        const d = await (await fetch(`${server}/api/quote/${encodeURIComponent(t)}`)).json();
        if (d.error) continue;
        n++;
        if (d.m1 !== rows[t].m1 || d.m3 !== rows[t].m3) { mism++; if (mism <= 5) console.log('  /api/quote distinto:', t, d.m1, d.m3, 'vs', rows[t].m1, rows[t].m3, d.asOf); }
      } catch { /* servidor no disponible */ }
    }
    console.log(`/api/quote frente a buildQuoteData con corte: ${n} comparados, ${mism} distintos`);
    ok(n > 0 && mism === 0, `/api/quote y los datos con corte no coinciden (${mism}/${n})`);
  }
  return res;
}

(async () => {
  const i = process.argv.indexOf('--live');
  if (i > 0) {
    const s = process.argv.indexOf('--server');
    await live(process.argv[i + 1], s > 0 ? process.argv[s + 1] : null);
  }
  console.log(`\n${pass} pasadas, ${fail} fallidas · huella original ${check.staticCheck().original_sha256.slice(0, 12)}`);
  process.exit(fail ? 1 : 0);
})();
