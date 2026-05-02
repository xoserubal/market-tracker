import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from portfolio.costs import transaction_cost, apply_entry_cost, apply_exit_cost


def test_entry_cost_10k():
    cost = transaction_cost(10_000)
    assert abs(cost - 5.0) < 0.001


def test_exit_cost_15k():
    cost = transaction_cost(15_000)
    assert abs(cost - 7.50) < 0.001


def test_round_trip_10k():
    """Round-trip: buy at 10k, sell at 10k. Total cost = 10."""
    entry_cost = transaction_cost(10_000)
    exit_cost  = transaction_cost(10_000)
    assert abs(entry_cost + exit_cost - 10.0) < 0.001


def test_apply_entry_deducts_from_cash():
    cash_after, cost = apply_entry_cost(10_000, 50_000)
    assert abs(cost - 5.0) < 0.001
    assert abs(cash_after - 49_995.0) < 0.001


def test_apply_exit_deducts_from_cash():
    cash_after, cost = apply_exit_cost(15_000, 0.0)
    assert abs(cost - 7.50) < 0.001
    assert abs(cash_after - (-7.50)) < 0.001


def test_zero_notional():
    assert transaction_cost(0) == 0.0
