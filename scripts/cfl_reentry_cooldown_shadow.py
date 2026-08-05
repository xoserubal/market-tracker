"""
cfl_reentry_cooldown_shadow.py — SHADOW-ONLY re-entry cooldown for
                                   CONFIRMED_FLOW_LEADERS.

Why: the CFL diagnosis (wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md, section 3.6)
found heavy re-entry into the same names — ASPI 11 times (-30.6% avg ret_1m),
SASK.V 11 times (-6.0% avg) — including repeated re-entries into tickers that
had just failed. This asks: if a ticker fails 1-week follow-through
(ret_1w < 0, the same primary rule validated in that document / used by
cfl_followthrough_shadow.py), what if CFL couldn't re-select it for the next
15-20 trading sessions? Per the agreed plan (2026-08-05, P3): shadow/log only,
never actually blocks a real selection.

This runs entirely retroactively over shadow_picks.jsonl — ret_1w is already
populated for most historical picks, so no new price fetches are needed to
build the full history. It also evaluates going forward: each pipeline run,
any newly-logged CFL pick is checked against the cooldown state built from
everything before it.

Reads:
  docs/data/shadow_picks.jsonl   (CFL active-model picks + their ret_1w)

Writes:
  docs/data/cfl_reentry_cooldown_shadow.jsonl   (one row per CFL pick event,
                                                   idempotent full rebuild —
                                                   see note below)

Note on idempotency: unlike the other two P0-P3 scripts, this one rebuilds its
output from scratch every run instead of incrementally appending. Reason: a
pick's cooldown status can only be known once we know whether the picks BEFORE
it (chronologically) failed follow-through — and ret_1w for older picks keeps
arriving asynchronously via update_performance.py days after the pick itself
was logged. An append-only log would freeze each pick's cooldown verdict at
whatever partial information existed the day it was first evaluated. Rebuilding
is cheap (pure computation over an already-small local file, no network calls)
so this trade-off is free.

Usage:
  py -3 scripts/cfl_reentry_cooldown_shadow.py             # rebuild + report
  py -3 scripts/cfl_reentry_cooldown_shadow.py --sessions 15
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
SHADOW_PICKS = DATA / "shadow_picks.jsonl"
OUT_LOG      = DATA / "cfl_reentry_cooldown_shadow.jsonl"

PORTFOLIO = "CONFIRMED_FLOW_LEADERS"
DEFAULT_COOLDOWN_SESSIONS = 18   # mid-point of the requested 15-20 range

# Same zombie-position exclusion as the CFL diagnosis (positions stuck open
# with no exit mechanism until 2026-06-09 — not real trading decisions).
EXCLUDE_ZOMBIE = {
    ("NVDA", "2026-05-08"), ("MSTR", "2026-05-08"), ("COIN", "2026-05-09"),
    ("KOS", "2026-05-15"), ("SU", "2026-05-16"), ("ASPI", "2026-05-27"),
    ("EOSE", "2026-05-29"), ("SASK.V", "2026-05-30"), ("RCAT", "2026-05-30"),
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def save_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def dedup_same_day_reruns(picks: list[dict]) -> list[dict]:
    """Same fix as compare_vs_baselines.py::dedup_same_day_reruns — several
    runs on the same calendar day log the same market event repeatedly."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in sorted(picks, key=lambda p: (p.get("date") or "", p.get("run_id") or "")):
        key = (p.get("model"), p.get("ticker"), p.get("portfolio"), p.get("date"))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def trading_sessions_between(dates: list[str], d1: str, d2: str) -> int:
    """Approximate trading sessions between two dates using the actual set of
    dates CFL picks were logged on as a stand-in trading calendar. Falls back
    to a 5/7 business-day approximation when the gap exceeds what's observed
    locally (sparse coverage for very old/new dates)."""
    cal = sorted(set(dates) | {d1, d2})
    try:
        i1, i2 = cal.index(d1), cal.index(d2)
        return abs(i2 - i1)
    except ValueError:
        from datetime import datetime
        dt1 = datetime.strptime(d1, "%Y-%m-%d")
        dt2 = datetime.strptime(d2, "%Y-%m-%d")
        return round(abs((dt2 - dt1).days) * 5 / 7)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=DEFAULT_COOLDOWN_SESSIONS,
                     help="cooldown length in trading sessions (default: %(default)s)")
    args = ap.parse_args()

    picks = dedup_same_day_reruns(load_jsonl(SHADOW_PICKS))
    cfl = [p for p in picks
           if p.get("portfolio") == PORTFOLIO
           and p.get("active_model")
           and (p.get("ticker"), (p.get("date") or "")[:10]) not in EXCLUDE_ZOMBIE]
    cfl.sort(key=lambda p: (p.get("date") or ""))

    all_dates = sorted({p["date"][:10] for p in cfl})

    last_failure: dict[str, dict] = {}   # ticker -> {"date":..., "ret_1w":...}
    out_rows: list[dict] = []

    for p in cfl:
        ticker = p["ticker"]
        pick_date = p["date"][:10]
        ret_1w = p.get("ret_1w")
        is_failure = (ret_1w < 0) if ret_1w is not None else None

        cooldown_active = False
        triggered_by = None
        sessions_remaining = None
        prior = last_failure.get(ticker)
        if prior is not None:
            gap = trading_sessions_between(all_dates, prior["date"], pick_date)
            if gap < args.sessions:
                cooldown_active = True
                triggered_by = {"date": prior["date"], "ret_1w": prior["ret_1w"]}
                sessions_remaining = args.sessions - gap

        out_rows.append({
            "ticker": ticker,
            "date": pick_date,
            "portfolio": PORTFOLIO,
            "ret_1w": ret_1w,
            "ret_1m": p.get("ret_1m"),
            "is_failure": is_failure,
            "cooldown_active": cooldown_active,
            "cooldown_triggered_by": triggered_by,
            "cooldown_sessions_remaining": sessions_remaining,
            "cooldown_sessions_setting": args.sessions,
        })

        # Update state AFTER evaluating this pick against the prior state —
        # a pick can't be blocked by its own outcome.
        if is_failure:
            last_failure[ticker] = {"date": pick_date, "ret_1w": ret_1w}

    save_jsonl(OUT_LOG, out_rows)

    blocked = [r for r in out_rows if r["cooldown_active"]]
    blocked_with_1m = [r for r in blocked if r.get("ret_1m") is not None]
    not_blocked_with_1m = [r for r in out_rows if not r["cooldown_active"] and r.get("ret_1m") is not None]

    print(f"Rebuilt {len(out_rows)} CFL pick evaluations -> {OUT_LOG}")
    print(f"Cooldown setting: {args.sessions} trading sessions after a ret_1w<0 failure")
    print(f"Picks that WOULD have been blocked by cooldown: {len(blocked)}/{len(out_rows)}")
    if blocked:
        tickers_blocked = defaultdict(int)
        for r in blocked:
            tickers_blocked[r["ticker"]] += 1
        print("  by ticker:", dict(sorted(tickers_blocked.items(), key=lambda x: -x[1])))
    if blocked_with_1m:
        print(f"  their actual ret_1m: mean={st.mean(r['ret_1m'] for r in blocked_with_1m):.2f}% "
              f"(n={len(blocked_with_1m)})")
    if not_blocked_with_1m:
        print(f"  vs non-blocked picks ret_1m: mean={st.mean(r['ret_1m'] for r in not_blocked_with_1m):.2f}% "
              f"(n={len(not_blocked_with_1m)})")


if __name__ == "__main__":
    main()
