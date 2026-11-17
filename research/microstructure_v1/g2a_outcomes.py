"""G2A — resultados de DESARROLLO (G2A_PROTOCOLO §2), solo fechas de decisión <= 2021-10-29.

Para cada valor-día miembro del S&P 500 con barras, y h en {10, 20, 40}:
    R = (C_{t+h} · S + D) / O_{t+1} − 1
con S = splits coherentes (enmienda 7) con ex en (t+1, t+h] y D = dividendos en efectivo con ex en (t+1, t+h] en
acciones de t+1 (misma fórmula que outcomes.total_return, vectorizada; se comprueba contra ella).
Ex = R − R_SPY (bruto; los costes se aplican en el contraste, por tercil).

Salidas de cotización dentro del horizonte (exits_dev.csv):
- fusión de Alpaca en efectivo -> precio de la operación; en acciones o mixta -> se sigue al comprador si tiene barras,
  si no, último cierre (se marca);
- adquisición sin fusión en Alpaca -> último cierre, 0 después (enmienda 6); MON -> 128 $ (8-K).
Estados: ok, exit_*, missing (faltan barras sin salida: se excluye y se cuenta).
Salida: MICRO_DATA_DIR/features/dev_outcomes.parquet
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, distributions as D, outcomes, storage  # noqa: E402
import g2a_coverage  # noqa: E402

HS = (10, 20, 40)
DEV = outcomes.DEV_LAST_DECISION
EXITS = Path(__file__).resolve().parent / "exits_dev.csv"
MON_PRICE = 128.0


def series_arrays(g, splits, divs):
    """Arrays por barra: fecha, o, c, F (producto acumulado de factores con ex <= fecha) y P (suma acumulada de
    rate·F en la barra del ex)."""
    dates = g["date"].to_numpy()
    n = len(dates)
    fac = np.ones(n)
    for r in splits.itertuples():
        k = int(np.searchsorted(dates, r.ex_date))
        if k < n:
            fac[k] *= r.factor
    F = np.cumprod(fac)
    dv = np.zeros(n)
    for r in divs.itertuples():
        k = int(np.searchsorted(dates, r.ex_date))
        if k < n:
            dv[k] += r.rate
    P = np.cumsum(dv * F)
    return dates, g["o"].to_numpy(float), g["c"].to_numpy(float), F, P


def ret_between(arr, i1, ih):
    """R de la apertura de la barra i1 al cierre de la barra ih (índices de barra)."""
    _, o, c, F, P = arr
    S = F[ih] / F[i1]
    Dsum = (P[ih] - P[i1]) / F[i1]
    return (c[ih] * S + Dsum) / o[i1] - 1


def main():
    root = storage.root()
    ref = root / "reference"
    daily = pd.read_parquet(ref / "daily_ohlc_v2.parquet")
    daily["entity"] = daily["entity"].astype(str)
    daily = daily[~daily["filler"]].sort_values(["entity", "date"])
    ca = pd.read_parquet(ref / "corporate_actions.parquet")
    act = outcomes.parse_actions(ca)
    syms = g2a_coverage.entity_symbols(daily, ca)
    applied = D.applied_splits_by_entity()
    empty_sp = pd.DataFrame(columns=["symbol", "ex_date", "factor"])
    cal = calendar.trading_days("2016-01-04", "2026-11-13")
    cpos = {d: i for i, d in enumerate(cal)}
    md = pd.read_parquet(root / "results" / "g2a_coverage_entity_days.parquet", columns=["entity", "date"])
    md["entity"] = md["entity"].astype(str)
    md = md[md["date"] <= DEV]
    outcomes.guard(md["date"].max())

    bd = pd.read_parquet(ref / "benchmarks_daily.parquet")
    bca = outcomes.parse_actions(pd.read_parquet(ref / "benchmarks_corporate_actions.parquet"))
    spy = bd[bd["symbol"] == "SPY"].sort_values("date")
    spy_arr = series_arrays(spy, bca["splits"][bca["splits"]["symbol"] == "SPY"],
                            bca["dividends"][bca["dividends"]["symbol"] == "SPY"])
    spy_pos = {d: i for i, d in enumerate(spy_arr[0])}

    ex_list = pd.read_csv(EXITS, dtype=str)
    exit_of = {r.entity: r for r in ex_list.itertuples()}
    alp = act["exits"]
    by_symbol = {}
    for e, ss in syms.items():
        for s in ss:
            by_symbol.setdefault(s, []).append(e)

    rows = []
    for e, mdg in md.groupby("entity"):
        g = daily[daily["entity"] == e]
        if g.empty:
            continue
        arr = series_arrays(g, applied.get(e, empty_sp), act["dividends"][act["dividends"]["symbol"].isin(syms.get(e, set()))])
        dates = arr[0]
        bpos = {d: i for i, d in enumerate(dates)}
        last = dates[-1]
        xr = exit_of.get(e)
        for t in mdg["date"]:
            if t not in bpos:
                continue
            i = cpos[t]
            rec = {"entity": e, "date": t}
            for h in HS:
                d1, dh = cal[i + 1], cal[i + h]
                spy_r = ret_between(spy_arr, spy_pos[d1], spy_pos[dh])
                rec[f"spy{h}"] = spy_r
                if d1 in bpos and dh in bpos:
                    r, st = ret_between(arr, bpos[d1], bpos[dh]), "ok"
                elif last < dh and xr is not None:
                    # salida dentro del horizonte
                    entry = arr[1][bpos[d1]] if d1 in bpos else arr[2][bpos[t]]
                    lc = arr[2][-1]
                    adj_lc = lc * arr[3][-1] / (arr[3][bpos[d1]] if d1 in bpos else arr[3][bpos[t]])
                    if xr.ticker == "MON":
                        r, st = MON_PRICE / entry - 1, "exit_mon_8k"
                    elif isinstance(xr.alpaca_exit, str) and xr.alpaca_exit:
                        a = alp[alp["symbol"].isin(syms.get(e, set()) | {xr.ticker}) & (alp["type"] == xr.alpaca_exit)]
                        a = a.sort_values("date").iloc[0] if len(a) else None
                        acq_ret = None
                        if a is not None and xr.alpaca_exit != "cash_mergers":
                            for ae in by_symbol.get(a["acquirer"], []):
                                ga = daily[daily["entity"] == ae]
                                if len(ga) and last in set(ga["date"]) and dh in set(ga["date"]):
                                    aa = series_arrays(ga, applied.get(ae, empty_sp), act["dividends"][act["dividends"]["symbol"].isin(syms.get(ae, set()))])
                                    ap = {d: k for k, d in enumerate(aa[0])}
                                    acq_ret = (aa[2][ap[dh]] * aa[3][ap[dh]] / aa[3][ap[last]]) / aa[2][ap[last]] - 1
                                    break
                        rr, how = outcomes.liquidate_exit(entry, adj_lc, a, acq_ret)
                        if np.isnan(rr):
                            rr, how = adj_lc / entry - 1, "exit_stock_no_acquirer_last_close"
                        r, st = rr, "exit_alpaca_" + how
                    else:
                        r, st = adj_lc / entry - 1, "exit_last_close"
                else:
                    r, st = np.nan, "missing"
                rec[f"r{h}"], rec[f"st{h}"] = r, st
                rec[f"ex{h}"] = r - spy_r if np.isfinite(r) else np.nan
            rows.append(rec)
    out = pd.DataFrame(rows)
    storage.write_parquet_atomic(out, root / "features" / "dev_outcomes.parquet")
    summ = {f"st{h}": out[f"st{h}"].value_counts().to_dict() for h in HS}
    (root / "results" / "g2a_outcomes_summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False),
                                                               encoding="utf-8")
    print(json.dumps(summ, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
