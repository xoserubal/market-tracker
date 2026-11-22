"""E3 — registro diario completo (autorización del usuario, 2026-11-21). A mano o desde el piloto de cinco jornadas
(e3_pilot.py, Programador de tareas de Windows; aprobado el 2026-11-21). Sin otra programación permanente.

Una pasada `full` (después del after hours) para el universo actual (event_universe.current_universe, ≈ 620 valores) más
el contexto (SPY, QQQ y los ETFs sectoriales). Por cada valor y sesión conserva:
- capa 1: las barras originales de 1 minuto de la sesión completa (04:00-20:00 NY), una unidad diaria por valor en el
  manifiesto (misma clave que las bajadas individuales), con checksum;
- capa 2: las 44 medidas del valor-día, haya alertas o no (events/cat-v1/measures);
- capa 3: alertas y episodios de cat-v1, aparte (events/cat-v1/alerts, episodes);
- cobertura, incidencias, procedencia y versiones (events/cat-v1/symbol_days y results/e3/).
Universo: event_universe.current_universe() con el registro U1 (sucesiones de ticker resueltas; lo que Alpaca no cubre
no se pide y queda registrado como `provider_not_covered`).

Fases (cada una idempotente y reanudable; el diario results/e3/journal.jsonl registra lo hecho):
1. descarga con la petición múltiple, día a día (línea base + el día), en lotes; reintentos y división de lotes;
2. completitud: cada valor-día del día con unidad 'ok' o 'empty' y su cobertura de minutos frente a su propia historia;
3. escaneo cat-v1 por tandas (cada tanda se escribe al terminar; una tanda ya escrita con la misma versión se salta);
4. cierre del día: simultaneidad, días de mercado, sospechas y episodios sobre el universo entero;
5. registro de la pasada: coste real (peticiones, bytes, segundos por fase, disco añadido) y versiones.

Uso:
  py -3 e3_daily.py run --day 2026-11-20 [--batch 100] [--chunk 50] [--crash-after N]
  py -3 e3_daily.py verify --day 2026-11-20
--crash-after N simula una interrupción (os._exit) tras N lotes de descarga o N tandas de escaneo, para la prueba de
recuperación. Las fechas del periodo reservado de G2A están bloqueadas.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import catalog_v1 as V1, calendar, config, download, dq_checks, event_scan, event_store, event_universe, runtime, \
    sectors, sessions, storage, test_guard  # noqa: E402
from micro.manifest import Manifest  # noqa: E402

OUT = storage.root() / "results" / "e3"
JOURNAL = OUT / "journal.jsonl"
LOCK = OUT / "run.lock"
LOW_COV_RATIO = 0.5          # valor-día con menos de la mitad de sus minutos habituales (como g2a_outages)
_crash = {"left": None}


def jlog(ev: dict):
    OUT.mkdir(parents=True, exist_ok=True)
    ev = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **ev}
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")


def tick_crash(what: str):
    if _crash["left"] is None:
        return
    _crash["left"] -= 1
    if _crash["left"] <= 0:
        jlog({"event": "simulated_crash", "after": what})
        print(f"!! interrupción simulada tras {what}", flush=True)
        os._exit(3)


def universe() -> tuple:
    u = event_universe.current_universe()
    syms = sorted(u["symbols"])
    ctx = set(event_universe.CONTEXT) | {e for e in sectors._tables()[0].SECTOR_ETF.values() if e}
    # lo que Alpaca no cubre (según el registro del universo) no se pide: se registra como no cubierto en el escaneo
    nc = set(u.get("not_covered", {}))
    return syms, sorted((set(syms) | ctx) - nc), {k: v for k, v in u.items() if k != "symbols"}, u["symbols"]


def unit_bytes(m: Manifest, symbols: list, days: list) -> dict:
    cfg = download.config_for("bars", bars_window="day")
    keys = [download.unit_key("alpaca", "bars", s, None, d, cfg) for s in symbols for d in days]
    st, tot = {}, 0
    with m._c() as c:
        for i in range(0, len(keys), 500):
            q = ",".join("?" * len(keys[i:i + 500]))
            for r in c.execute(f"SELECT status, file_bytes FROM units WHERE unit_key IN ({q})", keys[i:i + 500]):
                st[r["status"]] = st.get(r["status"], 0) + 1
                tot += int(r["file_bytes"] or 0)
    st["missing"] = len(keys) - sum(st.values())
    return {"units": st, "file_bytes": tot}


def coverage_check(syms: list, day: str, base_days: list, m: Manifest) -> dict:
    """Completitud del día: unidad por valor, minutos de negociación continua y por tramo, frente a su propia historia."""
    from micro import intraday_features as F
    b = sessions.bounds(day)
    cont = b["close_slot"] - b["open_slot"] - 1
    rows = []
    look = base_days[-20:]
    # sesión reducida (p. ej. 27-nov: cierre 13:00, after hours hasta 17:00): lo esperado se escala por la duración de
    # la sesión completa de ese día frente a la mediana de la línea base; sin esto, todo saldría «cobertura baja»
    mins = lambda d: (sessions.bounds(d)["full_close"] - sessions.bounds(d)["full_open"]).total_seconds() / 60  # noqa: E731
    scale = mins(day) / float(np.median([mins(d) for d in look])) if look else 1.0
    o_m = b["open"].tz_convert(sessions.NY).hour * 60 + b["open"].tz_convert(sessions.NY).minute
    c_m = b["close"].tz_convert(sessions.NY).hour * 60 + b["close"].tz_convert(sessions.NY).minute
    for s in syms:
        bars = F.load_bars(s, look + [day], m)
        if not len(bars):
            rows.append({"symbol": s, "status": "no_bars", "cont_minutes": 0})
            continue
        cnt = bars.groupby("_day").size()
        today = int(cnt.get(day, 0))
        hist = cnt.drop(day, errors="ignore")
        med = float(hist.median()) if len(hist) else None
        x = bars[bars["_day"] == day]
        ny = x["t"].dt.tz_convert(sessions.NY)
        hm = ny.dt.hour * 60 + ny.dt.minute
        mx = dq_checks.mixed_series(x.sort_values("t")["c"].to_numpy()) if today else {"flag": False}
        rows.append({"symbol": s, "status": "ok" if today else "no_bars_today", "bars_today": today,
                     "mixed_flag": mx["flag"], "mixed": mx if mx["flag"] else None,
                     "median_bars_20d": med, "ratio": round(today / (med * scale), 3) if med else None,
                     "pre": int((hm < o_m).sum()), "regular": int(((hm >= o_m) & (hm < c_m)).sum()),
                     "post": int((hm >= c_m).sum()), "cont_minutes": cont})
    df = pd.DataFrame(rows)
    low = df[(df["ratio"].notna()) & (df["ratio"] < LOW_COV_RATIO)]
    # `is True`: en los valores sin barras la columna queda vacía (NaN), que en Python cuenta como verdadero
    mixed = {r.symbol: r.mixed for r in df.itertuples() if getattr(r, "mixed_flag", False) is True}
    return {"symbols": len(df), "with_bars_today": int((df["status"] == "ok").sum()),
            "early_close": bool(calendar.is_early_close(day)), "expected_scale": round(scale, 4),
            "mixed_series": mixed, "mixed_series_rule": dq_checks.MIXED,
            "without_bars_today": df.loc[df["status"] != "ok", "symbol"].tolist(),
            "low_coverage": low[["symbol", "bars_today", "median_bars_20d", "ratio"]].to_dict("records"),
            "low_coverage_share": round(len(low) / max(1, len(df)), 4),
            "market_wide_outage_candidate": len(low) / max(1, len(df)) > 0.20,
            "bars_today_total": int(df.get("bars_today", pd.Series(dtype=float)).fillna(0).sum()),
            "by_segment_total": {k: int(df[k].fillna(0).sum()) for k in ("pre", "regular", "post") if k in df}}


def run(day: str, pass_name: str, batch: int, chunk: int, crash_after=None):
    test_guard.check([day], purpose="E3 registro diario (prueba manual)", script="e3_daily")
    if pass_name != "full":
        raise SystemExit("la prueba E3 usa la pasada full")
    b = sessions.bounds(day)
    now = pd.Timestamp(datetime.now(timezone.utc))
    if now < b["full_close"] + pd.Timedelta(minutes=event_scan.SAFETY_MIN):
        raise SystemExit(f"la pasada full de {day} no puede correr antes de {b['full_close']} + {event_scan.SAFETY_MIN} min")
    OUT.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        info = LOCK.read_text(encoding="utf-8")
        pid = int(json.loads(info)["pid"])
        try:
            import psutil
            alive = psutil.pid_exists(pid)
        except Exception:  # noqa: BLE001
            alive = True
        if alive:
            raise SystemExit(f"hay otra pasada en marcha: {info}")
        jlog({"event": "stale_lock_removed", "lock": info})
    LOCK.write_text(json.dumps({"pid": os.getpid(), "day": day, "started": now.isoformat()}), encoding="utf-8")
    _crash["left"] = crash_after
    try:
        return _run(day, pass_name, batch, chunk)
    finally:
        LOCK.unlink(missing_ok=True)


def _run(day, pass_name, batch, chunk):
    t0 = time.time()
    m = Manifest()
    prov = runtime.alpaca()
    syms, dl_syms, umeta, sources = universe()
    base_days = event_scan.baseline_days(day)
    days = base_days + [day]
    rec = {"day": day, "pass": pass_name, "universe": len(syms), "download_symbols": len(dl_syms),
           "baseline_days": [days[0], days[-2], len(base_days)], "universe_meta": umeta,
           "code_version": config.code_version(), "catalog_version": V1.CATALOG_VERSION,
           "params_sha256": V1.PARAMS_SHA256, "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "not_covered": sorted(umeta.get("not_covered", {})), "superseded": umeta.get("superseded", {})}
    jlog({"event": "start", "day": day, "pass": pass_name, "code_version": rec["code_version"]})
    before = unit_bytes(m, dl_syms, days)
    events_before = sum(p.stat().st_size for p in event_store.root("cat-v1").rglob("*.parquet"))
    # 1. descarga
    t1 = time.time()
    dl = []
    for d in days:
        def lg(msg):
            print(msg, flush=True)
            tick_crash(f"lote de descarga ({d})")
        r = download.download_bars_multi_day(prov, dl_syms, d, manifest=m, batch=batch, log=lg)
        dl.append(r)
        jlog({"event": "download_day", **{k: r.get(k) for k in ("day", "already_done", "ok", "empty", "requests",
                                                                  "pages", "bytes_api", "batches", "splits")},
              "failed": len(r.get("failed", []))})
        print(f"{d}: {r.get('ok')} ok, {r.get('empty')} vacías, {r.get('already_done')} ya hechas, "
              f"{r.get('requests')} peticiones, {len(r.get('failed', []))} fallidas", flush=True)
    rec["download"] = {"seconds": round(time.time() - t1, 1),
                       **{k: sum(int(x.get(k) or 0) for x in dl) for k in ("ok", "empty", "already_done", "requests",
                                                                           "pages", "bytes_api", "batches", "retries",
                                                                           "batch_retries", "splits", "fallback_single")},
                       "failed": [f for x in dl for f in x.get("failed", [])]}
    after = unit_bytes(m, dl_syms, days)
    rec["units_before"], rec["units_after"] = before, after
    rec["disk_added_raw_mb"] = round((after["file_bytes"] - before["file_bytes"]) / 2**20, 1)
    # 2. completitud
    t2 = time.time()
    rec["coverage"] = coverage_check(syms, day, base_days, m)
    rec["coverage"]["seconds"] = round(time.time() - t2, 1)
    jlog({"event": "coverage", "with_bars_today": rec["coverage"]["with_bars_today"],
          "low_coverage_share": rec["coverage"]["low_coverage_share"]})
    # 3. escaneo por tandas (reanudable)
    t3 = time.time()
    sds = event_store.read("symbol_days", day, version="cat-v1")
    done = set(sds.loc[(sds["pass"] == pass_name) & (sds.get("code_version") == config.code_version()), "symbol"]) \
        if len(sds) and "code_version" in sds else set()
    todo = [s for s in syms if s not in done]
    scans = []
    print(f"escaneo: {len(todo)} pendientes, {len(done)} ya hechos con esta versión", flush=True)
    for i in range(0, len(todo), chunk):
        part = todo[i:i + chunk]
        r = event_scan.scan_day(part, day, pass_name, provider=prov, download_missing=False, sources=sources,
                                catalog="cat-v1", log=lambda *_: None)
        scans.append(r)
        jlog({"event": "scan_chunk", "first": part[0], "n": len(part), "alerts": r["alerts"],
              "seconds": r["stats"].get("total_seconds")})
        print(f"  tanda {i // chunk + 1}: {len(part)} valores, {r['alerts']} alertas, "
              f"{r['stats'].get('total_seconds')} s", flush=True)
        tick_crash("tanda de escaneo")
    rec["scan"] = {"seconds": round(time.time() - t3, 1), "chunks": len(scans), "scanned_now": len(todo),
                   "skipped_already_done": len(done)}
    # 4. cierre del día
    t4 = time.time()
    rec["finalize"] = {**event_scan.finalize_day_v1(day, pass_name, mixed=rec["coverage"]["mixed_series"]),
                       "seconds": round(time.time() - t4, 1)}
    # resumen del registro del día
    sds = event_store.read("symbol_days", day, version="cat-v1")
    sds = sds[sds["pass"] == pass_name]
    ms = event_store.read("measures", day, version="cat-v1")
    ms = ms[ms["pass"] == pass_name]
    rec["registry"] = {"symbol_days": int(len(sds)), "status": sds["status"].value_counts().to_dict(),
                       "measures_rows": int(len(ms)), "measures_per_symbol": ms.groupby("symbol").size()
                       .value_counts().to_dict(), "measure_states": ms["state"].value_counts().to_dict(),
                       "baseline_n": sds["baseline_n"].describe()[["min", "50%", "max"]].round(0).to_dict()
                       if "baseline_n" in sds else None}
    rec["events_disk_added_mb"] = round((sum(p.stat().st_size for p in event_store.root("cat-v1").rglob("*.parquet"))
                                         - events_before) / 2**20, 2)
    rec["seconds_total"] = round(time.time() - t0, 1)
    rec["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = OUT / f"run_{day}_{pass_name}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    p.write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    jlog({"event": "done", "file": p.name, "seconds": rec["seconds_total"]})
    print(json.dumps({k: rec[k] for k in ("download", "coverage", "scan", "finalize", "registry", "seconds_total",
                                          "disk_added_raw_mb", "events_disk_added_mb")}, ensure_ascii=False,
                     default=str)[:3000], flush=True)
    return rec


def snapshot_day(day: str, pass_name: str = "full") -> dict:
    """Contenido del registro del día sin las marcas de tiempo de cálculo (para comparar pasadas)."""
    out = {}
    drop = {"computed_utc", "seconds", "lab_url"}
    for t in ("measures", "symbol_days", "alerts", "episodes"):
        df = event_store.read(t, day, version="cat-v1")
        if not len(df):
            out[t] = None
            continue
        df = df[df["pass"] == pass_name].drop(columns=[c for c in df.columns if c in drop], errors="ignore")
        key = [c for c in ("symbol", "measure", "episode_id", "event_id", "t_detect_utc") if c in df.columns]
        df = df.sort_values(key).reset_index(drop=True)
        out[t] = pd.util.hash_pandas_object(df.astype(str), index=False).sum().item()
    return out


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--day", required=True)
    r.add_argument("--pass", dest="pass_name", default="full")
    r.add_argument("--batch", type=int, default=100)
    r.add_argument("--chunk", type=int, default=50)
    r.add_argument("--crash-after", type=int)
    v = sp.add_parser("snapshot")
    v.add_argument("--day", required=True)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.day, a.pass_name, a.batch, a.chunk, a.crash_after)
    else:
        print(json.dumps(snapshot_day(a.day)))


if __name__ == "__main__":
    main()
