"""Cava risk_off frente al VIX — ejecución única del preregistro (wiki/PREREGISTRO_CAVA_VS_VIX_V1.md).
Salida: results.json; postura diaria en _work/postures.parquet."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = HERE / "_work"; WORK.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "research" / "sector_confluence_v1"))

import cava_state_history as csh                         # noqa: E402
from cava_mapping import build_market_state              # noqa: E402
from cava_test_1c import to_engine_inputs                # noqa: E402
from build_signals import load_macro_inputs, lagged_inputs  # noqa: E402
sys.path.insert(0, str(ROOT / "backtest"))
from src.macro.simulator import simulate_history         # noqa: E402
from cava_engine import core, load_corpus, query_tree    # noqa: E402

RNG = np.random.default_rng(20261111)
EMI = -1.0
SUB = [('2005-01-01', '2012-12-31'), ('2013-01-01', '2019-12-31'), ('2020-01-01', '2026-12-31')]


def postures(macro: pd.DataFrame, prices: pd.DataFrame, hy: pd.Series, dates) -> pd.Series:
    csh._CACHE = (macro, prices, hy)
    tree, index, timeline, meta = load_corpus(core.CORPUS_SCOPE_PILOT)
    cache, out = {}, {}
    for ts in dates:
        flat = build_market_state(csh.macro_inputs_at(ts))
        key = "|".join(f"{k}={v}" for k, v in sorted(flat.items()))
        if key not in cache:
            r = query_tree(tree, index, timeline, to_engine_inputs(flat), corpus_meta=meta)
            cache[key] = r.get("structural_logic", {}).get("deterministic_risk_posture", "unknown")
        out[ts] = cache[key]
    print(f"  {len(cache)} estados distintos")
    return pd.Series(out)


def main():
    import yfinance as yf
    raw = yf.download(["SPY", "^VIX"], start="1999-01-01", end="2026-11-11", auto_adjust=True,
                      progress=False, group_by="ticker")
    px = pd.DataFrame({"SPY": raw["SPY"]["Close"], "VIX": raw["^VIX"]["Close"]}).dropna(how="all").sort_index()
    px.index = pd.to_datetime(px.index).tz_localize(None)

    hy = pd.read_parquet(ROOT / "backtest/data/processed/macro_daily.parquet")["BAMLH0A0HYM2"].dropna().sort_index() * 100
    data = load_macro_inputs()
    m_lag = simulate_history(lagged_inputs(data), mode='A')
    m_nolag = simulate_history(data, mode='A')
    for m in (m_lag, m_nolag):
        m['mode'] = 'A'
        m.index.name = 'date'

    spy = px["SPY"].dropna()
    cal = spy.index
    n = len(cal)
    last = n - 1 - 63
    dates = [d for d in cal[:last + 1] if d >= pd.Timestamp("2005-02-01")]

    post_lag = postures(m_lag, px, hy, dates)
    post_nolag = postures(m_nolag, px, hy, dates)

    df = pd.DataFrame({"post": post_lag, "post_nolag": post_nolag})
    pos = cal.get_indexer(df.index)
    s = spy.values
    ret = np.diff(np.log(s), prepend=np.nan)
    mdd, vol, r63 = [], [], []
    for i in pos:
        w = s[i + 1:i + 22]
        mdd.append(min(0.0, (w.min() / s[i] - 1) * 100))
        vol.append(np.std(ret[i + 1:i + 22], ddof=1) * np.sqrt(252) * 100)
        r63.append((s[i + 63] / s[i] - 1) * 100)
    df["MDD21"], df["VOL21"], df["R63"] = mdd, vol, r63

    # VIX: percentil del valor de t entre las 1260 sesiones anteriores (sin t)
    vix = px["VIX"].dropna()
    vv = vix.values
    pr = pd.Series(np.nan, index=vix.index)
    for j in range(1260, len(vv)):
        pr.iloc[j] = (vv[j - 1260:j] <= vv[j]).mean()
    df["vix"] = vix.reindex(df.index).values
    df["vix_pct"] = pr.reindex(df.index).values
    df["C"] = (df["post"] == "risk_off").astype(int)
    df["C_nolag"] = (df["post_nolag"] == "risk_off").astype(int)
    fC = df["C"].mean()
    q = float(np.nanquantile(df["vix_pct"], 1 - fC))
    df["V"] = (df["vix_pct"] >= q).astype(int)
    df["V25"] = (df["vix"] >= 25).astype(int)
    df.to_parquet(WORK / "postures.parquet")

    def stats(d, c="C", v="V", y="MDD21"):
        a, b_, yy = d[c].values, d[v].values, d[y].values
        m = lambda mask: yy[mask].mean() if mask.sum() else np.nan
        h1 = m((a == 1) & (b_ == 0)) - m((a == 0) & (b_ == 0))
        h2 = m((a == 1) & (b_ == 0)) - m((a == 0) & (b_ == 1))
        return h1, h2

    def boot(d, c="C", v="V", y="MDD21", reps=5000, block=63):
        a, b_, yy = d[c].values, d[v].values, d[y].values
        N = len(yy); nb = int(np.ceil(N / block))
        h1s, h2s = [], []
        for _ in range(reps):
            starts = RNG.integers(0, N, nb)
            idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:N] % N
            A, B, Y = a[idx], b_[idx], yy[idx]
            def mm(mask): return Y[mask].mean() if mask.sum() else np.nan
            c10 = mm((A == 1) & (B == 0))
            h1s.append(c10 - mm((A == 0) & (B == 0)))
            h2s.append(c10 - mm((A == 0) & (B == 1)))
        ci = lambda x: [round(float(np.nanpercentile(x, 2.5)), 3), round(float(np.nanpercentile(x, 97.5)), 3)]
        return ci(h1s), ci(h2s)

    def episodes(mask):
        idx = np.flatnonzero(mask)
        if len(idx) == 0:
            return 0
        return int(1 + (np.diff(idx) > 21).sum())

    def table(d, c="C", v="V"):
        t = {}
        for a in (0, 1):
            for b_ in (0, 1):
                g = d[(d[c] == a) & (d[v] == b_)]
                t[f"{c}={a},{v}={b_}"] = {"days": int(len(g)), "MDD21": round(float(g.MDD21.mean()), 3) if len(g) else None,
                                         "VOL21": round(float(g.VOL21.mean()), 2) if len(g) else None,
                                         "R63": round(float(g.R63.mean()), 3) if len(g) else None}
        return t

    res = {"n_days": int(len(df)), "range": [str(df.index.min().date()), str(df.index.max().date())],
           "freq_C": round(fC, 4), "q_vix_pct": round(q, 4), "freq_V": round(float(df.V.mean()), 4),
           "agreement_C_V": round(float((df.C == df.V).mean()), 4),
           "posture_counts": df["post"].value_counts().to_dict()}
    h1, h2 = stats(df)
    ci1, ci2 = boot(df)
    res["primary"] = {"H1_MDD21": round(float(h1), 3), "H1_ci95": ci1, "H2_MDD21": round(float(h2), 3), "H2_ci95": ci2,
                      "episodes_C1_V0": episodes(((df.C == 1) & (df.V == 0)).values),
                      "table": table(df)}
    res["separation_alone"] = {
        "C": round(float(df[df.C == 1].MDD21.mean() - df[df.C == 0].MDD21.mean()), 3),
        "V": round(float(df[df.V == 1].MDD21.mean() - df[df.V == 0].MDD21.mean()), 3)}
    res["subperiods_H1"] = {}
    for a, b_ in SUB:
        d = df[(df.index >= a) & (df.index <= b_)]
        res["subperiods_H1"][f"{a[:4]}-{b_[:4]}"] = round(float(stats(d)[0]), 3) if len(d) else None
    sens = {}
    h1n, h2n = stats(df, c="C_nolag"); sens["nolag"] = {"H1": round(float(h1n), 3), "H2": round(float(h2n), 3),
                                                        "ci95_H1": boot(df, c="C_nolag", reps=2000)[0]}
    h125, h225 = stats(df, v="V25"); sens["vix_ge_25"] = {"H1": round(float(h125), 3), "H2": round(float(h225), 3),
                                                         "ci95_H1": boot(df, v="V25", reps=2000)[0],
                                                         "table": table(df, v="V25")}
    d23 = df[df.index >= "2023-08-01"]
    h1c, h2c = stats(d23); sens["since_2023_08"] = {"H1": None if np.isnan(h1c) else round(float(h1c), 3),
                                                     "H2": None if np.isnan(h2c) else round(float(h2c), 3),
                                                     "table": table(d23)}
    h1v, h2v = stats(df, y="VOL21"); sens["VOL21"] = {"H1": round(float(h1v), 3), "H2": round(float(h2v), 3),
                                                     "ci95": boot(df, y="VOL21", reps=2000)}
    h1r, h2r = stats(df, y="R63"); sens["R63"] = {"H1": round(float(h1r), 3), "H2": round(float(h2r), 3)}
    res["sensitivities"] = sens

    p = res["primary"]
    crit = {"1_H1_le_-1_and_upper_lt0": p["H1_MDD21"] <= EMI and p["H1_ci95"][1] < 0,
            "2_H2_lt0": p["H2_MDD21"] < 0,
            "3_subperiods_2of3": sum((v is not None and v < 0) for v in res["subperiods_H1"].values()) >= 2,
            "4_same_sign_nolag_and_vix25": sens["nolag"]["H1"] < 0 and sens["vix_ge_25"]["H1"] < 0}
    res["criteria"] = crit
    if p["episodes_C1_V0"] < 3:
        res["classification"] = "INCONCLUYENTE (datos: < 3 episodios con C=1, V=0)"
    elif all(crit.values()):
        res["classification"] = "CAVA APORTA"
    elif p["H1_ci95"][0] > EMI:
        res["classification"] = "CAVA NO APORTA SOBRE EL VIX"
    else:
        res["classification"] = "INCONCLUYENTE"
    (HERE / "results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(res, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
