"""
pcs_floor_whipsaw_shadow.py — flags "PCS<62 absolute floor" mandatory exits
                               that may be reacting to single-day component
                               noise rather than real deterioration.

Why: investigating why SE (force_analyze.py, 2026-08-12) wasn't selected
around its cleanest metrics window (PCS 82.2, extension_risk low, 2026-08-05)
surfaced that its two real entries (CONFIRMED_FLOW_LEADERS 2026-07-07,
MACRO_THEMATIC_BENEFICIARIES 2026-07-15) were BOTH closed exactly 1 trading
day later by the "current_pcs < 62 absolute floor" rule while price barely
moved (-0.73%, +1.89%). Traced the CFL case to git history of
ai_candidates.json: B_theme_flow (one of six PCS components, 24-point
ceiling) swung 22.0 -> 6.0 -> 18.0 across three consecutive snapshots while
every other component stayed flat and SE's own price didn't move — a
same-day reversal in a single component, not stock-specific deterioration.
Scanning all 30 system-wide floor exits since June found 3 with the same
signature (SE x2, NVDA — all closed within 1-2 days at a near-flat price).
n=3 is far too small to touch the exit rule (this project's own bar, set in
wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md: ~100-150 independent events across
2+ regimes before promoting any shadow finding to a real rule change) — so
this script exists to accumulate that count automatically instead of relying
on someone noticing manually again.

Unlike cfl_followthrough_shadow.py, this does NOT project a hypothetical
"would exit / would hold" — the floor rule already fired for real, closing
a real (or shadow) position. This only classifies, after the fact, whether
that specific exit looks like a price-confirmed deterioration or a
flat-price whipsaw, and best-effort attributes the PCS drop to whichever of
the six components (A-F) moved the most between entry day and close day.

Reads:
  docs/data/ai_picks.json                   (portfolios[].history[], every portfolio —
                                               not just CONFIRMED_FLOW_LEADERS; the NVDA
                                               case that motivated this happened in
                                               MACRO_THEMATIC_BENEFICIARIES)
  git history of docs/data/ai_candidates.json (component breakdown at entry/close day,
                                               best-effort — reuses the same commit-lookup
                                               helpers as reconstruct_pcs_components_historical.py
                                               so the two scripts can't drift on how a
                                               ticker/date/pcs triple is matched to a commit)

Writes:
  docs/data/pcs_floor_whipsaw_shadow.jsonl  (append-only, one row per close event,
                                               dedup by ticker+portfolio+entry_date+close_date)

Classification (first pass, not calibrated against forward performance —
same "observe first" posture as extension_risk/Koncorde before they had
enough data to justify a real threshold):
  flat_price_whipsaw       holding_days <= 2 AND |price_change_pct| < 3.0
  likely_real_deterioration  otherwise (has price data)
  insufficient_data        entry_price or close_price missing

Usage:
  py -3 scripts/pcs_floor_whipsaw_shadow.py             # log new floor-exit events
  py -3 scripts/pcs_floor_whipsaw_shadow.py --dry-run   # show, don't write
  py -3 scripts/pcs_floor_whipsaw_shadow.py --report    # summary of what's logged so far
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from reconstruct_pcs_components_historical import (  # noqa: E402
    list_commits, candidates_at_commit, find_match, COMPONENT_LABELS,
)

DATA      = ROOT / "docs" / "data"
AI_PICKS  = DATA / "ai_picks.json"
OUT_LOG   = DATA / "pcs_floor_whipsaw_shadow.jsonl"

WHIPSAW_MAX_HOLDING_DAYS = 2
WHIPSAW_MAX_ABS_PRICE_MOVE = 3.0

_PCS_IN_REASON = re.compile(r"pcs[^0-9]{0,20}?(\d+\.\d+|\d+)", re.IGNORECASE)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _extract_close_pcs(close_reason: str) -> float | None:
    m = _PCS_IN_REASON.search(close_reason or "")
    return float(m.group(1)) if m else None


def _component_snapshot(ticker: str, date_str: str, pcs_val: float | None,
                         commits_by_date: dict[str, list[str]]) -> dict:
    cand, method, commit_hash = find_match(ticker, date_str, pcs_val, commits_by_date)
    comp = (cand.get("pcs_components") or {}) if cand else {}
    return {
        "matched": cand is not None,
        "match_method": method,
        "matched_commit": commit_hash,
        "components": {label: comp.get(label) for label in COMPONENT_LABELS.values()} if cand else None,
    }


def _largest_swing(entry_snap: dict, close_snap: dict) -> dict | None:
    ec, cc = entry_snap.get("components"), close_snap.get("components")
    if not ec or not cc:
        return None
    best = None
    for label in COMPONENT_LABELS.values():
        ev, cv = ec.get(label), cc.get(label)
        if ev is None or cv is None:
            continue
        delta = round(cv - ev, 2)
        if best is None or abs(delta) > abs(best["delta"]):
            best = {"component": label, "delta": delta, "entry_value": ev, "close_value": cv}
    return best


def _floor_exit_events(picks_data: dict) -> list[dict]:
    events = []
    for pid, ptf in picks_data.get("portfolios", {}).items():
        for ev in ptf.get("history", []):
            if ev.get("event") != "close":
                continue
            reason = ev.get("close_reason") or ""
            if "floor" not in reason.lower():
                continue
            events.append({**ev, "portfolio": pid})
    return events


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true", help="summary of logged rows only")
    args = ap.parse_args()

    existing = load_jsonl(OUT_LOG)

    if args.report:
        if not existing:
            print(f"{OUT_LOG.name}: no rows logged yet.")
            return
        by_class: dict[str, int] = {}
        for r in existing:
            by_class[r["classification"]] = by_class.get(r["classification"], 0) + 1
        print(f"{OUT_LOG.name}: {len(existing)} floor-exit event(s) logged")
        for c, n in sorted(by_class.items(), key=lambda kv: -kv[1]):
            print(f"  {c}: {n}")
        whipsaws = [r for r in existing if r["classification"] == "flat_price_whipsaw"]
        if whipsaws:
            print("\n  flat_price_whipsaw cases:")
            for r in whipsaws:
                comp = r.get("largest_component_swing")
                comp_txt = f", largest swing: {comp['component']} {comp['entry_value']}->{comp['close_value']}" if comp else ""
                print(f"    {r['ticker']:10} {r['portfolio']:28} {r['entry_date']}->{r['close_date']} "
                      f"({r['holding_days']}d, {r['price_change_pct']:+.2f}%){comp_txt}")
        return

    picks_data = load_json(AI_PICKS)
    floor_events = _floor_exit_events(picks_data)
    if not floor_events:
        print("No PCS-floor close events found in ai_picks.json.")
        return

    already = {
        (r["ticker"], r["portfolio"], r["entry_date"], r["close_date"]) for r in existing
    }
    todo = [
        ev for ev in floor_events
        if (ev["ticker"], ev["portfolio"], ev.get("entry_date"), ev.get("close_date")) not in already
    ]
    if not todo:
        print("All PCS-floor close events already logged.")
        return

    commits = list_commits()
    commits_by_date: dict[str, list[str]] = {}
    for h, d in commits:
        commits_by_date.setdefault(d, []).append(h)

    written = 0
    for ev in todo:
        ticker, portfolio = ev["ticker"], ev["portfolio"]
        entry_date, close_date = ev.get("entry_date"), ev.get("close_date")
        entry_price, close_price = ev.get("entry_price"), ev.get("close_price")
        entry_pcs = ev.get("entry_pcs")
        close_reason = ev.get("close_reason") or ""
        close_pcs = _extract_close_pcs(close_reason)

        holding_days = None
        if entry_date and close_date:
            try:
                holding_days = (datetime.strptime(close_date, "%Y-%m-%d")
                                 - datetime.strptime(entry_date, "%Y-%m-%d")).days
            except ValueError:
                holding_days = None

        price_change_pct = None
        if entry_price and close_price:
            price_change_pct = round((close_price / entry_price - 1) * 100, 2)

        if entry_price is None or close_price is None or holding_days is None:
            classification = "insufficient_data"
        elif holding_days <= WHIPSAW_MAX_HOLDING_DAYS and abs(price_change_pct) < WHIPSAW_MAX_ABS_PRICE_MOVE:
            classification = "flat_price_whipsaw"
        else:
            classification = "likely_real_deterioration"

        entry_snap = _component_snapshot(ticker, entry_date, entry_pcs, commits_by_date) if entry_date else {"matched": False, "components": None}
        close_snap = _component_snapshot(ticker, close_date, close_pcs, commits_by_date) if close_date else {"matched": False, "components": None}
        swing = _largest_swing(entry_snap, close_snap)

        record = {
            "ticker":            ticker,
            "portfolio":         portfolio,
            "entry_date":        entry_date,
            "close_date":        close_date,
            "holding_days":      holding_days,
            "entry_price":       entry_price,
            "close_price":       close_price,
            "price_change_pct":  price_change_pct,
            "entry_pcs":         entry_pcs,
            "close_pcs":         close_pcs,
            "close_pcs_extraction": "regex_from_close_reason" if close_pcs is not None else "unmatched",
            "close_reason":      close_reason,
            "classification":    classification,
            "entry_components_match":  {k: v for k, v in entry_snap.items() if k != "components"},
            "close_components_match":  {k: v for k, v in close_snap.items() if k != "components"},
            "entry_components": entry_snap.get("components"),
            "close_components": close_snap.get("components"),
            "largest_component_swing": swing,
            "logged_at":         datetime.now().isoformat(timespec="seconds"),
        }

        if args.dry_run:
            comp_txt = f", largest swing: {swing['component']} {swing['entry_value']}->{swing['close_value']}" if swing else ""
            print(f"  {ticker:10} {portfolio:28} {entry_date}->{close_date} "
                  f"({holding_days}d, {price_change_pct}%) -> {classification}{comp_txt}")
        else:
            append_jsonl(OUT_LOG, record)
        written += 1

    print(f"{'Would log' if args.dry_run else 'Logged'} {written} floor-exit event(s)"
          f"{'' if args.dry_run else f' -> {OUT_LOG}'}")


if __name__ == "__main__":
    main()
