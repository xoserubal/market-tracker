"""Estimación del lado agresor de cada trade. Nunca se fuerza: lo no clasificable queda en 0 (indeterminado).

Métodos (todos devuelven +1 compra agresiva, -1 venta agresiva, 0 indeterminado):
- tick:     regla del tick sobre la secuencia de precios de referencia (sube -> compra; baja -> venta; igual ->
            hereda el último cambio distinto de cero; el primer trade sin referencia queda indeterminado).
- bidask:   estricta sobre el NBBO vigente: precio >= ask -> compra; <= bid -> venta; dentro del diferencial -> 0.
- lr:       Lee-Ready: precio por encima del punto medio -> compra; por debajo -> venta; en el punto medio -> regla
            del tick. Sin quote válida -> 0 (no se rellena con el tick: sería otro método).
- emo:      Ellis-Michaely-O'Hara: en el ask/bid (o fuera) -> lado de la quote; dentro del diferencial -> tick.

Siempre indeterminado: subastas (O, Q, 5, 6, M), precios no estándar (B, C, G, H, N, P, R, V, W, Z, 4, 7, 9) y trades
anulados. Las subastas son volumen real sin agresor (cruce de órdenes); se informan aparte.

Quotes: NBBO consolidado de Alpaca (feed SIP). Se usa la última quote ESTRICTAMENTE anterior al trade (por defecto)
desplazada `quote_lag_ms`; la quote no vale si un lado es 0, está cruzada o bloqueada (no se busca otra anterior:
sería obsoleta) o si tiene más de `max_quote_age_s`. Fuera de las ventanas con quotes descargadas: 'no_coverage'.

Limitaciones que el resultado arrastra y la interfaz debe mostrar:
- Los trades fuera de mercado (código D, FINRA TRF) llevan la hora de comunicación, que puede llegar segundos
  después de la ejecución: su comparación con el NBBO y su lugar en la secuencia del tick son menos fiables.
- Antes de ~2018 los timestamps de Alpaca tienen precisión de milisegundos: el emparejamiento trade-quote es más
  ambiguo en esos años.
- Concordancia entre métodos no es exactitud: no hay lado agresor verdadero con el que comparar.
- La absorción pasiva (órdenes límite en espera que reciben las agresivas) no se observa sin libro de órdenes;
  solo se puede inferir indirectamente (mucho volumen agresor en un nivel sin que el precio avance).
"""
import numpy as np
import pandas as pd

METHODS = ("tick", "bidask", "lr", "emo")
EPS = 1e-9


def _ffill_values(a: np.ndarray) -> np.ndarray:
    s = pd.Series(a)
    return s.ffill().to_numpy()


def classify(tr: pd.DataFrame, quotes: pd.DataFrame = None, coverage: list = None, *, quote_lag_ms: float = 0.0,
             strict_before: bool = True, max_quote_age_s: float = 10.0, ref_exclude_trf: bool = False,
             ref_exclude_odd: bool = False, ref_exclude_nonbar: bool = False) -> pd.DataFrame:
    """Devuelve una copia de `tr` (ordenado por t) con las columnas de clasificación.

    Variantes de la secuencia de referencia del tick (sensibilidad, G1.5 §3 y §6): sin TRF, sin odd lots, o solo
    trades que actualizan máximo/mínimo de las barras (`ref_exclude_nonbar`: quita odd lots y comunicaciones
    tardías, que generan un tick falso y su vuelta). Los trades excluidos de la referencia se siguen clasificando.
    """
    tr = tr.sort_values("t", kind="stable").reset_index(drop=True).copy()
    n = len(tr)
    price = tr["price"].to_numpy()
    excluded = (tr["auction"] | tr["nonstandard"] | tr["canceled"]).to_numpy()
    ref = ~excluded
    if ref_exclude_trf:
        ref &= ~tr["trf"].to_numpy()
    if ref_exclude_odd:
        ref &= ~tr["odd_lot"].to_numpy()
    if ref_exclude_nonbar:
        ref &= tr["upd_hl"].to_numpy().astype(bool)

    # ── regla del tick ──
    ref_price = np.where(ref, price, np.nan)
    last_ref_price = _ffill_values(np.concatenate([[np.nan], ref_price[:-1]])) if n else ref_price
    raw = np.sign(price - last_ref_price)
    raw = np.where(np.abs(price - last_ref_price) < EPS, 0.0, raw)
    dir_ref = np.where(ref & (raw != 0) & ~np.isnan(raw), raw, np.nan)      # cambios de precio en la referencia
    carried = _ffill_values(dir_ref)                                         # último cambio distinto de 0 (hasta i)
    prev_dir = np.concatenate([[np.nan], carried[:-1]]) if n else carried    # ... estrictamente antes de i
    tick = np.where(~np.isnan(raw) & (raw != 0), raw, prev_dir)
    tick = np.where(np.isnan(tick) | excluded, 0, tick).astype("int8")
    tr["side_tick"] = tick
    tr["tick_kind"] = pd.Categorical(np.select(
        [excluded, np.isnan(raw) & np.isnan(prev_dir), raw > 0, raw < 0, prev_dir > 0, prev_dir < 0],
        ["excluded", "no_reference", "up", "down", "zero_up", "zero_down"], "no_reference"))

    # ── NBBO vigente ──
    tr["bid"] = np.nan
    tr["ask"] = np.nan
    tr["quote_age_ms"] = np.nan
    state = np.full(n, "no_coverage", dtype=object)
    if quotes is not None and len(quotes) and n:
        covered = np.zeros(n, dtype=bool)
        tt = tr["t"]
        for a, b in (coverage or [(quotes["t"].min(), quotes["t"].max() + pd.Timedelta(seconds=1))]):
            covered |= ((tt >= a) & (tt < b)).to_numpy()
        lagged = tr[["t"]].assign(tq=tt - pd.Timedelta(milliseconds=quote_lag_ms), i=np.arange(n))
        q = quotes[["t", "bid", "ask"]].rename(columns={"t": "tq"}).assign(tquote=quotes["t"].to_numpy())
        m = pd.merge_asof(lagged.sort_values("tq"), q.sort_values("tq"), on="tq", direction="backward",
                          allow_exact_matches=not strict_before).sort_values("i")
        bid, ask = m["bid"].to_numpy(), m["ask"].to_numpy()
        age = (m["tq"] - m["tquote"]).dt.total_seconds().to_numpy() * 1000
        tr["bid"], tr["ask"], tr["quote_age_ms"] = bid, ask, age
        st = np.select([~covered, np.isnan(bid), (bid <= 0) | (ask <= 0), bid > ask + EPS, np.abs(bid - ask) < EPS,
                        age > max_quote_age_s * 1000],
                       ["no_coverage", "missing", "zero_side", "crossed", "locked", "stale"], "ok")
        state = st
    tr["quote_state"] = pd.Categorical(state, categories=["ok", "no_coverage", "missing", "zero_side", "crossed",
                                                          "locked", "stale"])
    ok = (tr["quote_state"] == "ok").to_numpy() & ~excluded
    bid, ask = tr["bid"].to_numpy(), tr["ask"].to_numpy()
    mid = (bid + ask) / 2
    spread = ask - bid
    with np.errstate(invalid="ignore", divide="ignore"):
        tr["pos_in_spread"] = np.where(ok & (spread > EPS), (price - bid) / spread, np.nan)
    at_or_above_ask = ok & (price >= ask - EPS)
    at_or_below_bid = ok & (price <= bid + EPS)
    above_mid = ok & (price > mid + EPS)
    below_mid = ok & (price < mid - EPS)
    at_mid = ok & ~above_mid & ~below_mid
    tr["side_bidask"] = np.select([at_or_above_ask, at_or_below_bid], [1, -1], 0).astype("int8")
    tr["side_lr"] = np.select([above_mid, below_mid, at_mid], [1, -1, tick], 0).astype("int8")
    inside = ok & ~at_or_above_ask & ~at_or_below_bid
    tr["side_emo"] = np.select([at_or_above_ask, at_or_below_bid, inside], [1, -1, tick], 0).astype("int8")
    tr["spread_zone"] = pd.Categorical(np.select(
        [~ok, price > ask + EPS, np.abs(price - ask) <= EPS, price < bid - EPS, np.abs(price - bid) <= EPS,
         above_mid, below_mid], ["no_quote", "above_ask", "at_ask", "below_bid", "at_bid", "inside_upper",
                                 "inside_lower"], "at_mid"))
    tr["excluded_reason"] = pd.Categorical(np.select(
        [tr["canceled"].to_numpy(), tr["auction"].to_numpy(), tr["nonstandard"].to_numpy()],
        ["canceled", "auction", "nonstandard"], ""))
    return tr


def summary(tr: pd.DataFrame, live_only: bool = True) -> dict:
    """Proporción de volumen clasificable por método, desglose de lo indeterminado y concordancia entre métodos."""
    d = tr[~tr["canceled"]] if live_only else tr
    vol = float(d["size"].sum()) or 1.0
    out = {"trades": int(len(d)), "volume": int(d["size"].sum()), "methods": {}}
    for m in METHODS:
        s = d[f"side_{m}"]
        out["methods"][m] = {"buy_share": round(float(d.loc[s > 0, "size"].sum() / vol), 4),
                             "sell_share": round(float(d.loc[s < 0, "size"].sum() / vol), 4),
                             "undetermined_share": round(float(d.loc[s == 0, "size"].sum() / vol), 4)}
    reasons = d["excluded_reason"].astype(str).replace("", "eligible")
    out["volume_by_exclusion"] = {k: round(float(v / vol), 4) for k, v in d.groupby(reasons, observed=True)["size"].sum().items()}
    out["volume_by_quote_state"] = {k: round(float(v / vol), 4) for k, v in d.groupby("quote_state", observed=True)["size"].sum().items()}
    out["volume_by_spread_zone"] = {k: round(float(v / vol), 4) for k, v in d.groupby("spread_zone", observed=True)["size"].sum().items()}
    out["trf_volume_share"] = round(float(d.loc[d["trf"], "size"].sum() / vol), 4)
    out["odd_lot_volume_share"] = round(float(d.loc[d["odd_lot"], "size"].sum() / vol), 4)
    agree = {}
    for i, a in enumerate(METHODS):
        for b in METHODS[i + 1:]:
            sa, sb = d[f"side_{a}"], d[f"side_{b}"]
            both = (sa != 0) & (sb != 0)
            vb = float(d.loc[both, "size"].sum())
            agree[f"{a}~{b}"] = {"both_classified_share": round(vb / vol, 4),
                                 "agreement_when_both": round(float(d.loc[both & (sa == sb), "size"].sum() / vb), 4) if vb else None}
    out["agreement"] = agree
    by_venue = {}
    for name, mask in (("exchange", ~d["trf"]), ("trf", d["trf"])):
        g = d[mask]
        v = float(g["size"].sum())
        if not v:
            continue
        sa, sb = g["side_tick"], g["side_lr"]
        both = (sa != 0) & (sb != 0)
        vb = float(g.loc[both, "size"].sum())
        by_venue[name] = {"volume_share": round(v / vol, 4),
                          "lr_undetermined_share": round(float(g.loc[g["side_lr"] == 0, "size"].sum() / v), 4),
                          "tick_lr_agreement": round(float(g.loc[both & (sa == sb), "size"].sum() / vb), 4) if vb else None,
                          "at_mid_share": round(float(g.loc[g["spread_zone"] == "at_mid", "size"].sum() / v), 4)}
    out["by_venue"] = by_venue
    return out
