"""G2A — barras diarias SIP sin ajustar y acciones corporativas (dividendos, splits) del SPY y los 11 ETF sectoriales
SPDR, 2016-2026. Benchmarks de resultado y de fuerza relativa (G2A_PROTOCOLO §2). XLC empieza en jun-2018 y XLRE en
oct-2015: antes no hay ETF de ese sector y la fuerza relativa sectorial queda vacía (se informa).

Salidas: MICRO_DATA_DIR/reference/benchmarks_daily.parquet y benchmarks_corporate_actions.parquet.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import identity, runtime, storage  # noqa: E402

ETFS = ["SPY", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
FIRST, LAST = "2016-01-01", "2026-11-13"


def main():
    P = runtime.alpaca()
    rows = []
    for s in ETFS:
        d = identity.daily_bars(P, s, FIRST, LAST + "T21:00:00Z")
        d["symbol"] = s
        rows.append(d)
    daily = pd.concat(rows, ignore_index=True)
    keep = [c for c in ["symbol", "date", "o", "h", "l", "c", "v", "n", "vw"] if c in daily.columns]
    daily = daily[keep].sort_values(["symbol", "date"]).reset_index(drop=True)
    ca = P.corporate_actions(ETFS, FIRST, LAST, types=None)
    ca_df = pd.DataFrame([{"type": t, "symbol": a.get("symbol"), "ex_date": a.get("ex_date"),
                           "json": json.dumps(a, sort_keys=True)} for t, v in ca.items() for a in (v or [])])
    ref = storage.root() / "reference"
    storage.write_parquet_atomic(daily, ref / "benchmarks_daily.parquet")
    storage.write_parquet_atomic(ca_df, ref / "benchmarks_corporate_actions.parquet")
    print(daily.groupby("symbol")["date"].agg(["min", "max", "size"]).to_string())
    print(ca_df.groupby(["symbol", "type"]).size().to_string())


if __name__ == "__main__":
    main()
