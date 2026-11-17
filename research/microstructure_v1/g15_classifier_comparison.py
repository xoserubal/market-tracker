"""G1.5 — comparación técnica de clasificadores de agresor sobre la submuestra de quotes (20 bloques × 20 sesiones).

Solo estadísticas de clasificación (qué parte del volumen se puede clasificar, concordancia entre métodos, efecto de
TRF, odd lots, punto medio, antigüedad de la quote, precisión de los timestamps). NO se calcula ninguna variable de
resultado (rentabilidades): los bloques del periodo de prueba se usan solo para esta comparación técnica, y el uso
queda anotado en library/test_period_usage.jsonl.

Salida: results/g15_classifier_comparison.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import aggressor, calendar, episode, storage  # noqa: E402
from micro.library import lib_dir  # noqa: E402


def ts_precision(t: pd.Series) -> str:
    ns = t.astype("int64") % 1_000_000_000
    if (ns % 1_000_000 == 0).mean() > 0.99:
        return "ms"
    if (ns % 1000 == 0).mean() > 0.99:
        return "us"
    return "ns"


def day_stats(sym, day, block):
    tr, tcov = episode.load_trades(sym, day)
    q, qcov = episode.load_quotes(sym, day)
    if tr.empty or q.empty:
        return None
    tr = tr[tr["session"] == "regular"]
    c = aggressor.classify(tr, q, qcov)
    s = aggressor.summary(c)
    live = c[~c["canceled"] & ~c["auction"] & ~c["nonstandard"]]
    v = float(live["size"].sum()) or 1
    ok = live["quote_state"] == "ok"
    age = live.loc[ok, "quote_age_ms"]
    # sensibilidad: quote simultánea y retardo de 1 s
    alt = {}
    for name, opts in (("simultaneous", {"strict_before": False}), ("lag1s", {"quote_lag_ms": 1000})):
        a = aggressor.classify(tr, q, qcov, **opts)
        both = (a["side_lr"] != 0) & (c["side_lr"] != 0)
        vb = float(c.loc[both, "size"].sum())
        alt[name] = round(float(c.loc[both & (a["side_lr"] == c["side_lr"]), "size"].sum() / vb), 4) if vb else None
    return {"symbol": sym, "day": day, "block": block["block_id"], "period": block["period"],
            "liq_tercile": int(block["liq_tercile"]), "trades": int(len(tr)), "quotes": int(len(q)),
            "ts_precision_trades": ts_precision(tr["t"]), "ts_precision_quotes": ts_precision(q["t"]),
            "lr_undetermined": s["methods"]["lr"]["undetermined_share"],
            "bidask_undetermined": s["methods"]["bidask"]["undetermined_share"],
            "tick_undetermined": s["methods"]["tick"]["undetermined_share"],
            "agree_tick_lr": s["agreement"]["tick~lr"]["agreement_when_both"],
            "agree_bidask_lr": s["agreement"]["bidask~lr"]["agreement_when_both"],
            "agree_tick_bidask": s["agreement"]["tick~bidask"]["agreement_when_both"],
            "trf_share": s["trf_volume_share"], "odd_share": s["odd_lot_volume_share"],
            "at_mid_share": s["volume_by_spread_zone"].get("at_mid", 0.0),
            "inside_share": s["volume_by_spread_zone"].get("inside_upper", 0.0) + s["volume_by_spread_zone"].get("inside_lower", 0.0),
            "outside_share": s["volume_by_spread_zone"].get("above_ask", 0.0) + s["volume_by_spread_zone"].get("below_bid", 0.0),
            "quote_ok_share": round(float(live.loc[ok, "size"].sum() / v), 4),
            "quote_age_ms_median": float(age.median()) if len(age) else None,
            "trf_lr_undetermined": s["by_venue"].get("trf", {}).get("lr_undetermined_share"),
            "trf_tick_lr_agree": s["by_venue"].get("trf", {}).get("tick_lr_agreement"),
            "exch_tick_lr_agree": s["by_venue"].get("exchange", {}).get("tick_lr_agreement"),
            "lr_stability_simultaneous": alt["simultaneous"], "lr_stability_lag1s": alt["lag1s"],
            "auction_share": s["volume_by_exclusion"].get("auction", 0.0)}


def main():
    qp = pd.read_parquet(storage.root() / "samples" / "quotes_plan_v1.parquet")
    days = calendar.trading_days("2015-01-01", "2026-11-13")
    pos = {d: i for i, d in enumerate(days)}
    rows, missing = [], []
    usage = lib_dir() / "test_period_usage.jsonl"
    for b in qp.to_dict("records"):
        for d in days[pos[b["q_start"]]: pos[b["q_end"]] + 1]:
            r = day_stats(b["symbol"], d, b)
            if r is None:
                missing.append((b["symbol"], d))
                continue
            rows.append(r)
            if b["period"] == "test":
                with open(usage, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "symbol": b["symbol"],
                                        "day": d, "purpose": "comparación técnica de clasificadores; sin variables de resultado",
                                        "script": "g15_classifier_comparison.py"}) + "\n")
    df = pd.DataFrame(rows)
    num = [c for c in df.columns if df[c].dtype.kind in "fi" and c not in ("liq_tercile",)]
    w = df["trades"]
    out = {"days": len(df), "missing_days": missing[:50], "n_missing": len(missing),
           "median_all": df[num].median().round(4).to_dict(),
           "by_tercile": df.groupby("liq_tercile")[num].median().round(4).to_dict("index"),
           "by_period": df.groupby("period")[num].median().round(4).to_dict("index"),
           "ts_precision": df.groupby(["period", "ts_precision_trades", "ts_precision_quotes"]).size().to_dict(),
           "by_year": df.assign(year=df["day"].str[:4]).groupby("year")[["agree_tick_lr", "lr_undetermined", "trf_share",
                                                                        "odd_share", "at_mid_share"]].median().round(4).to_dict("index")}
    out["ts_precision"] = {"|".join(k): v for k, v in out["ts_precision"].items()}
    storage.root().joinpath("results", "g15_classifier_comparison.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    df.to_parquet(storage.root() / "results" / "g15_classifier_comparison_days.parquet")
    print(json.dumps({k: out[k] for k in ("days", "n_missing", "median_all", "by_tercile", "by_year", "ts_precision")},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
