"""Enmienda 2 — comparación de la tanda 1: original, c1 (enmienda 1), c1j (c1 con la regla §7 de la enmienda 2) y c2
(c1j + capitalización de las empresas con varias clases). Solo desarrollo (2018-2020).

Salida: data/etapa1_tanda1c2_conciliacion.json
"""
import json

import numpy as np
import pandas as pd

import fn_config as C

VARS = [("orig", ""), ("c1", "c1"), ("c1j", "c1j"), ("c2", "c2")]
TARGET = ("large", -30, 20, "all")


def sel(sfx):
    return json.loads((C.PUB / f"etapa1_tanda1{sfx}_selection.json").read_text(encoding="utf-8"))


def tab(sfx):
    return json.loads((C.PUB / f"etapa1_tanda1{sfx}_tables.json").read_text(encoding="utf-8"))


def ckey(c):
    return f"{c['size']}|{c['X']}|{c['H']}|{c['regime']}"


def main():
    S = {n: {ckey(c): c for c in sel(s)["candidates"]} for n, s in VARS}
    out = {"variants": dict(VARS)}
    keys = list(S["orig"])
    cands = []
    for k in keys:
        row = {"cell": k}
        for n, _ in VARS:
            c = S[n].get(k)
            row[n] = None if c is None else {"n": c["n"], "weeks": c["weeks"], "x": c["x_daily_mean"], "t": c["t_nw"],
                                              "x_lo": c["x_lo"], "x_hi": c["x_hi"], "unk": c["unknown_share"],
                                              "eligible": c["eligible"],
                                              "failed": [a for a, b in c["criteria"].items() if not b]}
        cands.append(row)
    out["candidates"] = cands
    out["eligible"] = {n: [k for k in keys if S[n][k]["eligible"]] for n, _ in VARS}
    out["eligibility_changes"] = [r["cell"] for r in cands
                                  if len({r[n]["eligible"] for n, _ in VARS if r[n]}) > 1]
    dt = []
    for r in cands:
        a, b = r["c1"], r["c2"]
        if a and b and a["t"] == a["t"] and b["t"] == b["t"]:
            dt.append({"cell": r["cell"], "t_c1": a["t"], "t_c2": b["t"], "d": b["t"] - a["t"],
                       "n_c1": a["n"], "n_c2": b["n"]})
    dt.sort(key=lambda x: -abs(x["d"]))
    out["largest_t_changes_c1_to_c2"] = dt[:12]
    out["abs_t_ge_2_5"] = {n: sorted([(k, round(S[n][k]["t_nw"], 2)) for k in keys
                                      if S[n][k]["t_nw"] == S[n][k]["t_nw"] and abs(S[n][k]["t_nw"]) >= 2.5],
                                     key=lambda x: -abs(x[1])) for n, _ in VARS}
    # celda objetivo con intervalo bootstrap de las tablas principales
    tk = "A|large|ep -30|20"
    tgt = {}
    for n, s in VARS:
        T = tab(s)["main"].get(tk, {})
        c = S[n][ckey(dict(zip(("size", "X", "H", "regime"), TARGET)))]
        tgt[n] = {"n": c["n"], "weeks": c["weeks"], "x": c["x_daily_mean"], "t": c["t_nw"], "halves": c["halves"],
                  "x_lo": c["x_lo"], "x_hi": c["x_hi"], "unk": c["unknown_share"], "eligible": c["eligible"],
                  "ci_b60": T.get("ci95_b60"), "ci_b20": T.get("ci95_b20"), "ci_b120": T.get("ci95_b120"),
                  "sens": {k: v for k, v in T.items() if k.startswith("sens_")} if T else None}
    out["target"] = tgt
    # filas y tallas: c1 → c2 (efecto de la capitalización por clases)
    cols = ["company", "date", "size", "r20", "x20"]
    a = pd.read_parquet(C.WORK / "etapa1_tanda1c1j_rows.parquet", columns=cols).set_index(["company", "date"])
    b = pd.read_parquet(C.WORK / "etapa1_tanda1c2_rows.parquet", columns=cols).set_index(["company", "date"])
    com = a.index.intersection(b.index)
    tr = pd.crosstab(a.loc[com, "size"], b.loc[com, "size"])
    out["size_transitions_c1j_to_c2"] = {f"{i}->{j}": int(tr.loc[i, j]) for i in tr.index for j in tr.columns
                                         if i != j and tr.loc[i, j]}
    out["rows"] = {"c1j": int(len(a)), "c2": int(len(b)), "only_c1j": int(len(a.index.difference(b.index))),
                   "only_c2": int(len(b.index.difference(a.index)))}
    chg = a.loc[com, "size"] != b.loc[com, "size"]
    out["companies_size_changed"] = int(len(set(com[chg].get_level_values(0))))
    ref_a = a.groupby(["date", "size"]).r20.mean()
    ref_b = b.groupby(["date", "size"]).r20.mean()
    d = (ref_b - ref_a).dropna().reset_index()
    out["size_mean_r20_diff_pp"] = {sz: {"mean": float(g.r20.abs().mean() * 100), "max": float(g.r20.abs().max() * 100)}
                                    for sz, g in d.groupby("size")}
    (C.PUB / "etapa1_tanda1c2_conciliacion.json").write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False),
                                                         encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("eligible", "eligibility_changes", "abs_t_ge_2_5", "target",
                                          "size_transitions_c1j_to_c2", "rows", "companies_size_changed",
                                          "size_mean_r20_diff_pp")}, indent=1, default=str, ensure_ascii=False))
    print("mayores cambios de t c1→c2:", json.dumps(out["largest_t_changes_c1_to_c2"][:8], default=str))


if __name__ == "__main__":
    main()
