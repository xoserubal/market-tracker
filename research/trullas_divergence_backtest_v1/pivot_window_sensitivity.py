"""
Sensibilidad de PIVOT_WINDOW (2/3/4/5 sesiones) sobre el Modelo B ya
validado (EOD, TP fijo 38.2%) — pedido por el usuario 2026-09-20: ¿confirmar
el pivote de mínimo con menos sesiones a cada lado (menos lag, reacciona
antes) mejora o empeora el resultado?

Reutiliza `scripts/trullas_lib.py` (misma matemática que producción) y el
`ohlcv_cache.json` ya descargado en esta carpeta — no vuelve a descargar
nada. Todo lo demás (MIN_SWING_PCT, niveles Fibonacci, ENTRY_WINDOW_BARS,
TIME_STOP_BARS) se deja fijo — solo varía PIVOT_WINDOW, para aislar el
efecto de ese único parámetro.

PIVOT_WINDOW=5 es el punto ya validado (research/trullas_divergence_backtest_v1/README.md).
Distinto del detector anticipado (research/trullas_early_detector_v1/) --
ahí se intentaba anticiparse SIN esperar ningún pivote fractal confirmado;
aquí seguimos exigiendo un pivote fractal confirmado, solo que con una
ventana de confirmación más corta.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
CACHE_FILE = OUT_DIR / "ohlcv_cache.json"

sys.path.insert(0, str(ROOT / "scripts"))
import trullas_lib as tl  # noqa: E402


def load_cache():
    with open(CACHE_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    return {t: pd.DataFrame(v) for t, v in raw.items()}


def simulate_model_b_eod_window(ticker, df, window):
    """Idéntico a simulate_model_b_eod() del backtest.py original, salvo
    que find_pivots_low() usa `window` en vez de tl.PIVOT_WINDOW."""
    close = df["Close"].to_numpy()
    vol = df["Volume"].to_numpy()
    dates = df["Date"].to_numpy()
    macd_arr, _, _ = tl.macd_full(df["Close"])
    macd_arr = macd_arr.to_numpy()
    rsi_arr = tl.rsi(df["Close"]).to_numpy()

    pivots = tl.find_pivots_low(close, window=window)
    trades = []
    for a, b in zip(pivots, pivots[1:]):
        ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
        if not ev.get("qualifies"):
            continue
        entry_low, entry_high, tp, stop = ev["entry_low"], ev["entry_high"], ev["tp"], ev["stop"]

        window_end = min(b + 1 + tl.ENTRY_WINDOW_BARS, len(close))
        scan = tl.find_entry_v1(close, entry_low, entry_high, stop, b + 1, window_end)
        if scan["outcome"] != "entry":
            continue
        entry_idx = scan["idx"]
        entry_price = close[entry_idx]

        exit_idx, exit_reason = None, None
        stop_end = min(entry_idx + 1 + tl.TIME_STOP_BARS, len(close))
        for k in range(entry_idx + 1, stop_end):
            if close[k] <= stop:
                exit_idx, exit_reason = k, "stop"
                break
            if close[k] >= tp:
                exit_idx, exit_reason = k, "tp"
                break
        if exit_idx is None:
            exit_idx, exit_reason = stop_end - 1, "time_stop"
        exit_price = close[exit_idx]

        trades.append({
            "ticker": ticker, "tier": ev["tier"], "pivot_window": window,
            "entry_date": str(dates[entry_idx]), "exit_date": str(dates[exit_idx]),
            "exit_reason": exit_reason, "holding_days": int(exit_idx - entry_idx),
            "ret_pct": float((exit_price - entry_price) / entry_price * 100),
        })
    return trades


def summarize(trades, label):
    if not trades:
        print(f"{label}: 0 señales")
        return None
    rets = np.array([t["ret_pct"] for t in trades])
    win = (rets > 0).mean() * 100
    holds = np.array([t["holding_days"] for t in trades])
    n_tickers = len(set(t["ticker"] for t in trades))
    row = {
        "label": label, "n_signals": len(trades), "n_tickers": n_tickers,
        "mean_ret": round(float(rets.mean()), 2), "median_ret": round(float(np.median(rets)), 2),
        "win_rate": round(float(win), 1), "worst": round(float(rets.min()), 2),
        "best": round(float(rets.max()), 2), "std": round(float(rets.std()), 2),
        "sharpe_like": round(float(rets.mean() / rets.std()), 3) if rets.std() else None,
        "median_holding_days": int(np.median(holds)),
        "pct_tp": round(100 * sum(1 for t in trades if t["exit_reason"] == "tp") / len(trades), 1),
        "pct_stop": round(100 * sum(1 for t in trades if t["exit_reason"] == "stop") / len(trades), 1),
        "pct_time_stop": round(100 * sum(1 for t in trades if t["exit_reason"] == "time_stop") / len(trades), 1),
    }
    print(f"{label}: n={row['n_signals']} tickers={row['n_tickers']} "
          f"mean={row['mean_ret']}% median={row['median_ret']}% win={row['win_rate']}% "
          f"worst={row['worst']}% best={row['best']}% sharpe~={row['sharpe_like']} "
          f"hold_med={row['median_holding_days']}d "
          f"tp={row['pct_tp']}% stop={row['pct_stop']}% time={row['pct_time_stop']}%")
    return row


def main():
    data = load_cache()
    print(f"Universo (caché V1): {len(data)} tickers\n")

    all_trades = {}
    summary_rows = []
    for window in [2, 3, 4, 5]:
        trades = []
        for t, df in data.items():
            try:
                trades.extend(simulate_model_b_eod_window(t, df, window))
            except Exception as e:
                print(f"[error sim window={window}] {t}: {e}")
        all_trades[window] = trades
        summary_rows.append(summarize(trades, f"PIVOT_WINDOW={window} (todas las señales)"))

    print()
    for window in [2, 3, 4, 5]:
        t3 = [t for t in all_trades[window] if t["tier"] == 3]
        summary_rows.append(summarize(t3, f"PIVOT_WINDOW={window} (T3 solo)"))

    with open(OUT_DIR / "trades_by_pivot_window.json", "w", encoding="utf-8") as f:
        json.dump(all_trades, f, indent=2)
    with open(OUT_DIR / "pivot_window_sensitivity_summary.json", "w", encoding="utf-8") as f:
        json.dump([r for r in summary_rows if r], f, indent=2)
    print(f"\nResumen -> {OUT_DIR / 'pivot_window_sensitivity_summary.json'}")


if __name__ == "__main__":
    main()
