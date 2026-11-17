"""G1 — universo del nivel A a fecha y cobertura real en Alpaca (barras DIARIAS, ~1 página por intervalo).

Para cada intervalo de pertenencia (ticker, inicio, fin):
  - barras diarias con asof = última fecha observada del ticker (baja -> sesión previa; vigente -> sin asof),
  - épocas (identity.epochs): se usa solo la época que contiene la fecha observada,
  - cobertura = sesiones del intervalo con volumen > 0 en esa época / sesiones del intervalo.
Corrige la medición de G0, que contaba también las barras de relleno con volumen 0.

Salidas (MICRO_DATA_DIR/reference): universe_intervals.parquet, daily_bars_levelA.parquet;
resumen agregado en MICRO_DATA_DIR/results/g1_universe_coverage.json.
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, identity, runtime, storage, universe  # noqa: E402
from micro.providers.base import clean_asof  # noqa: E402

FIRST, LAST = "2016-01-04", "2026-11-13"
LOOKBACK_CAL_DAYS = 400   # ~1 año de historia previa (consolidaciones largas)
FOLLOW_CAL_DAYS = 90      # ~60 sesiones tras la salida (horizontes de 20-40 + margen)
SNAPSHOT_2026 = "2026-01-14"   # última instantánea de Wikipedia con tabla de cambios


def main():
    P = runtime.alpaca()
    if not calendar.cache_path().exists():
        calendar.sync(P)
    days = calendar.trading_days(FIRST, LAST)
    sp = universe.sp500_membership(days)
    # asof = ÚLTIMA fecha en que el ticker se observó para esa empresa (verificado en G1: con un asof antiguo
    # Alpaca corta la serie en eventos corporativos -CB ene-2016, WMB jun-2016, LMT ago-2016, JCI sep-2016-).
    #   baja con fecha -> fecha de baja; sigue en el índice -> sin asof (hoy); baja de 2026 sin fecha -> instantánea.
    pos0 = {d: i for i, d in enumerate(days)}
    prev_day = lambda d: days[max(0, pos0[d] - 1)]     # la baja suele ser efectiva el día siguiente a la última sesión
    sp["asof"] = [None if (e == LAST and not u) else (SNAPSHOT_2026 if u else prev_day(e))
                  for e, u in zip(sp["end"], sp["end_uncertain"])]
    proj = pd.DataFrame([{"ticker": t, "symbol": t, "cik": "", "name": "", "source": "project", "start": FIRST, "end": LAST,
                          "asof": None, "end_uncertain": False} for t in universe.project_us_tickers()])
    iv = pd.concat([sp, proj], ignore_index=True)
    iv["entity"] = [c if c else f"T:{s}" for c, s in zip(iv["cik"], iv["symbol"])]
    print("intervalos", len(iv), "sp500", len(sp), "proyecto", len(proj), flush=True)

    ca = P.corporate_actions(sorted(iv["symbol"].unique()), "2016-01-01", LAST,
                             types=["forward_split", "reverse_split"])
    pos = {d: i for i, d in enumerate(days)}
    daily_rows, out = [], []
    t0 = time.time()
    for k, r in enumerate(iv.itertuples()):
        a = (pd.Timestamp(r.start) - pd.Timedelta(days=LOOKBACK_CAL_DAYS)).strftime("%Y-%m-%d")
        b = (pd.Timestamp(r.end) + pd.Timedelta(days=FOLLOW_CAL_DAYS)).strftime("%Y-%m-%d")
        a, b = max(a, "2016-01-01"), min(b, LAST)
        try:
            d = identity.daily_bars(P, r.symbol, a, b + "T21:00:00Z", asof=r.asof)
        except Exception as e:  # noqa: BLE001
            out.append({**r._asdict(), "status": f"error: {e}"[:200]})
            continue
        if d.empty:
            out.append({**r._asdict(), "status": "no_data", "coverage": 0.0})
            continue
        ep = identity.epochs(d, identity.split_events(ca, r.symbol))
        ref_date = (clean_asof(r.asof) or r.end) if r.source == "sp500" else r.end
        eo = identity.epoch_of(ep, ref_date)
        member_days = [x for x in days if r.start <= x <= r.end]
        if eo is None:
            cov, e, e0, e1 = 0.0, None, None, None
        else:
            e, e0, e1 = eo
            seg = ep[(ep["epoch"] == e) & (ep["v"] > 0)]
            cov = seg["date"].isin(member_days).sum() / len(member_days) if member_days else 0.0
            listed_days = [x for x in member_days if x >= e0]       # proyecto: desde la salida a bolsa
            cov_listed = seg["date"].isin(listed_days).sum() / len(listed_days) if listed_days else 0.0
            pre = seg[seg["date"] < r.start]
            post = seg[seg["date"] > r.end]
            seg = seg.assign(entity=r.entity, symbol=r.symbol, asof=r.asof)
            daily_rows.append(seg[["entity", "symbol", "asof", "date", "v", "n", "c", "epoch"]])
        out.append({**r._asdict(), "status": "ok", "coverage": round(float(cov), 4),
                    "coverage_since_listing": round(float(cov_listed), 4) if eo else 0.0, "epoch": e, "epoch_start": e0,
                    "epoch_end": e1, "n_epochs": int(ep.loc[ep["epoch"] >= 0, "epoch"].nunique()),
                    "filler_bars": int((ep["epoch"] == -1).sum()), "suspicious_jumps": int(ep["suspicious_jump"].sum()),
                    "pre_sessions": int(len(pre)) if eo else 0, "post_sessions": int(len(post)) if eo else 0,
                    "member_sessions": len(member_days)})
        if k % 100 == 0:
            print(k, len(iv), round(time.time() - t0), "s", flush=True)
    res = pd.DataFrame(out).drop(columns=["Index"], errors="ignore")
    res["departed"] = (res["source"] == "sp500") & (res["end"] < LAST)
    ref = storage.root() / "reference"
    storage.write_parquet_atomic(res, ref / "universe_intervals.parquet")
    daily = pd.concat(daily_rows, ignore_index=True)
    storage.write_parquet_atomic(daily, ref / "daily_bars_levelA.parquet")

    def stats(x):
        return {"intervals": int(len(x)), "entities": int(x["entity"].nunique()),
                "coverage_ge_95": int((x["coverage"] >= 0.95).sum()), "coverage_50_95": int(((x["coverage"] >= 0.5) & (x["coverage"] < 0.95)).sum()),
                "coverage_lt_50": int((x["coverage"] < 0.5).sum()),
                "since_listing_ge_95": int((x.get("coverage_since_listing", x["coverage"]) >= 0.95).sum()), "no_data_or_error": int((x["status"] != "ok").sum()),
                "median_coverage": float(x["coverage"].median()) if len(x) else None,
                "with_suspicious_jumps": int((x["suspicious_jumps"] > 0).sum()), "multi_epoch": int((x["n_epochs"] > 1).sum())}

    summary = {"all": stats(res), "sp500_current": stats(res[(res.source == "sp500") & ~res.departed]),
               "sp500_departed": stats(res[res.departed]), "project": stats(res[res.source == "project"]),
               "sp500_by_start_year": {y: stats(g) for y, g in res[res.source == "sp500"].groupby(res["start"].str[:4])},
               "worst": res.sort_values("coverage").head(25)[["symbol", "name", "source", "start", "end", "coverage", "coverage_since_listing", "status", "n_epochs"]].to_dict("records"),
               "suspicious": res[res["suspicious_jumps"] > 0][["symbol", "name", "start", "end", "suspicious_jumps", "n_epochs"]].to_dict("records"),
               "daily_rows": int(len(daily)), "elapsed_s": round(time.time() - t0, 1)}
    f = storage.root() / "results" / "g1_universe_coverage.json"
    f.write_text(json.dumps(summary, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("all", "sp500_current", "sp500_departed", "project")}, indent=1))


if __name__ == "__main__":
    main()
