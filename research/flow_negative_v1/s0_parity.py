"""Etapa 0 — paridad del Flow Score (puertas 3 y 4 del preregistro). Sin rendimientos posteriores.

Puerta 4 (fórmula): los componentes de cada fila se pasan a computeFlowScore de shared/flow-score.js (Node, el
código de producción) y se compara con el Flow de la réplica Python. Muestra aleatoria de >= 2 000 filas completas.
Puerta 3 (fuente): Flow con Alpaca frente al Flow con Yahoo de research/flow_cont_rev_v1/_work/U1_bars.pkl (mismo
código de cálculo, distinta fuente de precios) en las fechas comunes con Flow completo en ambos (desde 2018).

Salida: data/parity.json (agregados)
"""
import json
import pickle
import subprocess

import numpy as np
import pandas as pd

import fn_config as C

SER = C.WORK / "series"
JS = r"""
const {computeFlowScore} = require(process.argv[1]);
const rows = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(rows.map(r => computeFlowScore(r))));
"""


def formula_parity(n=3000, seed=0):
    files = sorted(SER.glob("*.parquet"))
    rng = np.random.default_rng(seed)
    rows = []
    for f in rng.choice(files, size=min(150, len(files)), replace=False):
        d = pd.read_parquet(f)
        d = d[d.flow_complete]
        if len(d):
            rows.append(d.sample(min(25, len(d)), random_state=int(rng.integers(1e9))))
    s = pd.concat(rows).head(n)
    payload = [{"w1": None if np.isnan(r.w1) else float(r.w1), "m1": None if np.isnan(r.m1) else float(r.m1),
                "rsi": None if np.isnan(r.rsi) else float(r.rsi),
                "macdBull": None if np.isnan(r.macd_hist) else bool(r.macd_hist >= 0),
                "atrPct": None if np.isnan(r.atrPct) else float(r.atrPct),
                "konc_d_state": r.konc_d, "konc_w_state": r.konc_w,
                "fromHigh": None if np.isnan(r.fromHigh) else float(r.fromHigh)} for r in s.itertuples()]
    out = subprocess.run(["node", "-e", JS, str(C.REPO / "shared" / "flow-score.js")], input=json.dumps(payload),
                         capture_output=True, text=True, check=True).stdout
    js = np.array(json.loads(out), float)
    diff = np.abs(js - s.flow.to_numpy(float))
    return {"rows": int(len(s)), "max_abs_diff": float(diff.max()), "rows_diff_gt_0_01": int((diff > 0.01).sum())}


def source_parity():
    yb = pickle.load(open(C.REPO / "research" / "flow_cont_rev_v1" / "_work" / "U1_bars.pkl", "rb"))
    summ = pd.read_csv(C.WORK / "series_summary.csv", dtype=str)
    summ = summ[(summ.status == "ok") & (summ["asof"].fillna("") == "")]
    diffs, per = [], []
    for r in summ.itertuples():
        t = r.ticker.replace(".", "-")
        if t not in yb or not yb[t]:
            continue
        y = pd.DataFrame(yb[t])[["bar", "flowScore"]]
        y["date"] = y.bar.dt.strftime("%Y-%m-%d")
        a = pd.read_parquet(SER / f"{r.key}.parquet")
        a = a[a.flow_complete & (a.date >= "2018-01-02")][["date", "flow"]]
        m = a.merge(y[["date", "flowScore"]], on="date").dropna()
        if len(m) < 100:
            continue
        d = (m.flow - m.flowScore).abs().to_numpy()
        diffs.append(d)
        per.append({"ticker": r.ticker, "n": len(m), "median": float(np.median(d)), "p90": float(np.quantile(d, .9))})
    d = np.concatenate(diffs)
    per = pd.DataFrame(per)
    return {"tickers": int(len(per)), "rows": int(len(d)), "median_abs_diff": float(np.median(d)),
            "p90_abs_diff": float(np.quantile(d, .9)), "p99_abs_diff": float(np.quantile(d, .99)),
            "share_diff_gt_2": float((d > 2).mean()),
            "worst_tickers_by_p90": per.sort_values("p90", ascending=False).head(15).to_dict("records")}


def main():
    res = {"formula": formula_parity(), "source_alpaca_vs_yahoo": source_parity()}
    res["gate4_pass"] = res["formula"]["max_abs_diff"] <= 0.01 and res["formula"]["rows"] >= 2000
    s = res["source_alpaca_vs_yahoo"]
    res["gate3_pass"] = s["median_abs_diff"] <= 0.5 and s["p90_abs_diff"] <= 2 and s["tickers"] >= 200
    json.dump(res, open(C.PUB / "parity.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "source_alpaca_vs_yahoo"}, indent=1))
    print({k: v for k, v in s.items() if k != "worst_tickers_by_p90"})


if __name__ == "__main__":
    main()
