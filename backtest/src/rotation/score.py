"""
RotationScore de 10 puntos (3 bloques).

Réplica de calcRotScore() en rotacion.html:

  Bloque A — Momentum/RS (4 pts):
    rs13w > 2.0% vs SPY → 2 pts
    rs4w  > 1.0% vs SPY → 1 pt
    close > SMA200      → 1 pt

  Bloque B — Flujo/Volumen (3 pts):
    CMF(20) > 0.05                → 1 pt
    OBV > SMA50(OBV)             → 1 pt
    vol4w / vol12w > 1.10        → 1 pt

  Bloque C — Técnico/anti-extensión (3 pts):
    MACD histograma > 0          → 1 pt
    RSI(14) entre 40 y 70        → 1 pt
    close > SMA20 AND
      (close - SMA20) / ATR14 < 1.5 → 1 pt

NaN en cualquier input → 0 pts en ese criterio (no rompe).
"""

import numpy as np
import pandas as pd


def _get(row: pd.Series, col: str):
    """Devuelve None si el valor es NaN/None."""
    if col not in row.index:
        return None
    val = row[col]
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return val


def rotation_score(
    ticker_row: pd.Series,
    spy_row: pd.Series,
) -> dict:
    """
    Calcula el RotationScore para un ticker en una fecha.

    Args:
        ticker_row: fila de indicators DataFrame para el ticker
        spy_row:    fila de indicators DataFrame para SPY

    Returns:
        {
          'total':    float (0-10),
          'blockA':   float (0-4),
          'blockB':   float (0-3),
          'blockC':   float (0-3),
          'components': {
              'rs_13w_pts', 'rs_4w_pts', 'trend_abs_pts',
              'cmf_pts', 'obv_pts', 'vol_rel_pts',
              'macd_pts', 'rsi_pts', 'no_ext_pts'
          }
        }
        Si datos insuficientes → total=None
    """
    t = ticker_row
    s = spy_row

    comp = {}

    # ── Bloque A: Momentum/RS (4 pts) ────────────────────────────────────────
    t_13w = _get(t, 'ret_13w')
    s_13w = _get(s, 'ret_13w')
    if t_13w is not None and s_13w is not None:
        comp['rs_13w_pts'] = 2.0 if (t_13w - s_13w) > 2.0 else 0.0
    else:
        comp['rs_13w_pts'] = 0.0

    t_4w = _get(t, 'ret_4w')
    s_4w = _get(s, 'ret_4w')
    if t_4w is not None and s_4w is not None:
        comp['rs_4w_pts'] = 1.0 if (t_4w - s_4w) > 1.0 else 0.0
    else:
        comp['rs_4w_pts'] = 0.0

    close  = _get(t, 'close')
    sma200 = _get(t, 'sma200')
    comp['trend_abs_pts'] = (
        1.0 if (close is not None and sma200 is not None and close > sma200) else 0.0
    )

    # ── Bloque B: Flujo/Volumen (3 pts) ──────────────────────────────────────
    cmf20 = _get(t, 'cmf20')
    comp['cmf_pts'] = (1.0 if cmf20 is not None and cmf20 > 0.05 else 0.0)

    obv_val  = _get(t, 'obv')
    obv_sma  = _get(t, 'obv_sma50')
    comp['obv_pts'] = (
        1.0 if (obv_val is not None and obv_sma is not None and obv_val > obv_sma) else 0.0
    )

    vol4w  = _get(t, 'vol4w')
    vol12w = _get(t, 'vol12w')
    comp['vol_rel_pts'] = (
        1.0 if (vol4w is not None and vol12w is not None
                and vol12w > 0.0 and (vol4w / vol12w) > 1.10) else 0.0
    )

    # ── Bloque C: Técnico/anti-extensión (3 pts) ─────────────────────────────
    macd_h = _get(t, 'macd_hist')
    comp['macd_pts'] = (1.0 if macd_h is not None and macd_h > 0.0 else 0.0)

    rsi14 = _get(t, 'rsi14')
    comp['rsi_pts'] = (
        1.0 if rsi14 is not None and 40.0 <= rsi14 <= 70.0 else 0.0
    )

    sma20 = _get(t, 'sma20')
    atr14 = _get(t, 'atr14')
    if close is not None and sma20 is not None and atr14 is not None and atr14 > 0.0:
        above_sma20 = close > sma20
        not_extended = (close - sma20) / atr14 < 1.5
        comp['no_ext_pts'] = 1.0 if (above_sma20 and not_extended) else 0.0
    else:
        comp['no_ext_pts'] = 0.0

    block_a = comp['rs_13w_pts'] + comp['rs_4w_pts'] + comp['trend_abs_pts']
    block_b = comp['cmf_pts']    + comp['obv_pts']   + comp['vol_rel_pts']
    block_c = comp['macd_pts']   + comp['rsi_pts']   + comp['no_ext_pts']
    total   = block_a + block_b + block_c

    return {
        'total':      total,
        'blockA':     block_a,
        'blockB':     block_b,
        'blockC':     block_c,
        'components': comp,
    }


def score_to_stars(score: float | None) -> int:
    if score is None:
        return 1
    if score >= 9:
        return 5
    if score >= 7:
        return 4
    if score >= 5:
        return 3
    if score >= 3:
        return 2
    return 1
