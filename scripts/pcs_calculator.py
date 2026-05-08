"""
Pick Conviction Score (PCS) Calculator — v1

Inputs:  docs/data/macro_history.json
         docs/data/rotation_signals.json   (sector ETFs / proxies)
         docs/data/stock_candidates.json   (individual stocks — 72 of 91 universe tickers)
         docs/data/universe.json

Output:  docs/data/ai_candidates.json
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"


def _load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── A. Macro Permission (0–15) ────────────────────────────────────────────────
# What: Does the macro regime allow taking risk? Is it improving or deteriorating?
# Sources: macro_history.json → latest + last history row (for emergency flag)

def score_a(macro_latest: dict, last_hist: dict) -> tuple[float, list[str]]:
    score     = macro_latest.get("score") or 0
    trend     = macro_latest.get("trend", "Stable")
    emergency = bool(last_hist.get("flag_emergency_mode"))

    if   score >= 70: base = 13.0
    elif score >= 55: base = 10.0
    elif score >= 40: base =  6.0
    else:             base =  2.0

    flags = []
    if   trend == "Improving":      base += 1; flags.append("macro_improving")
    elif trend == "Deteriorating":  base -= 1; flags.append("macro_deteriorating")
    if emergency:                   base -= 3; flags.append("emergency_mode")

    return _clamp(base, 0, 15), flags


# ── B. Theme Flow (0–25) ──────────────────────────────────────────────────────
# What: Is capital entering the theme/sector this ticker belongs to?
# Primary: theme_proxy rot_score from rotation_signals (sector ETFs + futures)
# Fallback: average ret_13w_vs_spy of same-theme tickers in stock_candidates

def score_b(
    meta: dict,
    rot_idx: dict,
    cand_by_theme: dict[str, list],
) -> tuple[float, list[str]]:
    proxy  = meta.get("theme_proxy")
    theme  = meta.get("theme", "")
    flags  = []

    if proxy and proxy in rot_idx:
        rot = rot_idx[proxy].get("rot_score") or 0
        sig = rot_idx[proxy].get("signal") or ""
        if   rot >= 7: pts = 22.0; flags.append("theme_strong")
        elif rot >= 6: pts = 18.0; flags.append("theme_good")
        elif rot >= 5: pts = 14.0; flags.append("theme_moderate")
        elif rot >= 4: pts = 10.0; flags.append("theme_weak")
        elif rot >= 3: pts =  6.0; flags.append("theme_poor")
        else:          pts =  3.0; flags.append("theme_very_poor")
        if   sig == "COMPRA":    pts = min(25, pts + 2); flags.append("proxy_compra")
        elif sig == "ACUMULAR":  pts = min(25, pts + 1)
        return pts, flags

    # Fallback: average same-theme relative performance
    rets = cand_by_theme.get(theme, [])
    if rets:
        avg = sum(rets) / len(rets)
        if   avg >= 10: pts = 18.0; flags.append("theme_avg_strong")
        elif avg >= 5:  pts = 14.0; flags.append("theme_avg_good")
        elif avg >= 0:  pts = 11.0; flags.append("theme_avg_neutral")
        elif avg >= -5: pts =  8.0; flags.append("theme_avg_weak")
        else:           pts =  4.0; flags.append("theme_avg_poor")
        return pts, flags

    return 10.0, ["no_theme_data"]


# ── C. Individual Relative Strength (0–25) ────────────────────────────────────
# What: Is this specific ticker outperforming SPY on 4W and 13W timeframes?
# Sources: stock_candidates.json or rotation_signals.json (ret_4w_vs_spy, ret_13w_vs_spy)

def score_c(
    ticker: str, rot_idx: dict, cand_idx: dict
) -> tuple[float, list[str]]:
    d   = cand_idx.get(ticker) or rot_idx.get(ticker) or {}
    r4  = d.get("ret_4w_vs_spy")
    r13 = d.get("ret_13w_vs_spy")

    if r4 is None and r13 is None:
        return 8.0, ["rs_no_data"]

    combined = (r13 or 0) * 0.6 + (r4 or 0) * 0.4

    if   combined >= 15: pts = 23.0; flag = "rs_strong_leader"
    elif combined >= 7:  pts = 19.0; flag = "rs_leader"
    elif combined >= 2:  pts = 15.0; flag = "rs_outperform"
    elif combined >= -2: pts = 11.0; flag = "rs_neutral"
    elif combined >= -7: pts =  7.0; flag = "rs_underperform"
    else:                pts =  3.0; flag = "rs_laggard"

    return _clamp(pts, 0, 25), [flag]


# ── D. Individual Flow / Rotation Score (0–20) ────────────────────────────────
# What: Is money flowing into this ticker? Combines rot_score with CMF/OBV/volume.
# Sources: stock_candidates.json → rot_score + components

def score_d(
    ticker: str, rot_idx: dict, cand_idx: dict
) -> tuple[float, list[str]]:
    d   = cand_idx.get(ticker) or rot_idx.get(ticker) or {}
    rot = d.get("rot_score")

    if rot is None:
        return 7.0, ["flow_no_data"]

    comp   = d.get("components") or {}
    cmf    = comp.get("cmf_pts",     d.get("cmf_pts",     0)) or 0
    obv    = comp.get("obv_pts",     d.get("obv_pts",     0)) or 0
    vol    = comp.get("vol_rel_pts", d.get("vol_rel_pts", 0)) or 0
    no_ext = comp.get("no_ext_pts",  0) or 0

    if   rot >= 8: base = 17.0; flag = "rot_high"
    elif rot >= 6: base = 13.0; flag = "rot_good"
    elif rot >= 4: base =  9.0; flag = "rot_moderate"
    elif rot >= 2: base =  5.0; flag = "rot_weak"
    else:          base =  2.0; flag = "rot_low"

    flow_bonus   = min(3.0, (cmf + obv + vol) * 0.75)
    timing_bonus = 0.5 if no_ext >= 1 else 0.0

    flags = [flag]
    sig   = d.get("signal") or ""
    if   sig in ("CANDIDATO", "COMPRA"): flags.append("signal_candidato")
    elif sig == "EN_RADAR":              flags.append("signal_en_radar")
    elif sig == "ACUMULAR":              flags.append("signal_acumular")

    return _clamp(base + flow_bonus + timing_bonus, 0, 20), flags


# ── E. Early Acceleration (0–10) ─────────────────────────────────────────────
# What: Is this ticker accelerating before the move becomes obvious?
# Sources: cluster_has_rot_temprana, macd_pts, rsi_pts, streak_weeks

def score_e(
    ticker: str, rot_idx: dict, cand_idx: dict
) -> tuple[float, list[str]]:
    d    = cand_idx.get(ticker) or rot_idx.get(ticker) or {}
    comp = d.get("components") or {}

    is_early = bool(d.get("is_early_rotation") or d.get("cluster_has_rot_temprana"))
    macd     = comp.get("macd_pts", d.get("macd_pts", 0)) or 0
    rsi      = comp.get("rsi_pts",  d.get("rsi_pts",  0)) or 0
    streak   = d.get("streak_weeks") or 0

    if is_early:
        return 9.0, ["early_rotation_active"]
    if macd >= 1 and rsi >= 1:
        pts = 7.0 if streak >= 3 else 6.0
        flags = ["macd_rsi_positive"]
        if streak >= 3: flags.append("streak_3w")
        return pts, flags
    if macd >= 1 or rsi >= 1:
        return 4.0, ["partial_momentum"]
    if not d:
        return 3.0, ["no_early_data"]
    return 2.0, ["no_acceleration"]


# ── F. Data Quality / Tradability (0–5) ──────────────────────────────────────
# What: Is this ticker tradable and do we have enough signal data to trust the score?

def score_f(
    ticker: str, meta: dict, rot_idx: dict, cand_idx: dict
) -> tuple[float, list[str]]:
    if not meta.get("tradable", True):
        return 0.0, ["not_tradable"]

    has_cand = ticker in cand_idx
    has_rot  = ticker in rot_idx
    priority = meta.get("priority", "medium")

    pts   = 0.0
    flags = []
    if has_cand: pts += 3.0; flags.append("individual_data_ok")
    if has_rot:  pts += 1.5; flags.append("rotation_data_ok")
    if not has_cand and not has_rot: flags.append("no_signal_data")

    if   priority == "high": pts += 0.5
    elif priority == "low":  pts -= 1.0

    return _clamp(pts, 0, 5), flags


# ── PCS aggregation ───────────────────────────────────────────────────────────

def compute_pcs(
    ticker: str,
    meta: dict,
    macro_latest: dict,
    last_hist: dict,
    rot_idx: dict,
    cand_idx: dict,
    cand_by_theme: dict,
) -> dict:
    a, fa = score_a(macro_latest, last_hist)
    b, fb = score_b(meta, rot_idx, cand_by_theme)
    c, fc = score_c(ticker, rot_idx, cand_idx)
    d, fd = score_d(ticker, rot_idx, cand_idx)
    e, fe = score_e(ticker, rot_idx, cand_idx)
    f, ff = score_f(ticker, meta, rot_idx, cand_idx)

    pcs      = round(a + b + c + d + e + f, 1)
    eligible = meta.get("tradable", True) and f > 0

    raw  = cand_idx.get(ticker) or rot_idx.get(ticker) or {}
    comp = raw.get("components") or {}

    return {
        "ticker":    ticker,
        "name":      meta.get("name", ""),
        "theme":     meta.get("theme", ""),
        "subtheme":  meta.get("subtheme", ""),
        "region":    meta.get("region", ""),
        "priority":  meta.get("priority", "medium"),
        "pcs":       pcs,
        "eligible":  eligible,
        "pcs_components": {
            "A_macro_permission":    round(a, 1),
            "B_theme_flow":          round(b, 1),
            "C_individual_rs":       round(c, 1),
            "D_individual_flow":     round(d, 1),
            "E_early_acceleration":  round(e, 1),
            "F_data_quality":        round(f, 1),
        },
        "flags":         fa + fb + fc + fd + fe + ff,
        "rot_score":     raw.get("rot_score"),
        "signal":        raw.get("signal"),
        "cluster":       raw.get("cluster"),
        "is_early":      bool(raw.get("is_early_rotation") or raw.get("cluster_has_rot_temprana")),
        "ret_4w_vs_spy": raw.get("ret_4w_vs_spy"),
        "ret_13w_vs_spy":raw.get("ret_13w_vs_spy"),
        "streak_weeks":  raw.get("streak_weeks"),
        "dist_52w_high": raw.get("dist_52w_high"),
        "macd_pts":      comp.get("macd_pts", raw.get("macd_pts")),
        "rsi_pts":       comp.get("rsi_pts",  raw.get("rsi_pts")),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    universe  = _load("universe.json")
    macro_j   = _load("macro_history.json")
    rot_j     = _load("rotation_signals.json")
    cand_j    = _load("stock_candidates.json")

    macro_latest = macro_j.get("latest", {})
    macro_hist   = macro_j.get("history", [])
    last_hist    = macro_hist[-1] if macro_hist else {}

    rot_idx  = {s["ticker"]: s for s in rot_j.get("latest_signals", [])}

    # Build stock_candidates index with theme from universe
    u_meta   = {t["ticker"]: t for t in universe.get("tickers", [])}
    cand_idx = {}
    for c in cand_j.get("candidates", []):
        tk = c["ticker"]
        entry = dict(c)
        if tk in u_meta:
            entry["theme"] = u_meta[tk].get("theme", "")
        cand_idx[tk] = entry

    # Theme averages (ret_13w_vs_spy) for Component B fallback
    cand_by_theme: dict[str, list] = {}
    for c in cand_idx.values():
        th = c.get("theme", "")
        r  = c.get("ret_13w_vs_spy")
        if th and r is not None:
            cand_by_theme.setdefault(th, []).append(r)

    candidates = []
    for ticker, meta in u_meta.items():
        result = compute_pcs(
            ticker, meta, macro_latest, last_hist,
            rot_idx, cand_idx, cand_by_theme,
        )
        candidates.append(result)

    candidates.sort(key=lambda x: x["pcs"], reverse=True)

    eligible = [c for c in candidates if c["eligible"]]

    out = {
        "date":          str(date.today()),
        "macro_context": {
            "score":         macro_latest.get("score"),
            "regime":        macro_latest.get("regime"),
            "trend":         macro_latest.get("trend"),
            "phase_quality": macro_latest.get("phase_quality"),
            "delta_1w":      macro_latest.get("delta_1w"),
            "delta_1m":      macro_latest.get("delta_1m"),
        },
        "summary": {
            "total":     len(candidates),
            "eligible":  len(eligible),
            "pcs_ge_85": sum(1 for c in eligible if c["pcs"] >= 85),
            "pcs_ge_78": sum(1 for c in eligible if c["pcs"] >= 78),
            "pcs_ge_70": sum(1 for c in eligible if c["pcs"] >= 70),
            "pcs_lt_50": sum(1 for c in eligible if c["pcs"] < 50),
        },
        "candidates": candidates,
    }

    out_path = DATA / "ai_candidates.json"
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"ai_candidates.json — {len(candidates)} tickers, {len(eligible)} elegibles")
    print(f"  PCS >= 85: {out['summary']['pcs_ge_85']}")
    print(f"  PCS >= 78: {out['summary']['pcs_ge_78']}")
    print(f"  PCS >= 70: {out['summary']['pcs_ge_70']}")
    top5 = eligible[:5]
    print("  Top 5:")
    for c in top5:
        comps = c["pcs_components"]
        print(f"    {c['ticker']:12} PCS={c['pcs']:5.1f}  "
              f"A={comps['A_macro_permission']} B={comps['B_theme_flow']} "
              f"C={comps['C_individual_rs']} D={comps['D_individual_flow']} "
              f"E={comps['E_early_acceleration']} F={comps['F_data_quality']}")


if __name__ == "__main__":
    run()
