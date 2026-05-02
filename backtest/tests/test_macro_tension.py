import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import numpy as np
from confluence.macro_tension import (
    hy_acceleration_score, netliq_contraction_score, curve_dynamics_score,
    vol_regime_shift_score, inflation_shift_score, compute_macro_tension,
    TOTAL_MAX,
)


class TestHyAcceleration:
    def test_strong(self):
        assert hy_acceleration_score(50, 90) == 10

    def test_moderate(self):
        assert hy_acceleration_score(30, 60) == 7

    def test_mild_either(self):
        assert hy_acceleration_score(20, 10) == 4   # d2w > 15
        assert hy_acceleration_score(5, 35) == 4    # d4w > 30

    def test_weak(self):
        assert hy_acceleration_score(5, 5) == 1

    def test_zero(self):
        assert hy_acceleration_score(-5, -5) == 0
        assert hy_acceleration_score(0, 5) == 0

    def test_missing_returns_none(self):
        assert hy_acceleration_score(None, 50) is None
        assert hy_acceleration_score(50, None) is None
        assert hy_acceleration_score(float('nan'), 50) is None


class TestNetliqContraction:
    def test_severe(self):
        assert netliq_contraction_score(-250_000, -500_000) == 10

    def test_strong(self):
        assert netliq_contraction_score(-120_000, -250_000) == 7

    def test_mild_either(self):
        assert netliq_contraction_score(-60_000, 0) == 4    # d4w threshold
        assert netliq_contraction_score(0, -120_000) == 4   # d8w threshold

    def test_weak(self):
        assert netliq_contraction_score(-10_000, -10_000) == 1

    def test_zero(self):
        assert netliq_contraction_score(50_000, 50_000) == 0

    def test_missing_returns_none(self):
        assert netliq_contraction_score(None, -100_000) is None
        assert netliq_contraction_score(-100_000, None) is None


class TestCurveDynamics:
    def test_inversion_deepening(self):
        assert curve_dynamics_score(-30, -5, -5) == 8

    def test_deep_stable(self):
        assert curve_dynamics_score(-60, 0, 5) == 6

    def test_shallow_deepening(self):
        assert curve_dynamics_score(-10, -5, -15) == 5

    def test_near_inversion(self):
        assert curve_dynamics_score(10, 0, 5) == 3

    def test_steep(self):
        assert curve_dynamics_score(200, 5, 5) == 0

    def test_missing_returns_none(self):
        assert curve_dynamics_score(None, 0, 0) is None
        assert curve_dynamics_score(-30, 0, None) is None


class TestVolRegimeShift:
    def test_high_rising(self):
        assert vol_regime_shift_score(30, 3, 10) == 6

    def test_moderate_spike(self):
        assert vol_regime_shift_score(22, 6, 3) == 4

    def test_accel_only(self):
        assert vol_regime_shift_score(15, 1, 7) == 3

    def test_zero(self):
        assert vol_regime_shift_score(15, 1, 2) == 0

    def test_missing_returns_none(self):
        assert vol_regime_shift_score(None, 5, 5) is None


class TestInflationShift:
    def test_runaway_inflation(self):
        assert inflation_shift_score(3.2, 0.1, 0.4) == 6

    def test_deflationary(self):
        assert inflation_shift_score(1.2, -0.1, -0.4) == 6

    def test_rapid_shift(self):
        assert inflation_shift_score(2.0, 0.25, 0.1) == 3

    def test_stable(self):
        assert inflation_shift_score(2.0, 0.05, 0.05) == 0

    def test_missing_returns_none(self):
        assert inflation_shift_score(None, 0.1, 0.1) is None


class TestComputeMacroTension:
    def _full_row(self):
        return {
            'hy_d2w': 50, 'hy_d4w': 100,        # A1 → 10
            'netliq_d4w': -250_000,               # A2 → 10
            'netliq_d8w': -500_000,
            't10y3m_bps': -30, 'curva_d2w': -5, 'curva_d4w': -5,  # A3 → 8
            'vix': 30, 'vix_d2w': 6, 'vix_d4w': 10,               # A4 → 6
            't5yie_pct': 3.2, 't5yie_d2w': 0.1, 't5yie_d4w': 0.4, # A5 → 6
        }

    def test_max_score_is_40(self):
        result = compute_macro_tension(self._full_row())
        assert abs(result['macro_tension_scaled'] - 40.0) < 0.01

    def test_zero_score(self):
        row = {
            'hy_d2w': -5, 'hy_d4w': -5,
            'netliq_d4w': 50_000, 'netliq_d8w': 50_000,
            't10y3m_bps': 200, 'curva_d2w': 5, 'curva_d4w': 5,
            'vix': 10, 'vix_d2w': -1, 'vix_d4w': -1,
            't5yie_pct': 2.0, 't5yie_d2w': 0.05, 't5yie_d4w': 0.05,
        }
        result = compute_macro_tension(row)
        assert result['macro_tension_scaled'] == 0.0

    def test_dynamic_rescaling_without_hy(self):
        row = self._full_row()
        row['hy_d2w'] = None
        row['hy_d4w'] = None
        result = compute_macro_tension(row)
        # Should still be 40 (rescaled to remaining max)
        assert abs(result['macro_tension_scaled'] - 40.0) < 0.01
        assert result['components']['hy_accel'] is None

    def test_all_missing_returns_none(self):
        result = compute_macro_tension({})
        assert result['macro_tension_scaled'] is None

    def test_scaled_never_exceeds_40(self):
        result = compute_macro_tension(self._full_row())
        assert result['macro_tension_scaled'] <= 40.0 + 1e-9
