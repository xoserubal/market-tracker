/* Laboratorio de microestructura — dibujo del footprint (el cálculo lo hace el servidor, aquí solo se representa). */
'use strict';

// ── funciones puras de maquetación (probadas en tests/test_lab_layout.js) ──
const Layout = {
  fmtVol(v) {
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + 'M';
    if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + 'K';
    return String(Math.round(v));
  },
  // Escala vertical: el nivel L ocupa [y(L+paso), y(L)) — los precios altos arriba.
  priceToY(p, view) { return view.top + (view.pMax - p) / view.step * view.rowH - view.offY; },
  barX(i, view) { return view.left + i * view.barW - view.offX; },
  // Intensidad del color de una celda según |delta| relativo al máximo visible (raíz para no saturar).
  cellAlpha(delta, maxAbs) { return maxAbs > 0 ? Math.min(0.85, 0.08 + 0.77 * Math.sqrt(Math.abs(delta) / maxAbs)) : 0; },
  detailLevel(barW, rowH) { return barW >= 78 && rowH >= 12 ? 'text' : 'heat'; },
  // Rango de precios de los niveles (de la vela o de todo el conjunto).
  priceRange(levels, step) {
    let lo = Infinity, hi = -Infinity;
    for (const l of levels) { if (l.p < lo) lo = l.p; if (l.p > hi) hi = l.p; }
    return { lo, hi: hi + step };
  },
  nyTime(ms) { return new Date(ms).toLocaleTimeString('en-GB', { timeZone: 'America/New_York', hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit' }); },
};
if (typeof module !== 'undefined' && module.exports) { module.exports = Layout; }

if (typeof document !== 'undefined') (function () {
  const $ = (id) => document.getElementById(id);
  let DATA = null, LABELS = {}, SEL = null, PIN = { A: null, B: null };
  const view = { left: 64, top: 10, barW: 120, rowH: 16, offX: 0, offY: 0, step: 0.1, pMax: 0, pMin: 0 };

  function params(extra = {}) {
    const p = {
      symbol: $('symbol').value.trim().toUpperCase(), day: $('day').value, start: $('start').value, end: $('end').value,
      tf: $('tf').value, session: $('session').value, method: $('method').value, step: $('step').value || 'auto',
      exclude_trf: $('exclude_trf').checked ? '1' : '0', exclude_odd: $('exclude_odd').checked ? '1' : '0',
      exclude_nonbar: $('exclude_nonbar').checked ? '1' : '0', quote_lag_ms: $('quote_lag_ms').value || '0',
      strict: $('strict').checked ? '1' : '0', ref_exclude_trf: $('ref_exclude_trf').checked ? '1' : '0',
      ref_exclude_nonbar: $('ref_exclude_nonbar').checked ? '1' : '0',
      blind: $('blind').checked ? '1' : '0', cursor: $('cursor').value, ...extra,
    };
    return p;
  }
  const qs = (o) => Object.entries(o).filter(([, v]) => v !== '' && v != null).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  async function get(path, o) { const r = await fetch(path + (o ? '?' + qs(o) : '')); return r.json(); }
  async function post(path, body) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return r.json();
  }

  async function load() {
    $('load').disabled = true;
    try {
      const d = await get('/api/footprint', params());
      if (d.error) {
        DATA = null; draw();
        $('fetchbox').classList.toggle('hidden', !d.need_fetch);
        $('quality').innerHTML = `<span class="badge bad">${d.error}</span>`;
        return;
      }
      $('fetchbox').classList.add('hidden');
      DATA = d; SEL = null;
      const r = Layout.priceRange(d.levels, d.step);
      view.step = d.step; view.pMax = r.hi; view.pMin = r.lo; view.offX = 0; view.offY = 0;
      const plotH = $('fp').height - 30;
      view.rowH = Math.max(6, Math.min(22, plotH / Math.max(1, (r.hi - r.lo) / d.step)));
      const plotW = $('fp').width - view.left - 130;
      view.barW = Math.max(14, Math.min(160, plotW / Math.max(1, d.bars.length)));
      renderMeta(); draw(); renderMethods(); renderCompare(); loadLibrary();
    } finally { $('load').disabled = false; }
  }

  function renderMeta() {
    const q = DATA.quality, b = [];
    const badge = (t, cls = '') => `<span class="badge ${cls}">${t}</span>`;
    b.push(badge(`método: ${$('method').selectedOptions[0].text}`));
    b.push(badge(`paso: $${DATA.step}`));
    b.push(badge(`clasificado ${(q.classified_share * 100).toFixed(1)}%`, q.classified_share < 0.6 ? 'bad' : 'ok'));
    b.push(badge(`subasta ${(q.auction_share * 100).toFixed(1)}%`));
    b.push(badge(`sin clasificar ${(q.unclassified_share * 100).toFixed(1)}%`));
    b.push(badge(`TRF ${(q.trf_share * 100).toFixed(1)}%`));
    b.push(badge(`odd lots ${(q.odd_lot_share * 100).toFixed(1)}%`));
    b.push(badge(`con quote válida ${(q.quote_coverage_share * 100).toFixed(1)}%`, q.quote_coverage_share < 0.9 ? 'bad' : 'ok'));
    b.push(badge(`quotes cargadas: ${DATA.n_quotes_loaded.toLocaleString('es-ES')}`));
    if (DATA.blind) b.push(badge(`modo ciego: datos hasta ${DATA.max_t_returned ? Layout.nyTime(Date.parse(DATA.max_t_returned)) : '—'} NY`, 'bad'));
    $('quality').innerHTML = b.join('');
    $('banner').innerHTML = DATA.in_test_period
      ? '<div class="warn">Fecha dentro del periodo de prueba (o su embargo): este acceso queda registrado. Si ves lo que pasó después o marcas un patrón, las observaciones de este valor alrededor de esta fecha se excluirán del contraste confirmatorio (G2_CAMBIOS.md §3).</div>' : '';
    $('limits').innerHTML = DATA.limitations.map((l) => `<li>${l}</li>`).join('');
  }

  function renderMethods() {
    const m = DATA.methods_summary;
    if (!m || !m.methods) { $('methods').textContent = '—'; return; }
    const pct = (x) => x == null ? '—' : (x * 100).toFixed(1) + '%';
    let h = '<table><tr><th>Método</th><th>Compra</th><th>Venta</th><th>Indet.</th></tr>';
    for (const [k, v] of Object.entries(m.methods)) h += `<tr><td>${k}</td><td class="buy">${pct(v.buy_share)}</td><td class="sell">${pct(v.sell_share)}</td><td>${pct(v.undetermined_share)}</td></tr>`;
    h += '</table><table><tr><th>Pareja</th><th>Ambos clasifican</th><th>Coinciden (si ambos)</th></tr>';
    for (const [k, v] of Object.entries(m.agreement)) h += `<tr><td>${k}</td><td>${pct(v.both_classified_share)}</td><td>${pct(v.agreement_when_both)}</td></tr>`;
    h += '</table><table><tr><th>Mercado</th><th>% volumen</th><th>LR indet.</th><th>En punto medio</th><th>tick~LR</th></tr>';
    for (const [k, v] of Object.entries(m.by_venue)) h += `<tr><td>${k === 'trf' ? 'fuera de mercado (TRF)' : 'bolsas'}</td><td>${pct(v.volume_share)}</td><td>${pct(v.lr_undetermined_share)}</td><td>${pct(v.at_mid_share)}</td><td>${pct(v.tick_lr_agreement)}</td></tr>`;
    h += '</table><p class="small">Volumen por posición en el diferencial: ' +
      Object.entries(m.volume_by_spread_zone).map(([k, v]) => `${k} ${pct(v)}`).join(' · ') + '</p>';
    $('methods').innerHTML = h;
  }

  function renderCompare() {
    const rows = DATA.method_compare || [];
    if (!rows.length) { $('mcompare').textContent = '—'; return; }
    const ms = Object.keys(rows[0].methods);
    const pct = (x) => x == null ? '—' : (x * 100).toFixed(0) + '%';
    const sgn = (s) => s > 0 ? '▲' : s < 0 ? '▼' : '≈0';
    let h = '<table><tr><th>Vela (NY)</th><th>Volumen</th>' + ms.map((m) => `<th>${m}: delta</th><th>indet.</th>`).join('') + '<th></th></tr>';
    let nd = 0;
    for (const r of rows) {
      if (r.sign_disagreement) nd++;
      h += `<tr${r.sign_disagreement ? ' class="disagree"' : ''}><td>${Layout.nyTime(r.t)}</td><td>${Layout.fmtVol(r.vol)}</td>` +
        ms.map((m) => { const v = r.methods[m]; return `<td class="${v.delta > 0 ? 'buy' : v.delta < 0 ? 'sell' : ''}">${sgn(v.sign)} ${Layout.fmtVol(v.delta)}</td><td>${pct(v.undetermined_share)}</td>`; }).join('') +
        `<td>${r.sign_disagreement ? 'signo distinto' : ''}</td></tr>`;
    }
    h += '</table>';
    $('mcompare').innerHTML = `<p class="small">${nd} de ${rows.length} velas con signo distinto según el método.</p>` + h;
  }

  // ── dibujo ──
  function draw() {
    const cv = $('fp'), ctx = cv.getContext('2d');
    cv.width = cv.clientWidth; ctx.clearRect(0, 0, cv.width, cv.height);
    const dc = $('delta'); dc.width = dc.clientWidth; const dx = dc.getContext('2d'); dx.clearRect(0, 0, dc.width, dc.height);
    if (!DATA || DATA.empty) { ctx.fillStyle = '#6b7385'; ctx.fillText(DATA && DATA.empty ? 'Sin operaciones en la ventana' : 'Sin datos', 20, 30); return; }
    const plotR = cv.width - 130, H = cv.height - 22;
    const byBar = new Map();
    for (const l of DATA.levels) { if (!byBar.has(l.t)) byBar.set(l.t, []); byBar.get(l.t).push(l); }
    let maxAbs = 0; for (const l of DATA.levels) maxAbs = Math.max(maxAbs, Math.abs(l.delta));
    const mode = Layout.detailLevel(view.barW, view.rowH);
    let maxVol = 0; for (const l of DATA.levels) maxVol = Math.max(maxVol, l.vol);
    ctx.save(); ctx.beginPath(); ctx.rect(view.left, 0, plotR - view.left, H); ctx.clip();
    DATA.bars.forEach((b, i) => {
      const x = Layout.barX(i, view); if (x > plotR || x + view.barW < view.left) return;
      const cellX = x + 10, cellW = view.barW - 14;
      for (const l of byBar.get(b.t) || []) {
        const y0 = Layout.priceToY(l.p + view.step, view), h = view.rowH;
        if (y0 > H || y0 + h < 0) continue;
        if (mode === 'text') {
          const a = Layout.cellAlpha(l.delta, maxAbs);
          ctx.fillStyle = l.delta >= 0 ? `rgba(27,138,75,${a})` : `rgba(192,57,43,${a})`;
        } else {
          const a = Math.min(0.9, 0.1 + 0.8 * Math.sqrt(l.vol / maxVol));
          ctx.fillStyle = l.delta >= 0 ? `rgba(27,138,75,${a})` : `rgba(192,57,43,${a})`;
        }
        ctx.fillRect(cellX, y0, cellW, h - 1);
        if (l.auction > 0) { ctx.fillStyle = '#7b4fbf'; ctx.fillRect(cellX, y0, 3, h - 1); }
        if (b.poc != null && Math.abs(b.poc - l.p) < 1e-9) { ctx.strokeStyle = '#e0a800'; ctx.lineWidth = 2; ctx.strokeRect(cellX + 1, y0 + 1, cellW - 2, h - 3); }
        if (mode === 'text') {
          ctx.font = `${Math.min(12, h - 3)}px ui-monospace, Consolas, monospace`; ctx.textBaseline = 'middle';
          ctx.textAlign = 'right'; ctx.fillStyle = l.imb_sell ? '#8e1b10' : '#333'; ctx.font = (l.imb_sell ? 'bold ' : '') + ctx.font.replace('bold ', '');
          ctx.fillText(Layout.fmtVol(l.sell), cellX + cellW / 2 - 4, y0 + h / 2);
          ctx.textAlign = 'left'; ctx.fillStyle = l.imb_buy ? '#0d5a2e' : '#333'; ctx.font = (l.imb_buy ? 'bold ' : '') + ctx.font.replace('bold ', '');
          ctx.fillText(Layout.fmtVol(l.buy), cellX + cellW / 2 + 4, y0 + h / 2);
          ctx.fillStyle = '#9aa2b1'; ctx.textAlign = 'center'; ctx.fillText('×', cellX + cellW / 2, y0 + h / 2);
        }
      }
      // vela
      if (b.open != null) {
        const yo = Layout.priceToY(b.open, view), yc = Layout.priceToY(b.close, view);
        const yh = Layout.priceToY(b.high, view), yl = Layout.priceToY(b.low, view);
        ctx.strokeStyle = '#333'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x + 5, yh); ctx.lineTo(x + 5, yl); ctx.stroke();
        ctx.fillStyle = b.close >= b.open ? '#1b8a4b' : '#c0392b';
        ctx.fillRect(x + 2, Math.min(yo, yc), 6, Math.max(1, Math.abs(yc - yo)));
      }
      if (SEL === i) { ctx.strokeStyle = '#1f5fa8'; ctx.lineWidth = 2; ctx.strokeRect(x + 1, 1, view.barW - 2, H - 2); }
    });
    ctx.restore();
    // eje de precios
    ctx.fillStyle = '#6b7385'; ctx.font = '11px system-ui'; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    const every = Math.max(1, Math.ceil(16 / view.rowH));
    for (let k = 0, p = view.pMin; p <= view.pMax + 1e-9; k++, p = view.pMin + k * view.step) {
      if (k % every) continue; const y = Layout.priceToY(p + view.step / 2, view); if (y < 0 || y > H) continue;
      ctx.fillText(p.toFixed(view.step < 0.1 ? 2 : view.step < 1 ? 2 : 0), view.left - 6, y);
    }
    // eje temporal
    ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    DATA.bars.forEach((b, i) => { const x = Layout.barX(i, view); if (x >= view.left && x + view.barW <= plotR && (view.barW > 50 || i % Math.ceil(50 / view.barW) === 0)) ctx.fillText(Layout.nyTime(b.t).slice(0, 5), x + view.barW / 2, cv.height - 6); });
    // perfil de volumen
    const pmax = Math.max(...DATA.profile.map((r) => r.vol));
    for (const r of DATA.profile) {
      const y = Layout.priceToY(r.p + view.step, view); if (y > H || y + view.rowH < 0) continue;
      const w = 115 * r.vol / pmax, wb = 115 * r.buy / pmax;
      ctx.fillStyle = 'rgba(192,57,43,0.55)'; ctx.fillRect(plotR + 8, y, w, view.rowH - 1);
      ctx.fillStyle = 'rgba(27,138,75,0.75)'; ctx.fillRect(plotR + 8, y, wb, view.rowH - 1);
      const va = DATA.value_area || {};
      if (r.p >= va.val - 1e-9 && r.p <= va.vah + 1e-9) { ctx.fillStyle = '#1f5fa8'; ctx.fillRect(plotR + 4, y, 2, view.rowH - 1); }
      if (Math.abs(r.p - va.poc) < 1e-9) { ctx.strokeStyle = '#e0a800'; ctx.strokeRect(plotR + 8, y, w, view.rowH - 1); }
    }
    drawDelta(dc, dx, plotR);
  }

  function drawDelta(dc, dx, plotR) {
    const H = dc.height, mid = H * 0.42;
    let maxD = 1; for (const b of DATA.bars) maxD = Math.max(maxD, Math.abs(b.delta));
    dx.fillStyle = '#6b7385'; dx.font = '11px system-ui'; dx.fillText('delta por vela (barras) · delta acumulado de 1 min (línea)', view.left, 12);
    dx.strokeStyle = '#dfe3ea'; dx.beginPath(); dx.moveTo(view.left, mid); dx.lineTo(plotR, mid); dx.stroke();
    DATA.bars.forEach((b, i) => {
      const x = Layout.barX(i, view); if (x > plotR || x + view.barW < view.left) return;
      const h = (mid - 18) * b.delta / maxD; dx.fillStyle = b.delta >= 0 ? '#1b8a4b' : '#c0392b';
      dx.fillRect(x + 10, b.delta >= 0 ? mid - h : mid, view.barW - 14, Math.abs(h));
    });
    const tl = DATA.timeline; if (!tl || !tl.length || !DATA.bars.length) return;
    const t0 = DATA.bars[0].t, tfms = DATA.tf_minutes * 60000;
    let lo = Infinity, hi = -Infinity; for (const r of tl) { lo = Math.min(lo, r.cum_delta); hi = Math.max(hi, r.cum_delta); }
    const y = (v) => H - 6 - (H * 0.5 - 10) * (v - lo) / Math.max(1, hi - lo);
    dx.strokeStyle = '#1f5fa8'; dx.lineWidth = 1.5; dx.beginPath();
    tl.forEach((r, k) => { const x = view.left + ((r.t - t0) / tfms) * view.barW - view.offX + 10; if (k === 0) dx.moveTo(x, y(r.cum_delta)); else dx.lineTo(x, y(r.cum_delta)); });
    dx.stroke();
    dx.fillStyle = '#1f5fa8'; dx.fillText(`acum. ${Layout.fmtVol(tl[tl.length - 1].cum_delta)}`, plotR - 70, H - 6);
  }

  function barTable(i) {
    const b = DATA.bars[i]; const ls = DATA.levels.filter((l) => l.t === b.t).sort((a, c) => c.p - a.p);
    const pct = (x) => (100 * x / Math.max(1, b.vol)).toFixed(1) + '%';
    let h = `<p><b>${Layout.nyTime(b.t).slice(0, 5)} NY</b> · O ${b.open} H ${b.high} L ${b.low} C ${b.close}<br>` +
      `vol ${Layout.fmtVol(b.vol)} · compra <span class="buy">${Layout.fmtVol(b.buy)}</span> · venta <span class="sell">${Layout.fmtVol(b.sell)}</span> · delta ${Layout.fmtVol(b.delta)}<br>` +
      `subasta ${pct(b.auction)} · sin clasificar ${pct(b.unclassified)} · TRF ${pct(b.trf)} · quote válida ${pct(b.quote_ok)} · POC ${b.poc}</p>`;
    h += '<table><tr><th>Precio</th><th>Venta</th><th>Compra</th><th>Delta</th><th>Total</th><th>Sub.</th><th>Indet.</th></tr>';
    for (const l of ls) h += `<tr><td>${l.p.toFixed(2)}</td><td class="sell">${Layout.fmtVol(l.sell)}${l.imb_sell ? ' ◆' : ''}</td><td class="buy">${Layout.fmtVol(l.buy)}${l.imb_buy ? ' ◆' : ''}</td><td>${Layout.fmtVol(l.delta)}</td><td>${Layout.fmtVol(l.vol)}</td><td>${Layout.fmtVol(l.auction)}</td><td>${Layout.fmtVol(l.unclassified)}</td></tr>`;
    return h + '</table><p class="small">◆ desequilibrio diagonal ≥ 3:1 (compra en p frente a venta en p − paso, y viceversa)</p>';
  }

  // ── interacción ──
  const cv = $('fp'); let drag = null;
  cv.addEventListener('wheel', (e) => {
    if (!DATA) return; e.preventDefault();
    const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    if (e.shiftKey) view.barW = Math.max(8, Math.min(400, view.barW * f)); else view.rowH = Math.max(3, Math.min(60, view.rowH * f));
    draw();
  }, { passive: false });
  cv.addEventListener('mousedown', (e) => { drag = { x: e.clientX, y: e.clientY, ox: view.offX, oy: view.offY, moved: false }; });
  window.addEventListener('mousemove', (e) => {
    if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    view.offX = drag.ox - dx; view.offY = drag.oy - dy; draw();
  });
  window.addEventListener('mouseup', (e) => {
    if (drag && !drag.moved && DATA) {
      const r = cv.getBoundingClientRect(); const x = (e.clientX - r.left) * (cv.width / r.width);
      const i = Math.floor((x - view.left + view.offX) / view.barW);
      if (i >= 0 && i < DATA.bars.length) { SEL = i; $('detail').innerHTML = barTable(i); draw(); prefillEpisode(i); }
    }
    drag = null;
  });
  function pin(which) {
    if (SEL == null) return; PIN[which] = { html: barTable(SEL), bar: DATA.bars[SEL], sym: DATA.symbol, day: DATA.day };
    const s = (p) => p ? `<div><b>${which === 'A' ? '' : ''}${p.sym} ${p.day}</b>${p.html}</div>` : '—';
    const c = (a, b) => (a && b) ? `<p>Δ delta B−A: ${Layout.fmtVol(b.bar.delta - a.bar.delta)} · Δ vol: ${Layout.fmtVol(b.bar.vol - a.bar.vol)}</p>` : '';
    $('compare').innerHTML = `<h4>A</h4>${s(PIN.A)}<h4>B</h4>${s(PIN.B)}${c(PIN.A, PIN.B)}`;
  }
  $('pinA').onclick = () => pin('A'); $('pinB').onclick = () => pin('B');

  function shiftCursor(sign) {
    if (!$('blind').checked) $('blind').checked = true;
    const tf = +$('tf').value; let c = $('cursor').value || $('start').value;
    const [h, m, s = '0'] = c.split(':').map(Number);
    let mins = h * 60 + m + sign * tf; if (mins < 0) mins = 0;
    $('cursor').value = `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    load();
  }
  $('back').onclick = () => shiftCursor(-1); $('fwd').onclick = () => shiftCursor(1);
  $('load').onclick = load;
  window.addEventListener('resize', draw);

  // ── descarga ──
  $('estimate').onclick = async () => {
    const d = await get('/api/estimate', { symbol: $('symbol').value, day: $('day').value, quote_ranges: $('qranges').value });
    $('fetchinfo').textContent = JSON.stringify(d, null, 1);
  };
  $('fetch').onclick = async () => {
    const ranges = $('qranges').value.split(',').map((s) => s.trim()).filter(Boolean);
    let d = await post('/api/fetch', { symbol: $('symbol').value, day: $('day').value, quote_ranges: ranges });
    if (d.error && d.pages_est && confirm(`Descarga grande (~${d.pages_est} páginas). ¿Continuar?`)) {
      d = await post('/api/fetch', { symbol: $('symbol').value, day: $('day').value, quote_ranges: ranges, confirm_large: true });
    }
    $('fetchinfo').textContent = JSON.stringify(d, null, 1);
    if (d.job) poll(d.job);
  };
  async function poll(job) {
    const j = (await get('/api/jobs')).jobs[job];
    $('fetchinfo').textContent = JSON.stringify(j, null, 1);
    if (j.status === 'done') load(); else if (j.status !== 'failed') setTimeout(() => poll(job), 3000);
  }

  // ── biblioteca ──
  function prefillEpisode(i) {
    const b = DATA.bars[i]; const t = Layout.nyTime(b.t).slice(0, 5); const t2 = Layout.nyTime(b.t + DATA.tf_minutes * 60000).slice(0, 5);
    $('ep_start').value = t; $('ep_end').value = t2; $('ep_lo').value = b.low; $('ep_hi').value = b.high;
  }
  $('ep_save').onclick = async () => {
    const p = params();
    const d = await post('/api/library/episode', {
      symbol: p.symbol, day: p.day, start: $('ep_start').value, end: $('ep_end').value,
      price_lo: parseFloat($('ep_lo').value) || null, price_hi: parseFloat($('ep_hi').value) || null,
      proposed_label: $('ep_label').value, selection_note: $('ep_note').value, outcome_known_at_selection: $('ep_known').checked,
      view: { tf: p.tf, method: p.method, step: p.step, quote_lag_ms: p.quote_lag_ms, strict: p.strict, ref_exclude_trf: p.ref_exclude_trf, ref_exclude_nonbar: p.ref_exclude_nonbar },
    });
    alert(d.error ? 'Error: ' + d.error : 'Episodio guardado: ' + d.episode_id); loadLibrary();
  };
  $('an_save').onclick = async () => {
    const p = params();
    const d = await post('/api/library/annotate', {
      episode_id: $('an_ep').value, label: $('an_label').value, confidence: parseFloat($('an_conf').value),
      justification: $('an_just').value, ambiguous: $('an_amb').checked, annotator_type: 'human', annotator_id: 'usuario',
      cursor_utc: (p.blind === '1' && DATA && DATA.cursor) ? DATA.cursor : null,
    });
    alert(d.error ? 'Error: ' + d.error : 'Anotación guardada'); loadLibrary();
  };
  async function loadLibrary() {
    const p = params();
    const eps = (await get('/api/library/episodes', { symbol: p.symbol, day: p.day })).episodes || [];
    $('an_ep').innerHTML = eps.map((e) => `<option value="${e.episode_id}">${e.episode_id}</option>`).join('');
    let h = eps.length ? '' : '<p class="muted">Sin episodios guardados.</p>';
    for (const e of eps) {
      const ans = (await get('/api/library/annotations', { episode_id: e.episode_id })).annotations || [];
      h += `<div><b>${e.episode_id}</b> ${e.start_utc.slice(11, 16)}–${e.end_utc.slice(11, 16)} UTC · ${LABELS[e.proposed_label] || 'sin propuesta'}` +
        `${e.outcome_known_at_selection ? '<span class="tag retro">resultado conocido al elegirlo</span>' : ''}${e.in_test_period ? '<span class="tag test">periodo de prueba</span>' : ''}` +
        `<div class="small">${e.selection_note || ''}</div><ul>` +
        ans.map((a) => `<li>${LABELS[a.label]} (${a.confidence ?? '—'})<span class="tag ${a.annotator_type === 'human' ? '' : 'ai'}">${a.annotator_type === 'human' ? 'humana' : a.annotator_type + ': ' + a.annotator_id}</span>` +
          `${a.revealed_future ? '<span class="tag retro">retrospectiva</span>' : ''}${a.ambiguous ? '<span class="tag">ambigua</span>' : ''} — ${a.justification}</li>`).join('') + '</ul></div>';
    }
    $('library').innerHTML = h;
  }
  (async () => {
    LABELS = (await get('/api/labels')).labels;
    const opts = Object.entries(LABELS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
    $('ep_label').innerHTML = '<option value="">(sin propuesta)</option>' + opts; $('an_label').innerHTML = opts;
    draw();
  })();
})();
