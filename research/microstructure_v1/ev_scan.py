"""Escaneo MANUAL de eventos intradía para un día (E1). No hay tarea programada: se lanza a mano.

    py -3 ev_scan.py --day 2026-11-17 --symbols PLTR,NVDA,GOOGL [--pass full|regular] [--catalog cat-v1|cat-v0]
                      [--no-download] [--dry-run]
    py -3 ev_scan.py --day 2026-11-17 --universe current --dry-run      # solo muestra el plan de descarga

Escribe en MICRO_DATA_DIR/events/ (medidas de TODOS los valores escaneados, alertas, episodios) y
results/ev_scan_log.jsonl (tiempos y peticiones). Las fechas del periodo reservado de G2A están bloqueadas.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import event_scan, event_universe, runtime, storage  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--symbols", default="")
    ap.add_argument("--universe", choices=["current"], default=None)
    ap.add_argument("--pass", dest="pass_name", choices=["regular", "full"], default="full")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--catalog", choices=["cat-v0", "cat-v1"], default="cat-v1",
                    help="versión del catálogo (cat-v1 desde 2026-11-21; cat-v0 se conserva para reproducir E1)")
    ap.add_argument("--dry-run", action="store_true", help="solo el plan de descarga, sin descargar ni escanear")
    a = ap.parse_args()
    sources = {}
    if a.universe:
        u = event_universe.current_universe()
        syms, sources = sorted(u["symbols"]), u["symbols"]
    else:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    if not syms:
        raise SystemExit("sin valores")
    prov = None if a.no_download else runtime.alpaca()
    if a.dry_run:
        tot = {"symbols": len(syms), "missing_days": 0, "month_units": 0, "day_units": 0}
        for s in syms:
            r = event_scan.ensure_bars(prov, s, event_scan.baseline_days(a.day) + [a.day], {a.day: a.pass_name},
                                       dry_run=True)
            tot["missing_days"] += r["missing_days"]
            tot["month_units"] += sum(1 for k, *_ in r["plan"] if k == "month")
            tot["day_units"] += sum(1 for k, *_ in r["plan"] if k == "day")
        tot["requests_est"] = tot["month_units"] * 2 + tot["day_units"]
        print(json.dumps(tot, indent=1))
        return
    t0 = time.time()
    res = event_scan.scan_day(syms, a.day, a.pass_name, provider=prov, download_missing=not a.no_download,
                              sources=sources, catalog=a.catalog)
    res["wall_seconds"] = round(time.time() - t0, 1)
    res["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(storage.root() / "results" / "ev_scan_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(res, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
