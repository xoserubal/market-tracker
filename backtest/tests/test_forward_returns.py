"""Tests unitarios para forward_returns.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.performance.forward_returns import compute_forward_returns


def _make_prices(tickers, n_weeks=60, weekly_return=0.01):
    """
    Serie sintetica diaria: precio crece a tasa semanal fija.
    Pone un valor en cada dia habil para que resample('W-FRI').last()
    recoja siempre el viernes (o el ultimo dia habil de la semana).
    """
    fridays = pd.date_range('2020-01-03', periods=n_weeks, freq='W-FRI')
    # Rango diario que cubre todos los viernes objetivo
    daily_idx = pd.bdate_range('2020-01-02', fridays[-1])
    df_daily = pd.DataFrame(index=daily_idx, columns=tickers, dtype=float)
    for day in daily_idx:
        # Semana 0 = primera semana, precio sube 'weekly_return' cada 5 dias habiles
        week_num = len(pd.bdate_range('2020-01-02', day)) // 5
        week_num = min(week_num, n_weeks - 1)
        price = 100.0 * (1 + weekly_return) ** week_num
        df_daily.loc[day] = price
    return df_daily


def test_growing_series_4w():
    """Serie +1%/semana: ret_fwd_4w debe ser aprox +4.06% (compuesto)."""
    prices = _make_prices(['SPY'], n_weeks=60, weekly_return=0.01)
    fwd = compute_forward_returns(prices, horizons_weeks=[4])
    spy = fwd.xs('SPY', level='ticker')['ret_fwd_4w'].dropna()
    expected = (1.01 ** 4) - 1.0
    assert abs(spy.mean() - expected) < 1e-6


def test_growing_series_13w():
    """Serie +1%/semana: ret_fwd_13w debe ser aprox +13.81% (compuesto)."""
    prices = _make_prices(['SPY'], n_weeks=70, weekly_return=0.01)
    fwd = compute_forward_returns(prices, horizons_weeks=[13])
    spy = fwd.xs('SPY', level='ticker')['ret_fwd_13w'].dropna()
    expected = (1.01 ** 13) - 1.0
    assert abs(spy.mean() - expected) < 1e-6


def test_last_n_weeks_are_nan():
    """Las ultimas N semanas no tienen ret_fwd_Nw disponible."""
    prices = _make_prices(['SPY'], n_weeks=30, weekly_return=0.01)
    fwd = compute_forward_returns(prices, horizons_weeks=[4, 13])
    spy = fwd.xs('SPY', level='ticker')

    # Las 4 ultimas entradas no tienen ret_fwd_4w
    assert pd.isna(spy['ret_fwd_4w'].iloc[-1])
    assert pd.isna(spy['ret_fwd_4w'].iloc[-4])
    assert not pd.isna(spy['ret_fwd_4w'].iloc[-5])

    # Las 13 ultimas no tienen ret_fwd_13w
    assert pd.isna(spy['ret_fwd_13w'].iloc[-13])
    assert not pd.isna(spy['ret_fwd_13w'].iloc[-14])


def test_flat_series_returns_zero():
    """Serie flat: todos los retornos forward son 0."""
    prices = _make_prices(['XLK'], n_weeks=40, weekly_return=0.0)
    fwd = compute_forward_returns(prices, horizons_weeks=[4, 13])
    xlk = fwd.xs('XLK', level='ticker')
    assert np.allclose(xlk['ret_fwd_4w'].dropna().values, 0.0, atol=1e-10)
    assert np.allclose(xlk['ret_fwd_13w'].dropna().values, 0.0, atol=1e-10)


def test_multiple_tickers():
    """Multiples tickers en el output."""
    prices = _make_prices(['SPY', 'XLK', 'TLT'], n_weeks=40, weekly_return=0.01)
    fwd = compute_forward_returns(prices, horizons_weeks=[4])
    tickers_in_output = fwd.index.get_level_values('ticker').unique().tolist()
    assert set(tickers_in_output) == {'SPY', 'XLK', 'TLT'}


def test_price_t_matches_input():
    """price_t en el output debe coincidir con el precio en esa semana."""
    prices = _make_prices(['SPY'], n_weeks=20, weekly_return=0.05)
    fwd = compute_forward_returns(prices, horizons_weeks=[4])
    spy = fwd.xs('SPY', level='ticker')
    # El primer precio deberia ser 100.0
    assert abs(spy['price_t'].iloc[0] - 100.0) < 1e-6
