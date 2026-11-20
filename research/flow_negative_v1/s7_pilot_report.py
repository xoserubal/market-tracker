"""Enmienda 2 §3 — informe del piloto de acciones por clase (sin rendimientos posteriores: solo capitalización).

Para cada emisor del piloto: presentaciones leídas, con acciones por clase, clase de la serie identificada, filtro sin
mirar al futuro, y días «sin capitalización» del panel c1 (v4c1sic) que la cota inferior resolvería (≥ 10 000 M$).
Comprobación independiente: cuando la API companyconcept sí tiene un total sin dimensión, se compara con la suma de
clases del XBRL de la misma fecha.

Uso: FN_TAG=v4c1sic py -3 s7_pilot_report.py CIK [CIK ...]  →  data/enmienda2_pilot.json
"""
import json
import sys

import numpy as np
import pandas as pd

import fn_config as C
import s1_panel as P

PANEL = C.WORK / "panel_v4c1sic.parquet"


def main(ciks):
    p = pd.read_parquet(PANEL, columns=["key", "date", "cik", "size", "usable", "mcap_pit", "raw_close"])
    comp = pd.read_csv(C.WORK / "companies_v4c1sic.csv", dtype=str, keep_default_na=False).drop_duplicates("key").set_index("key")
    out = {}
    for cik in ciks:
        cik = str(int(cik))
        recs = json.loads((C.SEC / "xbrl_classes" / f"{cik}.json").read_text())
        n_sh = sum(1 for r in recs if r.get("shares"))
        n_multi = sum(1 for r in recs if len({x["class"] for x in r.get("shares", [])}) > 1)
        keys = sorted(set(p.loc[(p.cik == cik) & p.usable & (p["size"] == "unknown"), "key"]))
        res = {"filings": len(recs), "with_shares": n_sh, "with_multiple_classes": n_multi,
               "errors": sorted({r["error"] for r in recs if r.get("error")}), "series": {}}
        # comprobación con companyconcept (total sin dimensión) cuando existe
        cc = P.filings(cik)
        chk = []
        if cc is not None:
            for r in recs:
                tot = sum(x["val"] for x in r.get("shares", []) if x["class"] and not x["other_dims"])
                d = {x["date"] for x in r.get("shares", [])}
                m = cc[(cc.filed == r["filed"]) & cc.end.isin(d)]
                if tot and len(m):
                    chk.append(float(m.val.iat[0] / tot))
        res["companyconcept_total_vs_sum_of_classes"] = {"n": len(chk), "ratios": [round(x, 4) for x in chk[:12]]}
        for k in keys:
            r = comp.loc[k] if k in comp.index else None
            syms = set(str(r.symbols).split("|")) | {str(r.ticker)} if r is not None else {k.split("__")[0]}
            g, info = P.own_class_filings(cik, syms)
            u = p[(p.key == k) & p.usable & (p["size"] == "unknown")]
            s = {"unknown_days": int(len(u)), "unknown_days_dev_2018_2020": int((u.date <= "2020-12-31").sum()),
                 "class": info if g is None else "ok", "members": [] if g is None else info}
            if g is not None:
                ser = pd.read_parquet((P.SER_C1 if (P.SER_C1 / f"{k}.parquet").exists() else P.SER) / f"{k}.parquet")
                ser["adv20"] = ser.dollar_vol.rolling(20, min_periods=20).median()
                ser = ser.set_index("date")
                splits = json.loads(r.splits_list) if (r is not None and r.splits_list) else []

                def turnover_at(filed, shares):
                    w = ser[ser.index <= filed].tail(1)
                    if w.empty or not (w.adv20.iat[0] > 0):
                        return None
                    return float(w.adv20.iat[0] / (shares * w.raw_close.iat[0]))
                ok = P.clean_pit(g, splits, turnover_at)
                dates = u.date.to_numpy()
                close = ser.raw_close.reindex(dates).to_numpy()
                fl, _ = P.mcap_series(g, ok, splits, dates, close)
                s.update({"own_filings": int(len(g)), "own_filings_accepted": int(ok.sum()),
                          "floor_ge_10B_days": int(np.nansum(fl >= 10e9)),
                          "floor_lt_10B_days": int(np.nansum(fl < 10e9)), "floor_nan_days": int(np.isnan(fl).sum()),
                          "floor_bn_min_med_max": [round(float(np.nanmin(fl)) / 1e9, 1), round(float(np.nanmedian(fl)) / 1e9, 1),
                                                   round(float(np.nanmax(fl)) / 1e9, 1)] if np.isfinite(fl).any() else None})
            res["series"][k] = s
        out[cik] = res
        print(cik, json.dumps(res, ensure_ascii=False)[:900], flush=True)
    (C.PUB / "enmienda2_pilot.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
