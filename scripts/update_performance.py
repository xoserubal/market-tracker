"""
update_performance.py — fills ret_* fields in shadow_picks.jsonl

Reads:
  docs/data/shadow_picks.jsonl
  docs/data/baselines.jsonl   (for --report comparison)

Writes:
  docs/data/shadow_picks.jsonl  (in-place update of performance fields)

Fields computed per pick:
  ret_1d, ret_3d, ret_1w, ret_2w, ret_1m, ret_3m
      → absolute ticker return (%) at N trading days after entry date
  vs_spy_1m
      → alpha vs SPY at 1 month  (ret_1m - spy_ret_1m)
  max_gain_1m
      → max intraday high vs entry close in 1-month window (%)
  max_drawdown_1m
      → max intraday low vs entry close in 1-month window (%, negative = loss)

Entry price:
  If entry_price is explicitly set in the pick, it is used as the denominator
  for all return calculations (matches actual paper-trade fill price).
  Otherwise, the yfinance close on the entry date (first trading day >= date) is used.

Usage:
  py -3 scripts/update_performance.py               # fill all null fields
  py -3 scripts/update_performance.py --dry-run     # show changes without writing
  py -3 scripts/update_performance.py --force       # recompute already-filled rows
  py -3 scripts/update_performance.py --report      # print summary after update
  py -3 scripts/update_performance.py --ticker CVE  # update only one ticker
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
SHADOW_PICKS  = DATA / "shadow_picks.jsonl"
BASELINES_LOG = DATA / "baselines.jsonl"

# Trading-day horizons (N business days after entry)
HORIZONS: dict[str, int] = {
    "ret_1d":  1,
    "ret_3d":  3,
    "ret_1w":  5,
    "ret_2w":  10,
    "ret_1m":  21,
    "ret_3m":  63,
}
PERF_FIELDS = list(HORIZONS) + ["vs_spy_1m", "max_gain_1m", "max_drawdown_1m"]


# ── I/O ────────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(l) for l in lines if l.strip()]


def save_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def needs_update(pick: dict, force: bool) -> bool:
    """True if the pick has at least one null performance field to fill."""
    if force:
        return True
    return any(pick.get(f) is None for f in PERF_FIELDS)


# ── Price download ──────────────────────────────────────────────────────────────

def download_prices(
    tickers: list[str],
    start: str,
    end: str,
) -> dict[str, dict]:
    """
    Download OHLCV for *tickers* + SPY from *start* to *end*.
    Returns {ticker: {"close": Series, "high": Series, "low": Series}}.
    Missing tickers return an empty dict.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        print("ERROR: yfinance / pandas not installed.", file=sys.stderr)
        return {}

    all_syms = sorted(set(tickers) | {"SPY"})
    print(f"  Downloading prices for {len(all_syms)} symbols "
          f"({start} to {end})...", end=" ", flush=True)

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

    # Normalise MultiIndex vs single-ticker layout
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            close_df = raw["Close"].dropna(how="all")
            high_df  = raw["High"].dropna(how="all")  if "High"  in raw else pd.DataFrame()
            low_df   = raw["Low"].dropna(how="all")   if "Low"   in raw else pd.DataFrame()
        else:
            # Single ticker: raw columns are field names
            sym = all_syms[0] if len(all_syms) == 1 else tickers[0]
            close_df = raw[["Close"]].rename(columns={"Close": sym})
            high_df  = raw[["High"]].rename(columns={"High":  sym}) if "High"  in raw else pd.DataFrame()
            low_df   = raw[["Low"]].rename(columns={"Low":   sym}) if "Low"   in raw else pd.DataFrame()
    except Exception as exc:
        print(f"  Parse error: {exc}", file=sys.stderr)
        return {}

    result: dict[str, dict] = {}
    for sym in all_syms:
        if sym not in close_df.columns:
            result[sym] = {}
            continue
        entry: dict[str, Any] = {
            "close": close_df[sym].dropna(),
        }
        if not high_df.empty and sym in high_df.columns:
            entry["high"] = high_df[sym].dropna()
        if not low_df.empty and sym in low_df.columns:
            entry["low"] = low_df[sym].dropna()
        result[sym] = entry

    return result


# ── Metric computation ──────────────────────────────────────────────────────────

def _idx_on_or_after(series_index, date_str: str):
    """
    Return the integer position of the first date >= date_str in series_index.
    Returns None if no such date exists.
    """
    try:
        import pandas as pd
        td = pd.Timestamp(date_str)
        mask = series_index >= td
        if not mask.any():
            return None
        return int(mask.argmax())
    except Exception:
        return None


def compute_metrics(
    ticker_data: dict,
    spy_data: dict,
    entry_date: str,
    entry_price_override: float | None,
) -> dict[str, float | None]:
    """
    Compute all PERF_FIELDS for one pick.
    Returns a dict with all field names; values are None when data is unavailable.
    """
    result: dict[str, float | None] = {f: None for f in PERF_FIELDS}

    try:
        import pandas as pd

        close_tk  = ticker_data.get("close")
        close_spy = spy_data.get("close")
        high_tk   = ticker_data.get("high")
        low_tk    = ticker_data.get("low")

        if close_tk is None or close_spy is None:
            return result
        if close_tk.empty or close_spy.empty:
            return result

        # Align on common trading days
        aligned = pd.concat([close_tk, close_spy], axis=1, join="inner").dropna()
        if aligned.shape[1] != 2:
            return result
        aligned.columns = ["tk", "spy"]

        # Entry index
        entry_idx = _idx_on_or_after(aligned.index, entry_date)
        if entry_idx is None:
            return result

        # Entry prices
        if entry_price_override is not None and entry_price_override > 0:
            tk_entry  = entry_price_override
        else:
            tk_entry  = float(aligned["tk"].iloc[entry_idx])
        spy_entry = float(aligned["spy"].iloc[entry_idx])

        if tk_entry <= 0 or spy_entry <= 0:
            return result

        total = len(aligned)

        # Point-in-time absolute returns
        for field, n in HORIZONS.items():
            idx = entry_idx + n
            if idx < total:
                result[field] = round(
                    (float(aligned["tk"].iloc[idx]) / tk_entry - 1) * 100, 2
                )
            # else: leave None (data not yet available)

        # vs_spy_1m  (alpha at 1 month)
        idx_1m = entry_idx + HORIZONS["ret_1m"]
        if idx_1m < total:
            ret_tk  = float(aligned["tk"].iloc[idx_1m])  / tk_entry  - 1
            ret_spy = float(aligned["spy"].iloc[idx_1m]) / spy_entry - 1
            result["vs_spy_1m"] = round((ret_tk - ret_spy) * 100, 2)

        # max_gain_1m / max_drawdown_1m  (intraday high/low in 1-month window)
        end_1m = min(entry_idx + HORIZONS["ret_1m"] + 1, total)
        win_start = entry_idx + 1  # day after entry

        if win_start < end_1m:
            # Prefer intraday High/Low; fall back to close
            if high_tk is not None and not high_tk.empty:
                h_aligned = high_tk.reindex(aligned.index)
                window_h  = h_aligned.iloc[win_start:end_1m].dropna()
            else:
                window_h = aligned["tk"].iloc[win_start:end_1m]

            if low_tk is not None and not low_tk.empty:
                l_aligned = low_tk.reindex(aligned.index)
                window_l  = l_aligned.iloc[win_start:end_1m].dropna()
            else:
                window_l = aligned["tk"].iloc[win_start:end_1m]

            if len(window_h) > 0:
                result["max_gain_1m"]     = round(
                    (float(window_h.max()) / tk_entry - 1) * 100, 2
                )
            if len(window_l) > 0:
                result["max_drawdown_1m"] = round(
                    (float(window_l.min()) / tk_entry - 1) * 100, 2
                )

    except Exception as exc:
        print(f"    compute error for {entry_date}: {exc}", file=sys.stderr)

    return result


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(picks: list[dict]) -> None:
    """
    Print a human-readable performance summary grouped by model type.
    Separates active-model picks (valid_for_performance_tracking=True) from shadows.
    """
    import statistics

    def _pct(v):
        return f"{v:+.1f}%" if v is not None else "   n/a"

    print("\n" + "=" * 72)
    print("PERFORMANCE REPORT — shadow_picks.jsonl")
    print("=" * 72)

    # Only picks that have at least ret_1w filled
    tracked = [
        p for p in picks
        if p.get("ret_1w") is not None
        and p.get("valid_for_performance_tracking", True)  # include early picks without flag
        and p.get("active_model", True)
    ]

    if not tracked:
        print("No picks with sufficient history yet (need ≥1 week of data).")
        return

    # Group by entry date for clarity
    by_date: dict[str, list[dict]] = {}
    for p in tracked:
        by_date.setdefault(p["date"], []).append(p)

    header = f"{'Date':<12} {'Ticker':<10} {'Port':<26} {'1d':>6} {'1w':>6} {'2w':>7} {'1m':>7} {'vSPY1m':>8}"
    print(header)
    print("-" * 72)

    all_vs_spy: list[float] = []
    all_ret_1m: list[float] = []

    for dt in sorted(by_date):
        for p in sorted(by_date[dt], key=lambda x: x.get("ticker", "")):
            row = (
                f"{p['date']:<12} "
                f"{p['ticker']:<10} "
                f"{p.get('portfolio',''):<26} "
                f"{_pct(p.get('ret_1d')):>6} "
                f"{_pct(p.get('ret_1w')):>6} "
                f"{_pct(p.get('ret_2w')):>7} "
                f"{_pct(p.get('ret_1m')):>7} "
                f"{_pct(p.get('vs_spy_1m')):>8}"
            )
            print(row)
            if p.get("vs_spy_1m") is not None:
                all_vs_spy.append(p["vs_spy_1m"])
            if p.get("ret_1m") is not None:
                all_ret_1m.append(p["ret_1m"])

    print("-" * 72)

    if all_vs_spy:
        avg_alpha = statistics.mean(all_vs_spy)
        wins      = sum(1 for v in all_vs_spy if v > 0)
        print(f"\n  Active picks with 1m data:  {len(all_vs_spy)}")
        print(f"  Avg ret_1m (abs):           {statistics.mean(all_ret_1m):+.1f}%")
        print(f"  Avg alpha vs SPY (1m):      {avg_alpha:+.1f}%")
        print(f"  Win rate vs SPY (1m):       {wins}/{len(all_vs_spy)} = {wins/len(all_vs_spy)*100:.0f}%")
    else:
        print("\n  Not enough picks with 1-month history yet.")

    # Baseline comparison (if baselines.jsonl has matching dates)
    baselines = load_jsonl(BASELINES_LOG)
    if baselines and all_vs_spy:
        _print_baseline_comparison(picks, baselines)

    print()


def _print_baseline_comparison(picks: list[dict], baselines: list[dict]) -> None:
    """
    For each baseline snapshot that has a corresponding active pick in the same run,
    show how the model pick vs top-PCS mechanical baseline performed at 1 month.
    """
    print("\n" + "-" * 72)
    print("BASELINE COMPARISON (model pick vs top-3 PCS mechanical baseline)")
    print("-" * 72)
    print(f"{'Run date':<12} {'Model ticker':<12} {'ModelAlpha':>10}  {'Baseline top-PCS tickers'}")
    print("-" * 72)

    # Build quick lookup: run_id → list of active picks
    picks_by_run: dict[str, list[dict]] = {}
    for p in picks:
        rid = p.get("run_id")
        if rid and p.get("valid_for_performance_tracking") and p.get("active_model"):
            picks_by_run.setdefault(rid, []).append(p)

    shown = 0
    for b in baselines:
        rid = b.get("run_id")
        if rid not in picks_by_run:
            continue
        run_picks = picks_by_run[rid]
        with_alpha = [p for p in run_picks if p.get("vs_spy_1m") is not None]
        if not with_alpha:
            continue

        avg_alpha = sum(p["vs_spy_1m"] for p in with_alpha) / len(with_alpha)
        baseline_tickers = " / ".join(
            t["ticker"] for t in (b.get("top_pcs") or [])[:3]
        )
        model_tickers = ", ".join(p["ticker"] for p in with_alpha)
        print(
            f"{b['date']:<12} {model_tickers:<12} {avg_alpha:>+9.1f}%  "
            f"top-PCS: {baseline_tickers}"
        )
        shown += 1

    if shown == 0:
        print("  No matching run_ids with complete 1m data yet.")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill ret_* performance fields in shadow_picks.jsonl"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute and display changes without writing to disk")
    parser.add_argument("--force", action="store_true",
                        help="Recompute metrics even if already filled")
    parser.add_argument("--report", action="store_true",
                        help="Print performance summary report after updating")
    parser.add_argument("--ticker", metavar="TICKER",
                        help="Update only this ticker (e.g. CVE, MLX.AX)")
    args = parser.parse_args()

    # ── Load picks ──
    picks = load_jsonl(SHADOW_PICKS)
    if not picks:
        print("shadow_picks.jsonl is empty or missing.")
        return

    # ── Filter picks that need updating ──
    candidates = [
        p for p in picks
        if needs_update(p, args.force)
        and p.get("ticker")
        and (args.ticker is None or p["ticker"].upper() == args.ticker.upper())
    ]

    if not candidates:
        print(f"Nothing to update ({len(picks)} picks already complete).")
        if args.report:
            print_report(picks)
        return

    print(f"Updating {len(candidates)} pick rows "
          f"(of {len(picks)} total) …")

    # ── Determine date range for download ──
    entry_dates = [p["date"] for p in candidates if p.get("date")]
    min_date    = min(entry_dates)
    # Add buffer beyond today to ensure 3m horizon is reachable eventually
    today_str   = date.today().isoformat()

    # ── Collect unique tickers ──
    tickers = sorted({p["ticker"] for p in candidates})

    # ── Download prices ──
    prices = download_prices(tickers, start=min_date, end=today_str)
    if not prices or "SPY" not in prices or prices["SPY"].get("close") is None:
        print("ERROR: Could not download SPY data. Aborting.", file=sys.stderr)
        sys.exit(1)

    spy_data = prices["SPY"]

    # ── Compute and apply metrics ──
    updated_count  = 0
    skipped_count  = 0
    failed_tickers: set[str] = set()

    for pick in picks:
        if not needs_update(pick, args.force):
            continue
        if args.ticker and pick.get("ticker", "").upper() != args.ticker.upper():
            continue

        ticker = pick.get("ticker", "")
        if not ticker:
            continue

        tk_data = prices.get(ticker)
        tk_close = tk_data.get("close") if tk_data else None
        if tk_close is None or tk_close.empty:
            if ticker not in failed_tickers:
                print(f"  SKIP {ticker}: no price data from yfinance")
                failed_tickers.add(ticker)
            skipped_count += 1
            continue

        metrics = compute_metrics(
            tk_data,
            spy_data,
            pick["date"],
            pick.get("entry_price"),
        )

        # Only count as updated if at least one new value was filled
        new_values = {k: v for k, v in metrics.items() if v is not None and pick.get(k) is None}
        if not new_values:
            continue

        if args.dry_run:
            filled = ", ".join(f"{k}={v:+.1f}%" for k, v in new_values.items()
                               if isinstance(v, float))
            print(f"  DRY-RUN {ticker} ({pick['date']}): {filled}")
        else:
            pick.update(metrics)

        updated_count += 1

    # ── Save ──
    if not args.dry_run and updated_count > 0:
        save_jsonl(SHADOW_PICKS, picks)
        print(f"\nSaved. {updated_count} picks updated, "
              f"{skipped_count} skipped (no price data).")
    elif args.dry_run:
        print(f"\nDry-run: {updated_count} picks would be updated.")
    else:
        print("No new data to fill.")

    # ── Optional report ──
    if args.report:
        # Re-load if we actually wrote changes
        if not args.dry_run and updated_count > 0:
            picks = load_jsonl(SHADOW_PICKS)
        print_report(picks)


if __name__ == "__main__":
    main()
