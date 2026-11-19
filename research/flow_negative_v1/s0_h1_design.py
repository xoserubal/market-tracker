"""Diagnóstico del diseño de H1 (sin rendimientos posteriores).

H1: entre valores con caídas parecidas a 5 y 21 sesiones, ¿el resto del Flow (R = Flow − momentum: RSI, MACD, ATR,
Koncorde, distancia al máximo) distingue resultados futuros? Este script solo mide si el diseño tiene datos para
contestar: tamaño de las celdas de retornos previos, variación de R dentro de ellas y relación de R con los retornos.
Población: días-miembro con Flow < 0, Flow completo, sin evento, en el periodo de DESARROLLO de cada índice.

Salida: data/h1_design.json
"""
import json

import numpy as np
import pandas as pd

import fn_config as C


def cells_per_date(g, q):
    """Celdas q×q por fecha (cuantiles transversales de w1 y m1 dentro del universo ese día)."""
    out = []
    for d, x in g.groupby("date"):
        if len(x) < 2 * q:
            continue
        a = pd.qcut(x.w1.rank(method="first"), q, labels=False)
        b = pd.qcut(x.m1.rank(method="first"), q, labels=False)
        out.append(pd.crosstab(a, b).reindex(index=range(q), columns=range(q), fill_value=0).to_numpy().ravel())
    return np.array(out)


def main():
    p = pd.read_parquet(C.WORK / "panel.parquet")
    res = {}
    for idx, g0 in p.groupby("index"):
        dev = g0[(g0.date >= C.SIGNAL_START[idx]) & (g0.date <= C.DEV_END[idx]) & g0.flow_complete.fillna(False)
                 & ~g0.event_excluded]
        neg = dev[dev.flow < 0].dropna(subset=["w1", "m1", "R"])
        r = {"dev_days": int(neg.date.nunique()), "neg_obs": int(len(neg)),
             "neg_per_date_median": float(neg.groupby("date").size().median()),
             "R_values_distinct": int(neg.R.round(2).nunique()),
             "R_quantiles": {str(q): float(neg.R.quantile(q)) for q in (.05, .25, .5, .75, .95)},
             "corr_spearman_R_w1": float(neg[["R", "w1"]].corr("spearman").iat[0, 1]),
             "corr_spearman_R_m1": float(neg[["R", "m1"]].corr("spearman").iat[0, 1])}
        for q in (10, 5):
            c = cells_per_date(neg, q)
            r[f"cells_{q}x{q}"] = {"per_date": q * q, "median_size": float(np.median(c)),
                                   "share_cells_lt5": float((c < 5).mean()), "share_cells_lt10": float((c < 10).mean()),
                                   "share_obs_in_cells_lt10": float((c * (c < 10)).sum() / c.sum())}
        # variación de R que queda tras controlar w1 y m1 (residuo de un ajuste por splines aditivos + interacción)
        X = np.column_stack([np.ones(len(neg))] + [np.clip(neg[v], neg[v].quantile(.01), neg[v].quantile(.99)) ** k
                                                   for v in ("w1", "m1") for k in (1, 2, 3)] + [neg.w1 * neg.m1])
        beta, *_ = np.linalg.lstsq(X, neg.R.to_numpy(), rcond=None)
        resid = neg.R.to_numpy() - X @ beta
        r["R_var_explained_by_returns"] = float(1 - resid.var() / neg.R.var())
        r["R_resid_sd"] = float(resid.std())
        # celdas de calendario: quintiles fijados en desarrollo, agrupando un mes; mínimo 30 observaciones
        qb = {v: np.quantile(neg[v], [.2, .4, .6, .8]) for v in ("w1", "m1")}
        cell = (np.searchsorted(qb["w1"], neg.w1) * 5 + np.searchsorted(qb["m1"], neg.m1))
        mon = neg.date.str[:7]
        sizes = pd.Series(1, index=pd.MultiIndex.from_arrays([mon, cell])).groupby(level=[0, 1]).size()
        r["month_cells_5x5"] = {"cells": int(len(sizes)), "share_cells_ge30": float((sizes >= 30).mean()),
                                "share_obs_in_cells_ge30": float(sizes[sizes >= 30].sum() / sizes.sum())}
        res[idx] = r
    json.dump(res, open(C.PUB / "h1_design.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
