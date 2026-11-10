"""Selección (2016-2020) y confirmación (2021-2026) del preregistro. Ver README.md.
Requiere _work/features.parquet, _work/earlyflow_out.csv, _work/sector_out.json.
Salida: results.json + tablas por consola."""
import importlib.util
import json
import os
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
spec = importlib.util.spec_from_file_location(
    "bt", os.path.join(ROOT, "research", "macd_combo_sp500_ndx_v1", "backtest.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

HORIZONS = [5, 10, 15, 20]
COST = 0.2
COOLDOWN = 10
DEV = (pd.Timestamp("2016-01-01"), pd.Timestamp("2020-12-31"))
TEST = (pd.Timestamp("2021-01-01"), pd.Timestamp("2026-11-09"))
EF_MIN = 4
FILTERS = ["A", "B", "C", "D", "E", "F", "ABC"]


def main():
    px = pd.read_parquet("prices_cache.parquet")
    feats = pd.read_parquet("_work/features.parquet")
    ef = pd.read_csv("_work/earlyflow_out.csv", parse_dates=["date"])
    sec = json.load(open("_work/sector_out.json"))

    spy = px[px.ticker == "SPY"].set_index("date").sort_index()
    cal = spy.index
    T = len(cal)
    uni = sorted(feats.ticker.unique())
    C = px[px.ticker.isin(uni)].pivot_table(index="date", columns="ticker", values="adj_close").reindex(cal)[uni]
    Cv = C.values

    feats = feats.merge(ef, on=["ticker", "date"], how="left")
    feats["B"] = feats.ef >= EF_MIN
    feats["C"] = [sec.get(e, {}).get(str(d.date())) in ("Leader", "Improving")
                  for e, d in zip(feats.sector_etf, feats.date)]
    feats["ABC"] = feats.A & feats.B & feats.C
    feats["M"] = feats.hc & feats.lz

    def mat(col):
        return (feats.pivot_table(index="date", columns="ticker", values=col, aggfunc="first")
                .reindex(index=cal, columns=uni).astype("boolean").fillna(False).astype(bool).values)

    masks = {k: mat(k) for k in ["M"] + FILTERS}

    EX = {}
    for H in HORIZONS:
        R = np.full_like(Cv, np.nan)
        R[:-H] = (Cv[H:] / Cv[:-H] - 1) * 100
        EX[H] = R - np.nanmean(R, axis=1, keepdims=True) - COST

    def events(mask):
        out = []
        for j in range(mask.shape[1]):
            last = None
            for t in np.flatnonzero(mask[:, j]):
                if last is None or (cal[t] - cal[last]).days >= COOLDOWN:
                    out.append((t, j))
                last = t
        return out

    ev_m = events(masks["M"])
    hyp = {}
    for k in FILTERS:
        hyp[k] = events(masks[k])
        hyp["MACD+" + k] = [(t, j) for t, j in ev_m if masks[k][t, j]]
    hyp["MACD (ref.)"] = ev_m

    def measure(evs, H, lo, hi):
        rows = [(cal[t], EX[H][t + 1, j]) for t, j in evs
                if lo <= cal[t] <= hi and t + 1 < T and not np.isnan(EX[H][t + 1, j])]
        if not rows:
            return {"n": 0}
        dates = pd.DatetimeIndex([r[0] for r in rows])
        return bt.summarize(np.array([r[1] for r in rows]), dates.to_period("W").astype(str))

    table = {name: {H: {"dev": measure(evs, H, *DEV), "test": measure(evs, H, *TEST)} for H in HORIZONS}
             for name, evs in hyp.items()}

    # selección en desarrollo
    cands = []
    for name in hyp:
        if name == "MACD (ref.)":
            continue
        for H in HORIZONS:
            d = table[name][H]["dev"]
            if d.get("n", 0) >= 100 and d["mean"] > 0 and (d["t_week"] or 0) >= 2:
                cands.append((d["t_week"], name, H))
    selected = sorted(cands, reverse=True)[:3]
    confirm = []
    for _, name, H in selected:
        te = table[name][H]["test"]
        ok = te.get("n", 0) > 0 and te["mean"] > 0 and (te["t_week"] or 0) >= 2.4
        parent = name.replace("MACD+", "") if name.startswith("MACD+") else None
        confirm.append({"hyp": name, "sessions": H, "dev": table[name][H]["dev"], "test": te, "confirmed": ok,
                        "test_filter_alone": table[parent][H]["test"] if parent else None})

    out = {"table": table, "selected": [s[1:] for s in selected], "confirmation": confirm,
           "params": {"cost": COST, "cooldown": COOLDOWN, "ef_min": EF_MIN, "horizons_sessions": HORIZONS}}
    json.dump(out, open("results.json", "w"), indent=1, default=str)

    def fmt(r):
        return "—" if not r.get("n") else f"{r['mean']:+.2f} t{r['t_week']:+.1f} ({r['hit']:.0f}% n{r['n']})"
    for per in ("dev", "test"):
        print(f"\n=== {per} (exceso neto de {COST}% frente al universo) ===")
        print(f"{'hipótesis':14}" + "".join(f"{H:>30}" for H in HORIZONS))
        for name in hyp:
            print(f"{name:14}" + "".join(f"{fmt(table[name][H][per]):>30}" for H in HORIZONS))
    print("\nseleccionadas en desarrollo:", out["selected"])
    for c in confirm:
        print("CONFIRMACIÓN", c["hyp"], c["sessions"], "test", c["test"], "confirmada" if c["confirmed"] else "NO",
              "| filtro solo:", c["test_filter_alone"])


if __name__ == "__main__":
    main()
