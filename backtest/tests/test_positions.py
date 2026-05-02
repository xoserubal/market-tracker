import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
from portfolio.positions import (compute_new_position_size, make_position,
                                  position_value, is_stopped_out)


def test_equal_weight_4_positions():
    size = compute_new_position_size(40_000, 4)
    assert abs(size - 10_000) < 0.01


def test_equal_weight_zero_cash():
    size = compute_new_position_size(0, 4)
    assert size == 0.0


def test_equal_weight_zero_new_entries():
    size = compute_new_position_size(40_000, 0)
    assert size == 0.0


def test_make_position_shares():
    pos = make_position('XLK', pd.Timestamp('2010-01-01'), 50.0, 10_000)
    assert abs(pos['shares'] - 200.0) < 0.001
    assert abs(pos['stop_price'] - 42.5) < 0.001  # 50 * 0.85


def test_position_value():
    pos = make_position('XLK', pd.Timestamp('2010-01-01'), 50.0, 10_000)
    val = position_value(pos, 60.0)
    assert abs(val - 12_000.0) < 0.001


def test_stop_not_triggered():
    pos = make_position('XLK', pd.Timestamp('2010-01-01'), 100.0, 10_000)
    assert not is_stopped_out(pos, 90.0)   # -10%: not yet at -15%


def test_stop_triggered():
    pos = make_position('XLK', pd.Timestamp('2010-01-01'), 100.0, 10_000)
    assert is_stopped_out(pos, 84.0)       # -16%: below 85


def test_stop_at_boundary():
    pos = make_position('XLK', pd.Timestamp('2010-01-01'), 100.0, 10_000)
    assert is_stopped_out(pos, 85.0)       # exactly at 85 → triggers
