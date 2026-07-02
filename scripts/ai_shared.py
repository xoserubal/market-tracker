"""
Shared constants between paper_trading.py (production selection pipeline) and
build_eval_bundle.py (external evaluator bundle).

Both files used to keep their own copy of HARD_RULES and _compact_candidate()
and drifted apart (build_eval_bundle.py ended up with 8 of 15 rules, missing
pcs_components and the Koncorde fields — see CLAUDE.md history). Import from
here instead of copying, so a future change to either only needs to happen once.
"""
from __future__ import annotations

HARD_RULES = [
    "Only SELECT tickers present in the candidates list.",
    "Only SELECT tickers with eligible=true.",
    "Do not SELECT futures, commodities, or macro indices directly.",
    "If a signal comes from a commodity/macro theme, SELECT the related stock or ETF.",
    "Do not fill portfolios with mediocre picks — empty selected list is valid.",
    "Return valid JSON only. No markdown, no explanation, no extra text.",
    "Do not invent data not present in the payload. If prev_snapshot_available=false, do not speculate on PCS or score changes between weeks.",
    "With strong contradictions, use WATCH or REJECT, not SELECT.",
    "Every selected item must have: portfolio, signal_type, confidence, reason_short (≥20 chars), reason_full (≥100 chars), comparative_edge (≥30 chars, must name at least one peer candidate and explain why it ranked lower).",
    "Every rejected item must have: reason and a valid rejection_category.",
    "Every candidate with pcs >= 62 that you do not SELECT must appear in EXACTLY ONE of watch or rejected, never both. A ticker in two lists is a hard rule violation — commit to one classification.",
    "Do not SELECT a ticker already present in active_picks_relevant — it is already an open position. Mention it in decision_summary if still relevant, but do not add it to selected.",
    "For HIGH_CONVICTION and CONFIRMED_FLOW_LEADERS portfolios, do not REJECT based primarily on dems or spike_flag when weekly metrics (ret_4w_vs_spy, ret_13w_vs_spy, streak_weeks) are strong. Use WATCH instead.",
    "Review ALL tickers in active_picks_relevant and include each one in open_picks_review. Use action=EXIT if: (a) current_pcs < pcs_min_entry AND current_streak_weeks <= 1, OR (b) current_rot_score <= 2, OR (c) current_pcs < 62 (absolute floor — below the minimum entry threshold of any portfolio, exit regardless of streak), OR (d) left_universe=true (ticker dropped out of the screener universe entirely — no current data available, exit is mandatory). Otherwise use HOLD. Do not omit any active position from open_picks_review.",
]

NON_TRADABLE_SUBTHEMES = frozenset({
    "futures", "commodity", "macro_index", "crude_oil_leveraged",
})

VALID_REJECT_CATS = frozenset({
    "insufficient_conviction", "macro_conflict", "weak_flow",
    "weak_relative_strength", "technical_overextension", "data_quality",
    "not_tradable", "better_alternative_available",
})


def compact_candidate(c: dict, conc: dict | None = None) -> dict:
    ds = c.get("daily_signals") or {}
    return {
        "ticker":         c["ticker"],
        "name":           c.get("name", ""),
        "theme":          c.get("theme", ""),
        "subtheme":       c.get("subtheme", ""),
        "pcs":            c.get("pcs"),
        "eligible":       c.get("eligible"),
        "signal":         c.get("signal"),
        "rot_score":      c.get("rot_score"),
        "ret_4w_vs_spy":  c.get("ret_4w_vs_spy"),
        "ret_13w_vs_spy": c.get("ret_13w_vs_spy"),
        "streak_weeks":   c.get("streak_weeks"),
        "dist_52w_high":  c.get("dist_52w_high"),
        "is_early":       c.get("is_early", False),
        "flags":          (c.get("flags") or [])[:5],
        "pcs_components": c.get("pcs_components"),
        # Daily signals — populated only when pcs_calculator fetched prices
        "dems":           ds.get("daily_early_momentum_score"),
        "ret_5d_vs_spy":  ds.get("ret_5d_vs_spy"),
        "ret_10d_vs_spy": ds.get("ret_10d_vs_spy"),
        "outperform_d10": ds.get("outperform_days_10d"),
        "streak_days":    ds.get("streak_days"),
        "momentum_accel": ds.get("momentum_accel"),
        "vol_5d_20d":     ds.get("vol_5d_vs_20d"),
        "spike_flag":     ds.get("spike_flag"),
        # Extension risk — informational, does not block selections
        "extension_risk":   c.get("extension_risk"),
        "extension_points": c.get("extension_points"),
        "extension_flags":  c.get("extension_flags"),
        # Theme concentration — informational, does not block selections
        "theme_concentration_risk":    (conc or {}).get("theme_risk"),
        "subtheme_concentration_risk": (conc or {}).get("subtheme_risk"),
        # Koncorde Plus — institutional/retail flow direction, informational.
        # Daily (D) is noisy; 3D is the sweet spot signal/noise-wise; W confirms.
        # konc_alignment is the top-level D/3D/W summary reading (see koncorde_calculator.py).
        "konc_d_state":   c.get("konc_d_state"),
        "konc_3d_state":  c.get("konc_3d_state"),
        "konc_3d_blue":   c.get("konc_3d_blue"),
        "konc_3d_green":  c.get("konc_3d_green"),
        "konc_3d_trend":  c.get("konc_3d_trend"),
        "konc_w_state":   c.get("konc_w_state"),
        "konc_alignment": c.get("konc_alignment"),
    }
