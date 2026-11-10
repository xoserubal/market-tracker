"""OHLCV + Adj Close (yfinance, auto_adjust=False) para el universo, SPY y ETF sectoriales; sector GICS por valor.
Salidas: prices_cache.parquet (gitignored), sectors.json."""
import io, json, requests, pandas as pd, yfinance as yf
c = json.load(open("../macd_combo_sp500_ndx_v1/constituents.json"))
SECTOR_ETF = {"Information Technology": "XLK", "Financials": "XLF", "Health Care": "XLV",
              "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Energy": "XLE", "Industrials": "XLI",
              "Materials": "XLB", "Real Estate": "XLRE", "Communication Services": "XLC", "Utilities": "XLU"}
H = {"User-Agent": "Mozilla/5.0 (research script)"}
sp = pd.read_html(io.StringIO(requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=H, timeout=30).text))[0]
sector = {s.replace(".", "-"): g for s, g in zip(sp["Symbol"], sp["GICS Sector"])}
# Solo-Nasdaq 100: sector GICS asignado a mano (Wikipedia da ICB para esa lista)
sector.update({"ALAB": "Information Technology", "ALNY": "Health Care", "ARM": "Information Technology",
               "ASML": "Information Technology", "CCEP": "Consumer Staples", "CRWV": "Information Technology",
               "FER": "Industrials", "MELI": "Consumer Discretionary", "MSTR": "Information Technology",
               "NBIS": "Information Technology", "PDD": "Consumer Discretionary", "RKLB": "Industrials",
               "SHOP": "Information Technology", "SPCX": "Industrials", "TRI": "Industrials"})
uni = sorted(set(c["sp500"]) | set(c["ndx"]))
missing = [t for t in uni if t not in sector]
assert not missing, missing
json.dump({"sector": {t: sector[t] for t in uni}, "etf": SECTOR_ETF}, open("sectors.json", "w"), indent=1)
tickers = uni + ["SPY"] + sorted(SECTOR_ETF.values())
frames = []
for i in range(0, len(tickers), 100):
    chunk = tickers[i:i+100]
    df = yf.download(chunk, start="2015-01-01", end="2026-11-10", auto_adjust=False, group_by="ticker", threads=True, progress=False)
    for t in chunk:
        if t not in df.columns.get_level_values(0): continue
        d = df[t][["Open", "High", "Low", "Close", "Adj Close", "Volume"]].dropna(subset=["Close"])
        if d.empty: continue
        frames.append(d.assign(ticker=t).reset_index())
    print(i, len(frames), flush=True)
out = pd.concat(frames)
out.columns = ["date", "open", "high", "low", "close", "adj_close", "volume", "ticker"]
out.to_parquet("prices_cache.parquet")
print("tickers", out.ticker.nunique(), "rows", len(out), out.date.min(), out.date.max())
