"""E2 — normalización estrictamente a fecha de las medidas de e2_compute.py, con tres métodos comparables.

Para cada entidad y medida, la línea base de la sesión t son los valores de la MISMA medida en sesiones anteriores
(nunca t ni posteriores). No se excluyen los días que ya dieron alerta (autorización §3: un cambio persistente de
régimen debe poder entrar en la referencia).

Métodos
- M0 · cat-v0 exacto: últimas 60 sesiones con valor dentro de 180 días naturales; marca si x > percentil 99 de la
  base (con 60 valores, superar su máximo) O z robusto (x − mediana) / (1,4826·MAD) ≥ 4 con MAD > 0.
- M1 · robusto con transformación por tipo de medida y suelo de dispersión: misma ventana; cocientes en log,
  rachas en log(1 + x), el resto sin transformar; puntuación (x − mediana) / max(1,4826·MAD, suelo). El suelo de cada
  medida es el percentil 10 de las MAD de su línea base en el periodo de calibración (lo fija e2_analyze.py; aquí se
  guarda la MAD sin suelo).
- M2 · adaptativo: media y desviación absoluta exponenciales (semivida 20 sesiones) de los valores anteriores,
  transformados como en M1; puntuación (x − m) / (1,2533·d). Se adapta antes a un cambio de nivel persistente.

Salida: MICRO_DATA_DIR/features/e2_norm/<entidad>.parquet (reanudable). Uso: py -3 e2_normalize.py [--workers 4]
"""
import argparse
import sys
import warnings
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import storage  # noqa: E402

SRC = storage.root() / "features" / "e2_measures"
OUT = storage.root() / "features" / "e2_norm"
WIN, MAX_AGE, HALFLIFE = 60, 180, 20
PCT_HI, Z_HI = 99.0, 4.0
LOG_MEASURES = ("V1_", "V2_size", "PRE_vol", "C3_vol_est", "V3_", "D2_range", "I2_stall")
LOG1P_MEASURES = ("P1_run", "P3_highvol_run", "D3_gap")


def transform_kind(name: str) -> str:
    if name.startswith(LOG_MEASURES):
        return "log"
    if name.startswith(LOG1P_MEASURES):
        return "log1p"
    return "id"


def transform(name: str, x: np.ndarray) -> np.ndarray:
    k = transform_kind(name)
    with np.errstate(all="ignore"):
        if k == "log":
            return np.log(np.where(x > 0, x, np.nan))
        if k == "log1p":
            return np.log1p(np.where(x >= 0, x, np.nan))
    return x


def windows(vals: np.ndarray, dates: np.ndarray, base_ok: np.ndarray = None):
    """Para cada fila, los WIN valores válidos anteriores (NaN de relleno) dentro de MAX_AGE días. -> (n_rows, WIN).

    Como en E1, solo entran en la base las sesiones válidas (base_ok: ≥ 20 % de minutos continuos con barra)."""
    n = len(vals)
    ok = np.isfinite(vals) & (base_ok if base_ok is not None else True)
    idx = np.where(ok)[0]
    W = np.full((n, WIN), np.nan)
    if len(idx) == 0:
        return W
    v = vals[idx]
    d = dates[idx]
    pad_v = np.concatenate([np.full(WIN, np.nan), v])
    pad_d = np.concatenate([np.full(WIN, np.datetime64("1900-01-01", "D")), d])
    sw_v = sliding_window_view(pad_v, WIN)[:-1]       # fila k: los WIN valores válidos anteriores al k-ésimo válido
    sw_d = sliding_window_view(pad_d, WIN)[:-1]
    # posición en la lista de válidos de cada fila: nº de válidos estrictamente anteriores
    k_prior = np.cumsum(ok) - ok
    k_prior = np.minimum(k_prior, len(v))
    full_v = np.vstack([sw_v, sliding_window_view(pad_v, WIN)[-1:]])
    full_d = np.vstack([sw_d, sliding_window_view(pad_d, WIN)[-1:]])
    W = full_v[k_prior].copy()
    age = (dates[:, None] - full_d[k_prior]).astype("timedelta64[D]").astype(float)
    W[age > MAX_AGE] = np.nan
    return W


def m0(x, W):
    n = np.isfinite(W).sum(1)
    S = np.sort(W, axis=1)                               # NaN al final
    with np.errstate(all="ignore"):
        med = np.nanmedian(W, axis=1)
        mad = np.nanmedian(np.abs(W - med[:, None]), axis=1) * 1.4826
        below = (W < x[:, None]).sum(1)
        eq = (W == x[:, None]).sum(1)
        pct = 100.0 * (below + 0.5 * eq) / n
        ti = np.minimum(n - 1, np.floor(PCT_HI / 100 * n)).astype(int)
        thr = S[np.arange(len(x)), np.clip(ti, 0, WIN - 1)]
        z = np.where(mad > 0, (x - med) / mad, np.nan)
    flag = np.isfinite(x) & (n > 0) & ((x > thr) | (z >= Z_HI))
    rule_z_only = flag & ~(x > thr)
    return n, pct, z, flag, rule_z_only, mad


def m1(x, W, name):
    xt = transform(name, x)
    Wt = transform(name, W)
    with np.errstate(all="ignore"):
        med = np.nanmedian(Wt, axis=1)
        mad = np.nanmedian(np.abs(Wt - med[:, None]), axis=1) * 1.4826
        n = np.isfinite(Wt).sum(1)
        pct = 100.0 * ((Wt < xt[:, None]).sum(1) + 0.5 * (Wt == xt[:, None]).sum(1)) / n
    return xt - med, mad, pct, n


def m2(xt):
    s = pd.Series(xt)
    m = s.ewm(halflife=HALFLIFE, ignore_na=True, min_periods=20).mean().shift(1)
    d = (s - m).abs().ewm(halflife=HALFLIFE, ignore_na=True, min_periods=20).mean().shift(1)
    # el desplazamiento usa la fila anterior: con NaN intermedios la media ya ignora esas filas
    m = m.ffill()
    d = d.ffill()
    with np.errstate(all="ignore"):
        return ((s - m) / (1.2533 * d)).to_numpy()


def norm_entity(path: Path) -> dict:
    warnings.simplefilter("ignore", RuntimeWarning)
    t0 = time.time()
    df = pd.read_parquet(path)
    dates = pd.to_datetime(df["date"]).to_numpy().astype("datetime64[D]")
    base_ok = (df["cov"] >= 0.2).to_numpy()
    out = {"entity": df["entity"], "date": df["date"]}
    for c in [c for c in df.columns if c.endswith("__v")]:
        name = c[:-3]
        x = df[c].to_numpy(dtype=float)
        W = windows(x, dates, base_ok)
        n, pct, z, flag, zonly, mad0 = m0(x, W)
        dev, mad1, pct1, _ = m1(x, W, name)
        out[f"{name}__n"] = n.astype("int16")
        out[f"{name}__m0pct"] = pct.astype("float32")
        out[f"{name}__m0z"] = z.astype("float32")
        out[f"{name}__m0f"] = flag
        out[f"{name}__m0zonly"] = zonly
        out[f"{name}__mad0"] = mad0.astype("float32")
        out[f"{name}__m1dev"] = dev.astype("float32")
        out[f"{name}__m1mad"] = mad1.astype("float32")
        out[f"{name}__m1pct"] = pct1.astype("float32")
        out[f"{name}__m2"] = m2(transform(name, x)).astype("float32")
    res = pd.DataFrame(out)
    storage.write_parquet_atomic(res, OUT / path.name)
    return {"entity": path.stem, "rows": len(res), "seconds": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [p for p in sorted(SRC.glob("*.parquet")) if not (OUT / p.name).exists()]
    print(f"pendientes {len(todo)}", flush=True)
    t0 = time.time()
    with Pool(a.workers) as pool:
        for k, r in enumerate(pool.imap_unordered(norm_entity, todo), 1):
            if k % 25 == 0 or k == len(todo):
                print(f"{k}/{len(todo)} · {round(time.time() - t0)} s", flush=True)


if __name__ == "__main__":
    main()
