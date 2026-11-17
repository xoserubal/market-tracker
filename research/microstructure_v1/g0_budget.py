"""G0 — presupuesto de datos por nivel (barras 1 min / trades / quotes).

Usa barras DIARIAS de Alpaca (campo n = número de trades del día) para el
universo S&P 500 + Nasdaq 100 actual + valores de EE. UU. del proyecto,
2016-01-01 → 2026-11-13, y combina esos recuentos con las mediciones reales de
alpaca_g0_probe.py (bytes por registro, segundos por página, ratio quotes/trades).

Salida: MICRO_DATA_DIR/g0_probe/g0_budget_results.json. No guarda datos de mercado
en el repo; el panel diario se cachea en MICRO_DATA_DIR/g0_probe/daily_n.parquet.
"""
import json
import math
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alpaca_g0_probe as P  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = P.DATA_DIR / "g0_probe" / "daily_n.parquet"
OUT = P.DATA_DIR / "g0_probe" / "g0_budget_results.json"


def universe():
    c = json.loads((ROOT / "research/macd_combo_sp500_ndx_v1/constituents.json").read_text(encoding="utf-8"))
    idx = set(c["sp500"]) | set(c["ndx"])
    proj = set()

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("ticker"), str):
                proj.add(o["ticker"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads((ROOT / "portfolio.json").read_text(encoding="utf-8")))
    walk(json.loads((ROOT / "docs/data/universe.json").read_text(encoding="utf-8")))
    proj = {t for t in proj if "." not in t and not t.startswith("^") and "=" not in t and "-USD" not in t}
    to_alp = lambda t: t.replace("-", ".")
    return sorted({to_alp(t) for t in idx}), sorted({to_alp(t) for t in proj})


def fetch_daily(symbols):
    rows = []
    for i in range(0, len(symbols), 100):
        chunk = symbols[i:i + 100]
        token = None
        while True:
            p = {"symbols": ",".join(chunk), "timeframe": "1Day", "start": "2016-01-01",
                 "end": "2026-11-13T21:00:00Z", "feed": "sip", "adjustment": "raw", "limit": 10000}
            if token:
                p["page_token"] = token
            r = P.get("/v2/stocks/bars", p)
            if r.status_code != 200:
                raise SystemExit(f"ERR {r.status_code} {r.text[:200]}")
                break
            j = r.json()
            for sym, bars in (j.get("bars") or {}).items():
                for b in bars:
                    rows.append((sym, b["t"][:10], b.get("n", 0), b.get("v", 0), b.get("c")))
            token = j.get("next_page_token")
            if not token:
                break
        print(f"{min(i + 100, len(symbols))}/{len(symbols)}  rows={len(rows)}  req={P._stats['requests']}")
    return pd.DataFrame(rows, columns=["sym", "date", "n", "v", "c"])


def main():
    idx, proj = universe()
    if CACHE.exists():
        df = pd.read_parquet(CACHE)
    else:
        df = fetch_daily(sorted(set(idx) | set(proj)))
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(CACHE, compression="zstd", index=False)
    df["year"] = df["date"].str[:4].astype(int)
    df["pages"] = (df["n"] / 10000).apply(math.ceil).clip(lower=1)

    probe = json.loads((P.OUT).read_text(encoding="utf-8"))["volume_2026-11-13"]
    stocks = [s for s in probe if s != "SPY"]
    b_trade = sum(probe[s]["trades"]["parquet_bytes"] for s in stocks) / sum(probe[s]["trades"]["rows"] for s in stocks)
    b_quote = sum(probe[s]["quotes"]["parquet_bytes"] for s in stocks) / sum(probe[s]["quotes"]["rows_downloaded"] for s in stocks)
    q_ratio = pd.Series({s: probe[s]["quotes"]["rows_est_full_session"] / probe[s]["trades"]["rows"] for s in stocks})
    sec_per_page = sum(probe[s]["trades"]["seconds"] for s in stocks) / sum(probe[s]["trades"]["pages"] for s in stocks)
    b_bar_day = sum(probe[s]["bars"]["parquet_bytes"] for s in stocks) / len(stocks)  # fichero suelto de 1 día: cota superior

    def summarize(sub, label):
        td = len(sub)
        trades = float(sub["n"].sum())
        pages_tr = float(sub["pages"].sum())
        q_est = trades * float(q_ratio.median())
        pages_q = float((sub["n"] * float(q_ratio.median()) / 10000).apply(math.ceil).clip(lower=1).sum())
        pages_bars = math.ceil(td * 390 / 10000)
        # throughput: el límite (180/min) o la latencia medida por página en serie
        serial_ppm = 60 / sec_per_page
        hours = lambda pages, conc: pages / min(180, serial_ppm * conc) / 60
        return {
            "label": label, "ticker_days": td, "tickers": int(sub["sym"].nunique()),
            "trades_total": trades, "trades_per_ticker_day_median": float(sub["n"].median()),
            "bars_1min": {"requests": pages_bars, "hours_at_180pm": round(pages_bars / 180 / 60, 2),
                          "storage_GB_upper": round(td * b_bar_day / 1e9, 2)},
            "trades": {"requests": pages_tr, "hours_serial": round(hours(pages_tr, 1), 1),
                       "hours_3_parallel": round(hours(pages_tr, 3), 1),
                       "storage_GB": round(trades * b_trade / 1e9, 1)},
            "quotes_est": {"rows": q_est, "requests": pages_q, "hours_3_parallel": round(hours(pages_q, 3), 1),
                           "storage_GB": round(q_est * b_quote / 1e9, 1)},
        }

    res = {"measured": {"bytes_per_trade_parquet": round(b_trade, 2), "bytes_per_quote_parquet": round(b_quote, 2),
                        "quotes_per_trade_median": round(float(q_ratio.median()), 2),
                        "quotes_per_trade_by_symbol": q_ratio.round(2).to_dict(),
                        "seconds_per_trades_page_serial": round(sec_per_page, 2),
                        "bars_parquet_bytes_per_ticker_day_single_file": round(b_bar_day)},
           "coverage": {"symbols_requested": len(set(idx) | set(proj)), "symbols_with_data": int(df["sym"].nunique()),
                        "missing_project_us": sorted(set(proj) - set(df["sym"]))},
           "trades_per_day_by_year_median_idx": df[df["sym"].isin(idx)].groupby("year")["n"].median().round(0).to_dict(),
           "configs": []}
    I = df[df["sym"].isin(idx)]
    Pj = df[df["sym"].isin(proj)]
    res["configs"].append(summarize(I, "S&P500+NDX actuales, 2016-2026 completo"))
    res["configs"].append(summarize(I[I["year"] >= 2024], "S&P500+NDX actuales, 2024-2026"))
    res["configs"].append(summarize(Pj, "Valores EE. UU. del proyecto, 2016-2026"))
    res["configs"].append(summarize(Pj[Pj["year"] >= 2024], "Valores EE. UU. del proyecto, 2024-2026"))
    # muestras para nivel B: N valores aleatorios × M días aleatorios (semilla fija), sobre el índice
    for n_t, n_d in ((100, 200), (200, 250), (300, 500)):
        syms = I["sym"].drop_duplicates().sample(n=min(n_t, I["sym"].nunique()), random_state=7)
        days = I["date"].drop_duplicates().sample(n=n_d, random_state=11)
        sub = I[I["sym"].isin(syms) & I["date"].isin(days)]
        res["configs"].append(summarize(sub, f"Muestra B1: {n_t} valores × {n_d} días aleatorios (2016-2026)"))
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False)[:6000])


if __name__ == "__main__":
    main()
