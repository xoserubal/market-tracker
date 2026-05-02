"""
Indicadores técnicos — frecuencia diaria, muestreados al viernes.

Flujo correcto (coincide con server.js):
  1. load_daily_ohlcv()  → DataFrame diario con OHLCV
  2. compute_daily_indicators() → indicadores calculados sobre diarios
  3. sample_to_friday() → tomar el último valor hábil de cada semana W-FRI

Todos los indicadores replican server.js exactamente:
  - CMF(20): 20 velas diarias (≈4 semanas)
  - MACD(12,26,9): EMA con SMA-seed, sobre diarios
  - RSI(14): Wilder con SMA-seed, sobre diarios
  - OBV + SMA50(OBV): sobre diarios
  - SMA20 / SMA200: 20 y 200 días hábiles
  - ATR14: 14 días hábiles
  - volRatio: media vol 20d / vol 60d
  - ret_4w / ret_13w: pct_change(21) / pct_change(63) sobre diarios
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ticker_to_filename(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "", ticker.replace("^", "").replace("=", ""))


# ── Carga de datos ────────────────────────────────────────────────────────────

def load_daily_ohlcv(ticker: str, raw_dir: Path) -> pd.DataFrame | None:
    """
    Carga OHLCV diario desde data/raw/yahoo_{ticker}.parquet.

    Devuelve DataFrame con columnas: high, low, close, volume.
    Indexado por fecha diaria, sin NaN en close.
    """
    safe = _ticker_to_filename(ticker)
    path = raw_dir / f"yahoo_{safe}.parquet"
    if not path.exists():
        return None

    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index).normalize()

    close_col = ('Adj Close' if 'Adj Close' in df.columns
                 else 'price' if 'price' in df.columns
                 else 'Close' if 'Close' in df.columns
                 else None)
    if close_col is None:
        return None

    high_col   = df['High']   if 'High'   in df.columns else df[close_col]
    low_col    = df['Low']    if 'Low'    in df.columns else df[close_col]
    volume_col = df['Volume'].fillna(0.0) if 'Volume' in df.columns else pd.Series(0.0, index=df.index)

    daily = pd.DataFrame({
        'high':   high_col,
        'low':    low_col,
        'close':  df[close_col],
        'volume': volume_col,
    })
    daily.index.name = 'date'
    return daily.dropna(subset=['close'])


def load_weekly_ohlcv(ticker: str, raw_dir: Path) -> pd.DataFrame | None:
    """Backward-compat: carga diario y resamplea a semanal W-FRI."""
    daily = load_daily_ohlcv(ticker, raw_dir)
    if daily is None:
        return None
    weekly = pd.DataFrame({
        'high':   daily['high'].resample('W-FRI').max(),
        'low':    daily['low'].resample('W-FRI').min(),
        'close':  daily['close'].resample('W-FRI').last(),
        'volume': daily['volume'].resample('W-FRI').sum(),
    })
    weekly.index.name = 'date'
    return weekly.dropna(subset=['close'])


# ── Indicadores base (backward-compat para tests) ────────────────────────────

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=window, min_periods=window).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff())
    return (direction * volume).fillna(0).cumsum()


def cmf(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    window: int = 20,
) -> pd.Series:
    hl = high - low
    mfm = ((close - low) - (high - close)) / hl.replace(0.0, np.nan)
    mfm = mfm.fillna(0.0)
    mfv = mfm * volume
    vol_sum = volume.rolling(window=window, min_periods=window).sum()
    return mfv.rolling(window=window, min_periods=window).sum() / vol_sum.replace(0.0, np.nan)


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict[str, pd.Series]:
    macd_line   = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal_period)
    histogram   = macd_line - signal_line
    return {'macd': macd_line, 'signal': signal_line, 'histogram': histogram}


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI con EWM alpha=1/N (backward-compat para unit tests)."""
    delta  = close.diff()
    gains  = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)
    avg_gain = gains.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.where(avg_loss != 0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
    return result.where(avg_loss != 0.0, 100.0)


# ── Indicadores diarios (réplica exacta de server.js) ────────────────────────

def _ema_sma_seeded(series: pd.Series, period: int) -> pd.Series:
    """
    EMA con SMA-seed sobre los primeros N valores no-NaN.
    Replica exactamente server.js emaFull(data, period).
    """
    values = series.values.astype(float)
    n = len(values)
    result = np.full(n, np.nan)

    k = 2.0 / (period + 1)

    # Posiciones no-NaN
    valid_idx = [i for i in range(n) if not np.isnan(values[i])]
    if len(valid_idx) < period:
        return pd.Series(result, index=series.index)

    # Seed = SMA de los primeros 'period' valores válidos
    seed_pos = valid_idx[period - 1]
    e = float(np.mean([values[i] for i in valid_idx[:period]]))
    result[seed_pos] = e

    # EMA a partir del (period)-ésimo valor válido
    for i in range(seed_pos + 1, n):
        if np.isnan(values[i]):
            result[i] = result[i - 1]      # carry-forward sobre gaps
        else:
            e = values[i] * k + e * (1.0 - k)
            result[i] = e

    return pd.Series(result, index=series.index)


def macd_sma_seeded(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict[str, pd.Series]:
    """
    MACD con SMA-seed, réplica de server.js calcMACD().

    server.js alinea ema12[i+14] - ema26[i], lo que equivale a
    pd.Series(e12) - pd.Series(e26) cuando ambas comparten el mismo
    índice de fechas (pandas las alinea automáticamente).
    """
    e12 = _ema_sma_seeded(close, fast)
    e26 = _ema_sma_seeded(close, slow)
    macd_line   = e12 - e26                         # NaN hasta barra 25
    signal_line = _ema_sma_seeded(macd_line, signal_period)
    histogram   = macd_line - signal_line
    return {'macd': macd_line, 'signal': signal_line, 'histogram': histogram}


def rsi_wilder_explicit(close: pd.Series, window: int = 14) -> pd.Series:
    """
    RSI Wilder con SMA-seed explícito. Réplica de server.js calcRSI().

    avgGain/avgLoss se inicializan con SMA de las primeras 'window'
    variaciones, luego se suavizan con Wilder: (prev*(N-1) + curr) / N.
    """
    values = close.values.astype(float)
    n = len(values)
    result = np.full(n, np.nan)

    if n < window + 1:
        return pd.Series(result, index=close.index)

    # SMA seed sobre los primeros 'window' diffs
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, window + 1):
        d = values[i] - values[i - 1]
        if d > 0:
            avg_gain += d / window
        else:
            avg_loss += -d / window

    if avg_loss == 0.0:
        result[window] = 100.0
    else:
        result[window] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    # Wilder rolling
    for i in range(window + 1, n):
        d = values[i] - values[i - 1]
        avg_gain = (avg_gain * (window - 1) + max(d, 0.0)) / window
        avg_loss = (avg_loss * (window - 1) + max(-d, 0.0)) / window
        if avg_loss == 0.0:
            result[i] = 100.0
        else:
            result[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    return pd.Series(result, index=close.index)


# ── Pipeline principal ────────────────────────────────────────────────────────

def compute_daily_indicators(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula todos los indicadores sobre OHLCV diario.

    Columnas de salida compatibles con score.py:
      close, high, low, volume,
      sma20, sma50, sma200, atr14,
      obv, obv_sma50, cmf20,
      macd_hist, rsi14,
      vol4w (= vol20d), vol12w (= vol60d),
      ret_1w (5d), ret_2w (10d), ret_4w (21d), ret_13w (63d)
    """
    c  = daily_df['close']
    h  = daily_df['high']
    lo = daily_df['low']
    v  = daily_df['volume']

    ind = pd.DataFrame(index=daily_df.index)
    ind['close']  = c
    ind['high']   = h
    ind['low']    = lo
    ind['volume'] = v

    # SMAs sobre diarios (coincide con server.js calcSMA)
    ind['sma20']  = sma(c, 20)    # 20 días hábiles ≈ 1 mes
    ind['sma50']  = sma(c, 50)
    ind['sma200'] = sma(c, 200)   # 200 días hábiles ≈ 10 meses

    # ATR14 diario
    ind['atr14'] = atr(h, lo, c, 14)

    # OBV diario + SMA50(OBV) diaria
    obv_s         = obv(c, v)
    ind['obv']       = obv_s
    ind['obv_sma50'] = sma(obv_s, 50)

    # CMF(20) diario — 20 velas diarias ≈ 4 semanas
    ind['cmf20'] = cmf(h, lo, c, v, 20)

    # MACD(12,26,9) con SMA-seed (replica server.js)
    m = macd_sma_seeded(c, 12, 26, 9)
    ind['macd_hist'] = m['histogram']

    # RSI(14) Wilder con SMA-seed explícito (replica server.js)
    ind['rsi14'] = rsi_wilder_explicit(c, 14)

    # Vol ratio: vol20d / vol60d (alias vol4w / vol12w para compatibilidad)
    ind['vol4w']  = v.rolling(20,  min_periods=20).mean()   # vol20d
    ind['vol12w'] = v.rolling(60,  min_periods=60).mean()   # vol60d

    # Retornos en % sobre diarios (alineados con server.js ret(5)/ret(10)/ret(21)/ret(63))
    ind['ret_1w']  = c.pct_change(5)  * 100.0   # 5 días ≈ 1 semana
    ind['ret_2w']  = c.pct_change(10) * 100.0   # 10 días ≈ 2 semanas
    ind['ret_4w']  = c.pct_change(21) * 100.0   # 21 días ≈ 1 mes (app m1)
    ind['ret_13w'] = c.pct_change(63) * 100.0   # 63 días ≈ 13 semanas (app m3)

    return ind


def sample_to_friday(daily_ind: pd.DataFrame) -> pd.DataFrame:
    """
    Muestrea indicadores diarios al último día hábil de cada semana W-FRI.

    Equivale a: "el valor que la app vería si se ejecutara el viernes
    al cierre de mercado" (o jueves si viernes es festivo).
    """
    return daily_ind.resample('W-FRI').last()


# ── Backward-compat: compute_all_indicators sobre semanal ───────────────────

def compute_all_indicators(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """
    Backward-compat (usado por unit tests de indicadores).
    Calcula sobre datos OHLCV ya resampleados a semanal.
    NO usar en el simulador — usar compute_daily_indicators + sample_to_friday.
    """
    c  = ohlcv['close']
    h  = ohlcv['high']
    lo = ohlcv['low']
    v  = ohlcv['volume']

    ind = pd.DataFrame(index=ohlcv.index)
    ind['close']  = c
    ind['high']   = h
    ind['low']    = lo
    ind['volume'] = v

    ind['sma20']  = sma(c, 20)
    ind['sma50']  = sma(c, 50)
    ind['sma200'] = sma(c, 200)
    ind['atr14']  = atr(h, lo, c, 14)

    obv_series       = obv(c, v)
    ind['obv']       = obv_series
    ind['obv_sma50'] = sma(obv_series, 50)

    ind['cmf20'] = cmf(h, lo, c, v, 20)

    m = macd(c, 12, 26, 9)
    ind['macd_hist'] = m['histogram']

    ind['rsi14'] = rsi(c, 14)

    ind['vol4w']  = v.rolling(4,  min_periods=4).mean()
    ind['vol12w'] = v.rolling(12, min_periods=12).mean()

    ind['ret_1w']  = c.pct_change(1)  * 100.0
    ind['ret_2w']  = c.pct_change(2)  * 100.0
    ind['ret_4w']  = c.pct_change(4)  * 100.0
    ind['ret_13w'] = c.pct_change(13) * 100.0

    return ind
