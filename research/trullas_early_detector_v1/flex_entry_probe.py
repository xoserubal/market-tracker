"""Sonda rápida (2026-10-09): ¿qué pasa si la zona de entrada de Trullás se flexibiliza?
Misma señal (evaluate_pivot_pair), misma salida (stop pivote / TP 38.2% / time stop), solo cambia
qué aperturas valen como entrada: open en [low_pivot + f_min*rango, entry_high]. f_min=0.23 = estricto."""
import sys, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest as B
tl = B.tl
cache = B.load_cache()

def run(f_min, ceil_mult=1.0, start_off=1):
    trades = []
    for tk, df in cache.items():
        close = df["Close"].to_numpy(); open_ = df["Open"].to_numpy(); vol = df["Volume"].to_numpy()
        dates = df["Date"].to_numpy(); n = len(close)
        macd_arr = tl.macd_full(df["Close"])[0].to_numpy(); rsi_arr = tl.rsi(df["Close"]).to_numpy()
        piv = tl.find_pivots_low(close)
        for a, b in zip(piv, piv[1:]):
            ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
            if not ev.get("qualifies"): continue
            lowp = close[b]; rng = close[a] - close[b]
            lo = lowp + f_min * rng; hi = ev["entry_high"] * ceil_mult
            tp, stop = ev["tp"], ev["stop"]
            fill = None
            for j in range(b + start_off, min(b + 1 + tl.ENTRY_WINDOW_BARS, n)):
                if open_[j] <= stop: break
                if lo <= open_[j] <= hi: fill = j; break
            if fill is None: continue
            ep = open_[fill]; end = min(fill + tl.TIME_STOP_BARS, n); ex = None
            for k in range(fill, end):
                if close[k] <= stop: ex, why = k, "stop"; break
                if close[k] >= tp: ex, why = k, "tp"; break
            if ex is None: ex, why = end - 1, "time"
            trades.append((tk, str(dates[fill]), (close[ex] - ep) / ep * 100, why, ev["tier"]))
    return trades

def show(label, tr):
    r = np.array([t[2] for t in tr])
    print(f"{label:34s} n={len(r):3d} mean={r.mean():+.2f}% (-1pp coste {r.mean()-1:+.2f}%) med={np.median(r):+.2f}% win={100*(r>0).mean():.0f}% "
          f"worst={r.min():.1f}% sharpe~={r.mean()/r.std():.3f} stop={100*sum(t[3]=='stop' for t in tr)/len(tr):.0f}%")

off = tl.PIVOT_WINDOW + 1
print("== SIN look-ahead, tolerancia pequeña por debajo de la zona ==")
for f in (0.23, 0.22, 0.21, 0.20, 0.18):
    show(f"retroceso >= {int(f*100)}% (techo 25%)", run(f, start_off=off))
