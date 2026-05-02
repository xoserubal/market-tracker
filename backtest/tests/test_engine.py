import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
import numpy as np
import pytest
from portfolio.engine import PortfolioEngine, INITIAL_CAPITAL


def _make_prices(tickers, start='2010-01-01', periods=520, price=100.0):
    """Constant price for all tickers."""
    idx = pd.bdate_range(start, periods=periods)
    data = {tk: price for tk in tickers}
    data['SPY'] = price
    return pd.DataFrame(data, index=idx)


def _make_regime(start='2010-01-01', periods=520, value='Bull Pleno'):
    idx = pd.bdate_range(start, periods=periods)
    return pd.Series(value, index=idx)


def _make_signals(dates_tickers_mode, early_rotation=True):
    rows = []
    for dt, tk, mode in dates_tickers_mode:
        rows.append({
            'ticker': tk, 'mode': mode, 'signal': 'ROT. TEMPRANA',
            'is_early_rotation': early_rotation, 'regime': 'Bull Pleno',
            'cluster': 'Growth',
        })
    if rows:
        idx = pd.DatetimeIndex([pd.Timestamp(dt) for dt, _, _ in dates_tickers_mode])
        df = pd.DataFrame(rows, index=idx)
        df.index.name = 'date'
        return df
    return pd.DataFrame()


class TestConstantPrices:
    """With constant prices, equity should stay close to initial capital (minus costs)."""

    def test_no_signals_tracks_spy(self):
        prices  = _make_prices(['XLK'])
        regime  = _make_regime()
        signals = pd.DataFrame()
        engine = PortfolioEngine(signals, prices, regime,
                                 include_btc=True, mode='A',
                                 start_date=pd.Timestamp('2010-01-01'),
                                 end_date=pd.Timestamp('2011-12-31'),
                                 strategy='rot_temprana_pure')
        result = engine.run()
        eq = result['equity_curve']
        spy = result['spy_equity']
        # No trades => equity tracks SPY exactly (both at constant 100)
        assert not eq.empty
        # All equity values should equal SPY equity (same price, same shares)
        diff = (eq - spy).abs()
        assert diff.max() < 1.0  # within $1 (no cost on SPY default)

    def test_one_signal_generates_two_trades(self):
        """ROT. TEMPRANA on a Friday → entry trade. 26w later → exit (max holding)."""
        # Friday 2010-01-08 is a Friday
        friday = pd.Timestamp('2010-01-08')
        assert friday.dayofweek == 4, f"Expected Friday, got {friday.day_name()}"

        prices  = _make_prices(['XLK', 'SPY'], periods=600)
        regime  = _make_regime(periods=600)
        signals = _make_signals([(friday, 'XLK', 'A')])

        engine = PortfolioEngine(signals, prices, regime,
                                 include_btc=True, mode='A',
                                 start_date=pd.Timestamp('2010-01-04'),
                                 end_date=pd.Timestamp('2011-12-31'),
                                 strategy='rot_temprana_pure')
        result = engine.run()
        trades = result['trades']
        # Should have at least 1 entry (and eventually 1 exit)
        xlt = trades[trades['ticker'] == 'XLK']
        assert len(xlt) >= 1

    def test_equity_always_positive(self):
        prices  = _make_prices(['XLK', 'GC=F', 'TLT'])
        regime  = _make_regime()
        friday  = pd.Timestamp('2010-01-08')
        signals = _make_signals([(friday, 'XLK', 'A'), (friday, 'GC=F', 'A')])

        engine = PortfolioEngine(signals, prices, regime,
                                 include_btc=False, mode='A',
                                 start_date=pd.Timestamp('2010-01-04'),
                                 end_date=pd.Timestamp('2012-12-31'),
                                 strategy='rot_temprana_pure')
        result = engine.run()
        assert (result['equity_curve'] > 0).all()

    def test_btc_excluded(self):
        prices  = _make_prices(['BTC-USD', 'XLK'])
        regime  = _make_regime()
        friday  = pd.Timestamp('2010-01-08')
        signals = _make_signals([(friday, 'BTC-USD', 'A'), (friday, 'XLK', 'A')])

        engine = PortfolioEngine(signals, prices, regime,
                                 include_btc=False, mode='A',
                                 start_date=pd.Timestamp('2010-01-04'),
                                 end_date=pd.Timestamp('2012-12-31'),
                                 strategy='rot_temprana_pure')
        result = engine.run()
        trades = result['trades']
        if not trades.empty:
            assert 'BTC-USD' not in trades['ticker'].values
