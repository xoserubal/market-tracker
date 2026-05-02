"""Tests unitarios para determinación de señales."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.rotation.signals import determine_signal


def sig(score, fit, er=False, credit=False, emergency=False,
        spy_above=True, er_netliq=False):
    return determine_signal(
        rot_score=score, fit=fit, is_early_rotation=er,
        flag_credit_complacency=credit, flag_emergency=emergency,
        spy_above_sma200=spy_above, er_validated_by_netliq=er_netliq,
    )


# ── Señales estándar ──────────────────────────────────────────────────────────
def test_compra():
    assert sig(7, fit=True) == ('COMPRA', None)


def test_compra_score_8():
    assert sig(8, fit=True) == ('COMPRA', None)


def test_acumular():
    assert sig(5, fit=True) == ('ACUMULAR', None)
    assert sig(6, fit=True) == ('ACUMULAR', None)


def test_vigilar_no_fit():
    assert sig(3, fit=False) == ('VIGILAR', None)
    assert sig(4, fit=False) == ('VIGILAR', None)


def test_vigilar_con_fit_score_bajo():
    # fit pero score <5 → no califica COMPRA/ACUMULAR → VIGILAR
    assert sig(4, fit=True) == ('VIGILAR', None)


def test_ignorar():
    assert sig(2, fit=False) == (None, None)
    assert sig(0, fit=False) == (None, None)


def test_early_rotation():
    assert sig(8, fit=False, er=True) == ('ROT. TEMPRANA', None)


# ── CREDIT_COMPLACENCY ───────────────────────────────────────────────────────
def test_credit_complacency_raises_threshold():
    """Con flag activo, umbral COMPRA sube a 8."""
    assert sig(7, fit=True, credit=True) == ('ACUMULAR', None)
    assert sig(8, fit=True, credit=True) == ('COMPRA',   None)


# ── Master Filter: SPY < SMA200 ───────────────────────────────────────────────
def test_master_filter_degrades_compra():
    assert sig(7, fit=True, spy_above=False) == ('ACUMULAR', None)


def test_master_filter_degrades_acumular():
    assert sig(5, fit=True, spy_above=False) == ('VIGILAR', None)


def test_master_filter_kills_vigilar():
    assert sig(3, fit=False, spy_above=False) == (None, None)


def test_master_filter_does_not_degrade_early_rotation_via_spy():
    """ROT. TEMPRANA NO se degrada por master filter (tiene su propio benchmark)."""
    result = sig(8, fit=False, er=True, spy_above=False, er_netliq=False)
    assert result[0] == 'ROT. TEMPRANA'


def test_early_rotation_via_netliq_not_degraded():
    """ROT. TEMPRANA validada por NetLiq no se degrada aunque SPY<SMA200."""
    result = sig(8, fit=False, er=True, spy_above=False, er_netliq=True)
    assert result[0] == 'ROT. TEMPRANA'


# ── EMERGENCY_MODE ────────────────────────────────────────────────────────────
def test_emergency_suppresses_compra():
    """EMERGENCY_MODE suprime COMPRA incluso con fit y score alto."""
    result = sig(10, fit=True, emergency=True)
    # fit=True pero no Risk-OFF fit — la función no distingue régimen aquí
    # Si fit=True y score≥6, emite ACUMULAR*
    assert result == ('ACUMULAR*', 'emergencia')


def test_emergency_suppresses_when_score_low():
    result = sig(4, fit=False, emergency=True)
    assert result == (None, None)


def test_emergency_acumular_estrella():
    """EMERGENCY + fit Risk-OFF + score≥6 → ACUMULAR*."""
    result = sig(6, fit=True, emergency=True)
    assert result == ('ACUMULAR*', 'emergencia')


def test_emergency_suppresses_early_rotation():
    """EMERGENCY_MODE suprime ROT. TEMPRANA."""
    result = sig(9, fit=False, er=True, emergency=True)
    # er=True pero emergency anula todo → solo ACUMULAR* si fit=True
    assert result == (None, None)
