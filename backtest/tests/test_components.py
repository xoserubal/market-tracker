"""Tests de los 5 subcomponentes del MacroScore."""
import math
import pandas as pd
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.macro.components import (
    hy_score, netliq_delta13w_score,
    vix_level_score, vix_term_score, vol_score,
    curva_score, cfnai_score,
)


# ── HY Spread ─────────────────────────────────────────────────────────────────

class TestHyScore:
    def test_all_brackets(self):
        assert hy_score(200)  == 25.0
        assert hy_score(299)  == 25.0
        assert hy_score(300)  == 18.75
        assert hy_score(374)  == 18.75
        assert hy_score(375)  == 12.5
        assert hy_score(474)  == 12.5
        assert hy_score(475)  == 6.25
        assert hy_score(599)  == 6.25
        assert hy_score(600)  == 0.0
        assert hy_score(1000) == 0.0

    def test_nan_returns_none(self):
        assert hy_score(None) is None
        assert hy_score(float('nan')) is None

    def test_ground_truth_286bps(self):
        assert hy_score(286) == 25.0


# ── NetLiq Δ13w ───────────────────────────────────────────────────────────────

class TestNetliqDelta13wScore:
    def _make_series(self, vals: dict) -> pd.Series:
        return pd.Series(vals, dtype=float)

    def test_all_brackets(self):
        base  = pd.Timestamp('2020-06-05')   # un viernes
        ago13 = base - pd.Timedelta(weeks=13)
        for delta_b, expected in [
            (600,  25.0),
            (200,  18.75),
            (0,    12.5),
            (-200, 6.25),
            (-600, 0.0),
        ]:
            # delta_b en billions → delta_millions = delta_b * 1000
            past_val = 5_000_000.0
            cur_val  = past_val + delta_b * 1_000
            s = pd.Series({ago13: past_val, base: cur_val})
            assert netliq_delta13w_score(s, base) == expected

    def test_nan_returns_none(self):
        base = pd.Timestamp('2020-06-05')
        s = pd.Series({base: float('nan')})
        assert netliq_delta13w_score(s, base) is None

    def test_date_not_in_index(self):
        s = pd.Series({pd.Timestamp('2020-01-03'): 100.0})
        assert netliq_delta13w_score(s, pd.Timestamp('2020-06-05')) is None

    def test_no_past_data_returns_none(self):
        base = pd.Timestamp('2020-06-05')
        s = pd.Series({base: 5_000_000.0})  # sin datos 13w atrás
        assert netliq_delta13w_score(s, base) is None


# ── VolScore ──────────────────────────────────────────────────────────────────

class TestVixLevelScore:
    def test_all_brackets(self):
        assert vix_level_score(10)   == 20.0
        assert vix_level_score(13.9) == 20.0
        assert vix_level_score(14)   == 15.0
        assert vix_level_score(17.9) == 15.0
        assert vix_level_score(18)   == 10.0
        assert vix_level_score(22.9) == 10.0
        assert vix_level_score(23)   == 5.0
        assert vix_level_score(29.9) == 5.0
        assert vix_level_score(30)   == 0.0
        assert vix_level_score(50)   == 0.0

    def test_nan_returns_none(self):
        assert vix_level_score(None) is None
        assert vix_level_score(float('nan')) is None


class TestVixTermScore:
    def test_all_brackets(self):
        assert vix_term_score(8.0, 10.0)  == 20.0   # ratio 0.80
        assert vix_term_score(9.0, 10.0)  == 15.0   # ratio 0.90
        assert vix_term_score(10.0, 10.0) == 10.0   # ratio 1.00
        assert vix_term_score(11.0, 10.0) == 5.0    # ratio 1.10
        assert vix_term_score(12.0, 10.0) == 0.0    # ratio 1.20

    def test_nan_returns_none(self):
        assert vix_term_score(None, 10.0) is None
        assert vix_term_score(10.0, None) is None
        assert vix_term_score(None, None) is None

    def test_zero_vix3m_returns_none(self):
        assert vix_term_score(10.0, 0.0) is None


class TestVolScore:
    def test_uses_minimum(self):
        # nivel=15 (VIX=16), term=10 (ratio=1.04 < 1.05) → min=10
        assert vol_score(16, 10.4, 10.0) == 10.0
        # nivel=10 (VIX=20), term=20 (ratio=0.80 < 0.85) → min=10
        assert vol_score(20, 8.0, 10.0) == 10.0

    def test_fallback_when_term_none(self):
        # sin VIX9D/VIX3M → solo nivel
        assert vol_score(16, None, None) == 15.0
        assert vol_score(16, None, 10.0) == 15.0

    def test_vix_none_returns_none(self):
        assert vol_score(None, 10.0, 12.0) is None

    def test_ground_truth(self):
        # app: VIX≈17.94, VIX9D=15.46, VIX3M=20.77
        # nivel=15, term: ratio=0.744<0.85→20, min=15
        assert vol_score(17.94, 15.46, 20.77) == 15.0


# ── Curva ─────────────────────────────────────────────────────────────────────

class TestCurvaScore:
    def _series(self, val: float, dt: pd.Timestamp) -> pd.Series:
        return pd.Series({dt: val}, dtype=float)

    def test_all_brackets_positive_curve(self):
        dt = pd.Timestamp('2024-01-05')
        s = self._series(100.0, dt)
        assert curva_score(100,  s, dt) == pytest.approx(20.0 * 0.75)  # 15.0
        assert curva_score(50,   s, dt) == pytest.approx(15.0 * 0.75)  # 11.25
        assert curva_score(0,    s, dt) == pytest.approx(10.0 * 0.75)  # 7.5
        assert curva_score(-50,  s, dt) == pytest.approx(5.0 * 0.75)   # 3.75
        assert curva_score(-100, s, dt) == pytest.approx(0.0 * 0.75)   # 0.0

    def test_steepening_penalty(self):
        # Curva negativa: -20 bps, pero hace 13w era -100 bps → delta = +80 > 50
        # base /20 = 10 (−25 < −20 < 0 → bracket 10/20, wait: −20 > −25 → 10/20)
        # Actually: −20 bps → >-25 bracket → base=10, penalty applied → max(0,10-5)=5
        # scaled = 5 * 0.75 = 3.75
        cur_date = pd.Timestamp('2024-01-05')
        past_date = cur_date - pd.Timedelta(weeks=13)
        s = pd.Series({past_date: -100.0, cur_date: -20.0})
        result = curva_score(-20.0, s, cur_date)
        assert result == pytest.approx(5.0 * 0.75)

    def test_no_penalty_when_positive_curve(self):
        # Curva positiva: sin penalización aunque haya delta grande
        cur_date = pd.Timestamp('2024-01-05')
        past_date = cur_date - pd.Timedelta(weeks=13)
        s = pd.Series({past_date: -200.0, cur_date: 50.0})
        result = curva_score(50.0, s, cur_date)
        assert result == pytest.approx(15.0 * 0.75)

    def test_nan_returns_none(self):
        dt = pd.Timestamp('2024-01-05')
        assert curva_score(None, pd.Series(dtype=float), dt) is None
        assert curva_score(float('nan'), pd.Series(dtype=float), dt) is None

    def test_ground_truth_56bps(self):
        dt = pd.Timestamp('2026-04-17')
        s = pd.Series({dt: 56.0})
        assert curva_score(56.0, s, dt) == pytest.approx(11.25)


# ── CFNAI ─────────────────────────────────────────────────────────────────────

class TestCfnaiScore:
    def test_all_brackets(self):
        assert cfnai_score(0.5)   == 15.0
        assert cfnai_score(0.21)  == 15.0
        assert cfnai_score(0.20)  == 11.25
        assert cfnai_score(0.10)  == 11.25
        assert cfnai_score(0.00)  == 7.5
        assert cfnai_score(-0.10) == 7.5
        assert cfnai_score(-0.35) == 3.75
        assert cfnai_score(-0.50) == 3.75
        assert cfnai_score(-0.70) == 0.0
        assert cfnai_score(-1.00) == 0.0

    def test_nan_returns_none(self):
        assert cfnai_score(None) is None
        assert cfnai_score(float('nan')) is None

    def test_ground_truth(self):
        # app: CFNAI = -0.11 → 7.5
        assert cfnai_score(-0.11) == 7.5
