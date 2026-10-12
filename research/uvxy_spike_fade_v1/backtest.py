"""
UVXY spike-fade — backtest de calibración (5 años). Solo investigación.

Pregunta: ¿las condiciones de shared/inverse-etf-lib.js para UVXY (ETF extendido
+ girando a la baja + VIX alto y enfriándose) anticipan una caída posterior de
UVXY, y con qué cola adversa? No backtestea opciones (no hay IV histórica
gratuita): mide el movimiento del subyacente, que es lo que decide una put
spread + call vendida (la call del tuit estaba a +32% del spot).

PREREGISTRO (fijado antes de mirar resultados):
- Datos: UVXY y ^VIX diarios, yfinance, 2020-10 → hoy (warmup incluido). 5 años de
  señales: desde 2021-10. UVXY es 1,5x todo el periodo (cambió de 2x en 2018).
- Señal evaluada al CIERRE del día t; entrada a la APERTURA de t+1 (sin look-ahead).
- Evento independiente: cooldown de 10 sesiones tras cada señal.
- Salidas: retorno de UVXY a 5, 10 y 21 sesiones desde la entrada (ganar = que BAJE
  si vendes prima/estás corto), y MAE = máxima subida de UVXY (sobre cierres) dentro
  de 21 sesiones desde la entrada. P(MAE >= 30%) ~ riesgo de que la call vendida a +32% se toque.
- Regla base = la actual del lib: ext_atr=1.5 (o m1>=25%), rolling (d1<0 y Δhist MACD<0),
  VIX>=25 y VIX 5 sesiones <= -10%.
- Calibración = sensibilidad de UN parámetro cada vez (el resto en la regla base), no rejilla
  completa (pocos eventos; evitar sobreajuste). Parámetros: ext_atr {1.0,1.5,2.0,2.5},
  vix_min {0,20,25,30}, vix_cool {0,5,10,15}, rolling {on,off}.
- Dev = señales hasta 2024-06-30; Test = desde 2024-07-01 (incluye ago-2024 y abr-2025).
  Una variante solo se considera mejor si mejora en dev Y en test, con n>=8 por tramo.
- Baselines: (a) todos los días, (b) solo "VIX>=25" sin más condiciones.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
import yfinance as yf

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

START, SIGNAL_FROM, SPLIT = "2020-10-01", "2021-10-01", "2024-07-01"
COOLDOWN = 10
HORIZONS = (5, 10, 21)


def load():
    u = yf.download("UVXY", start=START, auto_adjust=False, progress=False)
    v = yf.download("^VIX", start=START, auto_adjust=False, progress=False)
    for d in (u, v):
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
    df = pd.DataFrame({"o": u["Open"], "h": u["High"], "l": u["Low"], "c": u["Close"], "vix": v["Close"]}).dropna()
    return df


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def features(df):
    c = df["c"]
    tr = pd.concat([df["h"] - df["l"], (df["h"] - c.shift()).abs(), (df["l"] - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    sma20 = c.rolling(20).mean()
    macd = ema(c, 12) - ema(c, 26)
    hist = macd - ema(macd, 9)
    df = df.copy()
    df["dist_atr"] = (c - sma20) / atr
    df["m1"] = c.pct_change(21) * 100
    df["d1"] = c.pct_change() * 100
    df["dhist"] = hist.diff()
    df["vix_w1"] = df["vix"].pct_change(5) * 100
    return df


def signal(df, ext_atr=1.5, ext_m1=25, rolling=True, vix_min=25, vix_cool=10):
    ext = (df["dist_atr"] >= ext_atr) | (df["m1"] >= ext_m1)
    roll = (df["d1"] < 0) & (df["dhist"] < 0) if rolling else True
    cool = (df["vix_w1"] <= -vix_cool) if vix_cool > 0 else True
    lvl = df["vix"] >= vix_min
    return (ext & roll & cool & lvl).fillna(False)


def events(df, mask):
    idx, last = [], -10**9
    pos = {d: i for i, d in enumerate(df.index)}
    for d in df.index[mask.values]:
        i = pos[d]
        if d < pd.Timestamp(SIGNAL_FROM) or i - last < COOLDOWN or i + 1 >= len(df):
            continue
        idx.append(i)
        last = i
    return idx


def outcomes(df, idxs):
    rows = []
    o, c = df["o"].values, df["c"].values
    for i in idxs:
        e = i + 1                      # entrada: apertura del día siguiente
        entry = o[e]
        r = {"date": df.index[i], "entry": entry}
        for h in HORIZONS:
            r[f"ret{h}"] = (c[e + h - 1] / entry - 1) * 100 if e + h - 1 < len(df) else np.nan
        w = c[e:e + 21]
        r["mae21"] = (w.max() / entry - 1) * 100 if len(w) >= 21 else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def summarize(ev, label):
    if ev.empty:
        return f"{label:<34} n=0"
    out = [f"{label:<34} n={len(ev):<3}"]
    for h in (10, 21):
        s = ev[f"ret{h}"].dropna()
        if len(s):
            out.append(f"r{h}: med {s.median():+6.1f}% medio {s.mean():+6.1f}% bajó {100*(s<0).mean():3.0f}%")
    m = ev["mae21"].dropna()
    if len(m):
        out.append(f"MAE21: med {m.median():4.0f}% máx {m.max():4.0f}% P(>=30%) {100*(m>=30).mean():3.0f}%")
    return " | ".join(out)


def run(df, label, **kw):
    ev = outcomes(df, events(df, signal(df, **kw)))
    dev, test = ev[ev["date"] < SPLIT], ev[ev["date"] >= SPLIT]
    print(summarize(dev, label + " [DEV]"))
    print(summarize(test, label + " [TEST]"))
    return ev


def main():
    df = features(load())
    print(f"Datos: {df.index[0].date()} → {df.index[-1].date()} ({len(df)} sesiones)\n")

    # Baselines
    allidx = list(range(len(df)))
    allidx = [i for i in allidx if df.index[i] >= pd.Timestamp(SIGNAL_FROM) and i + 22 < len(df)]
    base = outcomes(df, allidx)
    print("== BASELINES ==")
    print(summarize(base[base["date"] < SPLIT], "Todos los días [DEV]"))
    print(summarize(base[base["date"] >= SPLIT], "Todos los días [TEST]"))
    vm = (df["vix"] >= 25).fillna(False)
    vb = outcomes(df, events(df, vm))
    print(summarize(vb[vb["date"] < SPLIT], "Solo VIX>=25 [DEV]"))
    print(summarize(vb[vb["date"] >= SPLIT], "Solo VIX>=25 [TEST]"))

    print("\n== REGLA BASE ==")
    ev = run(df, "base (1.5ATR/roll/VIX25/-10%)")
    if not ev.empty:
        print("\nEventos base:")
        print(ev.assign(date=ev["date"].dt.date).round(1).to_string(index=False))

    print("\n== SENSIBILIDAD (un parámetro cada vez) ==")
    for v in (1.0, 1.5, 2.0, 2.5):
        run(df, f"ext_atr={v}", ext_atr=v)
    for v in (0, 20, 25, 30):
        run(df, f"vix_min={v}", vix_min=v)
    for v in (0, 5, 10, 15):
        run(df, f"vix_cool={v}%", vix_cool=v)
    run(df, "rolling=off", rolling=False)

    # ── EXPLORATORIO POST-HOC (añadido tras ver que la regla base da n=2) ──
    # No está en el preregistro: son hipótesis generadas mirando estos mismos
    # datos, por tanto SIN valor confirmatorio. Sirven solo para decidir qué
    # merece un test fuera de muestra (snapshots en vivo).
    print()
    print("== EXPLORATORIO POST-HOC (sin valor confirmatorio) ==")
    vix, d1, dh = df["vix"], df["d1"], df["dhist"]
    peak10 = vix.rolling(10).max()
    variants = {
        "VIX>=25 + UVXY girando":            (vix >= 25) & (d1 < 0) & (dh < 0),
        "VIX>=25 + VIX<=-5% en 5s":          (vix >= 25) & (df["vix_w1"] <= -5),
        "VIX>=25 + VIX 10%+ bajo máx10":     (vix >= 25) & (vix <= peak10 * 0.9),
        "VIX>=20 + UVXY girando":            (vix >= 20) & (d1 < 0) & (dh < 0),
        "VIX>=20 + VIX 10%+ bajo máx10":     (vix >= 20) & (vix <= peak10 * 0.9),
        "VIX>=30 (solo nivel)":              vix >= 30,
        "VIX>=20 + dist_atr>=1.5 + girando": (vix >= 20) & (df["dist_atr"] >= 1.5) & (d1 < 0) & (dh < 0),
    }
    for name, m in variants.items():
        ev = outcomes(df, events(df, m.fillna(False)))
        print(summarize(ev[ev["date"] < SPLIT], name + " [DEV]"))
        print(summarize(ev[ev["date"] >= SPLIT], name + " [TEST]"))


if __name__ == "__main__":
    main()
