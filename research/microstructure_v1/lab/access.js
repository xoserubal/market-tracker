// Acceso libre: ventana manual, coste, descarga confirmada, cinta de operaciones/cotizaciones, casos y varias sesiones.
const $ = id => document.getElementById(id);
const fmt = (x, d = 0) => x == null || Number.isNaN(x) ? "—" : Number(x).toLocaleString("es-ES", {maximumFractionDigits: d, minimumFractionDigits: d});
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const SEG = {
  pre: ["Premercado", "#8a94a0"], open_auction: ["Subasta de apertura", "#e07a10"], continuous: ["Continua", "#1f6fd1"],
  halt_reopen: ["Reapertura tras suspensión", "#8e44ad"], close_auction: ["Subasta de cierre", "#c0392b"],
  post: ["After hours", "#4d5560"], late_report: ["Comunicación tardía", "#111"], nonstandard: ["Precio no estándar", "#9c6b00"],
  official_print: ["Impresión oficial (no suma volumen)", "#c0392b"], canceled: ["Cancelada", "#bbb"],
};
function q() {
  const p = {symbol: $("sym").value.trim().toUpperCase(), day: $("day").value, start: $("start").value.trim(), end: $("end").value.trim()};
  if ($("allowtest").checked) p.allow_test = "1";
  return p;
}
async function getJ(path, params) {
  const r = await fetch(path + "?" + new URLSearchParams(params));
  return r.json();
}
async function postJ(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  return r.json();
}
async function pollJob(id, msgEl) {
  for (;;) {
    const j = (await getJ("/api/jobs", {})).jobs[id];
    if (!j) return null;
    msgEl.textContent = `trabajo ${id}: ${j.status}`;
    if (!["queued", "running"].includes(j.status)) return j;
    await new Promise(r => setTimeout(r, 1500));
  }
}

// ── 1. estimación y descarga ──
$("bEst").onclick = async () => {
  $("est").textContent = "estimando…";
  const e = await getJ("/api/window/estimate", {...q(), quotes: $("quotes").checked ? "1" : "0"});
  if (e.error) { $("est").innerHTML = `<span class="bad">${e.error}</span>`; $("fetchRow").style.display = "none"; return; }
  let h = `<table><tr><th>Tipo</th><th>Trades en la ventana</th><th>Filas previstas (alto)</th><th>Peticiones</th><th>MB (alto)</th><th>Tramos que faltan</th></tr>`;
  for (const [k, v] of Object.entries(e.kinds))
    h += `<tr><td>${k}</td><td>${fmt(v.trades_in_window)}</td><td>${fmt(v.rows_est_high)}</td><td>${fmt(v.requests_est)}</td><td>${fmt(v.mb_est_high, 1)}</td><td>${v.missing_ranges.join(", ") || "ya descargado"}</td></tr>`;
  h += `</table><div>${e.minutes} min · fuente del cálculo: ${e.source} · total ${fmt(e.requests_est)} peticiones, ${fmt(e.mb_est_high, 1)} MB · usadas en 24 h: ${fmt(e.requests_last_24h)} de ${fmt(e.limits.daily_requests)}${e.in_reserved_period ? ' · <span class="warn">periodo reservado</span>' : ""}</div>`;
  if (e.blocked.length) h += `<div class="bad">Bloqueado: ${e.blocked.map(b => b.detail).join("; ")}</div>`;
  $("est").innerHTML = h;
  $("fetchRow").style.display = e.requests_est > 0 && !e.blocked.length ? "flex" : "none";
  $("confLbl").style.display = e.needs_confirmation ? "inline" : "none";
};
$("bFetch").onclick = async () => {
  const r = await postJ("/api/window/fetch", {...q(), quotes: $("quotes").checked, confirm: $("confirm").checked, allow_test: $("allowtest").checked});
  if (!r.job) { $("fetchMsg").textContent = r.status === "needs_confirmation" ? "hace falta confirmar" : JSON.stringify(r).slice(0, 300); return; }
  const j = await pollJob(r.job, $("fetchMsg"));
  if (j && j.result && j.result.result) $("fetchMsg").textContent = `hecho: ${j.result.result.requests} peticiones, ${j.result.result.mb} MB, ${j.result.result.seconds} s`;
  else if (j) $("fetchMsg").textContent = `${j.status} ${j.error || ""}`;
};

// ── 2. cinta ──
function axes(ctx, W, H, pad, x0, x1, y0, y1, xl) {
  ctx.strokeStyle = css("--line"); ctx.fillStyle = css("--muted"); ctx.font = "11px system-ui"; ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const y = pad.t + (H - pad.t - pad.b) * i / 5, v = y1 - (y1 - y0) * i / 5;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke(); ctx.fillText(v.toFixed(2), 4, y + 4);
  }
  for (let i = 0; i <= 6; i++) {
    const x = pad.l + (W - pad.l - pad.r) * i / 6; ctx.fillText(xl(x0 + (x1 - x0) * i / 6), x - 18, H - 6);
  }
}
const nyTime = ms => new Date(ms).toLocaleTimeString("es-ES", {timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: "2-digit"});
const nyDay = ms => new Date(ms).toLocaleDateString("es-ES", {timeZone: "America/New_York", month: "2-digit", day: "2-digit"});
function prep(c) {
  const r = c.getBoundingClientRect(); c.width = r.width * devicePixelRatio; c.height = r.height * devicePixelRatio;
  const ctx = c.getContext("2d"); ctx.scale(devicePixelRatio, devicePixelRatio); ctx.clearRect(0, 0, r.width, r.height);
  return [ctx, r.width, r.height];
}
$("bTape").onclick = async () => {
  $("tapeMsg").textContent = "cargando…";
  const p = q();
  if ($("blind").checked && $("cursor").value) { p.blind = "1"; p.cursor = $("cursor").value.trim(); }
  const t = await getJ("/api/window/tape", p);
  if (t.error) { $("tapeMsg").innerHTML = `<span class="bad">${t.error}</span>`; return; }
  if (!t.trades.length) { $("tapeMsg").textContent = t.note || "sin trades"; return; }
  $("tapeMsg").textContent = `${fmt(t.trades.length)} puntos${t.sampled ? " (muestra: todas las subastas, tardías y grandes; el resto uniforme)" : ""} · ${fmt(t.quotes.length)} cotizaciones (último valor por segundo)`;
  const [ctx, W, H] = prep($("cTape")), pad = {l: 56, r: 10, t: 10, b: 22};
  const ts = t.trades.map(d => d.t).concat(t.quotes.map(d => d.t));
  const x0 = Math.min(...ts), x1 = Math.max(...ts);
  const ps = t.trades.map(d => d.p).concat(t.quotes.flatMap(d => [d.b, d.a]));
  const lo = quantile(ps, .002), hi = quantile(ps, .998), y0 = lo - (hi - lo) * .05, y1 = hi + (hi - lo) * .05;
  const X = v => pad.l + (W - pad.l - pad.r) * (v - x0) / Math.max(1, x1 - x0), Y = v => pad.t + (H - pad.t - pad.b) * (y1 - v) / (y1 - y0);
  axes(ctx, W, H, pad, x0, x1, y0, y1, nyTime);
  for (const [k, col] of [["b", "#2e8b57"], ["a", "#c0392b"]]) {
    ctx.strokeStyle = col; ctx.globalAlpha = .55; ctx.beginPath();
    t.quotes.forEach((d, i) => i ? ctx.lineTo(X(d.t), Y(d[k])) : ctx.moveTo(X(d.t), Y(d[k]))); ctx.stroke(); ctx.globalAlpha = 1;
  }
  for (const k of ["open", "close"]) {
    const b = t.session_bounds[k]; if (!b) continue; const v = Date.parse(b); if (v < x0 || v > x1) continue;
    ctx.strokeStyle = css("--muted"); ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(X(v), pad.t); ctx.lineTo(X(v), H - pad.b); ctx.stroke(); ctx.setLineDash([]);
  }
  const smax = Math.max(...t.trades.map(d => d.s));
  for (const d of t.trades) {
    const [, col] = SEG[d.seg] || ["", "#999"], r = 1.2 + 6 * Math.sqrt(d.s / smax);
    ctx.beginPath(); ctx.arc(X(d.t), Y(d.p), r, 0, 7);
    if (d.seg === "late_report" || !d.vol) { ctx.strokeStyle = col; ctx.stroke(); } else { ctx.fillStyle = col; ctx.globalAlpha = .6; ctx.fill(); ctx.globalAlpha = 1; }
  }
  $("legend").innerHTML = Object.entries(SEG).filter(([k]) => t.summary[k]).map(([k, [n, c]]) => `<span><i style="background:${c}"></i>${n}</span>`).join("") +
    `<span>círculo vacío = no suma volumen o es tardía · líneas: bid (verde) / ask (rojo)</span>`;
  let h = `<table><tr><th>Tramo</th><th>Operaciones</th><th>Acciones</th><th>Suman volumen</th><th>Efectivo</th><th>VWAP</th><th>Mín.</th><th>Máx.</th><th>Lotes impares</th><th>Acciones TRF</th></tr>`;
  for (const [k, v] of Object.entries(t.summary)) {
    if (k === "_all") continue;
    h += `<tr><td>${(SEG[k] || [k])[0]}</td><td>${fmt(v.trades)}</td><td>${fmt(v.shares)}</td><td>${fmt(v.shares_counted_in_volume)}</td><td>${fmt(v.notional)}</td><td>${fmt(v.vwap, 3)}</td><td>${fmt(v.price_min, 2)}</td><td>${fmt(v.price_max, 2)}</td><td>${fmt(v.odd_lot_trades)}</td><td>${fmt(v.trf_shares)}</td></tr>`;
  }
  h += `</table><div class="note">Recuentos y volúmenes con TODAS las operaciones de la ventana (el gráfico es una muestra). Duplicados por identificador quitados: ${t.summary._all.duplicate_ids_removed}. ${t.quote_summary ? `Diferencial relativo: mediana ${(t.quote_summary.spread_rel_median * 1e4).toFixed(1)} pb, p95 ${(t.quote_summary.spread_rel_p95 * 1e4).toFixed(1)} pb.` : "Sin quotes en la ventana."}</div>`;
  $("tapeSum").innerHTML = h;
};
function quantile(a, p) { const s = a.filter(Number.isFinite).sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.max(0, Math.floor(p * s.length)))]; }

// ── 3. casos ──
async function loadCases() {
  const c = (await getJ("/api/cases", {symbol: $("sym").value.trim().toUpperCase()})).cases || [];
  $("cases").innerHTML = c.length ? `<table><tr><th>Caso</th><th>Tipo</th><th>Días</th><th>Ventana (UTC)</th><th>Unidades</th><th>Nota</th><th>Desenlace conocido</th></tr>` +
    c.map(x => `<tr><td>${x.case_id}</td><td>${x.kind}</td><td>${x.start_day}${x.end_day !== x.start_day ? " → " + x.end_day : ""}</td><td>${(x.start_utc || "").slice(11, 16)}–${(x.end_utc || "").slice(11, 16)}</td><td>${JSON.parse(x.data_units).length}</td><td style="text-align:left">${x.note || ""}</td><td>${x.outcome_known_at_selection ? "sí" : "no"}</td></tr>`).join("") + "</table>" : `<span class="note">sin casos guardados para este valor</span>`;
}
$("bCase").onclick = async () => {
  const p = q(); let su = null, eu = null;
  try { const e = await getJ("/api/window/estimate", {...p, quotes: "0"}); su = e.start_utc; eu = e.end_utc; } catch (e) { /* sin barras: se guarda igualmente */ }
  const r = await postJ("/api/case", {kind: "manual_window", symbol: p.symbol, start_day: p.day, start_utc: su, end_utc: eu,
    params: {start_ny: p.start, end_ny: p.end, quotes: $("quotes").checked}, note: $("note").value,
    outcome_known_at_selection: $("known").checked, allow_test: $("allowtest").checked});
  $("caseMsg").textContent = r.case_id ? `guardado ${r.case_id} (${r.data_units} unidades de datos con su sha256)` : JSON.stringify(r);
  loadCases();
};

// ── 4. varias sesiones ──
$("bMulti").onclick = async () => {
  $("multiMsg").textContent = "cargando…";
  const p = {symbol: $("sym").value.trim().toUpperCase(), start_day: $("d0").value, end_day: $("d1").value, res: $("res").value};
  if ($("allowtest").checked) p.allow_test = "1";
  const m = await getJ("/api/multisession", p);
  if (m.error) { $("multiMsg").innerHTML = `<span class="bad">${m.error}</span>`; return; }
  $("multiMsg").textContent = `${m.sessions} sesiones · ${fmt(m.bars.length)} barras${m.missing_days.length ? ` · sin barras: ${m.missing_days.join(", ")}` : ""}`;
  if (!m.bars.length) return;
  const daily = m.res === "D";
  const B = m.bars.map((b, i) => ({...b, x: daily ? i : i}));          // eje de índice: sin huecos de noches y festivos
  const [ctx, W, H] = prep($("cMulti")), pad = {l: 56, r: 10, t: 10, b: 22}, vh = 70;
  const lo = Math.min(...B.map(b => b.l)), hi = Math.max(...B.map(b => b.h));
  const X = i => pad.l + (W - pad.l - pad.r) * (i + .5) / B.length, Y = v => pad.t + (H - pad.t - pad.b - vh) * (hi - v) / Math.max(1e-9, hi - lo);
  const lab = i => { const b = B[Math.min(B.length - 1, Math.max(0, Math.round(i)))]; return daily ? b.day.slice(5) : nyDay(b.t) + " " + nyTime(b.t).slice(0, 5); };
  axes(ctx, W, H - vh, pad, 0, B.length - 1, lo, hi, lab);
  const vmax = Math.max(...B.map(b => b.v + (b.v_ext || 0))), bw = Math.max(1, (W - pad.l - pad.r) / B.length - 1);
  let prevDay = null;
  B.forEach((b, i) => {
    if (!daily && b.day !== prevDay && prevDay) { ctx.strokeStyle = css("--line"); ctx.beginPath(); ctx.moveTo(X(i) - bw / 2, pad.t); ctx.lineTo(X(i) - bw / 2, H - pad.b); ctx.stroke(); }
    prevDay = b.day;
    const ext = !daily && b.seg !== "regular", up = b.c >= b.o, col = ext ? "#8a94a0" : up ? "#2e8b57" : "#c0392b";
    ctx.strokeStyle = col; ctx.beginPath(); ctx.moveTo(X(i), Y(b.h)); ctx.lineTo(X(i), Y(b.l)); ctx.stroke();
    ctx.fillStyle = col; ctx.fillRect(X(i) - bw / 2, Math.min(Y(b.o), Y(b.c)), bw, Math.max(1, Math.abs(Y(b.o) - Y(b.c))));
    const vv = (b.v + (b.v_ext || 0)) / vmax * (vh - 8);
    ctx.globalAlpha = .5; ctx.fillRect(X(i) - bw / 2, H - pad.b - vv, bw, vv); ctx.globalAlpha = 1;
  });
  ctx.fillStyle = css("--muted"); ctx.fillText(daily ? "barras diarias de la sesión regular; volumen con horario extendido" : "gris = pre/after hours; abajo, volumen", pad.l, H - pad.b - vh + 12);
};

// ── 5. desglose ──
$("bEps").onclick = async () => {
  const p = q(); const e = await getJ("/api/events", {day: p.day, catalog: "cat-v1"});
  const eps = (e.episodes || []).filter(x => x.symbol === p.symbol);
  $("eps").innerHTML = eps.length ? `<table><tr><th>Episodio</th><th>Códigos</th><th>Inicio</th><th>Fin</th><th>Estado</th><th></th></tr>` +
    eps.map(x => `<tr><td>${x.episode_id}</td><td>${[].concat(x.codes).join(", ")}</td><td>${nyTime(Date.parse(x.t_start_utc))}</td><td>${nyTime(Date.parse(x.t_end_utc))}</td><td>${x.status}</td><td><button class="sec" data-ep="${x.episode_id}">Desglosar</button></td></tr>`).join("") + "</table>"
    : `<span class="note">sin episodios cat-v1 de ${p.symbol} ese día: puedes desglosar la ventana manual igualmente</span>`;
  document.querySelectorAll("[data-ep]").forEach(b => b.onclick = () => runDd({catalog: "cat-v1", day: p.day, episode_id: b.dataset.ep}));
};
$("bDdWin").onclick = () => { const p = q(); runDd({catalog: "cat-v1", day: p.day, symbol: p.symbol, start: p.start, end: p.end, quotes: $("quotes").checked ? "yes" : "no"}); };
async function runDd(body) {
  if ($("allowtest").checked) body.allow_test = true;
  const r = await postJ("/api/drilldown", body);
  if (!r.job) { $("ddMsg").textContent = JSON.stringify(r).slice(0, 300); return; }
  const j = await pollJob(r.job, $("ddMsg"));
  if (!j || j.status !== "done") { $("ddMsg").textContent = `${j ? j.status : "?"} ${j && j.error || ""}`; return; }
  const d = await getJ("/api/drilldown/result", {key: j.key});
  const S = d.segments.segments;
  $("dd").textContent = `Desglose ${j.key} (${d.window_ny} NY, catálogo ${d.catalog_version}): ${fmt(d.trades_loaded)} trades, ${fmt(d.quotes_loaded)} quotes, ${j.fetch.requests} peticiones nuevas.\n` +
    Object.entries(S).filter(([, v]) => v.prints).map(([k, v]) => `  ${k}: ${fmt(v.shares)} acciones en ${fmt(v.prints)} impresiones`).join("\n") +
    `\nComunicaciones tardías: ${fmt(d.late_reports.shares)} acciones · revisiones de alertas: ${d.rechecks.length} · estados actualizados: ${j.statuses_updated}`;
}
const u = new URLSearchParams(location.search);
for (const k of ["sym", "day", "start", "end"]) { const v = u.get(k === "sym" ? "symbol" : k); if (v) $(k).value = v; }
loadCases();
