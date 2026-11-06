"""Divergencia ampliada de Trullás, v2 (2026-11-06): corrige el sesgo de la v1 y añade 12 meses.

v1 (research/trullas_extended_divergence_v1, 2026-09-23) buscaba la entrada desde b+1, pero el mínimo `b`
solo se sabe confirmado al cierre de b+5 (find_pivots_low exige 5 cierres posteriores más altos): las
entradas de b+1..b+5 no eran operables. Es el mismo sesgo que infló la regla estricta (ver
research/trullas_early_detector_v1/flex_entry_probe.py). Aquí la orden límite empieza en b+6.

Señales:
  STRICT   regla de producción: par de mínimos consecutivos (evaluate_pivot_pair).
  EXT{m}   pares que la regla estricta NO acepta, comparando el nuevo mínimo con el mínimo de precio más
           bajo de los últimos m meses (find_extended_reference) — categorías FULL (mínimo más bajo y MACD
           más alto) y STALL (mínimo más bajo, MACD algo más bajo pero «resistiéndose»,
           EXTENDED_STALL_FRACTION). La categoría de doble suelo plano no tiene estructura de Fibonacci y no
           se opera (igual que en v1).
  m = 6 (126 sesiones, la de v1) y 12 (252 sesiones, nueva).
Entrada y salida idénticas a producción: orden límite en la zona 23-25% del swing (medido entre los dos
mínimos), stop en el mínimo, objetivo 38,2%, time stop 20 sesiones, todo sobre aperturas/cierres diarios.
También se mide «comprar al confirmarse y aguantar 20 sesiones» para ver si la señal anticipa algo.

Descriptivo, sin corrección por comparaciones múltiples. Uso: py -3 .../backtest.py [--save]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "trullas_early_detector_v1"))
import backtest as B  # noqa: E402

tl = B.tl
OFF = tl.FIRST_ACTIONABLE_OFFSET
SPLIT = "2025-01-01"
COST_PP = 1.0
LOOKBACKS = {"EXT6": 126, "EXT12": 252}


def trade(close, open_, dates, b, c_ref, c_b, n):
    """Orden límite en la zona desde b+6; devuelve dict de la operación o None."""
    swing = c_ref - c_b
    lo, hi = c_b + tl.RETR_ENTRY_LOW * swing, c_b + tl.RETR_ENTRY_HIGH * swing
    tp, stop = c_b + tl.RETR_TP * swing, c_b
    fe = tl.find_entry_executable(open_, lo, hi, stop, b + OFF, min(b + 1 + tl.ENTRY_WINDOW_BARS, n))
    if fe["outcome"] != "entry":
        return None
    i = fe["idx"]; ep = float(open_[i])
    end = min(i + tl.TIME_STOP_BARS, n); k, why = end - 1, "time"
    for j in range(i, end):
        if close[j] <= stop: k, why = j, "stop"; break
        if close[j] >= tp: k, why = j, "tp"; break
    return {"date": str(dates[i])[:10], "ret": (close[k] - ep) / ep * 100, "exit": why,
            "swing_pct": round(swing / c_ref * 100, 2)}


def hold20(close, open_, dates, b, n):
    i = b + OFF
    if i + tl.TIME_STOP_BARS > n or open_[i] <= 0:
        return None
    return {"date": str(dates[i])[:10], "ret": (close[i + tl.TIME_STOP_BARS - 1] - open_[i]) / open_[i] * 100}


def run():
    cache = B.load_cache()
    trades = {"STRICT": [], **{f"{k}_{c}": [] for k in LOOKBACKS for c in ("FULL", "STALL")}}
    holds = {k: [] for k in trades}
    base = []
    for tk, df in cache.items():
        close = df["Close"].to_numpy(dtype=float); open_ = df["Open"].to_numpy(dtype=float)
        vol = df["Volume"].to_numpy(dtype=float); dates = df["Date"].to_numpy(); n = len(close)
        macd_arr = tl.macd_full(df["Close"])[0].to_numpy(); rsi_arr = tl.rsi(df["Close"]).to_numpy()
        for j in range(60, n - tl.TIME_STOP_BARS):
            if open_[j] > 0:
                base.append((str(dates[j])[:10], (close[j + tl.TIME_STOP_BARS - 1] - open_[j]) / open_[j] * 100))
        piv = tl.find_pivots_low(close)
        for a, b in zip(piv, piv[1:]):
            ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
            if ev and ev.get("qualifies"):
                t = trade(close, open_, dates, b, ev["pivot1_close"], ev["pivot2_close"], n)
                if t: trades["STRICT"].append({"ticker": tk, "tier": ev["tier"], **t})
                h = hold20(close, open_, dates, b, n)
                if h: holds["STRICT"].append({"ticker": tk, **h})
                continue
            for key, lb in LOOKBACKS.items():
                r = tl.find_extended_reference(close, piv, a, b, lookback_bars=lb)
                if r is None:
                    continue
                cat, _ = tl.classify_extended_divergence(close, macd_arr, r, b)
                if cat not in ("FULL", "PARTIAL_LOWER_LOW_STALLING_MOMENTUM"):
                    continue
                name = f"{key}_{'FULL' if cat == 'FULL' else 'STALL'}"
                t = trade(close, open_, dates, b, float(close[r]), float(close[b]), n)
                if t: trades[name].append({"ticker": tk, "months_back": round((b - r) / 21, 1), **t})
                h = hold20(close, open_, dates, b, n)
                if h: holds[name].append({"ticker": tk, **h})
    return trades, holds, base


def st(rs):
    r = np.array(rs, dtype=float)
    if len(r) == 0:
        return {"n": 0}
    srt = np.sort(r)
    return {"n": int(len(r)), "mean": round(float(r.mean()), 2), "mean_cost": round(float(r.mean() - COST_PP), 2),
            "median": round(float(np.median(r)), 2), "win": round(float((r > 0).mean() * 100), 1),
            "worst": round(float(r.min()), 1),
            "mean_wo_top5": round(float(srt[:-5].mean()), 2) if len(r) > 10 else None,
            "sharpe": round(float(r.mean() / r.std()), 3) if len(r) > 1 and r.std() > 0 else None}


def show(label, s):
    if not s["n"]:
        print(f"  {label:26s} n=   0"); return
    print(f"  {label:26s} n={s['n']:4d} media={s['mean']:+5.2f}% c/coste={s['mean_cost']:+5.2f}% "
          f"mediana={s['median']:+5.2f}% aciertos={s['win']:4.1f}% sin_top5={s['mean_wo_top5']} "
          f"peor={s['worst']:6.1f}% m/d={s['sharpe']}")


def main():
    trades, holds, base = run()
    combos = {
        "STRICT": ["STRICT"],
        "EXT6 (FULL+STALL)": ["EXT6_FULL", "EXT6_STALL"],
        "EXT12 (FULL+STALL)": ["EXT12_FULL", "EXT12_STALL"],
        "STRICT+EXT6": ["STRICT", "EXT6_FULL", "EXT6_STALL"],
        "STRICT+EXT12": ["STRICT", "EXT12_FULL", "EXT12_STALL"],
    }
    summary = {"trades": {}, "holds": {}, "by_period": {}}
    print("== Operaciones con la mecánica de producción (zona 23-25%, objetivo 38,2%, stop en el mínimo) ==")
    for k in trades:
        if k != "STRICT":
            summary["trades"][k] = s = st([t["ret"] for t in trades[k]]); show(k, s)
    print()
    for lab, keys in combos.items():
        rs = [t["ret"] for k in keys for t in trades[k]]
        summary["trades"][lab] = s = st(rs); show(lab, s)
    print("\n== Por periodo: 2019-2024 (dev) / 2025-2026 (test) ==")
    for lab, keys in combos.items():
        for per, cond in (("dev", lambda d: d < SPLIT), ("test", lambda d: d >= SPLIT)):
            s = st([t["ret"] for k in keys for t in trades[k] if cond(t["date"])])
            summary["by_period"][f"{lab} {per}"] = s; show(f"{lab} {per}", s)
    print("\n== ¿Anticipa la señal? Comprar al confirmarse (b+6) y vender a las 20 sesiones ==")
    bs = st([x[1] for x in base]); summary["holds"]["BASE cualquier día"] = bs; show("BASE cualquier día", bs)
    for lab, keys in combos.items():
        s = st([h["ret"] for k in keys for h in holds[k]]); summary["holds"][lab] = s; show(lab, s)
    mb = [t["months_back"] for k in ("EXT12_FULL", "EXT12_STALL") for t in trades[k]]
    if mb:
        print(f"\nEXT12: la referencia está a {np.median(mb):.1f} meses en mediana (p75 {np.percentile(mb, 75):.1f})")
    if "--save" in sys.argv:
        (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        (HERE / "trades.json").write_text(json.dumps(trades, ensure_ascii=False, indent=0, default=str), encoding="utf-8")
        print("Guardado summary.json y trades.json")


if __name__ == "__main__":
    main()
