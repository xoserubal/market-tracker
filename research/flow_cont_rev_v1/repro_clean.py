"""Reproducibilidad con dato limpio (condición previa del §4): coincidencia, por (ticker, día), entre la evaluación
en vivo (código de producción sobre portfolio_daily_snapshot.jsonl) y la reconstruida (features.py, U2), solo en
los días en que el dato en vivo de toda la ventana usada (16 filas) es la vela de cierre correcta:
misma vela que la reconstrucción y precio a ±0,3 % del cierre. Ahí la regla y las entradas deberían coincidir; si no,
la diferencia es de la reconstrucción de las entradas (Flow, RSI, Koncorde, MACD) y no del retraso del dato.
Cubre Continuación y Reversión. No calcula rentabilidades. Salida: repro_clean.json
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

FIELDS = ["flowScore", "rsi", "konc_alignment", "macdHist", "macdHistDelta1", "atrPct", "price", "m1"]
HI = "2026-11-10"
WIN = 16


def main():
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

    bars = pickle.load(open(os.path.join(HERE, "_work", "U2_bars.pkl"), "rb"))
    px = pd.read_parquet(os.path.join(HERE, "data", "u2_prices.parquet"))
    px["date"] = pd.to_datetime(px.date)
    spy = px[px.ticker == "SPY"].set_index("date").sort_index().close
    spy_m1 = {k: float(np.floor(v * 100 + 0.5)) for k, v in (spy / spy.shift(21) - 1).dropna().items()}

    recs = []
    for t, rows in bars.items():
        if t not in snap:
            continue
        b = pd.DataFrame(rows).set_index("bar")
        cal = pd.date_range(b.index[0], b.index[-1], freq="D")
        pos = np.searchsorted(b.index.values, cal.values, side="right") - 1
        seq = [{**{k: rows[p][k] for k in FIELDS}, "date": cal[i].strftime("%Y-%m-%d"), "bar": rows[p]["bar"]}
               for i, p in enumerate(pos)]
        rmet = fsl.compute_series_metrics(seq)
        ridx = {m["date"]: i for i, m in enumerate(rmet)}
        sdates = sorted(snap[t])
        lseq = [{k: snap[t][d].get(k) for k in FIELDS} | {"date": d, "asOf": (snap[t][d].get("asOf") or "")[:10]}
                for d in sdates]
        lmet = fsl.compute_series_metrics(lseq)
        for i, lm in enumerate(lmet):
            d = lm["date"]
            if d < "2026-08-27" or d > HI or i < 5 or d not in ridx:
                continue
            j = ridx[d]
            # ventana limpia: todas las filas en vivo usadas tienen la vela y el precio de la reconstrucción
            clean = True
            for k in range(max(0, i - WIN + 1), i + 1):
                dd = lmet[k]["date"]
                if dd not in ridx:
                    clean = False
                    break
                rr = rmet[ridx[dd]]
                if lmet[k]["asOf"] != rr["bar"].strftime("%Y-%m-%d") or not lmet[k]["price"] or \
                        abs(lmet[k]["price"] / rr["price"] - 1) > 0.003:
                    clean = False
                    break
            rm = rmet[j]
            rbm = spy_m1.get(rm["bar"])
            rrs = None if rbm is None or rm["m1"] is None else round(rm["m1"] - rbm, 2)
            lbm = bm(d)
            lrs = None if lbm is None or lm["m1"] is None else round(lm["m1"] - lbm, 2)
            lt, rt = lmet[max(0, i - 15):i + 1], rmet[max(0, j - 15):j + 1]
            recs.append({
                "ticker": t, "date": d, "clean": clean,
                "cont_live": fsl.evaluate_continuacion(lm, lt, lrs, t)["pass"],
                "cont_rec": fsl.evaluate_continuacion(rm, rt, rrs, t)["pass"],
                "rev_live": fsl.evaluate_reversion(lm, lt)["pass"],
                "rev_rec": fsl.evaluate_reversion(rm, rt)["pass"],
                "konc_eq": lm.get("konc_alignment") == rm.get("konc_alignment"),
                "flow_diff": None if lm["flowScore"] is None or rm["flowScore"] is None
                else abs(lm["flowScore"] - rm["flowScore"]),
            })
    df = pd.DataFrame(recs)
    res = {"period": ["2026-08-27", HI], "ticker_days": len(df), "clean_ticker_days": int(df.clean.sum())}
    for name, sub in (("clean", df[df.clean]), ("all", df)):
        out = {"n": len(sub), "konc_alignment_equal_pct": round(100 * sub.konc_eq.mean(), 1),
               "flow_abs_diff_median": float(sub.flow_diff.median()), "flow_abs_diff_p90": float(sub.flow_diff.quantile(.9))}
        for f in ("cont", "rev"):
            L, R = sub[f + "_live"], sub[f + "_rec"]
            both, lo, ro = int((L & R).sum()), int((L & ~R).sum()), int((R & ~L).sum())
            out[f] = {"live": int(L.sum()), "rec": int(R.sum()), "both": both, "only_live": lo, "only_rec": ro,
                      "jaccard_pct": round(100 * both / max(1, both + lo + ro), 1),
                      "day_agreement_pct": round(100 * float((L == R).mean()), 2)}
        res[name] = out
    log = pd.read_json(os.path.join(ROOT, "docs", "data", "screener_signal_log.jsonl"), lines=True)
    log["date"] = pd.to_datetime(log.date).dt.strftime("%Y-%m-%d")
    for f, col in (("flow_continuacion", "cont_live"), ("flow_reversion", "rev_live")):
        Lg = set(zip(log[(log["filter"] == f) & (log.date <= HI)].ticker, log[(log["filter"] == f) & (log.date <= HI)].date))
        Rp = set(zip(df[df[col]].ticker, df[df[col]].date))
        res["log_vs_replay_" + f] = {"log": len(Lg), "replay": len(Rp), "both": len(Lg & Rp),
                                     "log_only": sorted(Lg - Rp)[:10], "replay_only": sorted(Rp - Lg)[:10]}
    dis = df[df.clean & ((df.cont_live != df.cont_rec) | (df.rev_live != df.rev_rec))]
    res["clean_disagreements"] = dis.to_dict("records")
    json.dump(res, open(os.path.join(HERE, "repro_clean.json"), "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != "clean_disagreements"}, indent=1))
    print(dis[["ticker", "date", "cont_live", "cont_rec", "rev_live", "rev_rec", "konc_eq", "flow_diff"]].to_string())


if __name__ == "__main__":
    main()
