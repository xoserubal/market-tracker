"""
Shared condition vocabulary and evaluator for user-defined Koncorde alerts
(entries in docs/data/bot_alerts.json with type="koncorde").

Centralized so the NL parser prompt (telegram_portfolio_bot.py) and the
evaluator (check_koncorde_alerts.py) can never drift on what a condition
means — same failure mode already fixed once for HARD_RULES, see
scripts/ai_shared.py and the "Koncorde Plus en el payload del modelo"
section of CLAUDE.md.
"""
from __future__ import annotations

VALID_TIMEFRAMES = ("d", "3d", "w")

TIMEFRAME_LABELS = {
    "d":  "diario",
    "3d": "3 días",
    "w":  "semanal",
}

# condition_id -> (human label ES, field suffix read off konc_{tf}_<suffix>, comparator)
# Kept deliberately small — same principle as the rest of the project's
# observational features: start narrow, extend only if it proves useful.
CONDITIONS: dict[str, str] = {
    "blue_positive":      "Blue >= 0 (línea azul en positivo)",
    "blue_negative":      "Blue < 0 (línea azul en negativo)",
    "blue_cross_up":      "Blue cruza de negativo a positivo en la última barra cerrada",
    "green_positive":     "Green >= 0 (línea verde en positivo)",
    "green_negative":     "Green < 0 (línea verde en negativo)",
    "state_accumulation": "Estado Koncorde = acumulación",
    "state_distribution": "Estado Koncorde = distribución",
}


def evaluate(ticker_data: dict, timeframe: str, condition: str) -> bool | None:
    """Evaluates one condition against a ticker's koncorde_data.json entry.

    Returns True/False, or None if the ticker has no data for this field
    (e.g. left the universe, or the timeframe hasn't warmed up yet) — a
    missing field is never treated as False, to avoid firing/silently
    discarding an alert on absent data.
    """
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(f"Unknown timeframe: {timeframe}")
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown condition: {condition}")

    prefix = f"konc_{timeframe}_"

    if condition == "blue_positive":
        v = ticker_data.get(prefix + "blue")
        return None if v is None else v >= 0
    if condition == "blue_negative":
        v = ticker_data.get(prefix + "blue")
        return None if v is None else v < 0
    if condition == "blue_cross_up":
        v = ticker_data.get(prefix + "blue_cross_up")
        return None if v is None else bool(v)
    if condition == "green_positive":
        v = ticker_data.get(prefix + "green")
        return None if v is None else v >= 0
    if condition == "green_negative":
        v = ticker_data.get(prefix + "green")
        return None if v is None else v < 0
    if condition == "state_accumulation":
        v = ticker_data.get(prefix + "accumulation_flag")
        return None if v is None else bool(v)
    if condition == "state_distribution":
        v = ticker_data.get(prefix + "distribution_flag")
        return None if v is None else bool(v)

    raise AssertionError("unreachable — condition validated above")


def describe(ticker: str, timeframe: str, condition: str) -> str:
    """Human-readable ES summary, used in bot confirmations and alert listings."""
    tf_label   = TIMEFRAME_LABELS.get(timeframe, timeframe)
    cond_label = CONDITIONS.get(condition, condition)
    return f"{ticker} — {cond_label} en {tf_label}"
