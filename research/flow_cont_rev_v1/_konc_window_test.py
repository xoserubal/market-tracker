"""¿La diferencia de Koncorde se debe a la ventana de 820 días de producción? Muestra de (ticker, fecha) del periodo
en vivo con la misma vela y precio que la reconstrucción."""
import json, os, pickle, sys, random, collections
from datetime import timedelta
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import koncorde_calculator as kc
snap = collections.defaultdict(dict)
for l in open(os.path.join(ROOT, "docs/data/portfolio_daily_snapshot.jsonl"), encoding="utf8"):
    r = json.loads(l)
    if r.get("date", "") >= "2026-08-31": snap[r["ticker"]][r["date"]] = r
bars = pickle.load(open("_work/U2_bars.pkl", "rb"))
px = pd.read_parquet("data/u2_prices.parquet"); px["date"] = pd.to_datetime(px.date)
cand = []
for t, rows in bars.items():
    if t not in snap: continue
    rb = {r["bar"].strftime("%Y-%m-%d"): r for r in rows}
    for d, s in snap[t].items():
        a = (s.get("asOf") or "")[:10]
        if a in rb and s.get("price") and abs(s["price"] / rb[a]["price"] - 1) <= 0.003:
            cand.append((t, a, s.get("konc_alignment"), rb[a]["konc_alignment"], s.get("konc_d_state"), s.get("konc_3d_state"), s.get("konc_w_state")))
random.seed(7); sample = random.sample(sorted(set(cand)), min(300, len(set(cand))))
out = collections.Counter(); wins = collections.Counter(); ex = []
for t, a, live, rec, ld, l3, lw in sample:
    d = px[px.ticker == t].set_index("date").sort_index()
    d = d[~d.index.duplicated()].dropna(subset=["close"])
    f = d.adj_close / d.close
    adj = pd.DataFrame({"open": d.open * f, "high": d.high * f, "low": d.low * f, "close": d.adj_close, "volume": d.volume.fillna(0)}, index=d.index)
    end = pd.Timestamp(a)
    w = adj[(adj.index > end - timedelta(days=kc.HISTORY_DAYS)) & (adj.index <= end)]
    try:
        res = kc.compute_for_ticker(w)
    except Exception as e:
        out["error"] += 1; continue
    p = res.get("konc_alignment")
    out["n"] += 1
    out["prod820_eq_live"] += p == live
    out["rec_eq_live"] += rec == live
    out["prod820_eq_rec"] += p == rec
    for tf, lv in (("d", ld), ("3d", l3), ("w", lw)):
        wins[tf + "_prod820_eq_live"] += res.get(f"konc_{tf}_state") == lv
    if p != live and len(ex) < 8: ex.append((t, a, live, p, rec, (ld, l3, lw), (res.get("konc_d_state"), res.get("konc_3d_state"), res.get("konc_w_state"))))
print(dict(out)); print(dict(wins))
for e in ex: print(e)
