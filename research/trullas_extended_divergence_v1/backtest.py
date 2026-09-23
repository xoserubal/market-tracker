"""
Backtest: divergencia MACD con ventana extendida (6 meses) contra la
referencia mas significativa, en vez de solo el pivote consecutivo
inmediato que usa el sistema Trullas en produccion.

Origen: revisando QXO a mano (2026-09-22/23, ver CLAUDE.md "Sistema
Trullas") se encontro una divergencia alcista real de marzo a agosto 2026
que el metodo estandar (evaluate_pivot_pair, solo compara los DOS ULTIMOS
pivotes) no detecta porque un rebote intermedio (23-jun) "resetea" la
cadena de comparacion. El usuario pregunto si ampliar la ventana de
deteccion (penso en 6 meses) y comparar contra el minimo mas significativo
en vez de solo el inmediato anterior podria capturar estos casos.

Metodologia (decisiones tomadas aqui, documentadas porque no habia ninguna
especificacion previa mas alla de la conversacion con el usuario):

1. Para cada par de pivotes CONSECUTIVOS (a, b) que el metodo ESTANDAR
   (evaluate_pivot_pair) NO califica -- si ya calificara, no hay nada nuevo
   que aportar, se descarta de este backtest por definicion.
2. Se busca una referencia extendida `r`: el pivote de MACD mas negativo
   entre los que caen en una ventana de 126 sesiones (~6 meses) antes de
   `b`, exigiendo que sea estrictamente anterior a `a` (para no duplicar lo
   que el metodo estandar ya compara). Si no hay ninguno, no hay nada que
   evaluar.
3. Se clasifica la relacion r->b en 4 categorias (ver
   trullas_lib.classify_extended_divergence): FULL, PARTIAL_FLAT_PRICE_
   RISING_MOMENTUM, PARTIAL_LOWER_LOW_STALLING_MOMENTUM, NONE.
4. FULL y PARTIAL_LOWER_LOW_STALLING_MOMENTUM SI tienen una caida de precio
   real que retraceder (r->b) -- se construye la MISMA estructura Fibonacci
   y el MISMO modelo de ejecucion ya validado (V1_EXECUTABLE: orden limite
   real en la apertura, zona 23-25%, TP 38.2%, stop en el cierre del
   pivote, time-stop 20 sesiones), solo que el swing se calcula desde `r`
   en vez de desde el predecesor inmediato `a`.
5. PARTIAL_FLAT_PRICE_RISING_MOMENTUM NO tiene una caida de precio que
   retraceder (por definicion, precio practicamente plano) -- forzar una
   estructura Fibonacci ahi seria degenerada (swing~=0, entry~=tp~=stop).
   Se mide de forma puramente descriptiva: retorno futuro a 5/10/21
   sesiones desde el cierre del propio pivote, sin simular ningun trade.

Toda la matematica de indicadores/pivotes se importa de scripts/trullas_lib.py
-- la MISMA que usa produccion y el backtest original (mismo criterio que
motivo esa extraccion: que este backtest y el motor en vivo no puedan
desincronizarse en silencio si algun dia esto se lleva a produccion).

Reutiliza la cache de OHLCV ya descargada por
research/trullas_divergence_backtest_v1/ohlcv_cache.json (mismo universo,
mismo rango de fechas 2019-> hoy) -- sin volver a descargar nada.
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

TRADES_FILE = OUT_DIR / "trades_extended.json"
QUALITATIVE_FILE = OUT_DIR / "qualitative_flat.json"
SUMMARY_FILE = OUT_DIR / "summary.json"

sys.path.insert(0, str(ROOT / "scripts"))
import trullas_lib as tl  # noqa: E402


def load_cache():
    with open(V1_CACHE, encoding="utf-8") as f:
        raw = json.load(f)
    return {t: pd.DataFrame(v) for t, v in raw.items()}


def _indicators(df):
    macd_arr, _, _ = tl.macd_full(df["Close"])
    rsi_arr = tl.rsi(df["Close"])
    return macd_arr.to_numpy(), rsi_arr.to_numpy()


def simulate_ticker(ticker: str, df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    close = df["Close"].to_numpy()
    open_ = df["Open"].to_numpy()
    vol = df["Volume"].to_numpy()
    dates = df["Date"].to_numpy()
    macd_arr, rsi_arr = _indicators(df)
    n = len(close)

    pivots = tl.find_pivots_low(close)
    trades: list[dict] = []
    qualitative: list[dict] = []

    for i in range(1, len(pivots)):
        a, b = pivots[i - 1], pivots[i]

        ev_standard = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
        if ev_standard.get("qualifies"):
            continue  # el metodo estandar ya lo captura -- no es "nuevo"

        r = tl.find_extended_reference(close, pivots, a, b)
        if r is None:
            continue

        category, swing_pct_rb = tl.classify_extended_divergence(close, macd_arr, r, b)
        if category == "NONE":
            continue

        base = {
            "ticker": ticker, "category": category,
            "immediate_prev_date": str(dates[a]), "immediate_prev_reason": ev_standard.get("reason"),
            "ref_date": str(dates[r]), "ref_close": float(close[r]), "ref_macd": float(macd_arr[r]),
            "pivot_date": str(dates[b]), "pivot_close": float(close[b]), "pivot_macd": float(macd_arr[b]),
            "swing_pct_ref_to_pivot": float(swing_pct_rb),
            "months_back": round((b - r) / 21.0, 1),
        }

        if category == "PARTIAL_FLAT_PRICE_RISING_MOMENTUM":
            # Bug real encontrado y corregido en la propia verificacion
            # (2026-09-23): find_pivots_low exige que los PIVOT_WINDOW=5
            # cierres siguientes a un pivote sean TODOS mas altos que el
            # propio cierre del pivote -- es la definicion misma de
            # "minimo estricto en la ventana". Medir el retorno a 5 sesiones
            # desde close[b] esta garantizado positivo POR CONSTRUCCION
            # (confirmado: la primera version de este backtest daba 100% de
            # acierto en 690 casos a 5 dias -- imposible para una senal
            # real, la senal inequivoca de que algo estaba mal). Se mide en
            # su lugar desde el primer dia en que el pivote es REALMENTE
            # confirmable (b + PIVOT_WINDOW), que no tiene ninguna garantia
            # estructural de subir.
            confirm_idx = b + tl.PIVOT_WINDOW
            row = dict(base)
            if confirm_idx < n:
                row["confirm_date"] = str(dates[confirm_idx])
                row["confirm_close"] = float(close[confirm_idx])
                for h in (5, 10, 21):
                    if confirm_idx + h < n:
                        row[f"fwd_ret_{h}d_from_confirm"] = float(
                            (close[confirm_idx + h] - close[confirm_idx]) / close[confirm_idx] * 100
                        )
                qualitative.append(row)
            continue

        # FULL / PARTIAL_LOWER_LOW_STALLING_MOMENTUM -- swing real r->b,
        # misma estructura Fibonacci y ejecucion que V1_EXECUTABLE.
        swing = close[r] - close[b]
        entry_low = close[b] + tl.RETR_ENTRY_LOW * swing
        entry_high = close[b] + tl.RETR_ENTRY_HIGH * swing
        tp = close[b] + tl.RETR_TP * swing
        stop = close[b]

        window_end = min(b + 1 + tl.ENTRY_WINDOW_BARS, n)
        scan = tl.find_entry_executable(open_, entry_low, entry_high, stop, b + 1, window_end)
        if scan["outcome"] != "entry":
            continue  # invalidada o nunca rellego dentro de la ventana
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

    return trades, qualitative


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


def main():
    cache = load_cache()
    print(f"[cache] {len(cache)} tickers cargados de {V1_CACHE.name}")

    all_trades: list[dict] = []
    all_qualitative: list[dict] = []
    for ticker, df in cache.items():
        try:
            trades, qual = simulate_ticker(ticker, df)
        except Exception as e:
            print(f"  [fail] {ticker}: {e}")
            continue
        all_trades.extend(trades)
        all_qualitative.extend(qual)

    with open(TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(all_trades, f, indent=2, ensure_ascii=False)
    with open(QUALITATIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_qualitative, f, indent=2, ensure_ascii=False)

    # Baseline: V1_EXECUTABLE ya validado (metodo estandar, consecutivo)
    baseline_trades = []
    if V1_EXECUTABLE_TRADES.exists():
        baseline_trades = json.load(open(V1_EXECUTABLE_TRADES, encoding="utf-8"))

    by_cat: dict[str, list[float]] = {}
    for t in all_trades:
        by_cat.setdefault(t["category"], []).append(t["ret_pct"])

    summary = {
        "baseline_V1_EXECUTABLE_standard_consecutive": stats([t["ret_pct"] for t in baseline_trades]),
        "extended_new_signals_by_category": {cat: stats(rets) for cat, rets in by_cat.items()},
        "extended_new_signals_ALL_tradeable": stats([t["ret_pct"] for t in all_trades]),
        "qualitative_flat_price_rising_momentum_from_confirm_date": {
            "n": len(all_qualitative),
            "fwd_ret_5d":  stats([q["fwd_ret_5d_from_confirm"]  for q in all_qualitative if "fwd_ret_5d_from_confirm"  in q]),
            "fwd_ret_10d": stats([q["fwd_ret_10d_from_confirm"] for q in all_qualitative if "fwd_ret_10d_from_confirm" in q]),
            "fwd_ret_21d": stats([q["fwd_ret_21d_from_confirm"] for q in all_qualitative if "fwd_ret_21d_from_confirm" in q]),
        },
        "n_tickers": len(cache),
    }

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
