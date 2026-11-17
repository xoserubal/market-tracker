"""G1 — comprobaciones reales y acotadas (pocas unidades, ~1 000 peticiones). No es una descarga histórica.

Salida: MICRO_DATA_DIR/results/g1_live_checks.json (fuera del repo: contiene estadísticas por valor y día).
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, identity, normalize, quality, runtime, storage  # noqa: E402
from micro.download import config_for, download_unit  # noqa: E402
from micro.manifest import Manifest  # noqa: E402

OUT = {}
P = runtime.alpaca()
M = Manifest()


def section(name):
    print(f"\n== {name} ==", flush=True)


def cal_checks():
    section("calendario")
    df = calendar.sync(P)
    days = set(df["date"])
    checks = {
        "rows": len(df), "first": df["date"].min(), "last": df["date"].max(),
        "2026-07-03_observed_holiday_closed": "2026-07-03" not in days,
        "2026-06-19_juneteenth_closed": "2026-06-19" not in days,
        "2025-11-28_early_close": calendar.is_early_close("2025-11-28"),
        "2026-03-09_open_utc": str(calendar.session_bounds("2026-03-09")[0]),
        "2026-03-06_open_utc": str(calendar.session_bounds("2026-03-06")[0]),
        "early_closes_2016_2026": int(sum(calendar.is_early_close(d) for d in df["date"] if "2016" <= d <= "2026-11-13")),
    }
    OUT["calendar"] = checks
    print(checks)


def corp_actions():
    section("acciones corporativas")
    ca = P.corporate_actions(["NVDA", "AAPL", "TSLA", "GE"], "2016-01-01", "2026-11-13",
                             types=["forward_split", "reverse_split", "name_change", "stock_merger", "cash_merger",
                                    "spin_off"])
    summary = {k: len(v) for k, v in ca.items()}
    nv = identity.split_events(ca, "NVDA")
    OUT["corporate_actions"] = {"counts_by_type": summary, "NVDA_splits": nv.to_dict("records"),
                                "AAPL_splits": identity.split_events(ca, "AAPL").to_dict("records"),
                                "GE_reverse": identity.split_events(ca, "GE").to_dict("records"),
                                "sample_fields": {k: sorted(v[0].keys()) for k, v in ca.items() if v}}
    print(OUT["corporate_actions"])
    return ca


def identity_checks(ca):
    section("identidad")
    res = {}
    for label, sym, start, end, asof in [
        ("ADT_asof_2016", "ADT", "2015-12-01", "2019-06-01T00:00:00Z", "2016-03-01"),
        ("ADT_asof_2019", "ADT", "2015-12-01", "2019-06-01T00:00:00Z", "2019-06-01"),
        ("ADT_asof_none", "ADT", "2015-12-01", "2019-06-01T00:00:00Z", None),
        ("FB_asof_2016_through_2023", "FB", "2021-06-01", "2023-06-01T00:00:00Z", "2016-06-01"),
        ("TWTR_asof_2021", "TWTR", "2021-01-01", "2023-01-01T00:00:00Z", "2021-06-01"),
        ("NVDA_split_2024", "NVDA", "2024-05-01", "2024-07-01T00:00:00Z", None),
    ]:
        d = identity.daily_bars(P, sym, start, end, asof=asof)
        ep = identity.epochs(d, identity.split_events(ca, sym))
        res[label] = {"bars": int(len(d)), "zero_volume_bars": int((d["v"] == 0).sum()) if len(d) else 0,
                      "epochs": identity.epoch_summary(ep)}
        print(label, res[label])
    OUT["identity"] = res


def downloads():
    section("descargas y conciliación")
    cases = [("AAPL", "2026-11-13", None), ("HIMS", "2026-11-13", None), ("VFF", "2026-11-13", None),
             ("URI", "2025-11-28", None),          # cierre anticipado
             ("OSCR", "2026-03-09", None),         # primer día con horario de verano
             ("ADT", "2016-03-01", "2016-03-01")]  # empresa absorbida en 2016 (identidad por asof)
    res = {}
    for sym, day, asof in cases:
        rt = download_unit(P, "trades", sym, day, asof=asof, manifest=M)
        rb = download_unit(P, "bars", sym, day, asof=asof, cfg=config_for("bars", bars_window="day"), manifest=M)
        tr = normalize.trades(pd.read_parquet(rt["path"]), day)
        br = normalize.bars(pd.read_parquet(rb["path"]))
        o, c = calendar.session_bounds(day)
        br_reg = br[(br["t"] >= o) & (br["t"] < c)]
        rec = quality.reconcile_trades_bars(tr, br_reg)
        ses = quality.check_bars_session(br, day)
        res[f"{sym}_{day}"] = {"trades": {k: rt.get(k) for k in ("status", "rows", "pages", "requests", "seconds", "file_bytes", "grade")},
                               "bars_day": {k: rb.get(k) for k in ("status", "rows", "pages", "file_bytes", "grade")},
                               "trades_quality": json.loads(M.get(rt["unit_key"])["quality_json"]),
                               "reconciliation": rec, "bars_session": ses}
        print(sym, day, rt["status"], rt.get("rows"), "rec", rec["grade"], rec["volume_rel_diff"], rec["count_rel_diff"],
              "missing", rec["bars_missing_vs_expected"], "unexpected", rec["bars_unexpected"], "cov", ses["minute_coverage"])
    # idempotencia real
    again = download_unit(P, "trades", "AAPL", "2026-11-13", manifest=M)
    res["idempotent_rerun_AAPL"] = again["status"]
    # quotes
    for sym in ("VFF", "URI"):
        rq = download_unit(P, "quotes", sym, "2026-11-13", manifest=M)
        res[f"quotes_{sym}"] = {k: rq.get(k) for k in ("status", "rows", "pages", "seconds", "file_bytes", "grade")}
        res[f"quotes_{sym}"]["quality"] = json.loads(M.get(rq["unit_key"])["quality_json"])
        print("quotes", sym, res[f"quotes_{sym}"])
    # barras mensuales (unidad histórica): filas y páginas reales con horario extendido
    for sym, month, asof in (("AAPL", "2026-10", None), ("VFF", "2026-10", None), ("ADT", "2016-03", "2016-03-01")):
        r = download_unit(P, "bars", sym, month, asof=asof, manifest=M)
        res[f"bars_month_{sym}_{month}"] = {k: r.get(k) for k in ("status", "rows", "pages", "file_bytes", "grade")}
        res[f"bars_month_{sym}_{month}"]["quality"] = json.loads(M.get(r["unit_key"])["quality_json"])
        print("bars month", sym, month, res[f"bars_month_{sym}_{month}"])
    OUT["downloads"] = res


def parallelism():
    section("paralelismo")
    days = ["2026-11-10", "2026-11-11", "2026-11-12"]
    t0 = time.time()
    with ThreadPoolExecutor(3) as ex:
        rs = list(ex.map(lambda d: download_unit(P, "trades", "AAPL", d, manifest=M, force=True), days))
    wall = time.time() - t0
    pages = sum(r["pages"] for r in rs)
    serial = M.get(download_unit(P, "trades", "AAPL", "2026-11-13", manifest=M)["unit_key"])
    OUT["parallelism"] = {"parallel_3": {"pages": pages, "wall_s": round(wall, 1), "pages_per_min": round(pages / wall * 60, 1),
                                         "retries": sum(r["retries"] for r in rs)},
                          "serial_reference": {"pages": serial["pages"], "seconds": serial["seconds"],
                                               "pages_per_min": round(serial["pages"] / serial["seconds"] * 60, 1)}}
    print(OUT["parallelism"])


if __name__ == "__main__":
    t0 = time.time()
    cal_checks()
    ca = corp_actions()
    identity_checks(ca)
    downloads()
    parallelism()
    OUT["disk"] = {"free_GB": round(storage.free_bytes() / 1e9, 1),
                   "usage_by_layer_MB": {k: round(v / 1e6, 1) for k, v in storage.usage_by_layer().items()}}
    OUT["elapsed_s"] = round(time.time() - t0, 1)
    f = storage.root() / "results" / "g1_live_checks.json"
    f.write_text(json.dumps(OUT, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    print("\nOK", f, OUT["disk"], OUT["elapsed_s"])
