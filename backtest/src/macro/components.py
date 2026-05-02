"""
5 subcomponentes del MacroScore. Funciones puras — input NaN/None devuelve None.

NOTA DE UNIDADES (desviaciones respecto al brief):
- netliq_series: está en MILLONES USD en el parquet (no raw USD).
  La conversión correcta es /1e3 (millones → miles de millones), no /1e9.
- t10y3m_bps: debe llegar ya en bps (×100 aplicado en el simulador,
  ya que macro_daily['T10Y3M'] está en % en FRED).
"""
from __future__ import annotations
import pandas as pd


def _nearest_val(window: pd.Series, target_date: pd.Timestamp) -> float:
    """Value in window whose index date is nearest to target_date."""
    diffs = abs(window.index - target_date)
    return float(window.iloc[diffs.argmin()])


# ── HY Spread (/25) ──────────────────────────────────────────────────────────

def hy_score(spread_bps: float | None) -> float | None:
    if spread_bps is None or pd.isna(spread_bps):
        return None
    if spread_bps < 300:  return 25.0
    if spread_bps < 375:  return 18.75
    if spread_bps < 475:  return 12.5
    if spread_bps < 600:  return 6.25
    return 0.0


# ── Net Liquidity Δ13w (/25) ─────────────────────────────────────────────────

def netliq_delta13w_score(netliq_series: pd.Series, current_date: pd.Timestamp) -> float | None:
    """
    netliq_series en MILLONES USD (parquet usa WALCL−RRPONTSYD−WTREGEN en
    unidades FRED mixtas, el resultado queda en millones). Conversión /1e3
    para obtener miles de millones (billions).
    """
    if current_date not in netliq_series.index:
        return None
    current_val = netliq_series.loc[current_date]
    if pd.isna(current_val):
        return None

    date_13w_ago = current_date - pd.Timedelta(weeks=13)
    past_window = netliq_series.loc[
        date_13w_ago - pd.Timedelta(weeks=1) : date_13w_ago + pd.Timedelta(weeks=1)
    ].dropna()

    if past_window.empty:
        return None

    past_val = _nearest_val(past_window, date_13w_ago)
    delta_b = (current_val - past_val) / 1e3  # millones → billions

    if delta_b > 500:   return 25.0
    if delta_b > 100:   return 18.75
    if delta_b > -100:  return 12.5
    if delta_b > -500:  return 6.25
    return 0.0


# ── VolScore = min(nivel, term) (/20) ────────────────────────────────────────

def vix_level_score(vix: float | None) -> float | None:
    if vix is None or pd.isna(vix):
        return None
    if vix < 14:  return 20.0
    if vix < 18:  return 15.0
    if vix < 23:  return 10.0
    if vix < 30:  return 5.0
    return 0.0


def vix_term_score(vix9d: float | None, vix3m: float | None) -> float | None:
    if vix9d is None or vix3m is None or pd.isna(vix9d) or pd.isna(vix3m):
        return None
    if vix3m == 0:
        return None
    ratio = vix9d / vix3m
    if ratio < 0.85:  return 20.0
    if ratio < 0.95:  return 15.0
    if ratio < 1.05:  return 10.0
    if ratio < 1.15:  return 5.0
    return 0.0


def vol_score(vix: float | None, vix9d: float | None, vix3m: float | None) -> float | None:
    """
    Conservative: min(nivel, term).
    Fallback pre-2011: si VIX9D/VIX3M no disponibles, usa solo nivel.
    """
    level = vix_level_score(vix)
    if level is None:
        return None
    term = vix_term_score(vix9d, vix3m)
    if term is None:
        return level  # fallback válido pre-2011
    return min(level, term)


# ── Curva 10Y-3M con steepening penalty (/15) ────────────────────────────────

def curva_score(
    t10y3m_bps: float | None,
    t10y3m_series: pd.Series,
    current_date: pd.Timestamp,
) -> float | None:
    """
    t10y3m_bps y t10y3m_series deben estar en bps.
    El simulador convierte macro_daily['T10Y3M'] (en %) multiplicando ×100.
    """
    if t10y3m_bps is None or pd.isna(t10y3m_bps):
        return None

    if t10y3m_bps > 75:    base = 20.0
    elif t10y3m_bps > 25:  base = 15.0
    elif t10y3m_bps > -25: base = 10.0
    elif t10y3m_bps > -75: base = 5.0
    else:                  base = 0.0

    if t10y3m_bps < 0:
        date_13w_ago = current_date - pd.Timedelta(weeks=13)
        past_window = t10y3m_series.loc[
            date_13w_ago - pd.Timedelta(weeks=1) : date_13w_ago + pd.Timedelta(weeks=1)
        ].dropna()
        if not past_window.empty:
            past_val = _nearest_val(past_window, date_13w_ago)
            delta = t10y3m_bps - past_val
            if delta > 50:
                base = max(0.0, base - 5.0)

    return base * 0.75


# ── CFNAI (/15) ───────────────────────────────────────────────────────────────

def cfnai_score(cfnai_value: float | None) -> float | None:
    if cfnai_value is None or pd.isna(cfnai_value):
        return None
    if cfnai_value > 0.20:   return 15.0
    if cfnai_value > 0.00:   return 11.25
    if cfnai_value > -0.35:  return 7.5
    if cfnai_value > -0.70:  return 3.75
    return 0.0
