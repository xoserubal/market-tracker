"""
Motor de simulación semanal del MacroScore.

Itera sobre las fechas de prices_weekly (viernes) y acumula estado persistente
de régimen y flags semana a semana.

NOTAS DE FUENTES DE DATOS (desviaciones vs brief original):
  - VIX/VIX9D/VIX3M: en prices_weekly (no en macro_daily)
  - T10Y3M: en macro_daily en %, se convierte ×100 a bps aquí
  - NetLiq: en macro_weekly en millones USD; conversión /1e3 en components.py
  - hy_bps: en hy_real (índice diario), se resamplea a viernes
"""
from __future__ import annotations
import pandas as pd

from .components import (
    hy_score, netliq_delta13w_score,
    vol_score, curva_score, cfnai_score,
)
from .score   import compute_macro_score
from .regime  import make_regime_state, update_regime_state
from .flags   import (
    make_flag_state, make_emergency_state,
    check_credit_complacency, check_inflation_overlay,
    check_term_premium_extreme, check_emergency_mode,
)
from .deltas  import compute_short_deltas


def _resample_to_friday(series: pd.Series) -> pd.Series:
    """Resamplea cualquier serie (diaria o irregular) a cierres de viernes."""
    return series.resample('W-FRI').last()


def _get(series: pd.Series | None, date: pd.Timestamp) -> float | None:
    if series is None:
        return None
    if date not in series.index:
        return None
    val = series.loc[date]
    return None if pd.isna(val) else float(val)


def simulate_history(data: dict, mode: str = 'A') -> pd.DataFrame:
    """
    data keys: 'prices_weekly', 'macro_daily', 'macro_weekly', 'hy_real'
    mode: 'A' | 'B'

    Returns DataFrame con índice date (viernes semanales).
    """
    prices_weekly = data['prices_weekly']
    macro_daily   = data['macro_daily']
    macro_weekly  = data['macro_weekly']
    hy_real       = data['hy_real']

    # ── Preparar series semanales (viernes) ──────────────────────────────────

    # VIX: ya semanal en prices_weekly
    vix_w   = prices_weekly['^VIX']
    vix9d_w = prices_weekly.get('^VIX9D')
    vix3m_w = prices_weekly.get('^VIX3M')

    # T10Y3M: diario en %, convertir a bps antes de usarlo
    t10y3m_pct_w = _resample_to_friday(macro_daily['T10Y3M'])
    t10y3m_bps_w = t10y3m_pct_w * 100.0  # % → bps

    # T5YIE y THREEFYTP10: diarios en %
    t5yie_w       = _resample_to_friday(macro_daily['T5YIE'])
    threefytp10_w = _resample_to_friday(macro_daily['THREEFYTP10'])

    # HY spread: diario, resamplear a viernes
    hy_w = _resample_to_friday(hy_real['hy_bps'])

    # NetLiq: semanal
    # CFNAI: mensual con forward-fill hasta última publicación disponible
    netliq_s = macro_weekly['NetLiq']
    cfnai_s  = macro_weekly['CFNAI'].ffill()

    # ── Estado inicial ────────────────────────────────────────────────────────
    state = {
        'regime': make_regime_state(),
        'flags': {
            'credit_complacency':   make_flag_state(),
            'inflation_overlay':    make_flag_state(),
            'term_premium_extreme': make_flag_state(),
            'emergency_mode':       make_emergency_state(),
        },
    }

    results = []
    for current_date in prices_weekly.index:

        # ── Valores raw del período ───────────────────────────────────────────
        hy           = _get(hy_w,           current_date)
        netliq       = _get(netliq_s,        current_date)
        vix          = _get(vix_w,           current_date)
        vix9d        = _get(vix9d_w,         current_date) if vix9d_w is not None else None
        vix3m        = _get(vix3m_w,         current_date) if vix3m_w is not None else None
        t10y3m_bps   = _get(t10y3m_bps_w,   current_date)
        t5yie        = _get(t5yie_w,         current_date)
        threefytp10  = _get(threefytp10_w,   current_date)
        cfnai        = _get(cfnai_s,         current_date)

        # ── Subcomponentes ────────────────────────────────────────────────────
        hy_pts     = hy_score(hy)
        netliq_pts = netliq_delta13w_score(netliq_s, current_date)
        vol_pts    = vol_score(vix, vix9d, vix3m)
        curva_pts  = curva_score(t10y3m_bps, t10y3m_bps_w, current_date)
        cfnai_pts  = cfnai_score(cfnai)

        # ── MacroScore con reescalado dinámico ────────────────────────────────
        components = {
            'hy':     hy_pts,
            'netliq': netliq_pts,
            'vol':    vol_pts,
            'curva':  curva_pts,
            'cfnai':  cfnai_pts,
        }
        score_result = compute_macro_score(components, mode=mode)

        # ── Régimen con histéresis ────────────────────────────────────────────
        state['regime'] = update_regime_state(
            score_result['score_scaled_100'], state['regime'], current_date
        )

        # ── Flags ─────────────────────────────────────────────────────────────
        state['flags']['credit_complacency'] = check_credit_complacency(
            hy, mode, state['flags']['credit_complacency']
        )
        state['flags']['inflation_overlay'] = check_inflation_overlay(
            t5yie, state['flags']['inflation_overlay']
        )
        state['flags']['term_premium_extreme'] = check_term_premium_extreme(
            threefytp10, state['flags']['term_premium_extreme']
        )
        state['flags']['emergency_mode'] = check_emergency_mode(
            vix, current_date, state['flags']['emergency_mode']
        )

        # ── Deltas cortos (para Entrega 5) ────────────────────────────────────
        hy_d      = compute_short_deltas(hy_w,           current_date, (2, 4))
        netliq_d  = compute_short_deltas(netliq_s,        current_date, (4, 8))
        curva_d   = compute_short_deltas(t10y3m_bps_w,   current_date, (2, 4))
        t5yie_d   = compute_short_deltas(t5yie_w,         current_date, (2, 4))
        vix_d     = compute_short_deltas(vix_w,           current_date, (2, 4))

        rs = state['regime']
        fl = state['flags']

        results.append({
            'date':  current_date,
            'mode':  mode,

            # Score
            'macro_score':         score_result['score_scaled_100'],
            'score_absolute':      score_result['score_absolute'],
            'score_max_possible':  score_result['score_max_possible'],
            'reliability':         score_result['reliability'],

            # Subcomponentes
            'hy_pts':    hy_pts,
            'netliq_pts': netliq_pts,
            'vol_pts':   vol_pts,
            'curva_pts': curva_pts,
            'cfnai_pts': cfnai_pts,
            'components_available': ','.join(score_result['components_available']),

            # Régimen
            'regime':         rs['current_regime'],
            'pending_regime': rs['pending_regime'],
            'pending_streak': rs['pending_streak'],

            # Flags
            'flag_credit_complacency':   fl['credit_complacency']['active'],
            'credit_complacency_streak': fl['credit_complacency']['streak_weeks'],
            'flag_inflation_overlay':    fl['inflation_overlay']['active'],
            'inflation_overlay_streak':  fl['inflation_overlay']['streak_weeks'],
            'flag_term_premium_extreme': fl['term_premium_extreme']['active'],
            'term_premium_streak':       fl['term_premium_extreme']['streak_weeks'],
            'flag_emergency_mode':       fl['emergency_mode']['active'],
            'emergency_activated_at':    fl['emergency_mode']['activated_at'],

            # Valores raw
            'hy_bps':       hy,
            'netliq_usd':   netliq,
            'vix':          vix,
            'vix9d':        vix9d,
            'vix3m':        vix3m,
            't10y3m_bps':   t10y3m_bps,
            't5yie_pct':    t5yie,
            'threefytp10':  threefytp10,
            'cfnai':        cfnai,

            # Deltas cortos
            'hy_d2w':      hy_d.get('d2w'),
            'hy_d4w':      hy_d.get('d4w'),
            'netliq_d4w':  netliq_d.get('d4w'),
            'netliq_d8w':  netliq_d.get('d8w'),
            'curva_d2w':   curva_d.get('d2w'),
            'curva_d4w':   curva_d.get('d4w'),
            't5yie_d2w':   t5yie_d.get('d2w'),
            't5yie_d4w':   t5yie_d.get('d4w'),
            'vix_d2w':     vix_d.get('d2w'),
            'vix_d4w':     vix_d.get('d4w'),
        })

    df = pd.DataFrame(results).set_index('date')
    return df
