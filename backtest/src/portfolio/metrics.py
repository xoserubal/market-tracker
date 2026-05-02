"""
Portfolio performance metrics.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def compute_metrics(equity_curve: pd.Series, spy_equity: pd.Series,
                    trades: pd.DataFrame, strategy: str, include_btc: bool,
                    mode: str, period: str) -> dict:
    """
    equity_curve : daily equity values (DatetimeIndex)
    spy_equity   : SPY buy-and-hold equity (same index)
    trades       : DataFrame with columns entry_date, exit_date, pnl_pct
    """
    daily_ret = equity_curve.pct_change().dropna()
    spy_ret   = spy_equity.pct_change().dropna()

    n_days = len(equity_curve)
    n_years = n_days / 252

    equity_initial = float(equity_curve.iloc[0])
    equity_final   = float(equity_curve.iloc[-1])

    cagr = (equity_final / equity_initial) ** (1 / n_years) - 1 if n_years > 0 else 0.0
    total_return = equity_final / equity_initial - 1

    vol = float(daily_ret.std() * np.sqrt(252)) if len(daily_ret) > 1 else 0.0
    sharpe = float(daily_ret.mean() * 252 / (daily_ret.std() * np.sqrt(252))) \
             if daily_ret.std() > 0 else float('nan')

    # Max drawdown
    running_max = equity_curve.cummax()
    drawdown    = (equity_curve - running_max) / running_max
    max_dd      = float(drawdown.min())

    # Max drawdown duration (days from peak to recovery)
    dd_series = drawdown < 0
    max_dd_dur = 0
    if dd_series.any():
        cur = 0
        for in_dd in dd_series:
            cur = cur + 1 if in_dd else 0
            max_dd_dur = max(max_dd_dur, cur)

    # Beta and alpha vs SPY
    aligned = daily_ret.align(spy_ret, join='inner')
    strat_r, spy_r = aligned[0], aligned[1]
    if len(strat_r) > 10 and spy_r.std() > 0:
        beta = float(np.cov(strat_r, spy_r)[0, 1] / spy_r.var())
    else:
        beta = float('nan')

    spy_cagr = (float(spy_equity.iloc[-1]) / float(spy_equity.iloc[0])) ** (1 / n_years) - 1 \
               if n_years > 0 else 0.0
    alpha_ann = cagr - beta * spy_cagr if not np.isnan(beta) else float('nan')

    # Trade stats
    closed = trades[trades['exit_date'].notna()] if not trades.empty else pd.DataFrame()
    n_trades = len(closed)
    if n_trades > 0:
        winners  = closed[closed['pnl_pct'] > 0]
        losers   = closed[closed['pnl_pct'] <= 0]
        hit_rate = len(winners) / n_trades
        win_loss = (winners['pnl_pct'].mean() / abs(losers['pnl_pct'].mean())
                    if len(losers) > 0 and losers['pnl_pct'].mean() != 0 else float('nan'))
        avg_hold = (closed['exit_date'] - closed['entry_date']).dt.days.mean()

        mean_equity = equity_curve.mean()
        total_notional = closed['notional_entry'].sum() + closed['notional_exit'].sum() \
                         if 'notional_entry' in closed.columns else float('nan')
        turnover = total_notional / (2 * mean_equity) * (252 / n_days) \
                   if not np.isnan(total_notional) and mean_equity > 0 else float('nan')
    else:
        hit_rate = float('nan')
        win_loss = float('nan')
        avg_hold = float('nan')
        turnover = 0.0

    return {
        'strategy':               strategy,
        'include_btc':            include_btc,
        'mode':                   mode,
        'period':                 period,
        'equity_initial':         equity_initial,
        'equity_final':           equity_final,
        'cagr':                   cagr,
        'total_return':           total_return,
        'vol_annualized':         vol,
        'max_drawdown':           max_dd,
        'max_dd_duration_days':   max_dd_dur,
        'sharpe':                 sharpe,
        'beta_vs_spy':            beta,
        'alpha_annualized':       alpha_ann,
        'hit_rate':               hit_rate,
        'win_loss_ratio':         win_loss,
        'turnover_annual':        turnover,
        'n_trades':               n_trades,
        'avg_holding_period_days': avg_hold,
    }


def compute_spy_metrics(spy_equity: pd.Series, period: str) -> dict:
    n_days  = len(spy_equity)
    n_years = n_days / 252
    ei = float(spy_equity.iloc[0])
    ef = float(spy_equity.iloc[-1])
    cagr = (ef / ei) ** (1 / n_years) - 1 if n_years > 0 else 0.0
    daily_ret = spy_equity.pct_change().dropna()
    vol    = float(daily_ret.std() * np.sqrt(252)) if len(daily_ret) > 1 else 0.0
    sharpe = float(daily_ret.mean() * 252 / (daily_ret.std() * np.sqrt(252))) \
             if daily_ret.std() > 0 else float('nan')
    running_max = spy_equity.cummax()
    max_dd = float(((spy_equity - running_max) / running_max).min())
    return {
        'strategy': 'spy_benchmark', 'include_btc': True, 'mode': 'N/A',
        'period': period, 'equity_initial': ei, 'equity_final': ef,
        'cagr': cagr, 'total_return': ef / ei - 1,
        'vol_annualized': vol, 'max_drawdown': max_dd,
        'max_dd_duration_days': float('nan'), 'sharpe': sharpe,
        'beta_vs_spy': 1.0, 'alpha_annualized': 0.0,
        'hit_rate': float('nan'), 'win_loss_ratio': float('nan'),
        'turnover_annual': 0.0, 'n_trades': 0,
        'avg_holding_period_days': float('nan'),
    }
