"""Tests unitarios para alpha.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.performance.forward_returns import compute_forward_returns
from src.performance.alpha import compute_alpha


def _prices_with_spy(ticker_weekly_ret: float, spy_weekly_ret: float, n_weeks=40):
    """Crea DataFrame diario con SPY y un ticker a retornos constantes."""
    fridays = pd.date_range('2020-01-03', periods=n_weeks, freq='W-FRI')
    daily_idx = pd.bdate_range('2020-01-02', fridays[-1])
    df = pd.DataFrame(index=daily_idx, columns=['SPY', 'XLK'], dtype=float)
    for day in daily_idx:
        week = len(pd.bdate_range('2020-01-02', day)) // 5
        week = min(week, n_weeks - 1)
        df.loc[day, 'SPY'] = 100.0 * (1 + spy_weekly_ret) ** week
        df.loc[day, 'XLK'] = 100.0 * (1 + ticker_weekly_ret) ** week
    return df


def test_spy_alpha_is_zero():
    """SPY vs SPY: alpha debe ser siempre 0."""
    prices = _prices_with_spy(0.01, 0.01)
    fwd   = compute_forward_returns(prices, horizons_weeks=[4, 13])
    alpha = compute_alpha(fwd)
    spy_alpha = alpha.xs('SPY', level='ticker')['alpha_4w'].dropna()
    assert np.allclose(spy_alpha.values, 0.0, atol=1e-10)


def test_identical_ticker_alpha_zero():
    """Ticker con retorno identico a SPY: alpha = 0."""
    prices = _prices_with_spy(0.01, 0.01)
    fwd   = compute_forward_returns(prices, horizons_weeks=[4])
    alpha = compute_alpha(fwd)
    xlk_alpha = alpha.xs('XLK', level='ticker')['alpha_4w'].dropna()
    assert np.allclose(xlk_alpha.values, 0.0, atol=1e-10)


def test_constant_outperformance():
    """Ticker +1%/w vs SPY +0%/w: alpha_4w ~ (1.01^4 - 1) - (1^4 - 1) ≈ 4.06%."""
    prices = _prices_with_spy(ticker_weekly_ret=0.01, spy_weekly_ret=0.0)
    fwd   = compute_forward_returns(prices, horizons_weeks=[4])
    alpha = compute_alpha(fwd)
    xlk_alpha = alpha.xs('XLK', level='ticker')['alpha_4w'].dropna()
    expected = (1.01 ** 4) - 1.0   # SPY flat -> alpha = ticker ret
    assert np.allclose(xlk_alpha.values, expected, atol=1e-6)


def test_alpha_nan_when_spy_missing():
    """Ticker con dato pero SPY sin dato en esa fecha: alpha = NaN."""
    # Crear precios sin SPY
    daily_idx = pd.bdate_range('2020-01-02', periods=50)
    prices = pd.DataFrame({'XLK': 100.0}, index=daily_idx)
    fwd   = compute_forward_returns(prices, horizons_weeks=[4])
    alpha = compute_alpha(fwd)
    # Sin SPY en el dataset, todos los alphas deben ser NaN
    assert alpha['alpha_4w'].isna().all()


def test_alpha_columns_present():
    """compute_alpha debe anadir alpha_4w, alpha_13w, alpha_26w."""
    prices = _prices_with_spy(0.01, 0.01, n_weeks=60)
    fwd   = compute_forward_returns(prices, horizons_weeks=[4, 13, 26])
    alpha = compute_alpha(fwd)
    for col in ['alpha_4w', 'alpha_13w', 'alpha_26w']:
        assert col in alpha.columns
