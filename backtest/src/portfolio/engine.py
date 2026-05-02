"""
Portfolio simulation engine.

Granularity: daily price updates.
Signal decisions: only on Fridays (signal dates from rotation_history).
Cash not in open positions: held in SPY (default).
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from portfolio.costs import apply_entry_cost, apply_exit_cost
from portfolio.positions import (compute_new_position_size, make_position,
                                  position_value, is_stopped_out)


DEFENSIVE_BASKET = ['TLT', 'XLU', 'XLP', 'GC=F']
INITIAL_CAPITAL  = 100_000.0


def _get_price(prices_daily: pd.DataFrame, ticker: str, date: pd.Timestamp) -> float | None:
    """Return closing price for ticker on or before date (asof)."""
    if ticker not in prices_daily.columns:
        return None
    val = prices_daily[ticker].asof(date)
    if pd.isna(val) or val <= 0:
        return None
    return float(val)


def _get_spy_price(prices_daily: pd.DataFrame, date: pd.Timestamp) -> float:
    p = prices_daily['SPY'].asof(date)
    return float(p) if pd.notna(p) and p > 0 else None


def _portfolio_equity(cash: float, positions: dict,
                       prices_daily: pd.DataFrame, date: pd.Timestamp,
                       spy_cash: float) -> float:
    """
    Total equity = cash + sum(position market values) + spy_cash * (SPY return since last).
    SPY cash is tracked separately as notional invested in SPY default.
    """
    pos_value = 0.0
    for pos in positions.values():
        p = _get_price(prices_daily, pos['ticker'], date)
        if p is not None:
            pos_value += position_value(pos, p)
        else:
            pos_value += pos['shares'] * pos['entry_price']  # fallback: last known
    return cash + pos_value + spy_cash


class PortfolioEngine:
    """
    Simulates a portfolio day by day.

    Parameters
    ----------
    strategy_signals : pd.DataFrame
        Must have DatetimeIndex (weekly Fridays), columns: ticker, mode, signal, is_early_rotation,
        and strategy-specific entry/exit logic columns (regime, confluence_score, etc.)
    prices_daily     : pd.DataFrame with DatetimeIndex, columns = tickers
    macro_regime     : pd.Series with DatetimeIndex, values = regime string, indexed by date
    include_btc      : exclude BTC-USD if False
    mode             : 'A' or 'B'
    start_date       : simulation start
    end_date         : simulation end
    strategy         : 'rot_temprana_pure' | 'full_system'
    defensive_on_riskoff : bool (full_system only)
    """

    def __init__(self, strategy_signals: pd.DataFrame, prices_daily: pd.DataFrame,
                 macro_regime: pd.Series, include_btc: bool, mode: str,
                 start_date: pd.Timestamp, end_date: pd.Timestamp,
                 strategy: str = 'rot_temprana_pure',
                 confluence_series: pd.Series | None = None):
        self.signals       = strategy_signals
        self.prices        = prices_daily
        self.regime        = macro_regime
        self.include_btc   = include_btc
        self.mode          = mode
        self.start         = start_date
        self.end           = end_date
        self.strategy      = strategy
        self.confluence    = confluence_series  # for full_system COMPRA filter

    def _should_skip_ticker(self, ticker: str) -> bool:
        return not self.include_btc and ticker == 'BTC-USD'

    def _get_regime(self, date: pd.Timestamp) -> str:
        val = self.regime.asof(date)
        return str(val) if pd.notna(val) else 'Bull Pleno'

    def _get_confluence(self, date: pd.Timestamp) -> float | None:
        if self.confluence is None:
            return None
        val = self.confluence.asof(date)
        return float(val) if pd.notna(val) else None

    def _signals_on_date(self, date: pd.Timestamp) -> pd.DataFrame:
        """Return all signal rows for this exact date and mode."""
        if date not in self.signals.index:
            return pd.DataFrame()
        rows = self.signals.loc[[date]]
        return rows[rows['mode'] == self.mode]

    def _entry_signals(self, date: pd.Timestamp) -> pd.DataFrame:
        """Tickers that qualify for entry on this Friday."""
        rows = self._signals_on_date(date)
        if rows.empty:
            return rows

        if self.strategy == 'rot_temprana_pure':
            eligible = rows[rows['is_early_rotation'] == True]
        else:  # full_system
            rot = rows[rows['is_early_rotation'] == True]
            # COMPRA allowed only when confluence < 45
            conf = self._get_confluence(date)
            if conf is not None and conf < 45:
                compra = rows[rows['signal'] == 'COMPRA']
            else:
                compra = pd.DataFrame()
            eligible = pd.concat([rot, compra]).drop_duplicates(subset=['ticker'])

        # Filter BTC
        eligible = eligible[~eligible['ticker'].apply(self._should_skip_ticker)]
        return eligible

    def _check_exit(self, ticker: str, pos: dict, date: pd.Timestamp,
                    signals_today: pd.DataFrame, regime: str,
                    defensive_active: bool) -> str | None:
        """
        Returns exit reason string if position should be closed, else None.
        """
        price = _get_price(self.prices, ticker, date)
        if price is None:
            return None  # no price: hold

        # Stop loss: -15% from entry
        if is_stopped_out(pos, price):
            return 'stop_loss'

        # 26-week max holding period
        weeks_held = (date - pos['entry_date']).days / 7
        if weeks_held >= 26:
            return 'max_holding'

        # Signal changed to ACUMULAR* (emergency) or IGNORAR-equivalent
        if not signals_today.empty:
            row = signals_today[signals_today['ticker'] == ticker]
            if not row.empty:
                sig = row.iloc[0]['signal']
                if sig == 'ACUMULAR*':
                    return 'signal_acumular_star'

        # Risk-OFF: exit non-defensive positions
        if regime in ('Risk-OFF', 'Capitulación'):
            if ticker not in DEFENSIVE_BASKET:
                return 'regime_riskoff'

        # Full system: in defensive mode, non-basket tickers already exited above
        # But if defensive_active and ticker IS in basket: hold
        return None

    def run(self) -> dict:
        prices   = self.prices
        trading_days = prices.loc[self.start:self.end].index

        if len(trading_days) == 0:
            return {'equity_curve': pd.Series(dtype=float),
                    'trades': pd.DataFrame(),
                    'spy_equity': pd.Series(dtype=float)}

        cash      = INITIAL_CAPITAL
        positions: dict[str, dict] = {}  # ticker -> position dict
        spy_cash  = 0.0  # cash currently "in" SPY default
        trades_log: list[dict] = []

        equity_history = []

        # SPY entry price (for SPY default tracking)
        spy_entry_price = _get_spy_price(prices, trading_days[0])
        spy_shares = 0.0  # shares of SPY held as default

        # Initialize: put all capital in SPY default
        if spy_entry_price and spy_entry_price > 0:
            spy_shares = cash / spy_entry_price
            cash = 0.0

        defensive_active = False

        for date in trading_days:
            regime = self._get_regime(date)
            is_risk_off = regime in ('Risk-OFF', 'Capitulación')

            # ---- Activate/deactivate defensive mode (full_system only) ----
            if self.strategy == 'full_system':
                if is_risk_off and not defensive_active:
                    defensive_active = True
                    # Liquidate all non-defensive positions
                    for tk in list(positions.keys()):
                        if tk not in DEFENSIVE_BASKET:
                            price = _get_price(prices, tk, date)
                            if price is None:
                                price = positions[tk]['entry_price']
                            notional_exit = positions[tk]['shares'] * price
                            cash_after, cost = apply_exit_cost(notional_exit, cash)
                            pnl = notional_exit - positions[tk]['value_at_entry']
                            pnl_pct = price / positions[tk]['entry_price'] - 1
                            trades_log.append({
                                'strategy': self.strategy, 'mode': self.mode,
                                'ticker': tk, 'entry_date': positions[tk]['entry_date'],
                                'exit_date': date, 'entry_price': positions[tk]['entry_price'],
                                'exit_price': price, 'shares': positions[tk]['shares'],
                                'pnl': pnl - cost, 'pnl_pct': pnl_pct,
                                'notional_entry': positions[tk]['value_at_entry'],
                                'notional_exit': notional_exit, 'cost': cost,
                                'exit_reason': 'regime_riskoff',
                            })
                            cash = cash_after + notional_exit
                            del positions[tk]

                    # Enter defensive basket (equal-weight among available)
                    avail_def = [t for t in DEFENSIVE_BASKET if t in prices.columns
                                 and _get_price(prices, t, date) is not None]
                    if avail_def:
                        # Move SPY default to cash first
                        if spy_shares > 0:
                            spy_p = _get_spy_price(prices, date)
                            if spy_p:
                                spy_value = spy_shares * spy_p
                                cash += spy_value
                                spy_shares = 0.0
                        per_ticker = cash / len(avail_def)
                        for tk in avail_def:
                            if tk in positions:
                                # Mark existing signal position as defensive so it exits with regime
                                positions[tk]['position_type'] = 'defensive'
                                continue
                            p = _get_price(prices, tk, date)
                            cost_entry = per_ticker * 0.0005
                            pos = make_position(tk, date, p, per_ticker - cost_entry)
                            pos['position_type'] = 'defensive'
                            positions[tk] = pos
                            cash -= per_ticker
                            trades_log.append({
                                'strategy': self.strategy, 'mode': self.mode,
                                'ticker': tk, 'entry_date': date,
                                'exit_date': None, 'entry_price': p,
                                'exit_price': None, 'shares': pos['shares'],
                                'pnl': None, 'pnl_pct': None,
                                'notional_entry': per_ticker, 'notional_exit': None,
                                'cost': cost_entry, 'exit_reason': None,
                            })

                elif not is_risk_off and defensive_active:
                    defensive_active = False
                    # Exit only positions marked as defensive (entered during Risk-OFF)
                    for tk in list(positions.keys()):
                        if positions[tk].get('position_type') == 'defensive':
                            price = _get_price(prices, tk, date)
                            if price is None:
                                price = positions[tk]['entry_price']
                            notional_exit = positions[tk]['shares'] * price
                            cash_after, cost = apply_exit_cost(notional_exit, cash)
                            pnl_pct = price / positions[tk]['entry_price'] - 1
                            trades_log.append({
                                'strategy': self.strategy, 'mode': self.mode,
                                'ticker': tk, 'entry_date': positions[tk]['entry_date'],
                                'exit_date': date, 'entry_price': positions[tk]['entry_price'],
                                'exit_price': price, 'shares': positions[tk]['shares'],
                                'pnl': notional_exit - positions[tk]['value_at_entry'] - cost,
                                'pnl_pct': pnl_pct,
                                'notional_entry': positions[tk]['value_at_entry'],
                                'notional_exit': notional_exit, 'cost': cost,
                                'exit_reason': 'regime_normalized',
                            })
                            cash = cash_after + notional_exit
                            del positions[tk]

                    # Return to SPY default
                    if cash > 0 and spy_shares == 0:
                        sp = _get_spy_price(prices, date)
                        if sp:
                            spy_shares = cash / sp
                            cash = 0.0

            # ---- Friday: process exits and entries ----
            is_friday = (date.dayofweek == 4)
            if is_friday and not (defensive_active and self.strategy == 'full_system'):
                signals_today = self._signals_on_date(date)

                # Check exits for existing ROT./COMPRA positions
                for tk in list(positions.keys()):
                    # Skip positions currently designated as defensive (exit via regime_normalized)
                    if positions[tk].get('position_type') == 'defensive':
                        continue
                    reason = self._check_exit(tk, positions[tk], date,
                                               signals_today, regime, defensive_active)
                    if reason:
                        price = _get_price(prices, tk, date)
                        if price is None:
                            price = positions[tk]['entry_price']
                        notional_exit = positions[tk]['shares'] * price
                        cash_after, cost = apply_exit_cost(notional_exit, cash)

                        # Update SPY default with freed capital
                        freed = notional_exit - cost
                        sp = _get_spy_price(prices, date)
                        if sp and sp > 0:
                            spy_shares += freed / sp
                        else:
                            cash += freed

                        pnl_pct = price / positions[tk]['entry_price'] - 1
                        trades_log.append({
                            'strategy': self.strategy, 'mode': self.mode,
                            'ticker': tk, 'entry_date': positions[tk]['entry_date'],
                            'exit_date': date, 'entry_price': positions[tk]['entry_price'],
                            'exit_price': price, 'shares': positions[tk]['shares'],
                            'pnl': notional_exit - positions[tk]['value_at_entry'] - cost,
                            'pnl_pct': pnl_pct,
                            'notional_entry': positions[tk]['value_at_entry'],
                            'notional_exit': notional_exit, 'cost': cost,
                            'exit_reason': reason,
                        })
                        cash = cash_after
                        del positions[tk]

                # Check entries
                if not is_risk_off:
                    entries = self._entry_signals(date)
                    new_tickers = [r['ticker'] for _, r in entries.iterrows()
                                   if r['ticker'] not in positions]

                    if new_tickers:
                        # Withdraw from SPY default to fund entries
                        sp = _get_spy_price(prices, date)
                        total_spy_value = spy_shares * sp if (sp and spy_shares > 0) else 0.0
                        per_pos = compute_new_position_size(total_spy_value, len(new_tickers))

                        for tk in new_tickers:
                            if self._should_skip_ticker(tk):
                                continue
                            price = _get_price(prices, tk, date)
                            if price is None or per_pos <= 0:
                                continue
                            # Withdraw from SPY
                            if sp and sp > 0 and spy_shares > 0:
                                withdraw = min(per_pos, spy_shares * sp)
                                spy_shares -= withdraw / sp
                                alloc = withdraw
                            else:
                                alloc = 0.0

                            if alloc <= 1.0:  # less than $1, skip
                                continue

                            cost_entry = alloc * 0.0005
                            alloc_net = alloc - cost_entry
                            pos = make_position(tk, date, price, alloc_net)
                            positions[tk] = pos

                            trades_log.append({
                                'strategy': self.strategy, 'mode': self.mode,
                                'ticker': tk, 'entry_date': date,
                                'exit_date': None, 'entry_price': price,
                                'exit_price': None, 'shares': pos['shares'],
                                'pnl': None, 'pnl_pct': None,
                                'notional_entry': alloc, 'notional_exit': None,
                                'cost': cost_entry, 'exit_reason': None,
                            })

            # ---- Daily equity valuation ----
            pos_val = 0.0
            for pos in positions.values():
                p = _get_price(prices, pos['ticker'], date)
                if p is not None:
                    pos_val += position_value(pos, p)
                else:
                    pos_val += pos['shares'] * pos['entry_price']

            spy_p = _get_spy_price(prices, date)
            spy_val = spy_shares * spy_p if spy_p else 0.0

            total_equity = cash + pos_val + spy_val
            equity_history.append((date, total_equity))

        # Close all remaining open positions at end of period
        last_date = trading_days[-1]
        for tk in list(positions.keys()):
            price = _get_price(prices, tk, last_date)
            if price is None:
                price = positions[tk]['entry_price']
            notional_exit = positions[tk]['shares'] * price
            _, cost = apply_exit_cost(notional_exit, 0.0)
            pnl_pct = price / positions[tk]['entry_price'] - 1
            for tr in reversed(trades_log):
                if tr['ticker'] == tk and tr['exit_date'] is None:
                    tr['exit_date']    = last_date
                    tr['exit_price']   = price
                    tr['pnl']          = notional_exit - positions[tk]['value_at_entry'] - cost
                    tr['pnl_pct']      = pnl_pct
                    tr['notional_exit'] = notional_exit
                    tr['cost']         = tr.get('cost', 0) + cost
                    tr['exit_reason']  = 'end_of_period'
                    break

        equity_curve = pd.Series(
            [v for _, v in equity_history],
            index=[d for d, _ in equity_history],
        )

        # SPY buy-and-hold benchmark (same start capital, no costs)
        spy_start = _get_spy_price(prices, trading_days[0])
        spy_bench_shares = INITIAL_CAPITAL / spy_start if spy_start else 0
        spy_equity_vals = []
        for date in trading_days:
            sp = _get_spy_price(prices, date)
            spy_equity_vals.append(spy_bench_shares * sp if sp else INITIAL_CAPITAL)
        spy_equity = pd.Series(spy_equity_vals, index=trading_days)

        trades_df = pd.DataFrame(trades_log)

        return {
            'equity_curve': equity_curve,
            'spy_equity':   spy_equity,
            'trades':       trades_df,
        }
