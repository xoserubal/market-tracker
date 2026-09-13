"""
Snapshot de entrada (ATR_entry, pre_entry_low_5d, w1_ret_5d_at_entry) por
posicion -- compartido entre P1A (PROFIT_PROTECTION_V1), P1C
(INITIAL_RISK_V1) y P1B (ENTRY_TIMING_V1), Hoja de ruta consolidada
§3/§4/§5 (wiki/, firmada 2026-08-30).

Se calcula UNA VEZ por posicion/evento (via un fetch dedicado a yfinance
alrededor de entry_date) y se cachea -- evita reimplementar el mismo fetch
en tres scripts (mismo criterio que ai_shared.py) y evita el sesgo de usar
el ATR/retorno de "cuando P0 empezo a capturar" (2026-08-30) en vez del
valor real del dia de entrada para posiciones abiertas antes de esa fecha.

Todos los valores son honestos: si el fetch falla o no hay suficientes
barras, quedan en None con `error` documentado -- nunca se aproxima ni se
inventa un valor.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
CACHE_PATH = DATA / "p1_entry_snapshot_cache.json"


def _load_cache() -> dict:
    return json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _atr14(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float | None:
    if len(close) < 15:
        return None
    prev_c = np.roll(close, 1)
    prev_c[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))
    atr = np.mean(tr[-14:])
    return round(float(atr), 4) if not np.isnan(atr) else None


def fetch_entry_snapshot(ticker: str, entry_date: str) -> dict:
    """Descarga ~70 dias naturales terminando en entry_date (inclusive) y
    calcula, todo con datos hasta e incluyendo esa fecha (sin look-ahead):
      - atr_entry: ATR14 en unidades de precio, congelado al cierre de entry_date.
      - pre_entry_low_5d: minimo de Low en las 5 sesiones ANTERIORES a
        entry_date (excluye el propio dia de entrada) -- brazo D de P1C.
      - w1_ret_5d_at_entry: retorno propio del ticker (no vs SPY) en las 5
        sesiones terminando en entry_date -- predictor primario de P1B (H7).
    """
    end = (datetime.strptime(entry_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.strptime(entry_date, "%Y-%m-%d") - timedelta(days=70)).strftime("%Y-%m-%d")
    empty = {"atr_entry": None, "pre_entry_low_5d": None, "w1_ret_5d_at_entry": None, "error": None}
    try:
        df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    except Exception as e:
        return {**empty, "error": str(e)}
    if df is None or df.empty:
        return {**empty, "error": "empty_download"}
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance reciente devuelve columnas (Price, Ticker) incluso para un
        # solo ticker en forma de string -- se aplana al nivel de precio.
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close"])
    if len(df) < 2:
        return {**empty, "error": "insufficient_bars"}

    close = np.asarray(df["Close"], dtype=float).reshape(-1)
    high = np.asarray(df["High"], dtype=float).reshape(-1)
    low = np.asarray(df["Low"], dtype=float).reshape(-1)

    atr_entry = _atr14(high, low, close)
    # low[-1] es la sesion de entry_date; las 5 anteriores son low[-6:-1].
    pre_entry_low_5d = round(float(np.min(low[-6:-1])), 4) if len(low) >= 6 else None
    w1_ret_5d_at_entry = round(float((close[-1] / close[-6] - 1) * 100), 2) if len(close) >= 6 else None

    return {
        "atr_entry": atr_entry, "pre_entry_low_5d": pre_entry_low_5d,
        "w1_ret_5d_at_entry": w1_ret_5d_at_entry, "error": None,
    }


def get_entry_snapshot(cache_key: str, ticker: str, entry_date: str) -> dict:
    """cache_key tipicamente `f"{ticker}__{entry_date}"` (position_id/event_id).
    Solo refetchea si la entrada en cache no existe o quedo con error."""
    cache = _load_cache()
    if cache_key in cache and cache[cache_key].get("error") is None:
        return cache[cache_key]
    snap = fetch_entry_snapshot(ticker, entry_date)
    cache[cache_key] = snap
    _save_cache(cache)
    return snap
