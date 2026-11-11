"""Paridad de entradas en días con dato en vivo limpio (vela del día y precio a ±0,3 %) y estados Koncorde iguales."""
import json, os, pickle, collections
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
snap = collections.defaultdict(dict)
for l in open(os.path.join(ROOT, "docs/data/portfolio_daily_snapshot.jsonl"), encoding="utf8"):
    r = json.loads(l)
    if r.get("date", "") >= "2026-08-31": snap[r["ticker"]][r["date"]] = r
bars = pickle.load(open("_work/U2_bars.pkl", "rb"))
rows = []
for t, rr in bars.items():
    rb = {r["bar"].strftime("%Y-%m-%d"): r for r in rr}
    for d, s in snap.get(t, {}).items():
        a = (s.get("asOf") or "")[:10]
        if a in rb and s.get("price") and abs(s["price"] / rb[a]["price"] - 1) <= 0.003 and s.get("konc_alignment") == rb[a]["konc_alignment"]:
            r = rb[a]
            rows.append({k + "_d": (None if s.get(k) is None or r.get(k) is None else abs(s[k] - r[k])) for k in ("flowScore", "rsi", "m1", "atrPct")}
                        | {"hist_sign_eq": (s.get("macdHist") or 0) >= 0 if s.get("macdHist") is None else ((s["macdHist"] >= 0) == ((r["macdHist"] or 0) >= 0)),
                           "hd_sign_eq": None if s.get("macdHistDelta1") is None or r["macdHistDelta1"] is None else ((s["macdHistDelta1"] < 0) == (r["macdHistDelta1"] < 0))})
df = pd.DataFrame(rows); print("n", len(df))
for k in ("flowScore_d", "rsi_d", "m1_d", "atrPct_d"):
    x = df[k].dropna(); print(k, "exact%", round(100 * (x < 0.01).mean(), 1), "<=1:", round(100 * (x <= 1).mean(), 1), "p99", round(x.quantile(.99), 2), "max", round(x.max(), 2))
print("macdHist sign eq %", round(100 * df.hist_sign_eq.mean(), 2), "| delta1 sign eq %", round(100 * df.hd_sign_eq.dropna().mean(), 2))
