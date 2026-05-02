"""
Strategy runners: builds all 24 simulation variants and returns DataFrames.
"""
from __future__ import annotations

import pandas as pd
from portfolio.engine import PortfolioEngine
from portfolio.metrics import compute_metrics, compute_spy_metrics

PERIODS = {
    '2005-2026': ('2005-01-03', '2026-04-19'),
    '2010-2019': ('2010-01-04', '2019-12-31'),
    '2020-2026': ('2020-01-02', '2026-04-19'),
}

STRATEGIES = ['rot_temprana_pure', 'full_system']
MODES      = ['A', 'B']
BTC_FLAGS  = [True, False]


def run_all_simulations(rotation_history: pd.DataFrame,
                        macro_history: pd.DataFrame,
                        prices_daily: pd.DataFrame,
                        confluence_series: pd.Series | None = None,
                        ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Runs 24 simulations (8 combinations × 3 periods).
    Returns (equity_history_df, trades_df, metrics_df).
    """
    # Build macro regime series (mode-averaged or Mode A — both modes use same macro)
    macro_a = macro_history[macro_history['mode'] == 'A']['regime'] \
              if 'mode' in macro_history.columns else macro_history['regime']

    all_equity  = []
    all_trades  = []
    all_metrics = []
    spy_benchmarks_done = set()

    combo_n = 0
    for strategy in STRATEGIES:
        for include_btc in BTC_FLAGS:
            for mode in MODES:
                for period_label, (start_str, end_str) in PERIODS.items():
                    combo_n += 1
                    start = pd.Timestamp(start_str)
                    end   = pd.Timestamp(end_str)

                    btc_label = 'incl_btc' if include_btc else 'excl_btc'
                    label = f'{strategy}__{mode}__{btc_label}__{period_label}'
                    print(f'  [{combo_n}/24] {label}')

                    engine = PortfolioEngine(
                        strategy_signals = rotation_history,
                        prices_daily     = prices_daily,
                        macro_regime     = macro_a,
                        include_btc      = include_btc,
                        mode             = mode,
                        start_date       = start,
                        end_date         = end,
                        strategy         = strategy,
                        confluence_series= confluence_series,
                    )
                    result = engine.run()

                    eq = result['equity_curve']
                    trades = result['trades']
                    spy_eq = result['spy_equity']

                    # Equity history
                    eq_df = eq.reset_index()
                    eq_df.columns = ['date', 'equity']
                    eq_df['strategy']    = strategy
                    eq_df['mode']        = mode
                    eq_df['include_btc'] = include_btc
                    eq_df['period']      = period_label
                    all_equity.append(eq_df)

                    # Trades
                    if not trades.empty:
                        trades = trades.copy()
                        trades['period'] = period_label
                        all_trades.append(trades)

                    # Metrics
                    closed = trades[trades['exit_date'].notna()] \
                             if not trades.empty else pd.DataFrame()
                    m = compute_metrics(eq, spy_eq, closed, strategy,
                                        include_btc, mode, period_label)
                    all_metrics.append(m)

                    # SPY benchmark (once per period)
                    if period_label not in spy_benchmarks_done:
                        spy_benchmarks_done.add(period_label)
                        sm = compute_spy_metrics(spy_eq, period_label)
                        all_metrics.append(sm)

    equity_df  = pd.concat(all_equity,  ignore_index=True) if all_equity  else pd.DataFrame()
    trades_df  = pd.concat(all_trades,  ignore_index=True) if all_trades  else pd.DataFrame()
    metrics_df = pd.DataFrame(all_metrics)

    return equity_df, trades_df, metrics_df
