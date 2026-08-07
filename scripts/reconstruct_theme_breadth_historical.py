"""
reconstruct_theme_breadth_historical.py
    — backfills theme_breadth for every pick already logged in
      shadow_picks.jsonl, for Fase 0 of the Ranking Score plan
      (wiki/PREREGISTRO_RANKING_SCORE_V0.md §0: "theme_breadth reconstruible
      por el mismo método [que rot_score_delta]: contar candidatos elegibles
      del mismo theme en el snapshot del día").

Same git-history approach as reconstruct_pcs_components_historical.py (import
directly, don't reimplement, to avoid drift): `theme` and `eligible` are both
already fields on every candidate inside the committed docs/data/ai_candidates.json
snapshot (see pcs_calculator.compute_pcs), so this is a straight lookup, not a
recomputation from today's universe/theme assignments.

theme_breadth = count of candidates sharing the pick's `theme` that were
`eligible=true` in that same entry-day snapshot (the pick's own ticker counts
if it was itself eligible — the field answers "how crowded/strong was this
theme's opportunity set", not "how many peers"). theme_total is also recorded
for context (eligible + non-eligible candidates in the theme).

Reads:
  docs/data/shadow_picks.jsonl
  git history of docs/data/ai_candidates.json

Writes:
  docs/data/theme_breadth_reconstructed.jsonl   (one row per unique
                                                   ticker+date+pcs, append-only)

Usage:
  py -3 scripts/reconstruct_theme_breadth_historical.py             # fill missing only
  py -3 scripts/reconstruct_theme_breadth_historical.py --force     # recompute all
  py -3 scripts/reconstruct_theme_breadth_historical.py --dry-run   # show, don't write
  py -3 scripts/reconstruct_theme_breadth_historical.py --report    # coverage summary only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from reconstruct_pcs_components_historical import (  # noqa: E402
    list_commits, candidates_at_commit, find_match,
)

DATA = ROOT / "docs" / "data"
SHADOW_PICKS = DATA / "shadow_picks.jsonl"
OUT_LOG      = DATA / "theme_breadth_reconstructed.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


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

    print(f"Reconstructing theme_breadth for {len(wanted)} ticker/date/pcs triples...")

    commits = list_commits()
    if not commits:
        print("ERROR: no git history found for docs/data/ai_candidates.json", file=sys.stderr)
        sys.exit(1)
    commits_by_date: dict[str, list[str]] = {}
    for h, d in commits:
        commits_by_date.setdefault(d, []).append(h)

    written = n_ok = n_fail = 0
    for ticker, date_str, pcs_val in wanted:
        cand, method, commit_hash = find_match(ticker, date_str, pcs_val, commits_by_date)

        theme = cand.get("theme") if cand else None
        breadth = total = None
        if cand is not None and theme:
            snapshot = candidates_at_commit(commit_hash)
            same_theme = [c for c in snapshot.values() if c.get("theme") == theme]
            total = len(same_theme)
            breadth = sum(1 for c in same_theme if c.get("eligible"))

        row = {
            "ticker": ticker,
            "date": date_str,
            "pcs_at_pick": pcs_val,
            "entry_match_method": method,
            "entry_matched_commit": commit_hash,
            "theme": theme,
            "theme_breadth": breadth,
            "theme_total": total,
            "reconstructed": cand is not None and theme is not None and theme != "",
            "reconstructed_at": datetime.now().isoformat(timespec="seconds"),
        }
        if row["reconstructed"]:
            n_ok += 1
        else:
            n_fail += 1
        if args.dry_run:
            print(f"  {ticker:10} {date_str}  theme={theme}  "
                  f"breadth={breadth}/{total}")
        else:
            append_jsonl(OUT_LOG, row)
        written += 1

    print(f"{'Would write' if args.dry_run else 'Wrote'} {written} rows "
          f"({n_ok} reconstructed, {n_fail} unmatched)"
          + ("" if args.dry_run else f" -> {OUT_LOG}"))


if __name__ == "__main__":
    main()
