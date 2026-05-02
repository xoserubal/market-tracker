import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import numpy as np
import pandas as pd
from portfolio.metrics import compute_metrics, compute_spy_metrics


def _flat_equity(n_days=252, value=100_000.0):
    idx = pd.date_range('2010-01-01', periods=n_days, freq='B')
    return pd.Series(value, index=idx)


def _spy_same(equity):
    return equity.copy()


def test_flat_equity_cagr_zero():
    eq = _flat_equity()
    spy = _spy_same(eq)
    m = compute_metrics(eq, spy, pd.DataFrame(), 'rot_temprana_pure', True, 'A', '2010-2019')
    assert abs(m['cagr']) < 1e-6
    assert abs(m['total_return']) < 1e-6


def test_flat_equity_vol_zero():
    eq = _flat_equity()
    spy = _spy_same(eq)
    m = compute_metrics(eq, spy, pd.DataFrame(), 'rot_temprana_pure', True, 'A', '2010-2019')
    assert abs(m['vol_annualized']) < 1e-6


def test_known_max_drawdown():
    idx = pd.date_range('2010-01-01', periods=10, freq='B')
    vals = [100, 110, 120, 100, 90, 95, 100, 110, 115, 120]
    eq = pd.Series([float(v) for v in vals], index=idx)
    spy = _flat_equity(10, 100.0)
    m = compute_metrics(eq, spy, pd.DataFrame(), 'rot_temprana_pure', True, 'A', '2010-2019')
    # Max DD: from 120 down to 90 = -25%
    assert abs(m['max_drawdown'] - (-0.25)) < 0.001


def test_beta_one_against_identical_spy():
    idx = pd.date_range('2010-01-01', periods=252, freq='B')
    vals = pd.Series(100_000 * (1.0001 ** np.arange(252)), index=idx)
    m = compute_metrics(vals, vals.copy(), pd.DataFrame(),
                        'rot_temprana_pure', True, 'A', '2010-2019')
    assert abs(m['beta_vs_spy'] - 1.0) < 0.01


def test_alpha_zero_when_strategy_equals_spy():
    idx = pd.date_range('2010-01-01', periods=252, freq='B')
    vals = pd.Series(100_000 * (1.0001 ** np.arange(252)), index=idx)
    m = compute_metrics(vals, vals.copy(), pd.DataFrame(),
                        'rot_temprana_pure', True, 'A', '2010-2019')
    assert abs(m['alpha_annualized']) < 0.002


def test_spy_metrics():
    eq = _flat_equity()
    sm = compute_spy_metrics(eq, '2010-2019')
    assert sm['strategy'] == 'spy_benchmark'
    assert abs(sm['total_return']) < 1e-6
    assert sm['beta_vs_spy'] == 1.0
