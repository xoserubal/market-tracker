"""Calendario de sesiones de EE. UU. (Alpaca /v2/calendar), con festivos, cierres anticipados y horario de verano.

Las horas del calendario están en hora de Nueva York; se convierten a UTC con zoneinfo (DST correcto).
Se cachea en reference/calendar_alpaca.parquet.
"""
from datetime import datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd

from . import storage

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def cache_path():
    return storage.root() / "reference" / "calendar_alpaca.parquet"


def sync(provider, start="2015-12-01", end="2027-12-31"):
    rows = provider.calendar(start, end)
    df = pd.DataFrame(rows)[["date", "open", "close", "session_open", "session_close"]]
    storage.write_parquet_atomic(df, cache_path())
    load.cache_clear()
    return df


@lru_cache(maxsize=1)
def load() -> pd.DataFrame:
    df = pd.read_parquet(cache_path())
    return df.set_index("date")


def is_trading_day(day: str) -> bool:
    return day in load().index


def trading_days(start: str, end: str) -> list:
    idx = load().index
    return [d for d in idx if start <= d <= end]


def _hm(s: str) -> time:
    s = s.replace(":", "")
    return time(int(s[:2]), int(s[2:4]))


def session_bounds(day: str, session: str = "regular"):
    """(inicio_utc, fin_utc) de la sesión regular o extendida ('full': 04:00-20:00 NY)."""
    row = load().loc[day]
    d = datetime.strptime(day, "%Y-%m-%d").date()
    if session == "regular":
        a, b = _hm(row["open"]), _hm(row["close"])
    elif session == "full":
        a, b = _hm(row["session_open"]), _hm(row["session_close"])
    else:
        raise ValueError(session)
    start = datetime.combine(d, a, NY).astimezone(UTC)
    end = datetime.combine(d, b, NY).astimezone(UTC)
    return pd.Timestamp(start), pd.Timestamp(end)


def ny_range(day: str, a: str, b: str):
    """(inicio_utc, fin_utc) de un tramo 'HH:MM'-'HH:MM' en hora de Nueva York del día dado (DST correcto)."""
    d = datetime.strptime(day, "%Y-%m-%d").date()
    start = datetime.combine(d, _hm(a), NY).astimezone(UTC)
    end = datetime.combine(d, _hm(b), NY).astimezone(UTC)
    if end <= start:
        raise ValueError(f"rango vacío {a}-{b}")
    return pd.Timestamp(start), pd.Timestamp(end)


def is_early_close(day: str) -> bool:
    return _hm(load().loc[day]["close"]) < time(16, 0)


def iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
