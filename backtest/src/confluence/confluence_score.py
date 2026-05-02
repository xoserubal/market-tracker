"""
Agregación de bloques A + B + persistencia → score 0-100.
"""


def compute_persistence_score(macro_tension_history_8w):
    """
    Cuenta semanas en las últimas 8 con macro_tension_scaled > 20.
    Score = count * 3, cap 25.
    """
    if not macro_tension_history_8w:
        return 0
    window = macro_tension_history_8w[-8:]
    count = sum(1 for v in window if v is not None and v > 20)
    return min(count * 3, 25)


def compute_confluence_score(macro_tension_40, sector_tension_35, persistence_25):
    """
    macro_tension_40  : 0-40 (already scaled)
    sector_tension_35 : 0-35
    persistence_25    : 0-25

    Returns float 0-100 or None if both tension blocks missing.
    """
    if macro_tension_40 is None and sector_tension_35 is None:
        return None

    a = macro_tension_40  if macro_tension_40  is not None else 0.0
    b = sector_tension_35 if sector_tension_35 is not None else 0.0
    p = persistence_25    if persistence_25    is not None else 0.0

    return round(a + b + p, 2)


def score_label(score):
    """Human-readable label for the confluence score."""
    if score is None:    return 'N/A'
    if score < 21:       return 'Normal'
    if score < 41:       return 'Cautela'
    if score < 61:       return 'Tension elevada'
    if score < 81:       return 'Alerta'
    return 'Alerta maxima'
