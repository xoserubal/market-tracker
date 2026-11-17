"""G2 — descargas por lotes reanudables: quotes (submuestra), nivel A (barras 1 min) y piloto B1 (trades).

Uso:
  py -3 g2_downloads.py freeze-a              congela la lista de unidades del nivel A (samples/levelA_units_v1)
  py -3 g2_downloads.py run --stages quotes,A,B1 --workers 3
  py -3 g2_downloads.py status                resumen del manifiesto por etapa
  py -3 g2_downloads.py verify --stage A      recalcula checksums de lo descargado

Reanudable: una unidad 'ok'/'empty' en el manifiesto no se vuelve a pedir (al saltar no se relee el fichero
para no releer 36 GB; la verificación completa de checksums es el comando `verify`).
Parada segura: si el disco baja del margen (MICRO_MIN_FREE_GB) la etapa se detiene sin dejar ficheros a medias.
Errores no reintentables (4xx) quedan como 'failed' y la etapa sigue; al final se reintentan una vez.
Progreso: MICRO_DATA_DIR/results/g2_download_progress.json y g2_download_log.jsonl.
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g1_plans  # noqa: E402
from micro import calendar, download, runtime, sampling, storage  # noqa: E402
from micro.manifest import Manifest  # noqa: E402
from micro.providers.base import ProviderError  # noqa: E402

LAST_SESSION = g1_plans.LAST                  # 2026-11-13: última sesión cerrada del plan
CAP_UTC = None                                # se calcula: fin de la sesión extendida de LAST_SESSION
B1_SESSION = "full"                           # trades 04:00-20:00 NY (la sesión se etiqueta por trade)
QUOTES_SESSION = "regular"                    # quotes solo en sesión regular (comparación de clasificadores)

_lock = threading.Lock()
# Si ninguna unidad termina en este tiempo, el proceso se da por colgado (p. ej. hilos muertos por falta de
# memoria, 2026-11-15) y sale con código 3 para relanzarlo; la descarga es reanudable.
STALL_TIMEOUT_S = int(os.environ.get("MICRO_STALL_TIMEOUT_S", "900"))
# Planes B1/quotes: v2 corrige PCLN->BKNG y FISV->FI (g2_plan_corrections.py, autorizado 2026-11-15). v1 sigue
# intacto en samples/ como referencia; las unidades vacías que pidió v1 quedan en el manifiesto sin usarse.
PLAN_VERSION = os.environ.get("MICRO_PLAN_VERSION", "v2")
# Control de memoria: no se encola una unidad nueva si la memoria física libre baja de este margen; se espera.
# El 2026-11-15 un análisis en paralelo agotó la memoria y mató los hilos de descarga.
MIN_FREE_MEM_MB = int(os.environ.get("MICRO_DL_MIN_FREE_MB", "1500"))


def free_mem_mb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e6
    except Exception:  # noqa: BLE001 - sin psutil no se controla
        return float("inf")


def wait_for_memory(stage: str, max_wait_s: int = 600):
    """Espera (sin consumir peticiones) hasta que haya memoria libre suficiente; registra la espera."""
    t0 = time.time()
    logged = False
    while free_mem_mb() < MIN_FREE_MEM_MB and time.time() - t0 < max_wait_s:
        if not logged:
            _log({"event": "memory_wait", "stage": stage, "free_mb": round(free_mem_mb()), "min_mb": MIN_FREE_MEM_MB})
            logged = True
        time.sleep(15)
    if logged:
        _log({"event": "memory_resume", "stage": stage, "free_mb": round(free_mem_mb()), "waited_s": round(time.time() - t0)})


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(rec: dict):
    rec = {"ts": _now(), **rec}
    with _lock:
        with open(storage.root() / "results" / "g2_download_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")


def cap_utc() -> str:
    return calendar.iso(calendar.session_bounds(LAST_SESSION, "full")[1])


# ── listas de unidades ──
def freeze_level_a() -> pd.DataFrame:
    ref = storage.root() / "reference"
    iv = pd.read_parquet(ref / "universe_intervals.parquet")
    daily = pd.read_parquet(ref / "daily_bars_levelA.parquet").drop_duplicates(["entity", "date"])
    days = calendar.trading_days(g1_plans.FIRST, LAST_SESSION)
    ua = g1_plans.level_a_days(iv, daily, days)
    ua["asof"] = ua["asof"].where(ua["asof"].map(lambda x: isinstance(x, str) and bool(x.strip())), None)
    units = (ua.groupby(["symbol", "asof", "month"], dropna=False)
               .agg(entities=("entity", lambda s: ",".join(sorted(set(map(str, s))))), days=("date", "size"),
                    est_trades=("n", "sum"))
               .reset_index().sort_values(["month", "symbol"]).reset_index(drop=True))
    meta = sampling.freeze(units, {"design": "nivel A: barras 1 min por (símbolo, asof, mes); pertenencia S&P 500 a fecha "
                                             "+ EE. UU. del proyecto; 252 sesiones antes y 60 después",
                                   "last_session": LAST_SESSION, "cap_current_month_utc": cap_utc()},
                           "levelA_units_v1")
    print(json.dumps({"units": len(units), "months": units["month"].nunique(), **meta}, default=str)[:600])
    return units


def units_for(stage: str) -> list:
    """Lista de (kind, symbol, period, asof, cfg) de una etapa, a partir de los planes congelados."""
    smp = storage.root() / "samples"
    out = []
    if stage == "A":
        u = pd.read_parquet(smp / "levelA_units_v1.parquet")
        cap_month = LAST_SESSION[:7]
        for r in u.itertuples():
            cfg = download.config_for("bars", cap=cap_utc() if r.month == cap_month else None)
            out.append(("bars", r.symbol, r.month, r.asof, cfg))
    elif stage == "B1":
        plan = pd.read_parquet(smp / f"b1_plan_{PLAN_VERSION}.parquet")
        bd = sampling.block_days(plan, calendar.trading_days("2015-01-01", LAST_SESSION))
        cfg = download.config_for("trades", session=B1_SESSION)
        seen = set()
        for r in bd.sort_values(["date", "symbol"]).itertuples():
            k = (r.symbol, r.asof, r.date)
            if k not in seen:
                seen.add(k)
                out.append(("trades", r.symbol, r.date, r.asof, cfg))
    elif stage == "B1q":
        # subconjunto de B1: trades de los días con quotes (misma configuración que B1: no se duplican después)
        qp = pd.read_parquet(smp / f"quotes_plan_{PLAN_VERSION}.parquet")
        days = calendar.trading_days("2015-01-01", LAST_SESSION)
        pos = {d: i for i, d in enumerate(days)}
        cfg = download.config_for("trades", session=B1_SESSION)
        for r in qp.itertuples():
            for d in days[pos[r.q_start]: pos[r.q_end] + 1]:
                out.append(("trades", r.symbol, d, r.asof, cfg))
    elif stage == "quotes":
        qp = pd.read_parquet(smp / f"quotes_plan_{PLAN_VERSION}.parquet")
        days = calendar.trading_days("2015-01-01", LAST_SESSION)
        pos = {d: i for i, d in enumerate(days)}
        cfg_q = download.config_for("quotes", session=QUOTES_SESSION)
        for r in qp.itertuples():
            for d in days[pos[r.q_start]: pos[r.q_end] + 1]:
                out.append(("quotes", r.symbol, d, r.asof, cfg_q))
    else:
        raise ValueError(stage)
    return out


# ── ejecución ──
class Progress:
    def __init__(self, stage, total):
        self.stage, self.total, self.t0 = stage, total, time.time()
        self.counts = {"ok": 0, "empty": 0, "skipped": 0, "not_trading_day": 0, "failed": 0}
        self.requests = self.rows = self.file_bytes = 0
        self.grades = {}

    def add(self, res: dict):
        with _lock:
            st = res.get("status", "failed")
            self.counts[st] = self.counts.get(st, 0) + 1
            self.requests += res.get("requests", 0) or 0
            self.rows += res.get("rows", 0) or 0
            self.file_bytes += res.get("file_bytes", 0) or 0
            if res.get("grade"):
                self.grades[res["grade"]] = self.grades.get(res["grade"], 0) + 1

    def snapshot(self):
        done = sum(self.counts.values())
        el = time.time() - self.t0
        new = done - self.counts["skipped"]
        rate = new / el * 3600 if el > 0 else 0
        rem = (self.total - done) / rate if rate > 0 else None
        return {"stage": self.stage, "updated_utc": _now(), "total": self.total, "done": done, **self.counts,
                "requests": self.requests, "rows": self.rows, "GB_written": round(self.file_bytes / 1e9, 3),
                "grades": self.grades, "elapsed_h": round(el / 3600, 2), "units_per_h": round(rate),
                "eta_h": round(rem, 1) if rem else None, "free_GB": round(storage.free_bytes() / 1e9, 1)}

    def write(self):
        f = storage.root() / "results" / "g2_download_progress.json"
        try:
            allp = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            allp = {}
        allp[self.stage] = self.snapshot()
        with _lock:
            f.write_text(json.dumps(allp, indent=1, default=str), encoding="utf-8")


_providers = threading.local()


def _provider():
    if not hasattr(_providers, "p"):
        _providers.p = runtime.alpaca()
    return _providers.p


def _one(u, manifest):
    kind, sym, period, asof, cfg = u
    try:
        return download.download_unit(_provider(), kind, sym, period, asof=asof, cfg=cfg, manifest=manifest,
                                      verify_checksum=False)
    except storage.DiskGuardError:
        raise
    except MemoryError as e:
        _log({"event": "unit_failed", "kind": kind, "symbol": sym, "period": period, "asof": asof,
              "error": "MemoryError", "retryable": True})
        return {"status": "failed", "error": "MemoryError"}
    except Exception as e:   # noqa: BLE001 - se registra y la etapa sigue
        _log({"event": "unit_failed", "kind": kind, "symbol": sym, "period": period, "asof": asof,
              "error": f"{type(e).__name__}: {e}"[:400], "retryable": getattr(e, "retryable", None)})
        return {"status": "failed", "error": str(e)}


def run_stage(stage: str, workers: int, limit: int = None):
    manifest = Manifest()
    units = units_for(stage)
    if limit:
        units = units[:limit]
    prog = Progress(stage, len(units))
    _log({"event": "stage_start", "stage": stage, "units": len(units), "workers": workers})
    failed = []
    stop = threading.Event()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        it = iter(units)
        futs = {}
        # ventana deslizante para no crear 76 000 futuros a la vez
        for _ in range(workers * 4):
            u = next(it, None)
            if u:
                futs[ex.submit(_one, u, manifest)] = u
        last_write = 0
        while futs:
            try:
                done_iter = as_completed(list(futs), timeout=STALL_TIMEOUT_S)
                f0 = next(done_iter)
            except TimeoutError:
                prog.write()
                _log({"event": "stall_exit", "stage": stage, "pending": len(futs), "timeout_s": STALL_TIMEOUT_S})
                sys.stderr.write(f"stall: ninguna unidad terminó en {STALL_TIMEOUT_S}s; saliendo\n")
                sys.stderr.flush()
                os._exit(3)
            for f in [f0]:
                u = futs.pop(f)
                try:
                    res = f.result()
                except storage.DiskGuardError as e:
                    _log({"event": "disk_guard_stop", "stage": stage, "detail": str(e)})
                    stop.set()
                    res = {"status": "failed"}
                prog.add(res)
                if res.get("status") == "failed":
                    failed.append(u)
                if not stop.is_set():
                    wait_for_memory(stage)
                    nu = next(it, None)
                    if nu:
                        futs[ex.submit(_one, nu, manifest)] = nu
                if time.time() - last_write > 30:
                    prog.write()
                    last_write = time.time()
                break
    if stop.is_set():
        prog.write()
        _log({"event": "stage_stopped", "stage": stage, "reason": "disk_guard"})
        return prog.snapshot()
    # un reintento de los fallidos (solo los reintentables por naturaleza: red/5xx/429 agotados)
    if failed:
        _log({"event": "retry_failed", "stage": stage, "n": len(failed)})
        for u in failed:
            res = _one(u, manifest)
            if res.get("status") != "failed":
                prog.counts["failed"] -= 1
                prog.add(res)
    prog.write()
    _log({"event": "stage_end", "stage": stage, **prog.snapshot()})
    return prog.snapshot()


def status():
    m = Manifest()
    rows = m.rows()
    df = pd.DataFrame(rows)
    if df.empty:
        print("manifiesto vacío")
        return
    df["cfg"] = df["config_json"]
    print(df.groupby(["kind", "status"]).agg(units=("unit_key", "size"), rows=("rows", "sum"),
                                             GB=("file_bytes", lambda s: round(s.fillna(0).sum() / 1e9, 2)),
                                             requests=("requests", "sum")).to_string())
    print(df.groupby(["kind", "quality_grade"]).size().to_string())


def verify(stage: str):
    m = Manifest()
    bad = 0
    for kind, sym, period, asof, cfg in units_for(stage):
        key = download.unit_key("alpaca", kind, sym, asof, period, cfg)
        r = m.get(key)
        if r and r["status"] == "ok" and not m.is_done(key, verify_checksum=True):
            bad += 1
    print({"stage": stage, "bad": bad})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["freeze-a", "run", "status", "verify"])
    ap.add_argument("--stages", default="quotes,A,B1")
    ap.add_argument("--stage", default="A")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "freeze-a":
        freeze_level_a()
    elif a.cmd == "run":
        for st in a.stages.split(","):
            print(json.dumps(run_stage(st, a.workers, a.limit), default=str))
    elif a.cmd == "status":
        status()
    else:
        verify(a.stage)
