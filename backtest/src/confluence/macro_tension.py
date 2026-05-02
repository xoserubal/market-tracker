"""
Bloque A — Tensión macro por deltas cortos.
Todos los componentes devuelven None si los datos no están disponibles.
Reescalado dinámico: score / max_disponible * 40, SIN redistribuir pesos.
"""
import numpy as np

MAX_WEIGHTS = {
    'hy_accel':       10,
    'netliq_contract': 10,
    'curve_dynamics':   8,
    'vol_shift':        6,
    'inflation_shift':  6,
}
TOTAL_MAX = sum(MAX_WEIGHTS.values())  # 40


def _missing(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def hy_acceleration_score(hy_d2w, hy_d4w):
    """A1 — HY Spread Acceleration (bps). None pre-2023."""
    if _missing(hy_d2w) or _missing(hy_d4w):
        return None
    if hy_d2w > 40 and hy_d4w > 75:
        return 10
    if hy_d2w > 25 and hy_d4w > 50:
        return 7
    if hy_d2w > 15 or hy_d4w > 30:
        return 4
    if hy_d2w > 0 and hy_d4w > 0:
        return 1
    return 0


def netliq_contraction_score(netliq_d4w, netliq_d8w):
    """
    A2 — NetLiq Contraction. Units: millions USD.
    Thresholds: -100_000 = -$100B, -200_000 = -$200B, etc.
    None pre-2008-10.
    """
    if _missing(netliq_d4w) or _missing(netliq_d8w):
        return None
    if netliq_d4w < -200_000 and netliq_d8w < -400_000:
        return 10
    if netliq_d4w < -100_000 and netliq_d8w < -200_000:
        return 7
    if netliq_d4w < -50_000 or netliq_d8w < -100_000:
        return 4
    if netliq_d4w < 0 and netliq_d8w < 0:
        return 1
    return 0


def curve_dynamics_score(t10y3m_bps, curva_d2w, curva_d4w):
    """A3 — Curve Inversion Dynamics (all bps). Available from 2005."""
    if _missing(t10y3m_bps) or _missing(curva_d4w):
        return None
    if t10y3m_bps < -25 and curva_d4w < 0:
        return 8   # inversion deepening
    if t10y3m_bps < -50:
        return 6   # deep inversion, stable
    if t10y3m_bps < 0 and curva_d4w < -10:
        return 5   # shallow inversion deepening
    if -25 < t10y3m_bps < 25:
        return 3   # near inversion
    return 0


def vol_regime_shift_score(vix, vix_d2w, vix_d4w):
    """A4 — Volatility Regime Shift. Available from 2005."""
    if _missing(vix) or _missing(vix_d2w) or _missing(vix_d4w):
        return None
    if vix > 25 and vix_d4w > 8:
        return 6
    if vix > 20 and vix_d2w > 5:
        return 4
    if vix_d4w > 5:
        return 3
    return 0


def inflation_shift_score(t5yie_pct, t5yie_d2w, t5yie_d4w):
    """A5 — Inflation Expectations Deterioration. Available from 2005."""
    if _missing(t5yie_pct) or _missing(t5yie_d2w) or _missing(t5yie_d4w):
        return None
    if t5yie_pct > 3.0 and t5yie_d4w > 0.3:
        return 6   # runaway inflation
    if t5yie_pct < 1.5 and t5yie_d4w < -0.3:
        return 6   # deflationary collapse
    if abs(t5yie_d2w) > 0.2:
        return 3   # rapid shift in any direction
    return 0


def compute_macro_tension(row):
    """
    row: dict-like with macro columns.
    Returns dict:
      macro_tension_scaled  : float 0-40 (dynamic rescale), or None
      macro_tension_absolute: raw sum of available components
      macro_tension_max     : max possible given available components
      components            : {name: pts or None}
    """
    components = {
        'hy_accel':       hy_acceleration_score(
                              row.get('hy_d2w'), row.get('hy_d4w')),
        'netliq_contract': netliq_contraction_score(
                              row.get('netliq_d4w'), row.get('netliq_d8w')),
        'curve_dynamics':  curve_dynamics_score(
                              row.get('t10y3m_bps'),
                              row.get('curva_d2w'), row.get('curva_d4w')),
        'vol_shift':       vol_regime_shift_score(
                              row.get('vix'), row.get('vix_d2w'),
                              row.get('vix_d4w')),
        'inflation_shift': inflation_shift_score(
                              row.get('t5yie_pct'), row.get('t5yie_d2w'),
                              row.get('t5yie_d4w')),
    }

    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return {
            'macro_tension_scaled':   None,
            'macro_tension_absolute': None,
            'macro_tension_max':      None,
            'components':             components,
        }

    abs_score   = sum(available.values())
    max_possible = sum(MAX_WEIGHTS[k] for k in available)
    scaled_40   = abs_score * (40.0 / max_possible)

    return {
        'macro_tension_scaled':   scaled_40,
        'macro_tension_absolute': abs_score,
        'macro_tension_max':      max_possible,
        'components':             components,
    }
