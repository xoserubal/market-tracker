"""
Alpha simple vs SPY: alpha_Nw(t, ticker) = ret_fwd_Nw(t, ticker) - ret_fwd_Nw(t, SPY)

Reglas:
  - Si ticker no tiene retorno pero SPY si: alpha = NaN
  - Si SPY no tiene retorno: alpha = NaN para todos
  - Nunca computar alpha con alguno de los dos retornos ausente
"""

import pandas as pd
import numpy as np

BENCHMARK = 'SPY'
HORIZONS  = [4, 13, 26]


def compute_alpha(forward_returns: pd.DataFrame) -> pd.DataFrame:
    """
    Anade columnas alpha_4w, alpha_13w, alpha_26w al DataFrame de forward returns.

    Args:
        forward_returns: MultiIndex (date, ticker), columnas ret_fwd_{N}w.

    Returns:
        DataFrame con las columnas alpha_Nw anadidas.
        SPY mismo: alpha = 0.0 donde el retorno existe, NaN donde no.
    """
    df = forward_returns.copy()

    # Extraer retornos de SPY por fecha
    spy_rows = df.xs(BENCHMARK, level='ticker') if BENCHMARK in df.index.get_level_values('ticker') else None

    for nw in HORIZONS:
        ret_col   = f'ret_fwd_{nw}w'
        alpha_col = f'alpha_{nw}w'

        if ret_col not in df.columns:
            df[alpha_col] = np.nan
            continue

        if spy_rows is None or ret_col not in spy_rows.columns:
            df[alpha_col] = np.nan
            continue

        spy_ret = spy_rows[ret_col]  # Series indexed by date

        # Broadcast SPY ret a todas las filas del multiindex
        dates  = df.index.get_level_values('date')
        spy_aligned = spy_ret.reindex(dates).values

        ticker_ret = df[ret_col].values
        alpha_vals = np.where(
            np.isnan(ticker_ret) | np.isnan(spy_aligned),
            np.nan,
            ticker_ret - spy_aligned,
        )
        df[alpha_col] = alpha_vals

    return df
