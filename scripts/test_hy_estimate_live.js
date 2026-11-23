// Pruebas sin red de shared/hy-estimate-live.js (computeFromBars).
const assert = require("assert");
const { computeFromBars } = require("../shared/hy-estimate-live.js");
let n = 0; const t = (name, fn) => { fn(); n++; console.log("ok -", name); };
const latest = {
  official: { date: "2026-11-20", value_bp: 376 }, estimates: [], generated_at_utc: "x",
  model: { id: "m", resid_sigma_bp: 3, coef: { const: 0, HJ: -20, IEI: 20, HJ_l1: 0, IEI_l1: 0 } },
  live_reference: { ref_date: "2026-11-20", ref_level_bp: 376, ref_bridge_days: 0, ret_ref_day: { HJ: 0, IEI: 0 } },
};
const mk = (rows) => ({ bars: rows.map(([date, close, div = 0]) => ({ date, close, div })), meta: {} });
t("sin sesiones nuevas -> dato oficial", () => {
  const r = computeFromBars(latest, { HYG: mk([["2026-11-20", 100]]), JNK: mk([["2026-11-20", 100]]), IEI: mk([["2026-11-20", 100]]) });
  assert.equal(r.status, "official_only"); assert.equal(r.est_bp, 376);
});
t("HY sube 1% -> -20 pb", () => {
  const b = mk([["2026-11-20", 100], ["2026-11-23", 101]]); const i = mk([["2026-11-20", 100], ["2026-11-23", 100]]);
  const r = computeFromBars(latest, { HYG: b, JNK: b, IEI: i });
  assert.ok(Math.abs(r.est_bp - (376 - 20 * Math.log(1.01) * 100)) < 0.11); assert.equal(r.bridge_days, 1);
});
t("dia sin dividendo descontado no mueve la estimacion", () => {
  const b = mk([["2026-11-20", 100], ["2026-11-23", 99.6, 0.4]]); const i = mk([["2026-11-20", 100], ["2026-11-23", 100]]);
  const r = computeFromBars(latest, { HYG: b, JNK: b, IEI: i });
  assert.ok(Math.abs(r.est_bp - 376) < 0.01);
});
t("dos sesiones -> banda mas ancha", () => {
  const b = mk([["2026-11-20", 100], ["2026-11-23", 100], ["2026-11-24", 100]]);
  const r = computeFromBars(latest, { HYG: b, JNK: b, IEI: b });
  assert.equal(r.bridge_days, 2); assert.ok(Math.abs((r.high_bp - r.est_bp) - 1.2816 * 3 * Math.SQRT2) < 0.06);
});
t("referencia fuera de la ventana -> stale", () => {
  const b = mk([["2026-11-23", 100]]);
  assert.equal(computeFromBars(latest, { HYG: b, JNK: b, IEI: b }).status, "stale_reference");
});
t("usa la estimacion del pipeline si ya cubre la sesion", () => {
  const l2 = { ...latest, estimates: [{ date: "2026-11-23", est_bp: 370, low_bp: 366, high_bp: 374, bridge_days: 1 }],
    live_reference: { ...latest.live_reference, ref_date: "2026-11-23", ref_level_bp: 370, ref_bridge_days: 1 } };
  const b = mk([["2026-11-20", 100], ["2026-11-23", 100]]);
  const r = computeFromBars(l2, { HYG: b, JNK: b, IEI: b });
  assert.equal(r.status, "pipeline"); assert.equal(r.est_bp, 370);
});
console.log(`${n} tests ok`);
