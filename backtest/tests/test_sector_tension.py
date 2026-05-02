import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import numpy as np
from confluence.sector_tension import (
    cyclical_deterioration_score, defensive_strengthening_score,
    divergence_score, spy_internal_divergence_score, compute_sector_tension,
    TOTAL_MAX_B,
)


def _cluster(avg_rot, pct_4w=0.5):
    return {'avg_rotation_score': avg_rot, 'pct_ret_4w_positive_vs_spy': pct_4w}


class TestCyclicalDeterioration:
    def test_both_strong(self):
        g_now  = _cluster(2.0, 0.2)
        g_4w   = _cluster(4.0, 0.6)  # Δrot=-2, Δpct=-0.4
        v_now  = _cluster(2.5, 0.2)
        v_4w   = _cluster(4.5, 0.6)
        assert cyclical_deterioration_score(g_now, g_4w, v_now, v_4w) == 12

    def test_one_strong(self):
        g_now  = _cluster(2.0, 0.2)
        g_4w   = _cluster(4.0, 0.6)  # strong
        v_now  = _cluster(4.5, 0.5)
        v_4w   = _cluster(4.5, 0.5)  # none
        assert cyclical_deterioration_score(g_now, g_4w, v_now, v_4w) == 8

    def test_both_mild(self):
        g_now = _cluster(3.5, 0.5)
        g_4w  = _cluster(4.5, 0.6)  # Δrot=-1.0 (mild)
        v_now = _cluster(3.0, 0.5)
        v_4w  = _cluster(4.0, 0.6)  # mild
        assert cyclical_deterioration_score(g_now, g_4w, v_now, v_4w) == 5

    def test_one_mild(self):
        g_now = _cluster(3.5, 0.5)
        g_4w  = _cluster(4.5, 0.5)  # mild
        v_now = _cluster(4.5, 0.5)
        v_4w  = _cluster(4.5, 0.5)  # none
        assert cyclical_deterioration_score(g_now, g_4w, v_now, v_4w) == 2

    def test_none(self):
        g_now = _cluster(5.0, 0.5)
        g_4w  = _cluster(4.5, 0.5)
        v_now = _cluster(5.0, 0.5)
        v_4w  = _cluster(4.5, 0.5)
        assert cyclical_deterioration_score(g_now, g_4w, v_now, v_4w) == 0

    def test_missing_cluster_returns_none(self):
        assert cyclical_deterioration_score(None, None, None, None) is None


class TestDefensiveStrengthening:
    def test_both_strong(self):
        d_now  = _cluster(6.0)
        d_4w   = _cluster(4.5)   # Δ = +1.5
        dur_now = _cluster(5.0)
        dur_4w  = _cluster(3.5)  # Δ = +1.5
        assert defensive_strengthening_score(d_now, d_4w, dur_now, dur_4w) == 10

    def test_one_strong(self):
        d_now  = _cluster(6.0)
        d_4w   = _cluster(4.5)   # Δ = +1.5
        dur_now = _cluster(4.5)
        dur_4w  = _cluster(4.5)  # Δ = 0
        assert defensive_strengthening_score(d_now, d_4w, dur_now, dur_4w) == 6

    def test_mild(self):
        d_now  = _cluster(4.8)
        d_4w   = _cluster(4.0)   # Δ = +0.8 > 0.3
        dur_now = _cluster(4.0)
        dur_4w  = _cluster(4.0)  # Δ = 0
        assert defensive_strengthening_score(d_now, d_4w, dur_now, dur_4w) == 3

    def test_zero(self):
        d_now  = _cluster(4.0)
        d_4w   = _cluster(4.5)   # Δ = -0.5
        dur_now = _cluster(4.0)
        dur_4w  = _cluster(4.5)
        assert defensive_strengthening_score(d_now, d_4w, dur_now, dur_4w) == 0

    def test_missing_returns_none(self):
        assert defensive_strengthening_score(None, None, None, None) is None


class TestDivergenceScore:
    def test_strong(self):
        assert divergence_score(2.0, 5.5) == 8   # gap = 3.5

    def test_moderate(self):
        assert divergence_score(3.0, 5.5) == 5   # gap = 2.5

    def test_mild(self):
        assert divergence_score(4.0, 5.5) == 3   # gap = 1.5

    def test_none(self):
        assert divergence_score(4.5, 5.0) == 0   # gap = 0.5

    def test_missing(self):
        assert divergence_score(None, 5.0) is None


class TestSpyInternalDivergence:
    def test_spy_up_cyclicals_weak(self):
        assert spy_internal_divergence_score(True, 0.20, 0.25) == 5  # avg=0.225 < 0.30

    def test_spy_up_cyclicals_moderate(self):
        assert spy_internal_divergence_score(True, 0.35, 0.35) == 3  # avg=0.35 < 0.40

    def test_spy_up_cyclicals_ok(self):
        assert spy_internal_divergence_score(True, 0.50, 0.50) == 0

    def test_spy_below_sma200(self):
        assert spy_internal_divergence_score(False, 0.10, 0.10) == 0

    def test_missing_pct(self):
        assert spy_internal_divergence_score(True, None, 0.2) is None


class TestComputeSectorTension:
    def _make_clusters(self, cyc_rot=5.0, def_rot=5.0, pct=0.5):
        return {
            'Growth':        {'avg_rotation_score': cyc_rot, 'pct_ret_4w_positive_vs_spy': pct},
            'Value/Cyclical':{'avg_rotation_score': cyc_rot, 'pct_ret_4w_positive_vs_spy': pct},
            'Defensive':     {'avg_rotation_score': def_rot, 'pct_ret_4w_positive_vs_spy': pct},
            'Duration':      {'avg_rotation_score': def_rot, 'pct_ret_4w_positive_vs_spy': pct},
        }

    def test_max_score_is_35(self):
        now = {
            'Growth':        {'avg_rotation_score': 1.0, 'pct_ret_4w_positive_vs_spy': 0.1},
            'Value/Cyclical':{'avg_rotation_score': 1.0, 'pct_ret_4w_positive_vs_spy': 0.1},
            'Defensive':     {'avg_rotation_score': 8.0, 'pct_ret_4w_positive_vs_spy': 0.9},
            'Duration':      {'avg_rotation_score': 8.0, 'pct_ret_4w_positive_vs_spy': 0.9},
        }
        ago = {
            'Growth':        {'avg_rotation_score': 5.0, 'pct_ret_4w_positive_vs_spy': 0.6},
            'Value/Cyclical':{'avg_rotation_score': 5.0, 'pct_ret_4w_positive_vs_spy': 0.6},
            'Defensive':     {'avg_rotation_score': 4.5, 'pct_ret_4w_positive_vs_spy': 0.4},
            'Duration':      {'avg_rotation_score': 4.5, 'pct_ret_4w_positive_vs_spy': 0.4},
        }
        result = compute_sector_tension(now, ago, spy_above_sma200=True)
        assert result['sector_tension_scaled'] <= 35.0 + 1e-9

    def test_empty_clusters_returns_none(self):
        result = compute_sector_tension({}, {}, spy_above_sma200=True)
        assert result['sector_tension_scaled'] is None
