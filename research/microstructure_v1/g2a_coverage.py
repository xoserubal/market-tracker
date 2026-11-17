"""G2A — comprobación de que la muestra de desarrollo está completa y es representativa (G2A_PROTOCOLO §8), antes
de calcular ningún criterio de elección. No calcula resultados ni variables candidatas: solo presencia de datos,
historia, integridad de precios (splits, saltos) y clasificación de salidas.

Población: valor-días miembros del S&P 500 con fecha de decisión de desarrollo (2017-01-03 → 2021-10-29).
Salida: MICRO_DATA_DIR/results/g2a_coverage.json (agregados) y g2a_coverage_entity_days.parquet (detalle).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, manifest, outcomes, sectors, storage  # noqa: E402

DEV_FIRST, DEV_LAST = "2017-01-03", outcomes.DEV_LAST_DECISION
H = 40


def entity_symbols(daily, ca_raw):
    """Símbolos de cada entidad: los de sus barras + los anteriores según los cambios de nombre."""
    syms = daily.groupby("entity")["symbol"].agg(lambda s: set(s)).to_dict()
    nc = [json.loads(j) for t, j in zip(ca_raw["type"], ca_raw["json"]) if t == "name_changes"]
    for _ in range(3):
        for a in nc:
            for e, ss in syms.items():
                if a.get("new_symbol") in ss:
                    ss.add(a.get("old_symbol"))
    return syms


def main():
    root = storage.root()
    ref = root / "reference"
    iv = pd.read_parquet(ref / "universe_intervals.parquet")
    daily = pd.read_parquet(ref / "daily_ohlc_v2.parquet")
    daily["entity"] = daily["entity"].astype(str)
    ca_raw = pd.read_parquet(ref / "corporate_actions.parquet")
    act = outcomes.parse_actions(ca_raw)
    days = calendar.trading_days("2016-01-04", "2026-11-13")
    pos = {d: i for i, d in enumerate(days)}
    dev_days = [d for d in days if DEV_FIRST <= d <= DEV_LAST]
    out = {}

    # 1. unidades del nivel A hasta el último mes de desarrollo
    units = pd.read_parquet(root / "samples" / "levelA_units_v1.parquet")
    units = units[units["month"] <= DEV_LAST[:7]]
    with manifest.Manifest()._c() as c:
        man = pd.DataFrame([dict(r) for r in c.execute("SELECT symbol, asof, period, status FROM units WHERE kind='bars'")])
    norm = lambda x: x if isinstance(x, str) and x.strip() not in ("", "-") else ""  # noqa: E731
    st = {(r.symbol, norm(r.asof), r.period): r.status for r in man.itertuples()}
    ustat = pd.Series([st.get((u.symbol, norm(u.asof), u.month), "missing") for u in units.itertuples()])
    out["levelA_units_dev"] = {"planned": int(len(units)), **ustat.value_counts().to_dict()}

    # 2. valor-días miembro de desarrollo
    sp = iv[iv["source"] == "sp500"].copy()
    sp["entity"] = sp["entity"].astype(str)
    rows = []
    for r in sp.itertuples():
        for d in dev_days:
            if r.start <= d <= r.end:
                rows.append((r.entity, r.symbol, r.ticker, d, bool(r.departed)))
    md = pd.DataFrame(rows, columns=["entity", "symbol", "ticker", "date", "departed"]).drop_duplicates(["entity", "date"])
    intr = pd.concat([pd.read_parquet(f, columns=["entity", "day", "n_min", "v"])
                      for f in sorted((root / "features" / "intraday_daily").glob("*.parquet"))], ignore_index=True)
    intr = intr.rename(columns={"day": "date"})
    intr["entity"] = intr["entity"].astype(str)
    md = md.merge(intr, on=["entity", "date"], how="left")
    md["has_intraday"] = md["n_min"].fillna(0).gt(0) & md["v"].fillna(0).gt(0)
    dd = daily[~daily["filler"]][["entity", "date", "c", "v", "vw"]].rename(columns={"v": "dv_v"})
    md = md.merge(dd, on=["entity", "date"], how="left")
    md["has_daily"] = md["c"].notna()
    md["year"] = md["date"].str[:4]
    sec = {}
    for t, d in md[["ticker", "date"]].drop_duplicates().itertuples(index=False):
        sec[(t, d)] = sectors.sector_at(t, d)
    md["sector"] = [sec[(t, d)][0] for t, d in zip(md["ticker"], md["date"])]
    md["sector_src"] = [sec[(t, d)][1] for t, d in zip(md["ticker"], md["date"])]

    # liquidez previa: mediana de V·VWAP de las 60 sesiones previas; terciles transversales del día
    dl = daily[~daily["filler"]].sort_values(["entity", "date"]).copy()
    dl["dollar"] = dl["v"] * dl["vw"].fillna(dl["c"])
    dl["liq60"] = dl.groupby("entity")["dollar"].transform(lambda s: s.shift(1).rolling(60, min_periods=40).median())
    md = md.merge(dl[["entity", "date", "liq60"]], on=["entity", "date"], how="left")
    md["liq_tercile"] = md.groupby("date")["liq60"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=[1, 2, 3]) if s.notna().sum() >= 3 else np.nan)

    # 3. historia mínima (252 diarias, 260 de minutos: enmienda 1) y horizonte de resultado disponible
    first_daily = dl.groupby("entity")["date"].min().to_dict()
    last_daily = dl.groupby("entity")["date"].max().to_dict()
    intr_days = intr[intr["n_min"] > 0].groupby("entity")["date"].apply(lambda s: sorted(s)).to_dict()
    hist_d, hist_m, horizon = [], [], []
    for e, d in zip(md["entity"], md["date"]):
        f0 = first_daily.get(e)
        hist_d.append(f0 is not None and pos[d] - pos.get(f0, 10**9) >= 252)
        ds = intr_days.get(e, [])
        k = np.searchsorted(ds, d)
        hist_m.append(k >= 260)
        ld = last_daily.get(e)
        horizon.append("ok" if ld and pos.get(ld, -1) >= pos[d] + H else "ends_before_t+40")
    md["hist_daily_252"], md["hist_min_260"], md["horizon"] = hist_d, hist_m, horizon
    md["usable"] = md["has_intraday"] & md["has_daily"] & md["hist_daily_252"] & md["hist_min_260"]

    def cov(g):
        return {"n": int(len(g)), "intraday": round(float(g["has_intraday"].mean()), 4),
                "daily": round(float(g["has_daily"].mean()), 4), "usable": round(float(g["usable"].mean()), 4)}
    out["member_days"] = cov(md)
    out["by_year"] = {y: cov(g) for y, g in md.groupby("year")}
    out["by_sector"] = {str(s): cov(g) for s, g in md.groupby(md["sector"].fillna("desconocido"))}
    out["by_liq_tercile"] = {str(int(s)): cov(g) for s, g in md.groupby("liq_tercile")}
    out["departed"] = {"share_of_member_days": round(float(md["departed"].mean()), 4), **cov(md[md["departed"]])}
    out["sector_source"] = md["sector_src"].value_counts().to_dict()
    out["horizon_ends_before_t40"] = int((md["horizon"] != "ok").sum())

    # 4. integridad (enmienda 7): eventos de reparto, splits incoherentes y rupturas de identidad (g2a_events.py)
    from micro import distributions as D
    evs = pd.read_parquet(root / "results" / "g2a_events.parquet")
    gj = pd.read_parquet(root / "results" / "g2a_genuine_jumps.parquet")
    ex = np.zeros(len(md), bool)
    by_kind = {}
    for kind, gk in evs.groupby("kind"):
        evk = {e: sorted(set(x["date"])) for e, x in gk.groupby("entity")}
        mk = np.zeros(len(md), bool)
        for e, idx in md.groupby("entity").indices.items():
            if e in evk:
                mk[idx] = D.excluded_mask(md["date"].to_numpy()[idx], evk[e], pos)
        by_kind[kind] = int(mk.sum())
        ex |= mk
    md["excluded_event"] = ex
    md["usable_after_events"] = md["usable"] & ~md["excluded_event"]
    sts = pd.read_parquet(root / "results" / "g2a_split_status.parquet")
    out["integrity_events"] = {
        "splits": sts["status"].value_counts().to_dict(),
        "events_le_2021": evs[evs["date"] <= "2021-12-31"]["kind"].value_counts().to_dict(),
        "member_days_excluded": int(ex.sum()), "member_days_excluded_share": round(float(ex.mean()), 4),
        "member_days_excluded_by_kind": by_kind,
        "usable_after_events": round(float(md["usable_after_events"].mean()), 4),
        "genuine_jumps_member_dev": gj[gj["entity"].isin(set(md["entity"])) & (gj["date"] <= DEV_LAST)].to_dict("records"),
    }
    out["usable_after_events_by_year"] = {y: round(float(g["usable_after_events"].mean()), 4) for y, g in md.groupby("year")}
    out["usable_after_events_by_sector"] = {str(k): round(float(g["usable_after_events"].mean()), 4)
                                            for k, g in md.groupby(md["sector"].fillna("desconocido"))}
    dep = sp[sp["departed"]].groupby("entity").agg(end=("end", "max"), symbols=("symbol", lambda s: set(s))).reset_index()
    syms = entity_symbols(daily, ca_raw)
    exits_act = act["exits"]
    cls = []
    for r in dep.itertuples():
        cand = exits_act[exits_act["symbol"].isin(syms.get(r.entity, set()) | r.symbols)]
        ld = last_daily.get(r.entity)
        near = cand[(cand["date"] >= r.end) & (cand["date"] <= (pd.Timestamp(r.end) + pd.Timedelta(days=400)).strftime("%Y-%m-%d"))] if len(cand) else cand
        cls.append({"entity": r.entity, "end": r.end, "last_daily": ld,
                    "still_trading_after": bool(ld and ld > (pd.Timestamp(r.end) + pd.Timedelta(days=80)).strftime("%Y-%m-%d")),
                    "exit_type": near.sort_values("date")["type"].iloc[0] if len(near) else None})
    cls = pd.DataFrame(cls)
    out["departed_exits"] = {"entities": int(len(cls)),
                             "still_trading_after_leaving_index": int(cls["still_trading_after"].sum()),
                             "by_type_among_not_trading": cls[~cls["still_trading_after"]]["exit_type"].fillna(
                                 "sin acción identificable").value_counts().to_dict()}
    refj = json.loads((root / "results" / "g2a_reference.json").read_text(encoding="utf-8"))
    out["reference_check"] = {k: refj[k] for k in ("check_vs_g1", "b1_blocks_with_missing_daily", "status")}

    pe = pd.read_parquet(root / "samples" / "plan_exits_v2.parquet")
    exits_v2 = dict(zip(pe["symbol"], pe["effective_date"] if "effective_date" in pe.columns else pe.iloc[:, -1]))
    gates = {
        "1_levelA_complete": out["levelA_units_dev"].get("missing", 0) == 0 and out["levelA_units_dev"].get("failed", 0) == 0,
        "2_year_intraday_ge_98": all(v["intraday"] >= 0.98 for v in out["by_year"].values()),
        "2_sector_liq_ge_95": all(v["intraday"] >= 0.95 for k, v in out["by_sector"].items() if k != "desconocido")
        and all(v["intraday"] >= 0.95 for v in out["by_liq_tercile"].values()),
        "3_departed_ge_95": out["departed"]["intraday"] >= 0.95,
        "4_reference_matches_g1": refj["check_vs_g1"]["mismatch_c_or_v"] == 0 and refj["check_vs_g1"]["g1_rows_missing_now"] == 0,
        # faltan barras solo tras una salida registrada en plan_exits_v2 (MON, CTXS): se liquidan, no faltan
        "5_b1_daily_complete": all(b["symbol"] in exits_v2 and b["first_missing"] >= exits_v2[b["symbol"]]
                                   for b in refj["b1_blocks_with_missing_daily"]),
    }
    out["gates"] = gates
    storage.write_parquet_atomic(md, root / "results" / "g2a_coverage_entity_days.parquet")
    cls.to_parquet(root / "results" / "g2a_departed_exits.parquet")
    (root / "results" / "g2a_coverage.json").write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False),
                                                       encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("levelA_units_dev", "member_days", "by_year", "by_liq_tercile", "departed",
                                          "integrity_events", "gates")}, indent=1, default=str))


if __name__ == "__main__":
    main()
