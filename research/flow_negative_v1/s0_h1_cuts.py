"""Cortes de H1 congelables en la etapa 0 (no usan ningún resultado posterior).
Población: días con Flow < 0, completo, sin evento, del periodo de desarrollo de cada índice.
- Quintiles de w1 (retorno 5 sesiones) y m1 (21 sesiones), por índice.
- Tercios del resto R dentro de cada celda 5 x 5 (c1 = cuantil 1/3, c2 = cuantil 2/3).
Salida: data/h1_frozen_cuts.json. Dev de grandes y medianas desde 2018-01-02 (Flow completo), pendiente de decisión."""
import json
import numpy as np
import pandas as pd
import fn_config as C

DEV_START = {"sp500": "2018-01-02", "sp400": "2018-01-02", "sp600": "2020-01-02"}
p = pd.read_parquet(C.WORK / "panel.parquet", columns=["index", "date", "flow", "flow_complete", "event_excluded",
                                                        "w1", "m1", "R"])
out = {}
for idx, g in p.groupby("index"):
    d = g[(g.date >= DEV_START[idx]) & (g.date <= C.DEV_END[idx]) & g.flow_complete.fillna(False).astype(bool)
          & ~g.event_excluded & (g.flow < 0)].dropna(subset=["w1", "m1", "R"])
    qw = np.quantile(d.w1, [.2, .4, .6, .8]).tolist()
    qm = np.quantile(d.m1, [.2, .4, .6, .8]).tolist()
    cw, cm = np.searchsorted(qw, d.w1, side="right"), np.searchsorted(qm, d.m1, side="right")
    cells = {}
    for a in range(5):
        for b in range(5):
            r = d.R[(cw == a) & (cm == b)]
            cells[f"{a}{b}"] = {"n": int(len(r)), "c1": float(np.quantile(r, 1 / 3)) if len(r) else None,
                                "c2": float(np.quantile(r, 2 / 3)) if len(r) else None}
    out[idx] = {"dev": [DEV_START[idx], C.DEV_END[idx]], "n": int(len(d)), "w1_breaks": qw, "m1_breaks": qm,
                "R_tercile_cuts_by_cell": cells}
json.dump(out, open(C.PUB / "h1_frozen_cuts.json", "w"), indent=1)
for i, v in out.items():
    small = [k for k, c in v["R_tercile_cuts_by_cell"].items() if c["n"] < 300]
    ties = [k for k, c in v["R_tercile_cuts_by_cell"].items() if c["c1"] == c["c2"]]
    print(i, v["n"], "w1", v["w1_breaks"], "m1", v["m1_breaks"], "celdas<300:", small, "c1==c2:", ties)
