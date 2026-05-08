"""
Event Detector — compares the current AI candidates snapshot with the previous
one and returns a list of signal events that justify calling the Claude API.

Events emitted:
  - pcs_crossed_up / pcs_crossed_down  (threshold crossings per portfolio tier)
  - signal_changed                      (VIGILAR→EN_RADAR→CANDIDATO etc.)
  - macro_regime_changed               (Bull/Bear/Neutro regime shift)
  - macro_trend_changed                (Improving↔Stable↔Deteriorating)
  - new_early_rotation                 (is_early flipped to True)
  - rot_score_jumped                   (rot_score change >= 2)
  - first_snapshot                     (no previous snapshot, bootstrap)

Output written to docs/data/ai_events.json (appended, capped at 500 events).
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

# PCS thresholds per portfolio (crossing these up/down triggers evaluation)
PORTFOLIO_THRESHOLDS = {
    "HIGH_CONVICTION":             85.0,
    "CONFIRMED_FLOW_LEADERS":      78.0,
    "EARLY_ROTATION":              70.0,
    "MACRO_THEMATIC_BENEFICIARIES":65.0,
}

# Signal rank for change detection (higher = stronger)
SIGNAL_RANK = {
    None:        0,
    "VIGILAR":   1,
    "EN_RADAR":  2,
    "ACUMULAR":  3,
    "CANDIDATO": 4,
    "COMPRA":    5,
}

EVENTS_FILE = DATA / "ai_events.json"
SNAP_PREV   = DATA / "ai_candidates_prev.json"
SNAP_CURR   = DATA / "ai_candidates.json"
MAX_EVENTS  = 500


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _idx(snap: dict) -> dict[str, dict]:
    return {c["ticker"]: c for c in snap.get("candidates", [])}


def detect() -> list[dict]:
    curr_snap = _load(SNAP_CURR)
    prev_snap = _load(SNAP_PREV)

    today = str(date.today())
    events: list[dict] = []

    if not prev_snap:
        events.append({
            "date":  today,
            "type":  "first_snapshot",
            "tickers": [],
            "detail": "Bootstrap: no previous snapshot available",
            "macro_context": curr_snap.get("macro_context", {}),
        })
        _save_events(events)
        _rotate_snapshot(curr_snap)
        return events

    curr_idx = _idx(curr_snap)
    prev_idx = _idx(prev_snap)
    curr_macro = curr_snap.get("macro_context", {})
    prev_macro = prev_snap.get("macro_context", {})

    # ── 1. Macro regime / trend changes ──────────────────────────────────────
    if curr_macro.get("regime") != prev_macro.get("regime"):
        events.append({
            "date":   today,
            "type":   "macro_regime_changed",
            "tickers": [],
            "detail": f"{prev_macro.get('regime')} → {curr_macro.get('regime')}",
            "macro_context": curr_macro,
        })

    if curr_macro.get("trend") != prev_macro.get("trend"):
        events.append({
            "date":   today,
            "type":   "macro_trend_changed",
            "tickers": [],
            "detail": f"{prev_macro.get('trend')} → {curr_macro.get('trend')}",
            "macro_context": curr_macro,
        })

    # ── 2. Per-ticker events ──────────────────────────────────────────────────
    for ticker, curr in curr_idx.items():
        if not curr.get("eligible"):
            continue

        prev = prev_idx.get(ticker, {})
        pcs_now  = curr.get("pcs", 0)
        pcs_prev = prev.get("pcs", 0)
        sig_now  = curr.get("signal")
        sig_prev = prev.get("signal")
        rot_now  = curr.get("rot_score") or 0
        rot_prev = prev.get("rot_score") or 0
        early_now  = bool(curr.get("is_early"))
        early_prev = bool(prev.get("is_early"))

        base = {
            "date":   today,
            "ticker": ticker,
            "theme":  curr.get("theme", ""),
            "pcs":    pcs_now,
            "signal": sig_now,
            "macro_context": curr_macro,
        }

        # PCS threshold crossings
        for ptf, thr in PORTFOLIO_THRESHOLDS.items():
            crossed_up   = pcs_prev < thr <= pcs_now
            crossed_down = pcs_now  < thr <= pcs_prev
            if crossed_up:
                events.append({**base, "type": "pcs_crossed_up",
                                "portfolio": ptf, "threshold": thr,
                                "pcs_prev": pcs_prev})
            elif crossed_down:
                events.append({**base, "type": "pcs_crossed_down",
                                "portfolio": ptf, "threshold": thr,
                                "pcs_prev": pcs_prev})

        # Signal upgrade / downgrade
        rank_now  = SIGNAL_RANK.get(sig_now,  0)
        rank_prev = SIGNAL_RANK.get(sig_prev, 0)
        if sig_prev is not None and rank_now > rank_prev:
            events.append({**base, "type": "signal_upgraded",
                           "signal_prev": sig_prev, "signal_now": sig_now})
        elif sig_prev is not None and rank_now < rank_prev and rank_prev >= 3:
            # Only noise if it was meaningful (ACUMULAR or above)
            events.append({**base, "type": "signal_downgraded",
                           "signal_prev": sig_prev, "signal_now": sig_now})

        # New early rotation flag
        if early_now and not early_prev:
            events.append({**base, "type": "new_early_rotation",
                           "rot_score": rot_now})

        # rot_score jump ≥ 2 points (on already elevated score)
        if rot_now - rot_prev >= 2 and rot_now >= 6:
            events.append({**base, "type": "rot_score_jumped",
                           "rot_prev": rot_prev, "rot_now": rot_now})

    _save_events(events)
    _rotate_snapshot(curr_snap)
    return events


def _save_events(new_events: list[dict]):
    existing = []
    if EVENTS_FILE.exists():
        existing = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    combined = existing + new_events
    # Cap to most recent MAX_EVENTS
    if len(combined) > MAX_EVENTS:
        combined = combined[-MAX_EVENTS:]
    EVENTS_FILE.write_text(
        json.dumps(combined, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _rotate_snapshot(curr: dict):
    SNAP_PREV.write_text(
        json.dumps(curr, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    evs = detect()
    print(f"Events detected: {len(evs)}")
    for e in evs[:20]:
        ticker = e.get("ticker", "—")
        print(f"  [{e['type']:28}] {ticker:12} {e.get('detail', e.get('pcs', ''))}")
