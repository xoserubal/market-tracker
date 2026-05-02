"""Tests unitarios para early rotation (streaks y condiciones)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.rotation.early_rotation import update_streak, evaluate_early_rotation


def _state(**kwargs):
    """Crea estado con streaks dados."""
    state = {t: {'streak': 0, 'last_score': None}
             for t in ['XLK','XLC','XLY','QQQ','BTC-USD',
                       'XLF','XLI','XLB','XLE',
                       'XLP','XLU','XLV','XLRE',
                       'TLT','GC=F','SI=F','BZ=F','IWM','EEM']}
    for ticker, streak in kwargs.items():
        state[ticker] = {'streak': streak, 'last_score': 8.0 if streak > 0 else 0.0}
    return state


def _eval(ticker, fit=False, state=None, spy_above=True, netliq=0.0):
    if state is None:
        state = _state()
    return evaluate_early_rotation(
        ticker=ticker, fit=fit, state=state,
        spy_above_sma200=spy_above, netliq_d13w_b=netliq,
    )


# ── Streak updates ────────────────────────────────────────────────────────────
def test_streak_increments():
    state = {'XLK': {'streak': 2, 'last_score': 8.0}}
    update_streak('XLK', 8.5, state)
    assert state['XLK']['streak'] == 3


def test_streak_resets_on_low_score():
    state = {'XLK': {'streak': 3, 'last_score': 8.0}}
    update_streak('XLK', 7.0, state)
    assert state['XLK']['streak'] == 0


def test_streak_resets_on_none_score():
    state = {'XLK': {'streak': 5, 'last_score': 9.0}}
    update_streak('XLK', None, state)
    assert state['XLK']['streak'] == 0


def test_streak_exact_threshold():
    state = {'XLK': {'streak': 0, 'last_score': None}}
    update_streak('XLK', 8.0, state)
    assert state['XLK']['streak'] == 1
    update_streak('XLK', 7.9, state)
    assert state['XLK']['streak'] == 0


# ── Condición 1: persistencia ─────────────────────────────────────────────────
def test_streak_2_not_enough():
    """Streak=2 → no emite (necesita 3)."""
    state = _state(XLK=2, QQQ=2)
    result = _eval('XLK', state=state, spy_above=True)
    assert result['is_early_rotation'] is False


def test_streak_3_checks_cluster():
    """Streak=3 pero solo 1 miembro del clúster → no emite."""
    state = _state(XLK=3)  # QQQ/XLC/XLY/BTC-USD tienen streak 0
    result = _eval('XLK', state=state, spy_above=True)
    assert result['is_early_rotation'] is False


# ── Condición 2: clúster ──────────────────────────────────────────────────────
def test_cluster_2_members_qualifies():
    """Streak=3 + 2 miembros del clúster Growth → emite."""
    state = _state(XLK=3, QQQ=3)
    result = _eval('XLK', state=state, spy_above=True)
    assert result['is_early_rotation'] is True
    assert result['cluster'] == 'Growth'
    assert 'QQQ' in result['cluster_qualifying_peers']


def test_cluster_duration_never_emits():
    """TLT (clúster Duration, 1 solo miembro) → nunca emite."""
    state = _state(TLT=10)
    result = _eval('TLT', state=state, spy_above=True, netliq=500.0)
    assert result['is_early_rotation'] is False


# ── Condición 3: benchmark ────────────────────────────────────────────────────
def test_no_benchmark_no_emit():
    """Streak OK + clúster OK + SPY<SMA200 + NetLiq<300B → no emite."""
    state = _state(IWM=3, EEM=3)
    result = _eval('IWM', state=state, spy_above=False, netliq=100.0)
    assert result['is_early_rotation'] is False


def test_netliq_benchmark_overrides_spy():
    """SPY<SMA200 pero NetLiq>300B → sí emite (validada por NetLiq)."""
    state = _state(IWM=3, EEM=3)
    result = _eval('IWM', state=state, spy_above=False, netliq=350.0)
    assert result['is_early_rotation'] is True
    assert result['benchmark_condition'] == 'netliq_expanding'
    assert result['er_validated_by_netliq'] is True


def test_spy_benchmark():
    """SPY>SMA200 → benchmark vía SPY."""
    state = _state(IWM=3, EEM=3)
    result = _eval('IWM', state=state, spy_above=True, netliq=0.0)
    assert result['is_early_rotation'] is True
    assert result['benchmark_condition'] == 'spy_above_sma200'
    assert result['er_validated_by_netliq'] is False


# ── Fit excluye ROT. TEMPRANA ─────────────────────────────────────────────────
def test_fit_prevents_early_rotation():
    """Activo con fit con régimen actual NO emite ROT. TEMPRANA."""
    state = _state(XLK=5, QQQ=5)
    result = _eval('XLK', fit=True, state=state, spy_above=True)
    assert result['is_early_rotation'] is False
