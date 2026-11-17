"""G2A — días de caída de datos de 1 minuto (enmienda 8), sin resultados.

Un día es caída de datos si no es media sesión en el calendario oficial y más del 20 % de los miembros del S&P 500
con historia tiene menos de la mitad de su mediana de barras de minuto de las 60 sesiones previas. Esos días son
sesiones normales en el mercado; lo que falta es el dato de Alpaca. Para las variables intradía se tratan como no
sesión (ER, volumen por precio); las diarias no cambian.
Salida: MICRO_DATA_DIR/results/g2a_intraday_outages.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, storage  # noqa: E402

SHARE, RATIO, WIN = 0.20, 0.5, 60


def detect():
    root = storage.root()
    x = pd.concat([pd.read_parquet(f, columns=["entity", "day", "n_min"])
                   for f in sorted((root / "features" / "intraday_daily").glob("*.parquet"))], ignore_index=True)
    x["entity"] = x["entity"].astype(str)
    sp = pd.read_parquet(root / "reference" / "universe_intervals.parquet")
    members = set(sp.loc[sp["source"] == "sp500", "entity"].astype(str))
    x = x[x["entity"].isin(members)].sort_values(["entity", "day"])
    x["med"] = x.groupby("entity")["n_min"].transform(lambda s: s.shift(1).rolling(WIN, min_periods=20).median())
    x = x[x["med"].notna()]
    day = x.assign(low=x["n_min"] < RATIO * x["med"]).groupby("day")["low"].agg(["mean", "size"])
    cand = day[day["mean"] > SHARE]
    out = []
    for d, r in cand.iterrows():
        out.append({"day": d, "share_low": round(float(r["mean"]), 3), "n": int(r["size"]),
                    "early_close": bool(calendar.is_early_close(d))})
    outages = [o["day"] for o in out if not o["early_close"]]
    res = {"rule": f"no media sesión y > {SHARE:.0%} de miembros con n_min < {RATIO} · mediana({WIN} previas)",
           "candidates": out, "outages": outages}
    (root / "results" / "g2a_intraday_outages.json").write_text(json.dumps(res, indent=1, ensure_ascii=False),
                                                               encoding="utf-8")
    return res


def outage_days():
    p = storage.root() / "results" / "g2a_intraday_outages.json"
    return set(json.loads(p.read_text(encoding="utf-8"))["outages"])


if __name__ == "__main__":
    print(json.dumps(detect(), indent=1, ensure_ascii=False))
