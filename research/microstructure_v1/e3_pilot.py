"""E3 — piloto programado de cinco jornadas (autorización del usuario, 2026-11-21).

Lo lanza el Programador de tareas de Windows de LAWNMOWER (el equipo con MICRO_DATA_DIR) con `tick`. Cada `tick`:
1. Toma su propio cerrojo (si hay otro tick vivo, sale sin hacer nada; un cerrojo de un proceso muerto se retira).
2. Mira qué jornadas del piloto están pendientes: las que ya cerraron su after hours (calendario de Alpaca, hora de
   Nueva York con su cambio de horario) + el margen del proveedor y no tienen una pasada terminada. Si el equipo
   estuvo apagado, recupera todas las pendientes, de la más antigua a la más reciente.
3. Antes de cada jornada, una vez: la batería de pruebas (supervisión de la prueba intermitente); el resultado y los
   nombres de las que fallen quedan en el registro de la jornada.
4. Lanza la pasada full (e3_daily.run), con su cerrojo propio contra pasadas concurrentes y el bloqueo del periodo
   reservado, midiendo tiempo, CPU, memoria (pico del proceso y mínimo libre del sistema) y disco.
5. Comprueba cobertura y calidad del registro del día y decide ok / ok_con_avisos / fallo.
6. Escribe el resumen de la jornada (results/e3/pilot/days/AAAA-MM-DD.json) y avisa por Telegram: resumen breve si va
   bien, aviso con el error si falla. Tras 3 fallos de la misma jornada no la reintenta más (avisa).
7. Al terminar las cinco jornadas, avisa, deshabilita la tarea programada y no vuelve a hacer nada: la programación
   definitiva queda pendiente de revisión.

Uso:
  py -3 e3_pilot.py init --first 2026-11-23 --n 5     # fija las cinco jornadas (no cambia una vez fijadas)
  py -3 e3_pilot.py tick [--dry-run]                   # lo que ejecuta la tarea
  py -3 e3_pilot.py status
  py -3 e3_pilot.py install-task / uninstall-task      # tarea del Programador de Windows
  py -3 e3_pilot.py report                             # informe de fiabilidad y coste
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from micro import calendar, config, event_scan, sessions, storage, test_guard  # noqa: E402

PILOT = Path(os.environ.get("MICRO_E3_PILOT_DIR") or storage.root() / "results" / "e3" / "pilot")
TEST_MODE = bool(os.environ.get("MICRO_E3_PILOT_DIR"))      # directorio de prueba: avisos marcados y sin tocar la tarea
CFG = PILOT / "pilot.json"
DAYS = PILOT / "days"
LOGS = PILOT / "logs"
LOCK = PILOT / "tick.lock"
TASK = "MicroE3Pilot"
EXTRA_MIN = 10                 # además del margen de la pasada (SAFETY_MIN): no arrancar justo en el borde
MAX_ATTEMPTS = 3
# avisos de calidad (fijados antes del piloto; no son alertas del catálogo)
WARN = {"failed_units": 0, "low_coverage_share": 0.05, "without_bars_share": 0.02}


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def log(msg: str):
    line = f"{now_utc().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)


# ── Telegram ───────────────────────────────────────────────────────────────────────────────────────────────────
def notify(text: str, dry=False) -> bool:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if TEST_MODE:
        text = "[PRUEBA del piloto, no es una jornada del piloto]\n" + text
    if dry or not tok or not chat:
        log(f"[aviso{' (simulado)' if dry else ' SIN Telegram configurado'}] {text}")
        return False
    import requests
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": text[:3900]}, timeout=30)
        ok = r.status_code == 200
    except Exception as e:  # noqa: BLE001
        log(f"Telegram falló: {e}")
        ok = False
    log(f"[aviso {'enviado' if ok else 'NO enviado'}] {text[:200]}")
    return ok


# ── configuración y estado ─────────────────────────────────────────────────────────────────────────────────────
def load_cfg() -> dict:
    if not CFG.exists():
        raise SystemExit("piloto sin inicializar: py -3 e3_pilot.py init --first AAAA-MM-DD --n 5")
    return json.loads(CFG.read_text(encoding="utf-8"))


def day_rec(day: str) -> dict:
    p = DAYS / f"{day}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"day": day, "attempts": []}


def save_day(rec: dict):
    DAYS.mkdir(parents=True, exist_ok=True)
    p = DAYS / f"{rec['day']}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, p)


def ready_at(day: str) -> pd.Timestamp:
    return sessions.bounds(day)["full_close"] + pd.Timedelta(minutes=event_scan.SAFETY_MIN + EXTRA_MIN)


def init(first: str, n: int):
    if CFG.exists():
        raise SystemExit(f"el piloto ya está fijado: {CFG.read_text(encoding='utf-8')}")
    days = [d for d in calendar.trading_days(first, "2027-12-31")][:n]
    if len(days) < n:
        raise SystemExit("el calendario no tiene jornadas suficientes")
    test_guard.check(days, purpose="E3 piloto", script="e3_pilot")
    PILOT.mkdir(parents=True, exist_ok=True)
    cfg = {"created_utc": now_utc().isoformat(timespec="seconds"), "days": days, "n": n, "task": TASK,
           "status": "active", "early_close": [d for d in days if calendar.is_early_close(d)],
           "ready_at_utc": {d: ready_at(d).isoformat() for d in days},
           "warn_rules": WARN, "max_attempts": MAX_ATTEMPTS, "host": os.environ.get("COMPUTERNAME")}
    CFG.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    print(json.dumps(cfg, indent=1))


# ── cerrojo del tick ───────────────────────────────────────────────────────────────────────────────────────────
def take_lock() -> bool:
    import psutil
    PILOT.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            info = json.loads(LOCK.read_text(encoding="utf-8"))
            if psutil.pid_exists(int(info["pid"])):
                p = psutil.Process(int(info["pid"]))
                if "python" in p.name().lower() and "e3_pilot" in " ".join(p.cmdline()):
                    log(f"otro tick en marcha (pid {info['pid']}): salgo")
                    return False
            log(f"cerrojo de un proceso muerto retirado: {info}")
        except Exception as e:  # noqa: BLE001
            log(f"cerrojo ilegible retirado: {e}")
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        LOCK.unlink(missing_ok=True)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, json.dumps({"pid": os.getpid(), "started": now_utc().isoformat()}).encode())
    os.close(fd)
    return True


# ── medición de recursos ───────────────────────────────────────────────────────────────────────────────────────
class Meter:
    def __init__(self, every=3.0):
        import psutil
        self.ps, self.p, self.every = psutil, psutil.Process(), every
        self.peak_rss = 0
        self.min_avail = None
        self.stop = threading.Event()
        self.th = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.peak_rss = max(self.peak_rss, self.p.memory_info().rss)
                a = self.ps.virtual_memory().available
                self.min_avail = a if self.min_avail is None else min(self.min_avail, a)
            except Exception:  # noqa: BLE001
                pass
            self.stop.wait(self.every)

    def __enter__(self):
        self.t0 = time.time()
        self.cpu0 = self.p.cpu_times()
        try:
            self.io0 = self.p.io_counters()
        except Exception:  # noqa: BLE001
            self.io0 = None
        self.disk0 = shutil.disk_usage(storage.root()).free
        self.th.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        self.th.join(timeout=10)
        cpu = self.p.cpu_times()
        out = {"wall_s": round(time.time() - self.t0, 1),
               "cpu_user_s": round(cpu.user - self.cpu0.user, 1), "cpu_system_s": round(cpu.system - self.cpu0.system, 1),
               "peak_rss_mb": round(self.peak_rss / 2**20), "min_system_available_mb":
                   round(self.min_avail / 2**20) if self.min_avail else None,
               "disk_free_before_gb": round(self.disk0 / 2**30, 2),
               "disk_free_after_gb": round(shutil.disk_usage(storage.root()).free / 2**30, 2)}
        out["disk_used_gb"] = round(out["disk_free_before_gb"] - out["disk_free_after_gb"], 3)
        if self.io0:
            io = self.p.io_counters()
            out["io_read_mb"] = round((io.read_bytes - self.io0.read_bytes) / 2**20)
            out["io_write_mb"] = round((io.write_bytes - self.io0.write_bytes) / 2**20)
        self.result = out
        return False


# ── supervisión: batería de pruebas ────────────────────────────────────────────────────────────────────────────
def run_tests() -> dict:
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-rfE", "-p", "no:cacheprovider", "--tb=short"],
                       cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    out = p.stdout + p.stderr
    tail = [ln for ln in out.splitlines() if ln.strip()][-1:] or [""]
    failed = [ln.split(" ", 1)[1].split(" - ")[0] for ln in out.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
    res = {"returncode": p.returncode, "summary": tail[0], "failed": failed, "seconds": round(time.time() - t0, 1)}
    if failed:
        LOGS.mkdir(parents=True, exist_ok=True)
        f = LOGS / f"tests_failed_{now_utc().strftime('%Y%m%dT%H%M%S')}.log"
        f.write_text(out, encoding="utf-8")
        res["log"] = f.name
    return res


# ── calidad del día ────────────────────────────────────────────────────────────────────────────────────────────
def quality(rec: dict) -> tuple:
    cov, reg, dl = rec["coverage"], rec["registry"], rec["download"]
    n = cov["symbols"]
    without = [s for s in cov["without_bars_today"] if s not in set(rec.get("not_covered", []))]
    issues = []
    if len(dl["failed"]) > WARN["failed_units"]:
        issues.append(f"{len(dl['failed'])} unidades de descarga fallidas")
    if cov["low_coverage_share"] > WARN["low_coverage_share"]:
        issues.append(f"cobertura baja en el {cov['low_coverage_share']:.1%} de los valores")
    if cov["market_wide_outage_candidate"]:
        issues.append("posible caída general de datos (cobertura baja en > 20 %)")
    if len(without) / max(1, n) > WARN["without_bars_share"]:
        issues.append(f"{len(without)} valores sin barras hoy")
    if reg["symbol_days"] < n:
        issues.append(f"registro incompleto: {reg['symbol_days']} de {n} valor-días")
    if cov.get("mixed_series"):
        issues.append(f"series mezcladas: {', '.join(cov['mixed_series'])}")
    return ("ok" if not issues else "ok_con_avisos"), issues, without


def process_day(day: str, dry: bool) -> dict:
    import e3_daily
    rec = day_rec(day)
    att = {"started_utc": now_utc().isoformat(timespec="seconds"), "host": os.environ.get("COMPUTERNAME"),
           "code_version": config.code_version()}
    rec["attempts"].append(att)
    save_day(rec)
    try:
        att["tests"] = run_tests()
        log(f"pruebas: {att['tests']['summary']}")
        if dry:
            att["status"] = "dry_run"
            return rec
        with Meter() as m:
            r = e3_daily.run(day, "full", batch=100, chunk=50)
        att["resources"] = m.result
        status, issues, without = quality(r)
        att["status"], att["issues"] = status, issues
        att["summary"] = {
            "universe": r["universe"], "download_symbols": r["download_symbols"],
            "requests": r["download"]["requests"], "bytes_api_mb": round(r["download"]["bytes_api"] / 2**20, 1),
            "units_new": r["download"]["ok"] + r["download"]["empty"], "units_already": r["download"]["already_done"],
            "failed_units": len(r["download"]["failed"]), "with_bars_today": r["coverage"]["with_bars_today"],
            "without_bars_today": without, "not_covered": r.get("not_covered", []),
            "low_coverage": r["coverage"]["low_coverage"], "mixed_series": list(r["coverage"]["mixed_series"]),
            "alerts": r["finalize"].get("alerts"), "episodes": r["finalize"].get("episodes"),
            "symbol_days": r["registry"]["symbol_days"], "status_counts": r["registry"]["status"],
            "seconds": {k: r[k]["seconds"] for k in ("download", "coverage", "scan", "finalize")},
            "seconds_total": r["seconds_total"], "raw_added_mb": r["disk_added_raw_mb"],
            "events_added_mb": r["events_disk_added_mb"]}
        rec["done"] = True
    except SystemExit as e:                       # cerrojo de e3_daily ocupado, sesión no cerrada, periodo reservado
        att["status"], att["error"] = "skipped", str(e)
    except Exception as e:  # noqa: BLE001
        att["status"], att["error"] = "failed", f"{type(e).__name__}: {e}"
        att["traceback"] = traceback.format_exc()[-4000:]
    finally:
        att["finished_utc"] = now_utc().isoformat(timespec="seconds")
        save_day(rec)
    return rec


def message(day: str, att: dict, cfg: dict) -> str:
    i = cfg["days"].index(day) + 1
    if att["status"] in ("ok", "ok_con_avisos"):
        s, res = att["summary"], att["resources"]
        t = (f"E3 piloto {i}/{cfg['n']} · {day}: {'OK' if att['status'] == 'ok' else 'OK con avisos'}\n"
             f"{s['symbol_days']} valor-días, {s['with_bars_today']} con barras, {s['alerts']} alertas, "
             f"{s['episodes']} episodios\n"
             f"{round(s['seconds_total'] / 60, 1)} min, {s['requests']} peticiones, {s['raw_added_mb']} MB de barras, "
             f"pico {res['peak_rss_mb']} MB de memoria\n"
             f"pruebas: {att['tests']['summary']}")
        if att["issues"]:
            t += "\navisos: " + "; ".join(att["issues"])
        if att["tests"]["failed"]:
            t += "\nPRUEBAS FALLIDAS: " + ", ".join(att["tests"]["failed"])
        return t
    return f"E3 piloto {i}/{cfg['n']} · {day}: {att['status'].upper()}\n{att.get('error', '')[:1500]}"


def tick(dry: bool):
    cfg = load_cfg()
    if cfg["status"] != "active":
        log(f"piloto {cfg['status']}: nada que hacer")
        return
    if not take_lock():
        return
    try:
        for day in cfg["days"]:
            rec = day_rec(day)
            if rec.get("done"):
                continue
            if now_utc() < ready_at(day):
                log(f"{day}: aún no (lista a partir de {ready_at(day)})")
                break
            from micro import heavy_lock
            h = heavy_lock.holder()
            if h:                   # no solapar con un cálculo intensivo: se reintenta en el siguiente disparo
                log(f"{day}: lista, pero hay un proceso intensivo en marcha ({h.get('job')}, pid {h.get('pid')}); "
                    f"se reintentará en el siguiente disparo")
                rec.setdefault("deferred", []).append({"ts": now_utc().isoformat(timespec="seconds"), "by": h})
                save_day(rec)
                break
            fails = [a for a in rec["attempts"] if a.get("status") == "failed"]
            if len(fails) >= MAX_ATTEMPTS:
                if not rec.get("gave_up_notified"):
                    notify(f"E3 piloto · {day}: {MAX_ATTEMPTS} fallos seguidos, no se reintenta. Revisar.", dry)
                    rec["gave_up_notified"] = True
                    save_day(rec)
                continue
            log(f"{day}: pasada full")
            rec = process_day(day, dry)
            att = rec["attempts"][-1]
            log(f"{day}: {att['status']} {att.get('issues') or att.get('error') or ''}")
            if att["status"] != "skipped" or "otra pasada" not in (att.get("error") or ""):
                notify(message(day, att, cfg), dry)
            if att["status"] in ("failed", "skipped", "dry_run"):
                break
        if all(day_rec(d).get("done") for d in cfg["days"]):
            cfg["status"] = "complete"
            cfg["completed_utc"] = now_utc().isoformat(timespec="seconds")
            CFG.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
            if TEST_MODE:
                dis = subprocess.CompletedProcess([], 0, "modo prueba: tarea no tocada", "")
            else:
                dis = subprocess.run(["schtasks", "/Change", "/TN", TASK, "/DISABLE"], capture_output=True, text=True)
            notify(f"E3 piloto completado ({cfg['n']} jornadas). Tarea programada deshabilitada "
                   f"({'ok' if dis.returncode == 0 else 'NO: ' + (dis.stderr or dis.stdout).strip()[:200]}). "
                   f"Informe: py -3 e3_pilot.py report", dry)
    finally:
        LOCK.unlink(missing_ok=True)


# ── tarea del Programador de Windows ───────────────────────────────────────────────────────────────────────────
TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Piloto E3 de microestructura: pasada full diaria (5 jornadas). Se deshabilita sola al terminar.</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger><StartBoundary>2026-11-22T03:40:00</StartBoundary><Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>
    <CalendarTrigger><StartBoundary>2026-11-22T09:15:00</StartBoundary><Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>
    <LogonTrigger><Enabled>true</Enabled><Delay>PT10M</Delay><UserId>{user}</UserId></LogonTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT6H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>{pyw}</Command><Arguments>-3 "{script}" tick</Arguments><WorkingDirectory>{cwd}</WorkingDirectory></Exec></Actions>
</Task>
"""


def install_task():
    user = f"{os.environ.get('USERDOMAIN')}\\{os.environ.get('USERNAME')}"
    pyw = shutil.which("pyw") or r"C:\Windows\pyw.exe"
    xml = TASK_XML.format(user=user, pyw=pyw, script=HERE / "e3_pilot.py", cwd=HERE)
    PILOT.mkdir(parents=True, exist_ok=True)
    p = PILOT / "task.xml"
    p.write_text(xml, encoding="utf-16")
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK, "/XML", str(p), "/F"], capture_output=True, text=True)
    print(r.stdout, r.stderr)
    q = subprocess.run(["schtasks", "/Query", "/TN", TASK, "/V", "/FO", "LIST"], capture_output=True, text=True)
    print(q.stdout[:2500])


def uninstall_task():
    r = subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True, text=True)
    print(r.stdout, r.stderr)


def status():
    cfg = load_cfg()
    print(json.dumps({k: cfg[k] for k in ("status", "days", "early_close", "ready_at_utc")}, indent=1))
    for d in cfg["days"]:
        r = day_rec(d)
        a = r["attempts"][-1] if r["attempts"] else {}
        print(d, "hecho" if r.get("done") else "pendiente", len(r["attempts"]), "intentos", a.get("status"),
              a.get("issues") or a.get("error") or "")


def report():
    cfg = load_cfg()
    rows = []
    for d in cfg["days"]:
        r = day_rec(d)
        ok = [a for a in r["attempts"] if a.get("status") in ("ok", "ok_con_avisos")]
        a = ok[-1] if ok else (r["attempts"][-1] if r["attempts"] else {})
        s, res = a.get("summary", {}), a.get("resources", {})
        rows.append({"day": d, "done": bool(r.get("done")), "attempts": len(r["attempts"]),
                     "failed_attempts": sum(x.get("status") == "failed" for x in r["attempts"]),
                     "status": a.get("status"), "issues": a.get("issues"), "started_utc": a.get("started_utc"),
                     "delay_after_ready_min": round((pd.Timestamp(a["started_utc"]) - ready_at(d)).total_seconds() / 60)
                     if a.get("started_utc") else None,
                     "minutes": round(s.get("seconds_total", 0) / 60, 1), "requests": s.get("requests"),
                     "raw_added_mb": s.get("raw_added_mb"), "events_added_mb": s.get("events_added_mb"),
                     "peak_rss_mb": res.get("peak_rss_mb"), "cpu_s": (res.get("cpu_user_s") or 0) + (res.get("cpu_system_s") or 0),
                     "min_sys_avail_mb": res.get("min_system_available_mb"), "disk_used_gb": res.get("disk_used_gb"),
                     "tests": [x.get("tests", {}).get("summary") for x in r["attempts"]],
                     "tests_failed": sorted({f for x in r["attempts"] for f in x.get("tests", {}).get("failed", [])}),
                     "alerts": s.get("alerts"), "episodes": s.get("episodes"), "symbol_days": s.get("symbol_days"),
                     "without_bars_today": s.get("without_bars_today")})
    out = {"pilot": cfg, "days": rows}
    p = PILOT / "report.json"
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(rows, indent=1, ensure_ascii=False, default=str))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("init")
    i.add_argument("--first", required=True)
    i.add_argument("--n", type=int, default=5)
    t = sp.add_parser("tick")
    t.add_argument("--dry-run", action="store_true")
    for c in ("status", "install-task", "uninstall-task", "report"):
        sp.add_parser(c)
    a = ap.parse_args()
    if a.cmd == "tick":
        LOGS.mkdir(parents=True, exist_ok=True)
        f = open(LOGS / f"tick_{now_utc().strftime('%Y%m%d')}.log", "a", encoding="utf-8")
        if sys.stdout is None or not sys.stdout.isatty():
            sys.stdout = sys.stderr = f                 # pyw.exe no tiene consola
        log(f"tick (pid {os.getpid()}, {sys.executable})")
        try:
            tick(a.dry_run)
        except SystemExit as e:
            log(f"salida: {e}")
        except Exception:  # noqa: BLE001
            log(traceback.format_exc())
            notify(f"E3 piloto: error inesperado en el tick\n{traceback.format_exc()[-1500:]}", a.dry_run)
    elif a.cmd == "init":
        init(a.first, a.n)
    else:
        {"status": status, "install-task": install_task, "uninstall-task": uninstall_task, "report": report}[a.cmd]()


if __name__ == "__main__":
    main()
