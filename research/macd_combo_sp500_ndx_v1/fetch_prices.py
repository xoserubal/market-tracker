"""Descarga OHLC diario (auto_adjust=False, igual que /api/quote) para S&P 500 + Nasdaq 100 + SPY.
Salida: prices_cache.parquet (gitignored)."""
import json, yfinance as yf, pandas as pd
c = json.load(open("constituents.json"))
tickers = sorted(set(c["sp500"]) | set(c["ndx"]) | {"SPY"})
frames = []
for i in range(0, len(tickers), 100):
    chunk = tickers[i:i+100]
    df = yf.download(chunk, start="2015-01-01", auto_adjust=False, group_by="ticker", threads=True, progress=False)
    for t in chunk:
        if t not in df.columns.get_level_values(0): continue
        d = df[t][["High", "Low", "Close"]].dropna(subset=["Close"])
        if d.empty: continue
        d = d.assign(ticker=t).reset_index()
        frames.append(d)
    print(i, len(frames), flush=True)
out = pd.concat(frames)
out.columns = ["date", "high", "low", "close", "ticker"]
out.to_parquet("prices_cache.parquet")
print("tickers", out.ticker.nunique(), "rows", len(out), "range", out.date.min(), out.date.max())
