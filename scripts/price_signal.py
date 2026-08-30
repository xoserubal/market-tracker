"""
Ad-hoc live price fetch for "situaciones especiales" (composite thesis
alerts) — scripts/koncorde_alert_conditions.py's `price`-type condition
delegates here. Same spirit as ratio_signal.py (small, dedicated, live
fetch on demand, no registry) but for a single ticker's current price
against a fixed threshold (e.g. "TNZ > 70").

"Current price" = last available close from yfinance's most recent daily
bar (same source/freshness as the rest of the pipeline — no intraday feed
in this project). Not adjusted for splits/dividends beyond whatever
yfinance's default download already applies.

Usage (also importable — see koncorde_alert_conditions.evaluate_price):
    py -3 scripts/price_signal.py TNZ.TO
"""
from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def fetch_current_price(ticker: str) -> float | None:
    """Returns the last available close price for `ticker`, or None on failure."""
    try:
        import yfinance as yf
    except ImportError:
        print("price_signal: yfinance not installed", file=sys.stderr)
        return None

    try:
        raw = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
    except Exception as exc:
        print(f"price_signal: download failed for {ticker}: {exc}", file=sys.stderr)
        return None

    if raw is None or raw.empty or "Close" not in raw:
        print(f"price_signal: no data for {ticker}", file=sys.stderr)
        return None

    closes = raw["Close"]
    # yfinance single-ticker downloads sometimes come back with a MultiIndex
    # column (Close, TICKER) depending on version — handle both shapes.
    if hasattr(closes, "columns"):
        if ticker in closes.columns:
            closes = closes[ticker]
        else:
            closes = closes.iloc[:, 0]

    closes = closes.dropna()
    if closes.empty:
        print(f"price_signal: no valid close for {ticker}", file=sys.stderr)
        return None

    return float(closes.iloc[-1])


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: py -3 scripts/price_signal.py TICKER")
        sys.exit(1)
    price = fetch_current_price(sys.argv[1])
    if price is None:
        print("No se pudo obtener el precio.")
        sys.exit(1)
    print(f"{sys.argv[1]}: {price:.4f}")


if __name__ == "__main__":
    main()
