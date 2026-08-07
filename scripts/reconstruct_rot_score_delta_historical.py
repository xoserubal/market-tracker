"""
reconstruct_rot_score_delta_historical.py
    — backfills rot_score_delta_4w for every pick already logged in
      shadow_picks.jsonl, for Fase 0 of the Ranking Score plan
      (wiki/PREREGISTRO_RANKING_SCORE_V0.md §0: "rot_score_delta reconstruible
      al 100% vía git log de ai_candidates.json").

Same git-history approach as reconstruct_pcs_components_historical.py (import
directly, don't reimplement, to avoid drift): rot_score is committed inside
docs/data/ai_candidates.json on every pipeline run since 2026-05-08, so the
entry-day value and the value from ~4 weeks earlier are both real historical
data, not recomputation from today's state.

Two lookups per pick:
  1. Entry snapshot — same exact-match-by-pcs logic as the PCS reconstruction
     (disambiguates AM/PM same-day runs).
  2. Prior snapshot — nearest commit to entry_date-28d that has this ticker in
     its candidate list, searched within a +-5 calendar day window (pipeline
     runs ~daily but weekends/gaps exist; widening further would stop meaning
     "4 weeks"). No match in that window -> left null, never approximated.

rot_score_delta_4w = rot_score_entry - rot_score_prior (positive = rotation
improving into the pick).

Reads:
  docs/data/shadow_picks.jsonl
  git history of docs/data/ai_candidates.json

Writes:
  docs/data/rot_score_delta_reconstructed.jsonl   (one row per unique
                                                     ticker+date+pcs, append-only)

Usage:
  py -3 scripts/reconstruct_rot_score_delta_historical.py             # fill missing only
  py -3 scripts/reconstruct_rot_score_delta_historical.py --force     # recompute all
  py -3 scripts/reconstruct_rot_score_delta_historical.py --dry-run   # show, don't write
  py -3 scripts/reconstruct_rot_score_delta_historical.py --report    # coverage summary only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from reconstruct_pcs_components_historical import (  # noqa: E402
    list_commits, candidates_at_commit, find_match,
)

DATA = ROOT / "docs" / "data"
SHADOW_PICKS = DATA / "shadow_picks.jsonl"
OUT_LOG      = DATA / "rot_score_delta_reconstructed.jsonl"

LOOKBACK_DAYS = 28   # "4 weeks", calendar days (matches ret_4w_vs_spy convention elsewhere)
MAX_OFFSET    = 5    # search window around the lookback target, calendar days each side


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def find_nearest_with_ticker(
    ticker: str, target_date_str: str, commits_by_date: dict[str, list[str]],
    max_offset: int = MAX_OFFSET,
) -> tuple[dict | None, str | None, str | None, int | None]:
    """Nearest commit (by calendar day, +-max_offset) whose candidate list
    contains `ticker`. Ties prefer the earlier day. Returns
    (candidate_dict_or_None, matched_date, matched_commit, offset_days)."""
    ts = datetime.strptime(target_date_str, "%Y-%m-%d")
    for offset in range(0, max_offset + 1):
        signs = (0,) if offset == 0 else (-1, 1)
        for sign in signs:
            day = (ts + timedelta(days=offset * sign)).strftime("%Y-%m-%d")
            for commit_hash in commits_by_date.get(day, []):
                cand = candidates_at_commit(commit_hash).get(ticker)
                if cand is not None:
                    return cand, day, commit_hash, offset * sign
    return None, None, None, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="recompute rows already in output")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true", help="print coverage summary only")
    args = ap.parse_args()

    if args.report:
        existing = load_jsonl(OUT_LOG)
        n_ok = sum(1 for r in existing if r.get("reconstructed"))
        print(f"{OUT_LOG.name}: {len(existing)} rows, {n_ok} reconstructed, "
              f"{len(existing) - n_ok} unresolved")
        return

    picks = load_jsonl(SHADOW_PICKS)
    if not picks:
        print("shadow_picks.jsonl is empty, nothing to do.")
        return

    existing = load_jsonl(OUT_LOG)
    have: set[tuple[str, str, str]] = {
        (r["ticker"], r["date"], str(r.get("pcs_at_pick"))) for r in existing
    }

    wanted: list[tuple[str, str, float | None]] = []
    seen_keys = set()
    for p in picks:
        t, d = p.get("ticker"), (p.get("date") or "")[:10]
        pcs_val = p.get("pcs")
        if not t or not d:
            continue
        key = (t, d, str(pcs_val))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if not args.force and key in have:
            continue
        wanted.append((t, d, pcs_val))

    if not wanted:
        print("Nothing to reconstruct — all picks already have a row (use --force to recompute).")
        return

    print(f"Reconstructing rot_score_delta_4w for {len(wanted)} ticker/date/pcs triples...")

    commits = list_commits()
    if not commits:
        print("ERROR: no git history found for docs/data/ai_candidates.json", file=sys.stderr)
        sys.exit(1)
    commits_by_date: dict[str, list[str]] = {}
    for h, d in commits:
        commits_by_date.setdefault(d, []).append(h)

    written = n_ok = n_fail = 0
    for ticker, date_str, pcs_val in wanted:
        entry_cand, entry_method, entry_commit = find_match(ticker, date_str, pcs_val, commits_by_date)

        rot_score_entry = entry_cand.get("rot_score") if entry_cand else None

        target = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        prior_cand, prior_date, prior_commit, prior_offset = find_nearest_with_ticker(
            ticker, target, commits_by_date,
        )
        rot_score_prior = prior_cand.get("rot_score") if prior_cand else None

        delta = None
        if rot_score_entry is not None and rot_score_prior is not None:
            delta = round(rot_score_entry - rot_score_prior, 2)

        row = {
            "ticker": ticker,
            "date": date_str,
            "pcs_at_pick": pcs_val,
            "entry_match_method": entry_method,
            "entry_matched_commit": entry_commit,
            "rot_score_entry": rot_score_entry,
            "lookback_target_date": target,
            "prior_matched_date": prior_date,
            "prior_matched_commit": prior_commit,
            "prior_offset_days": prior_offset,
            "rot_score_prior": rot_score_prior,
            "rot_score_delta_4w": delta,
            "reconstructed": entry_cand is not None and prior_cand is not None,
            "reconstructed_at": datetime.now().isoformat(timespec="seconds"),
        }
        if row["reconstructed"]:
            n_ok += 1
        else:
            n_fail += 1
        if args.dry_run:
            print(f"  {ticker:10} {date_str}  rot_entry={rot_score_entry}  "
                  f"rot_prior={rot_score_prior} (@{prior_date}, offset={prior_offset})  "
                  f"delta_4w={delta}")
        else:
            append_jsonl(OUT_LOG, row)
        written += 1

    print(f"{'Would write' if args.dry_run else 'Wrote'} {written} rows "
          f"({n_ok} reconstructed, {n_fail} unmatched)"
          + ("" if args.dry_run else f" -> {OUT_LOG}"))


if __name__ == "__main__":
    main()
