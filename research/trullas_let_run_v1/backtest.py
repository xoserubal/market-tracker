"""Trullás: ¿y si se deja correr la subida? (2026-11-06, pregunta del usuario)

Entrada idéntica a producción y sin sesgo: orden límite en la zona 23-25% del swing desde b+6 (el mínimo
solo se sabe confirmado al cierre de b+5). Cambia solo la SALIDA. Menú fijado de antemano, sin ajustar
parámetros a los resultados; todas mantienen el stop inicial en el mínimo (sobre cierres, como producción):

  E0_PROD     objetivo 38,2% del swing, máx. 20 sesiones (producción)
  E1_TP100    objetivo 100% del swing (volver al mínimo anterior), máx. 40 sesiones
  E2_TP162    objetivo 161,8%, máx. 60 sesiones
  E3_MACD     sin objetivo; salir al primer cierre con la línea MACD por debajo de su señal, máx. 60
  E4_TRAIL    sin objetivo; stop dinámico = máximo cierre desde la entrada − 2×ATR14 (ATR fijado a la
              entrada), máx. 60
  E5_HOLD60   sin objetivo ni stop dinámico: aguantar 60 sesiones (solo el stop inicial)

Dos conjuntos de señales: la estricta (pares consecutivos) y estricta + ampliada a 6 meses (más muestra).
Referencia: comprar cualquier día del universo y vender a 20 / 60 sesiones.
Coste 1 pp ida y vuelta. Descriptivo, sin corrección por comparaciones múltiples.
Uso: py -3 research/trullas_let_run_v1/backtest.py [--save]
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
EXITS = ("E0_PROD", "E1_TP100", "E2_TP162", "E3_MACD", "E4_TRAIL", "E5_HOLD60")


def atr14(high, low, close):
    prev = np.concatenate([[close[0]], close[:-1]])
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    out = np.full_like(close, np.nan)
    if len(tr) > 14:
        out[14] = tr[1:15].mean()
        for i in range(15, len(tr)):
            out[i] = (out[i - 1] * 13 + tr[i]) / 14
    return out


def exit_for(rule, i, ep, c_b, swing, close, macd, sig, atr, n):
    stop = c_b
    caps = {"E0_PROD": 20, "E1_TP100": 40}
    end = min(i + caps.get(rule, 60), n)
    tp = {"E0_PROD": c_b + tl.RETR_TP * swing, "E1_TP100": c_b + swing,
          "E2_TP162": c_b + 1.618 * swing}.get(rule)
    a = atr[i - 1] if i > 0 and not np.isnan(atr[i - 1]) else None
    hi = ep
    for k in range(i, end):
        c = close[k]
        if c <= stop:
            return k, "stop"
        if tp is not None and c >= tp:
            return k, "tp"
        if rule == "E3_MACD" and k > i and macd[k] < sig[k]:
            return k, "macd"
        if rule == "E4_TRAIL" and a is not None:
            hi = max(hi, c)
            if c <= hi - 2 * a and k > i:
                return k, "trail"
    return end - 1, "time"


def signals_for(close, macd_arr, rsi_arr, vol, piv, with_ext):
    for a, b in zip(piv, piv[1:]):
        ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
        if ev and ev.get("qualifies"):
            yield b, ev["pivot1_close"], ev["pivot2_close"], "strict"
            continue
        if not with_ext:
            continue
        r = tl.find_extended_reference(close, piv, a, b, lookback_bars=126)
        if r is None:
            continue
        cat, _ = tl.classify_extended_divergence(close, macd_arr, r, b)
        if cat in ("FULL", "PARTIAL_LOWER_LOW_STALLING_MOMENTUM"):
            yield b, float(close[r]), float(close[b]), "ext6"


def run():
    cache = B.load_cache()
    res = {s: {e: [] for e in EXITS} for s in ("STRICT", "STRICT+EXT6")}
    base = {20: [], 60: []}
    for tk, df in cache.items():
        close = df["Close"].to_numpy(dtype=float); open_ = df["Open"].to_numpy(dtype=float)
        high = df["High"].to_numpy(dtype=float); low = df["Low"].to_numpy(dtype=float)
        vol = df["Volume"].to_numpy(dtype=float); dates = [str(d)[:10] for d in df["Date"].to_numpy()]
        n = len(close)
        m, s, _ = tl.macd_full(df["Close"]); macd, sig = m.to_numpy(), s.to_numpy()
        rsi_arr = tl.rsi(df["Close"]).to_numpy(); atr = atr14(high, low, close)
        for j in range(60, n - 60):
            if open_[j] > 0:
                for h in (20, 60):
                    base[h].append((dates[j], (close[j + h - 1] - open_[j]) / open_[j] * 100))
        piv = tl.find_pivots_low(close)
        for set_name, with_ext in (("STRICT", False), ("STRICT+EXT6", True)):
            # Una sola posición abierta por valor y regla de salida (como la cartera real): sin esto,
            # dos señales seguidas del mismo valor abrían dos posiciones idénticas (ASTS 2024-04 contada
            # dos veces en la primera pasada).
            busy_until = {e: -1 for e in EXITS}
            for b, c_ref, c_b, src in signals_for(close, macd, rsi_arr, vol, piv, with_ext):
                swing = c_ref - c_b
                fe = tl.find_entry_executable(open_, c_b + tl.RETR_ENTRY_LOW * swing, c_b + tl.RETR_ENTRY_HIGH * swing,
                                              c_b, b + OFF, min(b + 1 + tl.ENTRY_WINDOW_BARS, n))
                if fe["outcome"] != "entry":
                    continue
                i = fe["idx"]; ep = float(open_[i])
                for e in EXITS:
                    if i <= busy_until[e]:
                        continue
                    k, why = exit_for(e, i, ep, c_b, swing, close, macd, sig, atr, n)
                    busy_until[e] = k
                    res[set_name][e].append({"ticker": tk, "src": src, "date": dates[i],
                                             "ret": (close[k] - ep) / ep * 100, "exit": why, "bars": k - i})
    return res, base


def st(rs, bars=None):
    r = np.array(rs, dtype=float)
    if len(r) == 0:
        return {"n": 0}
    srt = np.sort(r)
    out = {"n": int(len(r)), "mean": round(float(r.mean()), 2), "mean_cost": round(float(r.mean() - COST_PP), 2),
           "median": round(float(np.median(r)), 2), "win": round(float((r > 0).mean() * 100), 1),
           "worst": round(float(r.min()), 1), "best": round(float(r.max()), 1),
           "wo_top5": round(float(srt[:-5].mean()), 2) if len(r) > 10 else None,
           "sharpe": round(float(r.mean() / r.std()), 3) if r.std() > 0 else None}
    if bars is not None:
        out["avg_bars"] = round(float(np.mean(bars)), 1)
    return out


def show(label, s):
    if not s["n"]:
        print(f"  {label:24s} n=0"); return
    extra = f" días={s['avg_bars']:5.1f}" if "avg_bars" in s else ""
    print(f"  {label:24s} n={s['n']:6d} media={s['mean']:+6.2f}% c/coste={s['mean_cost']:+6.2f}% "
          f"mediana={s['median']:+6.2f}% aciertos={s['win']:4.1f}% sin_top5={s['wo_top5']} "
          f"peor={s['worst']:6.1f}% mejor={s['best']:6.1f}% m/d={s['sharpe']}{extra}")


def main():
    res, base = run()
    summary = {"base": {}, "sets": {}, "by_period": {}}
    print("Referencia (comprar cualquier día):")
    for h in (20, 60):
        summary["base"][h] = s = st([x[1] for x in base[h]]); show(f"BASE {h} sesiones", s)
    for set_name, by_exit in res.items():
        print(f"\n== {set_name} ==")
        summary["sets"][set_name] = {}
        for e, tr in by_exit.items():
            s = st([t["ret"] for t in tr], [t["bars"] for t in tr])
            ex = {k: sum(t["exit"] == k for t in tr) for k in ("tp", "stop", "macd", "trail", "time")}
            s["exits"] = {k: v for k, v in ex.items() if v}
            summary["sets"][set_name][e] = s
            show(e, s); print(f"{'':28s}salidas {s['exits']}")
    print("\n== STRICT+EXT6 por periodo (2019-2024 / 2025-2026) ==")
    for e in EXITS:
        for per, cond in (("dev", lambda d: d < SPLIT), ("test", lambda d: d >= SPLIT)):
            s = st([t["ret"] for t in res["STRICT+EXT6"][e] if cond(t["date"])])
            summary["by_period"][f"{e} {per}"] = s; show(f"{e} {per}", s)
    if "--save" in sys.argv:
        (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        (HERE / "trades.json").write_text(json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8")
        print("Guardado summary.json y trades.json")


if __name__ == "__main__":
    main()
