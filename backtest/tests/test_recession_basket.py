"""Tests unitarios para recession_basket.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.performance.recession_basket import (
    compute_basket_returns,
    compute_basket_forward_returns,
    find_regime_transitions,
)


def _make_daily_prices(tickers, n_days=200, daily_return=0.0):
    """DataFrame diario con precios constantes o crecientes."""
    dates = pd.bdate_range('2020-01-02', periods=n_days)
    data  = {}
    for t in tickers:
        data[t] = [100.0 * (1 + daily_return) ** i for i in range(n_days)]
    return pd.DataFrame(data, index=dates)


def test_basket_all_up_10pct_spy_5pct():
    """Basket +10% y SPY +5% a 4w -> alpha ~ +5%."""
    n_days = 200
    dates  = pd.bdate_range('2020-01-02', periods=n_days)
    basket_tickers = ['DG','DLTR','WMT','MCD','KO','PG','JNJ','UNH','NEE','NEM']
    prices = pd.DataFrame(index=dates)
    for t in basket_tickers:
        prices[t] = [100.0 * (1.10 ** (i / 20)) for i in range(n_days)]  # +10%/4w
    prices['SPY'] = [100.0 * (1.05 ** (i / 20)) for i in range(n_days)]  # +5%/4w

    fwd = compute_basket_forward_returns(prices, basket=basket_tickers, horizons_weeks=[4])
    basket_ret = fwd['basket_ret_fwd_4w'].dropna()
    expected = (1.10 ** 1) - 1.0  # exactamente una semana de 4w
    # Solo verificamos que es positivo y cerca de +10%
    assert (basket_ret > 0).all()
    assert basket_ret.mean() == pytest.approx(expected, rel=0.05)


def test_basket_7_of_10_available():
    """Con solo 7 de 10 tickers con dato, la media usa solo los 7 disponibles."""
    basket_tickers = ['DG','DLTR','WMT','MCD','KO','PG','JNJ','UNH','NEE','NEM']
    prices_7 = _make_daily_prices(basket_tickers[:7], n_days=100, daily_return=0.01)
    basket_ret = compute_basket_returns(prices_7, basket=basket_tickers, min_members=7)
    # Con 7 miembros minimos = exactamente 7 disponibles: debe calcularse
    assert basket_ret.dropna().shape[0] > 0


def test_basket_less_than_min_is_nan():
    """Con menos de min_members disponibles: NaN."""
    basket_tickers = ['DG','DLTR','WMT','MCD','KO','PG','JNJ','UNH','NEE','NEM']
    prices_3 = _make_daily_prices(['DG','DLTR','WMT'], n_days=50, daily_return=0.01)
    basket_ret = compute_basket_returns(prices_3, basket=basket_tickers, min_members=7)
    # Con solo 3 disponibles < 7 minimo: todo NaN
    assert basket_ret.dropna().shape[0] == 0


def test_find_regime_transitions_detects_riskoff():
    """Transicion a Risk-OFF debe ser detectada correctamente."""
    dates = pd.date_range('2020-01-03', periods=6, freq='W-FRI')
    data = {
        'mode':   ['A'] * 6,
        'regime': ['Bull Maduro', 'Bull Maduro', 'Transicion', 'Risk-OFF', 'Risk-OFF', 'Capitulacion'],
        'flag_inflation_overlay': [False] * 6,
    }
    mh = pd.DataFrame(data, index=dates)
    transitions = find_regime_transitions(mh, mode='A')

    # Debe detectar: Transicion->Risk-OFF y Risk-OFF->Capitulacion
    assert len(transitions) == 2
    risk_off = transitions[transitions['new_regime'] == 'Risk-OFF']
    assert len(risk_off) == 1
    assert risk_off.iloc[0]['prev_regime'] == 'Transicion'


def test_find_regime_transitions_ignores_recovery():
    """Transicion de Risk-OFF a Bull Maduro NO es Early Bear."""
    dates = pd.date_range('2020-01-03', periods=4, freq='W-FRI')
    data = {
        'mode':   ['A'] * 4,
        'regime': ['Risk-OFF', 'Risk-OFF', 'Transicion', 'Bull Maduro'],
        'flag_inflation_overlay': [False] * 4,
    }
    mh = pd.DataFrame(data, index=dates)
    transitions = find_regime_transitions(mh, mode='A', to_regimes=['Risk-OFF', 'Capitulacion'])
    assert len(transitions) == 0
