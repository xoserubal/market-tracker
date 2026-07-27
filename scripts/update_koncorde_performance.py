"""
update_koncorde_performance.py — fills forward-return labels in the Koncorde
Research Log (docs/data/koncorde_signals_history.jsonl).

Companion to update_performance.py (which labels shadow_picks.jsonl). This one
closes the measurement loop for the Koncorde Research Log: koncorde_calculator.py
logs one row per ticker per day with objective "stealth accumulation" ingredients
(konc_d_blue_z, konc_d_blue_accel, blue slopes, low_break/reclaim, dist_sma20_atr,
volume_vs_20d, …) but leaves ret_/vs_spy_ as null. Without those labels the whole
research log is unfalsifiable — you can't tell which ingredient combination
actually detects the best opportunities. This script backfills them.

Reads:
  docs/data/koncorde_signals_history.jsonl

Writes:
  docs/data/koncorde_signals_history.jsonl  (in-place; adds the fields below)

Fields computed per row (entry = close on first trading day >= row date):
  ret_1w, ret_2w, ret_1m         → absolute ticker return (%) at 5/10/21 trading days
  vs_spy_1w, vs_spy_2w, vs_spy_1m → alpha vs SPY (ret − SPY ret) at the same horizons

A field stays null until enough sessions have elapsed for that horizon, so this
is safe to run every pipeline pass — it fills each row's horizons as they mature.

Usage:
  py -3 scripts/update_koncorde_performance.py             # fill all matured nulls
  py -3 scripts/update_koncorde_performance.py --dry-run   # show changes, don't write
  py -3 scripts/update_koncorde_performance.py --force     # recompute filled rows too
  py -3 scripts/update_koncorde_performance.py --ticker SE # only one ticker
  py -3 scripts/update_koncorde_performance.py --report    # print summary after update
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
RESEARCH_LOG = DATA / "koncorde_signals_history.jsonl"

# Trading-day horizons (N business days after the log date)
HORIZONS: dict[str, int] = {
    "ret_1w": 5,
    "ret_2w": 10,
    "ret_1m": 21,
}
VS_SPY: dict[str, str] = {
    "vs_spy_1w": "ret_1w",
    "vs_spy_2w": "ret_2w",
    "vs_spy_1m": "ret_1m",
}
PERF_FIELDS = list(HORIZONS) + list(VS_SPY)


# ── I/O ──────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for l in lines:
        if l.strip():
            out.append(json.loads(l))
    return out


def save_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def needs_update(row: dict, force: bool) -> bool:
    """True if the row is missing (or force-recomputing) any performance field."""
    if force:
        return True
    return any(row.get(f) is None for f in PERF_FIELDS)


# ── Price download ─────────────────────────────────────────────────────────────

def download_closes(tickers: list[str], start: str, end: str) -> dict[str, "pd.Series"]:
    """
    Bulk-download adjusted closes for *tickers* + SPY from *start* to *end*.
    Returns {ticker: close Series}. Missing tickers are simply absent from the dict.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        print("ERROR: yfinance / pandas not installed.", file=sys.stderr)
        return {}

    all_syms = sorted(set(tickers) | {"SPY"})
    print(f"  Downloading closes for {len(all_syms)} symbols "
          f"({start} to {end})…", end=" ", flush=True)

    try:
        raw = yf.download(
            all_syms, start=start, end=end,
            auto_adjust=True, progress=False, threads=True,
        )
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return {}

    if raw is None or raw.empty:
        print("no data returned.", file=sys.stderr)
        return {}
    print(f"ok ({len(raw)} rows)")

    try:
        if isinstance(raw.columns, pd.MultiIndex):
            close_df = raw["Close"]
        else:
            sym = all_syms[0] if len(all_syms) == 1 else tickers[0]
            close_df = raw[["Close"]].rename(columns={"Close": sym})
    except Exception as exc:
        print(f"  Parse error: {exc}", file=sys.stderr)
        return {}

    result: dict[str, "pd.Series"] = {}
    for sym in close_df.columns:
        s = close_df[sym].dropna()
        if not s.empty:
            result[sym] = s
    return result


def _idx_on_or_after(series_index, date_str: str):
    """Integer position of the first index date >= date_str, or None."""
    try:
        import pandas as pd
        mask = series_index >= pd.Timestamp(date_str)
        if not mask.any():
            return None
        return int(mask.argmax())
    except Exception:
        return None


# ── Metric computation ─────────────────────────────────────────────────────────

def compute_row_metrics(close_tk, close_spy, entry_date: str) -> dict[str, float | None]:
    """
    Forward returns + SPY alpha for one research-log row. Entry price = the
    ticker's close on the first trading day >= entry_date. Values stay None when
    the horizon hasn't elapsed yet or data is missing.
    """
    result: dict[str, float | None] = {f: None for f in PERF_FIELDS}
    try:
        import pandas as pd
        if close_tk is None or close_spy is None or close_tk.empty or close_spy.empty:
            return result

        aligned = pd.concat([close_tk, close_spy], axis=1, join="inner").dropna()
        if aligned.shape[1] != 2:
            return result
        aligned.columns = ["tk", "spy"]

        entry_idx = _idx_on_or_after(aligned.index, entry_date)
        if entry_idx is None:
            return result

        tk_entry = float(aligned["tk"].iloc[entry_idx])
        spy_entry = float(aligned["spy"].iloc[entry_idx])
        if tk_entry <= 0 or spy_entry <= 0:
            return result

        total = len(aligned)
        for field, n in HORIZONS.items():
            idx = entry_idx + n
            if idx < total:
                ret_tk = float(aligned["tk"].iloc[idx]) / tk_entry - 1
                result[field] = round(ret_tk * 100, 2)

        for vs_field, ret_field in VS_SPY.items():
            n = HORIZONS[ret_field]
            idx = entry_idx + n
            if idx < total:
                ret_tk = float(aligned["tk"].iloc[idx]) / tk_entry - 1
                ret_spy = float(aligned["spy"].iloc[idx]) / spy_entry - 1
                result[vs_field] = round((ret_tk - ret_spy) * 100, 2)

    except Exception as exc:
        print(f"    compute error ({entry_date}): {exc}", file=sys.stderr)
    return result


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(rows: list[dict]) -> None:
    import statistics
    print("\n" + "=" * 60)
    print("KONCORDE RESEARCH LOG — coverage")
    print("=" * 60)
    total = len(rows)
    for f in PERF_FIELDS:
        vals = [r[f] for r in rows if r.get(f) is not None]
        if vals:
            print(f"  {f:<12} filled {len(vals):>4}/{total}  "
                  f"mean {statistics.mean(vals):+.2f}%  "
                  f"median {statistics.median(vals):+.2f}%")
        else:
            print(f"  {f:<12} filled    0/{total}  (no matured rows yet)")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill forward-return labels in koncorde_signals_history.jsonl"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute and display changes without writing")
    parser.add_argument("--force", action="store_true",
                        help="Recompute rows even if already filled")
    parser.add_argument("--ticker", metavar="TICKER",
                        help="Update only this ticker")
    parser.add_argument("--report", action="store_true",
                        help="Print coverage summary after updating")
    args = parser.parse_args()

    rows = load_jsonl(RESEARCH_LOG)
    if not rows:
        print("koncorde_signals_history.jsonl is empty or missing.")
        return

    candidates = [
        r for r in rows
        if needs_update(r, args.force)
        and r.get("ticker") and r.get("date")
        and (args.ticker is None or r["ticker"].upper() == args.ticker.upper())
    ]
    if not candidates:
        print(f"Nothing to update ({len(rows)} rows already complete).")
        if args.report:
            print_report(rows)
        return

    print(f"Updating {len(candidates)} rows (of {len(rows)} total)…")

    tickers = sorted({r["ticker"] for r in candidates})
    min_date = min(r["date"] for r in candidates)
    # yfinance `end` is exclusive — add a day so today's closed bar is included.
    end_str = (date.today() + timedelta(days=1)).isoformat()

    closes = download_closes(tickers, start=min_date, end=end_str)
    if not closes or "SPY" not in closes:
        print("ERROR: could not download SPY data. Aborting.", file=sys.stderr)
        sys.exit(1)
    spy = closes["SPY"]

    updated = 0
    skipped_tickers: set[str] = set()
    for row in rows:
        if not needs_update(row, args.force):
            continue
        tk = row.get("ticker", "")
        if not tk or not row.get("date"):
            continue
        if args.ticker and tk.upper() != args.ticker.upper():
            continue

        tk_close = closes.get(tk)
        if tk_close is None:
            if tk not in skipped_tickers:
                print(f"  SKIP {tk}: no price data from yfinance")
                skipped_tickers.add(tk)
            continue

        metrics = compute_row_metrics(tk_close, spy, row["date"])
        new_values = {k: v for k, v in metrics.items()
                      if v is not None and (args.force or row.get(k) is None)}
        if not new_values:
            continue

        if args.dry_run:
            shown = ", ".join(f"{k}={v:+.1f}%" for k, v in new_values.items())
            print(f"  DRY-RUN {tk} ({row['date']}): {shown}")
        else:
            row.update(metrics)
        updated += 1

    if not args.dry_run and updated > 0:
        save_jsonl(RESEARCH_LOG, rows)
        print(f"\nSaved. {updated} rows updated, "
              f"{len(skipped_tickers)} ticker(s) skipped (no price data).")
    elif args.dry_run:
        print(f"\nDry-run: {updated} rows would be updated.")
    else:
        print("No matured horizons to fill yet.")

    if args.report:
        if not args.dry_run and updated > 0:
            rows = load_jsonl(RESEARCH_LOG)
        print_report(rows)


if __name__ == "__main__":
    main()
