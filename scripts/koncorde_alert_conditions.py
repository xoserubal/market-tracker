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
    # ── Dirección / giro de la "flecha" de cada línea (2026-08-31) ─────────
    # La flecha que muestra el mini-panel de portfolio.html sale de
    # konc_{tf}_{line}_delta1 (cambio de la última barra cerrada vs la
    # anterior). Se cubren las 3 líneas — blue, green y trend (la
    # "marrón/roja", lo que el usuario llama "global") — en los 3
    # timeframes. Dos condiciones de nivel (la flecha apunta arriba/abajo
    # ahora) + dos de evento (la flecha acaba de girar en la última barra).
    "blue_rising":        "Flecha azul hacia arriba (sube vs la barra anterior)",
    "blue_falling":       "Flecha azul hacia abajo (baja vs la barra anterior)",
    "blue_turns_up":      "La flecha azul gira al alza en la última barra cerrada (venía plana/bajando)",
    "blue_turns_down":    "La flecha azul gira a la baja en la última barra cerrada (venía plana/subiendo)",
    "green_rising":       "Flecha verde hacia arriba (sube vs la barra anterior)",
    "green_falling":      "Flecha verde hacia abajo (baja vs la barra anterior)",
    "green_turns_up":     "La flecha verde gira al alza en la última barra cerrada (venía plana/bajando)",
    "green_turns_down":   "La flecha verde gira a la baja en la última barra cerrada (venía plana/subiendo)",
    "trend_rising":       "Flecha de tendencia (marrón/roja) hacia arriba (sube vs la barra anterior)",
    "trend_falling":      "Flecha de tendencia (marrón/roja) hacia abajo (baja vs la barra anterior)",
    "trend_turns_up":     "La flecha de tendencia (marrón/roja) gira al alza en la última barra cerrada",
    "trend_turns_down":   "La flecha de tendencia (marrón/roja) gira a la baja en la última barra cerrada",
}

# Set of the arrow-direction conditions above, resolved to (line, kind) by
# splitting on the first "_". Kept separate so evaluate() can dispatch them
# with one branch instead of 12.
_ARROW_CONDITIONS = frozenset(
    f"{line}_{kind}"
    for line in ("blue", "green", "trend")
    for kind in ("rising", "falling", "turns_up", "turns_down")
)


def _arrow_eval(ticker_data: dict, prefix: str, line: str, kind: str) -> bool | None:
    """Direction / turn of one Koncorde line's per-bar change (the "flecha"
    the portfolio.html mini panel draws from konc_{tf}_{line}_delta1).

    `rising`/`falling` read konc_{tf}_{line}_delta1 directly. `turns_up`/
    `turns_down` also need the *previous* bar's delta, taken from
    konc_{tf}_{line}_last5 (oldest->newest, real per-bar values). Missing or
    too-short data -> None, never False — same principle as evaluate()."""
    if kind in ("rising", "falling"):
        d1 = ticker_data.get(f"{prefix}{line}_delta1")
        if d1 is None:
            return None
        return d1 > 0 if kind == "rising" else d1 < 0

    series = ticker_data.get(f"{prefix}{line}_last5") or []
    if len(series) < 3 or any(v is None for v in series[-3:]):
        return None
    a, b, c = series[-3], series[-2], series[-1]
    cur_delta, prev_delta = c - b, b - a
    if kind == "turns_up":
        return cur_delta > 0 and prev_delta <= 0
    return cur_delta < 0 and prev_delta >= 0  # turns_down


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
    if condition in _ARROW_CONDITIONS:
        line, kind = condition.split("_", 1)
        return _arrow_eval(ticker_data, prefix, line, kind)

    raise AssertionError("unreachable — condition validated above")


def describe(ticker: str, timeframe: str, condition: str) -> str:
    """Human-readable ES summary, used in bot confirmations and alert listings."""
    tf_label   = TIMEFRAME_LABELS.get(timeframe, timeframe)
    cond_label = CONDITIONS.get(condition, condition)
    return f"{ticker} — {cond_label} en {tf_label}"


# ── Generalization: composite multi-type conditions (2026-08-26) ───────────
# Extends the vocabulary above from "1 Koncorde condition on 1 ticker" to
# "N conditions of possibly-different types, all required at once (AND)" —
# for user-composed theses ("situaciones especiales") from the web UI, e.g.
# the ADS.DE case: Flow crosses positive + ADS/FEZ ratio improving + Koncorde
# D -> accumulation, all simultaneously. Deliberately generalizes the existing
# single-condition system instead of building a parallel one (see
# wiki/PREREGISTRO... — no, see the plan discussion: user explicitly asked
# for "un único sistema de alertas, de las más simples a las más complejas").
#
# evaluate()/describe()/CONDITIONS/VALID_TIMEFRAMES/TIMEFRAME_LABELS above are
# UNCHANGED — telegram_portfolio_bot.py and check_koncorde_alerts.py keep
# importing them as-is. Everything below is additive.

FLOW_OPS: dict[str, str] = {
    "cross_positive": "Flow Score cruza de negativo a positivo (sesión anterior -> hoy)",
    "improving":      "Flow Score mejora respecto a la sesión anterior",
}

RATIO_OPS: dict[str, str] = {
    "improving": "El ratio mejora (por encima de su media móvil reciente)",
}

PRICE_OPS: dict[str, str] = {
    "above": "Precio por encima de un umbral",
    "below": "Precio por debajo de un umbral",
}


def get_conditions(row: dict) -> list[dict]:
    """Returns the `conditions` list for an alert row, upgrading old-format
    rows (flat ticker/timeframe/condition, from /kalert before this change)
    into the new list-of-typed-conditions shape on the fly. Never mutates or
    rewrites the row on disk — this is a read-time compatibility shim, not a
    migration, so the ~2 alerts already active as of 2026-08-26 (IRS, GGAL)
    keep working without anyone touching docs/data/koncorde_bot_alerts.json.
    """
    if "conditions" in row:
        return row["conditions"]
    return [{"type": "koncorde", "timeframe": row["timeframe"], "condition": row["condition"]}]


def evaluate_flow(rows_for_ticker: list[dict], op: str) -> bool | None:
    """Evaluates one Flow Score condition from portfolio_daily_snapshot.jsonl
    rows for a single ticker (any order; only the two most recent by date are
    used). Returns None if fewer than 2 sessions of history exist yet, or if
    flowScore is null in either of the two most recent rows (computeFlowScore
    can return null — see shared/flow-score.js) — same "missing data is never
    False" principle as evaluate() above.
    """
    if op not in FLOW_OPS:
        raise ValueError(f"Unknown flow op: {op}")
    rows = sorted((r for r in rows_for_ticker if r.get("date")), key=lambda r: r["date"])
    if len(rows) < 2:
        return None
    prev_score, cur_score = rows[-2].get("flowScore"), rows[-1].get("flowScore")
    if prev_score is None or cur_score is None:
        return None
    if op == "cross_positive":
        return prev_score < 0 and cur_score >= 0
    if op == "improving":
        return cur_score > prev_score
    raise AssertionError("unreachable — op validated above")


def evaluate_ratio(trend: dict | None, op: str) -> bool | None:
    """Evaluates one ratio condition from a scripts/ratio_signal.py trend dict.
    `trend` is None if the ratio couldn't be fetched/computed that run (missing
    data, never treated as False)."""
    if op not in RATIO_OPS:
        raise ValueError(f"Unknown ratio op: {op}")
    if trend is None:
        return None
    if op == "improving":
        return trend.get("improving")
    raise AssertionError("unreachable — op validated above")


def evaluate_price(current_price: float | None, op: str, threshold: float) -> bool | None:
    """Evaluates one price-threshold condition. `current_price` is None if the
    live fetch failed that run (scripts/price_signal.py) — missing data is
    never treated as False, same principle as every other evaluator here."""
    if op not in PRICE_OPS:
        raise ValueError(f"Unknown price op: {op}")
    if current_price is None:
        return None
    if op == "above":
        return current_price > threshold
    if op == "below":
        return current_price < threshold
    raise AssertionError("unreachable — op validated above")


def evaluate_single_condition(condition: dict, ctx: dict) -> bool | None:
    """Dispatches one condition dict (from get_conditions()) to the right
    evaluator, using pre-fetched data supplied in `ctx`:
      ctx["koncorde_ticker_data"] — this ticker's koncorde_data.json entry
      ctx["flow_rows"]            — this ticker's portfolio_daily_snapshot rows
      ctx["ratio_trends"]         — {ratio_key: trend_dict} for this alert's ratio_pairs
      ctx["current_price"]        — this ticker's live price (scripts/price_signal.py), or None
    Never fetches anything itself — callers own all I/O, same separation of
    concerns evaluate() already has (it takes ticker_data, doesn't read files).
    """
    ctype = condition.get("type", "koncorde")  # legacy rows have no "type" key at all
    if ctype == "koncorde":
        ticker_data = ctx.get("koncorde_ticker_data")
        if ticker_data is None:
            return None
        return evaluate(ticker_data, condition["timeframe"], condition["condition"])
    if ctype == "flow":
        return evaluate_flow(ctx.get("flow_rows") or [], condition["op"])
    if ctype == "ratio":
        ratio_trends = ctx.get("ratio_trends") or {}
        return evaluate_ratio(ratio_trends.get(condition["ratio_key"]), condition["op"])
    if ctype == "price":
        return evaluate_price(ctx.get("current_price"), condition["op"], condition["threshold"])
    raise ValueError(f"Unknown condition type: {ctype}")


def evaluate_conditions(conditions: list[dict], ctx: dict) -> bool | None:
    """AND over all conditions. Returns:
      True  — every condition evaluated True (fire the alert)
      False — at least one condition evaluated False (definitively not yet — a
              single-condition legacy alert behaves exactly as evaluate() did)
      None  — no condition is False, but at least one is still unknown/missing
              data (keep pending, same as before — never fire, never discard)
    """
    results = [evaluate_single_condition(c, ctx) for c in conditions]
    if any(r is False for r in results):
        return False
    if any(r is None for r in results):
        return None
    return True


def describe_conditions(ticker: str, conditions: list[dict]) -> str:
    """Human-readable ES summary of a (possibly multi-condition) alert."""
    parts = []
    for c in conditions:
        ctype = c.get("type", "koncorde")
        if ctype == "koncorde":
            parts.append(f"{CONDITIONS.get(c['condition'], c['condition'])} en {TIMEFRAME_LABELS.get(c['timeframe'], c['timeframe'])}")
        elif ctype == "flow":
            parts.append(FLOW_OPS.get(c["op"], c["op"]))
        elif ctype == "ratio":
            parts.append(f"{c.get('ratio_key', '?')}: {RATIO_OPS.get(c['op'], c['op'])}")
        elif ctype == "price":
            verb = "por encima de" if c.get("op") == "above" else "por debajo de"
            parts.append(f"Precio {verb} {c.get('threshold')}")
        else:
            parts.append(f"[{ctype}?]")
    return f"{ticker} — " + " Y ".join(parts)
