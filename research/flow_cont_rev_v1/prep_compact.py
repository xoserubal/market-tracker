"""Preparación para el contraste (sin cambiar ninguna regla): recorre los valores uno a uno con las mismas funciones de
features.py (ticker_bars, candidates) para no cargar en memoria todo U*_bars.pkl, y guarda:
- _work/{U}_ses_cands.parquet  candidatos por sesiones (versión B), idéntico a `features.py U --sessions`
- _work/{U}_compact.pkl        por valor, arrays de la serie: fecha, precio (cierre sin dividendos), cierre y apertura
                               ajustados por dividendos, ATR%.
Uso: py -3 prep_compact.py U1|U2
"""
import gc
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F  # noqa: E402


def main():
    u = sys.argv[1]
    px = pd.read_parquet(F.SOURCES[u], columns=["date", "open", "high", "low", "close", "adj_close", "volume", "ticker"])
    px["date"] = pd.to_datetime(px.date)
    if u == "U1":
        import json
        uni = set(json.load(open(os.path.join(F.ROOT, "research", "macd_combo_filters_v1", "sectors.json")))["sector"])
    else:
        uni = set(px.ticker.unique())
    spy = px[px.ticker == "SPY"].set_index("date").sort_index().close
    spy_m1 = dict(zip(spy.index, F.js_round((spy / spy.shift(21) - 1) * 100)))
    spy_m1 = {k: float(v) for k, v in spy_m1.items() if not np.isnan(v)}
    compact, cands = {}, []
    for n, (t, d) in enumerate(px[px.ticker.isin(uni)].groupby("ticker")):
        rows = F.ticker_bars(d)
        if not rows:
            continue
        dd = d.set_index("date").sort_index()
        dd = dd[~dd.index.duplicated()].dropna(subset=["close"])
        assert len(dd) == len(rows) and dd.index[-1] == rows[-1]["bar"], t
        f = (dd.adj_close / dd.close).to_numpy(float)
        compact[t] = {
            "bar": dd.index.values,
            "price": np.array([r["price"] for r in rows], float),
            "adj": dd.adj_close.to_numpy(float),
            "adj_open": dd.open.to_numpy(float) * f,
            "atr": np.array([np.nan if r["atrPct"] is None else r["atrPct"] for r in rows], float),
        }
        cands += F.candidates(t, rows, spy_m1, sessions=True)
        del rows
        if n % 50 == 0:
            gc.collect()
            print(u, n, t, flush=True)
    pickle.dump(compact, open(os.path.join(F.W, f"{u}_compact.pkl"), "wb"))
    df = pd.DataFrame(cands, columns=["ticker", "date", "bar", "cont", "rev"])
    df.to_parquet(os.path.join(F.W, f"{u}_ses_cands.parquet"))
    print(u, "tickers", len(compact), "candidatos por sesiones", len(df), "cont", int(df.cont.sum()), "rev", int(df.rev.sum()))


if __name__ == "__main__":
    main()
