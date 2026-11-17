"""G2A — familia A (H-A1): rejilla de 6, puertas, reality check y desempate 1-ES (G2A_PROTOCOLO §3-§4, §7). Solo
desarrollo.

- A_t = media de pct_120(AWD_d) en las w sesiones del valor hasta t (variante diaria o intradía).
- Residuo transversal por fecha, sobre rangos, de A_t frente a mom5, mom20, rs63 vs SPY, rs63 vs su ETF sectorial
  (enmienda 2), RV_t y (C − SMA20)/ATR.
- IC de Spearman entre el residuo y Ex a 10 sesiones neto de costes (0,2 %; 0,5 % en el tercil de liquidez más bajo;
  SPY 0,02 %), por fecha. Fechas no solapadas cada 10 sesiones desde la primera (desfase 0); los otros 9 se informan.
- Universo: miembros con historia mínima, sin evento (enmienda 7) y con resultado (exits liquidadas incluidas;
  'missing' fuera).
Salida: MICRO_DATA_DIR/results/g2a_select_a.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, outcomes, storage  # noqa: E402

WS, VARS = (1, 5, 10), ("d", "i")
YEARS = ["2017", "2018", "2019", "2020", "2021"]
NPERM, SEED = 200, 20261116
COST, COST_LOW, COST_SPY = 0.002, 0.005, 0.0002
CONTROLS = ["mom5", "mom20", "rs63_spy", "rs63_sector", "rv", "ext_sma20_atr"]


def load():
    root = storage.root()
    f = pd.read_parquet(root / "features" / "dev_features.parquet",
                        columns=["entity", "date", "p_awd_d", "p_awd_i", "excluded_event", "near_genuine_jump"] + CONTROLS)
    f["entity"] = f["entity"].astype(str)
    f = f.sort_values(["entity", "date"])
    for v in VARS:
        for w in WS:
            f[f"a_{v}{w}"] = f.groupby("entity")[f"p_awd_{v}"].transform(lambda s: s.rolling(w, min_periods=w).mean())
    md = pd.read_parquet(root / "results" / "g2a_coverage_entity_days.parquet",
                         columns=["entity", "date", "usable", "liq_tercile"])
    md["entity"] = md["entity"].astype(str)
    o = pd.read_parquet(root / "features" / "dev_outcomes.parquet", columns=["entity", "date", "r10", "spy10", "st10"])
    f = f.merge(md, on=["entity", "date"]).merge(o, on=["entity", "date"])
    f = f[(f["date"] <= outcomes.DEV_LAST_DECISION) & f["usable"] & ~f["excluded_event"] & (f["st10"] != "missing")]
    cost = np.where(f["liq_tercile"].astype(float) == 1, COST_LOW, COST)
    f["ex_net"] = (f["r10"] - cost) - (f["spy10"] - COST_SPY)
    return root, f


def rank_cols(m):
    return np.column_stack([rankdata(m[:, j]) for j in range(m.shape[1])])


def date_blocks(f, col):
    """Por fecha: rango de A, matriz aniquiladora de los controles en rangos, rango de Ex y entidades."""
    blocks = {}
    for d, g in f.groupby("date"):
        g = g.dropna(subset=[col, "ex_net"] + CONTROLS)
        if len(g) < 30:
            continue
        X = np.column_stack([np.ones(len(g)), rank_cols(g[CONTROLS].to_numpy(float))])
        Q, _ = np.linalg.qr(X)          # residuo = y − Q Qᵀ y (sin guardar la matriz n×n)
        blocks[d] = (rankdata(g[col].to_numpy(float)), Q, rankdata(g["ex_net"].to_numpy(float)), len(g),
                     g["entity"].to_numpy())
    return blocks


def resid(Q, y):
    return y - Q @ (Q.T @ y)


def ic_from(resid, rex):
    r = rankdata(resid)
    return float(np.corrcoef(r, rex)[0, 1])


FIRST = "2017-01-03"     # primera fecha de decisión del periodo de desarrollo (§3: cada 10 sesiones desde ella)


def nonoverlap(dates, cal_pos, offset):
    first = cal_pos[FIRST]
    return sorted(d for d in dates if (cal_pos[d] - first) % 10 == offset)


def clustered_se(ics: pd.Series):
    """Error estándar de la media con errores agrupados por mes."""
    e = ics - ics.mean()
    g = e.groupby(ics.index.str[:7]).sum()
    return float(np.sqrt((g ** 2).sum()) / len(ics))


def main():
    root, f = load()
    cal = calendar.trading_days("2016-01-04", "2021-12-31")
    cpos = {d: i for i, d in enumerate(cal)}
    combos = [(w, v) for w in WS for v in VARS]
    res, blocks_all = {}, {}
    sigma10 = f.groupby("date")["ex_net"].std().median()
    for w, v in combos:
        tag = f"w{w}_{v}"
        bl = date_blocks(f, f"a_{v}{w}")
        blocks_all[tag] = bl
        ic = pd.Series({d: ic_from(resid(b[1], b[0]), b[2]) for d, b in bl.items()}).sort_index()
        by_off = {}
        for off in range(10):
            ds = nonoverlap(list(ic.index), cpos, off)
            by_off[off] = ic.loc[ds]
        ic0 = by_off[0]
        yearly = {y: float(ic0[ic0.index.str[:4] == y].mean()) for y in YEARS}
        nyear = {y: int((ic0.index.str[:4] == y).sum()) for y in YEARS}
        res[tag] = {"w": w, "variant": v, "criterion_median_yearly": float(np.median(list(yearly.values()))),
                    "pooled_mean_ic": float(ic0.mean()), "pooled_se_month_cluster": clustered_se(ic0),
                    "n_dates": int(len(ic0)), "ic_sd": float(ic0.std()), "yearly_ic": yearly, "dates_per_year": nyear,
                    "half_2017_2019": float(ic0[ic0.index.str[:4] <= "2019"].mean()),
                    "half_2020_2021": float(ic0[ic0.index.str[:4] >= "2020"].mean()),
                    "offsets_pooled_mean": {o: round(float(s.mean()), 4) for o, s in by_off.items()},
                    "mean_n_per_date": float(np.mean([b[3] for b in bl.values()]))}
    # puertas 1-3
    for tag, r in res.items():
        r["gate1_sample"] = all(n >= 20 for n in r["dates_per_year"].values())
        r["gate2_stability"] = (sum(x > 0 for x in r["yearly_ic"].values()) >= 4 and r["half_2017_2019"] > 0
                                and r["half_2020_2021"] > 0)
        nb = [t for t in res if t != tag and ((res[t]["w"] == r["w"]) != (res[t]["variant"] == r["variant"]))]
        r["neighbors"] = nb
        r["gate3_neighbors"] = sum(res[t]["pooled_mean_ic"] > 0 for t in nb) >= len(nb) / 2
    # puerta 4: reality check. Misma permutación para las 6 combinaciones en cada fecha: una clave aleatoria por
    # (fecha, valor); cada combinación reordena sus valores de A según esa clave.
    rng = np.random.default_rng(SEED)
    sched = {tag: nonoverlap(list(bl), cpos, 0) for tag, bl in blocks_all.items()}
    all_d = sorted(set().union(*sched.values()))
    ents = {d: sorted(set().union(*[set(blocks_all[t][d][4]) for t in res if d in blocks_all[t]])) for d in all_d}
    perm_max = []
    for p in range(NPERM):
        keys = {d: dict(zip(ents[d], rng.random(len(ents[d])))) for d in all_d}
        crit = []
        for tag in res:
            ics = {}
            for d in sched[tag]:
                b = blocks_all[tag][d]
                k = np.array([keys[d][e] for e in b[4]])
                ics[d] = ic_from(resid(b[1], b[0][np.argsort(k)]), b[2])
            ic0 = pd.Series(ics)
            crit.append(np.median([ic0[ic0.index.str[:4] == y].mean() for y in YEARS]))
        perm_max.append(max(crit))
    p95 = float(np.percentile(perm_max, 95))
    for tag, r in res.items():
        r["reality_check_p"] = float((np.array(perm_max) >= r["criterion_median_yearly"]).mean())
        r["gate4_reality_check"] = r["criterion_median_yearly"] > p95
        r["passes_all"] = all(r[g] for g in ("gate1_sample", "gate2_stability", "gate3_neighbors", "gate4_reality_check"))
    # elección: 1-ES y orden de parsimonia (w mayor -> diaria antes que intradía)
    passing = {t: r for t, r in res.items() if r["passes_all"]}
    choice = None
    if passing:
        best = max(passing, key=lambda t: passing[t]["criterion_median_yearly"])
        thr = passing[best]["criterion_median_yearly"] - passing[best]["pooled_se_month_cluster"]
        cand = [t for t in passing if passing[t]["criterion_median_yearly"] >= thr]
        cand.sort(key=lambda t: (-passing[t]["w"], 0 if passing[t]["variant"] == "d" else 1))
        choice = {"best": best, "one_se_threshold": thr, "candidates": cand, "chosen": cand[0]}
    sd_ic = res[choice["chosen"]]["ic_sd"] if choice else float(np.median([r["ic_sd"] for r in res.values()]))
    power = {"sigma10_median_cross_sectional": float(sigma10),
             "break_even_ic": float(COST / (1.40 * sigma10)),
             "min_useful_ic": float(max(0.03, COST / (1.40 * sigma10))),
             "ic_sd_dev": sd_ic,
             "projected_test_dates": 118,
             "mde_ic": float((2.394 + 0.84) * sd_ic / np.sqrt(118))}
    out = {"combos": res, "reality_check": {"n_perm": NPERM, "seed": SEED, "p95_of_max": p95,
                                            "perm_max_quantiles": np.percentile(perm_max, [50, 90, 95, 99]).tolist()},
           "choice": choice, "power": power}
    (root / "results" / "g2a_select_a.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(pd.DataFrame(res).T[["criterion_median_yearly", "pooled_mean_ic", "pooled_se_month_cluster", "yearly_ic",
                               "gate1_sample", "gate2_stability", "gate3_neighbors", "reality_check_p",
                               "gate4_reality_check"]].to_string())
    print(json.dumps({"choice": choice, "power": power, "p95": p95}, indent=1, default=str))


if __name__ == "__main__":
    main()
