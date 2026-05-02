import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import numpy as np
import pandas as pd
from confluence.validation import (run_lead_time_analysis,
                                   run_basket_alpha_analysis,
                                   run_false_positive_analysis)


_ALERT_COLS = ['date', 'mode', 'alert_type', 'confluence_score']

def _make_alerts(dates_modes):
    rows = []
    for date, mode in dates_modes:
        rows.append({
            'date': pd.Timestamp(date), 'mode': mode,
            'alert_type': 'STRUCTURAL', 'confluence_score': 65,
        })
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=_ALERT_COLS)


def _make_events(dates_modes_fp):
    rows = []
    for date, mode, is_fp in dates_modes_fp:
        rows.append({
            'transition_date': pd.Timestamp(date),
            'mode': mode,
            'is_false_positive_4w': is_fp,
        })
    return pd.DataFrame(rows)


class TestLeadTime:
    def test_alert_before_event_gives_positive_lead(self):
        alerts = _make_alerts([('2008-06-01', 'A')])
        events = _make_events([('2008-09-26', 'A', False)])
        result = run_lead_time_analysis(events, alerts)
        row = result[result['event_type'] == 'system_transition'].iloc[0]
        assert row['lead_time_days'] == (pd.Timestamp('2008-09-26')
                                         - pd.Timestamp('2008-06-01')).days

    def test_alert_after_event_gives_none(self):
        alerts = _make_alerts([('2008-10-01', 'A')])
        events = _make_events([('2008-09-26', 'A', False)])
        result = run_lead_time_analysis(events, alerts)
        row = result[result['event_type'] == 'system_transition'].iloc[0]
        assert row['lead_time_days'] is None or np.isnan(row['lead_time_days'])

    def test_no_alerts_gives_empty_df(self):
        events = _make_events([('2008-09-26', 'A', False)])
        result = run_lead_time_analysis(events, _make_alerts([]))
        assert result.empty

    def test_real_peaks_included(self):
        alerts = _make_alerts([('2007-07-01', 'A'), ('2007-07-01', 'B')])
        events = _make_events([])
        result = run_lead_time_analysis(events, alerts)
        real = result[result['event_type'] == 'real_peak']
        assert len(real) >= 2  # at least GFC and 2022 for one mode

    def test_covid_marked_informative(self):
        alerts = _make_alerts([('2020-01-01', 'A')])
        events = _make_events([])
        result = run_lead_time_analysis(events, alerts)
        covid = result[result['classification'] == 'COVID 2020']
        assert (covid['event_type'] == 'real_peak_informative').all()


class TestFalsePositiveRate:
    def _make_prices(self, t0, spy_min_after):
        dates = pd.date_range(t0, periods=300)
        spy = [100.0] * len(dates)
        # drop SPY to spy_min_after at midpoint
        mid = len(dates) // 2
        spy[mid] = 100 * (1 + spy_min_after)
        return pd.DataFrame({'SPY': spy}, index=dates)

    def test_drawdown_beyond_threshold_is_true_positive(self):
        t0 = '2010-01-01'
        prices = self._make_prices(t0, -0.15)
        alerts = _make_alerts([(t0, 'A')])
        result = run_false_positive_analysis(alerts, prices, drawdown_threshold=-0.10)
        assert result['true_positives'] == 1
        assert result['false_positives'] == 0

    def test_no_drawdown_is_false_positive(self):
        t0 = '2010-01-01'
        prices = self._make_prices(t0, -0.05)
        alerts = _make_alerts([(t0, 'A')])
        result = run_false_positive_analysis(alerts, prices, drawdown_threshold=-0.10)
        assert result['false_positives'] == 1
        assert result['true_positives'] == 0

    def test_no_alerts(self):
        prices = self._make_prices('2010-01-01', -0.20)
        result = run_false_positive_analysis(_make_alerts([]), prices)
        assert result['total'] == 0
