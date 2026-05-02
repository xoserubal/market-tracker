"""Tests unitarios para lead_time.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest

from src.performance.lead_time import compute_lead_time_single


def _make_rotation(rows):
    """
    rows: list of (date_str, ticker, mode, signal)
    Returns rotation_history DataFrame indexed by date.
    """
    data = [{'date': pd.Timestamp(r[0]), 'ticker': r[1], 'mode': r[2],
             'signal': r[3], 'cluster': 'Growth'} for r in rows]
    df = pd.DataFrame(data).set_index('date')
    return df


def test_lead_time_3_weeks():
    """ROT. TEMPRANA en t=0, COMPRA en t+3w -> lead_time=3."""
    rh = _make_rotation([
        ('2020-01-03', 'XLK', 'A', 'ROT. TEMPRANA'),
        ('2020-01-10', 'XLK', 'A', 'VIGILAR'),
        ('2020-01-17', 'XLK', 'A', 'VIGILAR'),
        ('2020-01-24', 'XLK', 'A', 'COMPRA'),   # 3 semanas despues
    ])
    result = compute_lead_time_single(
        early_rotation_date=pd.Timestamp('2020-01-03'),
        ticker='XLK', mode='A',
        rotation_history=rh,
    )
    assert result['lead_time_weeks'] == 3
    assert result['convergence_signal'] == 'COMPRA'
    assert result['first_convergence_date'] == pd.Timestamp('2020-01-24')


def test_no_convergence_within_52w():
    """Sin COMPRA/ACUMULAR en 52 semanas -> lead_time=None."""
    dates = pd.date_range('2020-01-10', periods=60, freq='W-FRI')
    rows = [(str(d.date()), 'XLK', 'A', 'VIGILAR') for d in dates]
    rh = _make_rotation(rows)
    result = compute_lead_time_single(
        early_rotation_date=pd.Timestamp('2020-01-03'),
        ticker='XLK', mode='A',
        rotation_history=rh,
    )
    assert result['lead_time_weeks'] is None
    assert result['first_convergence_date'] is None
    assert result['convergence_signal'] is None


def test_convergence_acumular_before_compra():
    """ACUMULAR aparece antes que COMPRA -> convergence_signal = ACUMULAR."""
    rh = _make_rotation([
        ('2020-01-10', 'XLK', 'A', 'VIGILAR'),
        ('2020-01-17', 'XLK', 'A', 'ACUMULAR'),  # converge aqui
        ('2020-01-24', 'XLK', 'A', 'COMPRA'),
    ])
    result = compute_lead_time_single(
        early_rotation_date=pd.Timestamp('2020-01-03'),
        ticker='XLK', mode='A',
        rotation_history=rh,
    )
    assert result['convergence_signal'] == 'ACUMULAR'
    assert result['lead_time_weeks'] == 2


def test_different_ticker_ignored():
    """La busqueda es solo para el mismo ticker."""
    rh = _make_rotation([
        ('2020-01-10', 'XLF', 'A', 'COMPRA'),   # diferente ticker
        ('2020-01-17', 'XLK', 'A', 'VIGILAR'),
    ])
    result = compute_lead_time_single(
        early_rotation_date=pd.Timestamp('2020-01-03'),
        ticker='XLK', mode='A',
        rotation_history=rh,
    )
    assert result['convergence_signal'] is None


def test_different_mode_ignored():
    """La busqueda es solo para el mismo mode."""
    rh = _make_rotation([
        ('2020-01-10', 'XLK', 'B', 'COMPRA'),   # diferente mode
        ('2020-01-17', 'XLK', 'A', 'VIGILAR'),
    ])
    result = compute_lead_time_single(
        early_rotation_date=pd.Timestamp('2020-01-03'),
        ticker='XLK', mode='A',
        rotation_history=rh,
    )
    assert result['convergence_signal'] is None


def test_convergence_exactly_at_52w():
    """COMPRA exactamente a las 52 semanas -> se incluye (limite inclusivo)."""
    target = pd.Timestamp('2020-01-03') + pd.DateOffset(weeks=52)
    rh = _make_rotation([
        (str(target.date()), 'XLK', 'A', 'COMPRA'),
    ])
    result = compute_lead_time_single(
        early_rotation_date=pd.Timestamp('2020-01-03'),
        ticker='XLK', mode='A',
        rotation_history=rh,
    )
    assert result['convergence_signal'] == 'COMPRA'


def test_convergence_beyond_52w_excluded():
    """COMPRA a las 53 semanas -> NO se incluye."""
    target = pd.Timestamp('2020-01-03') + pd.DateOffset(weeks=53)
    rh = _make_rotation([
        (str(target.date()), 'XLK', 'A', 'COMPRA'),
    ])
    result = compute_lead_time_single(
        early_rotation_date=pd.Timestamp('2020-01-03'),
        ticker='XLK', mode='A',
        rotation_history=rh,
    )
    assert result['convergence_signal'] is None
