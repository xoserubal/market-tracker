"""Validación del universo v4 (opción 2) frente a v3. Sin rendimientos posteriores.

Comprueba:
1. Que ninguna empresa entra en el marco antes del 17-dic-2019 solo por el S&P 600.
2. Cuántas empresas y días cambian por año (v3 → v4) y por qué vía entran.
3. S&P 400 2016-2020: miembros vigentes por día con la pertenencia de los ETF frente a los ~400 del índice.
4. Capitalización: valores absurdos y discrepancias con la versión retrospectiva, antes y después.
5. Supervivencia: parte de los días de 2018-2020 que corresponden a empresas que luego dejan de cotizar.
Salida: data/v4_validation.json.
"""
import json

import numpy as np
import pandas as pd

import fn_config as C

COLS = ["company", "key", "date", "idx_now", "usable", "flow", "mcap_pit", "mcap_retro", "size", "size_retro",
        "terminated"]


def load(tag):
    p = pd.read_parquet(C.WORK / f"panel_{tag}.parquet", columns=COLS)
    s = pd.read_csv(C.WORK / f"companies_{tag}.csv", dtype=str, keep_default_na=False)
    return p, s


def main():
    p3, s3 = load("v3")
    p4, s4 = load("v4")
    out = {}

    # 1. entradas por S&P 600 antes del corte
    mem = pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False)
    etf = pd.read_csv(C.PUB / "membership_etf_sp400.csv", dtype=str, keep_default_na=False)
    pre = p4[p4.date < "2019-12-17"]
    out["obs_before_2019-12-17_with_idx_sp600"] = int((pre.idx_now == "sp600").sum())

    # 2. por año
    by = {}
    for y in sorted(set(p3.date.str[:4]) | set(p4.date.str[:4])):
        a, b = p3[p3.date.str[:4] == y], p4[p4.date.str[:4] == y]
        ca, cb = set(a.company), set(b.company)
        by[y] = {"obs_v3": len(a), "obs_v4": len(b), "companies_v3": len(ca), "companies_v4": len(cb),
                 "companies_only_v3": len(ca - cb), "companies_only_v4": len(cb - ca),
                 "idx_now_v4": b.idx_now.value_counts().to_dict()}
    out["by_year"] = by
    ent3 = s3[s3.frame_entry != ""].groupby("company").frame_entry.min()
    ent4 = s4[s4.frame_entry != ""].groupby("company").frame_entry.min()
    j = pd.concat([ent3.rename("v3"), ent4.rename("v4")], axis=1)
    out["frame_entry_changes"] = {"companies_v3": int(ent3.size), "companies_v4": int(ent4.size),
                                  "same_entry": int((j.v3 == j.v4).sum()),
                                  "later_in_v4": int((j.v4 > j.v3).sum()), "earlier_in_v4": int((j.v4 < j.v3).sum()),
                                  "only_v3": int(j.v4.isna().sum()), "only_v4": int(j.v3.isna().sum())}

    # 3. S&P 400 vigente por día en 2016-2020 (fin de mes)
    days = p4[(p4.date >= "2016-01") & (p4.date < "2021-01")].date
    eom = sorted(days.groupby(days.str[:7]).max())
    cnt = {d: int(((p4.date == d) & (p4.idx_now == "sp400")).sum()) for d in eom}
    cnt3 = {d: int(((p3.date == d) & (p3.idx_now == "sp400")).sum()) for d in eom}
    out["sp400_members_in_panel_month_end"] = {"v4_min": min(cnt.values()), "v4_median": float(np.median(list(cnt.values()))),
                                               "v4_max": max(cnt.values()), "v3_median": float(np.median(list(cnt3.values()))),
                                               "etf_intervals": len(etf),
                                               "etf_intervals_status": etf.status.value_counts().to_dict()}

    # 4. capitalización
    def mc(p):
        b = p.dropna(subset=["mcap_pit", "mcap_retro"])
        r = np.abs(np.log(b.mcap_pit / b.mcap_retro))
        return {"obs_ge_1e15": int((p.mcap_pit >= 1e15).sum()), "obs_ge_5e12": int((p.mcap_pit >= 5e12).sum()),
                "companies_ge_5e12": sorted(p[p.mcap_pit >= 5e12].company.unique().tolist()),
                "pit_vs_retro_gt_10x_obs": int((r > np.log(10)).sum()),
                "pit_vs_retro_gt_10x_companies": int(b[r > np.log(10)].company.nunique()),
                "size_disagree_obs": int((p["size"] != p.size_retro).sum()),
                "mcap_coverage_pct": round(100 * p.mcap_pit.notna().mean(), 2)}
    out["mcap"] = {"v3": mc(p3), "v4": mc(p4)}
    shc = C.PUB / "v4_shares_cleaning.json"
    out["mcap"]["shares_cleaning_v4"] = json.load(open(shc)) if shc.exists() else None

    # 5. supervivencia en 2018-2020
    def surv(p):
        d = p[(p.date >= "2018") & (p.date < "2021") & p.usable]
        return {"usable_obs": len(d), "pct_obs_of_companies_that_later_stop_trading": round(100 * d.terminated.mean(), 2),
                "flow_neg_pct": round(100 * (d.flow < 0).mean(), 2),
                "flow_lt_-30_pct": round(100 * (d.flow < -30).mean(), 3)}
    out["dev_2018_2020"] = {"v3": surv(p3), "v4": surv(p4)}
    json.dump(out, open(C.PUB / "v4_validation.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != "by_year"}, indent=1, default=str))
    for y, v in by.items():
        print(y, {k: v[k] for k in ("obs_v3", "obs_v4", "companies_v3", "companies_v4", "companies_only_v3", "companies_only_v4")})


if __name__ == "__main__":
    main()
