"""
Shared constants between paper_trading.py (production selection pipeline) and
build_eval_bundle.py (external evaluator bundle).

Both files used to keep their own copy of HARD_RULES and _compact_candidate()
and drifted apart (build_eval_bundle.py ended up with 8 of 15 rules, missing
pcs_components and the Koncorde fields — see CLAUDE.md history). Import from
here instead of copying, so a future change to either only needs to happen once.
"""
from __future__ import annotations

# ── Suelo de PCS: histeresis + confirmacion (Brazo D del factorial P2) ───────
# Adoptado en real 2026-09-22 tras revisar la gestion de carteras IA: de 117
# cierres historicos en HIGH_CONVICTION/CONFIRMED_FLOW_LEADERS/EARLY_ROTATION/
# MACRO_THEMATIC_BENEFICIARIES/MIMO_SHADOW, el 100% tenia la misma causa
# ("PCS cayo por debajo del umbral", una sola lectura, sin confirmacion) y
# ninguno se cerro nunca por objetivo de beneficio. Ver "PCS-floor whipsaw
# monitor" en CLAUDE.md y wiki/PREREGISTRO_PCS_FLOOR_FACTORIAL_V1.md — el
# propio shadow (pcs_floor_factorial_v1_shadow.py) llevaba corriendo desde
# 2026-08-30 sin n suficiente para un veredicto formal, pero el patron
# cualitativo (100% mismo motivo) ya era lo bastante consistente para actuar
# sin esperar. Formula identica a la que evalua ese shadow (Brazo D), para
# que ambos midan literalmente la misma regla.
ABSOLUTE_FLOOR             = 62.0
PCS_FLOOR_HYSTERESIS_BUFFER = 1.5
PCS_FLOOR_SEVERE_BUFFER     = 3.0


def compute_t_active(pcs_min_entry: float, streak_weeks: float | None) -> tuple[float, str]:
    """T_active = max(ABSOLUTE_FLOOR, pcs_min_entry) si streak_weeks<=1, si no
    ABSOLUTE_FLOOR — definicion formal de la hoja de ruta de auditoria de
    carteras (wiki/, firmada 2026-08-30, §6). La formula ya vivia en
    ai_picks_decision_state.py (P0) con un envoltorio especifico de
    PCS_GATED_PORTFOLIOS; aqui queda solo la aritmetica pura, reusada tambien
    por el enforcement determinista de paper_trading.py."""
    if streak_weeks is not None and streak_weeks <= 1:
        t = max(ABSOLUTE_FLOOR, pcs_min_entry)
        return t, "portfolio_min_entry" if t > ABSOLUTE_FLOOR else "absolute_floor_62"
    return ABSOLUTE_FLOOR, "absolute_floor_62"


def compute_pcs_floor_verdict(
    pcs: float | None,
    rot_score: float | None,
    t_active: float | None,
    prev_breach_1_5: bool | None,
) -> dict:
    """Brazo D del factorial P2 (histeresis + confirmacion): un suelo de PCS
    con una sola lectura cierra por ruido de un dia (ver casos SE/NVDA en
    CLAUDE.md, seccion "PCS-floor whipsaw monitor") — exige dos lecturas
    consecutivas por debajo de T_active-1.5, salvo rotura severa, que cierra
    de inmediato. Misma logica exacta que evalua
    scripts/pcs_floor_factorial_v1_shadow.py para el Brazo D.

    Devuelve {"status", "reason", "breach_1_5_today"}. status:
      "must_exit_severe"           PCS < T_active-3.0 O rot_score<=2 (bypass, cierre inmediato)
      "must_exit_confirmed_breach" PCS < T_active-1.5 hoy Y en la lectura anterior
      "watch_unconfirmed_breach"   PCS < T_active-1.5 solo hoy (primera lectura, no cierra)
      "ok"                         sin breach
      None                         sin datos (pcs o t_active ausentes)
    """
    if pcs is None or t_active is None:
        return {"status": None, "reason": None, "breach_1_5_today": None}
    breach_1_5 = pcs < (t_active - PCS_FLOOR_HYSTERESIS_BUFFER)
    if pcs < (t_active - PCS_FLOOR_SEVERE_BUFFER) or (rot_score is not None and rot_score <= 2):
        return {"status": "must_exit_severe", "reason": "breach_severe", "breach_1_5_today": breach_1_5}
    if breach_1_5 and prev_breach_1_5:
        return {"status": "must_exit_confirmed_breach", "reason": "hysteresis_confirmed_2_readings",
                "breach_1_5_today": breach_1_5}
    if breach_1_5:
        return {"status": "watch_unconfirmed_breach", "reason": None, "breach_1_5_today": breach_1_5}
    return {"status": "ok", "reason": None, "breach_1_5_today": breach_1_5}


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
    "Review ALL tickers in active_picks_relevant and include each one in open_picks_review with action=HOLD or EXIT — do not omit any active position. PCS-floor exits are now enforced deterministically by the system (hysteresis + two-reading confirmation, not a single PCS reading) — you do not decide these and should not replicate the old single-reading formula. Check mechanical_floor_status per position: 'must_exit_severe', 'must_exit_confirmed_breach', or 'must_exit_left_universe' mean that position is already being closed regardless of what you write here (HOLD or EXIT, it makes no difference to the outcome). Only propose action=EXIT yourself for a position with mechanical_floor_status='ok' or 'watch_unconfirmed_breach' when you have an independent, fundamental reason unrelated to a single PCS dip (state it explicitly in reason) — this should be rare.",
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
        # Fase 0 — PCS reframing (Ranking Score plan, 2026-08-06). Persisted
        # here too so the entry-time value survives in ai_model_payloads/
        # snapshots, not just in ai_candidates.json (see CLAUDE.md).
        "pcs_raw":             c.get("pcs_raw"),
        "pcs_ex_macro":        c.get("pcs_ex_macro"),
        "pcs_ceiling":         c.get("pcs_ceiling"),
        "pcs_normalized":      c.get("pcs_normalized"),
        "component_A":         c.get("component_A"),
        "component_B":         c.get("component_B"),
        "component_C":         c.get("component_C"),
        "component_D":         c.get("component_D"),
        "component_E":         c.get("component_E"),
        "component_F":         c.get("component_F"),
        "component_A_ceiling": c.get("component_A_ceiling"),
        "component_B_ceiling": c.get("component_B_ceiling"),
        "component_C_ceiling": c.get("component_C_ceiling"),
        "component_D_ceiling": c.get("component_D_ceiling"),
        "component_E_ceiling": c.get("component_E_ceiling"),
        "component_F_ceiling": c.get("component_F_ceiling"),
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
