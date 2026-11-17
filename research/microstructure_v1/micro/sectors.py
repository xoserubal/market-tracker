"""Sector GICS a fecha (G2A_PROTOCOLO §2), con la reconstrucción de research/sector_breadth_v1.

Regla: sector de la instantánea anual de Wikipedia vigente en la fecha (la última con timestamp <= fecha).
- Si el valor no está en ella (alta a mitad de año), se usa la siguiente instantánea en la que aparece. Es
  información posterior, pero sobre un dato casi constante (el sector) y no sobre precios; se cuenta y se informa.
- Las reclasificaciones GICS generales (2016-09-01, 2018-09-24, 2023-03-20) se aplican en su fecha, como en
  sector_breadth_v1.
- «Telecommunication Services» se normaliza a «Communication Services». El ETF XLC empieza el 2018-06-19: antes no
  hay ETF para ese sector.
"""
import json
from functools import lru_cache

import pandas as pd

from . import universe


@lru_cache(maxsize=1)
def _tables():
    bp = universe._bp()
    revs = json.load(open(universe.SB / "data" / "wiki_revisions.json"))
    ts = {y: pd.Timestamp(revs[str(y)]["timestamp"]).tz_localize(None).strftime("%Y-%m-%d") for y in bp.YEARS}
    by = {}
    for y in bp.YEARS:
        for r in bp.read_snapshot(y)[0].itertuples():
            by.setdefault(r.ticker, {})[y] = r.sector
    for r in bp.read_snapshot("current")[0].itertuples():
        by.setdefault(r.ticker, {})[9999] = r.sector
    return bp, ts, by


def sector_etf(sector: str):
    bp, _, _ = _tables()
    return bp.SECTOR_ETF.get(sector)


def sector_at(ticker: str, date: str):
    """(sector, origen) con origen 'snapshot', 'next_snapshot' o 'unknown'. ticker en formato Wikipedia o Alpaca."""
    bp, ts, by = _tables()
    t = bp.norm_t(ticker)
    secs = by.get(t)
    if not secs:
        return None, "unknown"
    years = [y for y in sorted(ts) if ts[y] <= date]
    y = years[-1] if years else min(ts)
    s = secs.get(y)
    src = "snapshot"
    if s is None:
        later = [secs[k] for k in sorted(secs) if k > y]
        if not later:
            earlier = [secs[k] for k in sorted(secs) if k < y]
            return (earlier[-1], "previous_snapshot") if earlier else (None, "unknown")
        return later[0], "next_snapshot"
    nxt = next((secs[k] for k in sorted(secs) if k > y), None)
    if nxt and nxt != s:
        upper = ts.get(y + 1, "2100-01-01")
        for rd in bp.RECLASS:
            rds = rd.strftime("%Y-%m-%d")
            if ts[y] < rds <= upper and date >= rds:
                s = nxt
    return s, src
