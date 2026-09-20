"""
Calculadora de señales del sistema "Trullás" (divergencias MACD/Volumen/RSI
+ ejecución por retroceso de Fibonacci) sobre el universo de Portfolio
Tracker (portfolio.json).

Validado en research/trullas_divergence_backtest_v1/ (backtest 2026-09-20,
118 tickers, 2019→hoy): entrada solo en divergencias ALCISTAS en mínimos —
MACD es el filtro obligatorio (sin divergencia MACD no hay señal, el resto
no se consulta), RSI y Volumen confirman → 3 niveles de confianza (T1=solo
MACD, T2=+RSI, T3=+RSI+Volumen). TP en el 38.2%, stop en la ruptura del
pivote de origen, time-stop a 20 sesiones si no se toca ni TP ni stop. Es
el mejor punto de todo lo probado en el backtest — ver
research/trullas_divergence_backtest_v1/README.md para la comparativa
completa (bate a "dejar correr hasta cruce MACD" y a cualquier otro nivel
de la escalera Fibonacci).

**Ejecución — corregida 2026-09-21** (ver CLAUDE.md, "corrección de
V1_OPEN"): orden límite real, evaluada por la APERTURA de cada sesión (no
el cierre) desde que confirma la divergencia hasta que expira la ventana
de 15 sesiones — rellena si `entry_low <= open <= entry_high`. El modelo
original (fill al mismo cierre que genera la señal) sobreestimaba el
resultado real ejecutable: verificado contra las 82 señales del backtest,
solo el 41% tenían una apertura siguiente realmente válida dentro de la
zona; el resto ya había rebasado la zona (50%) o roto el stop (8.5%).
`find_entry_executable()` en `trullas_lib.py` filtra esos casos
correctamente. Coste medido en el backtest: n 82→54, Sharpe-like
0.293→0.151 (ver `research/trullas_early_detector_v1/README.md`).

Toda la matemática de indicadores/pivotes/gate de divergencia vive en
scripts/trullas_lib.py, compartida con el backtest — no una copia paralela
(ver CLAUDE.md, revisión de un asesor externo 2026-09-20 que señaló el
riesgo de deriva de tener esta lógica duplicada en dos archivos).

Salida:
- docs/data/trullas_signals.json — snapshot de HOY por ticker, servido al
  tab trullas.html (vía server.js) y consumido por
  scripts/trullas_shadow_portfolio.py para decidir entradas/salidas.
- docs/data/trullas_signals_history.jsonl — una fila por (ticker, fecha),
  append-only, dedup — para poder hacer estudios/simulaciones retrospectivas
  más adelante sobre datos propios en vez de tener que re-descargar y
  reconstruir desde yfinance. Incluye `rvol20` (volumen relativo a 20
  sesiones) aunque hoy no alimenta ninguna señal — sembrado ahora para que,
  si más adelante se decide investigar la hipótesis de detección anticipada
  vía volumen extraordinario (ver revisión del asesor externo, CLAUDE.md),
  ya haya histórico acumulado en vez de tener que esperar meses desde cero.

Universo: todos los tickers de portfolio.json + los que estén abiertos en
la cartera TRULLAS_SHADOW de ai_picks.json (para que una posición abierta
siga teniendo señal aunque el ticker salga de portfolio.json — mismo
criterio que koncorde_calculator.py con left_universe).

Uso:
    py -3 scripts/trullas_signal_calculator.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import trullas_lib as tl

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
OUT_PATH = DATA / "trullas_signals.json"
HISTORY_PATH = DATA / "trullas_signals_history.jsonl"
PICKS_PATH = DATA / "ai_picks.json"
PORTFOLIO_PATH = ROOT / "portfolio.json"

CARTERA_NAME = "TRULLAS_SHADOW"

HISTORY_DAYS = 760  # ~3 años: sobra para varios ciclos de pivotes + warmup MACD(26)/RSI(14)


def load_universe() -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Devuelve (tickers, ticker->sección de portfolio.json, ticker->entry_date
    si está abierto en TRULLAS_SHADOW)."""
    tickers: set[str] = set()
    sections: dict[str, str] = {}
    if PORTFOLIO_PATH.exists():
        data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
        for sec in data.get("sections", []):
            for item in sec.get("items", []):
                tk = item.get("ticker")
                if tk:
                    tickers.add(tk)
                    sections.setdefault(tk, sec.get("name", ""))

    entry_dates: dict[str, str] = {}
    if PICKS_PATH.exists():
        picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
        ptf = picks.get("portfolios", {}).get(CARTERA_NAME, {})
        for pos in ptf.get("positions", []):
            tk = pos.get("ticker")
            if tk:
                tickers.add(tk)
                entry_dates[tk] = pos.get("entry_date")

    return sorted(tickers), sections, entry_dates


def download_ohlcv(tickers: list[str]) -> dict[str, pd.DataFrame]:
    end = datetime.today()
    start = (end - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    out: dict[str, pd.DataFrame] = {}
    batch_size = 25
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            raw = yf.download(batch, start=start, auto_adjust=False, progress=False,
                               group_by="ticker", threads=False)
        except Exception as e:
            print(f"  [download error] batch {i // batch_size + 1}: {e}")
            continue
        for tk in batch:
            try:
                sub = raw[tk] if len(batch) > 1 else raw
                df = sub[["Open", "High", "Low", "Close", "Volume"]].copy()
                df.columns = ["open", "high", "low", "close", "volume"]
                df = df.dropna(subset=["close"])
                if df.empty or len(df) < 100:
                    continue
                tl.apply_gbx_scale_fix(tk, df, ["open", "high", "low", "close"])
                out[tk] = df
            except Exception:
                continue
    return out


def compute_signal_for_ticker(ticker: str, df: pd.DataFrame, entry_date: str | None) -> dict:
    close = df["close"].to_numpy()
    dates = [str(d.date()) for d in df.index]
    vol = df["volume"].to_numpy()
    open_ = df["open"].to_numpy()
    n = len(close)

    macd_s, sig_s, hist_s = tl.macd_full(df["close"])
    macd_arr, sig_arr, hist_arr = macd_s.to_numpy(), sig_s.to_numpy(), hist_s.to_numpy()
    rsi_arr = tl.rsi(df["close"]).to_numpy()
    rvol20 = tl.rvol(vol, n - 1)

    result: dict = {
        "ticker": ticker,
        "price": float(close[-1]),
        "open": float(open_[-1]),
        "price_date": dates[-1],
        "volume": float(vol[-1]),
        "rvol20": None if rvol20 is None else round(rvol20, 2),
        "macd": None if np.isnan(macd_arr[-1]) else round(float(macd_arr[-1]), 4),
        "macd_signal": None if np.isnan(sig_arr[-1]) else round(float(sig_arr[-1]), 4),
        "macd_hist": None if np.isnan(hist_arr[-1]) else round(float(hist_arr[-1]), 4),
        "rsi14": None if np.isnan(rsi_arr[-1]) else round(float(rsi_arr[-1]), 1),
        "signal_state": None,
        "pivot1_date": None, "pivot1_close": None,
        "pivot2_date": None, "pivot2_close": None,
        "swing_pct": None,
        "macd_div": None, "rsi_div": None, "vol_div": None, "tier": None,
        "entry_low": None, "entry_high": None, "tp": None, "stop": None,
        "entry_signal_date": None,
        "bars_remaining_in_window": None,
        "bars_held_since_entry": None,
    }

    # Si el ticker está abierto en TRULLAS_SHADOW, calcula cuántas barras
    # lleva desde la entrada real (índice en ESTA serie, no calendario —
    # necesario para aplicar el time-stop de 20 sesiones con precisión).
    if entry_date and entry_date in dates:
        entry_pos = dates.index(entry_date)
        result["bars_held_since_entry"] = n - 1 - entry_pos

    pivots = tl.find_pivots_low(close)
    if len(pivots) < 2:
        result["signal_state"] = "no_pivots_yet"
        return result

    a, b = pivots[-2], pivots[-1]
    result["pivot1_date"] = dates[a]
    result["pivot2_date"] = dates[b]

    ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
    result["pivot1_close"] = ev.get("pivot1_close")
    result["pivot2_close"] = ev.get("pivot2_close")
    if ev.get("swing_pct") is not None:
        result["swing_pct"] = round(ev["swing_pct"], 2)
    if ev.get("macd_div") is not None:
        result["macd_div"] = ev["macd_div"]

    if not ev.get("qualifies"):
        result["signal_state"] = ev["reason"]
        return result

    result.update(rsi_div=ev["rsi_div"], vol_div=ev["vol_div"], tier=ev["tier"])
    entry_low, entry_high, tp, stop = ev["entry_low"], ev["entry_high"], ev["tp"], ev["stop"]
    result.update(entry_low=round(entry_low, 4), entry_high=round(entry_high, 4),
                   tp=round(tp, 4), stop=round(stop, 4))

    window_end = min(b + 1 + tl.ENTRY_WINDOW_BARS, n)
    # find_entry_executable() (no find_entry_v1) -- corregido 2026-09-21:
    # orden límite real evaluada por APERTURA, no relleno ingenuo al mismo
    # cierre que genera la señal. Ver CLAUDE.md, "corrección de V1_OPEN".
    scan = tl.find_entry_executable(open_, entry_low, entry_high, stop, b + 1, window_end)

    if scan["outcome"] == "invalidated":
        result["signal_state"] = "invalidated"
        result["entry_signal_date"] = dates[scan["idx"]]
        return result

    if scan["outcome"] == "no_entry_yet":
        bars_since_pivot2 = (n - 1) - b
        if bars_since_pivot2 >= tl.ENTRY_WINDOW_BARS:
            result["signal_state"] = "expired_no_pullback"
        else:
            # Informativo para la pestaña discrecional (no cambia la lógica de
            # elegibilidad, que sigue siendo "sin entry_idx dentro de la
            # ventana"): si el precio ya rebasó la zona de entrada, lo más
            # probable es que ya no vuelva a retroceder tan abajo — distinto
            # de "todavía no ha rebotado lo suficiente desde el mínimo".
            # Referencia la apertura de hoy (open_[-1]), no el cierre --
            # coherente con que la entrada ahora se decide por apertura.
            if open_[-1] > entry_high:
                result["signal_state"] = "waiting_pullback_ran_ahead"
            else:
                result["signal_state"] = "waiting_pullback_below_zone"
            result["bars_remaining_in_window"] = tl.ENTRY_WINDOW_BARS - bars_since_pivot2
        return result

    entry_idx = scan["idx"]
    result["entry_signal_date"] = dates[entry_idx]
    result["signal_state"] = "entry_today" if entry_idx == n - 1 else "entry_in_past"
    return result


def _append_history(rows: list[dict]) -> int:
    """Append-only, dedup por (ticker, date) — mismo patrón que
    koncorde_signals_history.jsonl/mirror_signals.jsonl. Relee el fichero
    completo para dedupear (crece ~118 filas/día, barato de releer durante
    mucho tiempo antes de que haga falta un índice más sofisticado)."""
    seen: set[tuple[str, str]] = set()
    if HISTORY_PATH.exists():
        with HISTORY_PATH.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    seen.add((row.get("ticker"), row.get("date")))
                except Exception:
                    continue

    new_rows = [r for r in rows if (r["ticker"], r["date"]) not in seen]
    if new_rows:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(new_rows)


def run() -> int:
    today = datetime.today().strftime("%Y-%m-%d")
    tickers, sections, entry_dates = load_universe()
    if not tickers:
        print("Sin tickers en portfolio.json — nada que calcular.")
        return 1
    print(f"Trullás: {len(tickers)} tickers (universo Portfolio Tracker + posiciones {CARTERA_NAME})")

    price_data = download_ohlcv(tickers)
    print(f"  Descargados {len(price_data)}/{len(tickers)} tickers OK")

    out: dict[str, dict] = {}
    history_rows: list[dict] = []
    failed: list[str] = []
    for tk in tickers:
        df = price_data.get(tk)
        if df is None or df.empty:
            failed.append(tk)
            continue
        try:
            sig = compute_signal_for_ticker(tk, df, entry_dates.get(tk))
            sig["section"] = sections.get(tk, "")
            sig["updated"] = today
            out[tk] = sig
            history_rows.append({
                "date": sig["price_date"], "ticker": tk,
                "price": sig["price"], "open": sig["open"], "volume": sig["volume"], "rvol20": sig["rvol20"],
                "macd": sig["macd"], "macd_signal": sig["macd_signal"], "macd_hist": sig["macd_hist"],
                "rsi14": sig["rsi14"],
                "pivot1_date": sig["pivot1_date"], "pivot1_close": sig["pivot1_close"],
                "pivot2_date": sig["pivot2_date"], "pivot2_close": sig["pivot2_close"],
                "swing_pct": sig["swing_pct"], "macd_div": sig["macd_div"],
                "rsi_div": sig["rsi_div"], "vol_div": sig["vol_div"], "tier": sig["tier"],
                "entry_low": sig["entry_low"], "entry_high": sig["entry_high"],
                "tp": sig["tp"], "stop": sig["stop"],
                "signal_state": sig["signal_state"], "entry_signal_date": sig["entry_signal_date"],
            })
        except Exception as e:
            print(f"  [error] {tk}: {e}")
            failed.append(tk)

    n_entry_today = sum(1 for s in out.values() if s["signal_state"] == "entry_today")
    n_waiting = sum(1 for s in out.values()
                     if s["signal_state"] in ("waiting_pullback_below_zone", "waiting_pullback_ran_ahead"))
    print(f"  Calculados: {len(out)}  Fallos: {len(failed)}")
    print(f"  entry_today={n_entry_today}  waiting_pullback={n_waiting}")
    if failed:
        print(f"  Fallos: {failed[:15]}{'…' if len(failed) > 15 else ''}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({"date": today, "tickers": out}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  trullas_signals.json escrito ({len(out)} tickers)")

    n_new_history = _append_history(history_rows)
    print(f"  trullas_signals_history.jsonl: {n_new_history} fila(s) nueva(s) ({len(history_rows)} evaluadas)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run())
