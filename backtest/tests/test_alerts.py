import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import pandas as pd
from confluence.alerts import make_alert_state, update_alerts


def _week(n):
    return pd.Timestamp('2008-01-01') + pd.Timedelta(weeks=n)


def _apply(state, confluence, macro, sector, persistence, week_n):
    return update_alerts(confluence, macro, sector, persistence, state, _week(week_n))


class TestStructuralAlert:
    def test_activates_after_two_weeks(self):
        state = make_alert_state()
        # week 1: conditions met, no activation yet
        r1 = _apply(state, 60, 22, 18, 15, 1)
        assert not r1['structural_just_activated']
        assert not state['structural_active']
        # week 2: conditions still met → activate
        r2 = _apply(state, 60, 22, 18, 15, 2)
        assert r2['structural_just_activated']
        assert state['structural_active']

    def test_does_not_activate_if_condition_breaks_week2(self):
        state = make_alert_state()
        _apply(state, 60, 22, 18, 15, 1)
        r2 = _apply(state, 30, 22, 18, 15, 2)  # confluence drops
        assert not r2['structural_just_activated']
        assert not state['structural_active']

    def test_deactivates_after_two_low_confluence_weeks(self):
        state = make_alert_state()
        _apply(state, 60, 22, 18, 15, 1)
        _apply(state, 60, 22, 18, 15, 2)  # activated
        assert state['structural_active']
        _apply(state, 30, 22, 18, 15, 3)  # low confluence week 1
        assert state['structural_active']  # still active
        r4 = _apply(state, 30, 22, 18, 15, 4)  # low confluence week 2
        assert r4['structural_just_deactivated']
        assert not state['structural_active']

    def test_missing_macro_not_enough_for_structural(self):
        # structural requires macro >= 20
        state = make_alert_state()
        _apply(state, 60, None, 18, 15, 1)
        r2 = _apply(state, 60, None, 18, 15, 2)
        assert not r2['structural_just_activated']


class TestTacticalAlert:
    def test_activates_sector_only(self):
        state = make_alert_state()
        # sector >= 20, macro < 15
        _apply(state, 25, 10, 22, 5, 1)
        r2 = _apply(state, 25, 10, 22, 5, 2)
        assert r2['tactical_just_activated']
        assert state['tactical_active']

    def test_structural_supersedes_tactical(self):
        state = make_alert_state()
        # First get tactical active
        _apply(state, 25, 10, 22, 5, 1)
        _apply(state, 25, 10, 22, 5, 2)
        assert state['tactical_active']
        # Then structural kicks in
        _apply(state, 60, 22, 18, 15, 3)
        r4 = _apply(state, 60, 22, 18, 15, 4)
        assert r4['structural_just_activated']
        assert r4['tactical_just_deactivated']
        assert state['structural_active']
        assert not state['tactical_active']
