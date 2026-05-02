"""Tests unitarios para determinación de fit."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.rotation.fit import get_effective_leaders, determine_fit


def _leaders(regime='Bull Maduro', hy_bps=350.0, t10y3m_pct=0.5,
             curve_d13w=0.0, dfii10=0.8, dxy_ret=-1.0,
             flag_inflation=False, netliq_b=0.0, flag_tp=False):
    return get_effective_leaders(
        regime=regime, hy_bps=hy_bps, t10y3m_pct=t10y3m_pct,
        curve_d13w_pct=curve_d13w, dfii10=dfii10, dxy_ret_13w=dxy_ret,
        flag_inflation=flag_inflation, netliq_d13w_b=netliq_b,
        flag_term_premium=flag_tp,
    )


# ── Fit estándar (sin conditionals) ──────────────────────────────────────────
def test_bull_maduro_default_leaders():
    leaders = _leaders(regime='Bull Maduro')
    # GC=F incluido porque dfii10<1.0 (0.8) → goldOk
    assert 'XLF' in leaders
    assert 'XLE' in leaders
    assert 'GC=F' in leaders


def test_bull_pleno_includes_iwm_when_conditions_met():
    leaders = _leaders(regime='Bull Pleno', hy_bps=300.0, t10y3m_pct=0.3)
    assert 'IWM' in leaders


def test_capitulacion_only_tlT_gold():
    leaders = _leaders(regime='Capitulación', dfii10=0.5, dxy_ret=-2.0)
    assert set(leaders).issubset({'TLT', 'GC=F'})


# ── Conditional IWM ───────────────────────────────────────────────────────────
def test_iwm_excluded_when_hy_too_high():
    """HY ≥ 375 → IWM excluido aunque esté en Bull Pleno."""
    leaders = _leaders(regime='Bull Pleno', hy_bps=400.0, t10y3m_pct=0.5)
    assert 'IWM' not in leaders


def test_iwm_excluded_when_curve_inverted_no_steepening():
    """Curva invertida y sin steepening → IWM excluido."""
    leaders = _leaders(regime='Bull Pleno', hy_bps=300.0,
                       t10y3m_pct=-0.3, curve_d13w=-0.1)
    assert 'IWM' not in leaders


def test_iwm_ok_with_steepening_despite_inverted_curve():
    """Curva invertida PERO steepening (delta>0) → IWM ok."""
    leaders = _leaders(regime='Bull Pleno', hy_bps=300.0,
                       t10y3m_pct=-0.3, curve_d13w=0.2)
    assert 'IWM' in leaders


def test_iwm_not_in_bull_maduro():
    """IWM no está en defaultLeaders de Bull Maduro → nunca fit."""
    leaders = _leaders(regime='Bull Maduro', hy_bps=200.0, t10y3m_pct=1.0)
    assert 'IWM' not in leaders


# ── Conditional oro ───────────────────────────────────────────────────────────
def test_gold_excluded_when_dfii10_high_and_dxy_bullish():
    """DFII10≥1.0 Y DXY alcista → GC=F excluido."""
    leaders = _leaders(regime='Bull Maduro', dfii10=1.5, dxy_ret=+2.0)
    assert 'GC=F' not in leaders


def test_gold_ok_when_dfii10_low():
    """DFII10<1.0 → GC=F ok independientemente de DXY."""
    leaders = _leaders(regime='Bull Maduro', dfii10=0.5, dxy_ret=+5.0)
    assert 'GC=F' in leaders


def test_gold_ok_when_dxy_bearish():
    """DXY bajista → GC=F ok aunque DFII10≥1.0."""
    leaders = _leaders(regime='Bull Maduro', dfii10=1.5, dxy_ret=-1.0)
    assert 'GC=F' in leaders


# ── INFLATION_OVERLAY ─────────────────────────────────────────────────────────
def test_inflation_overlay_removes_tlT_qqq_xlk():
    leaders = _leaders(regime='Bull Pleno', flag_inflation=True, netliq_b=0.0)
    assert 'TLT' not in leaders
    assert 'QQQ' not in leaders
    assert 'XLK' not in leaders


def test_inflation_overlay_promotes_energy_materials():
    leaders = _leaders(regime='Bull Pleno', flag_inflation=True, netliq_b=0.0)
    for t in ('XLE', 'XLB', 'GC=F', 'SI=F'):
        assert t in leaders


def test_inflation_overlay_netliq_exception():
    """NetLiq Δ13w > 300B → TLT/QQQ/XLK no se bloquean."""
    leaders = _leaders(regime='Bull Pleno', flag_inflation=True, netliq_b=350.0,
                       dfii10=0.5, dxy_ret=-1.0)
    assert 'QQQ' in leaders
    assert 'XLK' in leaders


# ── TERM_PREMIUM_EXTREME ──────────────────────────────────────────────────────
def test_term_premium_degrades_regime():
    """Bull Pleno + TERM_PREMIUM → régimen efectivo Bull Maduro."""
    leaders_normal   = _leaders(regime='Bull Pleno',  flag_tp=False)
    leaders_degraded = _leaders(regime='Bull Pleno',  flag_tp=True)
    # Bull Maduro no tiene XLK, XLC, XLY, QQQ, BTC-USD, IWM, EEM como líderes
    assert 'XLK' not in leaders_degraded
    assert 'XLF' in leaders_degraded    # Bull Maduro leader


# ── Snapshot validation (2026-04-17) ─────────────────────────────────────────
def test_snapshot_bull_maduro_leaders():
    """
    Replica el estado de la app el 2026-04-17:
    DFII10=1.93%, DXY no bajista, no flags.
    Líderes esperados: XLF, XLI, XLB, XLE, SI=F, BZ=F (GC=F excluido).
    """
    leaders = _leaders(
        regime='Bull Maduro', hy_bps=286.0, t10y3m_pct=0.56,
        dfii10=1.93, dxy_ret=+1.0,   # DXY no bajista
        flag_inflation=False, netliq_b=-1.0, flag_tp=False,
    )
    expected = {'XLF', 'XLI', 'XLB', 'XLE', 'SI=F', 'BZ=F'}
    assert set(leaders) == expected
