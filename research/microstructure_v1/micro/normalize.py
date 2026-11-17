"""Normalización de registros crudos de Alpaca a tablas tipadas con flags de sesión y condiciones.

No modifica los datos crudos (que se conservan sin pérdida): son vistas deterministas, reproducibles.
Precios y tamaños SIN ajustar por splits (el ajuste se aplica en la capa de variables con identity.split_factors).
"""
import numpy as np
import pandas as pd

from . import calendar, conditions

NY = "America/New_York"
# campo `u` de Alpaca: el trade fue anulado o declarado erróneo después de publicarse (no cuenta como ejecución)
CANCELED_UPDATES = {"canceled", "cancelled", "incorrect", "error"}


def records_to_frame(kind: str, records: list) -> pd.DataFrame:
    """Lista de dicts del API -> DataFrame sin pérdida (t a timestamp ns UTC; condiciones como lista)."""
    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df
    df["t"] = pd.to_datetime(df["t"], utc=True, format="ISO8601")
    return df


def _session_labels(ts_utc: pd.Series, day: str) -> pd.Series:
    o, c = calendar.session_bounds(day, "regular")
    lab = np.where(ts_utc < o, "pre", np.where(ts_utc >= c, "post", "regular"))
    return pd.Series(lab, index=ts_utc.index)


def trades(df: pd.DataFrame, day: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = pd.DataFrame({
        "t": df["t"], "price": df["p"].astype("float64"), "size": df["s"].astype("int64"),
        "exchange": df["x"].astype("string"), "tape": df["z"].astype("string"), "trade_id": df["i"],
    })
    upd = df["u"] if "u" in df.columns else pd.Series(None, index=df.index, dtype="object")
    out["update"] = upd.astype("string")
    out["canceled"] = upd.isin(list(CANCELED_UPDATES)).to_numpy()
    conds = df["c"].apply(lambda v: tuple(v) if isinstance(v, (list, tuple, np.ndarray)) else ((v,) if v else (" ",)))
    out["conditions"] = conds.map("|".join)
    key = out["conditions"] + "#" + out["tape"].fillna("")
    cache = {}
    for k in key.unique():
        cs, tape = k.split("#")
        cache[k] = conditions.minute_flags(cs.split("|"), tape)
    flags = key.map(cache)
    out["upd_oc"] = flags.map(lambda f: f[0])
    out["upd_hl"] = flags.map(lambda f: f[1])
    out["upd_vol"] = flags.map(lambda f: f[2])
    out["unknown_cond"] = flags.map(lambda f: ",".join(f[3]))
    out["odd_lot"] = out["size"] < 100
    codes = out["conditions"].str.split("|")
    out["cond_odd_lot"] = codes.map(lambda cs: conditions.ODD_LOT in cs)
    out["trf"] = out["exchange"] == "D"           # FINRA ADF/TRF (fuera de mercado organizado)
    out["extended_cond"] = codes.map(lambda cs: bool(conditions.EXTENDED_HOURS.intersection(cs)))
    out["session"] = _session_labels(out["t"], day)
    out["minute"] = out["t"].dt.floor("min")
    return out


def bars(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "n": "n_trades",
                             "vw": "vwap"}).copy()
    out["day"] = out["t"].dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    labs = []
    for day, g in out.groupby("day", sort=False):
        if calendar.is_trading_day(day):
            labs.append(_session_labels(g["t"], day))
        else:
            labs.append(pd.Series("closed", index=g.index))
    out["session"] = pd.concat(labs).reindex(out.index)
    return out


def quotes(df: pd.DataFrame, day: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = pd.DataFrame({"t": df["t"], "bid": df["bp"].astype("float64"), "bid_size": df["bs"], "bid_ex": df["bx"],
                        "ask": df["ap"].astype("float64"), "ask_size": df["as"], "ask_ex": df["ax"],
                        "tape": df["z"]})
    out["conditions"] = df["c"].apply(lambda v: "|".join(v) if isinstance(v, (list, tuple, np.ndarray)) else (v or ""))
    out["mid"] = (out["bid"] + out["ask"]) / 2
    out["spread"] = out["ask"] - out["bid"]
    out["zero_side"] = (out["bid"] <= 0) | (out["ask"] <= 0)
    out["crossed"] = (out["bid"] > out["ask"]) & ~out["zero_side"]
    out["locked"] = (out["bid"] == out["ask"]) & ~out["zero_side"]
    out["session"] = _session_labels(out["t"], day)
    return out
