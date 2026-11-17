"""G1 — planes (sin descargar): nivel A, piloto B1 (bloques contiguos), submuestra de quotes, potencia preliminar.

Lee MICRO_DATA_DIR/reference/{universe_intervals,daily_bars_levelA}.parquet y las mediciones reales de
g1_live_checks.json. Congela los planes de muestreo en MICRO_DATA_DIR/samples/ (antes de cualquier descarga).
Resumen: MICRO_DATA_DIR/results/g1_plans.json.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, sampling, storage  # noqa: E402

SEED = 20261115
FIRST, LAST = "2016-01-04", "2026-11-13"
LOOKBACK_SESSIONS = 252    # historia previa para consolidaciones largas
FOLLOW_SESSIONS = 60       # horizonte máximo 40 + margen
# Propuesta de partición (fechas de decisión): la decide G2.
PERIODS = {"dev": ("2017-01-03", "2021-10-29"), "test": ("2022-01-03", "2026-09-14")}
BYTES_PER_TRADE = 10.71    # medido en G0 (Parquet zstd)
QUOTES_PER_TRADE = {"median": 1.30, "low": 0.84, "high": 3.51}   # medido en G0 (7 acciones)


def level_a_days(iv: pd.DataFrame, daily: pd.DataFrame, days: list) -> pd.DataFrame:
    """Entidad-día del nivel A: pertenencia +252 sesiones antes y +60 después, dentro de la época de identidad.

    Una sola descarga por entidad y día (si una empresa cambió de ticker, se usa el del intervalo que llega primero).
    Devuelve entity, date, symbol, asof, month, n (trades/día de las barras diarias; 0 si no hay).
    """
    pos = {d: i for i, d in enumerate(days)}
    units = {}
    ok = iv[(iv["status"] == "ok") & iv["epoch_start"].notna()]
    for r in ok.itertuples():
        i0 = max(0, pos.get(r.start, 0) - LOOKBACK_SESSIONS)
        i1 = min(len(days) - 1, pos.get(r.end, len(days) - 1) + FOLLOW_SESSIONS)
        a, b = max(days[i0], r.epoch_start), min(days[i1], r.epoch_end)
        for d in days[pos.get(a, i0): pos.get(b, i1) + 1] if a in pos and b in pos else []:
            key = (r.entity, d)
            if key not in units:
                units[key] = (r.symbol, r.asof, d[:7])
    ua = pd.DataFrame([{"entity": e, "date": d, "symbol": s, "asof": a, "month": m} for (e, d), (s, a, m) in units.items()])
    ua = ua.merge(daily[["entity", "date", "n"]], on=["entity", "date"], how="left")
    ua["n"] = ua["n"].fillna(0)
    return ua


def main():
    ref = storage.root() / "reference"
    iv = pd.read_parquet(ref / "universe_intervals.parquet")
    daily = pd.read_parquet(ref / "daily_bars_levelA.parquet").drop_duplicates(["entity", "date"])
    live = json.loads((storage.root() / "results" / "g1_live_checks.json").read_text(encoding="utf-8"))
    days = calendar.trading_days(FIRST, LAST)
    pos = {d: i for i, d in enumerate(days)}
    ppm = live["parallelism"]["parallel_3"]["pages_per_min"]
    ppm_serial = live["parallelism"]["serial_reference"]["pages_per_min"]
    out = {"throughput_pages_per_min": {"parallel_3": ppm, "serial": ppm_serial}}

    # ── cobertura por ENTIDAD (CIK): días de pertenencia cubiertos por cualquiera de sus tickers ──
    spi = iv[iv["source"] == "sp500"]
    have = set(zip(daily.loc[daily["v"] > 0, "entity"], daily.loc[daily["v"] > 0, "date"]))
    ent_rows = []
    for ent, g in spi.groupby("entity"):
        mdays = set()
        for r in g.itertuples():
            mdays.update(days[pos[r.start]: pos[r.end] + 1])
        cov = sum((ent, d) in have for d in mdays) / len(mdays)
        ent_rows.append({"entity": ent, "name": g["name"].iloc[0], "tickers": ",".join(sorted(set(g["symbol"]))),
                         "departed": bool(g["departed"].all()), "end_uncertain": bool(g["end_uncertain"].any()),
                         "member_days": len(mdays), "coverage": cov})
    ec = pd.DataFrame(ent_rows)
    md = ec["member_days"].sum()
    out["entity_coverage"] = {
        "entities": int(len(ec)), "departed_entities": int(ec["departed"].sum()),
        "member_entity_days": int(md), "covered_share_weighted": round(float((ec["coverage"] * ec["member_days"]).sum() / md), 4),
        "departed_covered_share_weighted": round(float((ec.loc[ec.departed, "coverage"] * ec.loc[ec.departed, "member_days"]).sum()
                                                       / ec.loc[ec.departed, "member_days"].sum()), 4),
        "entities_ge_95": int((ec["coverage"] >= 0.95).sum()), "entities_lt_50": int((ec["coverage"] < 0.5).sum()),
        "departed_ge_95": int((ec.departed & (ec["coverage"] >= 0.95)).sum()),
        "worst": ec.sort_values("coverage").head(15).round(3).to_dict("records")}
    storage.write_parquet_atomic(ec, ref / "entity_coverage.parquet")

    # ── nivel A: barras 1 min por (símbolo, asof, mes) ──
    bm = live["downloads"]
    rows_day = {}
    for k, v in bm.items():
        if k.startswith("bars_month_") and v.get("rows"):
            q = v["quality"]
            rows_day[k] = v["rows"] / max(q.get("days_with_regular_bars") or 1, 1)
    cap = max(rows_day.values())            # filas/día del valor más líquido medido (incluye horario extendido)
    bytes_per_bar = np.mean([v["file_bytes"] / v["rows"] for k, v in bm.items() if k.startswith("bars_month_") and v.get("rows")])
    n_by = daily.set_index(["entity", "date"])["n"]
    ua = level_a_days(iv, daily, days)
    ua["est_bars"] = np.minimum(ua["n"], cap)
    per_unit = ua.groupby(["symbol", "asof", "month"], dropna=False)["est_bars"].sum()
    pages = per_unit.apply(lambda x: max(1, math.ceil(x / 10000)))
    out["level_A"] = {
        "entities": int(ua["entity"].nunique()), "symbol_days": int(len(ua)), "units_symbol_month": int(len(per_unit)),
        "est_bars": int(per_unit.sum()), "est_requests": int(pages.sum()),
        "est_hours_parallel": round(pages.sum() / ppm / 60, 1), "est_hours_serial": round(pages.sum() / ppm_serial / 60, 1),
        "est_GB": round(per_unit.sum() * bytes_per_bar / 1e9, 2), "bars_per_day_cap_measured": round(cap),
        "bytes_per_bar_measured": round(float(bytes_per_bar), 1),
        "lookback_sessions": LOOKBACK_SESSIONS, "follow_sessions": FOLLOW_SESSIONS,
        "proposed_periods_decision_dates": PERIODS,
        "note": "barras estimadas = min(trades del día, filas/día medidas en AAPL con horario extendido); cota alta para valores poco líquidos",
    }

    # ── piloto B1 ──
    members = iv[(iv["source"] == "sp500") & (iv["status"] == "ok")][["entity", "symbol", "asof", "start", "end"]]
    plan = sampling.b1_plan(members, daily[["entity", "date", "n"]], days, PERIODS, seed=SEED,
                            blocks_per_period=100, block_len=100, burn_in=40, horizon=40)
    bd = sampling.block_days(plan, days)
    bd = bd.merge(daily[["entity", "date", "n"]], on=["entity", "date"], how="left")
    bd["pages"] = bd["n"].fillna(0).apply(lambda x: max(1, math.ceil(x / 10000)))
    trades_rows = float(bd["n"].sum())
    meta = sampling.freeze(plan, {"seed": SEED, "design": "200 bloques x 100 sesiones (40 burn-in + 60 elegibles)",
                                  "periods": PERIODS, "universe": "S&P 500 a fecha (sin valores del proyecto: sesgo de supervivencia)",
                                  "liquidity": "terciles de mediana de trades/día en las 60 sesiones previas al bloque"},
                           "b1_plan_v1")
    eligible_obs = int(bd["eligible"].sum())
    blocks = len(plan)
    neff = {h: blocks * math.ceil(60 / h) for h in (5, 10, 20, 40)}
    out["B1"] = {
        "frozen": meta, "blocks": blocks, "distinct_entities": int(plan["entity"].nunique()),
        "departed_entities": int(plan["entity"].isin(iv.loc[iv["departed"], "entity"]).sum()),
        "by_period_tercile": plan.groupby(["period", "liq_tercile"]).size().to_dict(),
        "nominal_symbol_days": int(len(bd)), "eligible_symbol_days": eligible_obs,
        "days_without_data": int(bd["n"].isna().sum()),
        "est_trades": trades_rows, "est_requests": int(bd["pages"].sum()),
        "est_hours_parallel": round(bd["pages"].sum() / ppm / 60, 1), "est_hours_serial": round(bd["pages"].sum() / ppm_serial / 60, 1),
        "est_GB": round(trades_rows * BYTES_PER_TRADE / 1e9, 2),
        "n_eff_by_horizon_non_overlapping": neff,
        "mde_ic_1_test": {h: sampling.power_preview(n) for h, n in neff.items()},
        "mde_ic_6_tests_bonferroni": {h: sampling.power_preview(n, k_tests=6) for h, n in neff.items()},
    }
    out["B1"]["by_period_tercile"] = {f"{k[0]}_T{k[1]}": v for k, v in out["B1"]["by_period_tercile"].items()}

    # ── quotes ──
    qp = sampling.quotes_plan(plan, days, seed=SEED)
    qmeta = sampling.freeze(qp, {"seed": SEED, "design": "20 bloques de B1 (7/7/6 por tercil) x 20 sesiones elegibles contiguas",
                                 "purpose": "comparar clasificación por regla del tick vs bid/ask; sin uso predictivo"}, "quotes_plan_v1")
    qd = []
    for r in qp.itertuples():
        for d in days[pos[r.q_start]: pos[r.q_end] + 1]:
            qd.append(n_by.get((r.entity, d), np.nan))
    qd = pd.Series(qd)
    out["quotes"] = {"frozen": qmeta, "symbol_days": int(len(qd)), "est_trades": float(qd.sum())}
    for k, ratio in QUOTES_PER_TRADE.items():
        rows = qd.sum() * ratio
        pg = (qd.fillna(0) * ratio / 10000).apply(lambda x: max(1, math.ceil(x))).sum()
        out["quotes"][f"est_{k}"] = {"quotes": float(rows), "requests": int(pg), "hours_parallel": round(pg / ppm / 60, 2),
                                     "GB": round(rows * 8.3 / 1e9, 2)}

    # ── captura prospectiva (estimación diaria) ──
    cur = iv[((iv["source"] == "sp500") & ~iv["departed"]) | (iv["source"] == "project")]
    last_n = daily[daily["date"] >= "2026-10-01"].groupby("entity")["n"].median()
    k = 50
    est_trades = float(last_n.median() * k)
    out["shadow_daily_estimate"] = {"eligible": int(cur["symbol"].nunique()), "k_trades": k,
                                    "bars_requests": int(cur["symbol"].nunique()),
                                    "trades_requests": int(k * max(1, math.ceil(last_n.median() / 10000)) * 1.5),
                                    "est_trades": est_trades, "est_MB": round(est_trades * BYTES_PER_TRADE / 1e6, 1)}
    f = storage.root() / "results" / "g1_plans.json"
    f.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    main()
