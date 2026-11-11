"""Descarga OHLC + Adj Close (yfinance, auto_adjust=False) del universo S&P 500 + Nasdaq 100 y SPY → _work/prices.parquet."""
import json
from pathlib import Path
import pandas as pd, yfinance as yf
HERE = Path(__file__).resolve().parent
c = json.load(open(HERE.parent / "macd_combo_sp500_ndx_v1" / "constituents.json"))
tickers = sorted(set(c["sp500"]) | set(c["ndx"])) + ["SPY"]
frames = []
for i in range(0, len(tickers), 100):
    chunk = tickers[i:i+100]
    df = yf.download(chunk, start="2015-01-01", end="2026-11-11", auto_adjust=False, group_by="ticker", threads=True, progress=False)
    for t in chunk:
        if t not in df.columns.get_level_values(0): continue
        d = df[t][["Open", "High", "Low", "Close", "Adj Close"]].dropna(subset=["Close"])
        if not d.empty: frames.append(d.assign(ticker=t).reset_index())
p = pd.concat(frames, ignore_index=True)
p.to_parquet(HERE / "_work" / "prices.parquet")
print(len(tickers), "pedidos;", p.ticker.nunique(), "con datos;", p.Date.min(), p.Date.max())
