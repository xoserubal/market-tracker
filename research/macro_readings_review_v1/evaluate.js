// Revisión de lecturas macro: aplica las funciones REALES de shared/market-macro.js (STATUS) a la historia de cada
// serie, con los mismos desfases que usa la página (server.js / shared/quote-lib.js), y resume:
// etiqueta actual, percentil del valor actual, frecuencia de cada etiqueta en 10 y 3 años.
'use strict';
const fs = require('fs');
const path = require('path');
const { STATUS } = require(path.join(__dirname, '..', '..', 'shared', 'market-macro.js'));
const S = JSON.parse(fs.readFileSync(path.join(__dirname, '_work', 'series.json'), 'utf8'));

// desfases en observaciones: [1S, 1M, 3M, 6M, 1A] (null = no aplica)
const OFF = { daily: [5, 21, 65, 130, 252], yahoo: [5, 21, 63, 126, 252], weekly: [1, 4, 13, 26, 52], monthly: [null, 1, 3, 6, 12] };
const ITEMS = [
  { id: 'vix', name: 'VIX', type: 'vix', key: '^VIX', off: 'yahoo' },
  { id: 'dxy', name: 'DXY', type: 'dxy', key: 'DX-Y.NYB', off: 'yahoo' },
  { id: 'tnx', name: '10Y (^TNX)', type: 'yield_10y', key: '^TNX', off: 'yahoo' },
  { id: 'dfii10', name: '10Y TIPS real', type: 'real_yield_10y', key: 'DFII10', off: 'daily' },
  { id: 'irx', name: '3M T-Bill (^IRX)', type: 'short_rate', key: '^IRX', off: 'yahoo' },
  { id: 'c3m', name: 'Curva 10Y-3M', type: 'curve_pct', key: 'T10Y3M', off: 'daily' },
  { id: 'c2y', name: 'Curva 10Y-2Y', type: 'curve_pct', key: 'T10Y2Y', off: 'daily' },
  { id: 'hy', name: 'HY spread', type: 'hy_spread', key: 'BAMLH0A0HYM2', off: 'daily' },
  { id: 'ig', name: 'IG spread', type: 'ig_spread', key: 'BAMLC0A0CM', off: 'daily' },
  { id: 'bei', name: 'Breakeven 5Y', type: 'breakeven', key: 'T5YIE', off: 'daily' },
  { id: 'pmi', name: 'INDPRO (nivel)', type: 'pmi', key: 'INDPRO', off: 'monthly' },
  { id: 'm2', name: 'M2', type: 'm2', key: 'WM2NS', off: 'weekly' },
  { id: 'walcl', name: 'Balance Fed', type: 'fed_bs', key: 'WALCL', off: 'weekly' },
  { id: 'netliq', name: 'Liquidez neta (como hoy)', type: 'net_liq', key: 'NETLIQ_BUG', off: 'weekly' },
  { id: 'netliq_ok', name: 'Liquidez neta (unidades corregidas)', type: 'net_liq', key: 'NETLIQ_OK', off: 'weekly' },
];

// liquidez neta: ancla WALCL, valor anterior más cercano de RRP y TGA (como /api/fred3)
function nearestPrior(arr, d) { let lo = 0, hi = arr.length - 1, f = null; while (lo <= hi) { const m = (lo + hi) >> 1; if (arr[m].date <= d) { f = arr[m].value; lo = m + 1; } else hi = m - 1; } return f; }
const W = S.WALCL, R = S.RRPONTSYD, T = S.WTREGEN;
S.NETLIQ_BUG = W.map((o) => ({ date: o.date, value: o.value - (nearestPrior(R, o.date) ?? 0) - (nearestPrior(T, o.date) ?? 0) }));
S.NETLIQ_OK = W.map((o) => ({ date: o.date, value: o.value - 1000 * (nearestPrior(R, o.date) ?? 0) - (nearestPrior(T, o.date) ?? 0) }));

const pct = (arr, v) => { const b = arr.filter((x) => x < v).length, e = arr.filter((x) => x === v).length; return Math.round(1000 * (b + e / 2) / arr.length) / 10; };
const out = [];
for (const it of ITEMS) {
  const s = S[it.key]; const off = OFF[it.off];
  const labels = s.map((o, i) => {
    const at = (k) => (k == null || i - k < 0) ? null : s[i - k].value;
    const d = off.map((k) => { const p = at(k); return p == null ? null : o.value - p; });
    const st = STATUS[it.type] ? STATUS[it.type](o.value, d[0], d[1], d[4]) : null;
    return { date: o.date, value: o.value, label: st ? st[0] : null, dM: d[1], d3: d[2], dY: d[4] };
  });
  const last = labels[labels.length - 1];
  const since = (y) => labels.filter((r) => r.date >= y);
  const dist = (rows) => { const c = {}; let n = 0; for (const r of rows) { if (!r.label) continue; const k = r.label.replace(/ \(.*\)/, ''); c[k] = (c[k] || 0) + 1; n++; }
    return Object.fromEntries(Object.entries(c).sort((a, b) => b[1] - a[1]).map(([k, v]) => [k, Math.round(1000 * v / n) / 10])); };
  const vals10 = since('2016-11-01').map((r) => r.value), valsAll = labels.map((r) => r.value);
  // número de cambios de etiqueta en el último año (estabilidad)
  const y1 = since('2025-11-17'); let flips = 0; const base = (l) => (l || '').replace(/ \(.*\)/, '');   // sin la cifra entre paréntesis
  for (let k = 1; k < y1.length; k++) if (base(y1[k].label) !== base(y1[k - 1].label)) flips++;
  out.push({ id: it.id, name: it.name, first: s[0].date, last_date: last.date, value: last.value, label: last.label,
    dM: last.dM, d3m: last.d3, dY: last.dY, pct_10y: pct(vals10, last.value), pct_all: pct(valsAll, last.value),
    dist_10y: dist(since('2016-11-01')), dist_3y: dist(since('2023-11-17')), label_changes_last_year: flips, obs_last_year: y1.length });
}
fs.writeFileSync(path.join(__dirname, '_work', 'evaluation.json'), JSON.stringify(out, null, 1));
for (const r of out) {
  console.log(`\n${r.name} [${r.first}→${r.last_date}] valor ${r.value.toFixed(3)} → «${r.label}» · Δ1M ${r.dM == null ? '—' : r.dM.toFixed(3)} Δ3M ${r.d3m == null ? '—' : r.d3m.toFixed(3)} · pctl 10a ${r.pct_10y} (todo ${r.pct_all}) · cambios de etiqueta/año ${r.label_changes_last_year}/${r.obs_last_year}`);
  console.log('  10a:', JSON.stringify(r.dist_10y)); console.log('  3a :', JSON.stringify(r.dist_3y));
}
