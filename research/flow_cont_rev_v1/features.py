"""Reconstruye, sin mirar al futuro, las entradas de los filtros Flow Continuación / Reversión y sus candidatos por día
de calendario (como el registro en vivo). No calcula rentabilidades. Preregistro: wiki/PREREGISTRO_FLOW_CONT_REV_V1.md
Uso: py -3 features.py U1|U2 [--sessions]   → _work/{U}[_ses]_cands.parquet, _work/{U}_bars.pkl"""
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import koncorde_calculator as kc  # noqa: E402
import flow_state_lib as fsl  # noqa: E402

W = os.path.join(HERE, "_work")
os.makedirs(W, exist_ok=True)
SOURCES = {"U1": os.path.join(ROOT, "research", "macd_combo_filters_v1", "prices_cache.parquet"),
           "U2": os.path.join(HERE, "data", "u2_prices.parquet")}
MIN_BARS_DW = kc.MIN_BARS      # 120 barras para D y 3D, como producción
MIN_BARS_W = 100               # semanal: como research/macd_combo_filters_v1 (validado 42/42 contra producción)
KMAP = {"up": 2, "accumulation": 1, "distribution": -1, "down": -2}


def js_round(x):
    return np.floor(np.asarray(x, float) + 0.5)


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


def wilder_atr(c, h, l, p=14):
    tr = np.full(len(c), np.nan)
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    out = np.full(len(c), np.nan)
    if len(c) <= p:
        return out
    a = np.nanmean(tr[1:p + 1])
    out[p] = a
    for i in range(p + 1, len(c)):
        a = (a * (p - 1) + tr[i]) / p
        out[i] = a
    return out


def ema_full(x, p):
    out = np.full(len(x), np.nan)
    if len(x) < p:
        return out
    k = 2 / (p + 1)
    e = x[:p].mean()
    out[p - 1] = e
    for i in range(p, len(x)):
        e = x[i] * k + e * (1 - k)
        out[i] = e
    return out


def macd_hist(c):
    m = ema_full(c, 12) - ema_full(c, 26)
    valid = np.flatnonzero(~np.isnan(m))
    sig = np.full(len(c), np.nan)
    if len(valid) >= 9:
        sig[valid[0]:] = ema_full(m[valid[0]:], 9)
    return m - sig


def konc_blocks(df):
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    blue, green, _, _ = kc._calc_koncorde_plus(o, h, l, c, v)
    return blue, green


def konc_all(adj):
    """Estados D, 3D (bloque que acaba en la vela), W (última semana cerrada) y blue_down_2_bars del 3D."""
    n = len(adj)
    blue, green = konc_blocks(adj)
    sd = np.array([kc._state(float(b), float(g)) if i >= MIN_BARS_DW - 1 and not (np.isnan(b) or np.isnan(g)) else None
                   for i, (b, g) in enumerate(zip(blue, green))], dtype=object)
    s3 = np.full(n, None, dtype=object)
    d3 = np.zeros(n, bool)
    roll = pd.DataFrame({"open": adj.open.shift(2), "high": adj.high.rolling(3).max(), "low": adj.low.rolling(3).min(),
                         "close": adj.close, "volume": adj.volume.rolling(3).sum()}).reset_index(drop=True)
    for r in range(3):
        ends = np.arange(n)
        ends = ends[(ends % 3 == r) & (ends >= 2)]
        if not len(ends):
            continue
        blk = roll.iloc[ends].reset_index(drop=True)
        b3, g3 = konc_blocks(blk)
        for k, j in enumerate(ends):
            if k >= MIN_BARS_DW - 1 and not (np.isnan(b3[k]) or np.isnan(g3[k])):
                s3[j] = kc._state(float(b3[k]), float(g3[k]))
                d3[j] = bool(k >= 2 and b3[k] < b3[k - 1] < b3[k - 2])
    wk = adj.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
                                   ).dropna(subset=["close"])
    bw, gw = konc_blocks(wk)
    sw_bins = np.array([kc._state(float(b), float(g)) if i >= MIN_BARS_W - 1 and not (np.isnan(b) or np.isnan(g)) else None
                        for i, (b, g) in enumerate(zip(bw, gw))], dtype=object)
    pos = np.searchsorted(wk.index.values, adj.index.values, side="right") - 1
    sw = np.array([sw_bins[p] if p >= 0 else None for p in pos], dtype=object)
    align = np.array([kc._konc_alignment(a, b, c, bool(dd)) for a, b, c, dd in zip(sd, s3, sw, d3)], dtype=object)
    return sd, s3, sw, align


def flow_score(w1, m1, rsi, macd_bull, atr, kd, kw, fh):
    """Réplica de computeFlowScore (shared/flow-score.js)."""
    m = (w1 or 0) * 0.6 + (m1 or 0) * 0.4
    r = 0
    if rsi is not None:
        r += 2 if rsi > 65 else 1 if rsi > 55 else 0
    if macd_bull is True:
        r += 1
    elif macd_bull is False:
        r -= 1
    atr = atr or 0
    a = 1 if 1 <= atr <= 3 else 0.5 if 3 < atr <= 6 else -0.5 if atr > 6 else 0
    k = KMAP.get(kd, 0) + KMAP.get(kw, 0) * 0.5
    fh = fh or 0
    t = 1 if -10 <= fh <= 0 else 0 if -25 <= fh < -10 else -1
    return float(np.floor(((m * 2) + r + a + k + t) * 100 + 0.5) / 100)


def nz(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else x


def ticker_bars(d):
    d = d.set_index("date").sort_index()
    d = d[~d.index.duplicated()].dropna(subset=["close"])
    if len(d) < 60:
        return None
    f = d.adj_close / d.close
    adj = pd.DataFrame({"open": d.open * f, "high": d.high * f, "low": d.low * f, "close": d.adj_close,
                        "volume": d.volume.fillna(0)}, index=d.index)
    sd, s3, sw, align = konc_all(adj)
    c, h, l = (d[k].to_numpy(float) for k in ("close", "high", "low"))
    atr = wilder_atr(c, h, l)
    atrp = np.round(atr / c * 100, 1)
    rsi = js_round(wilder_rsi(c))
    hi = d.close.rolling("365D").max().to_numpy()
    fh = js_round((c - hi) / hi * 100)
    w1 = np.full(len(c), np.nan); w1[5:] = js_round((c[5:] / c[:-5] - 1) * 100)
    m1 = np.full(len(c), np.nan); m1[21:] = js_round((c[21:] / c[:-21] - 1) * 100)
    hist = macd_hist(c)
    hd1 = np.full(len(c), np.nan); hd1[1:] = hist[1:] - hist[:-1]
    rows = []
    for i in range(len(c)):
        mb = None if np.isnan(hist[i]) else bool(hist[i] >= 0)
        row = {"bar": d.index[i], "price": float(c[i]), "adj": float(d.adj_close.iat[i]),
               "atrPct": nz(float(atrp[i])), "rsi": nz(float(rsi[i])), "m1": nz(float(m1[i])),
               "macdHist": nz(float(hist[i])), "macdHistDelta1": nz(float(hd1[i])), "konc_alignment": align[i]}
        row["flowScore"] = flow_score(nz(float(w1[i])), row["m1"], row["rsi"], mb, row["atrPct"], sd[i], sw[i],
                                      nz(float(fh[i])))
        rows.append(row)
    return rows


def candidates(t, rows, spy_m1, sessions):
    """Candidatos de Continuación y Reversión por día (calendario, como producción; o sesiones)."""
    bars = pd.DataFrame(rows).set_index("bar")
    if sessions:
        cal = bars.index
    else:
        cal = pd.date_range(bars.index[0], bars.index[-1], freq="D")
    pos = np.searchsorted(bars.index.values, cal.values, side="right") - 1
    seq = []
    for k, p in enumerate(pos):
        r = rows[p]
        seq.append({"date": cal[k], "bar": r["bar"], "flowScore": r["flowScore"], "rsi": r["rsi"],
                    "konc_alignment": r["konc_alignment"], "macdHist": r["macdHist"],
                    "macdHistDelta1": r["macdHistDelta1"], "atrPct": r["atrPct"], "price": r["price"], "m1": r["m1"]})
    met = fsl.compute_series_metrics(seq)
    out = []
    for i in range(5, len(met)):
        today = met[i]
        tail = met[max(0, i - 15):i + 1]
        bm = spy_m1.get(today["bar"])
        rs = None if bm is None or today["m1"] is None else round(today["m1"] - bm, 2)
        cont = fsl.evaluate_continuacion(today, tail, rs, t)["pass"] if bm is not None else False
        rev = fsl.evaluate_reversion(today, tail)["pass"]
        if cont or rev:
            out.append((t, today["date"], today["bar"], bool(cont), bool(rev)))
    return out


def main():
    u = sys.argv[1]
    sessions = "--sessions" in sys.argv
    px = pd.read_parquet(SOURCES[u])
    px["date"] = pd.to_datetime(px.date)
    if u == "U1":
        import json
        uni = set(json.load(open(os.path.join(ROOT, "research", "macd_combo_filters_v1", "sectors.json")))["sector"])
    else:
        uni = set(px.ticker.unique())
    spy = px[px.ticker == "SPY"].set_index("date").sort_index().close
    spy_m1 = dict(zip(spy.index, js_round((spy / spy.shift(21) - 1) * 100)))
    spy_m1 = {k: float(v) for k, v in spy_m1.items() if not np.isnan(v)}
    bars_file = os.path.join(W, f"{u}_bars.pkl")
    if os.path.exists(bars_file):
        allbars = pickle.load(open(bars_file, "rb"))
    else:
        allbars = {}
        for n, (t, d) in enumerate(px[px.ticker.isin(uni)].groupby("ticker")):
            r = ticker_bars(d)
            if r:
                allbars[t] = r
            if n % 50 == 0:
                print(u, n, t, flush=True)
        pickle.dump(allbars, open(bars_file, "wb"))
    cands = []
    for t, rows in allbars.items():
        cands += candidates(t, rows, spy_m1, sessions)
    df = pd.DataFrame(cands, columns=["ticker", "date", "bar", "cont", "rev"])
    df.to_parquet(os.path.join(W, f"{u}{'_ses' if sessions else ''}_cands.parquet"))
    print(u, "sesiones" if sessions else "calendario", "tickers", len(allbars), "filas candidatas", len(df),
          "cont", int(df.cont.sum()), "rev", int(df.rev.sum()))


if __name__ == "__main__":
    main()
