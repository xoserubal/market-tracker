"""Efecto real de la corrección de episode.load_trades (2026-11-22) en los consumidores de G1.5 y E1.

No busca reproducir los resultados anteriores: mide, caso por caso, qué cambia entre la carga anterior
(`legacy_overlap_dedupe=True`) y la corregida, con la misma opción `dedupe_ids` que usa cada consumidor. Los artefactos
congelados (fichas/, results/g15_*.json, informes) NO se reescriben: la salida va aparte.

Casos (fijados antes de ver nada, sin mirar resultados posteriores):
- G1.5: los dos estudios de caso (NVDA 2026-11-12, GOOGL 2026-10-29; g15_case_study.py, dedupe_ids=False) y los bloques
  de DESARROLLO de la comparación de clasificadores (samples/quotes_plan_v1.parquet, g15_classifier_comparison.py,
  dedupe_ids=False). Los bloques del periodo de prueba de G2A NO se vuelven a leer (test_guard).
- E1: las fichas de fichas/ (ev_case_sheet.py usa dedupe_ids=False; el desglose de eventos y el acceso libre usan
  dedupe_ids=True, así que se miden las dos) y KSS 2017-05-10, el caso que destapó el fallo.

Por cada valor-día y carga: operaciones, volumen, volumen regular y de la subasta de cierre, VWAP regular y, si hay
quotes, el resumen de agresor de micro/aggressor (proporción compradora/vendedora/indeterminada por método,
concordancia entre métodos, TRF). Toma el cerrojo de procesos intensivos: el piloto E3 espera a que termine.

Uso (en el equipo con MICRO_DATA_DIR, fuera de la ventana nocturna del piloto):
  py -3 loader_correction_diff.py [--cases-only] [--max-dev-days N]
Salida: results/loader_correction/diff_days.parquet, diff.json; el resumen se imprime.
"""
import argparse
import gc
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import aggressor, calendar, episode, heavy_lock, sessions, storage, test_guard  # noqa: E402

HERE = Path(__file__).resolve().parent
CASES = [  # (símbolo, día, origen, dedupe_ids que usa el consumidor)
    ("NVDA", "2026-11-12", "G1.5 estudio de caso", (False,)),
    ("GOOGL", "2026-10-29", "G1.5 estudio de caso", (False,)),
    ("KSS", "2017-05-10", "caso que destapó el fallo", (False, True)),
]


def fichas_cases() -> list:
    out = []
    for f in sorted((HERE / "fichas").glob("*.md")):
        sym, day = f.stem.split("_")[:2]
        out.append((sym, day, f"E1 ficha {f.name}", (False, True)))
    return out


def metrics(tr: pd.DataFrame, q: pd.DataFrame, qcov, day: str) -> dict:
    live = tr[~tr["canceled"]]
    seg = sessions.classify_trades(live, day).astype(str)
    reg = live[(live["session"] == "regular") & (seg != "close_auction") & live["upd_vol"]]
    out = {"trades": int(len(tr)), "volume": int(live["size"].sum()), "regular_volume": int(reg["size"].sum()),
           "close_auction_volume": int(live.loc[seg == "close_auction", "size"].sum()),
           "vwap_regular": float((reg["price"] * reg["size"]).sum() / reg["size"].sum()) if len(reg) else None,
           "duplicate_ids_removed": tr.attrs.get("duplicate_ids_removed", 0)}
    if q is not None and not q.empty:
        r = tr[tr["session"] == "regular"]
        s = aggressor.summary(aggressor.classify(r, q, qcov))
        for m, v in s["methods"].items():
            out[f"{m}_buy"], out[f"{m}_sell"], out[f"{m}_undet"] = v["buy_share"], v["sell_share"], v["undetermined_share"]
            out[f"{m}_net"] = round(v["buy_share"] - v["sell_share"], 4)
        out["agree_tick_lr"] = s["agreement"]["tick~lr"]["agreement_when_both"]
        out["trf_share"] = s["trf_volume_share"]
    return out


def compare(sym: str, day: str, origin: str, dedupes) -> list:
    if test_guard.reserved(day):
        return [{"symbol": sym, "day": day, "origin": origin, "skipped": "periodo reservado de G2A"}]
    q, qcov = episode.load_quotes(sym, day)
    rows = []
    for d in dedupes:
        res = {}
        for mode, legacy in (("legacy", True), ("corrected", False)):
            tr, _ = episode.load_trades(sym, day, dedupe_ids=d, legacy_overlap_dedupe=legacy)
            if tr.empty:
                res = None
                break
            res[mode] = metrics(tr, q, qcov, day)
            del tr
            gc.collect()
        if res is None:
            rows.append({"symbol": sym, "day": day, "origin": origin, "dedupe_ids": d, "skipped": "sin trades"})
            continue
        row = {"symbol": sym, "day": day, "origin": origin, "dedupe_ids": d, "has_quotes": not q.empty}
        for k in res["legacy"]:
            a, b = res["legacy"][k], res["corrected"].get(k)
            row[f"{k}_legacy"], row[f"{k}_corrected"] = a, b
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                row[f"{k}_diff"] = round(b - a, 6)
        row["added_trades_share"] = round((res["corrected"]["trades"] - res["legacy"]["trades"]) / res["legacy"]["trades"], 6)
        row["added_volume_share"] = round((res["corrected"]["volume"] - res["legacy"]["volume"]) / max(1, res["legacy"]["volume"]), 6)
        rows.append(row)
    return rows


def dev_blocks(max_days: int = None) -> list:
    qp = pd.read_parquet(storage.root() / "samples" / "quotes_plan_v1.parquet")
    days = calendar.trading_days("2015-01-01", "2026-11-13")
    pos = {d: i for i, d in enumerate(days)}
    out = []
    for b in qp.to_dict("records"):
        if b["period"] != "dev":
            continue
        for d in days[pos[b["q_start"]]: pos[b["q_end"]] + 1]:
            if not test_guard.reserved(d):
                out.append((b["symbol"], d, f"G1.5 clasificadores, bloque {b['block_id']}", (False,)))
    return out[:max_days] if max_days else out


def summarize(df: pd.DataFrame) -> dict:
    ok = df[df.get("skipped").isna()] if "skipped" in df else df
    out = {"rows": int(len(df)), "compared": int(len(ok)), "skipped": int(len(df) - len(ok))}
    for (origin_kind, d), g in ok.assign(kind=ok["origin"].str.split(",").str[0].str.split(" ").str[:2].str.join(" "))\
            .groupby(["kind", "dedupe_ids"]):
        cols = [c for c in g.columns if c.endswith("_diff") or c.startswith("added_")]
        out[f"{origin_kind} | dedupe_ids={d}"] = {
            "n": int(len(g)), "with_any_change": int((g["added_trades_share"] != 0).sum()),
            "max_added_trades_share": float(g["added_trades_share"].max()),
            "median_abs": {c: float(g[c].abs().median()) for c in cols if g[c].notna().any()},
            "max_abs": {c: float(g[c].abs().max()) for c in cols if g[c].notna().any()}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases-only", action="store_true")
    ap.add_argument("--max-dev-days", type=int)
    a = ap.parse_args()
    cases = CASES + fichas_cases() + ([] if a.cases_only else dev_blocks(a.max_dev_days))
    out_dir = storage.root() / "results" / "loader_correction"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, t0 = [], time.time()
    with heavy_lock.HeavyJob("loader_correction_diff"):
        for i, (sym, day, origin, dd) in enumerate(cases, 1):
            try:
                rows += compare(sym, day, origin, dd)
            except Exception as e:  # noqa: BLE001
                rows.append({"symbol": sym, "day": day, "origin": origin, "skipped": f"{type(e).__name__}: {e}"})
            if i % 25 == 0:
                print(f"{i}/{len(cases)} ({round(time.time() - t0)} s)", flush=True)
    df = pd.DataFrame(rows)
    df.to_parquet(out_dir / "diff_days.parquet")
    s = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seconds": round(time.time() - t0),
         "code_note": "legacy = legacy_overlap_dedupe=True; corrected = carga por defecto desde 2026-11-22",
         **summarize(df)}
    (out_dir / "diff.json").write_text(json.dumps(s, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(s, indent=1, ensure_ascii=False, default=str))
    show = [c for c in ("symbol", "day", "dedupe_ids", "trades_legacy", "trades_corrected", "added_volume_share",
                        "vwap_regular_diff", "lr_net_diff", "tick_net_diff", "agree_tick_lr_diff", "skipped") if c in df]
    print(df[df["origin"].str.contains("caso|ficha", regex=True)][show].to_string(index=False))


if __name__ == "__main__":
    main()
