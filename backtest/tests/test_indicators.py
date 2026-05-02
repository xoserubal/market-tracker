"""Tests unitarios para indicadores técnicos."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.rotation.indicators import sma, ema, atr, obv, cmf, macd, rsi


def make_series(values, start='2020-01-01', freq='W-FRI'):
    idx = pd.date_range(start=start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


# ── SMA ───────────────────────────────────────────────────────────────────────
def test_sma_known_values():
    s = make_series([1, 2, 3, 4, 5])
    result = sma(s, 3)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_sma_window_1():
    s = make_series([10, 20, 30])
    assert sma(s, 1).tolist() == pytest.approx([10, 20, 30])


# ── EMA ───────────────────────────────────────────────────────────────────────
def test_ema_converges():
    s = make_series([100.0] * 30)
    result = ema(s, 12)
    assert result.iloc[-1] == pytest.approx(100.0, abs=1e-6)


def test_ema_trend():
    values = list(range(1, 31))
    s = make_series(values)
    e = ema(s, 5)
    # EMA debe seguir la tendencia alcista
    assert e.iloc[-1] > e.iloc[10]


# ── ATR ───────────────────────────────────────────────────────────────────────
def test_atr_flat_market():
    # high=101, low=99, close=100 → TR=2 siempre → ATR(3)=2
    n = 20
    c = make_series([100.0] * n)
    h = make_series([101.0] * n)
    lo = make_series([99.0]  * n)
    result = atr(h, lo, c, window=3)
    assert result.dropna().iloc[-1] == pytest.approx(2.0, abs=0.01)


def test_atr_nan_before_window():
    n = 20
    c = make_series([100.0] * n)
    h = make_series([102.0] * n)
    lo = make_series([98.0]  * n)
    result = atr(h, lo, c, window=5)
    # TR es válido desde índice 0 (pandas max(axis=1) skipna=True, high-low siempre válido).
    # Con rolling(5, min_periods=5): primer valor válido en índice 4.
    assert pd.isna(result.iloc[3])
    assert not pd.isna(result.iloc[4])


# ── OBV ───────────────────────────────────────────────────────────────────────
def test_obv_up_trend():
    c = make_series([10, 11, 12, 11, 13])
    v = make_series([100, 200, 300, 150, 400])
    result = obv(c, v)
    assert result.iloc[1] == pytest.approx(200.0)   # up: +200
    assert result.iloc[2] == pytest.approx(500.0)   # up: +300
    assert result.iloc[3] == pytest.approx(350.0)   # down: -150
    assert result.iloc[4] == pytest.approx(750.0)   # up: +400


def test_obv_flat():
    c = make_series([10, 10, 10])
    v = make_series([100, 200, 300])
    result = obv(c, v)
    assert result.iloc[-1] == pytest.approx(0.0)


# ── CMF ───────────────────────────────────────────────────────────────────────
def test_cmf_neutral_volume():
    # close = midpoint de high-low → MFM=0 → CMF≈0
    n = 25
    c = make_series([100.0] * n)
    h = make_series([105.0] * n)
    lo = make_series([95.0]  * n)
    v = make_series([1000.0] * n)
    result = cmf(h, lo, c, v, window=20)
    assert result.dropna().iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_cmf_bullish():
    # close cerca del high → MFM positivo → CMF positivo
    n = 25
    c  = make_series([104.0] * n)
    h  = make_series([105.0] * n)
    lo = make_series([95.0]  * n)
    v  = make_series([1000.0] * n)
    result = cmf(h, lo, c, v, window=20)
    assert result.dropna().iloc[-1] > 0


def test_cmf_high_equals_low_no_crash():
    # high == low → división por 0 → debe devolver 0 (no NaN ni excepción)
    n = 25
    c  = make_series([100.0] * n)
    h  = c.copy()
    lo = c.copy()
    v  = make_series([1000.0] * n)
    result = cmf(h, lo, c, v, window=20)
    valid = result.dropna()
    assert (valid == 0.0).all()


# ── MACD ──────────────────────────────────────────────────────────────────────
def test_macd_uptrend_histogram_positive():
    values = list(range(1, 60))
    s = make_series(values)
    m = macd(s, 12, 26, 9)
    # En tendencia alcista fuerte, histograma debe ser positivo al final
    assert m['histogram'].dropna().iloc[-1] > 0


def test_macd_uses_ema_not_sma():
    s = make_series([100.0] * 30 + [200.0] * 30)
    m = macd(s, 12, 26, 9)
    # Con EMA, el MACD reacciona al salto; el histograma no debería ser 0 en el final
    hist = m['histogram'].dropna()
    assert not (hist == 0.0).all()


# ── RSI ───────────────────────────────────────────────────────────────────────
def test_rsi_all_up():
    # Serie con solo alzas → avg_loss=0 → RSI debe ser 100
    values = [float(i) for i in range(1, 25)]
    s = make_series(values)
    result = rsi(s, 14)
    valid = result.dropna()
    assert len(valid) > 0
    assert valid.iloc[-1] == pytest.approx(100.0, abs=0.1)


def test_rsi_all_down():
    values = [float(i) for i in range(25, 1, -1)]
    s = make_series(values)
    result = rsi(s, 14)
    valid = result.dropna()
    assert len(valid) > 0
    # Solo pérdidas → RSI debe ser muy bajo (cerca de 0)
    assert valid.iloc[-1] < 5


def test_rsi_bounds():
    import numpy as np
    values = np.random.randn(100).cumsum() + 100
    s = make_series(values.tolist())
    result = rsi(s, 14).dropna()
    assert (result >= 0).all() and (result <= 100).all()
