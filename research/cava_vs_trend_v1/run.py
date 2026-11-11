"""Cava risk_off frente a VIX + tendencia del SPY (wiki/PREREGISTRO_CAVA_VS_TENDENCIA_V1.md). Ejecución única.
Reutiliza research/cava_vs_vix_v1/_work/postures.parquet (posturas, VIX, MDD21/VOL21/R63)."""
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

HERE = Path(__file__).resolve().parent
RNG = np.random.default_rng(20261111)
SUB = [('2005-01-01', '2012-12-31'), ('2013-01-01', '2019-12-31'), ('2020-01-01', '2026-12-31')]
df = pd.read_parquet(HERE.parent / "cava_vs_vix_v1" / "_work" / "postures.parquet")
spy = yf.download("SPY", start="1999-01-01", end="2026-11-11", auto_adjust=True, progress=False)["Close"].squeeze()
spy.index = pd.to_datetime(spy.index).tz_localize(None)
sma = spy.rolling(200).mean()
dist = (spy / sma - 1).reindex(df.index)
dd = (spy / spy.rolling(252).max() - 1).reindex(df.index)
df["T"] = (dist < 0).astype(int)
df["T15"] = (dist <= dist.quantile(df["C"].mean())).astype(int)
df["DD10"] = (dd <= -0.10).astype(int)

def h1(d, c="C", t="T"):
    base = d[(d.V == 0) & (d[t] == 0)]
    a, b = base[base[c] == 1].MDD21, base[base[c] == 0].MDD21
    return (a.mean() - b.mean()) if len(a) else np.nan

def boot(d, c="C", t="T", reps=5000, block=63):
    A, V, T, Y = d[c].values, d.V.values, d[t].values, d.MDD21.values
    N = len(Y); nb = int(np.ceil(N / block)); out = []
    for _ in range(reps):
        idx = ((RNG.integers(0, N, nb)[:, None] + np.arange(block)).ravel()[:N]) % N
        a, v, tt, y = A[idx], V[idx], T[idx], Y[idx]
        m = (v == 0) & (tt == 0)
        x1, x0 = y[m & (a == 1)], y[m & (a == 0)]
        out.append(x1.mean() - x0.mean() if len(x1) and len(x0) else np.nan)
    return [round(float(np.nanpercentile(out, 2.5)), 3), round(float(np.nanpercentile(out, 97.5)), 3)]

def episodes(mask):
    i = np.flatnonzero(mask); return int(1 + (np.diff(i) > 21).sum()) if len(i) else 0

res = {"freq": {k: round(float(df[k].mean()), 4) for k in ["C", "V", "T", "T15", "DD10"]}}
m = (df.C == 1) & (df.V == 0) & (df["T"] == 0)
res["riskoff_days_not_covered_by_V_or_T"] = {"days": int(m.sum()), "share_of_riskoff": round(float(m.sum() / df.C.sum()), 3),
                                             "episodes": episodes(m.values)}
tab = {}
for c in (0, 1):
    for vt in (0, 1):
        g = df[(df.C == c) & (((df.V == 1) | (df["T"] == 1)).astype(int) == vt)]
        tab[f"C={c},VoT={vt}"] = {"days": int(len(g)), "MDD21": round(float(g.MDD21.mean()), 3),
                                 "VOL21": round(float(g.VOL21.mean()), 2), "R63": round(float(g.R63.mean()), 3)}
res["table_C_vs_VorT"] = tab
H1 = h1(df); ci = boot(df)
res["H1"] = round(float(H1), 3); res["H1_ci95"] = ci
res["subperiods_H1"] = {f"{a[:4]}-{b[:4]}": round(float(h1(df[(df.index >= a) & (df.index <= b)])), 3) for a, b in SUB}
sens = {}
for t in ("T15", "DD10"):
    mm = (df.C == 1) & (df.V == 0) & (df[t] == 0)
    sens[t] = {"H1": round(float(h1(df, t=t)), 3), "ci95": boot(df, t=t, reps=2000), "days_C1_uncovered": int(mm.sum())}
sens["nolag"] = {"H1": round(float(h1(df, c="C_nolag")), 3)}
res["sensitivities"] = sens
crit = {"1_H1_le_-1_upper_lt0": H1 <= -1 and ci[1] < 0,
        "2_subperiods_2of3": sum(v < 0 for v in res["subperiods_H1"].values() if not np.isnan(v)) >= 2,
        "3_same_sign_T15_DD10_nolag": all(sens[k]["H1"] < 0 for k in ("T15", "DD10", "nolag"))}
res["criteria"] = crit
if res["riskoff_days_not_covered_by_V_or_T"]["episodes"] < 3:
    res["classification"] = "INCONCLUYENTE (datos)"
elif all(crit.values()):
    res["classification"] = "CAVA APORTA MÁS ALLÁ DE VIX Y TENDENCIA"
elif ci[0] > -1:
    res["classification"] = "CAVA NO APORTA MÁS ALLÁ DE VIX Y TENDENCIA"
else:
    res["classification"] = "INCONCLUYENTE"
(HERE / "results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
print(json.dumps(res, indent=1, ensure_ascii=False))
