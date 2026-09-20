"""
Backtest del sistema de divergencias (MACD / Volumen / RSI) + ejecucion por
Fibonacci descrito por David Trullas, sobre el universo de Portfolio Tracker
(portfolio.json, ~118 tickers), en diario.

Alcance: SOLO LARGOS (divergencias alcistas en minimos). Decision explicita,
no del texto original de Trullas -- ninguna cartera de este proyecto abre
cortos (CAVA_MACRO, MIRROR_ESPEJO, CRUCE_ROJO_D son todas long-only), asi que
construir infraestructura de cortos para esta primera pasada exploratoria
habria sido alcance no pedido. Si el backtest muestra borde real, extender a
cortos es una decision aparte con el usuario.

Dos modelos de ejecucion, ambos reproducibles desde este mismo script
(2026-09-20: el modelo B -- el que de verdad implementa produccion -- vivia
antes solo como comandos sueltos de terminal sin guardar, un hueco de
reproducibilidad real senalado en la revision de un asesor externo, ver
CLAUDE.md):

  MODELO A -- fills intradia (toca la zona de entrada/TP/stop con High/Low).
              Se descarto para produccion: se invierte con costes de
              transaccion realistas (~1pp ida+vuelta) y exige ejecucion con
              limite intradia que este proyecto no tiene.
  MODELO B -- fills solo a cierre diario (el que SI implementa
              scripts/trullas_signal_calculator.py / trullas_shadow_portfolio.py).
              TP fijo al 38.2% de Fibonacci -- el mejor punto de todo el
              barrido probado (bate a dejar correr hasta cruce MACD bajista,
              y a cualquier otro nivel de la escalera Fibonacci).

Ver README.md para la comparativa completa y el razonamiento de cada
decision. Toda la matematica de indicadores/pivotes/gate de divergencia se
importa de scripts/trullas_lib.py -- la MISMA que usa produccion, no una
copia paralela (mismo criterio que ai_shared.py/relative_flow_lib.py en
este proyecto: que el backtest y el motor en vivo no puedan desincronizarse
en silencio).

Metodologia (decisiones tomadas aqui, documentadas porque el texto original
de Trullas no las fija con precision matematica) -- ver docstring de
scripts/trullas_lib.py para el detalle de cada parametro.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
CACHE_FILE = OUT_DIR / "ohlcv_cache.json"
TRADES_FILE = OUT_DIR / "trades.json"
TRADES_EOD_FILE = OUT_DIR / "trades_eod.json"

sys.path.insert(0, str(ROOT / "scripts"))
import trullas_lib as tl  # noqa: E402

START_DATE = "2019-01-01"


def load_universe():
    with open(ROOT / "portfolio.json", encoding="utf-8") as f:
        data = json.load(f)
    tickers = set()
    for sec in data["sections"]:
        for it in sec.get("items", []):
            t = it.get("ticker") if isinstance(it, dict) else it
            if t:
                tickers.add(t)
    return sorted(tickers)


def download_universe(tickers, force=False):
    if CACHE_FILE.exists() and not force:
        print(f"[cache] usando {CACHE_FILE.name}")
        with open(CACHE_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        return {t: pd.DataFrame(v) for t, v in raw.items()}

    out = {}
    failed = []
    for i, t in enumerate(tickers):
        try:
            df = yf.download(t, start=START_DATE, auto_adjust=False,
                              progress=False, threads=False)
            if df is None or df.empty or len(df) < 200:
                failed.append(t)
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            tl.apply_gbx_scale_fix(t, df, ["Open", "High", "Low", "Close"])
            df = df.reset_index()
            df["Date"] = df["Date"].astype(str)
            out[t] = df
        except Exception as e:
            failed.append(t)
            print(f"[fail] {t}: {e}")
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{len(tickers)}")
        time.sleep(0.05)

    print(f"Descargados {len(out)}/{len(tickers)} (fallos: {failed})")
    serializable = {t: df.to_dict(orient="list") for t, df in out.items()}
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(serializable, f)
    return out


def _indicators(df):
    macd_arr, _, _ = tl.macd_full(df["Close"])
    rsi_arr = tl.rsi(df["Close"])
    return macd_arr.to_numpy(), rsi_arr.to_numpy()


def simulate_model_a_intraday(ticker, df):
    """Modelo A -- descartado para producción, se conserva aquí solo por
    trazabilidad histórica del backtest original (ver README)."""
    close = df["Close"].to_numpy()
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    vol = df["Volume"].to_numpy()
    dates = df["Date"].to_numpy()
    macd_arr, rsi_arr = _indicators(df)

    pivots = tl.find_pivots_low(close)
    trades = []

    for a, b in zip(pivots, pivots[1:]):
        ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
        if not ev.get("qualifies"):
            continue
        c1, c2 = ev["pivot1_close"], ev["pivot2_close"]
        entry_low, entry_high, tp, stop = ev["entry_low"], ev["entry_high"], ev["tp"], ev["stop"]

        entry_idx = None
        entry_price = None
        window_end = min(b + 1 + tl.ENTRY_WINDOW_BARS, len(close))
        for j in range(b + 1, window_end):
            if low[j] <= entry_high and high[j] >= entry_low:
                entry_idx = j
                entry_price = min(max(entry_low, low[j]), entry_high)
                break
            if low[j] <= stop:
                break  # invalidado antes de poder entrar

        if entry_idx is None:
            continue  # señal expirada, sin operacion

        exit_idx = None
        exit_price = None
        exit_reason = None
        stop_end = min(entry_idx + 1 + tl.TIME_STOP_BARS, len(close))
        for k in range(entry_idx + 1, stop_end):
            hit_stop = low[k] <= stop
            hit_tp = high[k] >= tp
            if hit_stop:
                # ambiguo intradia si tambien hit_tp -> conservador, stop primero
                exit_idx, exit_price, exit_reason = k, stop, "stop"
                break
            if hit_tp:
                exit_idx, exit_price, exit_reason = k, tp, "tp"
                break
        if exit_idx is None:
            exit_idx = stop_end - 1
            exit_price = close[exit_idx]
            exit_reason = "time_stop"

        ret_pct = (exit_price - entry_price) / entry_price * 100
        trades.append({
            "ticker": ticker, "tier": ev["tier"], "rsi_div": ev["rsi_div"], "vol_div": ev["vol_div"],
            "pivot1_date": str(dates[a]), "pivot1_close": float(c1),
            "pivot2_date": str(dates[b]), "pivot2_close": float(c2),
            "swing_pct": float(ev["swing_pct"]),
            "entry_date": str(dates[entry_idx]), "entry_price": float(entry_price),
            "exit_date": str(dates[exit_idx]), "exit_price": float(exit_price),
            "exit_reason": exit_reason, "holding_days": int(exit_idx - entry_idx),
            "ret_pct": float(ret_pct),
        })

    return trades


def simulate_model_b_eod(ticker, df):
    """Modelo B -- fills EOD, TP 38.2%. Es EL MODELO QUE IMPLEMENTA
    PRODUCCIÓN: usa find_entry_v1() de trullas_lib, la misma función que
    scripts/trullas_signal_calculator.py llama en vivo para decidir
    `signal_state=entry_today`."""
    close = df["Close"].to_numpy()
    vol = df["Volume"].to_numpy()
    dates = df["Date"].to_numpy()
    macd_arr, rsi_arr = _indicators(df)

    pivots = tl.find_pivots_low(close)
    trades = []

    for a, b in zip(pivots, pivots[1:]):
        ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
        if not ev.get("qualifies"):
            continue
        c2 = ev["pivot2_close"]
        entry_low, entry_high, tp, stop = ev["entry_low"], ev["entry_high"], ev["tp"], ev["stop"]

        window_end = min(b + 1 + tl.ENTRY_WINDOW_BARS, len(close))
        scan = tl.find_entry_v1(close, entry_low, entry_high, stop, b + 1, window_end)
        if scan["outcome"] != "entry":
            continue  # invalidado o expirado sin retroceso -> sin operación
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

        ret_pct = (exit_price - entry_price) / entry_price * 100
        trades.append({
            "ticker": ticker, "tier": ev["tier"],
            "entry_date": str(dates[entry_idx]), "exit_date": str(dates[exit_idx]),
            "exit_reason": exit_reason, "holding_days": int(exit_idx - entry_idx),
            "ret_pct": float(ret_pct),
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
        "label": label,
        "n_signals": len(trades),
        "n_tickers": n_tickers,
        "mean_ret": round(float(rets.mean()), 2),
        "median_ret": round(float(np.median(rets)), 2),
        "win_rate": round(float(win), 1),
        "worst": round(float(rets.min()), 2),
        "best": round(float(rets.max()), 2),
        "std": round(float(rets.std()), 2),
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
    force = "--force" in sys.argv
    tickers = load_universe()
    print(f"Universo: {len(tickers)} tickers")
    data = download_universe(tickers, force=force)

    trades_a, trades_b = [], []
    for t, df in data.items():
        try:
            trades_a.extend(simulate_model_a_intraday(t, df))
            trades_b.extend(simulate_model_b_eod(t, df))
        except Exception as e:
            print(f"[error sim] {t}: {e}")

    with open(TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(trades_a, f, indent=2)
    with open(TRADES_EOD_FILE, "w", encoding="utf-8") as f:
        json.dump(trades_b, f, indent=2)
    print(f"\n{len(trades_a)} operaciones Modelo A -> {TRADES_FILE.name}")
    print(f"{len(trades_b)} operaciones Modelo B -> {TRADES_EOD_FILE.name}\n")

    print("--- Modelo A (intradía, descartado para producción) ---")
    summary_rows = []
    summary_rows.append(summarize(trades_a, "A: T1+T2+T3 (todas las señales MACD)"))
    summary_rows.append(summarize([t for t in trades_a if t["tier"] >= 2], "A: T2+T3 (MACD+RSI)"))
    summary_rows.append(summarize([t for t in trades_a if t["tier"] == 3], "A: T3 (MACD+RSI+Volumen)"))
    summary_rows.append(summarize([t for t in trades_a if t["tier"] == 1], "A: T1 solo (MACD sin RSI ni Volumen)"))

    print("\n--- Modelo B (EOD, el que implementa producción) ---")
    summary_rows.append(summarize(trades_b, "B: todas las señales"))
    summary_rows.append(summarize([t for t in trades_b if t["tier"] == 3], "B: T3 (MACD+RSI+Volumen)"))

    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump([r for r in summary_rows if r], f, indent=2)


if __name__ == "__main__":
    main()
