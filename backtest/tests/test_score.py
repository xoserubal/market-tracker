"""Tests unitarios para RotationScore."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.rotation.score import rotation_score


def _row(**kwargs) -> pd.Series:
    """Helper: crea una fila de indicadores con valores por defecto razonables."""
    defaults = {
        'close': 100.0, 'sma20': 95.0, 'sma200': 80.0, 'atr14': 2.0,
        'obv': 5000.0, 'obv_sma50': 4000.0, 'cmf20': 0.1,
        'macd_hist': 0.5, 'rsi14': 55.0,
        'vol4w': 1200.0, 'vol12w': 1000.0,
        'ret_1w': 1.0, 'ret_2w': 2.0, 'ret_4w': 4.0, 'ret_13w': 8.0,
    }
    defaults.update(kwargs)
    return pd.Series(defaults)


def _spy(**kwargs) -> pd.Series:
    defaults = {
        'close': 100.0, 'sma200': 80.0,
        'ret_4w': 2.0, 'ret_13w': 5.0, 'ret_2w': 1.0,
    }
    defaults.update(kwargs)
    return pd.Series(defaults)


# ── Score total ───────────────────────────────────────────────────────────────
def test_score_perfect_10():
    """Cuando todos los criterios se cumplen → 10."""
    # atr14=10 → (close100-sma20_90)/10 = 1.0 < 1.5 (anti-ext OK)
    t = _row(ret_13w=10.0, ret_4w=5.0, close=100.0, sma200=80.0,
             cmf20=0.5, obv=5000.0, obv_sma50=3000.0,
             vol4w=1500.0, vol12w=1000.0,
             macd_hist=1.0, rsi14=55.0,
             sma20=90.0, atr14=10.0)
    s = _spy(ret_13w=5.0, ret_4w=3.0)
    result = rotation_score(t, s)
    assert result['total'] == pytest.approx(10.0)
    assert result['blockA'] == pytest.approx(4.0)
    assert result['blockB'] == pytest.approx(3.0)
    assert result['blockC'] == pytest.approx(3.0)


def test_score_zero():
    """Cuando ningún criterio se cumple → 0."""
    t = _row(
        ret_13w=0.0, ret_4w=0.0,
        close=50.0, sma200=100.0,      # close < sma200 → sin tendencia
        cmf20=-0.1,                    # CMF negativo
        obv=1000.0, obv_sma50=5000.0, # OBV < SMA50
        vol4w=800.0, vol12w=1000.0,   # vol ratio < 1.10
        macd_hist=-0.5,               # MACD negativo
        rsi14=80.0,                   # RSI fuera del rango 40-70
        sma20=60.0, atr14=5.0,        # close < sma20 → no antiExt
    )
    s = _spy(ret_13w=5.0, ret_4w=5.0)
    result = rotation_score(t, s)
    assert result['total'] == pytest.approx(0.0)


def test_score_nan_input_gives_zero_not_crash():
    """NaN en inputs críticos → 0 pts en ese criterio, no excepción."""
    t = _row(sma200=float('nan'), cmf20=float('nan'), rsi14=float('nan'))
    s = _spy()
    result = rotation_score(t, s)
    assert result['components']['trend_abs_pts'] == 0.0
    assert result['components']['cmf_pts']       == 0.0
    assert result['components']['rsi_pts']        == 0.0
    assert result['total'] is not None  # no debe ser None


# ── Criterios individuales ────────────────────────────────────────────────────
def test_rs13w_threshold():
    """RS 13w > 2.0% → 2 pts; exactamente 2.0% → 0 pts (no supera)."""
    s = _spy(ret_13w=0.0)
    t_above = _row(ret_13w=2.1)
    t_exact = _row(ret_13w=2.0)
    t_below = _row(ret_13w=1.9)
    assert rotation_score(t_above, s)['components']['rs_13w_pts'] == 2.0
    assert rotation_score(t_exact, s)['components']['rs_13w_pts'] == 0.0
    assert rotation_score(t_below, s)['components']['rs_13w_pts'] == 0.0


def test_rs4w_threshold():
    """RS 4w > 1.0% vs SPY → 1 pt."""
    s = _spy(ret_4w=0.0)
    assert rotation_score(_row(ret_4w=1.1), s)['components']['rs_4w_pts'] == 1.0
    assert rotation_score(_row(ret_4w=1.0), s)['components']['rs_4w_pts'] == 0.0


def test_trend_abs_criterion():
    """close > SMA200 → 1 pt."""
    t_above = _row(close=100.0, sma200=90.0)
    t_below = _row(close=80.0,  sma200=90.0)
    s = _spy()
    assert rotation_score(t_above, s)['components']['trend_abs_pts'] == 1.0
    assert rotation_score(t_below, s)['components']['trend_abs_pts'] == 0.0


def test_vol_ratio_criterion():
    """vol4w/vol12w > 1.10 → 1 pt."""
    s = _spy()
    assert rotation_score(_row(vol4w=1200, vol12w=1000), s)['components']['vol_rel_pts'] == 1.0
    assert rotation_score(_row(vol4w=1000, vol12w=1000), s)['components']['vol_rel_pts'] == 0.0
    assert rotation_score(_row(vol4w=1100, vol12w=1000), s)['components']['vol_rel_pts'] == 0.0  # exactamente 1.10 ≠ > 1.10


def test_rsi_range_criterion():
    """RSI entre 40 y 70 inclusive → 1 pt."""
    s = _spy()
    assert rotation_score(_row(rsi14=40.0), s)['components']['rsi_pts'] == 1.0
    assert rotation_score(_row(rsi14=70.0), s)['components']['rsi_pts'] == 1.0
    assert rotation_score(_row(rsi14=55.0), s)['components']['rsi_pts'] == 1.0
    assert rotation_score(_row(rsi14=39.9), s)['components']['rsi_pts'] == 0.0
    assert rotation_score(_row(rsi14=70.1), s)['components']['rsi_pts'] == 0.0


def test_anti_extension_criterion():
    """close > sma20 AND (close-sma20)/atr14 < 1.5 → 1 pt."""
    s = _spy()
    # Justo por debajo del umbral de extensión
    t_ok = _row(close=100.0, sma20=90.0, atr14=10.0)  # (100-90)/10 = 1.0 < 1.5 ✓
    # Extendido
    t_ext = _row(close=120.0, sma20=90.0, atr14=10.0)  # (120-90)/10 = 3.0 > 1.5 ✗
    # Por debajo de SMA20
    t_below = _row(close=85.0, sma20=90.0, atr14=10.0)
    assert rotation_score(t_ok,    s)['components']['no_ext_pts'] == 1.0
    assert rotation_score(t_ext,   s)['components']['no_ext_pts'] == 0.0
    assert rotation_score(t_below, s)['components']['no_ext_pts'] == 0.0
