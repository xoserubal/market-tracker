"""
Bloque B — Degradación de cluster health sectorial.
La función principal recibe dicts pre-extraídos para fecha actual y 4w antes.
Reescalado dinámico a 35 pts, igual que Bloque A.
"""
import numpy as np

MAX_WEIGHTS_B = {
    'cyclical_deteri':   12,
    'defensive_strength': 10,
    'cyc_def_divergence':  8,
    'spy_internal_div':    5,
}
TOTAL_MAX_B = sum(MAX_WEIGHTS_B.values())  # 35


def _missing(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def _cluster_rot_pct(cluster_dict):
    """Extract (avg_rotation_score, pct_ret_4w_positive_vs_spy) from cluster dict."""
    if cluster_dict is None:
        return None, None
    rot = cluster_dict.get('avg_rotation_score')
    pct = cluster_dict.get('pct_ret_4w_positive_vs_spy')
    return (None if _missing(rot) else rot), (None if _missing(pct) else pct)


def cyclical_deterioration_score(growth_now, growth_4w, valcyc_now, valcyc_4w):
    """
    B1 — Cyclical Deterioration (12 pts).
    growth_now / valcyc_now: dict {avg_rotation_score, pct_ret_4w_positive_vs_spy, ...}
    growth_4w / valcyc_4w: same, 4 weeks prior.

    pct_ret_4w_positive_vs_spy is in [0,1] range, so -25pp = -0.25.
    """
    def cluster_level(now, ago):
        if now is None or ago is None:
            return None
        rot_n, pct_n = _cluster_rot_pct(now)
        rot_a, pct_a = _cluster_rot_pct(ago)
        if rot_n is None or rot_a is None:
            return None
        rot_delta = rot_n - rot_a
        pct_delta = (pct_n - pct_a) if (pct_n is not None and pct_a is not None) else None

        if rot_delta < -1.5 and pct_delta is not None and pct_delta < -0.25:
            return 'strong'
        if rot_delta < -0.5:
            return 'mild'
        return 'none'

    g_lvl = cluster_level(growth_now, growth_4w)
    v_lvl = cluster_level(valcyc_now, valcyc_4w)

    levels = [l for l in [g_lvl, v_lvl] if l is not None]
    if not levels:
        return None

    n_strong = sum(1 for l in levels if l == 'strong')
    n_mild   = sum(1 for l in levels if l == 'mild')
    n_valid  = len(levels)

    if n_valid == 2:
        if n_strong == 2: return 12
        if n_strong == 1: return 8
        if n_mild == 2:   return 5
        if n_mild == 1:   return 2
        return 0
    # n_valid == 1
    if n_strong == 1: return 8
    if n_mild == 1:   return 2
    return 0


def defensive_strengthening_score(defensive_now, defensive_4w,
                                   duration_now, duration_4w):
    """
    B2 — Defensive Strengthening (10 pts).
    Measures increase in avg_rotation_score for defensive clusters.
    """
    def rot_delta(now, ago):
        if now is None or ago is None:
            return None
        rn = now.get('avg_rotation_score')
        ra = ago.get('avg_rotation_score')
        if _missing(rn) or _missing(ra):
            return None
        return rn - ra

    d_delta = rot_delta(defensive_now, defensive_4w)
    dur_delta = rot_delta(duration_now, duration_4w)

    valid = {k: v for k, v in [('def', d_delta), ('dur', dur_delta)] if v is not None}
    if not valid:
        return None

    n_above_1 = sum(1 for v in valid.values() if v > 1.0)
    n_above_03 = sum(1 for v in valid.values() if v > 0.3)

    if len(valid) == 2:
        if n_above_1 == 2: return 10
        if n_above_1 == 1: return 6
        if n_above_03 >= 1: return 3
        return 0
    # 1 valid cluster
    if n_above_1 == 1: return 6
    if n_above_03 == 1: return 3
    return 0


def divergence_score(cyclical_avg_score, defensive_avg_score):
    """
    B3 — Cyclical-Defensive Divergence (8 pts).
    Uses current average rotation scores directly (no delta).
    """
    if _missing(cyclical_avg_score) or _missing(defensive_avg_score):
        return None
    gap = defensive_avg_score - cyclical_avg_score
    if gap > 3.0: return 8
    if gap > 2.0: return 5
    if gap > 1.0: return 3
    return 0


def spy_internal_divergence_score(spy_above_sma200, cyclical_pct_outperforming,
                                   valcyc_pct_outperforming):
    """
    B4 — SPY Internal Divergence (5 pts).
    Detects when SPY is in uptrend but cyclicals are underperforming.
    pct values in [0,1].
    """
    if not spy_above_sma200:
        return 0   # SPY already broken — no "hidden divergence"
    if _missing(cyclical_pct_outperforming) or _missing(valcyc_pct_outperforming):
        return None
    avg_cyc = (cyclical_pct_outperforming + valcyc_pct_outperforming) / 2
    if avg_cyc < 0.30: return 5
    if avg_cyc < 0.40: return 3
    return 0


def compute_sector_tension(cluster_now, cluster_4w_ago, spy_above_sma200):
    """
    cluster_now / cluster_4w_ago: dict {cluster_name: {metric: value}}
    spy_above_sma200: bool

    Returns dict:
      sector_tension_scaled   : float 0-35 or None
      sector_tension_absolute : raw sum
      sector_tension_max      : max possible given available components
      components              : {name: pts or None}
    """
    g_now  = cluster_now.get('Growth')
    g_4w   = cluster_4w_ago.get('Growth')
    v_now  = cluster_now.get('Value/Cyclical')
    v_4w   = cluster_4w_ago.get('Value/Cyclical')
    d_now  = cluster_now.get('Defensive')
    d_4w   = cluster_4w_ago.get('Defensive')
    dur_now  = cluster_now.get('Duration')
    dur_4w   = cluster_4w_ago.get('Duration')

    # Average cyclical score for B3 (Growth + Value/Cyclical)
    rot_cyc = []
    for c in [g_now, v_now]:
        if c is not None:
            r = c.get('avg_rotation_score')
            if not _missing(r):
                rot_cyc.append(r)
    cyc_avg = float(np.mean(rot_cyc)) if rot_cyc else None

    rot_def = []
    for c in [d_now, dur_now]:
        if c is not None:
            r = c.get('avg_rotation_score')
            if not _missing(r):
                rot_def.append(r)
    def_avg = float(np.mean(rot_def)) if rot_def else None

    # pct_ret_4w for B4
    g_pct  = g_now.get('pct_ret_4w_positive_vs_spy') if g_now else None
    v_pct  = v_now.get('pct_ret_4w_positive_vs_spy') if v_now else None
    g_pct  = None if _missing(g_pct) else g_pct
    v_pct  = None if _missing(v_pct) else v_pct

    components = {
        'cyclical_deteri':   cyclical_deterioration_score(g_now, g_4w, v_now, v_4w),
        'defensive_strength': defensive_strengthening_score(d_now, d_4w, dur_now, dur_4w),
        'cyc_def_divergence': divergence_score(cyc_avg, def_avg),
        'spy_internal_div':   spy_internal_divergence_score(
                                  spy_above_sma200, g_pct, v_pct),
    }

    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return {
            'sector_tension_scaled':   None,
            'sector_tension_absolute': None,
            'sector_tension_max':      None,
            'components':              components,
        }

    abs_score    = sum(available.values())
    max_possible = sum(MAX_WEIGHTS_B[k] for k in available)
    scaled_35    = abs_score * (35.0 / max_possible)

    return {
        'sector_tension_scaled':   scaled_35,
        'sector_tension_absolute': abs_score,
        'sector_tension_max':      max_possible,
        'components':              components,
    }
