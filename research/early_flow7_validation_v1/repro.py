"""Paso 1 del preregistro (wiki/PREREGISTRO_EARLY_FLOW_7_V1.md): Early Flow capturado por el pipeline
(versión original) frente al reconstruido desde precios con sesión anterior real (versión corregida).
Solo lectura. Salida: repro_results.json"""
import collections
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FB = os.path.join(ROOT, "research", "macd_combo_filters_v1")
FLOW = os.path.join(ROOT, "shared", "flow-score.js")
sys.path.insert(0, FB)
os.chdir(FB)
import build_features as bf  # noqa: E402
os.chdir(HERE)

SNAPS = ("portfolio_daily_snapshot.jsonl", "market_equities_daily_snapshot.jsonl")
CAP_KEYS = ("earlyFlow", "konc_d_state", "konc_3d_state", "konc_w_state", "atrPct", "fromHigh", "rsi", "w1", "m1", "date")


def py(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.floating, np.integer)):
        v = v.item()
    if v is pd.NA:
        return None
    return v


def run_ef(items):
    """items: [(d, prev)] -> scores con computeEarlyFlowScore de producción."""
    tmp_in, tmp_out = os.path.join(HERE, "_ef_in.json"), os.path.join(HERE, "_ef_out.json")
    json.dump([{"d": d, "p": p} for d, p in items], open(tmp_in, "w"))
    js = ("const {computeEarlyFlowScore}=require(process.argv[1]);const fs=require('fs');"
          "const a=JSON.parse(fs.readFileSync(process.argv[2]));"
          "fs.writeFileSync(process.argv[3],JSON.stringify(a.map(x=>computeEarlyFlowScore(x.d,x.p))));")
    subprocess.run(["node", "-e", js, FLOW, tmp_in, tmp_out], check=True)
    out = json.load(open(tmp_out))
    os.remove(tmp_in)
    os.remove(tmp_out)
    return out


def crosses(series):
    """Cruces del umbral 7: primera vela >= 7 tras >= 10 velas por debajo."""
    out, last = [], -99
    for i, (bar, v) in enumerate(series):
        if v is None:
            continue
        prev = series[i - 1][1] if i > 0 else None
        if v >= 7 and i > 0 and (prev is None or prev < 7) and i - last > 10:
            out.append((i, bar))
        if v >= 7:
            last = i
    return out


def main():
    px = pd.read_parquet(os.path.join(FB, "prices_cache.parquet"))
    cache_t = set(px.ticker.unique())
    cap = collections.defaultdict(dict)          # ticker -> vela -> última captura
    for fn in SNAPS:
        for line in open(os.path.join(ROOT, "docs", "data", fn), encoding="utf-8"):
            r = json.loads(line)
            if r.get("ticker") not in cache_t or not r.get("asOf"):
                continue
            bd = r["asOf"][:10]
            p = cap[r["ticker"]].get(bd)
            if p is None or r["date"] >= p["date"]:
                cap[r["ticker"]][bd] = r
    tick = sorted(cap)

    rows = []
    for t in tick:
        d = px[px.ticker == t].set_index("date").sort_index()
        d = d[~d.index.duplicated()]
        f = d.adj_close / d.close
        adj = pd.DataFrame({"open": d.open * f, "high": d.high * f, "low": d.low * f, "close": d.adj_close,
                            "volume": d.volume.fillna(0)}, index=d.index)
        sd, s3, sw = bf.konc_daily_3d_weekly(adj)
        c = d.close.to_numpy(float)
        atr = bf.bt.wilder_atr(c, d.high.to_numpy(float), d.low.to_numpy(float))
        atrp = np.round(atr / c * 100, 1)
        rsi = bf.js_round(bf.wilder_rsi(c))
        hi = d.close.rolling("365D").max().to_numpy()
        fh = bf.js_round((c - hi) / hi * 100)
        w1 = np.full(len(c), np.nan); w1[5:] = bf.js_round((c[5:] / c[:-5] - 1) * 100)
        m1 = np.full(len(c), np.nan); m1[21:] = bf.js_round((c[21:] / c[:-21] - 1) * 100)
        dates = [str(x.date()) for x in d.index]
        for i in range(1, len(c)):
            if dates[i] < "2026-08-19":
                continue
            rec = {"ticker": t, "bar": dates[i], "real_prev_bar": dates[i - 1],
                   "kd": py(sd[i]), "pkd": py(sd[i - 1]), "k3": py(s3[i]), "pk3": py(s3[i - 1]), "kw": py(sw[i]),
                   "atr": py(atrp[i]), "patr": py(atrp[i - 1]), "fh": py(fh[i]), "rsi": py(rsi[i]),
                   "w1": py(w1[i]), "m1": py(m1[i])}
            cr = cap[t].get(dates[i])
            if cr:
                rec["cap"] = {k: cr.get(k) for k in CAP_KEYS}
            rows.append(rec)

    ef = run_ef([({"konc_d_state": r["kd"], "konc_3d_state": r["k3"], "konc_w_state": r["kw"], "atrPct": r["atr"],
                   "fromHigh": r["fh"], "rsi": r["rsi"], "w1": r["w1"], "m1": r["m1"]},
                  {"konc_d_state": r["pkd"], "konc_3d_state": r["pk3"], "atrPct": r["patr"]}) for r in rows])
    for r, e in zip(rows, ef):
        r["ef_rec"] = e

    by = collections.defaultdict(dict)
    for r in rows:
        if "cap" in r:
            by[r["ticker"]][r["bar"]] = r
    cmp = [r for r in rows if "cap" in r and r["cap"]["earlyFlow"] is not None]

    # Entradas capturadas + sesión anterior real (si se capturó): aísla el efecto de la "sesión anterior".
    items = []
    for r in cmp:
        pr = by[r["ticker"]].get(r["real_prev_bar"])
        c_ = r["cap"]
        items.append(({k: c_[k] for k in ("konc_d_state", "konc_3d_state", "konc_w_state", "atrPct", "fromHigh", "rsi", "w1", "m1")},
                      None if pr is None else {"konc_d_state": pr["cap"]["konc_d_state"],
                                               "konc_3d_state": pr["cap"]["konc_3d_state"], "atrPct": pr["cap"]["atrPct"]}))
    for r, e in zip(cmp, run_ef(items)):
        r["ef_cap_realprev"] = e
        r["has_real_prev_capture"] = by[r["ticker"]].get(r["real_prev_bar"]) is not None

    a = np.array([r["cap"]["earlyFlow"] for r in cmp], float)
    b = np.array([r["ef_rec"] for r in cmp], float)
    c2 = np.array([r["ef_cap_realprev"] for r in cmp], float)
    res = {"tickers": tick, "n_tickers": len(tick), "n_compared": len(cmp),
           "bars": [min(r["bar"] for r in cmp), max(r["bar"] for r in cmp)]}
    res["value_match"] = {
        "captured_vs_reconstructed_identical": round(float(np.mean(a == b)), 3),
        "captured_vs_reconstructed_within1": round(float(np.mean(abs(a - b) <= 1)), 3),
        "captured_vs_reconstructed_same_side_of_7": round(float(np.mean((a >= 7) == (b >= 7))), 3),
        "captured_vs_captured_inputs_real_prev_identical": round(float(np.mean(a == c2)), 3),
        "captured_inputs_real_prev_vs_reconstructed_identical": round(float(np.mean(c2 == b)), 3)}
    res["state7_confusion"] = {"both": int(np.sum((a >= 7) & (b >= 7))), "only_captured": int(np.sum((a >= 7) & (b < 7))),
                               "only_reconstructed": int(np.sum((a < 7) & (b >= 7))), "neither": int(np.sum((a < 7) & (b < 7)))}

    def same(x, y):
        if isinstance(x, str) or isinstance(y, str):
            return x == y
        if x is None or y is None:
            return x is None and y is None
        return float(x) == float(y)
    mm = collections.Counter()
    pairs = [("konc_d_state", "kd"), ("konc_3d_state", "k3"), ("konc_w_state", "kw"), ("atrPct", "atr"),
             ("fromHigh", "fh"), ("rsi", "rsi"), ("w1", "w1"), ("m1", "m1")]
    for r in cmp:
        for ck, rk in pairs:
            if not same(r["cap"][ck], r[rk]):
                mm[ck] += 1
    res["input_mismatch_rate"] = {ck: round(mm[ck] / len(cmp), 3) for ck, _ in pairs}
    pre = [r for r in cmp if r["bar"] < "2026-08-30"]
    post = [r for r in cmp if r["bar"] >= "2026-08-30"]
    res["konc_w_mismatch"] = {"pre_2026_08_30": round(float(np.mean([r["cap"]["konc_w_state"] != r["kw"] for r in pre])), 3) if pre else None,
                              "n_pre": len(pre),
                              "post": round(float(np.mean([r["cap"]["konc_w_state"] != r["kw"] for r in post])), 3)}
    res["pipeline_prev_is_real_prev_session"] = round(float(np.mean([r["has_real_prev_capture"] for r in cmp])), 3)
    # discrepancia del valor de EF atribuible a cada causa
    diff = a != b
    res["ef_differs_rows"] = int(diff.sum())
    res["ef_differs_with_identical_inputs"] = int(sum(1 for r, dd in zip(cmp, diff) if dd and all(same(r["cap"][ck], r[rk]) for ck, rk in pairs)))

    cr = {"same_day": 0, "within2": 0, "only_captured": 0, "only_reconstructed": 0}
    detail = []
    for t in tick:
        ser = sorted((r["bar"], r) for r in rows if r["ticker"] == t)
        sc = [(bb, r["cap"]["earlyFlow"] if "cap" in r else None) for bb, r in ser]
        sr = [(bb, r["ef_rec"]) for bb, r in ser]
        xc, xr = crosses(sc), crosses(sr)
        used = set()
        for i, bb in xc:
            m = [j for j, _ in xr if abs(j - i) <= 2 and j not in used]
            if i in m:
                cr["same_day"] += 1; used.add(i); detail.append([t, bb, "mismo dia"])
            elif m:
                cr["within2"] += 1; used.add(m[0]); detail.append([t, bb, "a +-2 sesiones"])
            else:
                cr["only_captured"] += 1; detail.append([t, bb, "solo capturado"])
        for j, bb in xr:
            if j not in used:
                cr["only_reconstructed"] += 1; detail.append([t, bb, "solo reconstruido"])
    res["crossings_7"] = cr
    res["crossings_detail"] = sorted(detail, key=lambda x: x[1])
    json.dump(res, open(os.path.join(HERE, "repro_results.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in res.items() if k not in ("crossings_detail", "tickers")}, indent=1))
    for x in res["crossings_detail"]:
        print(x)


if __name__ == "__main__":
    main()
