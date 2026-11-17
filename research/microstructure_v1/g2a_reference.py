"""G2A — datos de referencia para la integridad de resultados (2026-11-16).

G1 guardó solo cierre, volumen y número de trades de las barras diarias, con una ventana de 90 días naturales tras la
salida del índice, y no guardó las acciones corporativas. Para medir resultados hacen falta:
- apertura, máximo, mínimo y VWAP diarios (entrada a la apertura de t+1, ATR, rango de la lateralidad);
- barras diarias hasta el final del horizonte de cada bloque B1, aunque el valor ya hubiera salido del índice
  (CZR test-097 salió el 19-sep-2025 y su bloque llega hasta el 31-oct-2025 + 40 sesiones);
- splits, dividendos y fusiones para ajustar precios y liquidar las salidas.

Misma regla de identidad que G1 (asof y época de g1_universe_coverage.py). Se comprueba que cierre y volumen coinciden
con daily_bars_levelA.parquet en todas las fechas comunes; si no, se detiene.

Salidas (MICRO_DATA_DIR/reference): daily_ohlc_v2.parquet, corporate_actions.parquet; resumen en
results/g2a_reference.json. Solo descarga datos ya autorizados (barras diarias 2016-2026) y metadatos; no calcula
resultados ni variables.
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, identity, runtime, storage  # noqa: E402
import g1_universe_coverage as g1  # noqa: E402

B1_EXTRA_CAL_DAYS = 70          # 40 sesiones de horizonte tras el final del bloque + margen


def b1_ends() -> dict:
    """Último día que necesita cada (entidad, símbolo) por los bloques B1 v2 (final del bloque + horizonte)."""
    p = pd.read_parquet(storage.root() / "samples" / "b1_plan_v2.parquet")
    out = {}
    for r in p.itertuples():
        e = (pd.Timestamp(r.end) + pd.Timedelta(days=B1_EXTRA_CAL_DAYS)).strftime("%Y-%m-%d")
        k = (str(r.entity), r.symbol)
        out[k] = max(out.get(k, ""), e)
    return out


def main():
    P = runtime.alpaca()
    ref = storage.root() / "reference"
    iv = pd.read_parquet(ref / "universe_intervals.parquet")
    iv = iv[iv["status"] == "ok"].reset_index(drop=True)
    old = pd.read_parquet(ref / "daily_bars_levelA.parquet").drop_duplicates(["entity", "date"])
    need = b1_ends()
    plan = pd.read_parquet(storage.root() / "samples" / "b1_plan_v2.parquet")
    t0 = time.time()
    rows, log = [], []
    for k, r in enumerate(iv.itertuples()):
        a = max((pd.Timestamp(r.start) - pd.Timedelta(days=g1.LOOKBACK_CAL_DAYS)).strftime("%Y-%m-%d"), "2016-01-01")
        b = (pd.Timestamp(r.end) + pd.Timedelta(days=g1.FOLLOW_CAL_DAYS)).strftime("%Y-%m-%d")
        b = min(max(b, need.get((str(r.entity), r.symbol), "")), g1.LAST)
        d = identity.daily_bars(P, r.symbol, a, b + "T21:00:00Z", asof=r.asof)
        if d.empty:
            log.append({"symbol": r.symbol, "entity": r.entity, "status": "no_data"})
            continue
        ep = identity.epochs(d, None)
        ref_date = (g1.clean_asof(r.asof) or r.end) if r.source == "sp500" else r.end
        eo = identity.epoch_of(ep, ref_date)
        if eo is None:
            log.append({"symbol": r.symbol, "entity": r.entity, "status": "no_epoch"})
            continue
        e, e0, e1 = eo
        seg = ep[(ep["epoch"] == e)].copy()
        seg["filler"] = seg["v"].fillna(0).eq(0)
        seg = seg.assign(entity=r.entity, symbol=r.symbol, asof=r.asof, interval_start=r.start, interval_end=r.end)
        keep = ["entity", "symbol", "asof", "interval_start", "interval_end", "date", "o", "h", "l", "c", "v", "n",
                "vw", "filler", "epoch"]
        rows.append(seg[[c for c in keep if c in seg.columns]])
        log.append({"symbol": r.symbol, "entity": r.entity, "status": "ok", "epoch_start": e0, "epoch_end": e1,
                    "g1_epoch_start": r.epoch_start, "same_epoch_start": e0 == r.epoch_start,
                    "fetched_to": b, "extended_for_b1": b > min((pd.Timestamp(r.end) + pd.Timedelta(
                        days=g1.FOLLOW_CAL_DAYS)).strftime("%Y-%m-%d"), g1.LAST)})
        if k % 100 == 0:
            print(k, len(iv), round(time.time() - t0), "s", flush=True)
    daily = pd.concat(rows, ignore_index=True).drop_duplicates(["entity", "date"], keep="first")

    # coincidencia con G1 en cierre y volumen
    m = daily.merge(old[["entity", "date", "c", "v"]], on=["entity", "date"], suffixes=("", "_g1"))
    mism = m[(m["c"] != m["c_g1"]) | (m["v"] != m["v_g1"])]
    lost = old.merge(daily[["entity", "date"]], on=["entity", "date"], how="left", indicator=True)
    lost = lost[lost["_merge"] == "left_only"]

    # cobertura de los bloques B1 (todas las sesiones del bloque + 40 de horizonte)
    days = calendar.trading_days("2016-01-04", g1.LAST)
    pos = {x: i for i, x in enumerate(days)}
    have = set(zip(daily["entity"].astype(str), daily["date"]))
    b1_cov = []
    for r in plan.itertuples():
        i1 = pos[r.end]
        span = days[pos[r.start]: min(i1 + 41, len(days))]
        miss = [x for x in span if (str(r.entity), x) not in have]
        b1_cov.append({"block_id": r.block_id, "symbol": r.symbol, "missing": len(miss),
                       "first_missing": miss[0] if miss else None, "last_missing": miss[-1] if miss else None})
    b1_cov = pd.DataFrame(b1_cov)

    # acciones corporativas, todos los tipos
    syms = sorted(set(iv["symbol"]) | set(plan["symbol"]) | set(plan["symbol_v1"]))
    ca = P.corporate_actions(syms, "2016-01-01", g1.LAST, types=None)
    ca_rows = [{"type": typ, "symbol": a.get("symbol") or a.get("acquiree_symbol") or a.get("old_symbol"),
                "ex_date": a.get("ex_date") or a.get("effective_date") or a.get("process_date"),
                "json": json.dumps(a, sort_keys=True)} for typ, v in ca.items() for a in (v or [])]
    ca_df = pd.DataFrame(ca_rows).drop_duplicates()

    storage.write_parquet_atomic(daily, ref / "daily_ohlc_v2.parquet")
    storage.write_parquet_atomic(ca_df, ref / "corporate_actions.parquet")
    out = {"intervals": int(len(iv)), "daily_rows": int(len(daily)), "entities": int(daily["entity"].nunique()),
           "status": pd.DataFrame(log)["status"].value_counts().to_dict(),
           "epoch_start_changed": [x for x in log if x.get("status") == "ok" and not x["same_epoch_start"]],
           "extended_for_b1": sum(1 for x in log if x.get("extended_for_b1")),
           "check_vs_g1": {"common_rows": int(len(m)), "mismatch_c_or_v": int(len(mism)),
                           "g1_rows_missing_now": int(len(lost)),
                           "mismatch_examples": mism.head(10).to_dict("records")},
           "b1_blocks_with_missing_daily": b1_cov[b1_cov["missing"] > 0].to_dict("records"),
           "corporate_actions_by_type": ca_df["type"].value_counts().to_dict(),
           "elapsed_s": round(time.time() - t0, 1)}
    (storage.root() / "results" / "g2a_reference.json").write_text(
        json.dumps(out, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("epoch_start_changed",)}, default=str, indent=1)[:3000])
    if len(mism) or len(lost):
        sys.exit("ERROR: no coincide con G1 (ver results/g2a_reference.json)")


if __name__ == "__main__":
    main()
