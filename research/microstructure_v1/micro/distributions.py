"""Splits coherentes, eventos de reparto y rupturas de identidad por entidad (G2A, enmienda 7).

No usa ningún resultado: solo acciones corporativas, la lista curada de escisiones y precios en la fecha del evento.

- **Split coherente:** el registro de split de Alpaca se aplica solo si explica el cociente de precios en bruto de su
  ex_date mejor que la hipótesis «no hubo split» y con |ln(cociente·factor)| <= SPLIT_TOL. Alpaca codifica a veces el
  ratio de una escisión como un split de la matriz (TGNA, EQT, Aptiv, Arconic, UTX) o aplica un canje a otra entidad
  con el mismo símbolo (Gardner Denver/IR 2020-03-02): esos registros no se aplican y pasan a ser eventos.
- **Eventos** (E1 reparto, E2 split incoherente, E3 ruptura de identidad): ver `entity_events`.
- **Exclusión:** un valor-día (e, t) queda fuera si algún evento de e cae en [t - LOOKBACK, t + HORIZON] sesiones
  del calendario oficial (ventana de variables y de resultado).
"""
from pathlib import Path

import numpy as np
import pandas as pd

SPLIT_TOL = 0.15          # |ln(cociente bruto · factor)| máximo para aplicar un split
SWITCH_TOL = 0.10         # |ln salto| en un cambio de tramo de petición que se toma como ruptura de identidad
GAP_CAL_DAYS = 10         # hueco de la serie (días naturales) que se toma como ruptura
BIG_DIVIDEND = 0.10       # dividendo en efectivo >= 10 % del cierre previo
LOOKBACK, HORIZON = 259, 40   # [t-259, t] variables (260 sesiones, enmienda 1); (t, t+40] resultado
CURATED = Path(__file__).resolve().parent.parent / "distribution_events_dev.csv"


def split_status(g: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """g: barras no de relleno de UNA entidad (date, c) ordenadas. splits: registros candidatos (por símbolo).
    Devuelve los registros con raw_ratio, err, err0 y status ('applied' | 'incoherent' | 'outside')."""
    dates = g["date"].to_numpy()
    c = g["c"].to_numpy(float)
    out = []
    for r in splits.itertuples():
        k = int(np.searchsorted(dates, r.ex_date))
        if k == 0 or k >= len(dates):
            out.append({"ex_date": r.ex_date, "symbol": r.symbol, "factor": r.factor, "raw_ratio": np.nan,
                        "status": "outside"})
            continue
        raw = c[k] / c[k - 1]
        err, err0 = float(np.log(raw * r.factor)), float(np.log(raw))
        ok = abs(err) <= SPLIT_TOL and abs(err) < abs(err0)
        # ex_date sin barra propia: el split se aplica a la primera barra posterior (mismo criterio que antes)
        out.append({"ex_date": r.ex_date, "symbol": r.symbol, "factor": r.factor, "raw_ratio": raw, "err": err,
                    "err0": err0, "status": "applied" if ok else "incoherent", "bar_date": dates[k]})
    return pd.DataFrame(out)


def curated_events() -> pd.DataFrame:
    cur = pd.read_csv(CURATED, dtype=str)
    return cur[cur["entity"].notna() & (cur["entity"] != "")][["entity", "ex_date", "parent", "child", "source"]]


def entity_events(e: str, g: pd.DataFrame, syms: set, act: dict, spin_raw: pd.DataFrame, cur: pd.DataFrame):
    """Eventos de la entidad e. g: barras no de relleno (date, c, symbol, asof) ordenadas por fecha.
    spin_raw: escisiones de Alpaca (source_symbol, ex_date). Devuelve (splits aplicados, eventos)."""
    ss = act["splits"][act["splits"]["symbol"].isin(syms)]
    st = split_status(g, ss) if len(ss) else pd.DataFrame(columns=["ex_date", "status", "factor", "bar_date"])
    applied = st[st["status"] == "applied"] if len(st) else st
    ev = []
    for r in st[st["status"] == "incoherent"].itertuples() if len(st) else []:
        ev.append((r.bar_date, "E2_split_incoherente", f"{r.symbol} factor {r.factor:.4g} cociente {r.raw_ratio:.3f}"))
    for r in spin_raw[spin_raw["source_symbol"].isin(syms)].itertuples():
        ev.append((r.ex_date, "E1_escision_alpaca", f"{r.source_symbol}->{r.new_symbol}"))
    for r in cur[cur["entity"] == e].itertuples():
        ev.append((r.ex_date, "E1_escision_curada", f"{r.parent}->{r.child} ({r.source})"))
    dates = g["date"].to_numpy()
    c = g["c"].to_numpy(float)
    pc = pd.Series(c).shift().to_numpy()
    dv = act["dividends"][act["dividends"]["symbol"].isin(syms)]
    pos = {d: i for i, d in enumerate(dates)}
    for r in dv.itertuples():
        i = pos.get(r.ex_date)
        if i and pc[i] > 0 and r.rate / pc[i] >= BIG_DIVIDEND:
            ev.append((r.ex_date, "E1_dividendo_grande", f"{r.rate} = {100 * r.rate / pc[i]:.1f} % del cierre previo"))
    # E3: cambios de tramo de petición con salto no explicado por un split aplicado, y huecos de la serie
    key = (g["symbol"].astype(str) + "|" + g["asof"].fillna("").astype(str)).to_numpy()
    applied_bars = set(applied["bar_date"]) if len(applied) else set()
    dt = pd.to_datetime(pd.Series(dates))
    gap = dt.diff().dt.days.to_numpy()
    for i in range(1, len(dates)):
        if gap[i] > GAP_CAL_DAYS:
            ev.append((dates[i], "E3_hueco_serie", f"{int(gap[i])} días naturales desde {dates[i - 1]}"))
        elif key[i] != key[i - 1] and dates[i] not in applied_bars:
            j = float(np.log(c[i] / c[i - 1]))
            if abs(j) > SWITCH_TOL:
                ev.append((dates[i], "E3_cambio_tramo", f"{key[i - 1]} -> {key[i]} salto {np.exp(j):.3f}"))
    evdf = pd.DataFrame(ev, columns=["date", "kind", "detail"]).drop_duplicates()
    evdf.insert(0, "entity", e)
    return applied, evdf


def excluded_mask(dates, event_dates, days_pos: dict) -> np.ndarray:
    """True si alguna fecha de evento cae en [t - LOOKBACK, t + HORIZON] (sesiones del calendario oficial)."""
    p = np.array([days_pos.get(d, -10 ** 9) for d in dates])
    ep = np.sort(np.array([days_pos[d] for d in event_dates if d in days_pos])) if len(event_dates) else np.array([])
    if not len(ep):
        return np.zeros(len(dates), bool)
    lo = np.searchsorted(ep, p - LOOKBACK, side="left")
    hi = np.searchsorted(ep, p + HORIZON, side="right")
    return hi > lo


def unexplained_jumps(g: pd.DataFrame, applied: pd.DataFrame, events: pd.DataFrame, days_pos: dict, near=3):
    """Saltos brutos >x2 o <x0,5 no explicados por un split aplicado ni a <= near sesiones de un evento:
    movimientos de mercado reales (se conservan; sensibilidad que los excluye)."""
    dates = g["date"].to_numpy()
    r = g["c"].to_numpy(float) / pd.Series(g["c"].to_numpy(float)).shift().to_numpy()
    ap = set(applied["bar_date"]) if len(applied) else set()
    evp = [days_pos[d] for d in events["date"] if d in days_pos]
    out = []
    for i in np.where((r > 2) | (r < 0.5))[0]:
        d = dates[i]
        if d in ap:
            continue
        if any(abs(days_pos.get(d, -10 ** 9) - q) <= near for q in evp):
            continue
        out.append((d, float(r[i])))
    return out


def applied_splits_by_entity() -> dict:
    """Splits que sí se aplican (coherentes con el precio), por entidad, de results/g2a_split_status.parquet."""
    from micro import storage
    st = pd.read_parquet(storage.root() / "results" / "g2a_split_status.parquet")
    st = st[st["status"] == "applied"][["entity", "symbol", "ex_date", "factor"]]
    return {e: g.reset_index(drop=True) for e, g in st.groupby("entity")}


def events_by_entity() -> dict:
    from micro import storage
    ev = pd.read_parquet(storage.root() / "results" / "g2a_events.parquet")
    return {e: sorted(set(g["date"])) for e, g in ev.groupby("entity")}
