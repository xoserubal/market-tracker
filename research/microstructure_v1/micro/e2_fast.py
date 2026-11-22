"""E2 — versiones rápidas (vectorizadas) de build_matrix y build_profile de intraday_features (cat-v0).

No sustituyen a las originales: el escaneo diario y cat-v0 siguen usando intraday_features tal cual. Estas existen
porque el retrospectivo de E2 recalcula el perfil de cada sesión (≈ 700 000 valor-días) y los bucles por minuto de las
originales lo harían inviable. `tests/test_e2.py` comprueba que dan exactamente el mismo resultado.

Perfil incremental: `day_parts` extrae una sola vez lo que cada sesión aporta al perfil (volúmenes alineados, retornos
de 1 minuto por bloque, tamaño y rango por bloque); `profile_from_parts` junta las sesiones de la línea base.
"""
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd

from . import intraday_features as F, sessions

BUCKET = F.BUCKET


@lru_cache(maxsize=None)
def bounds(day: str) -> dict:
    return sessions.bounds(day)


def build_matrix_fast(bars: pd.DataFrame, days: list, dtype=np.float64) -> F.DayMatrix:
    """Igual que intraday_features.build_matrix, sin filtrar el DataFrame día a día."""
    D, S = len(days), sessions.N_SLOTS
    arr = {k: np.full((D, S), np.nan, dtype=dtype) for k in ("O", "H", "L", "C", "V", "N", "VW")}
    meta = [bounds(d) for d in days]
    units = {}
    if len(bars):
        pos = {d: i for i, d in enumerate(days)}
        x = bars[bars["_day"].isin(pos)]
        di = x["_day"].map(pos).to_numpy()
        base = np.array([m["base"].value for m in meta], dtype=np.int64)
        tv = x["t"].astype("int64").to_numpy() if x["t"].dt.unit == "ns" else x["t"].dt.as_unit("ns").astype("int64").to_numpy()
        s = (tv - base[di]) // 60_000_000_000
        ok = (s >= 0) & (s < S)
        for k, col in (("O", "o"), ("H", "h"), ("L", "l"), ("C", "c"), ("V", "v"), ("N", "n"), ("VW", "vw")):
            arr[k][di[ok], s[ok]] = x[col].to_numpy(dtype=float)[ok]
        if "_unit" in x:
            for d, g in x.groupby("_day")["_unit"]:
                units[d] = sorted(set(g))
    return F.DayMatrix(days=list(days), meta=meta, units=units, **arr)


def day_parts(M: F.DayMatrix, i: int) -> dict:
    """Aportación de la sesión i al perfil (misma selección de minutos que intraday_features._build_profile)."""
    S = sessions.N_SLOTS
    b = M.meta[i]
    o, c, e = b["open_slot"], b["close_slot"], b["end_slot"]
    v = np.nan_to_num(M.V[i].astype(float))
    vc, vp, vq = np.full(S, np.nan), np.full(S, np.nan), np.full(S, np.nan)
    vc[:c - o] = v[o:c]
    vp[:o] = v[:o]
    vq[:e - c] = v[c:e]
    C = M.C[i].astype(float)
    with np.errstate(all="ignore"):
        lc = np.log(F._ffill(C))
        r = np.diff(lc, prepend=np.nan)
    has = ~np.isnan(C)
    idx = np.arange(S)
    fin = np.isfinite(r)
    m_cont = (idx > o + 1) & (idx < c) & has & fin            # s in (o+1, c) y s-1 > o
    rc = r[m_cont]
    kc = (idx[m_cont] - o) // BUCKET
    rpre = r[(idx >= 1) & (idx < o) & has & fin]
    rpost = r[(idx >= c + 1) & (idx < e) & has & fin]
    Nn = M.N[i].astype(float)
    m_sz = (idx >= o + 1) & (idx < c) & has & (Nn > 0)
    with np.errstate(all="ignore"):
        sz = (M.V[i].astype(float) / Nn)[m_sz]
        rg = ((M.H[i].astype(float) - M.L[i].astype(float)) / C)[m_sz]
    ks = (idx[m_sz] - o) // BUCKET
    return {"vc": vc, "vp": vp, "vq": vq, "rc": rc, "kc": kc, "rpre": rpre, "rpost": rpost, "sz": sz, "rg": rg, "ks": ks}


def profile_from_parts(parts: list) -> F.Profile:
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        S = sessions.N_SLOTS
        n = len(parts)
        med = lambda key: np.nanmedian(np.vstack([p[key] for p in parts]), axis=0) if n else np.full(S, np.nan)  # noqa
        vol_cont = med("vc")
        floor = max(1.0, F.VOL_FLOOR_SHARE * float(np.nanmedian(vol_cont[1:390])) if np.any(np.isfinite(vol_cont[1:390])) else 1.0)
        rc = np.concatenate([p["rc"] for p in parts]) if n else np.array([])
        kc = np.concatenate([p["kc"] for p in parts]) if n else np.array([], dtype=int)
        nb = int(kc.max()) + 1 if len(kc) else 1
        sz = np.concatenate([p["sz"] for p in parts]) if n else np.array([])
        rg = np.concatenate([p["rg"] for p in parts]) if n else np.array([])
        ks = np.concatenate([p["ks"] for p in parts]) if n else np.array([], dtype=int)
        sig_cont = np.array([F._robust_sigma(rc[kc == k]) for k in range(nb)])
        size_cont = np.array([np.median(sz[ks == k]) if np.any(ks == k) else np.nan for k in range(nb)])
        range_cont = np.array([np.median(rg[ks == k]) if np.any(ks == k) else np.nan for k in range(nb)])
        return F.Profile(vol_cont=vol_cont, vol_pre=med("vp"), vol_post=med("vq"), sig_cont=sig_cont,
                         sig_pre=F._robust_sigma(np.concatenate([p["rpre"] for p in parts]) if n else np.array([])),
                         sig_post=F._robust_sigma(np.concatenate([p["rpost"] for p in parts]) if n else np.array([])),
                         size_cont=size_cont, range_cont=range_cont, vol_floor=floor, n_days=n)
