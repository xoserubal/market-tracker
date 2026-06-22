"""
compare_vs_baselines.py -- AI picks vs mechanical baselines + EXIT simulation

Sections:
  1. Per-run comparativa: AI picks avg ret_1m vs top_pcs / top_rot_score / top_ret_4w
  2. Overall aggregate + win rates
  3. Per-portfolio breakdown
  4. EXIT simulation (using payload PCS/rot_score history for tickers that reappear)
  5. spike_flag analysis (from payload candidates at entry date)
  6. Extension risk analysis (from shadow_picks fields)

Output:
  Console report (human-readable)
  docs/data/baseline_comparison.json  (machine-readable)

Usage:
  py -3 scripts/compare_vs_baselines.py
  py -3 scripts/compare_vs_baselines.py --no-fetch    # skip yfinance (use cached JSON)
  py -3 scripts/compare_vs_baselines.py --save-cache  # save fetched prices to cache
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
SHADOW_PICKS  = DATA / "shadow_picks.jsonl"
BASELINES_LOG = DATA / "baselines.jsonl"
PAYLOAD_DIR   = DATA / "ai_model_payloads"
OUT_JSON      = DATA / "baseline_comparison.json"
CACHE_JSON    = DATA / "_baseline_price_cache.json"

# Portfolio pcs_min_entry thresholds (matches paper_trading.py mandates)
PCS_MIN_ENTRY: dict[str, float] = {
    "HIGH_CONVICTION":              82.0,
    "CONFIRMED_FLOW_LEADERS":       75.0,
    "EARLY_ROTATION":               68.0,
    "MACRO_THEMATIC_BENEFICIARIES": 62.0,
    "REJECTED_HIGH_SCORE":          75.0,
}

# -- I/O helpers ----------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_payloads() -> dict[str, dict]:
    """Returns {date_str: payload} for all stored payloads."""
    result: dict[str, dict] = {}
    if not PAYLOAD_DIR.exists():
        return result
    for f in sorted(PAYLOAD_DIR.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
            d = f.stem[:10]
            result[d] = payload
        except Exception:
            pass
    return result


def _safe_mean(vals: list[float | None]) -> float | None:
    clean = [v for v in vals if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _pct(v: float | None, w: int = 7) -> str:
    return f"{v:+.1f}%" .rjust(w) if v is not None else "   n/a".rjust(w)


# -- Price fetching --------------------------------------------------------------

def fetch_returns_yfinance(
    requests: list[tuple[str, str]],   # [(ticker, entry_date), ...]
    end_date: str,
) -> dict[tuple[str, str], float | None]:
    """
    For each (ticker, entry_date), compute 21-trading-day return.
    Returns {(ticker, entry_date): ret_1m_pct or None}.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        print("ERROR: yfinance/pandas not installed.", file=sys.stderr)
        return {}

    tickers = sorted({t for t, _ in requests} | {"SPY"})
    min_date = min(d for _, d in requests)

    print(f"  Downloading prices for {len(tickers)} baseline tickers "
          f"({min_date} to {end_date})...", end=" ", flush=True)

    try:
        raw = yf.download(tickers, start=min_date, end=end_date,
                          auto_adjust=True, progress=False, threads=True)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return {}

    if raw is None or raw.empty:
        print("no data returned.", file=sys.stderr)
        return {}

    print(f"ok ({len(raw)} rows)")

    if isinstance(raw.columns, pd.MultiIndex):
        close_df = raw["Close"].dropna(how="all")
    else:
        sym = tickers[0]
        close_df = raw[["Close"]].rename(columns={"Close": sym})

    result: dict[tuple[str, str], float | None] = {}

    for ticker, entry_date in requests:
        key = (ticker, entry_date)
        try:
            if ticker not in close_df.columns or "SPY" not in close_df.columns:
                result[key] = None
                continue

            aligned = close_df[[ticker, "SPY"]].dropna()
            td = pd.Timestamp(entry_date)
            mask = aligned.index >= td
            if not mask.any():
                result[key] = None
                continue

            entry_idx = int(mask.argmax())
            target_idx = entry_idx + 21

            if target_idx >= len(aligned):
                result[key] = None
                continue

            entry_price = float(aligned[ticker].iloc[entry_idx])
            exit_price  = float(aligned[ticker].iloc[target_idx])

            if entry_price <= 0:
                result[key] = None
                continue

            result[key] = round((exit_price / entry_price - 1) * 100, 2)
        except Exception:
            result[key] = None

    return result


def fetch_price_at_date(
    ticker: str,
    target_date: str,
    close_df: Any,          # pandas DataFrame (already downloaded)
) -> float | None:
    """Return close price on or after target_date for ticker."""
    try:
        import pandas as pd
        if ticker not in close_df.columns:
            return None
        col = close_df[ticker].dropna()
        mask = col.index >= pd.Timestamp(target_date)
        if not mask.any():
            return None
        return round(float(col[mask].iloc[0]), 4)
    except Exception:
        return None


# -- Build run groups ------------------------------------------------------------

def build_run_groups(picks: list[dict]) -> dict[str, list[dict]]:
    """
    Group picks by run_id when available, else by date.
    Only includes active_model=True picks.
    Deduplicates by (ticker, portfolio) within each run.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    seen: dict[str, set] = defaultdict(set)

    for p in picks:
        if not p.get("active_model"):
            continue
        run_key = p.get("run_id") or p.get("date", "unknown")
        dedup_key = (p.get("ticker"), p.get("portfolio"))
        if dedup_key in seen[run_key]:
            continue
        seen[run_key].add(dedup_key)
        groups[run_key].append(p)

    return dict(groups)


# -- Build baselines per run -----------------------------------------------------

def build_baselines_index(
    baselines: list[dict],
    payloads: dict[str, dict],
) -> dict[str, dict]:
    """
    Returns {run_key: {top_pcs: [...], top_rot_score: [...], top_ret_4w: [...]}}.
    Prefers baselines.jsonl; falls back to virtual baseline from payload top-3 PCS.
    run_key = run_id from baselines.jsonl, or date for virtual baselines.
    """
    index: dict[str, dict] = {}

    # From baselines.jsonl (authoritative)
    for b in baselines:
        run_id = b.get("run_id") or b.get("date")
        if run_id:
            index[run_id] = {
                "date":          b["date"],
                "top_pcs":       b.get("top_pcs", []),
                "top_rot_score": b.get("top_rot_score", []),
                "top_ret_4w":    b.get("top_ret_4w", []),
                "source":        "baselines.jsonl",
            }

    # Virtual baselines from payloads (for dates not covered)
    covered_dates = {v["date"] for v in index.values()}
    for date_str, payload in payloads.items():
        if date_str in covered_dates:
            continue
        candidates = [c for c in payload.get("candidates", []) if c.get("eligible")]
        if not candidates:
            continue
        by_pcs     = sorted(candidates, key=lambda c: c.get("pcs", 0),       reverse=True)[:3]
        by_rot     = sorted(candidates, key=lambda c: c.get("rot_score", 0), reverse=True)[:3]
        by_ret4w   = sorted(candidates, key=lambda c: c.get("ret_4w_vs_spy", 0), reverse=True)[:3]
        index[date_str] = {
            "date":          date_str,
            "top_pcs":       [{"ticker": c["ticker"], "value": c.get("pcs")}       for c in by_pcs],
            "top_rot_score": [{"ticker": c["ticker"], "value": c.get("rot_score")} for c in by_rot],
            "top_ret_4w":    [{"ticker": c["ticker"], "value": c.get("ret_4w_vs_spy")} for c in by_ret4w],
            "source":        "payload_virtual",
        }

    return index


def match_baseline(run_key: str, baselines_index: dict[str, dict]) -> dict | None:
    """Try run_id match, then date prefix match."""
    if run_key in baselines_index:
        return baselines_index[run_key]
    date_prefix = run_key[:10]
    if date_prefix in baselines_index:
        return baselines_index[date_prefix]
    return None


# -- EXIT simulation -------------------------------------------------------------

def simulate_exits(
    picks: list[dict],
    payloads: dict[str, dict],
) -> list[dict]:
    """
    For each AI pick, scan subsequent payloads where the ticker appears as a candidate.
    Simulate EXIT rule: (pcs < pcs_min_entry AND streak_weeks <= 1) OR rot_score <= 2
    Returns list of exit simulation results.
    """
    results = []
    sorted_payload_dates = sorted(payloads.keys())

    for pick in picks:
        if not pick.get("active_model"):
            continue
        ticker    = pick.get("ticker", "")
        portfolio = pick.get("portfolio", "")
        entry_date = pick.get("date", "")
        pcs_min   = PCS_MIN_ENTRY.get(portfolio, 75.0)
        ret_1m    = pick.get("ret_1m")

        # Track ticker in subsequent payloads (after entry date)
        history = []
        for pd_date in sorted_payload_dates:
            if pd_date <= entry_date:
                continue
            cands = payloads[pd_date].get("candidates", [])
            match = next((c for c in cands if c.get("ticker") == ticker), None)
            if match:
                history.append({
                    "date":         pd_date,
                    "pcs":          match.get("pcs"),
                    "rot_score":    match.get("rot_score"),
                    "streak_weeks": match.get("streak_weeks"),
                })

        if not history:
            results.append({
                "ticker":       ticker,
                "portfolio":    portfolio,
                "entry_date":   entry_date,
                "ret_1m":       ret_1m,
                "exit_simulated": False,
                "note":         "not_in_subsequent_payloads",
            })
            continue

        # Find first EXIT signal
        exit_event = None
        for h in history:
            pcs          = h.get("pcs")
            rot_score    = h.get("rot_score")
            streak_weeks = h.get("streak_weeks")

            triggered_pcs = (pcs is not None and pcs < pcs_min
                             and streak_weeks is not None and streak_weeks <= 1)
            triggered_rot = (rot_score is not None and rot_score <= 2)

            if triggered_pcs or triggered_rot:
                reason = []
                if triggered_pcs:
                    reason.append(f"pcs={pcs}<{pcs_min} + streak={streak_weeks}")
                if triggered_rot:
                    reason.append(f"rot_score={rot_score}<=2")
                exit_event = {
                    "date":   h["date"],
                    "reason": " & ".join(reason),
                    "pcs":    pcs,
                    "rot":    rot_score,
                }
                break

        results.append({
            "ticker":           ticker,
            "portfolio":        portfolio,
            "entry_date":       entry_date,
            "pcs_min_entry":    pcs_min,
            "ret_1m":           ret_1m,
            "payload_history":  history,
            "exit_simulated":   exit_event is not None,
            "exit_event":       exit_event,
            "note":             f"{len(history)} payload snapshots tracked",
        })

    return results


# -- spike_flag lookup -----------------------------------------------------------

def build_spike_index(payloads: dict[str, dict]) -> dict[tuple[str, str], bool]:
    """Returns {(ticker, date): spike_flag} from payload candidates."""
    idx: dict[tuple[str, str], bool] = {}
    for date_str, payload in payloads.items():
        for c in payload.get("candidates", []):
            t = c.get("ticker")
            if t:
                idx[(t, date_str)] = bool(c.get("spike_flag", False))
    return idx


def _fill_exit_returns(
    exit_sims: list[dict],
    picks_lookup: list[dict],
) -> list[dict]:
    """
    For simulated EXITs, fetch price at exit date and compute ret_at_exit.
    pick.entry_price used when available; else yfinance close on entry_date.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return exit_sims

    triggered = [e for e in exit_sims if e.get("exit_simulated") and e.get("exit_event")]
    if not triggered:
        return exit_sims

    # Build entry_price lookup from picks
    entry_price_map: dict[tuple, float | None] = {
        (p["ticker"], p["date"]): p.get("entry_price")
        for p in picks_lookup
    }

    tickers   = list({e["ticker"] for e in triggered})
    min_date  = min(e["entry_date"] for e in triggered)
    today_str = date.today().isoformat()

    print(f"  Fetching exit-date prices for {len(tickers)} tickers...", end=" ", flush=True)
    try:
        raw = yf.download(tickers, start=min_date, end=today_str,
                          auto_adjust=True, progress=False, threads=True)
    except Exception as exc:
        print(f"FAILED: {exc}")
        return exit_sims

    if raw is None or raw.empty:
        print("no data")
        return exit_sims
    print(f"ok ({len(raw)} rows)")

    if isinstance(raw.columns, pd.MultiIndex):
        close_df = raw["Close"].dropna(how="all")
    else:
        sym = tickers[0]
        close_df = raw[["Close"]].rename(columns={"Close": sym})

    for sim in triggered:
        ticker     = sim["ticker"]
        entry_date = sim["entry_date"]
        exit_date  = sim["exit_event"]["date"]

        if ticker not in close_df.columns:
            continue

        col = close_df[ticker].dropna()
        try:
            # Entry price
            ep = entry_price_map.get((ticker, entry_date))
            if ep is None or ep <= 0:
                em = col.index >= pd.Timestamp(entry_date)
                if not em.any():
                    continue
                ep = float(col[em].iloc[0])

            # Exit price (first trading day >= simulated exit date)
            xm = col.index >= pd.Timestamp(exit_date)
            if not xm.any():
                continue
            xp = float(col[xm].iloc[0])

            sim["ret_at_exit"] = round((xp / ep - 1) * 100, 2)
            sim["entry_price_used"] = round(ep, 4)
            sim["exit_price"] = round(xp, 4)
        except Exception:
            pass

    return exit_sims


# -- Main analysis ---------------------------------------------------------------

def run_analysis(no_fetch: bool = False, save_cache: bool = False) -> dict:
    print("Loading data...")
    picks     = load_jsonl(SHADOW_PICKS)
    baselines = load_jsonl(BASELINES_LOG)
    payloads  = load_payloads()

    if not picks:
        print("ERROR: shadow_picks.jsonl is empty.")
        sys.exit(1)

    print(f"  {len(picks)} picks, {len(baselines)} baselines, "
          f"{len(payloads)} payloads")

    # -- Build indexes --
    baselines_index = build_baselines_index(baselines, payloads)
    spike_idx       = build_spike_index(payloads)
    run_groups      = build_run_groups(picks)

    # -- Filter: only picks with ret_1m --
    picks_with_1m = [p for p in picks if p.get("ret_1m") is not None]
    print(f"  {len(picks_with_1m)} picks with ret_1m available")

    # -- Collect baseline ticker requests --
    # For each run, gather the baseline tickers we need ret_1m for
    baseline_requests: list[tuple[str, str]] = []   # (ticker, date)
    runs_with_data: list[dict] = []

    for run_key, run_picks in sorted(run_groups.items()):
        run_picks_1m = [p for p in run_picks if p.get("ret_1m") is not None]
        if not run_picks_1m:
            continue

        bl = match_baseline(run_key, baselines_index)
        if bl is None:
            continue

        entry_date = run_picks_1m[0]["date"]

        for bl_type in ("top_pcs", "top_rot_score", "top_ret_4w"):
            for entry in bl.get(bl_type, []):
                t = entry.get("ticker")
                if t:
                    baseline_requests.append((t, entry_date))

        runs_with_data.append({
            "run_key":   run_key,
            "date":      entry_date,
            "picks":     run_picks_1m,
            "baseline":  bl,
        })

    # -- Fetch or load cached baseline returns --
    price_cache: dict[str, float | None] = {}
    cache_key_fn = lambda t, d: f"{t}|{d}"

    if CACHE_JSON.exists() and no_fetch:
        print("  Loading cached baseline prices...")
        raw_cache = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
        price_cache = raw_cache
    elif baseline_requests:
        today_str = date.today().isoformat()
        fetched = fetch_returns_yfinance(
            list(set(baseline_requests)),
            end_date=today_str,
        )
        for (t, d), v in fetched.items():
            price_cache[cache_key_fn(t, d)] = v
        if save_cache:
            CACHE_JSON.write_text(
                json.dumps(price_cache, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def bl_ret(ticker: str, entry_date: str) -> float | None:
        return price_cache.get(cache_key_fn(ticker, entry_date))

    # -- Per-run results --
    run_results: list[dict] = []

    for rd in runs_with_data:
        run_picks = rd["picks"]
        bl        = rd["baseline"]
        entry_date = rd["date"]

        ai_ret_1m  = _safe_mean([p.get("ret_1m") for p in run_picks])
        ai_vs_spy  = _safe_mean([p.get("vs_spy_1m") for p in run_picks])

        bl_results = {}
        for bl_type in ("top_pcs", "top_rot_score", "top_ret_4w"):
            tickers_in_bl = [e["ticker"] for e in bl.get(bl_type, [])]
            rets = [bl_ret(t, entry_date) for t in tickers_in_bl]
            bl_results[bl_type] = {
                "tickers": tickers_in_bl,
                "avg_ret":  _safe_mean(rets),
                "rets":     rets,
            }

        run_results.append({
            "run_key":   rd["run_key"],
            "date":      entry_date,
            "baseline_source": bl.get("source"),
            "ai_picks":  [{"ticker": p["ticker"], "portfolio": p["portfolio"],
                           "ret_1m": p.get("ret_1m"), "vs_spy_1m": p.get("vs_spy_1m")}
                          for p in run_picks],
            "ai_ret_1m":  ai_ret_1m,
            "ai_vs_spy":  ai_vs_spy,
            "baselines":  bl_results,
        })

    # -- EXIT simulation --
    active_picks_1m = [p for p in picks if p.get("active_model") and p.get("ret_1m") is not None]
    print(f"\nRunning EXIT simulation for {len(active_picks_1m)} active picks with ret_1m...")
    exit_sims = simulate_exits(active_picks_1m, payloads)

    # -- Compute actual returns at simulated exit dates --
    if not no_fetch:
        exit_sims = _fill_exit_returns(exit_sims, active_picks_1m)

    # -- spike_flag analysis --
    spike_groups: dict[bool, list[float]] = {True: [], False: []}
    no_spike_data: int = 0

    for p in picks_with_1m:
        if not p.get("active_model"):
            continue
        sf = spike_idx.get((p["ticker"], p["date"]))
        if sf is None:
            no_spike_data += 1
            continue
        spike_groups[sf].append(p["ret_1m"])

    # -- Extension risk analysis --
    ext_groups: dict[str, list[float]] = defaultdict(list)
    for p in picks_with_1m:
        if not p.get("active_model"):
            continue
        er = p.get("extension_risk") or "unknown"
        ext_groups[er].append(p["ret_1m"])

    return {
        "generated": date.today().isoformat(),
        "run_results": run_results,
        "exit_simulation": exit_sims,
        "spike_flag": {
            "spike_true":  spike_groups[True],
            "spike_false": spike_groups[False],
            "no_data_picks": no_spike_data,
        },
        "extension_risk": dict(ext_groups),
        "_meta": {
            "total_picks": len(picks),
            "picks_with_ret_1m": len(picks_with_1m),
            "active_picks_with_ret_1m": len(active_picks_1m),
            "payloads_loaded": len(payloads),
            "baselines_loaded": len(baselines),
        },
    }


# -- Console report --------------------------------------------------------------

def print_report(data: dict) -> None:
    run_results   = data["run_results"]
    exit_sims     = data["exit_simulation"]
    spike         = data["spike_flag"]
    ext_risk      = data["extension_risk"]
    meta          = data["_meta"]

    print()
    print("=" * 76)
    print("  AI PICKS vs MECHANICAL BASELINES -- 1-MONTH RETURN")
    print("=" * 76)
    print(f"  Picks with ret_1m: {meta['active_picks_with_ret_1m']} active-model  "
          f"/ {meta['picks_with_ret_1m']} total")
    print()

    if not run_results:
        print("  No runs with complete data yet.")
    else:
        # -- Per-run table --
        hdr = (f"{'Date':<12} {'AI picks':>8} {'AI ret1m':>9} "
               f"{'vsBasePCS':>10} {'vsBaseRot':>10} {'vsBaseR4w':>10}  {'AI tickers'}")
        print(hdr)
        print("-" * 76)

        all_ai: list[float] = []
        all_pcs: list[float] = []
        all_rot: list[float] = []
        all_r4w: list[float] = []

        beats_pcs = beats_rot = beats_r4w = 0
        runs_compared = 0

        for rr in sorted(run_results, key=lambda x: x["date"]):
            ai_ret = rr.get("ai_ret_1m")
            bl_pcs = rr["baselines"].get("top_pcs", {}).get("avg_ret")
            bl_rot = rr["baselines"].get("top_rot_score", {}).get("avg_ret")
            bl_r4w = rr["baselines"].get("top_ret_4w", {}).get("avg_ret")

            tickers = ", ".join(p["ticker"] for p in rr["ai_picks"])

            diff_pcs = f"{(ai_ret - bl_pcs):+.1f}%".rjust(10) if (ai_ret is not None and bl_pcs is not None) else "  no data".rjust(10)
            diff_rot = f"{(ai_ret - bl_rot):+.1f}%".rjust(10) if (ai_ret is not None and bl_rot is not None) else "  no data".rjust(10)
            diff_r4w = f"{(ai_ret - bl_r4w):+.1f}%".rjust(10) if (ai_ret is not None and bl_r4w is not None) else "  no data".rjust(10)

            src_tag = "(virtual)" if rr.get("baseline_source") == "payload_virtual" else ""
            print(f"{rr['date']:<12} {len(rr['ai_picks']):>8} {_pct(ai_ret, 9)} "
                  f"{diff_pcs} {diff_rot} {diff_r4w}  {tickers} {src_tag}")

            if ai_ret is not None:
                all_ai.append(ai_ret)
            if bl_pcs is not None:
                all_pcs.append(bl_pcs)
                if ai_ret is not None:
                    runs_compared += 1
                    if ai_ret > bl_pcs:
                        beats_pcs += 1
                    if bl_rot is not None and ai_ret > bl_rot:
                        beats_rot += 1
                    if bl_r4w is not None and ai_ret > bl_r4w:
                        beats_r4w += 1
            if bl_rot is not None:
                all_rot.append(bl_rot)
            if bl_r4w is not None:
                all_r4w.append(bl_r4w)

        print("-" * 76)
        print(f"{'OVERALL':<12} {'':>8} {_pct(_safe_mean(all_ai), 9)} "
              f"  base_pcs={_pct(_safe_mean(all_pcs), 7)}  "
              f"base_rot={_pct(_safe_mean(all_rot), 7)}  "
              f"base_r4w={_pct(_safe_mean(all_r4w), 7)}")
        print()

        if runs_compared:
            print(f"  Win rate vs top-PCS:      {beats_pcs}/{runs_compared} = {beats_pcs/runs_compared*100:.0f}%")
            print(f"  Win rate vs top-rot:      {beats_rot}/{runs_compared} = {beats_rot/runs_compared*100:.0f}%")
            print(f"  Win rate vs top-ret_4w:   {beats_r4w}/{runs_compared} = {beats_r4w/runs_compared*100:.0f}%")

        print()
        print("  Legend: vsBasePCS/Rot/R4w = AI avg ret_1m minus baseline avg ret_1m")
        print("          (virtual) = no baselines.jsonl entry; top-3 PCS reconstructed from payload")

    # -- Per-portfolio breakdown --
    print()
    print("-" * 76)
    print("  PER-PORTFOLIO BREAKDOWN")
    print("-" * 76)
    portfolio_data: dict[str, list] = defaultdict(list)
    for rr in run_results:
        for p in rr["ai_picks"]:
            if p.get("ret_1m") is not None:
                portfolio_data[p["portfolio"]].append(p["ret_1m"])

    if portfolio_data:
        print(f"  {'Portfolio':<35} {'n':>4} {'avg ret_1m':>11} {'best':>8} {'worst':>8}")
        print(f"  {'-'*35} {'-'*4} {'-'*11} {'-'*8} {'-'*8}")
        for ptf in sorted(portfolio_data):
            rets = portfolio_data[ptf]
            avg  = sum(rets) / len(rets)
            print(f"  {ptf:<35} {len(rets):>4} {_pct(avg, 11)} "
                  f"{_pct(max(rets), 8)} {_pct(min(rets), 8)}")
    else:
        print("  No per-portfolio data available yet.")

    # -- EXIT simulation --
    print()
    print("-" * 76)
    print("  EXIT SIMULATION  (rule: pcs < pcs_min_entry + streak<=1  OR  rot_score<=2)")
    print("-" * 76)

    tracked   = [e for e in exit_sims if e.get("note") != "not_in_subsequent_payloads"]
    triggered = [e for e in exit_sims if e.get("exit_simulated")]
    no_data   = [e for e in exit_sims if e.get("note") == "not_in_subsequent_payloads"]

    print(f"  Picks analyzed: {len(exit_sims)}  |  "
          f"tracked in payloads: {len(tracked)}  |  "
          f"not reappeared: {len(no_data)}")
    print(f"  EXIT signals would have triggered: {len(triggered)}/{len(tracked)} "
          f"({len(triggered)/max(len(tracked),1)*100:.0f}% of tracked)")
    print()

    if triggered:
        print(f"  {'Ticker':<8} {'Portfolio':<28} {'entry':>10} {'exit_date':>10} "
              f"{'ret@exit':>9} {'ret_1m':>7}  {'diff':>6}  Reason")
        print(f"  {'-'*8} {'-'*28} {'-'*10} {'-'*10} {'-'*9} {'-'*7}  {'-'*6}  {'-'*25}")

        exit_returns_diff: list[float] = []
        for e in sorted(triggered, key=lambda x: x["entry_date"]):
            evt      = e["exit_event"]
            r1m      = e.get("ret_1m")
            r_exit   = e.get("ret_at_exit")
            diff     = None
            if r_exit is not None and r1m is not None:
                diff = r_exit - r1m   # positive = exit was better than holding
                exit_returns_diff.append(diff)
            diff_str = f"{diff:+.1f}%" if diff is not None else "  n/a"
            print(f"  {e['ticker']:<8} {e['portfolio']:<28} {e['entry_date']:>10} "
                  f"{evt['date']:>10} {_pct(r_exit, 9)} {_pct(r1m, 7)}  {diff_str:>6}  {evt['reason']}")
        print()
        print("  diff = ret@exit minus ret_1m (positive = exiting early was better)")

        if exit_returns_diff:
            avg_diff = sum(exit_returns_diff) / len(exit_returns_diff)
            print(f"  Avg benefit of early exit: {avg_diff:+.1f}% per position")
        print()

        # Summary: calendar days to EXIT signal
        import datetime
        early_exits = []
        for e in triggered:
            evt = e["exit_event"]
            try:
                d_entry = datetime.date.fromisoformat(e["entry_date"])
                d_exit  = datetime.date.fromisoformat(evt["date"])
                days_held = (d_exit - d_entry).days
                early_exits.append(days_held)
            except Exception:
                pass
        if early_exits:
            avg_days = sum(early_exits) / len(early_exits)
            print(f"  Avg calendar days to EXIT signal: {avg_days:.0f}  "
                  f"(range: {min(early_exits)}-{max(early_exits)})")
    else:
        print("  No EXIT signals triggered for any tracked pick.")

    print()
    print("  LIMITATION: EXIT simulation only covers tickers that reappeared in")
    print("  subsequent payloads (top-15 candidates each run). Tickers that dropped")
    print("  out of the candidate universe have no PCS/rot_score history available.")

    # -- spike_flag analysis --
    print()
    print("-" * 76)
    print("  SPIKE_FLAG ANALYSIS")
    print("-" * 76)

    sf_true  = spike["spike_true"]
    sf_false = spike["spike_false"]
    no_sf    = spike["no_data_picks"]

    print(f"  Picks with spike=True:   n={len(sf_true)}  avg ret_1m={_pct(_safe_mean(sf_true), 7)}")
    print(f"  Picks with spike=False:  n={len(sf_false)}  avg ret_1m={_pct(_safe_mean(sf_false), 7)}")
    print(f"  No spike_flag in payload: {no_sf} (early payloads before field was added)")

    if sf_true and sf_false:
        diff = _safe_mean(sf_false) - _safe_mean(sf_true)  # type: ignore
        print()
        if diff is not None:
            if diff > 0:
                print(f"  -> Avoiding spike picks would have improved avg ret by {diff:+.1f}%")
            else:
                print(f"  -> Spike picks actually outperformed non-spike by {-diff:+.1f}%")
    else:
        print("\n  Insufficient data for spike_flag conclusion.")

    # -- Extension risk --
    print()
    print("-" * 76)
    print("  EXTENSION RISK ANALYSIS  (from shadow_picks fields)")
    print("-" * 76)

    ext_order = ["low", "medium", "high", "extreme", "unknown"]
    has_data = any(ext_risk.get(k) for k in ext_order if k != "unknown")

    if has_data:
        print(f"  {'Level':<10} {'n':>4}  {'avg ret_1m':>11}  {'best':>8}  {'worst':>8}")
        print(f"  {'-'*10} {'-'*4}  {'-'*11}  {'-'*8}  {'-'*8}")
        for level in ext_order:
            rets = ext_risk.get(level, [])
            if not rets:
                continue
            avg = sum(rets) / len(rets)
            print(f"  {level:<10} {len(rets):>4}  {_pct(avg, 11)}  "
                  f"{_pct(max(rets), 8)}  {_pct(min(rets), 8)}")
    else:
        print("  extension_risk field is null for most picks (added mid-May).")
        print("  Will populate as newer picks reach 1-month horizon.")

    print()
    print("=" * 76)


# -- Entry point -----------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare AI picks vs mechanical baselines"
    )
    parser.add_argument("--no-fetch",    action="store_true",
                        help="Skip yfinance download; use cached prices")
    parser.add_argument("--save-cache",  action="store_true",
                        help="Save fetched prices to JSON cache for --no-fetch")
    args = parser.parse_args()

    data = run_analysis(no_fetch=args.no_fetch, save_cache=args.save_cache)
    print_report(data)

    OUT_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"Results saved to {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
