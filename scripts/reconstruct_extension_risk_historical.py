"""
reconstruct_extension_risk_historical.py
    — backfills extension_risk (and the richer proxy fields the CFL diagnosis
      asked for) for every pick already logged in shadow_picks.jsonl, computed
      strictly from prices available at-or-before entry_date (no look-ahead).

Why: extension_risk existed as a live field since 2026-05-16, but a lookup bug
in paper_trading.py (_log_shadow_picks, fixed 2026-07-02) left it null for
~96% of historical picks. That's the field needed to test the "entering too
late" hypothesis on CONFIRMED_FLOW_LEADERS (see wiki/ASESOR_EXTERNO_CFL_DIAGNOSTICO.md,
P2). Rather than guess, this reconstructs it from real historical OHLCV.

Reads:
  docs/data/shadow_picks.jsonl        (which ticker/date pairs need reconstruction)

Writes:
  docs/data/extension_risk_reconstructed.jsonl   (one row per unique ticker+date,
                                                    append-only, dedup on rerun)

Fields per row (all computed using only bars with date <= entry_date):
  dist_sma20_atr, ret_5d_vs_spy, ret_20d_vs_spy, ret_4w_vs_spy (proxy = ret_20d_vs_spy,
      we only have daily OHLCV here, not the weekly rotation series pcs_calculator
      uses live — documented approximation, same "proxy" framing as the MOVE proxy
      in duration.html), rsi_14, spike_flag, momentum_decay,
  atr_pct                    — ATR14 / close * 100
  atr_percentile_126d        — percentile rank of today's ATR14 within trailing 126 bars
  bb_width_percentile_126d   — percentile rank of today's Bollinger Band width (20,2std)
                                within trailing 126 bars
  days_since_20d_high_breakout / days_since_55d_high_breakout
                              — sessions since the most recent fresh N-day high
  extension_risk / extension_points / extension_flags
                              — same scoring as pcs_calculator.compute_extension_risk()
                                (imported directly, not reimplemented, to avoid drift)
  bars_before_entry          — how many trading days of history were available
                                (early picks on recent IPOs may have too little
                                for the 126d percentile fields -> null there)

Usage:
  py -3 scripts/reconstruct_extension_risk_historical.py             # fill missing only
  py -3 scripts/reconstruct_extension_risk_historical.py --force     # recompute all
  py -3 scripts/reconstruct_extension_risk_historical.py --dry-run   # show, don't write
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

DATA = ROOT / "docs" / "data"
SHADOW_PICKS = DATA / "shadow_picks.jsonl"
OUT_LOG      = DATA / "extension_risk_reconstructed.jsonl"

ATR_PERIOD  = 14
SMA_PERIOD  = 20
RSI_PERIOD  = 14
BB_PERIOD   = 20
BB_STD      = 2
PCTL_WINDOW = 126
HISTORY_BUFFER_DAYS = 260   # calendar days of extra history fetched before earliest entry


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _rsi14(close):
    import pandas as pd
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
    loss = (-delta).clip(lower=0).rolling(RSI_PERIOD).mean()
    rsi = pd.Series(index=close.index, dtype=float)
    with_loss = loss > 0
    rsi[with_loss] = 100 - 100 / (1 + gain[with_loss] / loss[with_loss])
    rsi[(~with_loss) & (gain > 0)] = 100.0
    rsi[(~with_loss) & (gain == 0)] = 50.0
    return rsi


def _atr14(high, low, close):
    import pandas as pd
    prev_c = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_c).abs(),
        (low - prev_c).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()


def _bb_width(close):
    sma = close.rolling(BB_PERIOD).mean()
    std = close.rolling(BB_PERIOD).std()
    upper = sma + BB_STD * std
    lower = sma - BB_STD * std
    return (upper - lower) / sma


def _percentile_rank(series, window: int) -> float | None:
    """Percentile of the last value within its own trailing `window` bars."""
    tail = series.dropna()
    if len(tail) < max(20, window // 4):   # need a minimally meaningful sample
        return None
    tail = tail.iloc[-window:]
    last = tail.iloc[-1]
    return round(100.0 * (tail <= last).mean(), 1)


def _days_since_high_breakout(close, window: int) -> int | None:
    """Sessions since the most recent close that was a fresh `window`-day high
    (close[i] > max(close[i-window:i])). None if never happened in available history."""
    if len(close) < window + 2:
        return None
    roll_max_prior = close.shift(1).rolling(window).max()
    breakout = close > roll_max_prior
    hits = breakout[breakout].index
    if len(hits) == 0:
        return None
    last_hit = hits[-1]
    return int((close.index.get_loc(close.index[-1]) - close.index.get_loc(last_hit)))


def reconstruct_for_ticker(ticker: str, dates: list[str], px: dict) -> dict[str, dict]:
    """px = {'close':Series,'high':Series,'low':Series} for ticker, spy_close = Series."""
    import pandas as pd
    from pcs_calculator import compute_extension_risk

    close, high, low = px.get("close"), px.get("high"), px.get("low")
    spy_close = px.get("spy_close")
    if close is None or close.empty:
        return {}

    atr = _atr14(high, low, close) if high is not None and low is not None else None
    sma20 = close.rolling(SMA_PERIOD).mean()
    rsi = _rsi14(close)
    bb_width = _bb_width(close)
    ret_1d = close.pct_change() * 100

    out: dict[str, dict] = {}
    for d in dates:
        ts = pd.Timestamp(d)
        idx = close.index[close.index <= ts]
        if len(idx) == 0:
            continue
        asof = idx[-1]
        pos = close.index.get_loc(asof)
        bars_before = pos + 1

        def _nd_ago(n: int):
            j = pos - n
            return close.index[j] if j >= 0 else None

        c_today = float(close.loc[asof])
        r5 = r20 = None
        d5 = _nd_ago(5)
        if d5 is not None:
            r5 = round((c_today / float(close.loc[d5]) - 1) * 100, 2)
        d20 = _nd_ago(20)
        if d20 is not None:
            r20 = round((c_today / float(close.loc[d20]) - 1) * 100, 2)

        r5_spy = r20_spy = None
        if spy_close is not None:
            spy_idx = spy_close.index[spy_close.index <= ts]
            if len(spy_idx) > 0:
                spy_pos = spy_close.index.get_loc(spy_idx[-1])
                sc_today = float(spy_close.iloc[spy_pos])
                if spy_pos - 5 >= 0:
                    r5_spy = round((sc_today / float(spy_close.iloc[spy_pos - 5]) - 1) * 100, 2)
                if spy_pos - 20 >= 0:
                    r20_spy = round((sc_today / float(spy_close.iloc[spy_pos - 20]) - 1) * 100, 2)

        ret_5d_vs_spy = round(r5 - r5_spy, 2) if (r5 is not None and r5_spy is not None) else None
        ret_20d_vs_spy = round(r20 - r20_spy, 2) if (r20 is not None and r20_spy is not None) else None

        # spike_flag: same formula as pcs_calculator.fetch_daily_metrics
        spike_flag = False
        if r5 is not None and r5 > 0 and pos >= 5:
            window_1d = ret_1d.iloc[pos - 4: pos + 1]
            if len(window_1d) == 5 and r5 != 0:
                raw_5d_frac = r5 / 100.0
                if raw_5d_frac > 0:
                    spike_flag = bool((window_1d.max() / 100.0) / raw_5d_frac > 0.70)

        momentum_decay = bool(r5 is not None and r5 < -1.0 and r20 is not None and r20 > 20.0)

        dist_sma20_atr = None
        atr_val = None
        if atr is not None and pos < len(atr):
            atr_val = atr.iloc[pos]
            sma_val = sma20.iloc[pos]
            if pd_notna(atr_val) and pd_notna(sma_val) and atr_val > 0:
                dist_sma20_atr = round((c_today - float(sma_val)) / float(atr_val), 2)

        rsi_val = rsi.iloc[pos] if pos < len(rsi) else None
        rsi_val = round(float(rsi_val), 1) if pd_notna(rsi_val) else None

        atr_pct = round(float(atr_val) / c_today * 100, 2) if atr_val is not None and pd_notna(atr_val) else None
        atr_pctl = _percentile_rank(atr.iloc[:pos + 1], PCTL_WINDOW) if atr is not None else None
        bbw_pctl = _percentile_rank(bb_width.iloc[:pos + 1], PCTL_WINDOW) if bb_width is not None else None

        d20b = _days_since_high_breakout(close.iloc[:pos + 1], 20)
        d55b = _days_since_high_breakout(close.iloc[:pos + 1], 55)

        ext_input = {
            "dist_sma20_atr": dist_sma20_atr,
            "ret_4w_vs_spy":  ret_20d_vs_spy,   # proxy: only daily OHLCV available here
            "momentum_decay": momentum_decay,
            "spike_flag":     spike_flag,
            "rsi_14":         rsi_val,
        }
        ext = compute_extension_risk(ext_input)

        out[d] = {
            "ticker": ticker,
            "date": d,
            "dist_sma20_atr": dist_sma20_atr,
            "ret_5d_vs_spy": ret_5d_vs_spy,
            "ret_20d_vs_spy": ret_20d_vs_spy,
            "ret_4w_vs_spy": ret_20d_vs_spy,
            "rsi_14": rsi_val,
            "spike_flag": spike_flag,
            "momentum_decay": momentum_decay,
            "atr_pct": atr_pct,
            "atr_percentile_126d": atr_pctl,
            "bb_width_percentile_126d": bbw_pctl,
            "days_since_20d_high_breakout": d20b,
            "days_since_55d_high_breakout": d55b,
            "extension_risk": ext["extension_risk"],
            "extension_points": ext["extension_points"],
            "extension_flags": ext["extension_flags"],
            "bars_before_entry": bars_before,
            "reconstructed": True,
            "reconstructed_at": datetime.now().isoformat(timespec="seconds"),
        }
    return out


def pd_notna(v) -> bool:
    import pandas as pd
    return v is not None and pd.notna(v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="recompute rows already in output")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        print("ERROR: yfinance / pandas not installed.", file=sys.stderr)
        sys.exit(1)

    picks = load_jsonl(SHADOW_PICKS)
    if not picks:
        print("shadow_picks.jsonl is empty, nothing to do.")
        return

    wanted: dict[str, set[str]] = {}
    for p in picks:
        t, d = p.get("ticker"), (p.get("date") or "")[:10]
        if not t or not d:
            continue
        wanted.setdefault(t, set()).add(d)

    existing = load_jsonl(OUT_LOG)
    have: set[tuple[str, str]] = {(r["ticker"], r["date"]) for r in existing}

    if not args.force:
        for t in list(wanted):
            wanted[t] = {d for d in wanted[t] if (t, d) not in have}
            if not wanted[t]:
                del wanted[t]

    if not wanted:
        print("Nothing to reconstruct — all picks already have a row (use --force to recompute).")
        return

    all_dates = sorted({d for ds in wanted.values() for d in ds})
    start = (datetime.strptime(all_dates[0], "%Y-%m-%d") - timedelta(days=HISTORY_BUFFER_DAYS)).strftime("%Y-%m-%d")
    end = (datetime.strptime(all_dates[-1], "%Y-%m-%d") + timedelta(days=3)).strftime("%Y-%m-%d")

    tickers = sorted(wanted)
    print(f"Reconstructing extension_risk for {len(tickers)} tickers, "
          f"{sum(len(v) for v in wanted.values())} ticker-date pairs, "
          f"history {start} -> {end}")

    all_syms = sorted(set(tickers) | {"SPY"})
    raw = yf.download(all_syms, start=start, end=end, auto_adjust=True,
                       progress=False, threads=True)
    if raw is None or raw.empty:
        print("ERROR: yfinance returned no data.", file=sys.stderr)
        sys.exit(1)

    if isinstance(raw.columns, pd.MultiIndex):
        close_df = raw["Close"]
        high_df  = raw["High"] if "High" in raw else pd.DataFrame()
        low_df   = raw["Low"]  if "Low" in raw else pd.DataFrame()
    else:
        close_df = raw[["Close"]].rename(columns={"Close": all_syms[0]})
        high_df  = raw[["High"]].rename(columns={"High": all_syms[0]}) if "High" in raw else pd.DataFrame()
        low_df   = raw[["Low"]].rename(columns={"Low": all_syms[0]}) if "Low" in raw else pd.DataFrame()

    spy_close = close_df["SPY"].dropna() if "SPY" in close_df.columns else None

    written = 0
    skipped_no_data = []
    for t in tickers:
        if t not in close_df.columns:
            skipped_no_data.append(t)
            continue
        px = {
            "close": close_df[t].dropna(),
            "high":  high_df[t].dropna() if t in getattr(high_df, "columns", []) else None,
            "low":   low_df[t].dropna() if t in getattr(low_df, "columns", []) else None,
            "spy_close": spy_close,
        }
        if px["close"].empty:
            skipped_no_data.append(t)
            continue
        rows = reconstruct_for_ticker(t, sorted(wanted[t]), px)
        for d, row in sorted(rows.items()):
            if args.dry_run:
                print(f"  {t} {d}: extension_risk={row['extension_risk']} "
                      f"(pts={row['extension_points']}) atr_pctl={row['atr_percentile_126d']} "
                      f"days20b={row['days_since_20d_high_breakout']}")
            else:
                append_jsonl(OUT_LOG, row)
            written += 1

    if skipped_no_data:
        print(f"  no price data for: {', '.join(skipped_no_data)}")
    print(f"{'Would write' if args.dry_run else 'Wrote'} {written} rows"
          f"{' (dry-run, nothing saved)' if args.dry_run else f' -> {OUT_LOG}'}")


if __name__ == "__main__":
    main()
