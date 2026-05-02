"""
Detector de régimen con histéresis direccional.

Regla de cambio:
  1. El score cruza la frontera del régimen actual en ≥5 puntos
     (medido direccionalmente: subida → score − cur.max; bajada → cur.min − score)
  2. Ese cruce persiste ≥2 semanas consecutivas

Nota: TERM_PREMIUM_EXTREME puede degradar el régimen 1 nivel según la metodología,
pero ese modificador se aplica en la capa de presentación/señales (Entregas 3-4),
no en este detector base.
"""
from __future__ import annotations
import pandas as pd

REGIMES: list[dict] = [
    {'name': 'Bull Pleno',   'min': 80.0,  'max': 100.0},
    {'name': 'Bull Maduro',  'min': 60.0,  'max':  79.999},
    {'name': 'Transición',   'min': 40.0,  'max':  59.999},
    {'name': 'Risk-OFF',     'min': 20.0,  'max':  39.999},
    {'name': 'Capitulación', 'min':  0.0,  'max':  19.999},
]


def detect_regime(score: float) -> str:
    for r in REGIMES:
        if r['min'] <= score <= r['max']:
            return r['name']
    return 'Capitulación'  # fallback defensivo


def make_regime_state() -> dict:
    return {
        'current_regime':   None,
        'regime_entered_at': None,
        'pending_regime':   None,
        'pending_streak':   0,
    }


def update_regime_state(
    score: float | None,
    state: dict,
    current_date: pd.Timestamp,
) -> dict:
    if score is None:
        return state

    detected = detect_regime(score)

    if state['current_regime'] is None:
        state['current_regime']    = detected
        state['regime_entered_at'] = current_date
        state['pending_regime']    = None
        state['pending_streak']    = 0
        return state

    if detected == state['current_regime']:
        state['pending_regime'] = None
        state['pending_streak'] = 0
        return state

    cur = next(r for r in REGIMES if r['name'] == state['current_regime'])
    if score > cur['max']:
        diff = score - cur['max']      # ascendente
    elif score < cur['min']:
        diff = cur['min'] - score      # descendente
    else:
        diff = 0.0

    if diff < 5.0:
        state['pending_regime'] = None
        state['pending_streak'] = 0
        return state

    if state['pending_regime'] == detected:
        state['pending_streak'] += 1
    else:
        state['pending_regime'] = detected
        state['pending_streak'] = 1

    if state['pending_streak'] >= 2:
        state['current_regime']    = detected
        state['regime_entered_at'] = current_date
        state['pending_regime']    = None
        state['pending_streak']    = 0

    return state
