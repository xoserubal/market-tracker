"""G2A — exploración descriptiva SIN resultados (G2A_PROTOCOLO §4, §6, §8).

Calcula, solo con variables con fecha <= t y sin ninguna rentabilidad posterior:
- la población base de C (condiciones 1, 3, 4, 5 + historia mínima + enmienda 7) y los k (q20/q35/q50 de RANGO_L);
- para cada una de las 12 combinaciones (L, k, θ): población elegible, umbral de AI (p66,7), episodios y episodios
  tratados por año (puerta 1 de muestra);
- distribuciones de las variables candidatas y su correlación (sin resultado);
- universo de A: valor-días con historia mínima por año.
Salida: MICRO_DATA_DIR/results/g2a_describe.json y features/g2a_episodes_c.parquet (episodios por combinación).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, outcomes, storage  # noqa: E402

LS, KQ, THETAS = (40, 120), (20, 35, 50), (0.80, 0.90)
GAP = 5


def load():
    root = storage.root()
    f = pd.read_parquet(root / "features" / "dev_features.parquet")
    f["entity"] = f["entity"].astype(str)
    md = pd.read_parquet(root / "results" / "g2a_coverage_entity_days.parquet",
                         columns=["entity", "date", "usable", "liq_tercile", "departed"])
    md["entity"] = md["entity"].astype(str)
    f = f.merge(md, on=["entity", "date"], how="inner")          # condición 1: miembro del S&P 500 en t
    f = f[f["date"] <= outcomes.DEV_LAST_DECISION]
    return root, f


def base_mask(f):
    """Condiciones 1 (por el merge), 3, 4 y 5, historia mínima (usable) y sin evento (enmienda 7)."""
    return (f["usable"] & ~f["excluded_event"] & (f["rs63_spy"] <= 0) & (~f["high252_last20"].astype(bool))
            & (f["flow"] < 4) & (f["ef"] < 7))


def episodes(g, pos):
    """g: filas elegibles de un valor (ordenadas). Devuelve id de episodio: racha con huecos <= GAP sesiones."""
    p = np.array([pos[d] for d in g["date"]])
    brk = np.r_[True, np.diff(p) > GAP + 1]
    return np.cumsum(brk)


def main():
    root, f = load()
    days = calendar.trading_days("2016-01-04", "2021-12-31")
    pos = {d: i for i, d in enumerate(days)}
    f["year"] = f["date"].str[:4]
    out = {"member_days": int(len(f))}
    base = base_mask(f)
    out["base_population"] = {"n": int(base.sum()), "by_year": f[base].groupby("year").size().to_dict(),
                              "cond_counts": {"usable": int(f["usable"].sum()),
                                              "no_event": int((f["usable"] & ~f["excluded_event"]).sum()),
                                              "rs63_spy<=0": int((f["usable"] & ~f["excluded_event"] & (f["rs63_spy"] <= 0)).sum()),
                                              "no_high252_20": int((f["usable"] & ~f["excluded_event"] & (f["rs63_spy"] <= 0)
                                                                    & ~f["high252_last20"].astype(bool)).sum()),
                                              "flow_ef": int(base.sum())},
                              "departed_share": round(float(f.loc[base, "departed"].mean()), 4)}
    kv = {}
    for L in LS:
        r = f.loc[base, f"range_{L}"].dropna()
        kv[L] = {q: float(np.percentile(r, q)) for q in KQ}
    out["k_values"] = {str(L): {f"q{q}": round(v, 4) for q, v in kv[L].items()} for L in LS}

    combos, eps_all = {}, []
    for L in LS:
        for q in KQ:
            k = kv[L][q]
            for th in THETAS:
                tag = f"L{L}_k{q}_t{int(th * 100)}"
                ai = f"ai_{L}_{int(th * 100)}"
                el = base & (f[f"range_{L}"] <= k) & f[ai].notna()
                e = f.loc[el, ["entity", "date", "year", ai, f"range_{L}", "liq_tercile", "sector"]].sort_values(
                    ["entity", "date"]).copy()
                thr = float(np.percentile(e[ai], 100 * 2 / 3))
                e["ep"] = 0
                for ent, idx in e.groupby("entity").indices.items():
                    e.iloc[idx, e.columns.get_loc("ep")] = episodes(e.iloc[idx], pos)
                e["treat"] = e[ai] >= thr
                ep = e.groupby(["entity", "ep"])
                first_t = e[e["treat"]].groupby(["entity", "ep"]).head(1)
                n_ep = ep.ngroups
                tr = first_t.groupby("year").size()
                combos[tag] = {"k": round(k, 4), "ai_threshold_p66_7": round(thr, 4), "eligible_rows": int(len(e)),
                               "episodes": int(n_ep), "treated_episodes": int(len(first_t)),
                               "treated_by_year": {y: int(tr.get(y, 0)) for y in ["2017", "2018", "2019", "2020", "2021"]},
                               "gate1_ge20_each_year": bool(all(tr.get(y, 0) >= 20 for y in ["2017", "2018", "2019", "2020", "2021"])),
                               "low_ai_rows_tercile1": int((e[ai] <= np.percentile(e[ai], 100 / 3)).sum()),
                               "median_episode_len": float(ep.size().median())}
                first_t = first_t.assign(combo=tag)
                eps_all.append(first_t[["combo", "entity", "date", "year", ai, f"range_{L}", "liq_tercile", "sector"]]
                               .rename(columns={ai: "ai", f"range_{L}": "range"}))
    out["combos_c"] = combos
    pd.concat(eps_all, ignore_index=True).to_parquet(root / "features" / "g2a_episodes_c.parquet")

    # distribuciones y correlaciones de las variables (sin resultado), en la población base
    cols = ["c1_40", "c2", "c3_80", "c3_90", "c4_40", "ai_40_80", "c1_120", "c4_120", "ai_120_80", "awd_d", "awd_i",
            "p_awd_d", "p_awd_i", "range_40", "range_120", "rs63_spy", "mom20", "ext_sma20_atr"]
    b = f.loc[base, cols]
    out["describe_base"] = b.describe(percentiles=[.05, .25, .5, .75, .95]).round(4).to_dict()
    out["spearman_base"] = b[["c1_40", "c2", "c3_80", "c4_40", "range_40", "rs63_spy", "mom20"]].corr("spearman").round(3).to_dict()

    # universo de A: miembros con historia mínima y sin evento
    a = f["usable"] & ~f["excluded_event"]
    out["universe_a"] = {"n": int(a.sum()), "by_year": f[a].groupby("year").size().to_dict(),
                         "dates": int(f.loc[a, "date"].nunique()),
                         "rs63_sector_is_spy_share": round(float(f.loc[a, "rs63_sector_is_spy"].mean()), 4),
                         "p_awd_d_nonnull": round(float(f.loc[a, "p_awd_d"].notna().mean()), 4),
                         "p_awd_i_nonnull": round(float(f.loc[a, "p_awd_i"].notna().mean()), 4)}
    (root / "results" / "g2a_describe.json").write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False),
                                                       encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("member_days", "base_population", "k_values", "universe_a")}, indent=1))
    print(pd.DataFrame(combos).T[["k", "ai_threshold_p66_7", "eligible_rows", "episodes", "treated_episodes",
                                  "treated_by_year", "gate1_ge20_each_year", "median_episode_len"]].to_string())


if __name__ == "__main__":
    main()
