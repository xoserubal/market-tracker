"""
Calculo de retornos forward a horizontes 4w, 13w, 26w.

Metodologia:
  - Muestrear prices_daily al ultimo dia habil de cada semana (W-FRI).
  - Para cada horizonte N_weeks, el retorno forward es:
      price(t + N*5 trading days) / price(t) - 1
    implementado como shift(-N_weeks) sobre el indice semanal.
  - NaN en las ultimas N semanas del dataset (sin horizonte disponible): se preservan.
  - Output: DataFrame long con MultiIndex (date, ticker).
"""

import pandas as pd
import numpy as np


HORIZONS_WEEKS = [4, 13, 26]
TRADING_DAYS   = {4: 20, 13: 65, 26: 130}


def compute_forward_returns(
    prices_daily: pd.DataFrame,
    horizons_weeks: list[int] | None = None,
) -> pd.DataFrame:
    """
    Para cada ticker y cada viernes, calcula retornos forward.

    Args:
        prices_daily: DataFrame diario (index=date, columns=tickers, values=close).
        horizons_weeks: lista de horizontes en semanas. Default [4, 13, 26].

    Returns:
        DataFrame con MultiIndex (date, ticker) y columnas:
          price_t, ret_fwd_4w, ret_fwd_13w, ret_fwd_26w
        NaN donde el horizonte se sale del rango de datos.
    """
    if horizons_weeks is None:
        horizons_weeks = HORIZONS_WEEKS

    # Muestrear al ultimo dia habil de cada semana
    weekly = prices_daily.resample('W-FRI').last()

    records = []
    tickers = [c for c in weekly.columns]

    for ticker in tickers:
        s = weekly[ticker]
        row = pd.DataFrame({'price_t': s})
        for nw in horizons_weeks:
            fwd = s.shift(-nw)
            row[f'ret_fwd_{nw}w'] = (fwd / s) - 1.0
        row.index.name = 'date'
        row['ticker'] = ticker
        records.append(row)

    df = pd.concat(records).reset_index().set_index(['date', 'ticker'])
    return df


def get_available_counts(fwd_df: pd.DataFrame) -> dict[str, int]:
    """
    Reporta cuantas observaciones (date, ticker) tienen cada horizonte disponible.
    """
    counts = {}
    for col in [c for c in fwd_df.columns if c.startswith('ret_fwd_')]:
        counts[col] = int(fwd_df[col].notna().sum())
    return counts
