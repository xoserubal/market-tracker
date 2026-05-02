import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from confluence.confluence_score import (
    compute_persistence_score, compute_confluence_score, score_label,
)


class TestPersistenceScore:
    def test_zero_weeks(self):
        assert compute_persistence_score([]) == 0

    def test_no_weeks_above_threshold(self):
        assert compute_persistence_score([10, 15, 19, 20]) == 0  # 20 is NOT > 20

    def test_four_weeks_above(self):
        hist = [25, 25, 25, 25]
        assert compute_persistence_score(hist) == 12  # 4 * 3

    def test_eight_weeks_above_cap(self):
        hist = [25] * 8
        assert compute_persistence_score(hist) == 24   # 8 * 3 = 24, cap 25

    def test_window_uses_last_8(self):
        # 9 weeks: first is below threshold, last 8 all above
        hist = [5] + [25] * 8
        assert compute_persistence_score(hist) == 24   # uses last 8 only

    def test_mixed(self):
        hist = [25, 10, 25, 10, 25, 10, 25, 10]  # 4 above 20
        assert compute_persistence_score(hist) == 12


class TestComputeConfluenceScore:
    def test_max_score(self):
        assert compute_confluence_score(40.0, 35.0, 25.0) == 100.0

    def test_zero_score(self):
        assert compute_confluence_score(0.0, 0.0, 0.0) == 0.0

    def test_missing_macro(self):
        # None macro → treated as 0
        score = compute_confluence_score(None, 35.0, 10.0)
        assert score == 45.0

    def test_missing_sector(self):
        score = compute_confluence_score(40.0, None, 10.0)
        assert score == 50.0

    def test_both_missing_returns_none(self):
        assert compute_confluence_score(None, None, 10.0) is None

    def test_partial(self):
        assert compute_confluence_score(20.0, 15.0, 9.0) == 44.0


class TestScoreLabel:
    def test_labels(self):
        assert score_label(None) == 'N/A'
        assert score_label(0)    == 'Normal'
        assert score_label(20)   == 'Normal'
        assert score_label(21)   == 'Cautela'
        assert score_label(40)   == 'Cautela'
        assert score_label(41)   == 'Tension elevada'
        assert score_label(60)   == 'Tension elevada'
        assert score_label(61)   == 'Alerta'
        assert score_label(80)   == 'Alerta'
        assert score_label(81)   == 'Alerta maxima'
        assert score_label(100)  == 'Alerta maxima'
