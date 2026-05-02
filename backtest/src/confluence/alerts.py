"""
Alertas binarias: ALERTA ESTRUCTURAL y ALERTA TÁCTICA.
Estado persistido en un dict mutable que el simulador mantiene.
"""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


def make_alert_state():
    return {
        'structural_active':          False,
        'structural_activated_at':    None,
        'structural_pending_weeks':   0,
        'tactical_active':            False,
        'tactical_activated_at':      None,
        'tactical_pending_weeks':     0,
        'deactivation_pending_weeks': 0,
    }


def _structural_conditions_met(confluence, macro_scaled, sector_scaled, persistence):
    return (
        confluence is not None and confluence >= 55
        and macro_scaled  is not None and macro_scaled  >= 20
        and sector_scaled is not None and sector_scaled >= 15
        and persistence >= 12
    )


def _tactical_conditions_met(confluence, macro_scaled, sector_scaled):
    return (
        sector_scaled is not None and sector_scaled >= 20
        and (macro_scaled is None or macro_scaled < 15)
    )


def update_alerts(confluence, macro_scaled, sector_scaled, persistence,
                  state, current_date):
    """
    Updates alert_state in-place.

    Returns dict:
      structural_just_activated : bool
      structural_just_deactivated: bool
      tactical_just_activated   : bool
      tactical_just_deactivated : bool
    """
    result = {
        'structural_just_activated':    False,
        'structural_just_deactivated':  False,
        'tactical_just_activated':      False,
        'tactical_just_deactivated':    False,
    }

    struct_cond = _structural_conditions_met(
        confluence, macro_scaled, sector_scaled, persistence)
    tactic_cond = _tactical_conditions_met(
        confluence, macro_scaled, sector_scaled)

    # ---- Structural alert ----
    if not state['structural_active']:
        if struct_cond:
            state['structural_pending_weeks'] += 1
            if state['structural_pending_weeks'] >= 2:
                state['structural_active'] = True
                state['structural_activated_at'] = current_date
                result['structural_just_activated'] = True
        else:
            state['structural_pending_weeks'] = 0
    else:
        if not struct_cond:
            state['structural_pending_weeks'] = 0  # reset pending for re-entry

    # ---- Tactical alert (only when structural is NOT active) ----
    if not state['structural_active']:
        if tactic_cond:
            state['tactical_pending_weeks'] += 1
            if state['tactical_pending_weeks'] >= 2:
                if not state['tactical_active']:
                    state['tactical_active'] = True
                    state['tactical_activated_at'] = current_date
                    result['tactical_just_activated'] = True
        else:
            state['tactical_pending_weeks'] = 0
    else:
        # Structural supersedes tactical
        if state['tactical_active']:
            state['tactical_active'] = False
            state['tactical_activated_at'] = None
            result['tactical_just_deactivated'] = True
        state['tactical_pending_weeks'] = 0

    # ---- Deactivation (applies to whichever is active) ----
    # Deactivate if confluence < 35 for 2 consecutive weeks.
    # Reset timer on same tick as an activation to avoid self-cancellation.
    if result['structural_just_activated'] or result['tactical_just_activated']:
        state['deactivation_pending_weeks'] = 0

    if confluence is not None and confluence < 35:
        state['deactivation_pending_weeks'] += 1
        if state['deactivation_pending_weeks'] >= 2:
            if state['structural_active']:
                state['structural_active'] = False
                state['structural_activated_at'] = None
                state['structural_pending_weeks'] = 0
                result['structural_just_deactivated'] = True
            if state['tactical_active']:
                state['tactical_active'] = False
                state['tactical_activated_at'] = None
                state['tactical_pending_weeks'] = 0
                result['tactical_just_deactivated'] = True
    else:
        state['deactivation_pending_weeks'] = 0

    return result
