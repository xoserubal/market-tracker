"""
Motor semanal: itera el histórico completo y produce confluence_history y confluence_alerts.
"""
import numpy as np
import pandas as pd

from .macro_tension import compute_macro_tension
from .sector_tension import compute_sector_tension
from .confluence_score import compute_persistence_score, compute_confluence_score
from .alerts import make_alert_state, update_alerts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_cluster_lookup(cluster_health_df):
    """
    Returns dict: (date, mode) -> {cluster_name: {col: val}}
    """
    lookup = {}
    for date, grp_date in cluster_health_df.groupby(cluster_health_df.index):
        for mode, grp_mode in grp_date.groupby('mode'):
            clusters = {}
            for _, row in grp_mode.iterrows():
                clusters[row['cluster']] = row.to_dict()
            lookup[(date, mode)] = clusters
    return lookup


def _build_spy_sma200(prices_daily):
    spy = prices_daily['SPY'].dropna()
    sma200 = spy.rolling(200, min_periods=100).mean()
    above = (spy > sma200).reindex(prices_daily.index)
    return above


def _get_cluster_data(lookup, date, mode, dates_sorted, lookback_weeks):
    """Get cluster data for (date, mode) and for (date - lookback_weeks) ago."""
    current = lookup.get((date, mode), {})

    # Find date ~lookback_weeks weeks ago using sorted date list
    date_idx = dates_sorted.get_loc(date) if date in dates_sorted else None
    if date_idx is None or date_idx < lookback_weeks:
        return current, {}
    past_date = dates_sorted[date_idx - lookback_weeks]
    past = lookup.get((past_date, mode), {})
    return current, past


def _spy_above_sma200_on(date, spy_above_series):
    if date in spy_above_series.index:
        v = spy_above_series.asof(date)
        return bool(v) if not pd.isna(v) else False
    return False


# ---------------------------------------------------------------------------
# Main simulator
# ---------------------------------------------------------------------------

def simulate_confluence_history(macro_history, cluster_health, prices_daily,
                                  modes=('A', 'B')):
    """
    Run the detector over the full history for each mode.

    Returns:
      history_df : DataFrame (date, mode, confluence_score, components, ...)
      alerts_df  : DataFrame (one row per alert activation)
    """
    cluster_lookup = _build_cluster_lookup(cluster_health)
    spy_above      = _build_spy_sma200(prices_daily)

    # Sorted unique dates from macro_history
    all_dates = macro_history.index.unique().sort_values()
    # pd.DatetimeIndex for positional lookup
    dates_idx = all_dates

    history_rows = []
    alert_rows   = []

    for mode in modes:
        macro_mode = macro_history[macro_history['mode'] == mode].copy()
        macro_mode = macro_mode[~macro_mode.index.duplicated(keep='first')]

        state = make_alert_state()
        macro_tension_history_8w = []

        for date in dates_idx:
            if date not in macro_mode.index:
                continue

            macro_row = macro_mode.loc[date].to_dict()

            # ---- Bloque A ----
            macro_t = compute_macro_tension(macro_row)
            macro_scaled = macro_t['macro_tension_scaled']

            # ---- Bloque B ----
            cluster_now, cluster_4w = _get_cluster_data(
                cluster_lookup, date, mode, dates_idx,
                lookback_weeks=4
            )
            spy_bool = _spy_above_sma200_on(date, spy_above)
            sector_t = compute_sector_tension(cluster_now, cluster_4w, spy_bool)
            sector_scaled = sector_t['sector_tension_scaled']

            # ---- Persistencia ----
            macro_tension_history_8w.append(macro_scaled)
            if len(macro_tension_history_8w) > 8:
                macro_tension_history_8w = macro_tension_history_8w[-8:]
            persistence = compute_persistence_score(macro_tension_history_8w)

            # ---- Score total ----
            confluence = compute_confluence_score(macro_scaled, sector_scaled, persistence)

            # ---- Alertas ----
            alert_updates = update_alerts(
                confluence, macro_scaled, sector_scaled, persistence,
                state, date
            )

            # ---- Componentes individuales para output ----
            comps_A = macro_t['components']
            comps_B = sector_t['components']
            missing_components = [k for k, v in {**comps_A, **comps_B}.items()
                                   if v is None]

            row = {
                'date':              date,
                'mode':              mode,
                'confluence_score':  confluence,
                'macro_tension':     macro_scaled,
                'sector_tension':    sector_scaled,
                'persistence':       persistence,
                'structural_active': state['structural_active'],
                'tactical_active':   state['tactical_active'],
                # Bloque A components
                'A_hy_accel':        comps_A.get('hy_accel'),
                'A_netliq_contract': comps_A.get('netliq_contract'),
                'A_curve_dynamics':  comps_A.get('curve_dynamics'),
                'A_vol_shift':       comps_A.get('vol_shift'),
                'A_inflation_shift': comps_A.get('inflation_shift'),
                # Bloque B components
                'B_cyclical_deteri':    comps_B.get('cyclical_deteri'),
                'B_defensive_strength': comps_B.get('defensive_strength'),
                'B_cyc_def_divergence': comps_B.get('cyc_def_divergence'),
                'B_spy_internal_div':   comps_B.get('spy_internal_div'),
                # Meta
                'components_missing': ','.join(missing_components),
                'spy_above_sma200':   spy_bool,
                'macro_abs':          macro_t.get('macro_tension_absolute'),
                'macro_max':          macro_t.get('macro_tension_max'),
                'sector_abs':         sector_t.get('sector_tension_absolute'),
                'sector_max':         sector_t.get('sector_tension_max'),
            }
            history_rows.append(row)

            # ---- Registrar alertas ----
            for alert_type, just_key in [
                ('STRUCTURAL', 'structural_just_activated'),
                ('TACTICAL',   'tactical_just_activated'),
            ]:
                if alert_updates[just_key]:
                    all_comps = {**comps_A, **comps_B}
                    # dominant: component with highest pts contribution
                    available_comps = {k: v for k, v in all_comps.items()
                                        if v is not None and v > 0}
                    dominant = (max(available_comps, key=available_comps.get)
                                if available_comps else None)
                    alert_row = {
                        'date':              date,
                        'mode':              mode,
                        'alert_type':        alert_type,
                        'confluence_score':  confluence,
                        'macro_tension':     macro_scaled,
                        'sector_tension':    sector_scaled,
                        'persistence':       persistence,
                        # Component contributions at activation
                        'component_A1_hy_accel':       comps_A.get('hy_accel'),
                        'component_A2_netliq_contract': comps_A.get('netliq_contract'),
                        'component_A3_curve_dynamics':  comps_A.get('curve_dynamics'),
                        'component_A4_vol_shift':       comps_A.get('vol_shift'),
                        'component_A5_inflation_shift': comps_A.get('inflation_shift'),
                        'component_B1_cyclical_deteri':    comps_B.get('cyclical_deteri'),
                        'component_B2_defensive_strength': comps_B.get('defensive_strength'),
                        'component_B3_cyc_def_divergence': comps_B.get('cyc_def_divergence'),
                        'component_B4_spy_internal_div':   comps_B.get('spy_internal_div'),
                        'components_missing': ','.join(missing_components),
                        'dominant_component': dominant,
                    }
                    alert_rows.append(alert_row)

    history_df = pd.DataFrame(history_rows)
    alerts_df  = pd.DataFrame(alert_rows) if alert_rows else pd.DataFrame()

    if not history_df.empty:
        history_df = history_df.sort_values(['date', 'mode']).reset_index(drop=True)
    if not alerts_df.empty:
        alerts_df = alerts_df.sort_values(['date', 'mode']).reset_index(drop=True)

    return history_df, alerts_df
