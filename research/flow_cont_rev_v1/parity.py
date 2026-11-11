"""Paridad Python (scripts/flow_state_lib.py) vs JS (shared/flow-state-lib.js, el de producción) sobre series reconstruidas."""
import json, os, pickle, subprocess, sys, random
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts")); import flow_state_lib as fsl
bars = pickle.load(open(os.path.join(HERE, "_work", "U2_bars.pkl"), "rb"))
random.seed(3); sample = random.sample(sorted(bars), 25)
px = pd.read_parquet(os.path.join(HERE, "data", "u2_prices.parquet")); spy = px[px.ticker == "SPY"].set_index("date").close.sort_index()
spy_m1 = {k: float(np.floor((v) * 100 + 0.5)) for k, v in (spy / spy.shift(21) - 1).dropna().items()}
F = ["flowScore", "rsi", "konc_alignment", "macdHist", "macdHistDelta1", "atrPct", "price", "m1"]
payload, py_flags = [], []
for t in sample:
    rows = bars[t]; b = pd.DataFrame(rows).set_index("bar")
    cal = pd.date_range(b.index[0], b.index[-1], freq="D"); pos = np.searchsorted(b.index.values, cal.values, side="right") - 1
    seq = [{**{k: rows[p][k] for k in F}, "date": str(cal[i].date()), "bar": str(rows[p]["bar"].date())} for i, p in enumerate(pos)]
    met = fsl.compute_series_metrics(seq)
    for i in range(5, len(met)):
        bm = spy_m1.get(pd.Timestamp(met[i]["bar"])); rs = None if bm is None or met[i]["m1"] is None else round(met[i]["m1"] - bm, 2)
        py_flags.append((t, met[i]["date"], fsl.evaluate_continuacion(met[i], met[max(0, i-15):i+1], rs, t)["pass"], fsl.evaluate_reversion(met[i], met[max(0, i-15):i+1])["pass"]))
    payload.append({"t": t, "seq": seq, "bm": {s["bar"]: spy_m1.get(pd.Timestamp(s["bar"])) for s in seq}})
json.dump(payload, open("_par_in.json", "w"))
js = r"""
const fsl=require(process.argv[1]);const fs=require('fs');const a=JSON.parse(fs.readFileSync('_par_in.json'));const out=[];
for(const x of a){const met=fsl.fslComputeSeriesMetrics(x.seq);for(let i=5;i<met.length;i++){const bm=x.bm[met[i].bar];
const rs=(bm==null||met[i].m1==null)?null:+(met[i].m1-bm).toFixed(2);const tail=met.slice(Math.max(0,i-15),i+1);
out.push([x.t,met[i].date,fsl.fslEvaluateContinuacion(met[i],tail,rs,x.t).pass,fsl.fslEvaluateReversion(met[i],tail).pass]);}}
fs.writeFileSync('_par_out.json',JSON.stringify(out));"""
subprocess.run(["node", "-e", js, os.path.join(ROOT, "shared", "flow-state-lib.js")], check=True)
jsf = json.load(open("_par_out.json")); os.remove("_par_in.json"); os.remove("_par_out.json")
d = [(a, b) for a, b in zip(py_flags, jsf) if (a[2], a[3]) != (bool(b[2]), bool(b[3]))]
print("filas", len(py_flags), "diferencias", len(d), "cont py/js", sum(x[2] for x in py_flags), sum(bool(x[2]) for x in jsf), "rev py/js", sum(x[3] for x in py_flags), sum(bool(x[3]) for x in jsf))
print(d[:5])
