"""
Lead time de ROT. TEMPRANA vs señal convencional (COMPRA o ACUMULAR).

Para cada ROT. TEMPRANA emitida en (t, ticker, mode), busca la primera
señal COMPRA o ACUMULAR del mismo ticker+mode DESPUES de t (y antes de 52w).
"""

import pandas as pd
import numpy as np

CONVERGENCE_SIGNALS = {'COMPRA', 'ACUMULAR'}
MAX_LEAD_WEEKS      = 52


def compute_lead_time_single(
    early_rotation_date: pd.Timestamp,
    ticker: str,
    mode: str,
    rotation_history: pd.DataFrame,
    alpha_df: pd.DataFrame | None = None,
) -> dict:
    """
    Para una ROT. TEMPRANA individual, busca convergencia a COMPRA/ACUMULAR.

    Args:
        early_rotation_date: fecha de la ROT. TEMPRANA.
        ticker, mode:        identificadores del activo.
        rotation_history:    DataFrame completo (index=date).
        alpha_df:            opcional; si presente, extrae alpha_13w en la fecha
                             de convergencia y en la fecha de ROT. TEMPRANA.

    Returns dict con campos del brief.
    """
    rh = rotation_history
    mask_ticker = (
        (rh['ticker'] == ticker) &
        (rh['mode'] == mode) &
        (rh.index > early_rotation_date) &
        (rh.index <= early_rotation_date + pd.DateOffset(weeks=MAX_LEAD_WEEKS))
    )
    future = rh[mask_ticker].sort_index()
    conv_rows = future[future['signal'].isin(CONVERGENCE_SIGNALS)]

    first_conv_date = conv_rows.index[0] if not conv_rows.empty else None
    lead_weeks      = None
    conv_signal     = None

    if first_conv_date is not None:
        delta_days  = (first_conv_date - early_rotation_date).days
        lead_weeks  = round(delta_days / 7)
        conv_signal = conv_rows.iloc[0]['signal']

    # Extraer alphas si se provee alpha_df
    alpha_early = np.nan
    alpha_conv  = np.nan
    if alpha_df is not None:
        try:
            alpha_early = float(alpha_df.loc[(early_rotation_date, ticker), 'alpha_13w'])
        except KeyError:
            pass
        if first_conv_date is not None:
            try:
                alpha_conv = float(alpha_df.loc[(first_conv_date, ticker), 'alpha_13w'])
            except KeyError:
                pass

    return {
        'early_rotation_date':    early_rotation_date,
        'ticker':                 ticker,
        'mode':                   mode,
        'first_convergence_date': first_conv_date,
        'lead_time_weeks':        lead_weeks,
        'convergence_signal':     conv_signal,
        'alpha_13w_from_early':   alpha_early,
        'alpha_13w_from_convergence': alpha_conv,
    }


def compute_all_lead_times(
    rotation_history: pd.DataFrame,
    alpha_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Calcula lead time para todas las ROT. TEMPRANA en rotation_history.

    Returns DataFrame con columnas del brief + cluster.
    """
    er_rows = rotation_history[rotation_history['signal'] == 'ROT. TEMPRANA']

    records = []
    for date, row in er_rows.iterrows():
        rec = compute_lead_time_single(
            early_rotation_date = date,
            ticker              = row['ticker'],
            mode                = row['mode'],
            rotation_history    = rotation_history,
            alpha_df            = alpha_df,
        )
        rec['cluster'] = row.get('cluster')
        records.append(rec)

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df['early_rotation_date'] = pd.to_datetime(df['early_rotation_date'])
    df['first_convergence_date'] = pd.to_datetime(df['first_convergence_date'])
    return df
