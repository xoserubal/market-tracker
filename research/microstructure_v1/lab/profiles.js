// Mapa de calor tiempo × precio del perfil de volumen (estimado con barras), con POC, área de valor, cierre y
// concentraciones persistentes. Fuente y calidad visibles; enlace a cada sesión con trades y quotes bajo demanda.
const $ = id => document.getElementById(id);
const fmt = (x, d = 2) => x == null || Number.isNaN(x) ? "—" : Number(x).toLocaleString("es-ES", {maximumFractionDigits: d, minimumFractionDigits: d});
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const FLAG = {corp_event: "evento corporativo no reconstruido", split_day: "día de split", outage: "caída de datos", low_cov: "cobertura < 50 %"};
let W = null, geom = null;

async function getJ(path, p) { const r = await fetch(path + "?" + new URLSearchParams(p)); return r.json(); }

async function load() {
  $("msg").textContent = "cargando…";
  const w = await getJ("/api/vp/window", {symbol: $("sym").value.trim().toUpperCase(), end: $("end").value, n: $("n").value});
  if (w.error || !w.ok) { $("msg").innerHTML = `<span class="bad">${w.error || w.reason}</span>`; return; }
  W = w; $("msg").textContent = "";
  const per = (w.periods || []).map(p => `${p.period} ${p.first}→${p.last}`).join(" · ");
  $("meta").innerHTML = `<span class="chip">fuente: ${w.source} (${w.version})</span><span class="chip">${w.n} sesiones ${w.start} → ${w.end}</span>` +
    `<span class="chip">rejilla común ${fmt(w.grid_step, 4)} $ · ${w.price_scale}</span><span class="chip">entidad ${w.entity} (${w.period})</span>` +
    (w.quality_flags.length ? `<span class="chip warn">calidad: ${w.quality_flags.map(f => FLAG[f] || f).join(", ")}</span>` : `<span class="chip">sin marcas de calidad</span>`) +
    (w.missing_sessions.length ? `<span class="chip warn">sesiones sin perfil: ${w.missing_sessions.join(", ")}</span>` : "") +
    (w.observed_available.length ? `<span class="chip">perfil observado con trades disponible: ${w.observed_available.join(", ")}</span>` : "") +
    `<div>Datos disponibles del valor: ${per}. Estimado con barras de 1 min, sesión regular sin subasta de cierre (la de apertura va dentro de la barra de las 09:30; los minutos con solo lotes impares no tienen barra).</div>`;
  draw(); summary(); dayTable();
}

function draw() {
  const c = $("hm"), r = c.getBoundingClientRect();
  c.width = r.width * devicePixelRatio; c.height = r.height * devicePixelRatio;
  const ctx = c.getContext("2d"); ctx.scale(devicePixelRatio, devicePixelRatio); ctx.clearRect(0, 0, r.width, r.height);
  const w = W, nD = w.days.length, L = w.levels;
  const pad = {l: 62, r: 150, t: 10, b: 26}, H = r.height - pad.t - pad.b, Wd = r.width - pad.l - pad.r;
  // rango de precios: niveles con volumen y precios del día
  const px = w.days.flatMap(d => [d.h, d.l]);
  let lo = Math.min(...px), hi = Math.max(...px);
  const g = w.grid_step;
  const Y = p => pad.t + H * (hi - p) / (hi - lo), colW = Wd / nD, X = i => pad.l + colW * i;
  const norm = $("norm").value;
  const amax = Math.max(...w.matrix.flat());
  w.matrix.forEach((row, i) => {
    const tot = row.reduce((a, b) => a + b, 0), m = Math.max(...row);
    row.forEach((v, j) => {
      if (!v) return; const p = L[j]; if (p < lo || p > hi) return;
      const a = norm === "day" ? v / m : Math.log1p(v) / Math.log1p(amax);
      ctx.fillStyle = `rgba(31,95,168,${(0.06 + 0.9 * a).toFixed(3)})`;
      ctx.fillRect(X(i) + 0.5, Y(p + g / 2), colW - 1, Math.max(1, Y(p - g / 2) - Y(p + g / 2)));
    });
  });
  // persistencia continua: fracción de días en que cada nivel está dentro del área de valor del día (gradiente)
  (w.persistence_va || []).forEach((v, j) => { const p = L[j]; if (!v || p < lo || p > hi) return;
    ctx.fillStyle = `rgba(148,103,189,${(0.1 + 0.9 * v).toFixed(3)})`;
    ctx.fillRect(pad.l + Wd + 4, Y(p + g / 2), 8, Math.max(1, Y(p - g / 2) - Y(p + g / 2))); });
  // compuesto
  const comp = L.map((p, j) => w.matrix.reduce((a, row) => a + row[j], 0)), cm = Math.max(...comp);
  ctx.fillStyle = "rgba(31,95,168,.55)";
  comp.forEach((v, j) => { const p = L[j]; if (!v || p < lo || p > hi) return; ctx.fillRect(pad.l + Wd + 16, Y(p + g / 2), (pad.r - 22) * v / cm, Math.max(1, Y(p - g / 2) - Y(p + g / 2))); });
  // área de valor, rango, cierre, POC
  w.days.forEach((d, i) => {
    const x0 = X(i), xm = x0 + colW / 2;
    ctx.strokeStyle = "#2ca02c"; ctx.lineWidth = 1.4;
    for (const p of [d.va_low, d.va_high]) { ctx.beginPath(); ctx.moveTo(x0 + 1, Y(p)); ctx.lineTo(x0 + colW - 1, Y(p)); ctx.stroke(); }
    ctx.strokeStyle = css("--ink"); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(xm, Y(d.h)); ctx.lineTo(xm, Y(d.l)); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(xm, Y(d.c)); ctx.lineTo(x0 + colW - 2, Y(d.c)); ctx.lineWidth = 2; ctx.stroke();
    ctx.beginPath(); ctx.arc(xm, Y(d.poc), 3.5, 0, 7); ctx.strokeStyle = "#d62728"; ctx.lineWidth = 1.6;
    if (d.conf === "baja") ctx.stroke(); else { ctx.fillStyle = "#d62728"; ctx.fill(); }
    if (d.flags.length) { ctx.fillStyle = "#b54708"; ctx.fillRect(x0 + 1, pad.t + H + 2, colW - 2, 4); }
  });
  // ejes
  ctx.fillStyle = css("--muted"); ctx.font = "11px system-ui"; ctx.strokeStyle = css("--line");
  for (let k = 0; k <= 6; k++) { const p = hi - (hi - lo) * k / 6; ctx.fillText(p.toFixed(2), 4, Y(p) + 4); }
  const step = Math.max(1, Math.ceil(nD / 10));
  w.days.forEach((d, i) => { if (i % step === 0 || i === nD - 1) ctx.fillText(d.date.slice(5), X(i) + 2, r.height - 8); });
  geom = {pad, colW, nD};
}

function summary() {
  const w = W, comp = w.composite;
  const sh = w.poc_shifts.filter(s => s.material);
  $("sum").innerHTML = `<table>
   <tr><th>Medida</th><th>Valor</th><th style="text-align:left">Lectura</th></tr>
   <tr><td>Precio (apertura → cierre)</td><td>${fmt(w.price_change_pct)} %</td><td style="text-align:left">rango de la ventana ${fmt(w.range_pct)} %</td></tr>
   <tr><td>POC: desplazamiento neto primer → último día</td><td>${fmt(w.poc_net_shift_bps, 1)} pb</td><td style="text-align:left">incluye saltos entre casi empates</td></tr>
   <tr><td>POC: desplazamientos materiales</td><td>${w.poc_material_shifts} de ${w.n - 1}</td><td style="text-align:left">fuera de la zona del 90 % del día anterior y viceversa, sin días de confianza baja</td></tr>
   <tr><td>POC: suma y neto de los materiales</td><td>${fmt(w.poc_material_path_bps, 1)} / ${fmt(w.poc_material_net_bps, 1)} pb</td><td style="text-align:left">coherencia de dirección ${w.poc_material_consistency == null ? "—" : fmt(w.poc_material_consistency, 2)} (1 = todos en el mismo sentido)</td></tr>
   <tr><td>Área de valor: Jaccard medio entre días consecutivos</td><td>${fmt(w.va_jaccard_mean, 3)}</td><td style="text-align:left">anchura primer / último día: ${w.va_width_first_last_bps.map(x => fmt(x, 0)).join(" / ")} pb</td></tr>
   <tr><td>Distancia de variación total media entre días</td><td>${fmt(w.tvd_mean, 3)}</td><td style="text-align:left">0 = mismo reparto por niveles</td></tr>
   <tr><td>Perfil compuesto: POC y confianza</td><td>${fmt(comp.poc_price)}</td><td style="text-align:left">${comp.poc_confidence}; cuota del nivel máximo ${fmt(comp.top1_share * 100, 1)} %; segmentos de la zona del 90 %: ${comp.zone90_n_segments}</td></tr>
   <tr><td>Persistencia máxima (área de valor diaria)</td><td>${fmt(w.max_persistence_va * 100, 0)} %</td><td style="text-align:left">el nivel ${fmt(w.max_persistence_va_price)} está dentro del área de valor del día en esa fracción de sesiones; con la zona del 90 %: ${fmt(w.max_persistence_zone90 * 100, 0)} %</td></tr>
   <tr><td>Concentraciones persistentes (zona del 90 % ≥ 50 % de los días)</td><td>${w.persistent.length}</td><td style="text-align:left">${w.persistent.map(z => `${fmt(z.low)}–${fmt(z.high)} (${fmt(z.max_persistence * 100, 0)} % de los días, ${fmt(z.composite_share * 100, 1)} % del volumen)`).join("; ") || "ninguna"}</td></tr>
  </table>`;
}

function dayTable() {
  const w = W;
  $("days").innerHTML = `<table><tr><th>Día</th><th>Cierre</th><th>Volumen</th><th>POC</th><th>Confianza</th><th>Área de valor</th><th>Zona del 90 %</th><th>Cambio POC</th><th>Jaccard AV</th><th>Calidad</th><th></th></tr>` +
    w.days.map((d, i) => { const s = i ? w.poc_shifts[i - 1] : null, o = i ? w.overlap[i - 1] : null;
      return `<tr><td>${d.date}</td><td>${fmt(d.c)}</td><td>${fmt(d.volume, 0)}</td><td>${fmt(d.poc)}</td><td>${d.conf}</td><td>${fmt(d.va_low)}–${fmt(d.va_high)}</td>
      <td>${d.zone90.map(z => `${fmt(z[0])}–${fmt(z[1])}`).join(" · ")}</td><td>${s ? fmt(s.shift_bps, 1) + " pb" + (s.material ? " ●" : "") : ""}</td><td>${o ? fmt(o.va_jaccard, 2) : ""}</td>
      <td class="warn">${d.flags.map(f => FLAG[f] || f).join(", ")}</td><td><a href="/access.html?symbol=${encodeURIComponent(d.symbol)}&day=${d.date}&start=09:30&end=16:00">trades</a></td></tr>`; }).join("") +
    `</table><div class="note">● = desplazamiento material. Volumen en acciones a la escala del último día (corregido por splits).</div>`;
}

$("hm").addEventListener("click", e => {
  if (!W || !geom) return;
  const r = e.target.getBoundingClientRect(), i = Math.floor((e.clientX - r.left - geom.pad.l) / geom.colW);
  if (i < 0 || i >= geom.nD) return;
  const d = W.days[i];
  window.open(`/access.html?symbol=${encodeURIComponent(d.symbol)}&day=${d.date}&start=09:30&end=16:00`, "_blank");
});
$("go").onclick = load;
$("norm").onchange = () => W && draw();
window.addEventListener("resize", () => W && draw());
const u = new URLSearchParams(location.search);
for (const [k, id] of [["symbol", "sym"], ["end", "end"], ["n", "n"]]) if (u.get(k)) $(id).value = u.get(k);
getJ("/api/vp/symbols", {}).then(r => { $("symlist").innerHTML = [...new Set((r.symbols || []).map(x => x.symbol))].map(s => `<option value="${s}">`).join(""); }).catch(() => {});
if (u.get("symbol")) load();
