"""G2A — variables candidatas y de referencia por entidad y día, solo DESARROLLO (fechas <= 2021-10-29).

No calcula resultados. Junta:
- barras diarias SIP de referencia, ajustadas hacia atrás por splits (enmienda 4.4);
- resumen intradía y volumen por precio de g2a_intraday_daily.py (minutos de sesión regular);
- benchmarks (SPY y ETF sectoriales) de g2a_benchmarks.py;
- Flow/Early Flow de g2a_flow.py.

Calcula con micro/features.py las variables de las familias C y A para las dos L de la rejilla, las condiciones de
la población y los factores de referencia de H-A1.
Salida: MICRO_DATA_DIR/features/dev_features.parquet. Control de memoria igual que el resumen intradía.
"""
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, distributions as D, features as F, outcomes, sectors, storage  # noqa: E402
import g2a_coverage  # noqa: E402
import g2a_intraday_daily as gi  # noqa: E402
import g2a_outages  # noqa: E402

DEV = outcomes.DEV_LAST_DECISION
LS = (40, 120)


def split_factors(dates, splits):
    """F_d = producto de factores con ex_date > d (ajuste hacia atrás: precio/F, volumen·F)."""
    f = np.ones(len(dates))
    for r in splits.itertuples():
        f[dates < r.ex_date] *= r.factor
    return f


def bench_series(bd, bca, sym):
    g = bd[bd["symbol"] == sym].sort_values("date")
    sp = bca[bca["symbol"] == sym]
    f = split_factors(g["date"].to_numpy(), sp)
    return pd.Series(g["c"].to_numpy() / f, index=g["date"].to_numpy())


def main(only=None):
    root = storage.root()
    ref = root / "reference"
    daily = pd.read_parquet(ref / "daily_ohlc_v2.parquet")
    daily = daily[(~daily["filler"]) & (daily["date"] <= DEV)].copy()
    daily["entity"] = daily["entity"].astype(str)
    ca_raw = pd.read_parquet(ref / "corporate_actions.parquet")
    act = outcomes.parse_actions(ca_raw)
    syms = g2a_coverage.entity_symbols(daily, ca_raw)
    bd = pd.read_parquet(ref / "benchmarks_daily.parquet")
    bca = outcomes.parse_actions(pd.read_parquet(ref / "benchmarks_corporate_actions.parquet"))["splits"]
    spy = bench_series(bd, bca, "SPY")
    etf = {s: bench_series(bd, bca, s) for s in bd["symbol"].unique()}
    intr = pd.concat([pd.read_parquet(f) for f in sorted((root / "features" / "intraday_daily").glob("*.parquet"))],
                     ignore_index=True)
    intr["entity"] = intr["entity"].astype(str)
    intr["er"] = (intr["c_last"] - intr["o_first"]).abs() / intr["path"].where(intr["path"] > 0)
    vap = pd.concat([pd.read_parquet(f, columns=["day", "bin", "v", "entity"])
                     for f in sorted((root / "features" / "vap_daily").glob("*.parquet"))], ignore_index=True)
    vap["entity"] = vap["entity"].astype(str)
    flow = pd.read_parquet(root / "features" / "flow_dev.parquet")
    flow["entity"] = flow["entity"].astype(str)
    tick_of = (pd.read_parquet(ref / "universe_intervals.parquet").assign(entity=lambda x: x["entity"].astype(str))
               .groupby("entity")["ticker"].agg(lambda s: list(s)[-1]).to_dict())
    applied = D.applied_splits_by_entity()
    events = D.events_by_entity()
    outages = g2a_outages.outage_days()
    gj = pd.read_parquet(root / "results" / "g2a_genuine_jumps.parquet")
    gjumps = {e: sorted(set(g["date"])) for e, g in gj.groupby("entity")} if len(gj) else {}
    cal = calendar.trading_days("2016-01-04", "2026-11-13")
    cpos = {d: i for i, d in enumerate(cal)}
    vap_g = dict(tuple(vap.groupby("entity")))
    intr_g = dict(tuple(intr.groupby("entity")))
    out, t0 = [], time.time()
    ents = sorted(daily["entity"].unique()) if not only else only
    for k, e in enumerate(ents):
        gi.wait_mem()
        g = daily[daily["entity"] == e].sort_values("date").reset_index(drop=True)
        if len(g) < 260:
            continue
        dates = g["date"].to_numpy()
        fct = split_factors(dates, applied.get(e, pd.DataFrame(columns=["symbol", "ex_date", "factor"])))  # solo splits coherentes (enmienda 7)
        s = pd.DataFrame({"date": dates, "o": g["o"] / fct, "h": g["h"] / fct, "l": g["l"] / fct, "c": g["c"] / fct,
                          "v": g["v"] * fct})
        it = intr_g.get(e)
        s["er"] = s["date"].map(dict(zip(it["day"], it["er"]))) if it is not None else np.nan
        s["has_intraday"] = s["date"].isin(set(it["day"])) if it is not None else False
        vp = vap_g.get(e)
        if vp is None:
            continue
        vp = vp[~vp["day"].isin(outages)]                                          # enmienda 8
        shift = dict(zip(dates, np.round(np.log(fct) / F.LOG_STEP).astype(int)))
        vp = vp[vp["day"].isin(shift)]
        b_adj = vp["bin"].to_numpy() - vp["day"].map(shift).to_numpy()
        b0 = int(b_adj.min())
        row = pd.Series(np.arange(len(dates)), index=dates)
        mat = np.zeros((len(dates), int(b_adj.max()) - b0 + 1))
        np.add.at(mat, (row[vp["day"]].to_numpy(), b_adj - b0), vp["v"].to_numpy(float))
        a = F.awd(s, intraday_skip=s["date"].isin(outages).to_numpy())
        parts = [s[["date", "has_intraday"]], a]
        for L in LS:
            fc = F.family_c(s, mat, b0, a, L)
            if L == LS[0]:
                shared = fc[[c for c in fc.columns if c == "c2" or c.startswith("c3_")]]
                parts.append(fc)
            else:   # C2 y C3 no dependen de L: se guardan una vez (y se comprueba que coinciden)
                dup = [c for c in fc.columns if c == "c2" or c.startswith("c3_")]
                assert fc[dup].equals(shared[dup]), "C2/C3 distintos entre L"
                parts.append(fc.drop(columns=dup))
        mf = F.momentum_filters(s, spy)
        parts.append(mf)
        f = pd.concat(parts, axis=1)
        f["entity"] = e
        tk = tick_of.get(e, "")
        sec = [sectors.sector_at(tk, d) for d in dates]
        f["sector"] = [x[0] for x in sec]
        f["sector_src"] = [x[1] for x in sec]
        etf_sym = [sectors.sector_etf(x[0]) if x[0] else None for x in sec]
        c = s["c"].to_numpy(float)
        rs_sec = np.full(len(c), np.nan)
        for i in range(63, len(c)):
            es = etf.get(etf_sym[i]) if etf_sym[i] else None
            if es is not None and dates[i] in es.index and dates[i - 63] in es.index:
                rs_sec[i] = math.log(c[i] / c[i - 63]) - math.log(es[dates[i]] / es[dates[i - 63]])
        f["rs63_sector_raw"] = rs_sec
        f["rs63_sector"] = np.where(np.isnan(rs_sec), f["rs63_spy"], rs_sec)        # enmienda 2
        f["rs63_sector_is_spy"] = np.isnan(rs_sec) & f["rs63_spy"].notna()
        dollar = g["v"].to_numpy(float) * g["vw"].fillna(g["c"]).to_numpy(float)
        f["excluded_event"] = D.excluded_mask(dates, events.get(e, []), cpos)       # enmienda 7
        f["near_genuine_jump"] = D.excluded_mask(dates, gjumps.get(e, []), cpos)  # sensibilidad
        f["liq60"] = pd.Series(dollar).shift(1).rolling(60, min_periods=40).median().to_numpy()
        out.append(f)
        if k % 50 == 0:
            print(k, len(ents), e, round(time.time() - t0), "s", flush=True)
    res = pd.concat(out, ignore_index=True).merge(flow, on=["entity", "date"], how="left")
    if not only:
        storage.write_parquet_atomic(res, root / "features" / "dev_features.parquet")
    return res


if __name__ == "__main__":
    main()
