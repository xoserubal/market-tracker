"""
4 flags globales con sus streaks.

Regla general de streak:
  - condición cumplida: streak += 1; si streak >= threshold → activo
  - condición NO cumplida (1 sola semana): streak = 0 Y activo = False

EMERGENCY_MODE es especial: activa inmediatamente (sin streak),
duración mínima 14 días desde activación.
"""
from __future__ import annotations
import pandas as pd


def make_flag_state() -> dict:
    return {'active': False, 'streak_weeks': 0}


def make_emergency_state() -> dict:
    return {'active': False, 'activated_at': None}


def _update_streak(condition_met: bool, flag_state: dict, threshold_weeks: int) -> dict:
    if condition_met:
        flag_state['streak_weeks'] += 1
        if flag_state['streak_weeks'] >= threshold_weeks:
            flag_state['active'] = True
    else:
        flag_state['streak_weeks'] = 0
        flag_state['active'] = False
    return flag_state


def check_credit_complacency(
    hy_bps: float | None,
    mode: str,
    flag_state: dict,
) -> dict:
    """HY < 275 bps × 8 semanas. Deshabilitado en Modo B."""
    if mode == 'B':
        flag_state['active'] = False
        flag_state['streak_weeks'] = 0
        return flag_state
    if hy_bps is None or pd.isna(hy_bps):
        flag_state['streak_weeks'] = 0
        flag_state['active'] = False
        return flag_state
    return _update_streak(hy_bps < 275, flag_state, threshold_weeks=8)


def check_inflation_overlay(
    t5yie_pct: float | None,
    flag_state: dict,
) -> dict:
    """T5YIE ≥ 2.8% × 4 semanas."""
    if t5yie_pct is None or pd.isna(t5yie_pct):
        flag_state['streak_weeks'] = 0
        flag_state['active'] = False
        return flag_state
    return _update_streak(t5yie_pct >= 2.8, flag_state, threshold_weeks=4)


def check_term_premium_extreme(
    threefytp10: float | None,
    flag_state: dict,
) -> dict:
    """THREEFYTP10 < −0.75 × 13 semanas."""
    if threefytp10 is None or pd.isna(threefytp10):
        flag_state['streak_weeks'] = 0
        flag_state['active'] = False
        return flag_state
    return _update_streak(threefytp10 < -0.75, flag_state, threshold_weeks=13)


def check_emergency_mode(
    vix: float | None,
    current_date: pd.Timestamp,
    flag_state: dict,
) -> dict:
    """
    VIX ≥ 35 activa inmediatamente (sin streak).
    Duración mínima 14 días; luego se desactiva si VIX < 35.
    """
    if flag_state['activated_at'] is not None:
        days_active = (current_date - flag_state['activated_at']).days
        if days_active < 14:
            return flag_state  # duración mínima, mantener activo
        if vix is None or pd.isna(vix) or vix < 35:
            flag_state['active'] = False
            flag_state['activated_at'] = None
            return flag_state
        return flag_state  # VIX sigue alto

    if vix is not None and not pd.isna(vix) and vix >= 35:
        flag_state['active'] = True
        flag_state['activated_at'] = current_date
    return flag_state
