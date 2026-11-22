"""Control de series de precio mezcladas sobre el histórico (aprobación del usuario, 2026-11-21, §3).

Recorre las barras originales de 1 minuto (capa 1, sin modificarlas) de cada valor-día del plan de E2 (S&P 500,
2016-01-04 → 2021-10-28, sesión completa) con micro/dq_checks.mixed_series, y registra:
- los valor-días marcados, con su evidencia (niveles, salto, cambios de nivel, reparto);
- los casi marcados (salto ≥ 8 % y ≥ 3 cambios), para ver qué deja fuera la regla;
- su impacto: alertas de cat-v1 y medidas de la capa 2 de ese valor-día (sin cambiarlas).
No escribe en las capas 1-2. Salida (MICRO_DATA_DIR/results): dq_mixed_series.parquet, dq_mixed_series_summary.json.
Uso: py -3 dq_mixed_history.py [--workers 3] [--entities a,b]
"""
import argparse
import json
import sys
import time
import traceback
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import dq_checks as Q, storage  # noqa: E402
import e2_compute as EC  # noqa: E402

RES = storage.root() / "results"
TMP = RES / "dq_mixed" / "_entities"


def job(args):
    ent, g = args
    while EC.free_mb() < 1500:
        time.sleep(20)
    t0 = time.time()
    try:
        g = g.sort_values("date").assign(asof_k=lambda x: [a if isinstance(a, str) and a.strip() not in ("", "-")
                                                           else "" for a in x["asof"]])
        g = g[g["date"] >= EC.E2_FIRST]
        bars, used, miss = EC.load_entity_bars(g)
        rows = []
        sym_of = dict(zip(g["date"], g["symbol"]))
        for d, x in bars.groupby("_day", sort=True):
            r = Q.mixed_series(x.sort_values("t")["c"].to_numpy())
            near = (r["gap"] or 0) >= Q.MIXED["min_gap"] and r["switches"] >= 3
            if r["flag"] or near:
                rows.append({"entity": ent, "symbol": sym_of.get(d), "date": d, "flag": r["flag"], "n_bars": r["n"],
                             "gap": r["gap"], "switches": r["switches"], "minority_share": r["minority_share"],
                             "level_lo": r["levels"][0] if r["levels"] else None,
                             "level_hi": r["levels"][1] if r["levels"] else None})
        df = pd.DataFrame(rows)
        storage.write_parquet_atomic(df, TMP / f"{ent.replace(':', '_')}.parquet")
        return {"entity": ent, "days": int(bars["_day"].nunique()) if len(bars) else 0, "flagged": int(df["flag"].sum())
                if len(df) else 0, "near": int(len(df)), "seconds": round(time.time() - t0, 1)}
    except Exception as e:  # noqa: BLE001
        return {"entity": ent, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}


def impact(fl: pd.DataFrame) -> pd.DataFrame:
    """Alertas cat-v1 y medidas de la capa 2 de cada valor-día marcado (sin cambiar nada)."""
    al = pd.read_parquet(RES / "cat_v1" / "alerts.parquet", columns=["entity", "day", "measure"])
    al = al.rename(columns={"day": "date"})
    k = al.merge(fl[["entity", "date"]], on=["entity", "date"])
    cnt = k.groupby(["entity", "date"]).agg(cat_v1_alerts=("measure", "size"),
                                            cat_v1_measures=("measure", lambda s: ",".join(sorted(set(s)))))
    out = fl.merge(cnt.reset_index(), on=["entity", "date"], how="left")
    out["cat_v1_alerts"] = out["cat_v1_alerts"].fillna(0).astype(int)
    # medidas de precio de la capa 2 que ese día superan su propia historia (percentil ≥ 99 de M0)
    rows = []
    for ent, g in out.groupby("entity"):
        fn = f"{str(ent).replace(':', '_')}.parquet"
        n = pd.read_parquet(storage.root() / "features" / "e2_norm" / fn)
        n = n[n["date"].isin(set(g["date"]))]
        pc = [c for c in n.columns if c.endswith("__m0pct")]
        for r in n.itertuples(index=False):
            d = r._asdict()
            hi = [c[:-7] for c in pc if (d[c] or 0) >= 99]
            rows.append({"entity": ent, "date": d["date"], "layer2_measures_ge_p99": ",".join(sorted(hi)),
                         "layer2_n_ge_p99": len(hi)})
    return out.merge(pd.DataFrame(rows), on=["entity", "date"], how="left") if rows else out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--entities")
    a = ap.parse_args()
    ents, ua, member = EC.plan()
    if a.entities:
        ents = [e for e in ents if e in set(a.entities.split(","))]
    TMP.mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in TMP.glob("*.parquet")}
    groups = {e: g for e, g in ua.groupby("entity")}
    jobs = [(e, groups[e]) for e in ents if e.replace(":", "_") not in have]
    print(f"entidades {len(ents)}, pendientes {len(jobs)}", flush=True)
    t0 = time.time()
    log = RES / "dq_mixed" / "log.jsonl"
    with Pool(a.workers, initializer=EC._init) as pool, log.open("a", encoding="utf-8") as lf:
        for k, r in enumerate(pool.imap_unordered(job, jobs), 1):
            lf.write(json.dumps(r, ensure_ascii=False) + "\n")
            lf.flush()
            if k % 25 == 0 or r.get("error") or r.get("flagged"):
                print(f"{k}/{len(jobs)} {r['entity']}: {r.get('error') or (r['flagged'], r['near'])} · "
                      f"{round(time.time() - t0)} s", flush=True)
    parts = [pd.read_parquet(p) for p in TMP.glob("*.parquet") if p.stat().st_size]
    df = pd.concat([p for p in parts if len(p)], ignore_index=True) if parts else pd.DataFrame()
    lg = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    fl = df[df["flag"]].copy() if len(df) else df
    fl = impact(fl) if len(fl) else fl
    storage.write_parquet_atomic(df, RES / "dq_mixed_series_candidates.parquet")
    storage.write_parquet_atomic(fl, RES / "dq_mixed_series.parquet")
    summ = {"rule": Q.MIXED, "entities": len({r["entity"] for r in lg if "error" not in r}),
            "errors": [r for r in lg if "error" in r], "valor_days": sum(r.get("days", 0) for r in lg),
            "flagged": int(len(fl)), "near_not_flagged": int(len(df) - len(fl)) if len(df) else 0,
            "flagged_list": fl[["symbol", "date", "gap", "switches", "minority_share", "level_lo", "level_hi",
                                "cat_v1_alerts"]].to_dict("records") if len(fl) else [],
            "near_examples": df[~df["flag"]].sort_values("switches", ascending=False).head(15)[
                ["symbol", "date", "gap", "switches", "minority_share", "n_bars"]].to_dict("records") if len(df) else []}
    (RES / "dq_mixed_series_summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False, default=str),
                                                     encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("entities", "valor_days", "flagged", "near_not_flagged")}), flush=True)


if __name__ == "__main__":
    main()
