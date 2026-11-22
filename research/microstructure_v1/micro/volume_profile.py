"""Perfiles de volumen por precio: ESTIMADOS con barras de 1 minuto frente a OBSERVADOS con trades (VP1, 2026-11-21).

Dos fuentes que nunca se mezclan ni se presentan como la misma cosa:
- `estimated_bars_1m`: el volumen de cada barra se reparte entre precios con una regla (no se sabe a qué precio se
  negoció cada acción dentro del minuto). Reglas: cierre, VWAP de la barra, uniforme entre mínimo y máximo, y
  triangular centrada en el VWAP de la barra dentro de [mínimo, máximo].
- `observed_trades`: cada operación a su precio. Elegibles: las que suman volumen según las reglas oficiales de las
  barras (upd_vol) y no están canceladas; las impresiones oficiales (M, Q) no suman. Variantes: sin comunicaciones
  tardías y sin subastas.

Rejilla común: niveles de ancho relativo fijo (p. ej. 0,10 % del precio de referencia del día), anclados en múltiplos
del paso, para que dos perfiles del mismo día se comparen nivel a nivel. Entre días distintos los precios se llevan a
una escala común con el factor de split acumulado (`split_factor`), sin tocar las barras guardadas.

Métricas (todas descriptivas): distancia del POC (en niveles y en puntos básicos), área de valor del 70 %
(solapamiento de Jaccard y desplazamiento del punto medio), distancia de variación total entre perfiles
normalizados, cuota del nivel máximo y de los 3 mayores, y coincidencia de los nodos de volumen alto.
Una concentración de volumen es un hecho sobre dónde se negoció; no se interpreta como acumulación ni distribución.
"""
import numpy as np
import pandas as pd

METHODS = ("close", "vwap", "uniform", "triangular")
VA_SHARE = 0.70


def grid_step(ref_price: float, rel: float) -> float:
    """Paso de la rejilla: `rel` del precio de referencia, redondeado a un múltiplo de 0,01 (mínimo 0,01)."""
    return max(0.01, round(ref_price * rel / 0.01) * 0.01)


def level_index(price, step: float) -> np.ndarray:
    return np.floor(np.asarray(price, dtype=float) / step + 1e-9).astype(np.int64)


# ── observado ──────────────────────────────────────────────────────────────────────────────────────────────────
def observed(tr: pd.DataFrame, step: float, *, exclude_late: bool = False, exclude_auctions: bool = False,
             segments=None) -> pd.Series:
    """Volumen por nivel con trades. `tr` necesita price, size, upd_vol, canceled y, si se filtra, segment."""
    m = tr["upd_vol"].to_numpy() & ~tr["canceled"].to_numpy()
    if segments is not None:
        m &= tr["segment"].isin(segments).to_numpy()
    if exclude_late:
        m &= (tr["segment"] != "late_report").to_numpy()
    if exclude_auctions:
        m &= ~tr["segment"].isin(["open_auction", "close_auction", "halt_reopen"]).to_numpy()
    x = tr[m]
    if x.empty:
        return pd.Series(dtype=float)
    return pd.Series(x["size"].to_numpy(dtype=float)).groupby(level_index(x["price"], step)).sum()


# ── estimado ───────────────────────────────────────────────────────────────────────────────────────────────────
def estimated(bars: pd.DataFrame, step: float, method: str) -> pd.Series:
    """Volumen por nivel con barras (o, h, l, c, v, vw) repartido según `method`."""
    if method not in METHODS:
        raise ValueError(method)
    b = bars[(bars["v"] > 0) & np.isfinite(bars["c"])]
    if b.empty:
        return pd.Series(dtype=float)
    v = b["v"].to_numpy(dtype=float)
    if method in ("close", "vwap"):
        px = b["c"].to_numpy() if method == "close" else np.where(np.isfinite(b["vw"]), b["vw"], b["c"]).astype(float)
        return pd.Series(v).groupby(level_index(px, step)).sum()
    lo, hi = level_index(b["l"], step), level_index(b["h"], step)
    vw = np.where(np.isfinite(b["vw"]), b["vw"], b["c"]).astype(float)
    acc = {}
    for i in range(len(b)):
        lv = np.arange(lo[i], hi[i] + 1)
        if method == "uniform" or len(lv) == 1:
            w = np.ones(len(lv))
        else:                                   # triangular: peso máximo en el nivel del VWAP, cero fuera de [l, h]
            c = (vw[i] / step)
            half = max(c - lo[i], hi[i] + 1 - c, 1.0)
            w = np.clip(1 - np.abs(lv + 0.5 - c) / half, 0.05, None)
        w = w / w.sum() * v[i]
        for k, x in zip(lv, w):
            acc[k] = acc.get(k, 0.0) + x
    return pd.Series(acc).sort_index()


# ── métricas ───────────────────────────────────────────────────────────────────────────────────────────────────
def value_area(p: pd.Series, share: float = VA_SHARE) -> tuple:
    """(nivel_bajo, nivel_alto, poc): desde el POC se añade el nivel vecino con más volumen hasta cubrir `share`."""
    p = p[p > 0].sort_index()
    if p.empty:
        return None
    idx = p.index.to_numpy()
    full = pd.Series(0.0, index=np.arange(idx.min(), idx.max() + 1))
    full.loc[p.index] = p.to_numpy()
    arr, keys = full.to_numpy(), full.index.to_numpy()
    poc = int(np.argmax(arr))
    lo = hi = poc
    tot, acc = arr.sum(), arr[poc]
    while acc < share * tot:
        up = arr[hi + 1] if hi + 1 < len(arr) else -1
        dn = arr[lo - 1] if lo - 1 >= 0 else -1
        if up < 0 and dn < 0:
            break
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    return int(keys[lo]), int(keys[hi]), int(keys[poc])


def hvn(p: pd.Series, frac: float = 0.5) -> set:
    """Nodos de volumen alto: niveles con al menos `frac` del volumen del nivel máximo."""
    return set(p[p >= frac * p.max()].index) if len(p) else set()


def compare(est: pd.Series, obs: pd.Series, step: float, ref_price: float) -> dict:
    if est.empty or obs.empty:
        return {"ok": False}
    a, b = est / est.sum(), obs / obs.sum()
    keys = a.index.union(b.index)
    a, b = a.reindex(keys, fill_value=0), b.reindex(keys, fill_value=0)
    va_a, va_b = value_area(est), value_area(obs)
    inter = max(0, min(va_a[1], va_b[1]) - max(va_a[0], va_b[0]) + 1)
    union = max(va_a[1], va_b[1]) - min(va_a[0], va_b[0]) + 1
    bps = lambda levels: round(levels * step / ref_price * 1e4, 2)  # noqa: E731
    ha, hb = hvn(est), hvn(obs)
    top3 = lambda s: float(s.sort_values(ascending=False).iloc[:3].sum())  # noqa: E731
    return {"ok": True, "levels_obs": int((obs > 0).sum()),
            "poc_diff_levels": int(abs(va_a[2] - va_b[2])), "poc_diff_bps": bps(abs(va_a[2] - va_b[2])),
            "poc_same": va_a[2] == va_b[2],
            # volumen OBSERVADO en el nivel que la estimación da como POC, frente al del POC observado: cerca de 1 es un
            # casi empate (perfil plano), cerca de 0 es un POC estimado en un nivel con poca negociación real
            "poc_est_obs_volume_ratio": round(float(obs.get(va_a[2], 0.0) / obs.max()), 4),
            "va_jaccard": round(inter / union, 4),
            "va_mid_shift_bps": bps(abs((va_a[0] + va_a[1]) / 2 - (va_b[0] + va_b[1]) / 2)),
            "va_width_levels_obs": va_b[1] - va_b[0] + 1, "va_width_levels_est": va_a[1] - va_a[0] + 1,
            "tvd": round(0.5 * float(np.abs(a - b).sum()), 4),
            "top1_share_obs": round(float(b.max()), 4), "top1_share_est": round(float(a.max()), 4),
            "top3_share_obs": round(top3(b), 4), "top3_share_est": round(top3(a), 4),
            "hvn_jaccard": round(len(ha & hb) / max(1, len(ha | hb)), 4),
            "volume_ratio_est_obs": round(float(est.sum() / obs.sum()), 4)}


# ── escala común entre días ────────────────────────────────────────────────────────────────────────────────────
def split_factor(splits: pd.DataFrame, day: str, ref_day: str) -> float:
    """Factor que lleva los precios de `day` a la escala de `ref_day`: producto de 1/factor de los splits con fecha
    ex en (day, ref_day] (y su inverso si ref_day es anterior). `splits`: identity.split_events (ex_date, factor =
    acciones nuevas / antiguas; 4 en un split 4:1, 0,1 en un contrasplit 1:10)."""
    if splits is None or not len(splits) or day == ref_day:
        return 1.0
    a, b = sorted((day, ref_day))
    f = 1.0
    for r in splits[(splits["ex_date"] > a) & (splits["ex_date"] <= b)].itertuples():
        f /= float(r.factor)
    return f if day < ref_day else 1.0 / f
