"""Etapa 0 (v3) — descripción de la muestra por empresa y diagnóstico de H1. SIN rendimientos posteriores.

Salidas (en el repo, solo agregados): data/v3_sample.json, data/v3_h1_design.json, data/v3_h1_frozen_cuts.json,
data/v3_terminal.json; work/terminal_events_v3_full.csv (fuera del repo).
"""
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

import fn_config as C
import s0_terminal as T
from s0_coverage import calendar
from s0_series import load_ca

TAG = os.environ.get("FN_TAG", "v3")
SKIP_H1 = os.environ.get("FN_SKIP_H1") == "1"     # los cortes de H1 solo se recalculan tras validar el universo
DEV = ("2018-01-02", "2020-12-31")
TEST = ("2021-01-01", "2026-09-17")      # última señal con 40 sesiones de resultado
ZONES = [(-1e9, -30, "<-30"), (-30, -20, "[-30,-20)"), (-20, -15, "[-20,-15)"), (-15, -10, "[-15,-10)"),
         (-10, -5, "[-10,-5)"), (-5, 0, "[-5,0)"), (0, 1e9, ">=0")]


def zone(f):
    for lo, hi, n in ZONES:
        if lo <= f < hi:
            return n
    return None


def terminal(s):
    """Desenlace de las series del marco que terminan antes del final de los datos (incluye las prolongadas)."""
    ca = load_ca()
    ch = pd.read_csv(C.PUB / "changes.csv", dtype=str)
    ch["date"] = pd.to_datetime(ch.date)
    ch["reason"] = ch.reason.fillna("")      # cambios sin motivo registrado
    cm = pd.read_csv(C.SEC / "cik_map.csv", dtype=str, keep_default_na=False)
    cik_of = {k: c for k, c in zip(cm.key, cm.cik) if c}
    for k in s.req_key.unique():
        if k.endswith("x") and k[:-1] in cik_of:
            cik_of[k] = cik_of[k[:-1]]
    by_cik = defaultdict(list)
    for k, c in cik_of.items():
        by_cik[c].append(k)
    allsum = s.copy()
    out = []
    for key, r in s[(s.terminated == "True") & s.frame_entry.notna()].iterrows():
        rr = dict(r)
        rr["key"] = key
        cat, val, src, det = T.classify(rr, ca, ch, cik_of, by_cik, allsum)
        lc = float(r.last_close_raw)
        st = "conocido" if val is not None else ("no_aplica" if cat == "cambio_ticker" else "desconocido")
        if val is not None and val > 0 and lc > 0 and abs(np.log(lc / val)) > T.TERMS_TOL:
            st = "terminos_incoherentes"
        out.append({"key": key, "company": r.company, "end": r.end, "year": r.end[:4], "category": cat,
                    "source": src, "value_status": st, "last_close": lc, "terminal_value": val})
    return pd.DataFrame(out)


def episodes(g, X, gap=10):
    """Primera entrada bajo X tras >= gap sesiones sin estar por debajo (solo días utilizables)."""
    n = 0
    f, pp = g.flow.to_numpy(), g.pos.to_numpy()
    last = -10 ** 9
    for i in range(len(f)):
        if f[i] < X:
            if pp[i] - last > gap:
                n += 1
            last = pp[i]
    return n


def main():
    cal = calendar()
    cpos = {d: i for i, d in enumerate(cal)}
    s = pd.read_csv(C.WORK / f"companies_{TAG}.csv", dtype=str, keep_default_na=False).set_index("key")
    s["frame_entry"] = s.frame_entry.replace("", np.nan)
    p = pd.read_parquet(C.WORK / f"panel_{TAG}.parquet")
    # memoria: textos repetidos como categoría y columnas auxiliares en float32. flow, R, w1 y m1 siguen en float64
    # (los cortes de H1 se calculan con ellas y no deben cambiar por redondeo)
    for c in ("mcap_pit", "mcap_retro", "adv20", "spread_ar21", "turnover", "raw_close"):
        if c in p:
            p[c] = p[c].astype("float32")
    for c in ("key", "cik", "sector", "idx_now", "size", "size_retro", "liq", "year", "series_end",
              "future_event_40"):
        if c in p:
            p[c] = p[c].astype("category")
    p["pos"] = p.date.map(cpos)
    p["period"] = np.where(p.date <= DEV[1], "dev", np.where(p.date <= TEST[1], "test", "post"))
    res = {"note": "Etapa 0 v3: agregados sin ningún rendimiento posterior a una señal."}

    # ---------- muestra
    links = pd.read_csv(C.WORK / f"company_links_{TAG}.csv")
    fr = s[s.frame_entry.notna()]
    first_idx = {}
    mem = pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False)
    comp_tickers = defaultdict(set)
    for k, r in fr.iterrows():
        comp_tickers[r.company] |= set(r.symbols.split("|")) | {r.ticker}
    res["sample"] = {
        "series_total": int(len(s)), "series_in_frame": int(len(fr)),
        "series_never_member_in_epoch": int(s.frame_entry.isna().sum()),
        "companies_in_frame": int(fr.company.nunique()),
        "companies_in_panel_2018plus": int(p.company.nunique()),
        "dedup_links": links.tipo.value_counts().to_dict(),
        "extended_after_index_exit": int(fr.ext.astype(str).eq("True").sum()),
        "obs_total": int(len(p)), "obs_usable": int(p.usable.sum()),
        "by_year": {y: {"obs": int(len(g)), "companies": int(g.company.nunique()),
                        "usable_pct": round(100 * g.usable.mean(), 1),
                        "ex_member_pct": round(100 * (g.idx_now == "ex").mean(), 1),
                        "mcap_pct": round(100 * g.mcap_pit.notna().mean(), 1),
                        "sector_pct": round(100 * (g.sector != "").mean(), 1),
                        "idx_now": g.idx_now.value_counts(normalize=True).round(3).to_dict()}
                    for y, g in p.groupby("year")},
    }
    u = p[p.usable & (p.period != "post")]
    res["size_liquidity"] = {
        per: {"size": g["size"].value_counts().to_dict(),
              "liq": g.liq.value_counts().to_dict(),
              "size_x_liq_pct": (pd.crosstab(g["size"], g.liq, normalize="all") * 100).round(2).to_dict(),
              "companies_by_size": g.groupby("size").company.nunique().to_dict(),
              "idx_now_by_size_pct": (pd.crosstab(g["size"], g.idx_now, normalize="index") * 100).round(1).to_dict(),
              "turnover_median_by_size": g.groupby("size").turnover.median().round(5).to_dict(),
              "mcap_median_by_size_musd": (g.groupby("size").mcap_pit.median() / 1e6).round(0).to_dict()}
        for per, g in u.groupby("period")}
    res["size_pit_vs_retro"] = {"agree_pct": round(100 * (p["size"] == p.size_retro).mean(), 3),
                                "shares_cleaning": json.load(open(C.PUB / f"{TAG}_shares_cleaning.json")),
                                "cik_conflict_obs_pct": round(100 * p.cik_conflict.mean(), 3)}
    res["sector_source_pct"] = (p.sector_src.replace("", "sin_sector").value_counts(normalize=True) * 100) \
        .round(2).to_dict()
    # spread estimado (Abdi-Ranaldo) frente a los costes supuestos
    res["spread_ar21_median_pct_by_size_year"] = (u.groupby(["size", "year"]).spread_ar21.median() * 100) \
        .round(3).unstack().to_dict("index")
    res["spread_ar21_median_pct_by_liq"] = (u.groupby("liq").spread_ar21.median() * 100).round(3).to_dict()

    # ---------- Flow negativo
    uz = u.copy()
    uz["zone"] = uz.flow.map(zone)
    neg = uz[uz.flow < 0]
    res["flow_negative"] = {
        per: {"days": int(len(g)), "pct_of_usable": round(100 * len(g) / max(1, len(uz[uz.period == per])), 1),
              "zones": g.zone.value_counts().to_dict(),
              "zone_x_size": pd.crosstab(g.zone, g["size"]).to_dict(),
              "zone_x_liq": pd.crosstab(g.zone, g.liq).to_dict(),
              "operable_pct_by_zone": (g.groupby("zone").operable.mean() * 100).round(1).to_dict(),
              "operable_pct_by_size": (g.groupby("size").operable.mean() * 100).round(1).to_dict(),
              "excluded_by_filter": {"price_lt_3_pct": round(100 * (g.raw_close < 3).mean(), 2),
                                     "adv_lt_1M_pct": round(100 * (g.adv20 < 1e6).mean(), 2),
                                     "adv_missing_pct": round(100 * g.adv20.isna().mean(), 2)}}
        for per, g in neg.groupby("period")}
    epi = defaultdict(int)
    epi_size = defaultdict(int)
    for (per, cid), g in u.sort_values("date").groupby(["period", "company"]):
        sz = g["size"].iat[0]
        for X in (-10, -20, -30):
            n = episodes(g, X)
            epi[f"{per} X={X}"] += n
    for (per, sz), g in u.groupby(["period", "size"]):
        for X in (-10, -20, -30):
            epi_size[f"{per} {sz} X={X}"] = sum(episodes(h, X) for _, h in g.sort_values("date").groupby("company"))
    res["episodes"] = dict(epi)
    res["episodes_by_size_at_obs"] = dict(epi_size)
    res["future_event_within_40_pct_of_negative"] = round(100 * (neg.future_event_40 != "").mean(), 3)
    json.dump(res, open(C.PUB / f"{TAG}_sample.json", "w"), indent=1, default=str)
    print(json.dumps({k: res[k] for k in ("sample", "episodes")}, indent=1, default=str)[:4000])

    # ---------- desenlaces
    t = terminal(s)
    t.to_csv(C.WORK / f"terminal_events_{TAG}_full.csv", index=False)
    t.drop(columns=["last_close", "terminal_value"]).to_csv(C.PUB / f"terminal_events_{TAG}.csv", index=False)
    tv = {"series_terminated_in_frame": int(len(t)),
          "by_category_status": t.groupby(["category", "value_status"]).size().unstack(fill_value=0).to_dict("index"),
          "status_by_year": t.groupby(["year", "value_status"]).size().unstack(fill_value=0).to_dict("index")}
    # señales negativas afectadas por un fin de serie de valor desconocido en las 40 sesiones siguientes
    unk = t[t.value_status.isin(["desconocido", "terminos_incoherentes"])]
    endpos = {k: cpos.get(e) for k, e in zip(unk.key, unk.end)}
    aff = neg[neg.key.isin(endpos)]
    ep = aff.key.map(endpos)
    hit = (ep > aff.pos) & (ep <= aff.pos + 40)
    tv["negative_days_unknown_outcome_40"] = {per: round(100 * hit[g.index].sum() / max(1, (neg.period == per).sum()),
                                                         3) for per, g in aff.groupby("period")}
    tv["negative_days_unknown_outcome_40_by_zone"] = {f"{a} {b}": int(n) for (a, b), n in aff[hit].groupby(["period", "zone"]).size().items()}
    json.dump(tv, open(C.PUB / f"{TAG}_terminal.json", "w"), indent=1, default=str)
    print(json.dumps(tv, indent=1, default=str)[:3000])

    # ---------- H1 en desarrollo
    if SKIP_H1:
        print("H1 omitido (FN_SKIP_H1=1)")
        return
    d = neg[neg.period == "dev"].dropna(subset=["w1", "m1", "R"])
    qw = np.quantile(d.w1, [.2, .4, .6, .8]).tolist()
    qm = np.quantile(d.m1, [.2, .4, .6, .8]).tolist()
    d = d.assign(cw=np.searchsorted(qw, d.w1, side="right"), cm=np.searchsorted(qm, d.m1, side="right"))
    d["cell"] = d.cw.astype(str) + d.cm.astype(str)
    cells = {}
    for c, g in d.groupby("cell"):
        top = g.company.value_counts()
        run = (g.sort_values(["company", "pos"]).groupby("company").pos.diff() == 1).mean()
        cells[c] = {"n": int(len(g)), "companies": int(top.size), "top_company_share": round(float(top.iat[0] / len(g)), 4),
                    "hhi": round(float(((top / len(g)) ** 2).sum()), 5), "consecutive_day_share": round(float(run), 3),
                    "months": int(g.date.str[:7].nunique()),
                    "w1_sd": round(float(g.w1.std()), 2), "m1_sd": round(float(g.m1.std()), 2),
                    "R_c1": float(np.quantile(g.R, 1 / 3)), "R_c2": float(np.quantile(g.R, 2 / 3)),
                    "size_mix": g["size"].value_counts(normalize=True).round(3).to_dict()}
    mon = d.date.str[:7]
    sizes = d.groupby([mon, d.cell]).size()
    X = np.column_stack([np.ones(len(d))] + [np.clip(d[v], d[v].quantile(.01), d[v].quantile(.99)) ** k
                                             for v in ("w1", "m1") for k in (1, 2, 3)] + [d.w1 * d.m1])
    beta, *_ = np.linalg.lstsq(X, d.R.to_numpy(), rcond=None)
    resid = d.R.to_numpy() - X @ beta
    h1 = {"dev": DEV, "n": int(len(d)), "companies": int(d.company.nunique()),
          "R_var_explained_by_returns": round(float(1 - resid.var() / d.R.var()), 3),
          "month_cells": {"cells": int(len(sizes)), "share_cells_ge30": round(float((sizes >= 30).mean()), 3),
                          "share_obs_in_cells_ge30": round(float(sizes[sizes >= 30].sum() / sizes.sum()), 4)},
          "cells_lt300": [c for c, v in cells.items() if v["n"] < 300],
          "cells_lt30_companies": [c for c, v in cells.items() if v["companies"] < 30],
          "max_top_company_share": max(v["top_company_share"] for v in cells.values()),
          "cells": cells}
    by_size = {}
    for sz, g in d.groupby("size"):
        sz_sizes = g.groupby([g.date.str[:7], g.cell]).size()
        by_size[sz] = {"n": int(len(g)), "companies": int(g.company.nunique()),
                       "share_obs_in_month_cells_ge30": round(float(sz_sizes[sz_sizes >= 30].sum() / sz_sizes.sum()), 3),
                       "cells_with_ge300": int((g.cell.value_counts() >= 300).sum())}
    h1["by_size"] = by_size
    json.dump(h1, open(C.PUB / f"{TAG}_h1_design.json", "w"), indent=1)
    json.dump({"dev": DEV, "population": "usable, Flow < 0, marco por empresa (todas las tallas)",
               "w1_breaks": qw, "m1_breaks": qm,
               "R_tercile_cuts_by_cell": {c: {"n": v["n"], "c1": v["R_c1"], "c2": v["R_c2"]}
                                          for c, v in cells.items()}},
              open(C.PUB / f"{TAG}_h1_frozen_cuts.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in h1.items() if k != "cells"}, indent=1))


if __name__ == "__main__":
    main()
