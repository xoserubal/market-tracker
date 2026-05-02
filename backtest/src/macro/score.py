"""
Agregación del MacroScore con reescalado dinámico.

Modo A: usa todos los componentes disponibles (HY desde 2023).
Modo B: fuerza HY=None siempre (serie completa 2005-hoy sobre 75 pts).

Los umbrales de régimen (80/60/40/20) se aplican SIEMPRE sobre score_scaled_100,
nunca sobre score_absolute.
"""
from __future__ import annotations

MAX_WEIGHTS: dict[str, float] = {
    'hy':     25.0,
    'netliq': 25.0,
    'vol':    20.0,
    'curva':  15.0,
    'cfnai':  15.0,
}


def compute_macro_score(components: dict, mode: str = 'A') -> dict:
    """
    components: {'hy': float|None, 'netliq': ..., 'vol': ..., 'curva': ..., 'cfnai': ...}
    mode: 'A' (completo) | 'B' (ignora HY siempre)

    Returns dict con:
      score_absolute, score_max_possible, score_scaled_100,
      components_available (list), components_missing (list), reliability (0-1)
    """
    if mode == 'B':
        components = {**components, 'hy': None}

    available = {k: v for k, v in components.items() if v is not None}
    missing   = [k for k, v in components.items() if v is None]

    if not available:
        return {
            'score_absolute':      None,
            'score_max_possible':  0.0,
            'score_scaled_100':    None,
            'components_available': [],
            'components_missing':   missing,
            'reliability':          0.0,
        }

    score_abs   = sum(available.values())
    max_possible = sum(MAX_WEIGHTS[k] for k in available)
    score_scaled = score_abs * (100.0 / max_possible)
    reliability  = max_possible / 100.0

    return {
        'score_absolute':       score_abs,
        'score_max_possible':   max_possible,
        'score_scaled_100':     score_scaled,
        'components_available': list(available.keys()),
        'components_missing':   missing,
        'reliability':          reliability,
    }
