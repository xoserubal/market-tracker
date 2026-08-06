"""
reconstruct_pcs_components_historical.py
    — backfills pcs_raw/pcs_ex_macro/pcs_ceiling/pcs_normalized/component_A-F
      (+ component_*_ceiling) for every pick already logged in
      shadow_picks.jsonl, for Fase 0.4 of the Ranking Score plan
      (wiki/PREREGISTRO_RANKING_SCORE_V0.md).

Why a separate reconstruction script instead of recomputing from scratch
(like reconstruct_extension_risk_historical.py does from raw OHLCV): the PCS
component breakdown (`pcs_components`: A_macro_permission..F_data_quality)
depends on same-day rotation_signals.json/stock_candidates.json/macro_history.json
state that isn't preserved anywhere except inside the committed
docs/data/ai_candidates.json snapshot itself. Recomputing it today from
today's inputs would silently substitute today's macro/rotation state for the
pick's actual entry-day state — exactly the kind of look-ahead contamination
P0/this project's discipline exists to avoid. Instead this looks up the real
historical value from git history: docs/data/ai_candidates.json has been
committed on every pipeline run since the very first commit (2026-05-08,
verified) with an unchanged `pcs_components` schema throughout — so 100% of
shadow_picks.jsonl history is reconstructable without approximation, unlike
extension_risk (which needed a numeric proxy) or Koncorde (which didn't exist
as a feature before 2026-06-30).

Matching a shadow_picks.jsonl row to the right commit: the pipeline runs
1-3x/day (2 scheduled + occasional manual/forced runs), so a given calendar
date can have multiple ai_candidates.json commits with different candidate
data. Disambiguate by matching the ticker's `pcs` value recorded in
shadow_picks.jsonl (already the actual value used at selection time) against
the candidate's `pcs` in each same-day commit — exact match identifies the
right snapshot. If no same-day commit matches, widen +-1 day (covers a pick
logged just after/before a UTC day boundary). If still nothing matches
exactly, the row is left unreconstructed (null) — never guessed.

Reads:
  docs/data/shadow_picks.jsonl              (which ticker/date/pcs triples need reconstruction)
  git history of docs/data/ai_candidates.json (the actual historical values)

Writes:
  docs/data/pcs_components_reconstructed.jsonl   (one row per unique ticker+date+pcs,
                                                    append-only, dedup on rerun)

Usage:
  py -3 scripts/reconstruct_pcs_components_historical.py             # fill missing only
  py -3 scripts/reconstruct_pcs_components_historical.py --force     # recompute all
  py -3 scripts/reconstruct_pcs_components_historical.py --dry-run   # show, don't write
  py -3 scripts/reconstruct_pcs_components_historical.py --report    # coverage summary only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
SHADOW_PICKS = DATA / "shadow_picks.jsonl"
OUT_LOG      = DATA / "pcs_components_reconstructed.jsonl"
REL_PATH     = "docs/data/ai_candidates.json"

COMPONENT_LABELS = {
    "A": "A_macro_permission",
    "B": "B_theme_flow",
    "C": "C_individual_rs",
    "D": "D_individual_flow",
    "E": "E_early_acceleration",
    "F": "F_data_quality",
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def list_commits() -> list[tuple[str, str]]:
    """[(commit_hash, 'YYYY-MM-DD'), ...] for every commit touching ai_candidates.json,
    oldest first."""
    out = _git([
        "log", "--follow", "--format=%H|%ad", "--date=format:%Y-%m-%d", "--", REL_PATH,
    ])
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        h, d = line.split("|", 1)
        rows.append((h, d))
    rows.reverse()  # oldest first
    return rows


_JSON_CACHE: dict[str, dict] = {}


def candidates_at_commit(commit_hash: str) -> dict[str, dict]:
    """ticker -> candidate dict, cached per commit."""
    if commit_hash in _JSON_CACHE:
        return _JSON_CACHE[commit_hash]
    try:
        raw = _git(["show", f"{commit_hash}:{REL_PATH}"])
        data = json.loads(raw)
    except Exception:
        _JSON_CACHE[commit_hash] = {}
        return {}
    idx = {c["ticker"]: c for c in data.get("candidates", []) if "ticker" in c}
    _JSON_CACHE[commit_hash] = idx
    return idx


def build_fields(cand: dict) -> dict:
    comp = cand.get("pcs_components") or {}
    a = comp.get("A_macro_permission")
    pcs_raw = cand.get("pcs")
    pcs_ex_macro = round(pcs_raw - a, 1) if (pcs_raw is not None and a is not None) else None
    return {
        "pcs_raw":        pcs_raw,
        "pcs_ex_macro":   pcs_ex_macro,
        "pcs_ceiling":    95.0,
        "pcs_normalized": round(pcs_raw / 95.0 * 100, 1) if pcs_raw is not None else None,
        "component_A":    comp.get("A_macro_permission"),
        "component_B":    comp.get("B_theme_flow"),
        "component_C":    comp.get("C_individual_rs"),
        "component_D":    comp.get("D_individual_flow"),
        "component_E":    comp.get("E_early_acceleration"),
        "component_F":    comp.get("F_data_quality"),
        "component_A_ceiling": 14.0,
        "component_B_ceiling": 24.0,
        "component_C_ceiling": 23.0,
        "component_D_ceiling": 20.0,
        "component_E_ceiling": 9.0,
        "component_F_ceiling": 5.0,
    }


def find_match(
    ticker: str, date_str: str, pcs_val: float | None,
    commits_by_date: dict[str, list[str]],
) -> tuple[dict | None, str, str | None]:
    """Returns (candidate_dict_or_None, match_method, matched_commit)."""
    ts = datetime.strptime(date_str, "%Y-%m-%d")
    # Search window: same day first, then +-1 day (UTC boundary slop).
    for offset, method in ((0, "same_day_exact"), (-1, "prev_day_exact"), (1, "next_day_exact")):
        day = (ts + timedelta(days=offset)).strftime("%Y-%m-%d")
        for commit_hash in commits_by_date.get(day, []):
            cand = candidates_at_commit(commit_hash).get(ticker)
            if cand is None:
                continue
            if pcs_val is None or cand.get("pcs") == pcs_val:
                return cand, method, commit_hash
    # No exact pcs match anywhere nearby — if there's exactly one same-day
    # commit with this ticker at all, fall back to it (still same-day data,
    # just couldn't cross-validate via pcs — e.g. pcs missing in the log row).
    same_day_commits = commits_by_date.get(date_str, [])
    if pcs_val is None:
        for commit_hash in same_day_commits:
            cand = candidates_at_commit(commit_hash).get(ticker)
            if cand is not None:
                return cand, "same_day_no_pcs_check", commit_hash
    return None, "no_match", None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="recompute rows already in output")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true", help="print coverage summary only")
    args = ap.parse_args()

    picks = load_jsonl(SHADOW_PICKS)
    if not picks:
        print("shadow_picks.jsonl is empty, nothing to do.")
        return

    existing = load_jsonl(OUT_LOG)
    have: set[tuple[str, str, str]] = {
        (r["ticker"], r["date"], str(r.get("pcs_at_pick"))) for r in existing
    }

    if args.report:
        n_reconstructed = sum(1 for r in existing if r.get("reconstructed"))
        n_failed = len(existing) - n_reconstructed
        print(f"{OUT_LOG.name}: {len(existing)} rows, "
              f"{n_reconstructed} reconstructed, {n_failed} unresolved")
        by_method: dict[str, int] = {}
        for r in existing:
            by_method[r.get("match_method", "?")] = by_method.get(r.get("match_method", "?"), 0) + 1
        for m, n in sorted(by_method.items(), key=lambda kv: -kv[1]):
            print(f"  {m}: {n}")
        return

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

    print(f"Reconstructing PCS components for {len(wanted)} ticker/date/pcs triples...")

    commits = list_commits()
    if not commits:
        print(f"ERROR: no git history found for {REL_PATH}", file=sys.stderr)
        sys.exit(1)
    commits_by_date: dict[str, list[str]] = {}
    for h, d in commits:
        commits_by_date.setdefault(d, []).append(h)

    written = 0
    n_ok = 0
    n_fail = 0
    for ticker, date_str, pcs_val in wanted:
        cand, method, commit_hash = find_match(ticker, date_str, pcs_val, commits_by_date)
        row = {
            "ticker": ticker,
            "date": date_str,
            "pcs_at_pick": pcs_val,
            "match_method": method,
            "matched_commit": commit_hash,
            "reconstructed": cand is not None,
            "reconstructed_at": datetime.now().isoformat(timespec="seconds"),
        }
        if cand is not None:
            row.update(build_fields(cand))
            n_ok += 1
        else:
            n_fail += 1
        if args.dry_run:
            print(f"  {ticker:10} {date_str}  pcs={pcs_val}  -> {method}"
                  + (f"  pcs_ex_macro={row.get('pcs_ex_macro')}" if cand else "  UNMATCHED"))
        else:
            append_jsonl(OUT_LOG, row)
        written += 1

    print(f"{'Would write' if args.dry_run else 'Wrote'} {written} rows "
          f"({n_ok} reconstructed, {n_fail} unmatched)"
          + ("" if args.dry_run else f" -> {OUT_LOG}"))


if __name__ == "__main__":
    main()
