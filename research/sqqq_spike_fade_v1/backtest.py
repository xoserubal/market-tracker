"""
SQQQ spike-fade — ¿qué definición de "giro" sirve? Solo investigación.

PREREGISTRO (fijado antes de mirar resultados, 2026-11-17):
- Datos: SQQQ y QQQ diarios (yfinance, splits ajustados), 2010-02 -> hoy.
  Señales desde 2011-01 (warmup). Dev = hasta 2018-12-31; Test = desde 2019-01-01.
- Señal al CIERRE de t; entrada a la APERTURA de t+1. Cooldown 10 sesiones.
- Resultado: retorno de SQQQ a 5/10/21/42/63 sesiones desde la entrada (bueno para
  el vendedor de prima = que BAJE) y MAE = máxima subida de SQQQ (cierres) en 21 y
  63 sesiones. P(MAE21>=30%) ~ riesgo de tocar una call vendida a +30%.
- Regla de producción (shared/inverse-etf-lib.js): extendido (dist SMA20 >= 1.5 ATR o
  m1 >= 25%) + giro (d1<0 y Δhist MACD<0) + QQQ w1 >= +2.5%.
- Variantes del GIRO (todo lo demás igual):
    G0 sin giro | G1 producción (1 día) | G2 dos sesiones seguidas con d1<0 y Δhist<0 |
    G3 histograma MACD ya < 0 | G4 cierre < mínimo de las 3 sesiones previas
  y las mismas sin el filtro de QQQ (para ver qué aporta cada pieza).
- Baselines: (a) todos los días, (b) solo "extendido".
- Una variante solo cuenta como mejor si mejora en dev Y en test con n>=8 por tramo.
  Todo descriptivo: sin corrección por comparaciones múltiples; n efectivo < nominal
  (eventos agrupados en pocos episodios bajistas).
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd
import yfinance as yf

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

START, SIGNAL_FROM, SPLIT = "2010-02-01", "2011-01-01", "2019-01-01"
COOLDOWN = 10
H = (5, 10, 21, 42, 63)


def load():
    s = yf.download("SQQQ", start=START, auto_adjust=False, progress=False)
    q = yf.download("QQQ", start=START, auto_adjust=False, progress=False)
    for d in (s, q):
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    return pd.DataFrame({"o": s["Open"], "h": s["High"], "l": s["Low"], "c": s["Close"], "qqq": q["Close"]}).dropna()


def ema(x, n): return x.ewm(span=n, adjust=False).mean()


def features(df):
    c = df["c"]
    tr = pd.concat([df["h"] - df["l"], (df["h"] - c.shift()).abs(), (df["l"] - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    macd = ema(c, 12) - ema(c, 26)
    hist = macd - ema(macd, 9)
    df = df.copy()
    df["dist_atr"] = (c - c.rolling(20).mean()) / atr
    df["m1"] = c.pct_change(21) * 100
    df["d1"] = c.pct_change() * 100
    df["hist"] = hist
    df["dhist"] = hist.diff()
    df["qqq_w1"] = df["qqq"].pct_change(5) * 100
    df["low3"] = c.shift(1).rolling(3).min()
    return df


def giro(df, g):
    r1 = (df["d1"] < 0) & (df["dhist"] < 0)
    return {"G0": pd.Series(True, index=df.index), "G1": r1, "G2": r1 & r1.shift(1, fill_value=False),
            "G3": df["hist"] < 0, "G4": df["c"] < df["low3"]}[g]


def signal(df, g="G1", cool=True, ext=True):
    e = (df["dist_atr"] >= 1.5) | (df["m1"] >= 25) if ext else True
    c = df["qqq_w1"] >= 2.5 if cool else True
    return (e & giro(df, g) & c).fillna(False)


def events(df, sig):
    idx, last = [], -10**9
    pos = np.flatnonzero(sig.values)
    for p in pos:
        if df.index[p] < pd.Timestamp(SIGNAL_FROM) or p - last <= COOLDOWN or p + 1 >= len(df): continue
        idx.append(p); last = p
    rows = []
    c, o = df["c"].values, df["o"].values
    for p in idx:
        e = o[p + 1]
        r = {"date": df.index[p]}
        for h in H:
            j = p + h
            r[f"r{h}"] = (c[j] / e - 1) * 100 if j < len(c) else np.nan
        for h in (21, 63):
            w = c[p + 1: p + 1 + h]
            r[f"mae{h}"] = (w.max() / e - 1) * 100 if len(w) == h else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def summ(ev, label):
    if ev.empty: return f"{label:34s} n=0"
    out = [f"{label:34s} n={len(ev):3d}"]
    for h in (10, 21, 63):
        x = ev[f"r{h}"].dropna()
        if len(x): out.append(f"r{h} med {x.median():+6.1f} baja {100*(x<0).mean():3.0f}%")
    m = ev["mae21"].dropna()
    if len(m): out.append(f"MAE21 p≥30 {100*(m>=30).mean():3.0f}% max {m.max():5.0f}")
    m = ev["mae63"].dropna()
    if len(m): out.append(f"MAE63 p≥30 {100*(m>=30).mean():3.0f}%")
    return " | ".join(out)


def main():
    df = features(load())
    print(f"Datos {df.index[0].date()} -> {df.index[-1].date()}  ({len(df)} sesiones)\n")
    alld = pd.Series(True, index=df.index)
    cases = [("Baseline: todos los días", alld, 0), ("Baseline: solo extendido", signal(df, "G0", cool=False), 10)]
    for g in ("G0", "G1", "G2", "G3", "G4"):
        cases.append((f"ext+{g}+QQQ enfría", signal(df, g, True), COOLDOWN))
    for g in ("G1", "G2", "G3", "G4"):
        cases.append((f"ext+{g} (sin QQQ)", signal(df, g, False), COOLDOWN))
    global COOLDOWN_
    for name, sig, cd in cases:
        old = globals()["COOLDOWN"]; globals()["COOLDOWN"] = cd
        ev = events(df, sig); globals()["COOLDOWN"] = old
        dev, tst = ev[ev.date < SPLIT] if len(ev) else ev, ev[ev.date >= SPLIT] if len(ev) else ev
        print(name); print("   DEV  " + summ(dev, "")); print("   TEST " + summ(tst, ""))
    print("\nEventos de la regla de producción (ext+G1+QQQ):")
    ev = events(df, signal(df, "G1", True))
    print(ev.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
