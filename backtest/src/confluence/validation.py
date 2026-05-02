"""
Tres análisis de validación retrospectiva (no son pytest tests).
  run_lead_time_analysis   — Lead time vs 14 eventos + 2 picos reales
  run_basket_alpha_analysis — Alpha del basket desde alertas
  run_false_positive_analysis — Tasa de falsos positivos
"""
import numpy as np
import pandas as pd


REAL_PEAKS = [
    {'label': 'GFC 2007',   'peak_date': pd.Timestamp('2007-10-12'),
     'has_precursors': True},
    {'label': 'Bear 2022',  'peak_date': pd.Timestamp('2022-01-04'),
     'has_precursors': True},
    {'label': 'COVID 2020', 'peak_date': pd.Timestamp('2020-02-14'),
     'has_precursors': False},
]


def _find_alert_before(ref_date, structural_alerts, mode, max_days=180):
    candidates = structural_alerts[
        (structural_alerts['mode'] == mode)
        & (structural_alerts['alert_type'] == 'STRUCTURAL')
        & (structural_alerts['date'] <= ref_date)
        & (structural_alerts['date'] >= ref_date - pd.Timedelta(days=max_days))
    ]
    if candidates.empty:
        return None
    return candidates.sort_values('date').iloc[-1]


# ---------------------------------------------------------------------------
# Analysis 1 — Lead time
# ---------------------------------------------------------------------------

def run_lead_time_analysis(recession_events, alerts_df):
    """
    recession_events : DataFrame from recession_basket_validation.parquet
    alerts_df        : output of simulator

    Returns DataFrame with one row per (event × mode).
    """
    if alerts_df.empty:
        return pd.DataFrame()

    rows = []
    structural = alerts_df[alerts_df['alert_type'] == 'STRUCTURAL']

    for _, ev in recession_events.iterrows():
        event_date = pd.Timestamp(ev['transition_date'])
        mode       = ev['mode']
        classif    = 'VALIDADA' if not ev.get('is_false_positive_4w', False) else 'CEDIDA'

        alert = _find_alert_before(event_date, structural, mode)
        lead_days = (event_date - alert['date']).days if alert is not None else None
        rows.append({
            'event_date':       event_date,
            'mode':             mode,
            'event_type':       'system_transition',
            'classification':   classif,
            'alert_date':       alert['date'] if alert is not None else None,
            'lead_time_days':   lead_days,
            'alert_confluence': alert['confluence_score'] if alert is not None else None,
        })

    for pk in REAL_PEAKS:
        for mode in ['A', 'B']:
            alert = _find_alert_before(pk['peak_date'], structural, mode)
            lead_days = (pk['peak_date'] - alert['date']).days if alert is not None else None
            rows.append({
                'event_date':       pk['peak_date'],
                'mode':             mode,
                'event_type':       ('real_peak' if pk['has_precursors']
                                     else 'real_peak_informative'),
                'classification':   pk['label'],
                'alert_date':       alert['date'] if alert is not None else None,
                'lead_time_days':   lead_days,
                'alert_confluence': alert['confluence_score'] if alert is not None else None,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Analysis 2 — Basket alpha desde alertas
# ---------------------------------------------------------------------------

BASKET_TICKERS = ['TLT', 'XLU', 'XLV', 'XLP', 'XLRE', 'GC=F']
HORIZONS = {'4w': 28, '13w': 91, '26w': 182}


def run_basket_alpha_analysis(alerts_df, prices_daily):
    """
    Returns DataFrame with basket alpha per STRUCTURAL alert.
    """
    structural = alerts_df[alerts_df['alert_type'] == 'STRUCTURAL'].copy() \
        if not alerts_df.empty else pd.DataFrame()
    if structural.empty:
        return pd.DataFrame()

    rows = []
    for _, alert in structural.iterrows():
        t0 = pd.Timestamp(alert['date'])
        row = {'alert_date': t0, 'mode': alert['mode'],
               'confluence_at_alert': alert['confluence_score']}

        for label, days in HORIZONS.items():
            t1 = t0 + pd.Timedelta(days=days)
            spy0 = prices_daily['SPY'].asof(t0)
            spy1 = prices_daily['SPY'].asof(t1)
            spy_ret = (spy1 / spy0 - 1) if (spy0 and spy1 and spy0 > 0) else None

            basket_rets = []
            for tk in BASKET_TICKERS:
                if tk in prices_daily.columns:
                    p0 = prices_daily[tk].asof(t0)
                    p1 = prices_daily[tk].asof(t1)
                    if p0 and p1 and p0 > 0:
                        basket_rets.append(p1 / p0 - 1)

            basket_ret = float(np.mean(basket_rets)) if basket_rets else None
            alpha = ((basket_ret - spy_ret)
                     if (basket_ret is not None and spy_ret is not None) else None)
            row[f'basket_ret_{label}']   = basket_ret
            row[f'spy_ret_{label}']      = spy_ret
            row[f'basket_alpha_{label}'] = alpha

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Analysis 3 — Tasa de falsos positivos
# ---------------------------------------------------------------------------

def run_false_positive_analysis(alerts_df, prices_daily, drawdown_threshold=-0.10):
    """
    STRUCTURAL alert with no SPY drawdown > threshold in 26w → false positive.
    Returns dict with summary + 'detail' DataFrame.
    """
    structural = alerts_df[alerts_df['alert_type'] == 'STRUCTURAL'].copy() \
        if not alerts_df.empty else pd.DataFrame()
    if structural.empty:
        return {'total': 0, 'true_positives': 0, 'false_positives': 0,
                'fp_rate': None, 'detail': pd.DataFrame()}

    rows = []
    for _, alert in structural.iterrows():
        t0    = pd.Timestamp(alert['date'])
        t_end = t0 + pd.Timedelta(weeks=26)
        spy0  = prices_daily['SPY'].asof(t0)
        spy_window = prices_daily['SPY'].loc[
            (prices_daily.index >= t0) & (prices_daily.index <= t_end)
        ].dropna()

        if spy_window.empty or not spy0 or spy0 == 0:
            continue
        max_dd = spy_window.min() / spy0 - 1
        is_fp  = max_dd > drawdown_threshold
        rows.append({
            'alert_date':           t0,
            'mode':                 alert['mode'],
            'spy_max_drawdown_26w': max_dd,
            'is_false_positive':    is_fp,
            'confluence_at_alert':  alert['confluence_score'],
        })

    if not rows:
        return {'total': 0, 'true_positives': 0, 'false_positives': 0,
                'fp_rate': None, 'detail': pd.DataFrame()}

    detail  = pd.DataFrame(rows)
    total   = len(detail)
    fps     = int(detail['is_false_positive'].sum())
    tps     = total - fps
    fp_rate = fps / total if total > 0 else None
    return {'total': total, 'true_positives': tps, 'false_positives': fps,
            'fp_rate': fp_rate, 'detail': detail}
