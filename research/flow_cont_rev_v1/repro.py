"""Paso previo (§4 del preregistro): candidatos reconstruidos frente al registro en vivo del Screener."""
import json, os, collections
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
log = pd.read_json(os.path.join(ROOT, "docs", "data", "screener_signal_log.jsonl"), lines=True)
log = log[log["filter"].isin(["flow_continuacion", "flow_reversion"])].copy()
log["date"] = pd.to_datetime(log.date).dt.strftime("%Y-%m-%d")
c = pd.read_parquet(os.path.join(HERE, "_work", "U2_cands.parquet"))
c["date"] = c.date.dt.strftime("%Y-%m-%d")
lo, hi = log.date.min(), "2026-11-09"
log = log[log.date <= hi]
res = {}
for f, col in (("flow_continuacion", "cont"), ("flow_reversion", "rev")):
    L = set(zip(log[log["filter"] == f].ticker, log[log["filter"] == f].date))
    R = set(zip(c[c[col] & (c.date >= lo) & (c.date <= hi)].ticker, c[c[col] & (c.date >= lo) & (c.date <= hi)].date))
    near = 0
    Rt = collections.defaultdict(set)
    for t, d in R: Rt[t].add(pd.Timestamp(d))
    for t, d in L - R:
        if any(abs((x - pd.Timestamp(d)).days) <= 3 for x in Rt[t]): near += 1
    # eventos (enfriamiento 10 días) en ambos
    def ev(S):
        out = set(); last = {}
        for t, d in sorted(S, key=lambda x: x[1]):
            if t not in last or (pd.Timestamp(d) - pd.Timestamp(last[t])).days >= 10: out.add((t, d))
            last[t] = d
        return out
    EL, ER = ev(L), ev(R)
    evmatch = sum(1 for t, d in EL if any(t == t2 and abs((pd.Timestamp(d) - pd.Timestamp(d2)).days) <= 3 for t2, d2 in ER))
    res[f] = {"live_rows": len(L), "reconstructed_rows": len(R), "both_same_day": len(L & R),
              "live_matched_within_3d": len(L & R) + near, "only_live": len(L - R) - near, "only_reconstructed": len(R - L),
              "live_events": len(EL), "reconstructed_events": len(ER), "live_events_matched_pm3d": evmatch}
res["period"] = [lo, hi]
json.dump(res, open(os.path.join(HERE, "repro_results.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
