"""
Transaction cost model: 5 bps per trade on notional value.
Applied on both entry and exit.
"""

COST_BPS = 5
COST_RATE = COST_BPS / 10_000  # 0.0005


def transaction_cost(notional: float) -> float:
    """Cost in USD for a single trade of given notional."""
    return abs(notional) * COST_RATE


def apply_entry_cost(notional: float, cash: float) -> tuple[float, float]:
    """Deduct entry cost from cash. Returns (new_cash, cost_usd)."""
    cost = transaction_cost(notional)
    return cash - cost, cost


def apply_exit_cost(notional: float, cash: float) -> tuple[float, float]:
    """Deduct exit cost from cash. Returns (new_cash, cost_usd)."""
    cost = transaction_cost(notional)
    return cash - cost, cost
