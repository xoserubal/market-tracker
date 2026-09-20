"""
Backtest del detector anticipado de mínimos (B0/B1) propuesto por un asesor
externo, sobre el mismo universo/histórico que
research/trullas_divergence_backtest_v1/ (118 tickers de Portfolio Tracker,
2019→hoy, auto_adjust=False). Ver CLAUDE.md, sección "Sistema Trullás —
revisión de un asesor externo" para el contexto completo.

Hipótesis a contrastar (literal del asesor): un nuevo mínimo provisional con
divergencia MACD frente al último pivote fractal YA CONFIRMADO puede
anticipar un giro antes de que el propio pivote fractal se confirme 5
sesiones después. ¿Compensa el riesgo de señales falsas con más recorrido
capturado?

Tres variantes comparadas, TODAS con la MISMA disciplina de ejecución
(fill a la apertura de la sesión siguiente a la señal, nunca al cierre que
la generó — corrige una asimetría real que yo mismo señalé antes de
construir esto: comparar un detector con ejecución "realista" contra un V1
que entra al mismo cierre que generó la señal sería injusto para V1):

  V1_OPEN — el sistema ya validado (research/trullas_divergence_backtest_v1),
            re-simulado con fill a apertura siguiente en vez de al mismo
            cierre, para poder compararlo de tú a tú con B0/B1.
  B0      — mínimo provisional + divergencia MACD provisional CONTRA EL
            ÚLTIMO PIVOTE YA CONFIRMADO (no espera a que el segundo pivote
            se confirme). SIN exigir volumen extraordinario — control para
            aislar si "anticiparse" por sí solo aporta algo.
  B1      — B0 + RVOL20 >= EARLY_VOLUME_SPIKE_THRESHOLD (4.0 por defecto,
            punto de partida de investigación, no calibrado).

No se implementa B2 (confirmación por reacción del precio) en esta primera
pasada — añade una dimensión más (definir la ventana/trigger de reacción)
que no es central para responder la pregunta de fondo ("¿anticiparse
compensa el riesgo?"); se deja para una ronda posterior si B0/B1 muestran
algo prometedor.

Entrada: a diferencia de V1 (que espera un retroceso a la zona 23-25% de
Fibonacci), B0/B1 entran INMEDIATAMENTE a la apertura de la sesión
siguiente al evento — es la hipótesis central del asesor: comprar más cerca
del mínimo, sin esperar ningún retroceso, para capturar más recorrido hasta
el mismo TP del 38.2%. Stop = mínimo provisional (igual que V1: ruptura del
origen invalida). Sin filtro de RSI/Volumen-en-pivote (vol_div) en B0/B1 —
esos son conceptos de V1, no de este detector (ver distinción explícita del
asesor en su sección 10, y CLAUDE.md).

Sin dev/test split para la comparación principal V1_OPEN/B0/B1 (tres
variantes fijas, no una búsqueda de combinaciones — mismo criterio que el
backtest original). La sensibilidad a distintos umbrales de RVOL (sección
final) es puramente descriptiva, tal como pide el propio asesor — no se usa
para elegir un nuevo parámetro de producción sin validación fuera de
muestra.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
V1_CACHE = ROOT / "research" / "trullas_divergence_backtest_v1" / "ohlcv_cache.json"

sys.path.insert(0, str(ROOT / "scripts"))
import trullas_lib as tl  # noqa: E402

EPISODE_GAP_BARS = 5  # separación mínima entre eventos B0 del mismo ticker para tratarse como "mismo episodio"


def load_cache():
    if not V1_CACHE.exists():
        raise SystemExit(f"No existe {V1_CACHE} -- corre primero research/trullas_divergence_backtest_v1/backtest.py")
    with open(V1_CACHE, encoding="utf-8") as f:
        raw = json.load(f)
    return {t: pd.DataFrame(v) for t, v in raw.items()}


def simulate_v1_open(ticker, df):
    """V1, mismo gate/entrada que el Modelo B validado, pero fill a APERTURA
    de la sesión siguiente al día que confirma la entrada (no al mismo
    cierre) -- para comparar de tú a tú contra B0/B1."""
    close = df["Close"].to_numpy()
    open_ = df["Open"].to_numpy()
    vol = df["Volume"].to_numpy()
    dates = df["Date"].to_numpy()
    macd_arr, _, _ = tl.macd_full(df["Close"])
    macd_arr = macd_arr.to_numpy()
    rsi_arr = tl.rsi(df["Close"]).to_numpy()
    n = len(close)

    pivots = tl.find_pivots_low(close)
    trades = []
    for a, b in zip(pivots, pivots[1:]):
        ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
        if not ev.get("qualifies"):
            continue
        entry_low, entry_high, tp, stop = ev["entry_low"], ev["entry_high"], ev["tp"], ev["stop"]
        window_end = min(b + 1 + tl.ENTRY_WINDOW_BARS, n)
        scan = tl.find_entry_v1(close, entry_low, entry_high, stop, b + 1, window_end)
        if scan["outcome"] != "entry":
            continue
        signal_idx = scan["idx"]
        fill_idx = signal_idx + 1
        if fill_idx >= n:
            continue  # sin sesión siguiente disponible en los datos
        entry_price = open_[fill_idx]

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
        exit_price = close[exit_idx]

        trades.append({
            "variant": "V1_OPEN", "ticker": ticker, "tier": ev["tier"],
            "signal_date": str(dates[signal_idx]), "entry_date": str(dates[fill_idx]),
            "entry_price": float(entry_price), "exit_date": str(dates[exit_idx]),
            "exit_price": float(exit_price), "exit_reason": exit_reason,
            "holding_days": int(exit_idx - fill_idx),
            "ret_pct": float((exit_price - entry_price) / entry_price * 100),
        })
    return trades


def simulate_early(ticker, df, variant: str, rvol_threshold: float = tl.EARLY_VOLUME_SPIKE_THRESHOLD):
    """variant='B0' (sin filtro de volumen) o 'B1' (+ RVOL>=umbral). Fill
    inmediato a apertura de la sesión siguiente al evento -- sin esperar
    ningún retroceso, a diferencia de V1."""
    close = df["Close"].to_numpy()
    open_ = df["Open"].to_numpy()
    vol = df["Volume"].to_numpy()
    dates = df["Date"].to_numpy()
    macd_arr, _, _ = tl.macd_full(df["Close"])
    macd_arr = macd_arr.to_numpy()
    n = len(close)

    pivots = tl.find_pivots_low(close)
    pivots_set = set(pivots)
    trades = []
    last_episode_t = {}  # ref_pivot_idx -> último t usado, para episode_id

    for t in range(5, n - 1):  # -1: necesita una sesión siguiente para el fill
        ref = tl.reference_confirmed_pivot_asof(pivots, t)
        cand = tl.evaluate_early_candidate_b0(close, macd_arr, t, ref)
        if cand is None:
            continue
        if variant == "B1":
            rv = tl.rvol(vol, t)
            if rv is None or rv < rvol_threshold:
                continue
        else:
            rv = tl.rvol(vol, t)

        fill_idx = t + 1
        entry_price = open_[fill_idx]
        tp, stop = cand["tp"], cand["stop"]

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
        exit_price = close[exit_idx]

        # Seguimiento de confirmación (sección 11 del asesor): ¿t termina
        # siendo un pivote fractal real? Si sí, ¿la divergencia sigue
        # sosteniéndose contra el pivote INMEDIATAMENTE ANTERIOR real de V1
        # (que puede no ser `ref` si se formó otro pivote entre medias)?
        if t in pivots_set:
            idx_in_list = pivots.index(t)
            if idx_in_list == 0:
                confirmation_status = "confirmed_no_prior_pivot"
            else:
                actual_prior = pivots[idx_in_list - 1]
                holds = bool(not np.isnan(macd_arr[actual_prior]) and macd_arr[t] > macd_arr[actual_prior])
                confirmation_status = "confirmed_divergence_holds" if holds else "confirmed_divergence_lost"
        else:
            confirmation_status = "never_confirmed_as_pivot"

        episode_ref = last_episode_t.get(cand["ref_pivot_idx"])
        is_first_in_episode = episode_ref is None or (t - episode_ref) > EPISODE_GAP_BARS
        last_episode_t[cand["ref_pivot_idx"]] = t

        trades.append({
            "variant": variant, "ticker": ticker,
            "ref_pivot_date": str(dates[cand["ref_pivot_idx"]]), "ref_pivot_close": cand["ref_pivot_close"],
            "signal_date": str(dates[t]), "provisional_low_close": cand["provisional_low_close"],
            "swing_pct": cand["swing_pct"], "rvol20": None if rv is None else round(rv, 2),
            "entry_date": str(dates[fill_idx]), "entry_price": float(entry_price),
            "exit_date": str(dates[exit_idx]), "exit_price": float(exit_price),
            "exit_reason": exit_reason, "holding_days": int(exit_idx - fill_idx),
            "ret_pct": float((exit_price - entry_price) / entry_price * 100),
            "confirmation_status": confirmation_status,
            "is_first_in_episode": is_first_in_episode,
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


def confirmation_breakdown(trades, label):
    if not trades:
        return
    from collections import Counter
    c = Counter(t["confirmation_status"] for t in trades)
    total = len(trades)
    print(f"  {label} seguimiento de confirmación (n={total}): " +
          ", ".join(f"{k}={v} ({100*v/total:.0f}%)" for k, v in c.items()))


def main():
    data = load_cache()
    print(f"Universo (caché V1): {len(data)} tickers\n")

    v1_open, b0, b1 = [], [], []
    for t, df in data.items():
        try:
            v1_open.extend(simulate_v1_open(t, df))
            b0.extend(simulate_early(t, df, "B0"))
            b1.extend(simulate_early(t, df, "B1"))
        except Exception as e:
            print(f"[error sim] {t}: {e}")

    with open(OUT_DIR / "trades_v1_open.json", "w", encoding="utf-8") as f:
        json.dump(v1_open, f, indent=2)
    with open(OUT_DIR / "trades_b0.json", "w", encoding="utf-8") as f:
        json.dump(b0, f, indent=2)
    with open(OUT_DIR / "trades_b1.json", "w", encoding="utf-8") as f:
        json.dump(b1, f, indent=2)

    print("--- Comparación principal (misma disciplina de ejecución: fill a apertura siguiente) ---")
    summary_rows = []
    summary_rows.append(summarize(v1_open, "V1_OPEN (baseline homogéneo)"))
    summary_rows.append(summarize(b0, "B0 (anticipado, sin RVOL)"))
    summary_rows.append(summarize(b1, f"B1 (anticipado, RVOL>={tl.EARLY_VOLUME_SPIKE_THRESHOLD})"))
    print()
    confirmation_breakdown(b0, "B0")
    confirmation_breakdown(b1, "B1")

    print("\n--- Solo primer evento por episodio (evita sobre-contar caídas prolongadas) ---")
    b0_first = [t for t in b0 if t["is_first_in_episode"]]
    b1_first = [t for t in b1 if t["is_first_in_episode"]]
    summary_rows.append(summarize(b0_first, "B0 (solo 1er evento/episodio)"))
    summary_rows.append(summarize(b1_first, "B1 (solo 1er evento/episodio)"))

    print("\n--- Sensibilidad a umbral RVOL (descriptivo, NO para elegir parámetro de producción) ---")
    thresholds = [2.0, 3.0, 4.0, 5.0, 7.0]
    for th in thresholds:
        trades_th = []
        for tkr, df in data.items():
            trades_th.extend(simulate_early(tkr, df, "B1", rvol_threshold=th))
        summary_rows.append(summarize(trades_th, f"RVOL>={th}"))

    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump([r for r in summary_rows if r], f, indent=2)
    print(f"\nResumen -> {OUT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
