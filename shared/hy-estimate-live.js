// Estimación del HY spread con precios del día (2026-11-23).
//
// scripts/hy_spread_estimate.py (pipeline, 1×/día) deja en
// docs/data/hy_spread_estimate_latest.json el último dato oficial de FRED, las
// estimaciones de las sesiones ya cerradas y los coeficientes del modelo. Aquí
// se continúa esa misma cuenta con las cotizaciones actuales de Yahoo, para que
// al pulsar "actualizar" con el mercado abierto la estimación se mueva.
// Es una ESTIMACIÓN: nunca sustituye al dato de FRED ni alimenta nada automático.
//
// Modelo (mismo que el script de Python, ver allí la calibración):
//   ΔOAS = const + b·HJ + c·IEI + d·HJ(t−1) + e·IEI(t−1)
//   HJ = media de los retornos log (%) de HYG y JNK; IEI = retorno log (%) de IEI.
// Retornos con el cierre sin ajustar de Yahoo, sumando el dividendo el día en que
// la acción cotiza sin él (si no, el pago mensual de HYG/JNK parecería una caída
// de ~0,5 % y la estimación subiría ~10 pb sin motivo).

const TICKERS = ["HYG", "JNK", "IEI"];
const BAND_Z = 1.2816; // banda del 80 %

function nyDate(tsSec, gmtoffset) {
  return new Date((tsSec + (gmtoffset || 0)) * 1000).toISOString().slice(0, 10);
}

// Barras diarias {date, close, div} (+ meta) de un ticker.
async function fetchBars(fetchRaw, symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=1mo&events=div&includePrePost=false`;
  const r = await fetchRaw(url);
  const res = r?.chart?.result?.[0];
  if (!res) throw new Error(`Sin datos de Yahoo para ${symbol}`);
  const off = res.meta?.gmtoffset ?? 0;
  const divByDate = {};
  for (const d of Object.values(res.events?.dividends || {})) divByDate[nyDate(d.date, off)] = (divByDate[nyDate(d.date, off)] || 0) + d.amount;
  const closes = res.indicators?.quote?.[0]?.close || [];
  const bars = [];
  (res.timestamp || []).forEach((t, i) => {
    if (closes[i] == null) return;
    const date = nyDate(t, off);
    if (bars.length && bars[bars.length - 1].date === date) bars[bars.length - 1].close = closes[i];
    else bars.push({ date, close: closes[i], div: divByDate[date] || 0 });
  });
  return { bars, meta: res.meta || {} };
}

// latest = contenido de hy_spread_estimate_latest.json; data = {HYG:{bars,meta},...}
function computeFromBars(latest, data, nowMs = Date.now()) {
  const ref = latest.live_reference, coef = latest.model.coef, sigma = latest.model.resid_sigma_bp;
  const official = latest.official;
  const lastPipelineEst = (latest.estimates || []).slice(-1)[0] || null;
  const base = {
    official, label: "ESTIMACIÓN — no es el dato oficial de FRED", model: latest.model.id,
    pipeline_generated_at_utc: latest.generated_at_utc,
  };

  // Retornos por fecha posterior a ref_date, comunes a los 3 tickers.
  const retsByTicker = {};
  for (const t of TICKERS) {
    const bars = data[t].bars;
    const i0 = bars.findIndex(b => b.date === ref.ref_date);
    if (i0 < 0) return { ...base, status: "stale_reference", note: `La referencia ${ref.ref_date} ya no está en el último mes de Yahoo: falta que corra el pipeline.` };
    const m = {};
    for (let i = i0 + 1; i < bars.length; i++) m[bars[i].date] = Math.log((bars[i].close + bars[i].div) / bars[i - 1].close) * 100;
    retsByTicker[t] = m;
  }
  const dates = Object.keys(retsByTicker.HYG).filter(d => d in retsByTicker.JNK && d in retsByTicker.IEI).sort();

  if (!dates.length) {
    // Sin sesiones nuevas: lo último es lo que calculó el pipeline (o el oficial).
    const src = lastPipelineEst && lastPipelineEst.date > official.date ? lastPipelineEst : null;
    return {
      ...base, status: src ? "pipeline" : "official_only",
      date: src ? src.date : official.date,
      est_bp: src ? src.est_bp : official.value_bp,
      low_bp: src ? src.low_bp : null, high_bp: src ? src.high_bp : null,
      bridge_days: src ? src.bridge_days : 0, session_open: false,
    };
  }

  let level = ref.ref_level_bp, lagHJ = ref.ret_ref_day.HJ, lagIEI = ref.ret_ref_day.IEI;
  let bridge = ref.ref_bridge_days;
  const path = [];
  for (const d of dates) {
    const HJ = (retsByTicker.HYG[d] + retsByTicker.JNK[d]) / 2, IEI = retsByTicker.IEI[d];
    level += coef.const + coef.HJ * HJ + coef.IEI * IEI + coef.HJ_l1 * lagHJ + coef.IEI_l1 * lagIEI;
    bridge += 1;
    path.push({ date: d, est_bp: +level.toFixed(1) });
    lagHJ = HJ; lagIEI = IEI;
  }
  const half = BAND_Z * sigma * Math.sqrt(bridge);
  const meta = data.HYG.meta;
  const tp = meta.currentTradingPeriod?.regular;
  const nowSec = nowMs / 1000;
  const lastDate = dates[dates.length - 1];
  const sessionOpen = !!(tp && nowSec >= tp.start && nowSec < tp.end && lastDate === nyDate(tp.start, meta.gmtoffset));
  return {
    ...base, status: sessionOpen ? "live" : "closed_unofficial",
    date: lastDate, est_bp: +level.toFixed(1),
    low_bp: +(level - half).toFixed(1), high_bp: +(level + half).toFixed(1),
    bridge_days: bridge, session_open: sessionOpen,
    quotes_as_of_utc: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
    path,
  };
}

async function computeLiveHyEstimate(latest, fetchRaw) {
  const data = {};
  for (const t of TICKERS) data[t] = await fetchBars(fetchRaw, t);
  return computeFromBars(latest, data);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { computeLiveHyEstimate, computeFromBars, fetchBars };
}
