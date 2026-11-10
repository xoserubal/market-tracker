"""Reconstruye por valor y día (sin mirar al futuro) las entradas de los filtros del preregistro.
Salidas en _work/ (gitignored):
  features.parquet   — por (fecha, valor): hc, lz, konc d/3d/w, A, D, E, F y entradas de Early Flow
  earlyflow_in.csv   — entradas para shared/flow-score.js (las procesa early_flow.js)
  sector_in.json     — ratios ETF sectorial / SPY (los procesa sector_regime.js)
"""
import importlib.util
import json
import os
import sys
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import koncorde_calculator as kc  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "bt", os.path.join(ROOT, "research", "macd_combo_sp500_ndx_v1", "backtest.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

WORK = "_work"
os.makedirs(WORK, exist_ok=True)


def states(blue, green):
    out = np.full(len(blue), None, dtype=object)
    ok = ~np.isnan(blue) & ~np.isnan(green)
    for i in np.flatnonzero(ok):
        out[i] = kc._state(float(blue[i]), float(green[i]))
    return out


def konc_states(df, min_bars):
    """Estado por barra de una serie OHLCV (None si hay menos de min_bars barras hasta ahí)."""
    o, h, l, c, v = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close", "volume"))
    blue, green, _, _ = kc._calc_koncorde_plus(o, h, l, c, v)
    st = states(blue, green)
    st[: min_bars - 1] = None
    return st


def konc_daily_3d_weekly(adj):
    n = len(adj)
    sd = konc_states(adj, kc.MIN_BARS)
    s3 = np.full(n, None, dtype=object)
    for r in range(3):
        ends = np.arange(r, n)
        ends = ends[(ends % 3 == r) & (ends >= 2)]
        if len(ends) == 0:
            continue
        rows = [{"open": adj.open.iat[j - 2], "high": adj.high.iloc[j - 2:j + 1].max(),
                 "low": adj.low.iloc[j - 2:j + 1].min(), "close": adj.close.iat[j],
                 "volume": adj.volume.iloc[j - 2:j + 1].sum()} for j in ends]
        st = konc_states(pd.DataFrame(rows), kc.MIN_BARS)
        s3[ends] = st
    wk = adj.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                    "volume": "sum"}).dropna(subset=["close"])
    sw_bins = konc_states(wk, 100)
    labels = wk.index.values
    pos = np.searchsorted(labels, adj.index.values, side="right") - 1   # última semana con viernes <= fecha
    sw = np.array([sw_bins[p] if p >= 0 else None for p in pos], dtype=object)
    return sd, s3, sw


def wilder_rsi(c, p=14):
    out = np.full(len(c), np.nan)
    if len(c) < p + 1:
        return out
    d = np.diff(c)
    g, lo = np.maximum(d, 0), np.maximum(-d, 0)
    ag, al = g[:p].mean(), lo[:p].mean()
    out[p] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(p, len(d)):
        ag = (ag * (p - 1) + g[i]) / p
        al = (al * (p - 1) + lo[i]) / p
        out[i + 1] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def js_round(x):
    """Math.round de JS (mitades hacia +inf)."""
    return np.floor(x + 0.5)


def main():
    px = pd.read_parquet("prices_cache.parquet")
    sectors = json.load(open("sectors.json"))
    spy = px[px.ticker == "SPY"].set_index("date").sort_index()
    cal = spy.index
    spy_c = spy.close
    spy_ret63 = spy_c / spy_c.shift(63) - 1
    s200 = spy_c.rolling(200).mean()
    mkt_ok = (spy_c > s200) & s200.notna()

    # ratios sectoriales para Node
    sec_in = {}
    for etf in sectors["etf"].values():
        e = px[px.ticker == etf].set_index("date").sort_index().close
        al = pd.concat([e, spy_c], axis=1, join="inner").dropna()
        sec_in[etf] = [{"date": str(d.date()), "value": float(a / b)} for d, (a, b) in al.iterrows()]
    json.dump(sec_in, open(f"{WORK}/sector_in.json", "w"))

    feats, ef_lines = [], ["ticker,date,kd,pkd,k3,pk3,kw,atr,patr,fh,rsi,w1,m1"]
    uni = sorted(sectors["sector"])
    for n_t, t in enumerate(uni):
        d = px[px.ticker == t].set_index("date").sort_index()
        d = d[~d.index.duplicated()]
        if len(d) < 250:
            continue
        ind = bt.indicators(d[["high", "low", "close"]])
        f = d.adj_close / d.close
        adj = pd.DataFrame({"open": d.open * f, "high": d.high * f, "low": d.low * f, "close": d.adj_close,
                            "volume": d.volume.fillna(0)}, index=d.index)
        sd, s3, sw = konc_daily_3d_weekly(adj)

        c = d.close.to_numpy(float)
        atr = bt.wilder_atr(c, d.high.to_numpy(float), d.low.to_numpy(float))
        atr_pct = np.round(atr / c * 100, 1)
        sma20 = pd.Series(c).rolling(20).mean().to_numpy()
        rsi = js_round(wilder_rsi(c))
        hi365 = d.close.rolling("365D").max().to_numpy()
        fh = js_round((c - hi365) / hi365 * 100)
        w1 = np.full(len(c), np.nan); w1[5:] = js_round((c[5:] / c[:-5] - 1) * 100)
        m1 = np.full(len(c), np.nan); m1[21:] = js_round((c[21:] / c[:-21] - 1) * 100)
        ret63 = np.full(len(c), np.nan); ret63[63:] = c[63:] / c[:-63] - 1

        A = np.array([(a is not None and b is not None and a != "distribution" and b != "distribution")
                      for a, b in zip(s3, sw)])
        with np.errstate(invalid="ignore", divide="ignore"):
            Dx = ((c - sma20) / atr) < 1.5
        E = (ret63 - spy_ret63.reindex(d.index).to_numpy()) > 0
        F = mkt_ok.reindex(d.index).fillna(False).to_numpy()

        fr = pd.DataFrame({"date": d.index, "ticker": t, "hc": ind["hc"].to_numpy(), "lz": ind["lz"].to_numpy(),
                           "kd": sd, "k3": s3, "kw": sw, "A": A, "D": Dx, "E": E, "F": F,
                           "sector_etf": sectors["etf"][sectors["sector"][t]]})
        feats.append(fr)

        def s(x):
            return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x)

        for i in range(1, len(c)):
            ef_lines.append(",".join([t, str(d.index[i].date()), s(sd[i]), s(sd[i - 1]), s(s3[i]), s(s3[i - 1]),
                                      s(sw[i]), s(atr_pct[i]), s(atr_pct[i - 1]),
                                      s(None if np.isnan(fh[i]) else int(fh[i])),
                                      s(None if np.isnan(rsi[i]) else int(rsi[i])),
                                      s(None if np.isnan(w1[i]) else int(w1[i])),
                                      s(None if np.isnan(m1[i]) else int(m1[i]))]))
        if n_t % 50 == 0:
            print(n_t, t, flush=True)

    out = pd.concat(feats)
    for k in ("kd", "k3", "kw"):
        out[k] = out[k].astype("string")
    out.to_parquet(f"{WORK}/features.parquet")
    with open(f"{WORK}/earlyflow_in.csv", "w") as fh_:
        fh_.write("\n".join(ef_lines))
    print("filas", len(out), "valores", out.ticker.nunique())


if __name__ == "__main__":
    main()
