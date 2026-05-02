"""
Determinación de señales: COMPRA, ACUMULAR, VIGILAR, ROT. TEMPRANA, IGNORAR, ACUMULAR*.

Réplica de getSignal() en rotacion.html, incluyendo:
  - Umbral COMPRA: 7 por defecto, 8 si CREDIT_COMPLACENCY activo
  - Master Filter: SPY < SMA200 → degrada 1 nivel
    (excepción: ROT. TEMPRANA no se degrada)
  - EMERGENCY_MODE: suprime todo salvo ACUMULAR* para Risk-OFF fit + score≥6
  - ROT. TEMPRANA tiene prioridad si no hay fit convencional
"""

SIGNAL_COLORS = {
    'COMPRA':        {'color': '#1b5e20', 'bg': '#e8f5e9'},
    'ACUMULAR':      {'color': '#33691e', 'bg': '#f1f8e9'},
    'ACUMULAR*':     {'color': '#33691e', 'bg': '#f1f8e9'},
    'ROT. TEMPRANA': {'color': '#e65100', 'bg': '#fff3e0'},
    'VIGILAR':       {'color': '#888',    'bg': '#f5f5f5'},
}

_DOWNGRADE = {
    'COMPRA':   'ACUMULAR',
    'ACUMULAR': 'VIGILAR',
    'VIGILAR':  None,
}


def determine_signal(
    rot_score: float | None,
    fit: bool,
    is_early_rotation: bool,
    flag_credit_complacency: bool,
    flag_emergency: bool,
    spy_above_sma200: bool | None,
    er_validated_by_netliq: bool = False,
) -> tuple[str | None, str | None]:
    """
    Devuelve (signal_label, signal_note).

    signal_label: 'COMPRA' | 'ACUMULAR' | 'ACUMULAR*' |
                  'ROT. TEMPRANA' | 'VIGILAR' | None (ignorar)
    signal_note:  'emergencia' si aplica, None en otro caso

    Args:
        rot_score:               RotationScore 0-10 (None si no hay datos)
        fit:                     activo es líder en régimen actual
        is_early_rotation:       condiciones de ROT. TEMPRANA cumplidas
        flag_credit_complacency: CREDIT_COMPLACENCY activo
        flag_emergency:          EMERGENCY_MODE activo
        spy_above_sma200:        SPY > SMA200 (None si no disponible)
        er_validated_by_netliq:  la ROT. TEMPRANA fue validada vía NetLiq (no se degrada)
    """
    score = rot_score if rot_score is not None else 0.0

    # ── EMERGENCY_MODE ────────────────────────────────────────────────────────
    if flag_emergency:
        # Solo ACUMULAR* si fit Risk-OFF y score ≥ 6
        if fit and score >= 6:
            return ('ACUMULAR*', 'emergencia')
        return (None, None)

    # ── Umbral COMPRA ─────────────────────────────────────────────────────────
    buy_threshold = 8 if flag_credit_complacency else 7

    # ── Señal base ────────────────────────────────────────────────────────────
    if fit and score >= buy_threshold:
        level = 'COMPRA'
    elif fit and score >= 5:
        level = 'ACUMULAR'
    elif is_early_rotation:
        level = 'ROT. TEMPRANA'
    elif score >= 3:
        level = 'VIGILAR'
    else:
        level = None

    # ── Master Filter: SPY < SMA200 ───────────────────────────────────────────
    # ROT. TEMPRANA se exime si fue validada por NetLiq (excepción del protocolo)
    if spy_above_sma200 is False and level is not None:
        if level == 'ROT. TEMPRANA' and er_validated_by_netliq:
            pass  # no se degrada
        elif level != 'ROT. TEMPRANA':
            level = _DOWNGRADE.get(level)

    return (level, None)
