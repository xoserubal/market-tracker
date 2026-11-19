"""Etapa 0 — series por empresa: identidad, splits coherentes, dividendos, eventos, desenlace y Flow Score.

No calcula ningún rendimiento posterior a una señal. Para cada petición (ticker, asof) de work/requests.csv:
1. Barras en bruto → épocas de identidad (micro/identity.py): se usa la época que contiene el último día de
   pertenencia al índice (o la última, si sigue vigente).
2. Splits de Alpaca: solo se aplican si explican el cociente de precios en bruto de su fecha
   (micro/distributions.split_status, |ln| <= 0,15). Los incoherentes pasan a ser eventos.
3. Dividendos en efectivo → serie de rendimiento total (adj). Dividendo >= 10 % del cierre previo = evento.
4. Eventos (como la enmienda 7 de microestructura): escisión de Alpaca o de la lista curada (solo S&P 500 2016-2021),
   split incoherente, dividendo grande, hueco > 10 días naturales. Además, saltos x2 / x0,5 sin explicar (se informan).
5. Desenlace: si la época termina antes del final pedido, fecha y último cierre (la clasificación va en s0_terminal).
6. Flow Score con la réplica de producción (research/flow_cont_rev_v1/features.py) y su descomposición:
   momentum = 2·(0,6·w1 + 0,4·m1) y resto R = Flow − momentum (RSI, MACD, ATR, Koncorde, distancia al máximo).
   flow_complete = todos los componentes con datos (Koncorde D y W, máximo de 365 días).

Salidas (fuera del repo): work/series/<key>.parquet y work/series_summary.csv
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import fn_config as C

sys.path.insert(0, str(C.REPO / "research" / "flow_cont_rev_v1"))
from micro import identity  # noqa: E402
from micro.distributions import split_status, BIG_DIVIDEND, GAP_CAL_DAYS  # noqa: E402

SER = C.WORK / "series"
SER.mkdir(exist_ok=True)
CURATED = C.REPO / "research" / "microstructure_v1" / "distribution_events_dev.csv"


def load_ca():
    out = {}
    for f in sorted(C.CA.glob("ca_*.json")):
        for typ, lst in json.load(open(f))["actions"].items():
            out.setdefault(typ, []).extend(lst)
    t = {}
    sp = []
    for typ in ("forward_splits", "reverse_splits"):
        for a in out.get(typ, []):
            new, old = float(a.get("new_rate") or 0), float(a.get("old_rate") or 0)
            if new > 0 and old > 0:
                sp.append({"symbol": a.get("symbol"), "ex_date": a.get("ex_date"), "factor": new / old})
    t["splits"] = pd.DataFrame(sp, columns=["symbol", "ex_date", "factor"]).drop_duplicates()
    dv = [{"symbol": a.get("symbol"), "ex_date": a.get("ex_date"), "rate": float(a.get("rate") or 0),
           "special": bool(a.get("special"))} for a in out.get("cash_dividends", [])]
    t["dividends"] = pd.DataFrame(dv, columns=["symbol", "ex_date", "rate", "special"]).drop_duplicates()
    so = [{"source_symbol": a.get("source_symbol"), "new_symbol": a.get("new_symbol"),
           "ex_date": a.get("ex_date") or a.get("process_date")} for a in out.get("spin_offs", [])]
    t["spinoffs"] = pd.DataFrame(so, columns=["source_symbol", "new_symbol", "ex_date"])
    nc = [{"old": a.get("old_symbol"), "new": a.get("new_symbol"), "date": a.get("process_date")}
          for a in out.get("name_changes", [])]
    t["name_changes"] = pd.DataFrame(nc, columns=["old", "new", "date"])
    t["raw"] = out
    return t


def symbols_for(ticker, nc):
    """El ticker y sus nombres anteriores según los cambios de nombre de Alpaca (recursivo)."""
    s, frontier = {ticker}, [ticker]
    while frontier:
        x = frontier.pop()
        for o in nc.loc[nc["new"] == x, "old"]:
            if o and o not in s:
                s.add(o)
                frontier.append(o)
    return s


def curated():
    c = pd.read_csv(CURATED, dtype=str)
    return c[["parent", "ex_date"]].dropna()


def build_flow(df):
    """Réplica de computeFlowScore barra a barra (features.ticker_bars) con componentes y marca de completitud."""
    import features as F
    d = df.set_index("date")
    adj = pd.DataFrame({"open": d.open_adj.to_numpy(), "high": d.high_adj.to_numpy(), "low": d.low_adj.to_numpy(),
                        "close": d.adj.to_numpy(), "volume": d.volume.fillna(0).to_numpy()},
                       index=pd.to_datetime(d.index))
    sd, s3, sw, align = F.konc_all(adj)
    c, h, l = d.close.to_numpy(float), d.high.to_numpy(float), d.low.to_numpy(float)
    atr = F.wilder_atr(c, h, l)
    atrp = np.round(atr / c * 100, 1)
    rsi = F.js_round(F.wilder_rsi(c))
    cl = pd.Series(c, index=pd.to_datetime(d.index))
    hi = cl.rolling("365D").max().to_numpy()
    have_year = (cl.index - cl.index[0]).days >= 365
    fh = F.js_round((c - hi) / hi * 100)
    w1 = np.full(len(c), np.nan)
    w1[5:] = F.js_round((c[5:] / c[:-5] - 1) * 100)
    m1 = np.full(len(c), np.nan)
    m1[21:] = F.js_round((c[21:] / c[:-21] - 1) * 100)
    hist = F.macd_hist(c)
    flow, mom = np.full(len(c), np.nan), np.full(len(c), np.nan)
    for i in range(len(c)):
        mb = None if np.isnan(hist[i]) else bool(hist[i] >= 0)
        flow[i] = F.flow_score(F.nz(float(w1[i])), F.nz(float(m1[i])), F.nz(float(rsi[i])), mb,
                               F.nz(float(atrp[i])), sd[i], sw[i], F.nz(float(fh[i])))
        mom[i] = 2 * (0.6 * (0 if np.isnan(w1[i]) else w1[i]) + 0.4 * (0 if np.isnan(m1[i]) else m1[i]))
    out = pd.DataFrame({"date": d.index, "flow": flow, "mom": mom, "R": flow - mom, "w1": w1, "m1": m1,
                        "rsi": rsi, "atrPct": atrp, "macd_hist": hist, "fromHigh": fh,
                        "konc_d": sd, "konc_3d": s3, "konc_w": sw, "konc_align": align})
    out["flow_complete"] = (~np.isnan(w1) & ~np.isnan(m1) & ~np.isnan(rsi) & ~np.isnan(hist) &
                            pd.notna(sd) & pd.notna(sw) & have_year)
    return out


def one(args):
    """Una fila de resumen por ÉPOCA de identidad de la petición: un ticker reutilizado, o una empresa que quiebra y
    reaparece con el mismo ticker (Chesapeake, Gulfport...), da épocas distintas y cada una es una serie propia."""
    r, ca_small = args
    key = r["key"]
    try:
        raw = pd.read_parquet(C.BARS / f"{key}.parquet")
    except FileNotFoundError:
        return [{"key": key, "req_key": key, "status": "no_file"}]
    if raw.empty:
        return [{"key": key, "req_key": key, "status": "empty"}]
    raw["date"] = pd.to_datetime(raw["t"], utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    ep = identity.epochs(raw)
    epochs = sorted(int(x) for x in ep.loc[ep.epoch >= 0, "epoch"].unique())
    out = []
    for e in epochs:
        g = ep[ep.epoch == e].sort_values("date").reset_index(drop=True)
        nxt = ep.loc[ep.epoch > e, "date"]
        stop = nxt.min() if len(nxt) else min(r["end"], C.PRICE_END)
        out.append(one_epoch(r, ca_small, g, e, len(epochs), stop))
    return out


def one_epoch(r, ca_small, g, e, n_epochs, stop):
    key = f"{r['key']}__e{e}"
    e_end = g["date"].iat[-1]
    first_member = r["first_member"]

    syms = symbols_for(r["ticker"], ca_small["name_changes"])
    ss = ca_small["splits"][ca_small["splits"]["symbol"].isin(syms)]
    st = split_status(g[["date", "c"]], ss) if len(ss) else pd.DataFrame(columns=["status", "bar_date", "factor"])
    applied = st[st["status"] == "applied"] if len(st) else st
    # factor de split hacia atrás: precios anteriores a bar_date / factor
    fac = np.ones(len(g))
    for a in applied.itertuples():
        k = int(np.searchsorted(g["date"].to_numpy(), a.bar_date))
        fac[:k] *= a.factor
    o, h, l, c, v = (g[x].to_numpy(float) for x in ("o", "h", "l", "c", "v"))
    so, sh, slo, sc, sv = o / fac, h / fac, l / fac, c / fac, v * fac
    # dividendos → rendimiento total (sobre precios ajustados por split)
    dv = ca_small["dividends"][ca_small["dividends"]["symbol"].isin(syms)]
    pos = {d: i for i, d in enumerate(g["date"])}
    tr = np.ones(len(g))
    events = []
    for x in dv.itertuples():
        i = pos.get(x.ex_date)
        if not i:
            continue
        pc_raw = c[i - 1]
        if pc_raw <= 0 or x.rate <= 0:
            continue
        f = 1 - x.rate / pc_raw
        if x.rate / pc_raw >= BIG_DIVIDEND:
            events.append((x.ex_date, "E1_dividendo_grande"))
        if f > 0:
            tr[:i] *= f
    adj = sc * tr
    for x in (st[st["status"] == "incoherent"].itertuples() if len(st) else []):
        events.append((x.bar_date, "E2_split_incoherente"))
    sp = ca_small["spinoffs"]
    for x in sp[sp["source_symbol"].isin(syms)].itertuples():
        events.append((x.ex_date, "E1_escision_alpaca"))
    cur = ca_small["curated"]
    for x in cur[cur["parent"].isin(syms)].itertuples():
        events.append((x.ex_date, "E1_escision_curada"))
    dt = pd.to_datetime(g["date"])
    gaps = dt.diff().dt.days.to_numpy()
    for i in np.where(gaps > GAP_CAL_DAYS)[0]:
        events.append((g["date"].iat[i], "E3_hueco_serie"))
    ratio = c[1:] / c[:-1]
    ap = set(applied["bar_date"]) if len(applied) else set()
    evd = {d for d, _ in events}
    jumps = [g["date"].iat[i + 1] for i in np.where((ratio > 2) | (ratio < 0.5))[0]
             if g["date"].iat[i + 1] not in ap and g["date"].iat[i + 1] not in evd]

    df = pd.DataFrame({"date": g["date"], "open": so, "high": sh, "low": slo, "close": sc, "volume": sv,
                       "raw_close": c, "raw_volume": v, "adj": adj,
                       "open_adj": so * tr, "high_adj": sh * tr, "low_adj": slo * tr})
    fl = build_flow(df)
    df = df.merge(fl, on="date", how="left")
    df["dollar_vol"] = df.raw_close * df.raw_volume
    df.to_parquet(SER / f"{key}.parquet")

    # termina si la época acaba > 7 días antes de lo pedido (o de la época siguiente: ticker reutilizado/reaparecido)
    terminated = bool((pd.Timestamp(stop) - pd.Timestamp(e_end)).days > 7)
    return {"key": key, "req_key": r["key"], "ticker": r["ticker"], "asof": r["asof"], "indices": r["indices"],
            "names": r["names"], "status": "ok", "bars": len(g), "start": g["date"].iat[0], "end": e_end,
            "epochs_in_request": n_epochs, "epoch": e, "symbols": "|".join(sorted(syms)),
            "splits_applied": int(len(applied)),
            "splits_list": json.dumps([[a.bar_date, float(a.factor)] for a in applied.itertuples()]) if len(applied) else "[]",
            "splits_incoherent": int((st["status"] == "incoherent").sum()) if len(st) else 0,
            "events": json.dumps(sorted(set(events))), "n_events": len(set(events)),
            "unexplained_jumps": json.dumps(jumps), "terminated": terminated,
            "last_close_raw": float(c[-1]), "first_member": first_member, "last_member": r["last_member"],
            "flow_complete_from": (fl.loc[fl.flow_complete, "date"].min() if fl.flow_complete.any() else None)}


def main():
    plan = pd.read_csv(C.WORK / "requests.csv", dtype=str, keep_default_na=False)
    ca = load_ca()
    ca_small = {k: ca[k] for k in ("splits", "dividends", "spinoffs", "name_changes")}
    ca_small["curated"] = curated()
    only = set(sys.argv[1:])
    rows = [r for r in plan.to_dict("records") if not only or r["ticker"] in only]
    with ProcessPoolExecutor(6) as ex:
        res = [x for lst in ex.map(one, [(r, ca_small) for r in rows], chunksize=8) for x in lst]
    s = pd.DataFrame(res)
    if not only:
        s.to_csv(C.WORK / "series_summary.csv", index=False)
    print(s.status.value_counts().to_dict())
    if "terminated" in s:
        print("terminadas", int(s.terminated.fillna(False).sum()), "con eventos", int((s.n_events.fillna(0) > 0).sum()))


if __name__ == "__main__":
    main()
