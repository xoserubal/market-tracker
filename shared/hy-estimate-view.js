// Texto de la estimación del HY spread (/api/hy-estimate) para las páginas.
// Lo usan index.html (tabla macro) y duration.html (tarjeta HY). Siempre
// etiquetado como estimación: nunca se presenta como el dato de FRED.
function hyEstimateSummary(e) {
  if (!e || e.error && e.est_bp == null) return null;
  if (e.status === 'official_only') return null;
  if (e.status === 'stale_reference') return { text: 'Estimación no disponible: ' + (e.note || 'referencia desactualizada'), title: '', delta: null };
  const r = v => Math.round(v);
  const off = e.official || {};
  const delta = (e.est_bp != null && off.value_bp != null) ? e.est_bp - off.value_bp : null;
  const dTxt = delta != null ? ` · ${delta >= 0 ? '+' : ''}${r(delta)} pb vs oficial ${off.date}` : '';
  const band = (e.low_bp != null && e.high_bp != null) ? ` (${r(e.low_bp)}–${r(e.high_bp)})` : '';
  let when;
  if (e.status === 'live') {
    const hhmm = e.quotes_as_of_utc ? new Date(e.quotes_as_of_utc).toLocaleTimeString('es-ES', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit' }) : '';
    when = `en vivo, precios de las ${hhmm} ET`;
  } else {
    when = `cierre del ${e.date}, FRED aún no lo publica`;
  }
  const head = e.status === 'live' ? 'Estimado ahora' : 'Estimado';
  const text = `${head} ≈${r(e.est_bp)} pb${band} · ${when}${dTxt}`;
  const tr = e.tracking, bt = e.backtest_1d;
  const acc = tr && tr.n
    ? `Acierto real hasta hoy: error medio ${tr.mae_bp} pb, sesgo ${tr.bias_bp >= 0 ? '+' : ''}${tr.bias_bp}, ${tr.in_band_pct}% dentro del rango (n=${tr.n}).`
    : (bt ? `Acierto simulado (2 años): error medio ${bt.mae_bp} pb a 1 día, 9 de cada 10 días por debajo de ${bt.p90_abs_bp} pb.` : '');
  const title = 'ESTIMACIÓN, no es el dato de FRED. Parte del último dato oficial y suma el cambio estimado con HYG/JNK (high yield) frente a IEI (Tesoro 3-7 años). Rango = banda del 80 %. No alimenta ninguna lectura ni alerta. ' + acc + (e.status === 'pipeline_fallback' ? ' Sin precios de Yahoo ahora: se muestra el último cálculo del pipeline.' : '');
  return { text, title, delta };
}
if (typeof module !== 'undefined' && module.exports) module.exports = { hyEstimateSummary };
