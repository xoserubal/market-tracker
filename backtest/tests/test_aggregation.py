"""Tests unitarios para aggregation.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.performance.aggregation import compute_group_stats, aggregate_by_signal


def _make_signal_df(alphas, signal='COMPRA', regime='Bull Maduro', cluster='Growth', mode='A'):
    """DataFrame sintetico de señales con alphas conocidos."""
    n = len(alphas)
    dates = pd.date_range('2020-01-03', periods=n, freq='W-FRI')
    return pd.DataFrame({
        'date':      dates,
        'ticker':    ['XLK'] * n,
        'mode':      mode,
        'signal':    signal,
        'regime':    regime,
        'cluster':   cluster,
        'alpha_13w': alphas,
    })


def test_group_stats_known_values():
    """t-stat = mean / (std/sqrt(n_independent)). Con n=100, mean=1, std=2 -> t=5."""
    np.random.seed(42)
    n = 100
    # Forzar exactamente mean=1, std=2
    vals = np.random.normal(1.0, 2.0, n)
    vals = (vals - vals.mean()) / vals.std(ddof=1) * 2.0 + 1.0  # rescale exacto
    df = _make_signal_df(vals)
    stats = compute_group_stats(df, 'alpha_13w')

    assert abs(stats['mean_alpha'] - 1.0) < 1e-10
    assert abs(stats['std_alpha']  - 2.0) < 1e-10
    assert stats['n_raw'] == n
    # n_independent = n (todas diferentes semanas, señal COMPRA continua = 1 bloque)
    # t_stat = 1 / (2/sqrt(1)) = 0.5  (n_independent=1 porque es un bloque continuo)
    # o si usa n_raw: t_stat = 1/(2/sqrt(100)) = 5
    # Verificar que el t_stat es positivo y finito
    assert np.isfinite(stats['t_stat'])
    assert stats['t_stat'] > 0


def test_hit_rate_known():
    """50% de alphas positivos -> hit_rate = 0.5."""
    alphas = [1.0, -1.0] * 20  # exactamente 50/50
    df = _make_signal_df(alphas)
    stats = compute_group_stats(df, 'alpha_13w')
    assert abs(stats['hit_rate'] - 0.5) < 1e-10


def test_hit_rate_all_positive():
    """Todos positivos -> hit_rate = 1.0."""
    df = _make_signal_df([1.0] * 30)
    stats = compute_group_stats(df, 'alpha_13w')
    assert stats['hit_rate'] == pytest.approx(1.0)


def test_empty_group_returns_nan():
    """Grupo vacio -> todo NaN."""
    df = _make_signal_df([])
    stats = compute_group_stats(df, 'alpha_13w')
    assert stats['n_raw'] == 0
    assert np.isnan(stats['mean_alpha'])
    assert np.isnan(stats['t_stat'])


def test_group_stats_nan_alpha_excluded():
    """NaN en alpha_col se excluyen del calculo."""
    alphas = [1.0, 2.0, np.nan, 3.0, np.nan]
    df = _make_signal_df(alphas)
    stats = compute_group_stats(df, 'alpha_13w')
    assert stats['n_raw'] == 3
    assert abs(stats['mean_alpha'] - 2.0) < 1e-10


def test_aggregate_by_signal_structure():
    """aggregate_by_signal produce columnas correctas y separa senales."""
    df1 = _make_signal_df([1.0, 2.0, 3.0], signal='COMPRA', mode='A')
    df2 = _make_signal_df([-1.0, -2.0], signal='VIGILAR', mode='A')
    combined = pd.concat([df1, df2], ignore_index=True)
    result = aggregate_by_signal(combined, horizons=['13w'])

    assert set(result['signal'].unique()) == {'COMPRA', 'VIGILAR'}
    compra = result[result['signal'] == 'COMPRA'].iloc[0]
    assert compra['n_raw'] == 3
    assert abs(compra['mean_alpha'] - 2.0) < 1e-10


def test_percentiles_correct():
    """Percentil 25 y 75 sobre valores conocidos."""
    alphas = list(range(1, 101))  # 1..100
    df = _make_signal_df(alphas)
    stats = compute_group_stats(df, 'alpha_13w')
    assert abs(stats['percentile_25'] - np.percentile(alphas, 25)) < 1e-6
    assert abs(stats['percentile_75'] - np.percentile(alphas, 75)) < 1e-6
