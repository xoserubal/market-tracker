"""
Ad-hoc ratio trend for "situaciones especiales" (composite thesis alerts) —
scripts/koncorde_alert_conditions.py's `ratio`-type condition delegates here.

Unlike shared/relative-ratio-registry.js (a fixed registry of ~50 macro/sector
pairs, consumed by relative.html) this computes a ratio for ANY two tickers a
user picks from the web UI (e.g. ADS.DE/FEZ, ADS.DE/NKE) — no registry entry
needed. Kept as its own small module rather than forcing reuse of
relative_flow_lib.py's align_ratio(), which is shaped around the registry's
batch/backtest use case (many pairs at once, full history reconstruction);
here it's one pair, live, on demand. The join-by-date logic is the same one
line of pandas either way, so nothing meaningful is duplicated.

"Improving" = today's ratio is above its own trailing SMA (same convention as
"price above its 20-day SMA" used elsewhere in this project, e.g. SMA20 in
shared/quote-lib.js) — not a crossing, just a simple, defensible trend read.
First-pass threshold, unvalidated against forward returns, same observational
posture as every other new signal in this project.

Usage (also importable — see koncorde_alert_conditions.evaluate_ratio):
    py -3 scripts/ratio_signal.py ADS.DE FEZ
"""
from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SMA_WINDOW = 20
LOOKBACK_DAYS = 90  # comfortably more than SMA_WINDOW trading days once weekends/holidays are removed

# KNOWN CAVEAT, not a bug: no FX conversion. If ticker_a/ticker_b trade in
# different currencies (e.g. ADS.DE in EUR vs NKE in USD), the raw price
# ratio conflates genuine relative equity performance with EUR/USD movement.
# Verified in production 2026-08-26: ADS.DE/FEZ is same-currency (EUR/EUR),
# clean; ADS.DE/NKE is cross-currency (EUR/USD) and should be read with that
# in mind. Left unconverted deliberately for v1 — same currency pairs (vs a
# European benchmark) are the common case for this feature; add FX conversion
# here if a cross-currency pair proves to matter.


def fetch_ratio_trend(ticker_a: str, ticker_b: str, sma_window: int = SMA_WINDOW) -> dict | None:
    """Returns {"ratio_now", "sma", "improving", "ticker_a", "ticker_b"} or None
    if either ticker fails to fetch or there isn't enough overlapping history.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("ratio_signal: yfinance not installed", file=sys.stderr)
        return None

    try:
        raw = yf.download([ticker_a, ticker_b], period=f"{LOOKBACK_DAYS}d", auto_adjust=True, progress=False, threads=True)
    except Exception as exc:
        print(f"ratio_signal: download failed for {ticker_a}/{ticker_b}: {exc}", file=sys.stderr)
        return None

    if raw is None or raw.empty or "Close" not in raw:
        print(f"ratio_signal: no data for {ticker_a}/{ticker_b}", file=sys.stderr)
        return None

    closes = raw["Close"]
    if ticker_a not in closes.columns or ticker_b not in closes.columns:
        print(f"ratio_signal: missing column for {ticker_a} or {ticker_b}", file=sys.stderr)
        return None

    # Inner join on date (drop any date where either leg is NaN — same "align by
    # date" semantics as relative_flow_lib.py's align_ratio, just for one pair).
    pair = closes[[ticker_a, ticker_b]].dropna()
    if len(pair) < sma_window + 1:
        print(f"ratio_signal: not enough overlapping history for {ticker_a}/{ticker_b} "
              f"({len(pair)} rows, need >= {sma_window + 1})", file=sys.stderr)
        return None

    ratio_series = pair[ticker_a] / pair[ticker_b]
    ratio_now = float(ratio_series.iloc[-1])
    sma_val = float(ratio_series.iloc[-sma_window:].mean())

    return {
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "ratio_now": ratio_now,
        "sma": sma_val,
        "improving": ratio_now > sma_val,
    }


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: py -3 scripts/ratio_signal.py TICKER_A TICKER_B")
        sys.exit(1)
    trend = fetch_ratio_trend(sys.argv[1], sys.argv[2])
    if trend is None:
        print("No se pudo calcular el ratio.")
        sys.exit(1)
    print(f"{trend['ticker_a']}/{trend['ticker_b']}: ratio_now={trend['ratio_now']:.4f} "
          f"sma{SMA_WINDOW}={trend['sma']:.4f} improving={trend['improving']}")


if __name__ == "__main__":
    main()
