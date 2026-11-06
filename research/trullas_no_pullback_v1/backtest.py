"""Trullás sin esperar al retroceso (2026-11-06, pregunta del usuario).

Misma señal que producción (evaluate_pivot_pair: mínimo más bajo, swing >= 3%,
divergencia MACD obligatoria, tier por RSI/volumen). Lo único que cambia es la
ENTRADA: en vez de esperar a que la apertura caiga en la zona del 23-25% de
retroceso, se compra a la apertura de la primera sesión operable tras confirmarse
el mínimo (b + FIRST_ACTIONABLE_OFFSET = b+6: el mínimo solo se sabe confirmado
cuando cierran las 5 sesiones siguientes).

Variantes de SALIDA (todas con la misma entrada):
  NW_TP382   stop = mínimo, objetivo 38,2% del swing, time stop 20 sesiones
             (la salida de producción). Si la apertura ya está en o por encima
             del objetivo no hay operación (se cuenta aparte).
  NW_TP618   igual con objetivo 61,8% (hay más recorrido porque se entra más arriba)
  NW_TIME20  sin objetivo ni stop: salida al cierre de la sesión 20 (mide la
             deriva pura tras la señal)
Referencias:
  STRICT     regla de producción corregida (orden límite en la zona 23-25% desde
             b+6, ver flex_entry_probe.py) — el resultado honesto de hoy
  BASE_T20   comprar a la apertura de CUALQUIER sesión del universo y vender al
             cierre de la sesión 20 (deriva incondicional; contra esto se mide si
             la señal aporta algo)

Datos: la misma caché de precios diarios que el resto de estudios Trullás
(research/trullas_divergence_backtest_v1/ohlcv_cache.json). Descriptivo: varias
variantes sobre las mismas señales, sin corrección por comparaciones múltiples;
el corte 2019-2024 / 2025-2026 se muestra para ver estabilidad, no es una
confirmación formal.

Uso: py -3 research/trullas_no_pullback_v1/backtest.py [--save]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "trullas_early_detector_v1"))
import backtest as B  # noqa: E402  (load_cache de la caché compartida + trullas_lib como B.tl)

tl = B.tl
OFF = tl.FIRST_ACTIONABLE_OFFSET
SPLIT = "2025-01-01"
COST_PP = 1.0  # mismo coste ida+vuelta que los estudios anteriores


def simulate(close, entry_idx, entry_price, stop, tp, n):
    """Salida evaluada sobre cierres, como en producción. stop/tp = None → sin ese límite."""
    end = min(entry_idx + tl.TIME_STOP_BARS, n)
    for k in range(entry_idx, end):
        if stop is not None and close[k] <= stop:
            return k, "stop"
        if tp is not None and close[k] >= tp:
            return k, "tp"
    return end - 1, "time"


def run():
    cache = B.load_cache()
    out = {k: [] for k in ("STRICT", "NW_TP382", "NW_TP618", "NW_TIME20")}
    skipped = {"above_tp382": 0, "above_tp618": 0, "below_stop": 0, "no_bar": 0}
    entry_retr = []          # retroceso del swing ya recorrido al entrar (sin esperar)
    base = []                # deriva incondicional a 20 sesiones
    last_date = None
    for tk, df in cache.items():
        close = df["Close"].to_numpy(dtype=float)
        open_ = df["Open"].to_numpy(dtype=float)
        vol = df["Volume"].to_numpy(dtype=float)
        dates = [str(d)[:10] for d in df["Date"].to_numpy()]
        n = len(close)
        if n and (last_date is None or dates[-1] > last_date):
            last_date = dates[-1]
        macd_arr = tl.macd_full(df["Close"])[0].to_numpy()
        rsi_arr = tl.rsi(df["Close"]).to_numpy()

        for j in range(60, n - tl.TIME_STOP_BARS):
            if open_[j] > 0:
                base.append((dates[j], (close[j + tl.TIME_STOP_BARS - 1] - open_[j]) / open_[j] * 100))

        piv = tl.find_pivots_low(close)
        for a, b in zip(piv, piv[1:]):
            ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
            if not ev or not ev.get("qualifies"):
                continue
            stop, swing = ev["stop"], ev["pivot1_close"] - ev["pivot2_close"]
            tp382, tp618 = ev["tp"], ev["pivot2_close"] + 0.618 * swing
            meta = {"ticker": tk, "tier": ev["tier"], "swing_pct": round(ev["swing_pct"], 2)}

            # STRICT: orden límite en la zona desde b+6 (producción corregida)
            fe = tl.find_entry_executable(open_, ev["entry_low"], ev["entry_high"], stop,
                                          b + OFF, min(b + 1 + tl.ENTRY_WINDOW_BARS, n))
            if fe["outcome"] == "entry":
                i = fe["idx"]; ep = open_[i]
                k, why = simulate(close, i, ep, stop, tp382, n)
                out["STRICT"].append({**meta, "date": dates[i], "ret": (close[k] - ep) / ep * 100, "exit": why})

            # Sin esperar: apertura de b+6
            i = b + OFF
            if i >= n:
                skipped["no_bar"] += 1
                continue
            ep = open_[i]
            if ep <= stop:
                skipped["below_stop"] += 1
                continue
            entry_retr.append((ep - ev["pivot2_close"]) / swing * 100)
            rec = {**meta, "date": dates[i], "entry_retr_pct": round((ep - ev["pivot2_close"]) / swing * 100, 1)}
            for key, tp in (("NW_TP382", tp382), ("NW_TP618", tp618)):
                if ep >= tp:
                    skipped["above_tp382" if key == "NW_TP382" else "above_tp618"] += 1
                    continue
                k, why = simulate(close, i, ep, stop, tp, n)
                out[key].append({**rec, "ret": (close[k] - ep) / ep * 100, "exit": why})
            k, why = simulate(close, i, ep, None, None, n)
            out["NW_TIME20"].append({**rec, "ret": (close[k] - ep) / ep * 100, "exit": why})
    return out, skipped, entry_retr, base, last_date


def stats(rs):
    r = np.array(rs, dtype=float)
    if len(r) == 0:
        return None
    return {"n": int(len(r)), "mean": round(float(r.mean()), 2), "mean_cost": round(float(r.mean() - COST_PP), 2),
            "median": round(float(np.median(r)), 2), "win": round(float((r > 0).mean() * 100), 1),
            "worst": round(float(r.min()), 1), "best": round(float(r.max()), 1),
            "sharpe": round(float(r.mean() / r.std()), 3) if r.std() > 0 else None}


def line(label, s, extra=""):
    if not s:
        print(f"{label:30s} n=0")
        return
    print(f"{label:30s} n={s['n']:4d} media={s['mean']:+5.2f}% (con coste {s['mean_cost']:+5.2f}%) "
          f"mediana={s['median']:+5.2f}% aciertos={s['win']:4.1f}% peor={s['worst']:6.1f}% "
          f"media/desv={s['sharpe']}{extra}")


def main():
    out, skipped, entry_retr, base, last_date = run()
    summary = {"last_date": last_date, "skipped": skipped, "variants": {}, "by_period": {}, "by_tier": {}}
    print(f"Datos hasta {last_date}. Entrada sin esperar = apertura de b+{OFF}.")
    er = np.array(entry_retr)
    print(f"Al entrar sin esperar, el precio ya ha recorrido del swing: mediana {np.median(er):.0f}% "
          f"(p25 {np.percentile(er, 25):.0f}%, p75 {np.percentile(er, 75):.0f}%); "
          f"{(er >= 38.2).mean() * 100:.0f}% ya por encima del objetivo 38,2%")
    print(f"Descartadas: {skipped}\n")
    bs = stats([x[1] for x in base])
    summary["base_t20"] = bs
    line("BASE: cualquier día, 20 ses.", bs)
    for key in ("STRICT", "NW_TP382", "NW_TP618", "NW_TIME20"):
        s = stats([t["ret"] for t in out[key]])
        summary["variants"][key] = s
        exits = {e: sum(t["exit"] == e for t in out[key]) for e in ("tp", "stop", "time")}
        line(key, s, f"  salidas {exits}")
    print("\nPor periodo (2019-2024 / 2025-2026):")
    for key in ("STRICT", "NW_TP382", "NW_TP618", "NW_TIME20"):
        for lab, cond in (("dev", lambda d: d < SPLIT), ("test", lambda d: d >= SPLIT)):
            s = stats([t["ret"] for t in out[key] if cond(t["date"])])
            summary["by_period"][f"{key}_{lab}"] = s
            line(f"  {key} {lab}", s)
    bdev = stats([x[1] for x in base if x[0] < SPLIT]); btest = stats([x[1] for x in base if x[0] >= SPLIT])
    line("  BASE dev", bdev); line("  BASE test", btest)
    summary["by_period"]["BASE_dev"], summary["by_period"]["BASE_test"] = bdev, btest
    print("\nPor tier (NW_TP382 / NW_TIME20):")
    for key in ("NW_TP382", "NW_TIME20"):
        for t in (1, 2, 3):
            s = stats([x["ret"] for x in out[key] if x["tier"] == t])
            summary["by_tier"][f"{key}_T{t}"] = s
            line(f"  {key} T{t}", s)
    top = sorted(out["NW_TP382"], key=lambda t: -t["ret"])
    tot = sum(t["ret"] for t in out["NW_TP382"])
    if tot:
        print(f"\nConcentración NW_TP382: top-5 operaciones = {sum(t['ret'] for t in top[:5]) / tot * 100:.0f}% de la suma de retornos")
    if "--save" in sys.argv:
        (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        (HERE / "trades.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
        print("Guardado summary.json y trades.json")


if __name__ == "__main__":
    main()
