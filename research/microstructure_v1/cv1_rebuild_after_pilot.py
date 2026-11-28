"""Reconstrucción del histórico de cat-v1 en cuanto termine el piloto E3 (aprobado por el usuario 2026-11-28).

Por qué: el incidente del disco (22-23 nov) borró results/cat_v1 y events/cat-v1. La regeneración en DESPACHOB se
cortó con el apagón del 23-nov 06:47 con 139 de 629 entidades hechas en la fase 1. cv1_build.py es reanudable (salta
las entidades ya hechas) y su fase 2 solo reescribe los días históricos (pass="retro"), así que no toca los días del
piloto E3 en events/cat-v1.

Qué hace cada disparo (tarea de Windows MicroCV1Rebuild):
1. Si ya terminó (o se rindió) → deshabilita su tarea y sale.
2. Si el piloto E3 no está «complete», hay un tick del piloto vivo o hay otro proceso intensivo → sale (siguiente
   disparo).
3. Huella de las capas 1-2 (cv1_integrity snapshot --tag pre_rebuild), toma el cerrojo de procesos intensivos y lanza
   cv1_build.py --phase 1 --workers 3 y después --phase 2.
4. Huella después (post_rebuild) y comparación: las capas 1-2 y cat-v0 no pueden cambiar.
5. Comprueba contra la implantación del 21-nov (CV1_INFORME.md): 235 634 alertas, 97 089 episodios, sin errores en la
   fase 1 y sin discrepancias fila/vector.
6. Avisa por Telegram del resultado. Dos intentos fallidos → se rinde y avisa.

Uso:
  py -3 cv1_rebuild_after_pilot.py status
  py -3 cv1_rebuild_after_pilot.py tick [--force-ignore-pilot]
  py -3 cv1_rebuild_after_pilot.py install-task | uninstall-task
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from micro import config, heavy_lock, storage  # noqa: E402,F401  (config carga el .env)

ROOT = storage.root()
OUT = ROOT / "results" / "cat_v1"
STATE = OUT / "rebuild_after_pilot_state.json"
LOGF = OUT / "rebuild_after_pilot.log"
PILOT = ROOT / "results" / "e3" / "pilot"
TASK = "MicroCV1Rebuild"
EXPECTED = {"alerts": 235634, "episodes": 97089}
MAX_FAILS = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str):
    line = f"{now()} {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with LOGF.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def notify(text: str) -> bool:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        log(f"[aviso SIN Telegram configurado] {text}")
        return False
    import requests
    try:
        ok = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                           data={"chat_id": chat, "text": text[:3900]}, timeout=30).status_code == 200
    except Exception as e:  # noqa: BLE001
        log(f"Telegram falló: {e}")
        ok = False
    log(f"[aviso {'enviado' if ok else 'NO enviado'}] {text[:300]}")
    return ok


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"status": "pending", "created_utc": now(), "attempts": []}


def save_state(s: dict):
    OUT.mkdir(parents=True, exist_ok=True)
    t = STATE.with_suffix(".json.tmp")
    t.write_text(json.dumps(s, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(t, STATE)


def disable_task():
    r = subprocess.run(["schtasks", "/Change", "/TN", TASK, "/DISABLE"], capture_output=True, text=True)
    log(f"tarea {TASK} deshabilitada: {'ok' if r.returncode == 0 else (r.stderr or r.stdout).strip()[:200]}")


def pilot_busy() -> str:
    """Motivo para esperar, o '' si se puede empezar."""
    pj = PILOT / "pilot.json"
    if not pj.exists():
        return "pilot.json no existe"
    st = json.loads(pj.read_text(encoding="utf-8")).get("status")
    if st != "complete":
        return f"piloto E3 en estado {st!r}"
    lock = PILOT / "tick.lock"
    if lock.exists():
        try:
            import psutil
            if psutil.pid_exists(int(json.loads(lock.read_text(encoding="utf-8"))["pid"])):
                return "tick del piloto en marcha"
        except Exception:  # noqa: BLE001
            pass
    return ""


def py() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("python.exe")                    # pyw no tiene consola; los hijos van con python.exe
    return str(w if w.exists() else exe)


def run(args: list, label: str) -> int:
    log(f"lanzo {label}: {' '.join(args)}")
    t0 = time.time()
    with LOGF.open("a", encoding="utf-8") as f:
        r = subprocess.run([py(), *args], cwd=HERE, stdout=f, stderr=subprocess.STDOUT,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log(f"{label} terminó con código {r.returncode} en {round((time.time() - t0) / 60, 1)} min")
    return r.returncode


def validate() -> tuple:
    issues, info = [], {}
    mp = OUT / "build_manifest.json"
    if not mp.exists():
        return ["falta build_manifest.json"], info
    m = json.loads(mp.read_text(encoding="utf-8"))
    info = {k: m.get(k) for k in ("entities", "alerts", "episodes", "consistency", "status_counts",
                                  "suspected_data_outage_days")}
    for k, v in EXPECTED.items():
        if m.get(k) != v:
            issues.append(f"{k}: {m.get(k)} (esperado {v})")
    if m.get("errors"):
        issues.append(f"{len(m['errors'])} entidades con error en la fase 1")
    c = m.get("consistency", {})
    if c.get("row_vs_vector_disagreements"):
        issues.append(f"{c['row_vs_vector_disagreements']} discrepancias fila/vector")
    if c.get("values_checked") != c.get("values_match"):
        issues.append(f"valores recalculados {c.get('values_match')}/{c.get('values_checked')}")
    cmp = ROOT / "results" / "cv1_integrity_pre_rebuild.json", ROOT / "results" / "cv1_integrity_post_rebuild.json"
    if all(p.exists() for p in cmp):
        A, B = (json.loads(p.read_text(encoding="utf-8")) for p in cmp)
        for k in ("stat_only", "sha256"):
            x, y = A[k], B[k]
            ch = sorted(p for p in x if p in y and x[p] != y[p]) + sorted(set(x) - set(y))
            if ch:
                issues.append(f"capas 1-2/cat-v0 cambiadas ({k}): {len(ch)} ficheros, p. ej. {ch[:3]}")
        info["integrity_files"] = {k: len(B[k]) for k in ("stat_only", "sha256")}
    else:
        issues.append("faltan las huellas antes/después")
    return issues, info


def tick(force_ignore_pilot=False):
    s = load_state()
    if s["status"] in ("done", "gave_up"):
        log(f"reconstrucción en estado {s['status']}: nada que hacer")
        disable_task()
        return
    why = "" if force_ignore_pilot else pilot_busy()
    if why:
        log(f"espero: {why}")
        return
    h = heavy_lock.holder()
    if h:
        log(f"espero: otro proceso intensivo en marcha ({h})")
        return
    att = {"started_utc": now()}
    s["status"] = "running"
    s["attempts"].append(att)
    save_state(s)
    notify("cat-v1: empieza la reconstrucción del histórico 2016-2021 (piloto E3 terminado). Unas horas; "
           "no apagues el equipo.")
    try:
        with heavy_lock.HeavyJob("cv1_rebuild_after_pilot"):
            steps = [(["cv1_integrity.py", "snapshot", "--tag", "pre_rebuild"], "huella antes"),
                     (["cv1_build.py", "--phase", "1", "--workers", "3"], "cv1_build fase 1"),
                     (["cv1_build.py", "--phase", "2"], "cv1_build fase 2"),
                     (["cv1_integrity.py", "snapshot", "--tag", "post_rebuild"], "huella después")]
            for args, label in steps:
                rc = run(args, label)
                if rc != 0:
                    raise RuntimeError(f"{label} terminó con código {rc}")
        issues, info = validate()
        att.update({"finished_utc": now(), "issues": issues, "info": info})
        att["status"] = "ok" if not issues else "failed"
    except Exception as e:  # noqa: BLE001
        att.update({"finished_utc": now(), "status": "failed", "error": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc()[-1500:]})
    fails = sum(a.get("status") == "failed" for a in s["attempts"])
    if att["status"] == "ok":
        s["status"] = "done"
        i = att["info"]
        notify(f"cat-v1: histórico reconstruido y verificado. {i.get('entities')} entidades, {i.get('alerts')} alertas, "
               f"{i.get('episodes')} episodios (iguales a la implantación del 21-nov); capas 1-2 sin cambios.")
    else:
        s["status"] = "gave_up" if fails >= MAX_FAILS else "pending"
        notify(f"cat-v1: la reconstrucción FALLÓ (intento {fails}/{MAX_FAILS}"
               f"{', no se reintenta' if s['status'] == 'gave_up' else ', se reintenta en el siguiente disparo'}).\n"
               f"{att.get('error') or '; '.join(att.get('issues') or [])}\nRegistro: {LOGF}")
    save_state(s)
    if s["status"] in ("done", "gave_up"):
        disable_task()


TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Reconstrucción del histórico de cat-v1 cuando termine el piloto E3 (aprobada 2026-11-28). Se deshabilita sola.</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger><StartBoundary>2026-11-28T05:10:00</StartBoundary><Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>
    <CalendarTrigger><StartBoundary>2026-11-28T11:00:00</StartBoundary><Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>
    <CalendarTrigger><StartBoundary>2026-11-28T16:00:00</StartBoundary><Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>
    <LogonTrigger><Enabled>true</Enabled><Delay>PT45M</Delay><UserId>{user}</UserId></LogonTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT10H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>{pyw}</Command><Arguments>-3 "{script}" tick</Arguments><WorkingDirectory>{cwd}</WorkingDirectory></Exec></Actions>
</Task>
"""


def install_task():
    import shutil
    user = f"{os.environ.get('USERDOMAIN')}\\{os.environ.get('USERNAME')}"
    pyw = shutil.which("pyw") or r"C:\Windows\pyw.exe"
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "rebuild_task.xml"
    p.write_text(TASK_XML.format(user=user, pyw=pyw, script=Path(__file__).resolve(), cwd=HERE), encoding="utf-16")
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK, "/XML", str(p), "/F"], capture_output=True, text=True)
    print(r.stdout, r.stderr)


def status():
    s = load_state()
    print(json.dumps(s, indent=1, ensure_ascii=False, default=str))
    print("esperando a:", pilot_busy() or "nada (puede empezar)")
    done = len(list((OUT / "_entities").glob("famday__*.parquet")))
    print(f"fase 1: {done} entidades hechas")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("tick")
    t.add_argument("--force-ignore-pilot", action="store_true")
    for c in ("status", "install-task", "uninstall-task"):
        sp.add_parser(c)
    a = ap.parse_args()
    if a.cmd == "tick":
        if sys.stdout is None:                          # pyw.exe: log() ya escribe en LOGF
            sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
        log(f"tick (pid {os.getpid()})")
        try:
            tick(a.force_ignore_pilot)
        except Exception:  # noqa: BLE001
            log(traceback.format_exc())
            notify(f"cat-v1 reconstrucción: error inesperado\n{traceback.format_exc()[-1200:]}")
    elif a.cmd == "status":
        status()
    elif a.cmd == "install-task":
        install_task()
    else:
        print(subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True, text=True).stdout)


if __name__ == "__main__":
    main()
