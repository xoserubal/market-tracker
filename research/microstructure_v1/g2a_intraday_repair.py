"""Reparación de features/intraday_daily y features/vap_daily calculados antes del arreglo de g2a_intraday_daily.py.

El resumen asignaba cada día de una unidad del nivel A a UNA sola entidad (dict por fecha). Cuando la unidad servía
a varias entidades el mismo día (CIK del S&P y ticker del proyecto «T:»), solo quedaba la última. Aquí se replica
cada fila a todas las entidades de su unidad: (símbolo, asof, fecha) → entidades, con la misma tabla `ua` que usa el
resumen. Idempotente: sobre un fichero ya reparado no añade nada.

    py -3 g2a_intraday_repair.py            # todos los meses
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, storage  # noqa: E402
import g1_plans  # noqa: E402
from micro.outcomes import DEV_LAST_DECISION  # noqa: E402


def unit_map():
    ref = storage.root() / "reference"
    iv = pd.read_parquet(ref / "universe_intervals.parquet")
    daily = pd.read_parquet(ref / "daily_bars_levelA.parquet").drop_duplicates(["entity", "date"])
    ua = g1_plans.level_a_days(iv, daily, calendar.trading_days(g1_plans.FIRST, "2026-11-13"))
    ua = ua[ua["date"] <= DEV_LAST_DECISION].copy()
    ua["asof_k"] = [x if isinstance(x, str) and x.strip() else "" for x in ua["asof"]]
    ua["entity"] = ua["entity"].astype(str)
    return ua[["entity", "symbol", "asof_k", "date"]].drop_duplicates()


def expand(df, ua_m, day_col="day"):
    """Replica cada fila a todas las entidades de su unidad (símbolo, asof, fecha)."""
    if df.empty:
        return df, 0
    df = df.copy()
    df["entity"] = df["entity"].astype(str)
    key = ua_m.rename(columns={"date": day_col})
    src = df.merge(key, on=["entity", "symbol", day_col], how="left")
    if src["asof_k"].isna().any():
        raise RuntimeError(f"{int(src['asof_k'].isna().sum())} filas sin unidad de origen")
    sib = key.rename(columns={"entity": "entity_new"})
    x = src.merge(sib, on=["symbol", "asof_k", day_col], how="inner")
    x = x[x["entity_new"] != x["entity"]].drop(columns=["entity", "asof_k"]).rename(columns={"entity_new": "entity"})
    have = set(zip(df["entity"], df[day_col]))
    x = x[[(e, d) not in have for e, d in zip(x["entity"], x[day_col])]]
    out = pd.concat([df, x[df.columns]], ignore_index=True)
    return out, len(x)


def main():
    root = storage.root()
    ua = unit_map()
    ua["month"] = ua["date"].str[:7]
    tot_d = tot_v = 0
    for fd in sorted((root / "features" / "intraday_daily").glob("*.parquet")):
        month = fd.stem
        fv = root / "features" / "vap_daily" / fd.name
        ua_m = ua[ua["month"] == month].drop(columns="month")
        d = pd.read_parquet(fd)
        v = pd.read_parquet(fv)
        d2, nd = expand(d, ua_m)
        v2, nv = expand(v, ua_m)
        if nd or nv:
            storage.write_parquet_atomic(v2, fv)
            storage.write_parquet_atomic(d2, fd)
        tot_d += nd
        tot_v += nv
        print(month, "+días", nd, "+vap", nv, flush=True)
    print("total +días", tot_d, "+vap", tot_v)


if __name__ == "__main__":
    main()
