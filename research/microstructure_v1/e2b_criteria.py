"""E2 — comprobación pendiente 1: criterios propios de las cinco medidas problemáticas (calibración 2016-2019).

Encargo del usuario (2026-11-21, «para despues.md» §4 y §7). Solo calibración 2016-2019 para fijar cifras; 2020-2021
se informa sin reajustar. Ningún resultado posterior a los eventos.

Medidas: P1_run_up/dn, P3_highvol_run, D3_gap, C3_ext35_up/dn, V3_close_est. Con M1 marcan sobre todo valor-días de
dispersión pequeña (E2_INFORME §3): rachas enteras, after hours lleno de ceros, huecos casi siempre nulos.

Criterio cat-v1 para estas medidas (además de la regla general M1 ≥ umbral de su familia):
- Propia historia: el valor supera el máximo de su línea base de 60 sesiones (m0pct = 100). En las continuas
  (C3_ext35, V3_close_est), percentil ≥ 99 de la base.
- Magnitud absoluta: el valor supera el percentil 99 de esa medida en todos los valor-días elegibles de calibración
  (rareza frente al universo, no solo frente a la propia dispersión).
- V3_close_est, además, solo es evaluable con barras si ≥ 90 % de las sesiones de su base tienen volumen en la barra
  de las 16:00: en valores de NYSE esa barra suele no recoger la subasta de cierre (vale 0 en el 50-95 % de sus días),
  y entonces cualquier volumen parece raro. Si no es evaluable, queda «requiere trades».
- D3_gap: la regla de liquidez de E1 (≥ 5 operaciones por minuto) se mantiene, pero no filtra nada en el S&P 500
  (la cumple el ~100 % de los valor-días); el filtro real es la magnitud absoluta.

Salidas (MICRO_DATA_DIR/results): e2b_criteria.json (cifras fijadas e impacto). Uso: py -3 e2b_criteria.py
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import storage  # noqa: E402
import e2_analyze as A  # noqa: E402
import e2_normalize as N  # noqa: E402

warnings.simplefilter("ignore", RuntimeWarning)
ROOT = storage.root()
RES = ROOT / "results"
SPECIAL = ("P1_run_up", "P1_run_dn", "P3_highvol_run", "D3_gap", "C3_ext35_up", "C3_ext35_dn", "V3_close_est")
DISCRETE = ("P1_run_up", "P1_run_dn", "P3_highvol_run", "D3_gap")
ABS_PCT = 99.0
V3_MIN_NONZERO_BASE = 0.90
D3_MIN_LIQ = 5.0


def load(cols_v, cols_n):
    a = ds.dataset(str(A.MEAS), format="parquet").to_table(columns=A.META + cols_v).to_pandas()
    b = ds.dataset(str(A.NORM), format="parquet").to_table(columns=["entity", "date"] + cols_n).to_pandas()
    return a.merge(b, on=["entity", "date"], how="left", validate="one_to_one").sort_values(["entity", "date"]).reset_index(drop=True)


def nonzero_base_share(df, m):
    """Por fila: fracción de las sesiones de su línea base (misma ventana que la normalización) con valor > 0."""
    out = np.full(len(df), np.nan)
    for _, g in df.groupby("entity", sort=False):
        x = g[f"{m}__v"].to_numpy(float)
        d = pd.to_datetime(g["date"]).to_numpy().astype("datetime64[D]")
        W = N.windows(x, d, (g["cov"] >= 0.2).to_numpy())
        n = np.isfinite(W).sum(1)
        with np.errstate(all="ignore"):
            out[g.index] = np.where(n > 0, (W > 0).sum(1) / n, np.nan)
    return out


def special_flags(df, rep, elig, calib):
    """Marcas cat-v1 de las cinco medidas y cifras fijadas. Devuelve (flags, params)."""
    th, fl = rep["calibration"]["M1"]["thresholds"], rep["mad_floors"]
    flags, params = {}, {}
    nz = nonzero_base_share(df, "V3_close_est")
    for m in SPECIAL:
        x = df[f"{m}__v"].to_numpy(float)
        s1 = df[f"{m}__m1dev"].to_numpy(float) / np.maximum(np.nan_to_num(df[f"{m}__m1mad"].to_numpy(float)), fl[m])
        pct = df[f"{m}__m0pct"].to_numpy(float)
        evaluable = elig[m].copy()
        if m == "V3_close_est":
            evaluable &= nz >= V3_MIN_NONZERO_BASE
        if m == "D3_gap":
            evaluable &= df["liq"].to_numpy(float) >= D3_MIN_LIQ
        a_m = float(np.nanpercentile(x[calib & evaluable], ABS_PCT))
        own = (pct >= 100 - 1e-6) if m in DISCRETE else (pct >= 99)
        f_m1 = (s1 >= th[m]) & elig[m]
        flags[m] = f_m1 & evaluable & own & (x > a_m)
        params[m] = {"m1_threshold": th[m], "mad_floor": fl[m], "abs_threshold_raw": a_m, "abs_rule": f"> p{ABS_PCT:g} calibración",
                     "own_rule": "> máximo de la base (m0pct = 100)" if m in DISCRETE else "percentil ≥ 99 de la base",
                     "evaluable_rule": {"V3_close_est": f"≥ {V3_MIN_NONZERO_BASE:.0%} de la base con volumen en la barra de las 16:00",
                                        "D3_gap": f"liquidez ≥ {D3_MIN_LIQ:g} operaciones/min (regla de E1)"}.get(m, "elegible"),
                     "_f_m1": f_m1, "_evaluable": evaluable}
    return flags, params, nz


def main():
    rep = json.loads((RES / "e2_report.json").read_text(encoding="utf-8"))
    th, fl = rep["calibration"]["M1"]["thresholds"], rep["mad_floors"]
    names = sorted(th)
    fam_of = {m: A.family_of(m) for m in names}
    fams_touched = sorted({fam_of[m] for m in SPECIAL})
    out = {"generated_utc": pd.Timestamp.now("UTC").isoformat(), "rules": {"abs_pct": ABS_PCT, "v3_min_nonzero_base": V3_MIN_NONZERO_BASE,
                                                                         "d3_min_liq": D3_MIN_LIQ}, "measures": {}, "families": {}}
    # 1) las cinco medidas
    cv = [f"{m}__v" for m in SPECIAL]
    cn = [f"{m}__{s}" for m in SPECIAL for s in ("n", "m0pct", "m1dev", "m1mad", "mad0")]
    df = load(cv, cn)
    elig_day = A.base_mask(df).to_numpy()
    calib = (df["date"] <= A.CALIB_END).to_numpy()
    valid = ((df["date"] >= A.VALID_START) & (df["date"] <= A.E2_LAST)).to_numpy()
    year = df["date"].str[:4].to_numpy()
    elig = {m: elig_day & np.isfinite(df[f"{m}__v"].to_numpy(float)) & (df[f"{m}__n"].to_numpy() >= A.MIN_N) for m in SPECIAL}
    flags, params, nz = special_flags(df, rep, elig, calib)
    for m in SPECIAL:
        p = params[m]
        f1, ev = p.pop("_f_m1"), p.pop("_evaluable")
        mad0 = df[f"{m}__mad0"].to_numpy(float)
        small = mad0 <= np.nanpercentile(mad0[calib & elig[m]], 10)
        x = df[f"{m}__v"].to_numpy(float)
        out["measures"][m] = {
            **p,
            "evaluable_share_calib": round(float(ev[calib & elig[m]].mean()), 4),
            "rate_m1_calib": round(float(f1[calib & elig[m]].mean()), 5),
            "rate_v1_calib": round(float(flags[m][calib & elig[m]].mean()), 5),
            "rate_m1_valid": round(float(f1[valid & elig[m]].mean()), 5),
            "rate_v1_valid": round(float(flags[m][valid & elig[m]].mean()), 5),
            "rate_v1_by_year": {y: round(float(flags[m][(year == y) & elig[m]].mean()), 5) for y in sorted(set(year[elig[m]]))},
            "share_small_mad_m1": round(float(small[f1 & calib].mean()), 3) if (f1 & calib).any() else None,
            "share_small_mad_v1": round(float(small[flags[m] & calib].mean()), 3) if (flags[m] & calib).any() else None,
            "raw_of_v1_flags_q10_50_90": [round(float(v), 4) for v in np.nanquantile(x[flags[m] & calib], [.1, .5, .9])]
            if (flags[m] & calib).any() else None,
            "kept_share_of_m1_flags_calib": round(float(flags[m][f1 & calib].mean()), 3) if (f1 & calib).any() else None,
            # referencia: en medidas discretas o llenas de ceros, «MAD pequeña» es lo normal, no señal de falsa anomalía
            "share_small_mad_all_rows_calib": round(float(small[calib & elig[m]].mean()), 3),
            # sensibilidad (no decide): solo evaluable + M1, sin propia historia ni magnitud absoluta
            "rate_evaluable_m1_only_calib": round(float((f1 & ev)[calib & elig[m]].mean()), 5)}
    if True:
        ev3 = elig["V3_close_est"] & calib
        out["v3_close_venue_effect"] = {
            "share_valor_days_evaluable_calib": round(float((nz[ev3] >= V3_MIN_NONZERO_BASE).mean()), 4),
            "zero_share_by_year": {y: round(float((df["V3_close_est__v"].to_numpy(float)[(year == y) & elig["V3_close_est"]] == 0).mean()), 3)
                                   for y in sorted(set(year[elig["V3_close_est"]]))},
            "note": "en valores de Nasdaq la barra de las 16:00 casi siempre tiene volumen; en NYSE vale 0 en el 50-95 % de los días"}
    special = {m: flags[m] for m in SPECIAL}
    del df
    # 2) tasas por familia (calibración y comprobación) con las cinco medidas sustituidas; resto sin tocar
    for f in fams_touched:
        ms = [m for m in names if fam_of[m] == f]
        cols_v = [f"{m}__v" for m in ms]
        cols_n = [f"{m}__{s}" for m in ms for s in ("n", "m1dev", "m1mad")]
        d = load(cols_v, cols_n)
        ed = A.base_mask(d).to_numpy()
        assert len(d) == len(special[SPECIAL[0]])
        anyv0 = np.zeros(len(d), bool)
        anyv1 = np.zeros(len(d), bool)
        for m in ms:
            e = ed & np.isfinite(d[f"{m}__v"].to_numpy(float)) & (d[f"{m}__n"].to_numpy() >= A.MIN_N)
            s1 = d[f"{m}__m1dev"].to_numpy(float) / np.maximum(np.nan_to_num(d[f"{m}__m1mad"].to_numpy(float)), fl[m])
            fm1 = (s1 >= th[m]) & e
            anyv0 |= fm1
            anyv1 |= special[m] if m in SPECIAL else fm1
        y = d["date"].str[:4].to_numpy()
        c = (d["date"] <= A.CALIB_END).to_numpy()
        v = ((d["date"] >= A.VALID_START) & (d["date"] <= A.E2_LAST)).to_numpy()
        out["families"][f] = {"measures": ms, "changed": [m for m in ms if m in SPECIAL],
                              "rate_e2_m1_calib": round(float(anyv0[ed & c].mean()), 4), "rate_v1_calib": round(float(anyv1[ed & c].mean()), 4),
                              "rate_e2_m1_valid": round(float(anyv0[ed & v].mean()), 4), "rate_v1_valid": round(float(anyv1[ed & v].mean()), 4),
                              "rate_v1_by_year": {yy: round(float(anyv1[ed & (y == yy)].mean()), 4) for yy in sorted(set(y[ed]))}}
        del d
    (RES / "e2b_criteria.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    print(json.dumps({m: {k: out["measures"][m][k] for k in ("abs_threshold_raw", "rate_m1_calib", "rate_v1_calib", "rate_v1_valid",
                                                             "share_small_mad_m1", "share_small_mad_v1", "kept_share_of_m1_flags_calib")}
                      for m in SPECIAL}, indent=1, ensure_ascii=False))
    print(json.dumps(out["families"], indent=1, ensure_ascii=False)[:3000])
    print(out.get("v3_close_venue_effect"))


if __name__ == "__main__":
    main()
