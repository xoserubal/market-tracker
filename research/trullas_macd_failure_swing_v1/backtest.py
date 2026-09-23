"""
Backtest: "fallo de MACD" / fallo bajista de implicaciones alcistas
(David Trullas) -- patron distinto de la divergencia MACD estandar que ya
usa el sistema Trullas en produccion (evaluate_pivot_pair, que compara el
VALOR crudo del MACD entre dos pivotes de minimo consecutivos). Aqui el
gate es sobre la RELACION entre la linea MACD y su propia senal:

  1. En el pivote antiguo (a), la linea MACD esta por debajo de su senal.
  2. Entre a y el pivote nuevo (b) la linea cruza al alza sobre la senal.
  3. El precio cae de nuevo y marca un minimo MAS BAJO en b.
  4. La linea MACD retrocede pero NO vuelve a cruzar por debajo de la senal
     en NINGUN punto entre el cruce y b (version estricta, decidida con el
     usuario 2026-09-23 -- ver evaluate_macd_failure_swing en trullas_lib.py).
  5. Para cuando el pivote b queda confirmado (b + PIVOT_WINDOW), la linea
     MACD ya ha vuelto a girar al alza.

Peticion del usuario: validar el patron con un backtest ANTES de construir
ningun panel/senal -- mismo criterio que el propio sistema Trullas, Cruce
Rojo D, Mirror Espejo. Decision de alcance ya tomada con el usuario: si el
backtest resulta favorable, esto se expone SOLO como panel visual en
trullas.html (no cartera, no alertas) -- no hace falta preregistro con
split dev/test como el que se exige a un experimento que va a operar
capital o generar alertas reales.

Metodologia:
- Reutiliza la cache de OHLCV ya descargada por
  research/trullas_divergence_backtest_v1/ohlcv_cache.json (mismo universo
  Portfolio Tracker, mismo rango 2019->hoy) -- sin volver a descargar nada.
- Para cada ticker, pivotes de minimo (find_pivots_low) y pares CONSECUTIVOS
  (a, b) -- mismo criterio zip(pivots, pivots[1:]) que el resto del sistema.
- Para cada par que CALIFICA el nuevo gate (evaluate_macd_failure_swing):
    (A) Medicion descriptiva pura: retorno futuro del PRECIO a 5/21/63
        sesiones desde el primer dia en que el pivote es REALMENTE
        confirmable (b + PIVOT_WINDOW) -- NUNCA desde b mismo, que estaria
        sesgado por construccion (find_pivots_low garantiza que las
        PIVOT_WINDOW sesiones siguientes a b son todas mas altas que
        close[b] -- mismo bug ya encontrado y corregido en
        research/trullas_extended_divergence_v1).
    (B) Trade "ejecutable": misma estructura Fibonacci + mismo modelo de
        ejecucion ya validado (V1_EXECUTABLE -- orden limite real en la
        apertura, zona 23-25% del swing a->b, TP 38.2%, stop = close[b],
        time-stop 20 sesiones) -- para poder comparar de forma directa
        contra el baseline ya conocido (n=54, mean=+1.27%, ver
        research/trullas_early_detector_v1/trades_v1_executable.json).
- Se reporta tambien el solape con el metodo estandar (cuantos pares que
  aqui califican YA calificaban con evaluate_pivot_pair) y una version de
  sensibilidad sin la condicion 5 (require_turn_up=False).

Toda la matematica de indicadores/pivotes se importa de scripts/trullas_lib.py
-- la MISMA que usa produccion y el resto de backtests Trullas.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
V1_CACHE = ROOT / "research" / "trullas_divergence_backtest_v1" / "ohlcv_cache.json"
V1_EXECUTABLE_TRADES = ROOT / "research" / "trullas_early_detector_v1" / "trades_v1_executable.json"

TRADES_FILE = OUT_DIR / "trades_failure_swing.json"
DESCRIPTIVE_FILE = OUT_DIR / "descriptive_failure_swing.json"
SUMMARY_FILE = OUT_DIR / "summary.json"

sys.path.insert(0, str(ROOT / "scripts"))
import trullas_lib as tl  # noqa: E402


def load_cache():
    with open(V1_CACHE, encoding="utf-8") as f:
        raw = json.load(f)
    return {t: pd.DataFrame(v) for t, v in raw.items()}


def _indicators(df):
    macd_line, signal_line, _ = tl.macd_full(df["Close"])
    rsi_arr = tl.rsi(df["Close"])
    return macd_line.to_numpy(), signal_line.to_numpy(), rsi_arr.to_numpy()


def simulate_ticker(ticker: str, df: pd.DataFrame, require_turn_up: bool,
                     strict_stretch: bool) -> tuple[list[dict], list[dict]]:
    close = df["Close"].to_numpy()
    open_ = df["Open"].to_numpy()
    vol = df["Volume"].to_numpy()
    dates = df["Date"].to_numpy()
    macd_line, signal_line, rsi_arr = _indicators(df)
    n = len(close)

    pivots = tl.find_pivots_low(close)
    trades: list[dict] = []
    descriptive: list[dict] = []

    for i in range(1, len(pivots)):
        a, b = pivots[i - 1], pivots[i]

        ev = tl.evaluate_macd_failure_swing(close, macd_line, signal_line, a, b,
                                             require_turn_up=require_turn_up, strict_stretch=strict_stretch)
        if not (ev and ev.get("qualifies")):
            continue

        ev_standard = tl.evaluate_pivot_pair(close, macd_line, rsi_arr, vol, a, b)
        overlaps_standard = bool(ev_standard.get("qualifies"))

        base = {
            "ticker": ticker,
            "pivot_a_date": str(dates[a]), "pivot_a_close": float(close[a]),
            "pivot_b_date": str(dates[b]), "pivot_b_close": float(close[b]),
            "cross_date": str(dates[ev["cross_idx"]]),
            "swing_pct": float(ev["swing_pct"]),
            "overlaps_standard_divergence": overlaps_standard,
        }

        # (A) Descriptivo puro -- retorno de precio desde el primer dia
        # REALMENTE confirmable, nunca desde b (sesgo por construccion).
        confirm_idx = b + tl.PIVOT_WINDOW
        if confirm_idx < n:
            row = dict(base)
            row["confirm_date"] = str(dates[confirm_idx])
            row["confirm_close"] = float(close[confirm_idx])
            for h in (5, 21, 63):
                if confirm_idx + h < n:
                    row[f"fwd_ret_{h}d_from_confirm"] = float(
                        (close[confirm_idx + h] - close[confirm_idx]) / close[confirm_idx] * 100
                    )
            descriptive.append(row)

        # (B) Trade ejecutable -- misma estructura que V1_EXECUTABLE, swing a->b.
        swing = close[a] - close[b]
        entry_low = close[b] + tl.RETR_ENTRY_LOW * swing
        entry_high = close[b] + tl.RETR_ENTRY_HIGH * swing
        tp = close[b] + tl.RETR_TP * swing
        stop = close[b]

        window_end = min(b + 1 + tl.ENTRY_WINDOW_BARS, n)
        scan = tl.find_entry_executable(open_, entry_low, entry_high, stop, b + 1, window_end)
        if scan["outcome"] != "entry":
            continue
        fill_idx = scan["idx"]
        entry_price = float(open_[fill_idx])

        exit_idx, exit_reason = None, None
        scan_end = min(fill_idx + tl.TIME_STOP_BARS, n)
        for k in range(fill_idx, scan_end):
            if close[k] <= stop:
                exit_idx, exit_reason = k, "stop"
                break
            if close[k] >= tp:
                exit_idx, exit_reason = k, "tp"
                break
        if exit_idx is None:
            exit_idx, exit_reason = scan_end - 1, "time_stop"
        exit_price = float(close[exit_idx])

        trades.append({
            **base,
            "entry_date": str(dates[fill_idx]), "entry_price": entry_price,
            "exit_date": str(dates[exit_idx]), "exit_price": exit_price,
            "exit_reason": exit_reason, "holding_days": int(exit_idx - fill_idx),
            "ret_pct": float((exit_price - entry_price) / entry_price * 100),
        })

    return trades, descriptive


def stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0}
    arr = np.array(rets)
    return {
        "n": len(arr), "mean": round(float(arr.mean()), 2), "median": round(float(np.median(arr)), 2),
        "win_pct": round(float((arr > 0).mean() * 100), 1),
        "worst": round(float(arr.min()), 2), "best": round(float(arr.max()), 2),
        "std": round(float(arr.std()), 2),
    }


def run_variant(cache: dict, require_turn_up: bool, strict_stretch: bool) -> tuple[list[dict], list[dict]]:
    all_trades: list[dict] = []
    all_descriptive: list[dict] = []
    for ticker, df in cache.items():
        try:
            trades, desc = simulate_ticker(ticker, df, require_turn_up, strict_stretch)
        except Exception as e:
            print(f"  [fail] {ticker}: {e}")
            continue
        all_trades.extend(trades)
        all_descriptive.extend(desc)
    return all_trades, all_descriptive


def _variant_summary(trades: list[dict], descriptive: list[dict]) -> dict:
    overlap_n = sum(1 for t in trades if t["overlaps_standard_divergence"])
    new_only_trades = [t for t in trades if not t["overlaps_standard_divergence"]]
    return {
        "n_descriptive_candidates": len(descriptive),
        "executable_trades_ALL": stats([t["ret_pct"] for t in trades]),
        "executable_trades_NEW_ONLY_not_captured_by_standard_gate": stats([t["ret_pct"] for t in new_only_trades]),
        "overlap_with_standard_divergence": {
            "n_also_qualify_standard": overlap_n,
            "overlap_pct": round(overlap_n / len(trades) * 100, 1) if trades else None,
        },
        "descriptive_price_return_from_confirm_date": {
            "fwd_ret_5d":  stats([d["fwd_ret_5d_from_confirm"]  for d in descriptive if "fwd_ret_5d_from_confirm"  in d]),
            "fwd_ret_21d": stats([d["fwd_ret_21d_from_confirm"] for d in descriptive if "fwd_ret_21d_from_confirm" in d]),
            "fwd_ret_63d": stats([d["fwd_ret_63d_from_confirm"] for d in descriptive if "fwd_ret_63d_from_confirm" in d]),
        },
    }


def main():
    cache = load_cache()
    print(f"[cache] {len(cache)} tickers cargados de {V1_CACHE.name}")

    # Primaria (ya reportada 2026-09-24): tramo estricto, giro al alza exigido.
    trades_strict, descriptive_strict = run_variant(cache, require_turn_up=True, strict_stretch=True)
    # Sensibilidad ya conocida: sin exigir el giro al alza (apenas cambia nada).
    trades_strict_no_turnup, _ = run_variant(cache, require_turn_up=False, strict_stretch=True)
    # Nueva (2026-09-24, a petición del usuario): tramo laxo — solo se exige
    # que el MACD esté por encima de su señal EN el instante del nuevo mínimo,
    # no en todo el tramo desde el cruce alcista.
    trades_lax, descriptive_lax = run_variant(cache, require_turn_up=True, strict_stretch=False)
    trades_lax_no_turnup, _ = run_variant(cache, require_turn_up=False, strict_stretch=False)

    with open(TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(trades_strict, f, indent=2, ensure_ascii=False)
    with open(DESCRIPTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(descriptive_strict, f, indent=2, ensure_ascii=False)
    with open(OUT_DIR / "trades_failure_swing_lax.json", "w", encoding="utf-8") as f:
        json.dump(trades_lax, f, indent=2, ensure_ascii=False)
    with open(OUT_DIR / "descriptive_failure_swing_lax.json", "w", encoding="utf-8") as f:
        json.dump(descriptive_lax, f, indent=2, ensure_ascii=False)

    baseline_trades = []
    if V1_EXECUTABLE_TRADES.exists():
        baseline_trades = json.load(open(V1_EXECUTABLE_TRADES, encoding="utf-8"))

    summary = {
        "n_tickers": len(cache),
        "baseline_V1_EXECUTABLE_standard_divergence": stats([t["ret_pct"] for t in baseline_trades]),
        "strict_stretch_TRUE_primary_2026-09-24": _variant_summary(trades_strict, descriptive_strict),
        "strict_stretch_TRUE_sensitivity_no_turn_up": stats([t["ret_pct"] for t in trades_strict_no_turnup]),
        "strict_stretch_FALSE_lax_variant_2026-09-24": _variant_summary(trades_lax, descriptive_lax),
        "strict_stretch_FALSE_lax_sensitivity_no_turn_up": stats([t["ret_pct"] for t in trades_lax_no_turnup]),
    }

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
