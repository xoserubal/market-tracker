"""Etapa 2 del preregistro wiki/PREREGISTRO_SECTOR_BREADTH_V1.md (firmado 2026-11-11). Una sola ejecución.
Lee _work/panel.parquet (build_panel.py). Salida: results.json"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "_work")
DEV_END, TEST_START = pd.Timestamp("2022-12-31"), pd.Timestamp("2023-01-01")
EMI = 0.05
CTRL = ["RS21", "RS63", "dRS21"]
LAGS = {10: (2, 4), 20: (4, 8), 40: (8, 16), 60: (12, 24)}


def nw(x, lag):
    x = np.asarray([v for v in x if not np.isnan(v)], float)
    n = len(x)
    if n < 5:
        return {"mean": None, "t": None, "se": None, "n": n}
    m = x.mean(); e = x - m
    v = e @ e / n
    for j in range(1, min(lag, n - 1) + 1):
        v += 2 * (1 - j / (lag + 1)) * (e[j:] @ e[:-j]) / n
    se = float(np.sqrt(v / n))
    return {"mean": float(m), "t": float(m / se) if se > 0 else None, "se": se, "n": n}


def crank(s):
    n = s.notna().sum()
    if n < 2:
        return s * np.nan
    return (s.rank() - (n + 1) / 2) / (n - 1)


def prepare(p, th, drop=None):
    p = p.copy()
    p["rel"] = (p.coverage >= th) & (p.n_priced >= 10) & (p.ambiguous_share <= 0.05)
    if drop:
        p = p[p.sector != drop]
    p = p[p.rel & p[["dP"] + CTRL].notna().all(axis=1)]
    cnt = p.groupby("date").sector.transform("size")
    p = p[cnt >= 8].copy()
    for c in ["dP"] + CTRL + ["d_above50", "ew_minus_etf21"]:
        p["r_" + c] = p.groupby("date")[c].transform(crank)
    return p


def ols(X, y):
    m = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
    b, *_ = np.linalg.lstsq(X[m], y[m], rcond=None)
    return b


def ic_by_date(p, sig, tgt):
    out = []
    for d, g in p.groupby("date"):
        g = g[[sig, tgt]].dropna()
        out.append((d, g[sig].rank().corr(g[tgt].rank()) if len(g) >= 8 and g[sig].nunique() > 1 else np.nan))
    return pd.Series(dict(out)).sort_index()


def run(p, H, lag):
    """H1 y H2 con coeficientes estimados en desarrollo (fechas <= 2022-12-31) y congelados."""
    y = f"y{H}"
    p = p.copy()
    p["r_y"] = p.groupby("date")[y].transform(crank)
    dev = p[p.date <= DEV_END]
    X = lambda q, cols: q[["r_" + c for c in cols]].to_numpy(float)
    beta = ols(X(dev, CTRL), dev["r_dP"].to_numpy(float))
    p["resid"] = p["r_dP"] - X(p, CTRL) @ beta
    b_base = ols(X(dev, CTRL), dev["r_y"].to_numpy(float))
    b_full = ols(X(dev, CTRL + ["dP"]), dev["r_y"].to_numpy(float))
    p["pred_base"] = X(p, CTRL) @ b_base
    p["pred_full"] = X(p, CTRL + ["dP"]) @ b_full
    ic1 = ic_by_date(p, "resid", y)
    icb = ic_by_date(p, "pred_base", y)
    icf = ic_by_date(p, "pred_full", y)
    diff = icf - icb
    res = {"beta_resid": beta.round(4).tolist(), "beta_base": b_base.round(4).tolist(), "beta_full": b_full.round(4).tolist()}
    for per, msk in (("dev", ic1.index <= DEV_END), ("test", ic1.index >= TEST_START)):
        res[per] = {"H1": nw(ic1[msk].values, lag), "H2_diff": nw(diff[msk].values, lag),
                    "H2_base_ic": nw(icb[msk].values, lag), "H2_full_ic": nw(icf[msk].values, lag)}
    return res, p, ic1, diff


def main():
    p0 = pd.read_parquet(os.path.join(W, "panel.parquet"))
    p0["date"] = pd.to_datetime(p0.date)
    out = {}
    p = prepare(p0, 0.85)
    out["sample"] = {"dates_dev": int((p.date.drop_duplicates() <= DEV_END).sum()),
                     "dates_test": int((p.date.drop_duplicates() >= TEST_START).sum()),
                     "sectors_per_date_test": p[p.date >= TEST_START].groupby("date").size().describe().round(2).to_dict(),
                     "sector_dates": p.groupby("sector").size().to_dict()}

    # ── primario H=20 y horizontes secundarios ──
    for H, (lag, lag2) in LAGS.items():
        r, pp, ic1, diff = run(p, H, lag)
        r["sens_lag"] = {"lag": lag2, "test_H1": nw(ic1[ic1.index >= TEST_START].values, lag2),
                         "test_H2": nw(diff[diff.index >= TEST_START].values, lag2)}
        out[f"H{H}"] = r
        if H == 20:
            p20, ic20, diff20 = pp, ic1, diff
    # rejillas no solapadas (H=20): una fecha de cada cuatro, 4 desplazamientos
    t_ic, t_diff = ic20[ic20.index >= TEST_START], diff20[diff20.index >= TEST_START]
    out["H20"]["non_overlap"] = [{"offset": k, "H1_mean": float(np.nanmean(t_ic.values[k::4])),
                                  "H1_n": int(np.sum(~np.isnan(t_ic.values[k::4]))),
                                  "H2_diff_mean": float(np.nanmean(t_diff.values[k::4]))} for k in range(4)]

    # ── exclusión de cada sector ──
    loo = {}
    for s in sorted(p0.sector.unique()):
        ps = prepare(p0, 0.85, drop=s)
        r, *_ = run(ps, 20, 4)
        loo[s] = {"H1_test": r["test"]["H1"], "H2_diff_test": r["test"]["H2_diff"]}
    out["leave_one_sector_out"] = loo

    # ── sensibilidad umbral 80 % ──
    r80, *_ = run(prepare(p0, 0.80), 20, 4)
    out["threshold_80"] = {"dev": r80["dev"], "test": r80["test"]}

    # ── referencias (H=20) ──
    refs = {}
    rng = np.random.default_rng(7)
    p20["random"] = rng.normal(size=len(p20))
    for sig in ["r_RS21", "r_RS63", "r_dRS21", "r_dP", "r_d_above50", "r_ew_minus_etf21", "random"]:
        ic = ic_by_date(p20, sig, "y20")
        refs[sig] = {"dev": nw(ic[ic.index <= DEV_END].values, 4), "test": nw(ic[ic.index >= TEST_START].values, 4)}
    out["references_H20"] = refs
    out["corr_rank_dP_controls"] = {c: float(p20["r_dP"].corr(p20["r_" + c])) for c in CTRL}

    # ── lectura económica: 3 primeros − 3 últimos por residuo, con 0,1 % por cambio ──
    rows, prev_top, prev_bot = [], set(), set()
    for d, g in p20.dropna(subset=["resid", "y20"]).groupby("date"):
        g = g.sort_values("resid")
        bot, top = set(g.sector.head(3)), set(g.sector.tail(3))
        cost = 0.001 * (len(top - prev_top) / 3 + len(bot - prev_bot) / 3) if prev_top else 0.002
        rows.append({"date": d, "spread": g.y20.tail(3).mean() - g.y20.head(3).mean() - cost,
                     "bull": bool(g.spy_above_sma200.iloc[0])})
        prev_top, prev_bot = top, bot
    sp = pd.DataFrame(rows).set_index("date")
    st = sp[sp.index >= TEST_START]
    out["spread_top3_bottom3_H20"] = {
        "dev": nw(sp[sp.index <= DEV_END].spread.values, 4), "test": nw(st.spread.values, 4),
        "test_by_year": {int(y): float(g.spread.mean()) for y, g in st.groupby(st.index.year)},
        "by_regime": {f"{per} {'SPY>SMA200' if b else 'SPY<SMA200'}": float(g.spread.mean())
                      for per, q in (("dev", sp[sp.index <= DEV_END]), ("test", st)) for b, g in q.groupby("bull")}}

    # ── transiciones de liderazgo (descriptivo) ──
    out["transitions"] = transitions(p20)

    # ── clasificación ──
    t = out["H20"]["test"]; dv = out["H20"]["dev"]
    c1 = t["H1"]["mean"] > 0 and (t["H1"]["t"] or 0) >= 2
    c2 = t["H2_diff"]["mean"] > 0 and (t["H2_diff"]["t"] or 0) >= 2
    c3 = np.sign(dv["H1"]["mean"]) == np.sign(t["H1"]["mean"]) and np.sign(dv["H2_diff"]["mean"]) == np.sign(t["H2_diff"]["mean"])
    c4 = all(v["H1_test"]["mean"] > 0 and (v["H1_test"]["t"] or 0) >= 1.5 for v in loo.values())
    sl = out["H20"]["sens_lag"]
    c5 = ((sl["test_H1"]["t"] or 0) >= 2 and (sl["test_H2"]["t"] or 0) >= 2
          and all(g["H1_mean"] > 0 and g["H2_diff_mean"] > 0 for g in out["H20"]["non_overlap"]))
    yrs = out["spread_top3_bottom3_H20"]["test_by_year"]
    c6 = out["spread_top3_bottom3_H20"]["test"]["mean"] > 0 and sum(v > 0 for v in yrs.values()) >= 3
    upper = t["H1"]["mean"] + 1.96 * t["H1"]["se"]
    lower = t["H1"]["mean"] - 1.96 * t["H1"]["se"]
    amb_bad = sum(v > 0.05 for v in p20[p20.date >= TEST_START].groupby("sector").ambiguous_share.mean())
    data_inconclusive = out["sample"]["dates_test"] < 150 or amb_bad > 2
    if data_inconclusive:
        verdict = "INCONCLUYENTE (datos)"
    elif c1 and c2 and c3 and c4 and c5 and c6:
        verdict = "VALIDADO"
    elif upper < EMI:
        verdict = "NO SOPORTADO"
    else:
        verdict = "INCONCLUYENTE"
    out["verdict"] = {"verdict": verdict, "c1_H1": bool(c1), "c2_H2": bool(c2), "c3_same_sign_dev": bool(c3),
                      "c4_leave_one_out": bool(c4), "c5_temporal_sensitivity": bool(c5), "c6_spread": bool(c6),
                      "H1_test_ci95": [round(lower, 4), round(upper, 4)], "EMI": EMI}
    json.dump(out, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(out["verdict"], indent=1))


def transitions(p20):
    ed = pd.read_parquet(os.path.join(W, "etf_daily.parquet"))
    eo = pd.read_parquet(os.path.join(W, "etf_open_daily.parquet"))
    etfs = [c for c in ed.columns if c != "SPY"]
    rs63 = ed[etfs].div(ed[etfs].shift(63)).sub(ed["SPY"] / ed["SPY"].shift(63), axis=0)
    rs63.loc[rs63.index < pd.Timestamp("2018-10-01"), "XLC"] = np.nan
    rank = rs63.rank(axis=1, ascending=False)
    nvalid = rs63.notna().sum(axis=1)
    cal = ed.index
    idx = {d: i for i, d in enumerate(cal)}
    events = []
    for e in etfs:
        r = rank[e].values; nv = nvalid.values
        for i in range(20, len(cal) - 20):
            if cal[i] < pd.Timestamp("2019-01-01") or np.isnan(r[i]):
                continue
            if r[i] <= 3 and not (r[i - 1] <= 3) and all(r[i - k] >= 6 for k in range(1, 21) if not np.isnan(r[i - k])):
                events.append((e, i, int(np.sum(r[i + 1:i + 21] <= 3) >= 15)))
    ev_df = pd.DataFrame(events, columns=["etf", "i", "consolidated"])
    meth = {}
    p = p20.copy()
    p["random"] = np.random.default_rng(11).normal(size=len(p))
    for name, col in (("residuo_dP", "resid"), ("dRS21_ETF", "dRS21"), ("RS21_ETF", "RS21"), ("azar", "random")):
        flags = []
        for d, g in p.groupby("date"):
            for etf in g.sort_values(col).etf.tail(3):
                flags.append((etf, idx[d]))
        fl = pd.DataFrame(flags, columns=["etf", "i"])
        res = {}
        for per, lo, hi in (("dev", "2019-01-01", "2022-12-31"), ("test", "2023-01-01", "2026-12-31")):
            evp = ev_df[(ev_df.consolidated == 1) & ev_df.i.map(lambda i: lo <= str(cal[i].date()) <= hi)]
            cov, leads = 0, []
            for e, i, _ in evp.itertuples(index=False):
                prior = fl[(fl.etf == e) & (fl.i >= i - 40) & (fl.i <= i - 1)]
                if len(prior):
                    cov += 1; leads.append(i - prior.i.min())
            flp = fl[fl.i.map(lambda i: lo <= str(cal[i].date()) <= hi)]
            prec, pre, post20 = [], [], []
            cons = ev_df[ev_df.consolidated == 1]
            for e, i in flp.itertuples(index=False):
                prec.append(bool(((cons.etf == e) & (cons.i >= i + 1) & (cons.i <= i + 40)).any()))
                pre.append(ed[e].iat[i] / ed[e].iat[i - 20] - ed["SPY"].iat[i] / ed["SPY"].iat[i - 20])
                if i + 20 < len(cal):
                    post20.append(ed[e].iat[i + 20] / eo[e].iat[i + 1] - ed["SPY"].iat[i + 20] / eo["SPY"].iat[i + 1])
            res[per] = {"consolidated_transitions": int(len(evp)), "coverage": cov / len(evp) if len(evp) else None,
                        "median_lead_sessions": float(np.median(leads)) if leads else None,
                        "precision": float(np.mean(prec)) if prec else None, "n_flags": len(prec),
                        "median_excess_prior_20": float(np.nanmedian(pre) * 100) if pre else None,
                        "mean_excess_next_20": float(np.nanmean(post20) * 100) if post20 else None}
        meth[name] = res
    return {"n_events": int(len(ev_df)), "n_consolidated": int(ev_df.consolidated.sum()), "methods": meth}


if __name__ == "__main__":
    main()
