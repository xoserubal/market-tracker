"""G2A — familia C (H-C1, H-C2): rejilla de 12, puertas, reality check, 1-ES y potencia (G2A_PROTOCOLO §3, §4, §6).
Solo desarrollo.

Por combinación (L, k, θ):
- elegibles: población base (condiciones 1, 3, 4, 5, historia, enmienda 7) con RANGO_L <= k y AI calculado;
- umbrales de AI: p66,7 (tratado) y p33,3 (control) de AI en los elegibles de desarrollo;
- episodios: rachas de fechas elegibles con huecos <= 5 sesiones; tratado = primera fecha del episodio con AI alto;
- controles: misma fecha, AI bajo, mismo tercil de liquidez; mismo sector si hay alguno, si no cualquiera (se marca);
  hasta 3 por Mahalanobis en (RANGO_L, duración, ln liquidez) con covarianza de los elegibles (enmienda 3);
- H-C1: Δ = Ex_tratado − media(Ex_controles) a 40 sesiones (bruto: tratado y controles comparten tercil y coste);
  secundario a 20; H-C2: ruptura del máximo de cierres del rango en t+1..t+40 sin volver en las 5 siguientes.
Reality check: AI permutado dentro de cada fecha con una clave aleatoria común por (fecha, valor), 200 veces; se
recalculan tratados, controles y criterio de las 12 y se guarda el máximo.
Salida: MICRO_DATA_DIR/results/g2a_select_c.json y features/g2a_c_matches.parquet (combinación elegida).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, distributions as D, outcomes, storage  # noqa: E402
import g2a_describe as GD  # noqa: E402

YEARS = ["2017", "2018", "2019", "2020", "2021"]
NPERM, SEED = 200, 20261116
Z, MDE_DEP = 2.394, 1.25     # z de α = 0,05/3 bilateral; factor por dependencia (§6)


def breakout_flags(root, f, L):
    """Ruptura (H-C2) por (entidad, fecha) con cierres ajustados por splits coherentes."""
    daily = pd.read_parquet(root / "reference" / "daily_ohlc_v2.parquet", columns=["entity", "date", "c", "filler"])
    daily["entity"] = daily["entity"].astype(str)
    daily = daily[~daily["filler"]].sort_values(["entity", "date"])
    applied = D.applied_splits_by_entity()
    need = f.groupby("entity")["date"].apply(set).to_dict()
    out = {}
    for e, g in daily.groupby("entity"):
        if e not in need:
            continue
        dates = g["date"].to_numpy()
        c = g["c"].to_numpy(float)
        fac = np.ones(len(c))
        for r in applied.get(e, pd.DataFrame(columns=["ex_date", "factor"])).itertuples():
            fac[dates < r.ex_date] *= r.factor
        c = c / fac
        rmax = pd.Series(c).rolling(L, min_periods=L).max().to_numpy()
        for i, d in enumerate(dates):
            if d not in need[e] or np.isnan(rmax[i]):
                continue
            fut = c[i + 1:i + 46]
            b = False
            for j in range(min(40, len(fut))):
                if fut[j] > rmax[i] and np.all(fut[j + 1:j + 6] > rmax[i]):
                    b = True
                    break
            out[(e, d)] = b
    return out


def prepare(root, f, L, k, th, pos):
    ai = f"ai_{L}_{int(th * 100)}"
    el = GD.base_mask(f) & (f[f"range_{L}"] <= k) & f[ai].notna()
    e = f.loc[el, ["entity", "date", ai, f"range_{L}", "liq_tercile", "liq60", "sector", "ex40", "ex20",
                   f"brk{L}"]].rename(columns={ai: "ai", f"range_{L}": "range", f"brk{L}": "brk"})
    e = e.sort_values(["entity", "date"]).reset_index(drop=True)
    ep = np.zeros(len(e), int)
    nxt = 0
    for ent, idx in e.groupby("entity").indices.items():
        ep[idx] = GD.episodes(e.iloc[idx], pos) + nxt
        nxt = ep[idx].max()
    e["ep"] = ep
    e["dur"] = e.groupby("ep").cumcount() + 1
    e["lnliq"] = np.log(e["liq60"])
    hi, lo = np.percentile(e["ai"], 100 * 2 / 3), np.percentile(e["ai"], 100 / 3)
    Z3 = e[["range", "dur", "lnliq"]].to_numpy(float)
    ok = np.isfinite(Z3).all(1)
    VI = np.linalg.inv(np.cov(Z3[ok].T))
    # vecinos ordenados por Mahalanobis dentro de (fecha, tercil): mismo sector y cualquier sector
    nbs, nba = [None] * len(e), [None] * len(e)
    for _, idx in e.groupby(["date", "liq_tercile"]).indices.items():
        z = Z3[idx]
        dmat = np.einsum("ij,jk,ik->i", (z[:, None, :] - z[None, :, :]).reshape(-1, 3), VI,
                         (z[:, None, :] - z[None, :, :]).reshape(-1, 3)).reshape(len(idx), len(idx))
        sec = e["sector"].to_numpy()[idx]
        for a in range(len(idx)):
            order = np.argsort(dmat[a], kind="stable")
            order = order[order != a]
            nba[idx[a]] = idx[order]
            nbs[idx[a]] = idx[order[sec[order] == sec[a]]]
    w = max(len(x) for x in nba)
    NBA = np.full((len(e), max(w, 1)), -1)
    NBS = np.full((len(e), max(w, 1)), -1)
    for i in range(len(e)):
        NBA[i, :len(nba[i])] = nba[i]
        NBS[i, :len(nbs[i])] = nbs[i]
    return e, hi, lo, NBS, NBA


def evaluate(e, ai, hi, lo, NBS, NBA, detail=False):
    ex = e["ex40"].to_numpy(float)
    epv = e["ep"].to_numpy()
    high = ai >= hi
    low = (ai <= lo) & np.isfinite(ex)
    cs = np.cumsum(high)
    start = np.r_[0, np.flatnonzero(np.diff(epv)) + 1]
    base = np.repeat(np.r_[0, cs[start[1:] - 1]], np.diff(np.r_[start, len(epv)]))
    tr = np.flatnonzero(high & (cs - base == 1) & np.isfinite(ex))

    def pick(NB):
        S = NB[tr]
        valid = (S >= 0) & low[np.where(S >= 0, S, 0)]
        sel = valid & (np.cumsum(valid, 1) <= 3)
        return S, sel

    Ss, sels = pick(NBS)
    Sa, sela = pick(NBA)
    use_s = sels.any(1)
    S = np.where(use_s[:, None], Ss, Sa)
    sel = np.where(use_s[:, None], sels, sela)
    nctl = sel.sum(1)
    keep = nctl > 0
    exs = np.where(sel, ex[np.where(S >= 0, S, 0)], 0.0)
    delta = ex[tr] - exs.sum(1) / np.maximum(nctl, 1)
    years = e["date"].to_numpy()[tr]
    d = pd.DataFrame({"row": tr, "date": years, "delta": delta, "nctl": nctl, "sector_relaxed": ~use_s})[keep]
    if not detail:
        return d
    return d, S[keep], sel[keep]


def stats(d):
    yr = d["date"].str[:4]
    yearly = {y: float(d.loc[yr == y, "delta"].mean()) for y in YEARS}
    n = {y: int((yr == y).sum()) for y in YEARS}
    e = d["delta"] - d["delta"].mean()
    g = e.groupby(d["date"].str[:7]).sum()
    return {"criterion_median_yearly": float(np.median(list(yearly.values()))), "yearly_delta": yearly,
            "treated_per_year": n, "pooled_mean_delta": float(d["delta"].mean()),
            "pooled_se_month_cluster": float(np.sqrt((g ** 2).sum()) / len(d)), "sd_delta": float(d["delta"].std()),
            "half_2017_2019": float(d.loc[yr <= "2019", "delta"].mean()),
            "half_2020_2021": float(d.loc[yr >= "2020", "delta"].mean()), "n_treated": int(len(d))}


def main():
    root, f = GD.load()
    o = pd.read_parquet(root / "features" / "dev_outcomes.parquet", columns=["entity", "date", "ex20", "ex40", "st40", "st20"])
    f = f.merge(o, on=["entity", "date"], how="left")
    f.loc[f["st40"] == "missing", "ex40"] = np.nan
    f.loc[f["st20"] == "missing", "ex20"] = np.nan
    outcomes.guard(f["date"].max())
    days = calendar.trading_days("2016-01-04", "2021-12-31")
    pos = {d: i for i, d in enumerate(days)}
    base = GD.base_mask(f)
    for L in GD.LS:
        br = breakout_flags(root, f[base], L)
        f[f"brk{L}"] = [br.get((e, d), np.nan) for e, d in zip(f["entity"], f["date"])]
    kv = {L: {q: float(np.percentile(f.loc[base, f"range_{L}"].dropna(), q)) for q in GD.KQ} for L in GD.LS}
    combos = [(L, q, th) for L in GD.LS for q in GD.KQ for th in GD.THETAS]
    prep, res = {}, {}
    for L, q, th in combos:
        tag = f"L{L}_k{q}_t{int(th * 100)}"
        e, hi, lo, NBS, NBA = prepare(root, f, L, kv[L][q], th, pos)
        prep[tag] = (e, hi, lo, NBS, NBA)
        d = evaluate(e, e["ai"].to_numpy(float), hi, lo, NBS, NBA)
        r = stats(d)
        r.update({"L": L, "kq": q, "k": kv[L][q], "theta": th, "ai_hi": hi, "ai_lo": lo,
                  "share_sector_relaxed": float(d["sector_relaxed"].mean()), "share_lt3_controls": float((d["nctl"] < 3).mean())})
        res[tag] = r
        print(tag, round(r["criterion_median_yearly"], 5), r["n_treated"], flush=True)
    for tag, r in res.items():
        r["gate1_sample"] = all(n >= 20 for n in r["treated_per_year"].values())
        r["gate2_stability"] = (sum(x > 0 for x in r["yearly_delta"].values()) >= 4 and r["half_2017_2019"] > 0
                                and r["half_2020_2021"] > 0)
        nb = [t for t in res if t != tag and sum([res[t]["L"] != r["L"], res[t]["kq"] != r["kq"], res[t]["theta"] != r["theta"]]) == 1]
        r["neighbors"] = nb
        r["gate3_neighbors"] = sum(res[t]["pooled_mean_delta"] > 0 for t in nb) >= len(nb) / 2
    # reality check
    rng = np.random.default_rng(SEED)
    all_rows = pd.concat([prep[t][0][["date", "entity"]] for t in prep]).drop_duplicates().reset_index(drop=True)
    rid = pd.Series(np.arange(len(all_rows)), index=pd.MultiIndex.from_frame(all_rows))
    aux = {}
    for tag, (e, *_r) in prep.items():
        aux[tag] = (rid.reindex(pd.MultiIndex.from_frame(e[["date", "entity"]])).to_numpy(),
                    list(e.groupby("date").indices.values()), e["ai"].to_numpy(float))
    perm_max = []
    for p in range(NPERM):
        key = rng.random(len(all_rows))
        crit = []
        for tag, (e, hi, lo, NBS, NBA) in prep.items():
            kid, groups, ai = aux[tag]
            kk = key[kid]
            newai = np.empty_like(ai)
            for idx in groups:
                newai[idx] = ai[idx][np.argsort(kk[idx])]
            d = evaluate(e, newai, hi, lo, NBS, NBA)
            yr = d["date"].str[:4]
            crit.append(np.median([d.loc[yr == y, "delta"].mean() for y in YEARS]))
        perm_max.append(max(crit))
        if p % 20 == 0:
            print("perm", p, flush=True)
    p95 = float(np.percentile(perm_max, 95))
    for tag, r in res.items():
        r["reality_check_p"] = float((np.array(perm_max) >= r["criterion_median_yearly"]).mean())
        r["gate4_reality_check"] = r["criterion_median_yearly"] > p95
        r["passes_all"] = all(r[g] for g in ("gate1_sample", "gate2_stability", "gate3_neighbors", "gate4_reality_check"))
    passing = {t: r for t, r in res.items() if r["passes_all"]}
    choice, power, chosen_detail = None, None, None
    if passing:
        best = max(passing, key=lambda t: passing[t]["criterion_median_yearly"])
        thr = passing[best]["criterion_median_yearly"] - passing[best]["pooled_se_month_cluster"]
        cand = [t for t in passing if passing[t]["criterion_median_yearly"] >= thr]
        cand.sort(key=lambda t: (-passing[t]["kq"], passing[t]["theta"], -passing[t]["L"]))
        ch = cand[0]
        choice = {"best": best, "one_se_threshold": thr, "candidates": cand, "chosen": ch}
        e, hi, lo, NBS, NBA = prep[ch]
        d, S, sel = evaluate(e, e["ai"].to_numpy(float), hi, lo, NBS, NBA, detail=True)
        ex20, brk = e["ex20"].to_numpy(float), e["brk"].to_numpy(float)
        rows = np.where(S >= 0, S, 0)
        c20 = np.where(sel, ex20[rows], np.nan)
        cb = np.where(sel, brk[rows], np.nan)
        d["delta20"] = ex20[d["row"]] - np.nanmean(c20, 1)
        d["brk_tr"] = brk[d["row"]]
        d["brk_ctl"] = np.nanmean(cb, 1)
        d["c2_effect"] = d["brk_tr"] - d["brk_ctl"]
        excl = 1 - f.loc[f["date"] <= outcomes.DEV_LAST_DECISION, "excluded_event"].mean()
        per_year = d.groupby(d["date"].str[:4]).size().mean()
        n_proj = per_year * 4.7 * excl
        sd = float(d["delta"].std())
        mde = (Z + 0.84) * sd / np.sqrt(n_proj) * MDE_DEP
        sd2 = float(d["c2_effect"].std())
        power = {"treated_per_year_dev": float(per_year), "n_projected_test": float(n_proj), "sd_delta": sd,
                 "mde_hc1_pp": float(100 * mde),
                 "decision": "m=3 (H-C1 y H-C2)" if mde <= 0.005 else ("m=2 (H-C1; H-C2 exploratoria)" if mde <= 0.010 else "consultar"),
                 "sd_c2_effect": sd2, "mde_hc2_pp": float(100 * (Z + 0.84) * sd2 / np.sqrt(n_proj) * MDE_DEP)}
        chosen_detail = {"hc1_40_pooled": float(d["delta"].mean()), "hc1_20_pooled": float(d["delta20"].mean()),
                         "hc2_pooled": float(d["c2_effect"].mean()), "p_brk_treated": float(d["brk_tr"].mean()),
                         "p_brk_controls": float(d["brk_ctl"].mean())}
        d.assign(entity=e["entity"].to_numpy()[d["row"]]).to_parquet(root / "features" / "g2a_c_matches.parquet")
    out = {"combos": res, "reality_check": {"n_perm": NPERM, "seed": SEED, "p95_of_max": p95,
                                            "perm_max_quantiles": np.percentile(perm_max, [50, 90, 95, 99]).tolist()},
           "choice": choice, "power": power, "chosen_detail": chosen_detail}
    (root / "results" / "g2a_select_c.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(pd.DataFrame(res).T[["criterion_median_yearly", "pooled_mean_delta", "pooled_se_month_cluster", "yearly_delta",
                               "gate2_stability", "gate3_neighbors", "reality_check_p", "passes_all"]].to_string())
    print(json.dumps({"choice": choice, "power": power, "chosen": chosen_detail, "p95": p95}, indent=1, default=str))


if __name__ == "__main__":
    main()
