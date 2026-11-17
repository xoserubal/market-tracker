"""Identidad de los valores: un ticker NO es una empresa permanente.

Hallazgos verificados en G1 (2026-11-15):
- Alpaca enlaza renombrados con `asof` (FB/META devuelven la misma serie).
- Con `asof` posterior o '-', un símbolo reutilizado mezcla empresas: ADT 2016-2018 devuelve ADT Corp (hasta
  2016-04-29), ~430 barras diarias de RELLENO con volumen 0 y el último cierre repetido, y ADT Inc (desde
  2018-01-19, con un salto de -70 %). Con asof=2016-03-01 solo devuelve ADT Corp.

- Con un asof ANTIGUO, Alpaca devuelve el «valor» vigente en esa fecha solo hasta su siguiente evento corporativo,
  aunque la empresa siga cotizando con el mismo ticker: CB se corta el 14-ene-2016 (ACE toma el ticker), WMB el
  28-jun-2016, LMT el 15-ago-2016 (canje Leidos), JCI el 2-sep-2016 (fusión con Tyco). Con un asof posterior la
  serie es continua.

Regla: pedir con asof = la ÚLTIMA fecha en que el ticker se observó para la empresa de interés (sesión previa a
la baja del índice; sin asof si sigue vigente), y cortar la serie en ÉPOCAS separadas por tramos de relleno
(≥ ZERO_RUN días seguidos con volumen 0) o por saltos de precio no explicados por splits. Solo se usa la época
que contiene esa fecha. Residuo conocido: en fusiones donde el superviviente hereda el ticker (JCI), la serie es la
del superviviente (la entidad del CIK de Wikipedia), no la de la empresa absorbida.
Entidad = CIK (de Wikipedia) cuando existe; si no, (ticker, época).
"""
import numpy as np
import pandas as pd

ZERO_RUN = 5          # días seguidos con volumen 0 que separan épocas (relleno de Alpaca)
JUMP_LOG = np.log(2)  # |salto diario| > ×2 o ÷2 sin split que lo explique -> sospecha de cambio de entidad


def daily_bars(provider, symbol, start, end, asof=None) -> pd.DataFrame:
    rows = []
    for page in provider.fetch_pages("bars", symbol, start, end, asof=asof, timeframe="1Day"):
        rows.extend(page)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    return df


def split_events(corp_actions: dict, symbol: str) -> pd.DataFrame:
    """ex_date y factor (nuevas/antiguas acciones) de splits directos e inversos del símbolo."""
    rows = []
    for typ in ("forward_splits", "reverse_splits"):
        for a in corp_actions.get(typ, []) or []:
            if a.get("symbol") != symbol:
                continue
            new, old = float(a.get("new_rate") or 0), float(a.get("old_rate") or 0)
            if new > 0 and old > 0:
                rows.append({"ex_date": a.get("ex_date"), "factor": new / old, "type": typ})
    return pd.DataFrame(rows, columns=["ex_date", "factor", "type"])


def epochs(df: pd.DataFrame, splits: pd.DataFrame = None) -> pd.DataFrame:
    """Asigna 'epoch' a cada barra diaria y marca saltos sospechosos. Las barras de relleno quedan con epoch=-1."""
    if df.empty:
        return df.assign(epoch=pd.Series(dtype=int), suspicious_jump=pd.Series(dtype=bool))
    d = df.sort_values("date").reset_index(drop=True).copy()
    zero = d["v"].fillna(0).eq(0)
    run_id = (zero != zero.shift()).cumsum()
    run_len = zero.groupby(run_id).transform("size")
    filler = zero & (run_len >= ZERO_RUN)
    ep = (filler & ~filler.shift(fill_value=False)).cumsum()
    d["epoch"] = np.where(filler, -1, ep)
    # renumerar épocas reales 0..k
    real = sorted(set(d.loc[~filler, "epoch"]))
    d.loc[~filler, "epoch"] = d.loc[~filler, "epoch"].map({e: i for i, e in enumerate(real)})
    split_dates = set(splits["ex_date"]) if splits is not None and not splits.empty else set()
    lr = np.log(d["c"] / d["c"].shift())
    d["suspicious_jump"] = (lr.abs() > JUMP_LOG) & ~d["date"].isin(split_dates) & ~filler
    # un salto grande justo tras un tramo de relleno es la frontera esperada: no se marca dos veces
    d.loc[filler.shift(fill_value=False) & ~filler, "suspicious_jump"] = False
    return d


def epoch_of(d: pd.DataFrame, date: str):
    """(epoch, primera_fecha, última_fecha) de la época que contiene `date` (o la última anterior)."""
    real = d[d["epoch"] >= 0]
    prior = real[real["date"] <= date]
    if prior.empty:
        return None
    e = int(prior["epoch"].iloc[-1])
    seg = real[real["epoch"] == e]
    return e, seg["date"].iloc[0], seg["date"].iloc[-1]


def epoch_summary(d: pd.DataFrame) -> list:
    out = []
    for e, g in d[d["epoch"] >= 0].groupby("epoch"):
        out.append({"epoch": int(e), "start": g["date"].iloc[0], "end": g["date"].iloc[-1], "days": int(len(g)),
                    "first_close": float(g["c"].iloc[0]), "last_close": float(g["c"].iloc[-1]),
                    "suspicious_jumps": g.loc[g["suspicious_jump"], "date"].tolist()})
    return out
