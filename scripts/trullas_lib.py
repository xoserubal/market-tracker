"""
Librería compartida del sistema Trullás (divergencias MACD/Volumen/RSI +
ejecución Fibonacci) — matemática de indicadores, detección de pivotes y la
lógica de "gate" de divergencia, usadas IDÉNTICAS por el calculador en vivo
(`scripts/trullas_signal_calculator.py`) y por el backtest
(`research/trullas_divergence_backtest_v1/backtest.py`).

Extraída 2026-09-20 a raíz de una revisión de un asesor externo (ver
CLAUDE.md, sección "Sistema Trullás") que señaló correctamente que ambos
scripts tenían cada uno su propia copia de `ema`/`rsi`/`find_pivots_low` —
mismo patrón de deriva ya sufrido antes en este proyecto (`calcCMF`
duplicado, `HARD_RULES` duplicadas antes de `ai_shared.py`). Con esta
extracción, los parámetros (`PIVOT_WINDOW`, `MIN_SWING_PCT`, niveles
Fibonacci...) tienen una única fuente de verdad — no pueden desincronizarse
entre lo que se valida en el backtest y lo que corre en producción.

Todos los parámetros son los mismos con los que se validó el backtest
2026-09-20 (research/trullas_divergence_backtest_v1/README.md) — no
recalibrados aquí.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── Parámetros — fuente única de verdad ─────────────────────────────────────
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL_SPAN = 9
RSI_PERIOD = 14
PIVOT_WINDOW = 5
MIN_SWING_PCT = 3.0
RETR_ENTRY_LOW = 0.23
RETR_ENTRY_HIGH = 0.25
RETR_TP = 0.382
ENTRY_WINDOW_BARS = 15
TIME_STOP_BARS = 20
RVOL_WINDOW = 20
EARLY_VOLUME_SPIKE_THRESHOLD = 4.0  # punto de partida de investigación, no calibrado (ver advisor externo)

# Escala GBX/GBp — algunos tickers .L de Yahoo vienen en peniques, no libras.
# Mismo hallazgo que research/koncorde_cross_backtest_2026-08/README.md.
GBX_SUFFIX = ".L"
GBX_THRESHOLD = 1000.0


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd_full(close: pd.Series):
    """Devuelve (línea MACD, línea señal, histograma) — EMA 12/26/9 estándar."""
    m = ema(close, MACD_FAST) - ema(close, MACD_SLOW)
    sig = ema(m, MACD_SIGNAL_SPAN)
    hist = m - sig
    return m, sig, hist


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.where(avg_loss != 0, 100.0)


def find_pivots_low(close: np.ndarray, window: int = PIVOT_WINDOW) -> list[int]:
    """Índices donde close[i] es el mínimo estricto en [i-window, i+window].
    Un pivote no se confirma hasta `window` barras después — lag real, no bug."""
    n = len(close)
    idx = []
    for i in range(window, n - window):
        seg = close[i - window:i + window + 1]
        if close[i] == seg.min() and (seg == close[i]).sum() == 1:
            idx.append(i)
    return idx


def rvol(volume: np.ndarray, idx: int, window: int = RVOL_WINDOW) -> float | None:
    """Volumen relativo de la sesión `idx` frente a la media de las `window`
    sesiones ANTERIORES (excluye la propia sesión `idx` de la media — mismo
    criterio que pidió el asesor externo, evita que un pico de hoy infle su
    propia referencia). `None` si no hay suficiente histórico previo.

    No se usa todavía en ninguna señal — se calcula y persiste para poder
    estudiar más adelante la hipótesis de detección anticipada mediante
    volumen extraordinario (ver CLAUDE.md, revisión del asesor externo
    2026-09-20), sin esperar meses adicionales a que exista histórico una
    vez se decida construir esa parte."""
    if idx < window:
        return None
    window_vals = volume[idx - window:idx]
    mean_vol = window_vals.mean()
    if mean_vol <= 0 or np.isnan(mean_vol):
        return None
    return float(volume[idx] / mean_vol)


def apply_gbx_scale_fix(ticker: str, df: pd.DataFrame, price_cols: list[str],
                         log_fn=print) -> None:
    """Corrige in-place el hallazgo de escala GBX/GBp en tickers .L —
    mismo criterio ya usado en cruce_rojo_d_portfolio.py y el backtest."""
    if ticker.endswith(GBX_SUFFIX) and df[price_cols[0]].mean() > GBX_THRESHOLD:
        for c in price_cols:
            df[c] = df[c] / 100.0
        log_fn(f"  [scale-fix] {ticker}: dividido por 100 (GBX->GBP sospechoso)")


def evaluate_pivot_pair(close: np.ndarray, macd_arr: np.ndarray, rsi_arr: np.ndarray,
                         vol: np.ndarray, a: int, b: int) -> dict | None:
    """Evalúa el par de pivotes de mínimo (a=más antiguo, b=más reciente):
    ¿hay divergencia MACD (gate obligatorio)? ¿RSI/Volumen confirman (tier)?
    Devuelve None si no pasa el gate MACD o el swing mínimo — en ese caso no
    hay señal, el resto de indicadores ni se consulta (literal del método).

    No decide si hay entrada HOY — eso lo resuelve find_entry_v1() escaneando
    hacia delante desde `b`, porque la zona de entrada puede tardar varias
    sesiones en alcanzarse."""
    c1, c2 = float(close[a]), float(close[b])
    if not (c2 < c1):
        return {"reason": "no_lower_low", "pivot1_close": c1, "pivot2_close": c2}

    swing_pct = (c1 - c2) / c1 * 100
    if swing_pct < MIN_SWING_PCT:
        return {"reason": "swing_too_small", "pivot1_close": c1, "pivot2_close": c2,
                "swing_pct": swing_pct}

    if np.isnan(macd_arr[a]) or np.isnan(macd_arr[b]):
        return {"reason": "insufficient_history", "pivot1_close": c1, "pivot2_close": c2,
                "swing_pct": swing_pct}

    macd_div = bool(macd_arr[b] > macd_arr[a])
    if not macd_div:
        return {"reason": "no_macd_divergence", "pivot1_close": c1, "pivot2_close": c2,
                "swing_pct": swing_pct, "macd_div": False}

    rsi_div = bool(not np.isnan(rsi_arr[a]) and not np.isnan(rsi_arr[b]) and rsi_arr[b] > rsi_arr[a])
    vol_div = bool(vol[b] > vol[a])  # Método A: volumen de la vela exacta del pivote
    # (no el pico del tramo — ver revisión del asesor externo, "Método B" sin
    # implementar, ambigüedad documentada en CLAUDE.md, no resuelta aquí)
    tier = 1
    if rsi_div:
        tier = 2
    if rsi_div and vol_div:
        tier = 3

    swing = c1 - c2
    entry_low = c2 + RETR_ENTRY_LOW * swing
    entry_high = c2 + RETR_ENTRY_HIGH * swing
    tp = c2 + RETR_TP * swing
    stop = c2

    return {
        "reason": None, "qualifies": True,
        "pivot1_close": c1, "pivot2_close": c2, "swing_pct": swing_pct,
        "macd_div": True, "rsi_div": rsi_div, "vol_div": vol_div, "tier": tier,
        "entry_low": entry_low, "entry_high": entry_high, "tp": tp, "stop": stop,
    }


def find_entry_v1(close: np.ndarray, entry_low: float, entry_high: float, stop: float,
                   start_idx: int, max_idx_exclusive: int) -> dict:
    """Escanea close[start_idx:max_idx_exclusive] buscando el primer cierre
    que caiga en [entry_low, entry_high] (fill EOD — el modelo validado en
    el backtest, no el de fills intradía). Si el precio rompe `stop` antes
    de entrar, la señal queda invalidada en ese punto.

    Devuelve {"outcome": "entry"|"invalidated"|"no_entry_yet", "idx": int|None}."""
    for j in range(start_idx, max_idx_exclusive):
        if close[j] <= stop:
            return {"outcome": "invalidated", "idx": j}
        if entry_low <= close[j] <= entry_high:
            return {"outcome": "entry", "idx": j}
    return {"outcome": "no_entry_yet", "idx": None}


# ── Detector anticipado (B0/B1) — investigación, no en producción ──────────
# Añadido 2026-09-20 a raíz de la propuesta de un asesor externo: identificar
# un posible mínimo ANTES de que el pivote fractal se confirme 5 sesiones
# después (ver CLAUDE.md, sección "Sistema Trullás — revisión de un asesor
# externo"). Ninguna función de aquí abajo se usa en
# trullas_signal_calculator.py ni en trullas_shadow_portfolio.py todavía —
# solo en research/trullas_early_detector_v1/.


def reference_confirmed_pivot_asof(pivots: list[int], t: int, window: int = PIVOT_WINDOW) -> int | None:
    """Último pivote de mínimo YA CONFIRMADO a fecha `t` (pivote p tal que
    p + window <= t, es decir, sus `window` barras de confirmación a la
    derecha ya han pasado en o antes de `t`). None si no hay ninguno.

    `pivots` puede ser la lista completa calculada sobre toda la serie —
    filtrar por `p + window <= t` es equivalente a recomputar find_pivots_low
    solo con datos hasta `t` (un pivote confirmado con datos futuros a t no
    pudo haber usado ninguna barra posterior a p+window para confirmarse),
    pero muchísimo más barato que repetir el escaneo día a día."""
    candidates = [p for p in pivots if p + window <= t]
    return candidates[-1] if candidates else None


def evaluate_early_candidate_b0(close: np.ndarray, macd_arr: np.ndarray,
                                 t: int, ref_pivot_idx: int | None) -> dict | None:
    """Variante B0 (control, SIN exigir volumen extraordinario) — aísla si
    anticiparse por sí solo (antes de la confirmación fractal) aporta algo,
    independientemente del volumen. Condición literal (asesor externo,
    sección 8.3-8.4): nuevo mínimo de 5 sesiones + inferior al pivote de
    referencia + divergencia MACD provisional contra ese mismo pivote.

    None si no califica. El pivote de referencia debe estar YA CONFIRMADO
    antes de `t` (nunca un pivote futuro) — responsabilidad del caller pasar
    el resultado de reference_confirmed_pivot_asof()."""
    if ref_pivot_idx is None or t < 5:
        return None
    c1, c2 = float(close[ref_pivot_idx]), float(close[t])
    if not (c2 < c1):
        return None
    if not (c2 < close[t - 5:t].min()):
        return None  # no es un mínimo nuevo de 5 sesiones
    swing_pct = (c1 - c2) / c1 * 100
    if swing_pct < MIN_SWING_PCT:
        return None
    if np.isnan(macd_arr[ref_pivot_idx]) or np.isnan(macd_arr[t]):
        return None
    if not (macd_arr[t] > macd_arr[ref_pivot_idx]):
        return None

    swing = c1 - c2
    return {
        "ref_pivot_idx": ref_pivot_idx, "t": t,
        "ref_pivot_close": c1, "provisional_low_close": c2, "swing_pct": swing_pct,
        "tp": c2 + RETR_TP * swing, "stop": c2,
    }
