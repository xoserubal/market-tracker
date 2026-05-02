"""
Equal-weight position sizing with SPY as default for uninvested cash.

Rules:
- No forced rebalance on existing positions when a new one opens.
- New position receives: available_cash / (n_new_positions).
- SPY absorbs cash not invested in active signals.
- stop_price = entry_price * (1 - 0.15) for 15% individual stop.
"""
from __future__ import annotations
import pandas as pd


def compute_new_position_size(available_cash: float, n_new_entries: int) -> float:
    """Cash allocated to each new entry (equal split of available cash)."""
    if n_new_entries <= 0 or available_cash <= 0:
        return 0.0
    return available_cash / n_new_entries


def make_position(ticker: str, entry_date: pd.Timestamp,
                  entry_price: float, value_usd: float) -> dict:
    """Create a position record."""
    shares = value_usd / entry_price
    return {
        'ticker':       ticker,
        'entry_date':   entry_date,
        'entry_price':  entry_price,
        'shares':       shares,
        'value_at_entry': value_usd,
        'stop_price':   entry_price * 0.85,  # 15% stop
    }


def position_value(position: dict, current_price: float) -> float:
    return position['shares'] * current_price


def is_stopped_out(position: dict, current_price: float) -> bool:
    return current_price <= position['stop_price']


def spy_weight(open_positions: dict, prices: dict[str, float]) -> float:
    """
    Total portfolio value fraction not covered by open positions.
    Returns cash_fraction (0.0 - 1.0) that should be in SPY.
    Not used for execution — only for equity valuation.
    """
    total_pos_value = sum(
        position_value(p, prices.get(p['ticker'], p['entry_price']))
        for p in open_positions.values()
    )
    return total_pos_value  # caller computes SPY value as total_equity - total_pos_value
