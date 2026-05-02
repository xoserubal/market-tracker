"""
Cálculo de deltas cortos (Δ2w, Δ4w, Δ8w) para uso futuro en Entrega 5.

Estos deltas NO entran en el MacroScore; se almacenan en macro_history.parquet
para el detector de confluencia temprana.

Las series se pasan en sus unidades nativas (las mismas que llegan al simulador):
  - hy_bps: bps
  - netliq: millones USD
  - t10y3m_bps: bps (ya convertida ×100 en el simulador)
  - t5yie: %
  - vix: puntos
"""
from __future__ import annotations
import pandas as pd


def _nearest_val(window: pd.Series, target_date: pd.Timestamp) -> float:
    """Value in window whose index date is nearest to target_date."""
    diffs = abs(window.index - target_date)
    return float(window.iloc[diffs.argmin()])


def compute_short_deltas(
    series: pd.Series,
    current_date: pd.Timestamp,
    weeks: tuple[int, ...] = (2, 4, 8),
) -> dict[str, float | None]:
    """
    Calcula deltas hacia atrás para los períodos indicados.
    Retorna dict con claves 'd{n}w' por cada n en weeks.
    """
    if current_date not in series.index:
        return {f'd{n}w': None for n in weeks}

    current_val = series.loc[current_date]
    if pd.isna(current_val):
        return {f'd{n}w': None for n in weeks}

    result: dict[str, float | None] = {}
    for n in weeks:
        date_ago = current_date - pd.Timedelta(weeks=n)
        past_window = series.loc[
            date_ago - pd.Timedelta(weeks=1) : date_ago + pd.Timedelta(weeks=1)
        ].dropna()
        if past_window.empty:
            result[f'd{n}w'] = None
        else:
            result[f'd{n}w'] = float(current_val) - _nearest_val(past_window, date_ago)
    return result
