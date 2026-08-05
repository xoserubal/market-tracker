"""
cfl_followthrough_shadow.py — CONFIRMED_FLOW_LEADERS 1-week follow-through,
                               SHADOW ONLY (never closes a real position).

Why: wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md found that ret_1w predicts ret_1m
strongly for CFL (corr +0.72; only 2/30 picks negative at 1 week ever recovered
by 1 month). "Cut at 1w if negative" improved the simulated mean from -4.85% to
-1.68% on historical data, but on the SAME data it was discovered on (n=48,
single regime) — not enough to operate as a real stop. This script logs what
that rule (and three related ones) would have decided, for every CFL position
once it reaches ~1 week of age, without ever touching ai_picks.json. Promote
to a real stop only per the criteria in that document (P0 of the plan agreed
2026-08-05: ~100-150 independent events, 2+ regimes, out-of-sample validation).

Reads:
  docs/data/ai_picks.json                        (CFL open positions)
  docs/data/ai_candidates.json                    (current pcs/rot_score, if ticker still in universe)
  docs/data/shadow_picks.jsonl                    (entry-time extension_risk, if logged)
  docs/data/extension_risk_reconstructed.jsonl    (fallback entry-time extension_risk)
  yfinance                                        (price history since entry)

Writes:
  docs/data/cfl_followthrough_shadow.jsonl        (append-only, one row per position,
                                                     evaluated exactly once — dedup on rerun)

A position is evaluated once it has >=5 trading days of price history since
entry (matches ret_1w's horizon elsewhere in this project — HORIZONS in
update_performance.py). Nothing is evaluated twice: rerunning the pipeline
(2x/day) simply finds nothing new to do once every open CFL position has
already been logged.

Usage:
  py -3 scripts/cfl_followthrough_shadow.py             # log new evaluations
  py -3 scripts/cfl_followthrough_shadow.py --dry-run   # show, don't write
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

AI_PICKS      = DATA / "ai_picks.json"
AI_CANDIDATES = DATA / "ai_candidates.json"
SHADOW_PICKS  = DATA / "shadow_picks.jsonl"
EXT_RECON     = DATA / "extension_risk_reconstructed.jsonl"
OUT_LOG       = DATA / "cfl_followthrough_shadow.jsonl"

PORTFOLIO = "CONFIRMED_FLOW_LEADERS"
RET_1W_TRADING_DAYS = 5


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


def _entry_extension_risk(ticker: str, entry_date: str,
                           shadow_index: dict, recon_index: dict) -> dict:
    row = shadow_index.get((ticker, entry_date))
    if row and row.get("extension_risk") is not None:
        return {
            "extension_risk": row.get("extension_risk"),
            "extension_points": row.get("extension_points"),
            "source": "shadow_picks_live",
        }
    row = recon_index.get((ticker, entry_date))
    if row:
        return {
            "extension_risk": row.get("extension_risk"),
            "extension_points": row.get("extension_points"),
            "atr_pct": row.get("atr_pct"),
            "source": "reconstructed",
        }
    return {"extension_risk": None, "extension_points": None, "source": None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        print("ERROR: yfinance / pandas not installed.", file=sys.stderr)
        sys.exit(1)

    picks_data = load_json(AI_PICKS)
    positions = (picks_data.get("portfolios", {})
                            .get(PORTFOLIO, {})
                            .get("positions", []))
    if not positions:
        print(f"No open positions in {PORTFOLIO}, nothing to evaluate.")
        return

    already = {r["position_id"] for r in load_jsonl(OUT_LOG)}
    todo = [p for p in positions
            if f"{p['ticker']}__{p['entry_date']}" not in already]
    if not todo:
        print("All open CFL positions already evaluated.")
        return

    # -- candidate snapshot (current pcs/rot_score) --
    cand_data = load_json(AI_CANDIDATES)
    cand_by_ticker = {c["ticker"]: c for c in cand_data.get("candidates", [])}

    # -- entry-time extension_risk sources --
    shadow_rows = load_jsonl(SHADOW_PICKS)
    shadow_index = {}
    for r in shadow_rows:
        if r.get("portfolio") == PORTFOLIO and r.get("active_model"):
            shadow_index.setdefault((r["ticker"], r["date"][:10]), r)
    recon_rows = load_jsonl(EXT_RECON)
    recon_index = {(r["ticker"], r["date"]): r for r in recon_rows}

    # -- price history: entry_date -> today, per ticker, + SPY --
    tickers = sorted({p["ticker"] for p in todo})
    all_syms = sorted(set(tickers) | {"SPY"})
    earliest_entry = min(p["entry_date"] for p in todo)
    raw = yf.download(all_syms, start=earliest_entry, auto_adjust=True,
                       progress=False, threads=True)
    if raw is None or raw.empty:
        print("ERROR: yfinance returned no data.", file=sys.stderr)
        sys.exit(1)

    if isinstance(raw.columns, pd.MultiIndex):
        close_df = raw["Close"]
        high_df = raw["High"] if "High" in raw else pd.DataFrame()
        low_df = raw["Low"] if "Low" in raw else pd.DataFrame()
    else:
        close_df = raw[["Close"]].rename(columns={"Close": all_syms[0]})
        high_df = raw[["High"]].rename(columns={"High": all_syms[0]}) if "High" in raw else pd.DataFrame()
        low_df = raw[["Low"]].rename(columns={"Low": all_syms[0]}) if "Low" in raw else pd.DataFrame()

    spy_close = close_df["SPY"].dropna() if "SPY" in close_df.columns else None

    written = 0
    for p in todo:
        ticker, entry_date = p["ticker"], p["entry_date"]
        if ticker not in close_df.columns:
            continue
        close = close_df[ticker].dropna()
        high = high_df[ticker].dropna() if ticker in getattr(high_df, "columns", []) else None
        low = low_df[ticker].dropna() if ticker in getattr(low_df, "columns", []) else None

        idx = close.index[close.index >= pd.Timestamp(entry_date)]
        if len(idx) <= RET_1W_TRADING_DAYS:
            continue   # not yet 1 week old — evaluate on a later run
        entry_bar = idx[0]
        week_bar = idx[RET_1W_TRADING_DAYS]
        entry_pos = close.index.get_loc(entry_bar)
        week_pos = close.index.get_loc(week_bar)

        entry_price = p.get("entry_price") or float(close.loc[entry_bar])
        close_1w = float(close.loc[week_bar])
        ret_1w = round((close_1w / entry_price - 1) * 100, 2)

        ret_1w_vs_spy = None
        if spy_close is not None:
            spy_idx = spy_close.index[spy_close.index >= pd.Timestamp(entry_date)]
            if len(spy_idx) > RET_1W_TRADING_DAYS:
                spy_entry = float(spy_close.loc[spy_idx[0]])
                spy_week = float(spy_close.loc[spy_idx[RET_1W_TRADING_DAYS]])
                spy_ret_1w = (spy_week / spy_entry - 1) * 100
                ret_1w_vs_spy = round(ret_1w - spy_ret_1w, 2)

        mfe_1w = mae_1w = None
        if high is not None and low is not None:
            window_h = high.iloc[entry_pos: week_pos + 1]
            window_l = low.iloc[entry_pos: week_pos + 1]
            if not window_h.empty and not window_l.empty:
                mfe_1w = round((float(window_h.max()) / entry_price - 1) * 100, 2)
                mae_1w = round((float(window_l.min()) / entry_price - 1) * 100, 2)

        ext = _entry_extension_risk(ticker, entry_date, shadow_index, recon_index)
        atr_pct_entry = ext.get("atr_pct")
        # ATR% isn't stored for shadow_picks-sourced rows (only reconstructed
        # ones compute it) — fall back to the reconstruction file directly.
        if atr_pct_entry is None:
            r = recon_index.get((ticker, entry_date))
            atr_pct_entry = r.get("atr_pct") if r else None

        cand = cand_by_ticker.get(ticker, {})
        current_pcs = cand.get("pcs")
        current_rot = cand.get("rot_score")

        # atr_adjusted_breach: position lost more than 1x its entry-day ATR% in a week
        # (None when ATR% at entry isn't available, per "si hay ATR" in the plan)
        atr_adjusted_breach = bool(ret_1w < -atr_pct_entry) if atr_pct_entry is not None else None

        rules = {
            "ret_1w_negative":            ret_1w < 0,
            "ret_1w_below_minus3":        ret_1w < -3,
            "ret_1w_vs_spy_below_minus2": (ret_1w_vs_spy is not None and ret_1w_vs_spy < -2),
            "atr_adjusted_breach":        atr_adjusted_breach,
        }

        shadow_decision = "WOULD_EXIT" if rules["ret_1w_negative"] else "WOULD_HOLD"
        triggered = [k for k, v in rules.items() if v]
        if shadow_decision == "WOULD_EXIT":
            reason = (f"ret_1w {ret_1w:+.2f}% < 0 (primary rule, validated in "
                      f"ASESOR_EXTERNO_CFL_DIAGNOSTICO.md P0); also triggered: "
                      f"{[t for t in triggered if t != 'ret_1w_negative']}")
        else:
            reason = f"ret_1w {ret_1w:+.2f}% >= 0, no follow-through failure"

        record = {
            "position_id":      f"{ticker}__{entry_date}",
            "ticker":            ticker,
            "entry_date":        entry_date,
            "portfolio":         PORTFOLIO,
            "days_since_entry":  (datetime.now().date() - datetime.strptime(entry_date, "%Y-%m-%d").date()).days,
            "ret_1w":            ret_1w,
            "ret_1w_vs_spy":     ret_1w_vs_spy,
            "entry_pcs":         p.get("entry_pcs"),
            "current_pcs":       current_pcs,
            "entry_rot":         None,   # not captured at entry time by paper_trading.py today
            "current_rot":       current_rot,
            "entry_extension_risk": ext.get("extension_risk"),
            "entry_extension_points": ext.get("extension_points"),
            "entry_extension_source": ext.get("source"),
            "atr_pct_entry":     atr_pct_entry,
            "mfe_1w":            mfe_1w,
            "mae_1w":            mae_1w,
            "rules":             rules,
            "shadow_decision":   shadow_decision,
            "reason":            reason,
            "evaluated_at":      datetime.now().isoformat(timespec="seconds"),
        }

        if args.dry_run:
            print(f"  {ticker} (entered {entry_date}): ret_1w={ret_1w:+.2f}% "
                  f"-> {shadow_decision}  [{reason}]")
        else:
            append_jsonl(OUT_LOG, record)
        written += 1

    print(f"{'Would log' if args.dry_run else 'Logged'} {written} follow-through "
          f"evaluation(s){'' if args.dry_run else f' -> {OUT_LOG}'}")


if __name__ == "__main__":
    main()
