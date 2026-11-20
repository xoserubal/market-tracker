"""Enmienda 1 — conciliación de la tanda 1 original con la corregida, por familias acumuladas.

Compara: original (etapa1_tanda1_*), c1s (+contrasplits), c1si (+identidad), c1sic (+CIK), c1sicp (+escisiones),
c1sicpj (+saltos indeterminados), c1sicpjt (+fusiones valoradas), c1 (+regla §7, versión corregida completa).
Salida: data/etapa1_tanda1c1_conciliacion.json (agregados). El informe se redacta a partir de ella.
"""
import json

import numpy as np
import pandas as pd

import fn_config as C

VARS = [("orig", ""), ("c1s", "c1s"), ("c1si", "c1si"), ("c1sic", "c1sic"), ("c1sicp", "c1sicp"),
        ("c1sicpj", "c1sicpj"), ("c1sicpjt", "c1sicpjt"), ("c1", "c1")]
FAMILY = {"c1s": "contrasplits", "c1si": "identidad", "c1sic": "CIK y capitalización", "c1sicp": "escisiones",
          "c1sicpj": "saltos indeterminados", "c1sicpjt": "fusiones valoradas (Alpaca)", "c1": "regla §7 (ausentes)"}
COLS = ["company", "key", "date", "size", "flow", "r20", "x20", "ep-30", "ep-20", "ep-10", "operable"]
TARGET = ("large", -30, 20, "all")


def rows(sfx):
    p = pd.read_parquet(C.WORK / f"etapa1_tanda1{sfx}_rows.parquet")
    keep = [c for c in COLS + ["unk20", "unk_s20", "unk_j20", "unkany20", "xs20"] if c in p]
    return p[keep]


def sel(sfx):
    return json.loads((C.PUB / f"etapa1_tanda1{sfx}_selection.json").read_text(encoding="utf-8"))


def main():
    R = {n: rows(s) for n, s in VARS}
    S = {n: sel(s) for n, s in VARS}
    out = {"variants": dict(VARS), "family_of_step": FAMILY}

    # --- 1. empresas y días: totales y cambios entre pasos consecutivos
    tot, steps = {}, {}
    prev = None
    for n, _ in VARS:
        r = R[n]
        tot[n] = {"rows": int(len(r)), "companies": int(r.company.nunique()),
                  "rows_by_size": r["size"].value_counts().to_dict(),
                  "companies_by_size": r.groupby("size").company.nunique().to_dict()}
        if prev is not None:
            a = R[prev].set_index(["company", "date"])
            b = r.set_index(["company", "date"])
            only_a, only_b = a.index.difference(b.index), b.index.difference(a.index)
            com = a.index.intersection(b.index)
            aa, bb = a.loc[com], b.loc[com]
            size_ch = (aa["size"] != bb["size"])
            flow_ch = ~np.isclose(aa.flow, bb.flow, equal_nan=True)
            r20_ch = ~np.isclose(aa.r20, bb.r20, equal_nan=True, rtol=0, atol=1e-9)
            x20_ch = ~np.isclose(aa.x20, bb.x20, equal_nan=True, rtol=0, atol=1e-9)
            ch_comp = set(com[size_ch | flow_ch | r20_ch].get_level_values(0)) | set(only_a.get_level_values(0)) \
                | set(only_b.get_level_values(0))
            steps[n] = {"family": FAMILY[n], "rows_removed": int(len(only_a)), "rows_added": int(len(only_b)),
                        "rows_size_changed": int(size_ch.sum()), "rows_flow_changed": int(flow_ch.sum()),
                        "rows_r20_changed": int(r20_ch.sum()), "rows_x20_changed": int(x20_ch.sum()),
                        "companies_affected": len(ch_comp),
                        "size_transitions": {f"{x}->{y}": int(v) for (x, y), v in
                                             pd.crosstab(aa["size"][size_ch], bb["size"][size_ch]).stack().items() if v},
                        "companies_added": sorted(set(only_b.get_level_values(0)) - set(a.index.get_level_values(0)))[:50],
                        "companies_removed": sorted(set(only_a.get_level_values(0)) - set(b.index.get_level_values(0)))[:50]}
        prev = n
    out["totals"], out["steps"] = tot, steps

    # --- 2. capitalización: transiciones de talla original → corregida (días utilizables comunes)
    a = R["orig"].set_index(["company", "date"])
    b = R["c1"].set_index(["company", "date"])
    com = a.index.intersection(b.index)
    ct = pd.crosstab(a.loc[com, "size"], b.loc[com, "size"])
    out["size_crosstab_orig_vs_c1"] = {f"{x}->{y}": int(v) for (x, y), v in ct.stack().items() if v}
    sc = a.loc[com, "size"] != b.loc[com, "size"]
    out["companies_changing_size"] = int(len(set(com[sc].get_level_values(0))))

    # --- 3. episodios por talla y umbral
    out["episodes"] = {n: {f"{sz} X={X}": int(R[n][(R[n]["size"] == sz) & R[n][f"ep{X}"]].shape[0])
                           for sz in ("large", "mid", "small", "micro", "unknown") for X in (-10, -20, -30)}
                       for n, _ in VARS}

    # --- 4. medias de referencia (media de r20 de la talla por día)
    ref = {}
    for n, _ in VARS:
        g = R[n].groupby(["date", "size"]).r20.mean()
        ref[n] = g
    d = {}
    for n, _ in VARS[1:]:
        j = pd.concat([ref["orig"], ref[n]], axis=1, keys=["o", "c"]).dropna()
        diff = (j.c - j.o) * 100
        d[n] = {sz: {"mean_abs_pp": float(diff.xs(sz, level=1).abs().mean()),
                     "max_abs_pp": float(diff.xs(sz, level=1).abs().max()),
                     "days_gt_0p25pp": int((diff.xs(sz, level=1).abs() > 0.25).sum())}
                for sz in sorted(set(j.index.get_level_values(1)))}
    out["reference_mean_r20_vs_orig"] = d

    # --- 5. las 72 candidatas
    cand = {}
    for n, _ in VARS:
        for c in S[n]["candidates"]:
            kk = f"{c['size']}|{c['X']}|{c['H']}|{c['regime']}"
            cand.setdefault(kk, {})[n] = {"n": c["n"], "weeks": c["weeks"], "x_pp": round(100 * c["x_daily_mean"], 3),
                                          "t": round(c["t_nw"], 3), "eligible": c["eligible"],
                                          "failed": [k for k, v in c["criteria"].items() if not v]}
    out["candidates"] = cand
    out["eligible_by_variant"] = {n: [f"{c['size']}|{c['X']}|{c['H']}|{c['regime']}" for c in S[n]["candidates"]
                                      if c["eligible"]] for n, _ in VARS}
    out["chosen_by_variant"] = {n: S[n]["chosen_this_tanda"] for n, _ in VARS}

    # --- 6. la candidata original
    tk = f"{TARGET[0]}|{TARGET[1]}|{TARGET[2]}|{TARGET[3]}"
    out["target_cell"] = {n: cand[tk].get(n) for n, _ in VARS}

    # --- 7. M0/M1
    out["models"] = {n: {sz: {"n": m["n"], "M1": {k: round(100 * v, 3) for k, v in m["M1_tercile_effect"].items()},
                              "M0_pp": {k: round(100 * v, 3) for k, v in m["M0"].items()}}
                         for sz, m in S[n]["models"].items()} for n, _ in VARS}

    # --- 8. resultados todavía desconocidos (versión corregida, plazo 20)
    r = R["c1"]
    out["unknown_c1_h20"] = {
        "terminal": int(r.unk20.sum()), "spinoff": int(r.unk_s20.sum()), "jump": int(r.unk_j20.sum()),
        "any": int(r.unkany20.sum()),
        "by_size": r.groupby("size")[["unk20", "unk_s20", "unk_j20"]].sum().astype(int).to_dict("index"),
        "neg_flow_any_by_size": r[r.flow < 0].groupby("size").unkany20.sum().astype(int).to_dict(),
        "episodes_any": {f"X={X}": int(r[r[f"ep{X}"]].unkany20.sum()) for X in (-10, -20, -30)}}
    (C.PUB / "etapa1_tanda1c1_conciliacion.json").write_text(json.dumps(out, indent=1, default=str),
                                                            encoding="utf-8")
    print("hecho")


if __name__ == "__main__":
    main()
