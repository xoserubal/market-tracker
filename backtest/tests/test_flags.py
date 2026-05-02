"""Tests de los 4 flags globales."""
import pandas as pd
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.macro.flags import (
    make_flag_state, make_emergency_state,
    check_credit_complacency,
    check_inflation_overlay,
    check_term_premium_extreme,
    check_emergency_mode,
)

FRI = lambda s: pd.Timestamp(s)


# ── CREDIT_COMPLACENCY ────────────────────────────────────────────────────────

class TestCreditComplacency:
    def test_activates_after_8_weeks(self):
        state = make_flag_state()
        for i in range(7):
            state = check_credit_complacency(270, 'A', state)
            assert not state['active']
        state = check_credit_complacency(270, 'A', state)
        assert state['active']
        assert state['streak_weeks'] == 8

    def test_deactivates_immediately_on_miss(self):
        state = make_flag_state()
        for _ in range(8):
            state = check_credit_complacency(270, 'A', state)
        assert state['active']
        state = check_credit_complacency(275, 'A', state)
        assert not state['active']
        assert state['streak_weeks'] == 0

    def test_disabled_in_mode_b(self):
        state = make_flag_state()
        for _ in range(10):
            state = check_credit_complacency(200, 'B', state)
        assert not state['active']
        assert state['streak_weeks'] == 0

    def test_none_hy_resets(self):
        state = make_flag_state()
        for _ in range(8):
            state = check_credit_complacency(270, 'A', state)
        assert state['active']
        state = check_credit_complacency(None, 'A', state)
        assert not state['active']
        assert state['streak_weeks'] == 0

    def test_exactly_275_not_active(self):
        """HY = 275: condición es < 275, no se cumple."""
        state = make_flag_state()
        state = check_credit_complacency(275, 'A', state)
        assert state['streak_weeks'] == 0


# ── INFLATION_OVERLAY ─────────────────────────────────────────────────────────

class TestInflationOverlay:
    def test_activates_after_4_weeks(self):
        state = make_flag_state()
        for i in range(3):
            state = check_inflation_overlay(3.0, state)
            assert not state['active']
        state = check_inflation_overlay(3.0, state)
        assert state['active']

    def test_deactivates_immediately_on_miss(self):
        state = make_flag_state()
        for _ in range(4):
            state = check_inflation_overlay(3.0, state)
        assert state['active']
        state = check_inflation_overlay(2.5, state)
        assert not state['active']
        assert state['streak_weeks'] == 0

    def test_exactly_2_8_activates(self):
        """T5YIE = 2.8%: condición ≥ 2.8% → sí se cuenta."""
        state = make_flag_state()
        for _ in range(4):
            state = check_inflation_overlay(2.8, state)
        assert state['active']

    def test_none_resets(self):
        state = make_flag_state()
        for _ in range(4):
            state = check_inflation_overlay(3.0, state)
        assert state['active']
        state = check_inflation_overlay(None, state)
        assert not state['active']


# ── TERM_PREMIUM_EXTREME ──────────────────────────────────────────────────────

class TestTermPremiumExtreme:
    def test_activates_after_13_weeks(self):
        state = make_flag_state()
        for i in range(12):
            state = check_term_premium_extreme(-1.0, state)
            assert not state['active']
        state = check_term_premium_extreme(-1.0, state)
        assert state['active']

    def test_deactivates_immediately_on_miss(self):
        state = make_flag_state()
        for _ in range(13):
            state = check_term_premium_extreme(-1.0, state)
        assert state['active']
        state = check_term_premium_extreme(-0.74, state)
        assert not state['active']
        assert state['streak_weeks'] == 0

    def test_exactly_minus_075_not_active(self):
        """threefytp10 = -0.75: condición es < -0.75, no se cumple."""
        state = make_flag_state()
        state = check_term_premium_extreme(-0.75, state)
        assert state['streak_weeks'] == 0


# ── EMERGENCY_MODE ────────────────────────────────────────────────────────────

class TestEmergencyMode:
    def test_activates_immediately_at_35(self):
        state = make_emergency_state()
        dt = FRI('2020-03-16')
        state = check_emergency_mode(35.0, dt, state)
        assert state['active']
        assert state['activated_at'] == dt

    def test_does_not_activate_below_35(self):
        state = make_emergency_state()
        state = check_emergency_mode(34.9, FRI('2020-03-16'), state)
        assert not state['active']

    def test_stays_active_during_14_days(self):
        """Aunque VIX baje < 35, se mantiene activo los primeros 14 días."""
        state = make_emergency_state()
        activated = FRI('2020-03-16')
        state = check_emergency_mode(40.0, activated, state)
        assert state['active']

        # VIX baja pero solo han pasado 7 días
        state = check_emergency_mode(20.0, activated + pd.Timedelta(days=7), state)
        assert state['active']

        # VIX sigue bajo, pasan 13 días → aún activo
        state = check_emergency_mode(20.0, activated + pd.Timedelta(days=13), state)
        assert state['active']

    def test_deactivates_after_14_days_if_vix_low(self):
        """Tras 14 días con VIX < 35, se desactiva."""
        state = make_emergency_state()
        activated = FRI('2020-03-16')
        state = check_emergency_mode(40.0, activated, state)
        state = check_emergency_mode(20.0, activated + pd.Timedelta(days=14), state)
        assert not state['active']
        assert state['activated_at'] is None

    def test_stays_active_after_14_days_if_vix_still_high(self):
        """Tras 14 días, si VIX ≥ 35 se mantiene activo."""
        state = make_emergency_state()
        activated = FRI('2020-03-16')
        state = check_emergency_mode(40.0, activated, state)
        state = check_emergency_mode(36.0, activated + pd.Timedelta(days=14), state)
        assert state['active']

    def test_none_vix_deactivates_after_min_duration(self):
        """Si VIX es None tras 14 días, se desactiva (condición no cumplida)."""
        state = make_emergency_state()
        activated = FRI('2020-03-16')
        state = check_emergency_mode(40.0, activated, state)
        state = check_emergency_mode(None, activated + pd.Timedelta(days=14), state)
        assert not state['active']
