"""Diagnóstico del paso de reproducibilidad (§4): por qué los candidatos de Flow Continuación en vivo y reconstruidos
no coinciden. Compara condición por condición, en los mismos (ticker, fecha), lo que vio el registro en vivo
(portfolio_daily_snapshot.jsonl, evaluado como scripts/screener_signal_log.js) y lo reconstruido (features.py, U2).
No calcula rentabilidades. Salida: repro_diag.json
"""
import collections
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import flow_state_lib as fsl  # noqa: E402

FIELDS = ["date", "flowScore", "rsi", "konc_alignment", "macdHist", "macdHistDelta1", "atrPct", "price", "m1"]
HI = "2026-11-09"


def conds(today, rows, rs, t):
    """Mismas condiciones que fsl.evaluate_continuacion, una a una."""
    f = today.get("flowScore")
    last5 = [r.get("delta5") for r in rows[-5:] if r.get("delta5") is not None]
    h, hd = today.get("macdHist"), today.get("macdHistDelta1")
    rsi = today.get("rsi")
    ev = fsl.evaluate_continuacion(today, rows, rs, t)
    return {
        "flow_pos": f is not None and f > 0,
        "above5": (today.get("flow_above_zero_days") or 0) >= 5,
        "delta_3of5": len(last5) >= 3 and sum(d >= 0 for d in last5) >= 3,
        "konc_bull": today.get("konc_alignment") == "bullish_aligned",
        "rsi_55_68": rsi is not None and 55 <= rsi <= 68,
        "rs_pos": rs is not None and rs > 0,
        "macd_ok": h is not None and h >= 0 and not (hd is not None and hd < 0),
        "not_mature": not ev["mature"],
        "pass": ev["pass"],
    }


def main():
    # ── en vivo: snapshot por fecha de captura, como el registro ──
    snap = collections.defaultdict(dict)
    with open(os.path.join(ROOT, "docs", "data", "portfolio_daily_snapshot.jsonl"), encoding="utf8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("ticker") and r.get("date"):
                snap[r["ticker"]][r["date"]] = r
    g = yf.download("^GSPC", start="2026-06-01", end="2026-11-12", progress=False, auto_adjust=False)
    gc = g["Close"].squeeze().dropna()
    gd = [d.strftime("%Y-%m-%d") for d in gc.index]
    gv = gc.to_numpy()

    def bm(date):
        idx = max([i for i, d in enumerate(gd) if d <= date], default=-1)
        return None if idx < 21 else round((gv[idx] / gv[idx - 21] - 1) * 100, 2)

    log = pd.read_json(os.path.join(ROOT, "docs", "data", "screener_signal_log.jsonl"), lines=True)
    log = log[log["filter"] == "flow_continuacion"]
    log["date"] = pd.to_datetime(log.date).dt.strftime("%Y-%m-%d")
    lo = log.date.min()
    L = set(zip(log.ticker, log.date))

    # ── reconstruido ──
    bars = pickle.load(open(os.path.join(HERE, "_work", "U2_bars.pkl"), "rb"))
    px = pd.read_parquet(os.path.join(HERE, "data", "u2_prices.parquet"))
    px["date"] = pd.to_datetime(px.date)
    spy = px[px.ticker == "SPY"].set_index("date").sort_index().close
    spy_m1 = {k: float(np.floor(v * 100 + 0.5)) for k, v in (spy / spy.shift(21) - 1).dropna().items()}

    out_rows = []
    for t, rows in bars.items():
        if t not in snap:
            continue
        b = pd.DataFrame(rows).set_index("bar")
        cal = pd.date_range(b.index[0], b.index[-1], freq="D")
        pos = np.searchsorted(b.index.values, cal.values, side="right") - 1
        seq = [{**{k: rows[p][k] for k in FIELDS if k != "date"}, "date": cal[i].strftime("%Y-%m-%d"),
                "bar": rows[p]["bar"]} for i, p in enumerate(pos)]
        rmet = fsl.compute_series_metrics(seq)
        ridx = {m["date"]: i for i, m in enumerate(rmet)}
        sdates = sorted(snap[t])
        lseq = [{k: snap[t][d].get(k) for k in FIELDS} | {"asOf": (snap[t][d].get("asOf") or "")[:10]} for d in sdates]
        lmet = fsl.compute_series_metrics(lseq)
        for i, lm in enumerate(lmet):
            d = lm["date"]
            if d < lo or d > HI or i < 5 or d not in ridx:
                continue
            j = ridx[d]
            rm = rmet[j]
            rbm = spy_m1.get(rm["bar"])
            rrs = None if rbm is None or rm["m1"] is None else round(rm["m1"] - rbm, 2)
            lbm = bm(d)
            lrs = None if lbm is None or lm["m1"] is None else round(lm["m1"] - lbm, 2)
            lc = conds(lm, lmet[max(0, i - 15):i + 1], lrs, t)
            rc = conds(rm, rmet[max(0, j - 15):j + 1], rrs, t)
            if not (lc["pass"] or rc["pass"] or (t, d) in L):
                continue
            out_rows.append({
                "ticker": t, "date": d, "in_log": (t, d) in L, "live_pass": lc["pass"], "rec_pass": rc["pass"],
                "live_bar": lm["asOf"], "rec_bar": rm["bar"].strftime("%Y-%m-%d"),
                "live": {k: lm.get(k) for k in ("flowScore", "rsi", "konc_alignment", "macdHist", "m1", "delta5")},
                "rec": {k: rm.get(k) for k in ("flowScore", "rsi", "konc_alignment", "macdHist", "m1", "delta5")},
                "live_rs": lrs, "rec_rs": rrs, "live_c": lc, "rec_c": rc,
                "live_price": lm.get("price"), "rec_price": rm.get("price"),
                "live_hist_bars": [r.get("asOf") for r in lmet[max(0, i - 9):i + 1]],
            })

    df = pd.DataFrame(out_rows)
    res = {"period": [lo, HI]}
    # 1) ¿la réplica del registro (Python sobre el snapshot) reproduce el registro?
    res["log_vs_replay"] = {"log_rows": len(L), "replay_pass": int(df.live_pass.sum()),
                            "both": int((df.live_pass & df.in_log).sum()),
                            "log_only": int((df.in_log & ~df.live_pass).sum()),
                            "replay_only": int((df.live_pass & ~df.in_log).sum())}
    # 2) diferencias réplica en vivo vs reconstruido, condición por condición
    dis = df[df.live_pass != df.rec_pass].copy()
    dis["bar_same"] = dis.live_bar == dis.rec_bar
    ckeys = ["flow_pos", "above5", "delta_3of5", "konc_bull", "rsi_55_68", "rs_pos", "macd_ok", "not_mature"]
    for side, mask in (("only_live", dis.live_pass & ~dis.rec_pass), ("only_rec", dis.rec_pass & ~dis.live_pass)):
        sub = dis[mask]
        cnt = collections.Counter()
        single = collections.Counter()
        for _, r in sub.iterrows():
            failing = [k for k in ckeys if r.live_c[k] != r.rec_c[k]]
            for k in failing:
                cnt[k] += 1
            if len(failing) == 1:
                single[failing[0]] += 1
        res[side] = {"n": len(sub), "bar_same": int(sub.bar_same.sum()),
                     "condition_differs": dict(cnt.most_common()), "only_condition_differing": dict(single.most_common())}
    # causa por desacuerdo, en orden de prioridad
    def cause(r):
        if r.live_bar != r.rec_bar:
            return "1_vela_distinta_hoy"
        if r.live_price and r.rec_price and abs(r.live_price / r.rec_price - 1) > 0.003:
            return "2_misma_vela_precio_distinto(intradia)"
        if r.live["konc_alignment"] != r.rec["konc_alignment"]:
            return "3_koncorde_distinto"
        stale = len(set(r.live_hist_bars)) < len(r.live_hist_bars)
        if r.live_c["delta_3of5"] != r.rec_c["delta_3of5"] or r.live_c["above5"] != r.rec_c["above5"] or r.live_c["not_mature"] != r.rec_c["not_mature"]:
            return "4_historia_de_10_dias(" + ("velas_repetidas" if stale else "sin_repetidas") + ")"
        return "5_otro(redondeo/benchmark/macd)"
    for side, mask in (("only_live", dis.live_pass & ~dis.rec_pass), ("only_rec", dis.rec_pass & ~dis.live_pass)):
        res[side]["cause"] = dict(collections.Counter(dis[mask].apply(cause, axis=1)).most_common())
    # eventos (enfriamiento 10 días) en vivo, con su causa si no se reproducen el mismo día
    def events(S):
        out, last = [], {}
        for t, d in sorted(S, key=lambda x: x[1]):
            if t not in last or (pd.Timestamp(d) - pd.Timestamp(last[t])).days >= 10:
                out.append((t, d))
            last[t] = d
        return out
    Lp = set(zip(df[df.live_pass].ticker, df[df.live_pass].date))
    Rp = set(zip(df[df.rec_pass].ticker, df[df.rec_pass].date))
    EL, ER = events(Lp), events(Rp)
    near = lambda E, S: sum(1 for t, d in E if any(t == t2 and abs((pd.Timestamp(d) - pd.Timestamp(d2)).days) <= 3 for t2, d2 in S))
    res["events"] = {"live": len(EL), "rec": len(ER), "live_found_in_rec_pm3d": near(EL, Rp), "rec_found_in_live_pm3d": near(ER, Lp)}
    # magnitud de las diferencias de entradas cuando la vela es la misma
    same = df[(df.live_bar == df.rec_bar)]
    def diffs(k):
        a = [abs(r.live[k] - r.rec[k]) for _, r in same.iterrows() if r.live[k] is not None and r.rec[k] is not None]
        return {"n": len(a), "median": float(np.median(a)) if a else None, "p90": float(np.percentile(a, 90)) if a else None}
    res["input_diffs_same_bar"] = {k: diffs(k) for k in ("flowScore", "rsi", "m1", "delta5")}
    res["input_diffs_same_bar"]["konc_alignment_equal_pct"] = round(
        100 * float((same.apply(lambda r: r.live["konc_alignment"] == r.rec["konc_alignment"], axis=1)).mean()), 1)
    res["bar_lag_all_compared"] = {"n": len(df), "same_bar": int((df.live_bar == df.rec_bar).sum())}
    res["examples"] = dis.head(12)[["ticker", "date", "live_bar", "rec_bar", "live", "rec", "live_rs", "rec_rs"]].to_dict("records")
    json.dump(res, open(os.path.join(HERE, "repro_diag.json"), "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != "examples"}, indent=1, default=str))


if __name__ == "__main__":
    main()
