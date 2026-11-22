"""Perfiles de volumen de la capa 2 (VP2, aprobado 2026-11-22): estimados con barras de 1 minuto.

Fuente y definición (fijas en PARAMS, con su hash en cada fila):
- `estimated_bars_1m_ex_auction`: barras de 1 minuto de la sesión regular [apertura, cierre). Excluye la subasta de
  cierre (se imprime a las 16:00 y no entra en esos minutos). La subasta de apertura NO se puede separar con barras:
  va dentro de la barra de las 09:30. Los minutos con solo lotes impares no tienen barra en Alpaca y su volumen falta
  (VP2: GL 2026-11-20, −5 %).
- Reparto del volumen de cada barra: triangular centrado en el VWAP de la barra dentro de [mínimo, máximo] (VP1).
- Se guarda un perfil BASE en precio sin ajustar, en una rejilla fina absoluta (paso = máx(tick, 0,025 % del precio de
  referencia del día)). De ahí se derivan, por reparto proporcional al solape de intervalos:
  - la rejilla canónica del día: 0,10 % del precio de referencia, nunca menor que el tick efectivo;
  - la rejilla común de cada comparación entre sesiones (vp_windows), ya en la escala de precios de la ventana.
  Así un cambio de rejilla no crea desplazamientos: la resolución del perfil base es 4 veces más fina que la del 0,10 %.
- Tick efectivo: 0,01 $ con precio ≥ 1 $; 0,0001 $ por debajo (Reg NMS 612).

Estadísticas del día (en la rejilla canónica), descriptivas, sin interpretación:
- POC y área de valor del 70 % (desde el POC se añade el nivel vecino con más volumen).
- Zona del 90 %: niveles con al menos el 90 % del volumen del máximo, agrupados en SEGMENTOS contiguos (no se presenta
  como banda continua si no lo es).
- Planitud: cuota del nivel máximo y de los 3 mayores, entropía normalizada y fracción de niveles para el 50 %.
- Prominencia del POC: 1 − (mayor volumen fuera del segmento del POC y de sus vecinos inmediatos) / máximo.
- Confianza en la localización del POC (heurística de VP1, sin calibrar): alta / media / baja.
- Picos separados: máximos locales ≥ 50 % del máximo con un valle entre ellos ≤ 70 % del pico menor.
"""
import hashlib
import json

import numpy as np

PARAMS = {
    "version": "vp2-1",
    "source": "estimated_bars_1m_ex_auction",
    "session": "regular [open, close); sin subasta de cierre; apertura dentro de la barra de las 09:30",
    "allocation": "triangular centrado en el VWAP de la barra dentro de [low, high]; peso mínimo 0,05; sin VWAP -> cierre",
    "fine_rel": 0.00025, "canonical_rel": 0.001, "tick_ge_1": 0.01, "tick_lt_1": 0.0001,
    "max_levels_per_bar": 2000, "va_share": 0.70, "zone_frac": 0.90,
    "peak_min_frac": 0.50, "peak_valley_frac": 0.70,
    "confidence": {"alta": "un solo segmento de la zona del 90 %, ≤ 2 niveles y prominencia ≥ 0,20",
                   "baja": "≥ 2 segmentos en la zona del 90 %, prominencia < 0,10 o segmento del POC de ≥ 5 niveles "
                           "(perfil plano: el POC no localiza nada)", "media": "el resto"},
}
PARAMS_SHA256 = hashlib.sha256(json.dumps(PARAMS, sort_keys=True).encode()).hexdigest()[:16]


def tick_of(price: float) -> float:
    return PARAMS["tick_ge_1"] if price >= 1 else PARAMS["tick_lt_1"]


def step_for(price: float, rel: float) -> float:
    t = tick_of(price)
    return round(max(t, round(price * rel / t) * t), 6)


# ── perfil base: reparto triangular vectorizado ────────────────────────────────────────────────────────────────
def allocate(l, h, vw, c, v, step: float) -> tuple:
    """(nivel_inicial, volúmenes por nivel, barras_recortadas). Mismo resultado que volume_profile.estimated
    (triangular), vectorizado."""
    l, h, c, v = (np.asarray(x, dtype=float) for x in (l, h, c, v))
    vw = np.asarray(vw, dtype=float)
    vw = np.where(np.isfinite(vw) & (vw > 0), vw, c)
    ok = np.isfinite(l) & np.isfinite(h) & np.isfinite(vw) & (v > 0) & (h >= l) & (l > 0)
    l, h, vw, v = l[ok], h[ok], vw[ok], v[ok]
    if not len(v):
        return 0, np.zeros(0, dtype=np.float64), 0
    lo = np.floor(l / step + 1e-9).astype(np.int64)
    hi = np.floor(h / step + 1e-9).astype(np.int64)
    n = hi - lo + 1
    capped = n > PARAMS["max_levels_per_bar"]
    lo = np.where(capped, np.floor(vw / step + 1e-9).astype(np.int64), lo)
    hi = np.where(capped, lo, hi)
    n = hi - lo + 1
    rep = np.repeat(np.arange(len(v)), n)
    off = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    lv = lo[rep] + off
    cc = (vw / step)[rep]
    half = np.maximum.reduce([cc - lo[rep], hi[rep] + 1 - cc, np.ones(len(rep))])
    w = np.where(n[rep] == 1, 1.0, np.clip(1 - np.abs(lv + 0.5 - cc) / half, 0.05, None))
    tot = np.bincount(rep, weights=w, minlength=len(v))
    vol = w / tot[rep] * v[rep]
    base = int(lv.min())
    prof = np.bincount(lv - base, weights=vol)
    return base, prof, int(capped.sum())


def rebin(lvl0: int, vols: np.ndarray, step: float, factor: float, g: float) -> tuple:
    """Lleva un perfil (niveles [k·step, (k+1)·step)) a precios × factor y a la rejilla de paso g (múltiplos de g),
    repartiendo cada nivel por solape de intervalos (volumen uniforme dentro del nivel). Devuelve (nivel_inicial, vols)."""
    vols = np.asarray(vols, dtype=float)
    k = np.nonzero(vols > 0)[0]
    if not len(k):
        return 0, np.zeros(0)
    a = (lvl0 + k) * step * factor
    b = a + step * factor
    i0 = np.floor(a / g + 1e-9).astype(np.int64)
    i1 = np.floor(b / g - 1e-9).astype(np.int64)
    n = i1 - i0 + 1
    rep = np.repeat(np.arange(len(k)), n)
    off = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    t = i0[rep] + off
    lo_edge = np.maximum(a[rep], t * g)
    hi_edge = np.minimum(b[rep], (t + 1) * g)
    frac = np.clip(hi_edge - lo_edge, 0, None) / (step * factor)
    vol = vols[k][rep] * frac
    base = int(t.min())
    return base, np.bincount(t - base, weights=vol)


# ── estadísticas ───────────────────────────────────────────────────────────────────────────────────────────────
def _segments(mask: np.ndarray) -> list:
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        if not m and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def value_area_idx(v: np.ndarray, share: float = None) -> tuple:
    share = PARAMS["va_share"] if share is None else share
    poc = int(np.argmax(v))
    lo = hi = poc
    tot, acc = v.sum(), v[poc]
    while acc < share * tot:
        up = v[hi + 1] if hi + 1 < len(v) else -1.0
        dn = v[lo - 1] if lo > 0 else -1.0
        if up < 0 and dn < 0:
            break
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    return lo, hi, poc


def peaks(v: np.ndarray) -> list:
    """Máximos locales ≥ peak_min_frac del máximo, separados por un valle ≤ peak_valley_frac del pico menor."""
    mx = v.max()
    cand = [i for i in range(len(v)) if v[i] >= PARAMS["peak_min_frac"] * mx and
            (i == 0 or v[i] >= v[i - 1]) and (i == len(v) - 1 or v[i] >= v[i + 1])]
    cand.sort(key=lambda i: -v[i])
    keep = []
    for i in cand:
        ok = True
        for j in keep:
            a, b = sorted((i, j))
            if v[a:b + 1].min() > PARAMS["peak_valley_frac"] * min(v[i], v[j]):
                ok = False
                break
        if ok:
            keep.append(i)
        if len(keep) >= 5:
            break
    return sorted(keep)


def stats(lvl0: int, v: np.ndarray, g: float) -> dict:
    v = np.asarray(v, dtype=float)
    if not len(v) or v.sum() <= 0:
        return {"ok": False}
    tot = v.sum()
    price = lambda i: round((lvl0 + i + 0.5) * g, 6)  # noqa: E731
    edge = lambda i: round((lvl0 + i) * g, 6)  # noqa: E731
    lo, hi, poc = value_area_idx(v)
    mx = v[poc]
    zone = v >= PARAMS["zone_frac"] * mx
    segs = _segments(zone)
    pseg = next(s for s in segs if s[0] <= poc <= s[1])
    outside = np.ones(len(v), dtype=bool)
    outside[max(0, pseg[0] - 1):pseg[1] + 2] = False
    prom = 1 - (v[outside].max() / mx if outside.any() else 0.0)
    nz = v[v > 0]
    p = nz / tot
    ent = float(-(p * np.log(p)).sum() / np.log(len(p))) if len(p) > 1 else 0.0
    srt = np.sort(nz)[::-1]
    lv50 = int(np.searchsorted(np.cumsum(srt), 0.5 * tot) + 1)
    width = pseg[1] - pseg[0] + 1
    conf = ("baja" if len(segs) >= 2 or prom < 0.10 or width >= 5 else
            "alta" if width <= 2 and prom >= 0.20 else "media")
    pk = peaks(v)
    return {"ok": True, "grid_step": g, "levels": int((v > 0).sum()),
            "poc_price": price(poc), "poc_share": round(float(mx / tot), 5),
            "va_low": edge(lo), "va_high": edge(hi + 1), "va_levels": hi - lo + 1,
            "zone90_segments": json.dumps([[edge(a), edge(b + 1), round(float(v[a:b + 1].sum() / tot), 5)] for a, b in segs]),
            "zone90_n_segments": len(segs), "zone90_poc_segment_levels": width,
            "poc_prominence": round(float(prom), 4), "poc_confidence": conf,
            "top1_share": round(float(mx / tot), 5), "top3_share": round(float(srt[:3].sum() / tot), 5),
            "entropy_norm": round(ent, 4), "levels_for_50pct_frac": round(lv50 / len(nz), 4),
            "peaks": json.dumps([[price(i), round(float(v[i] / mx), 3)] for i in pk]), "n_peaks": len(pk)}
