"""E3 — comprobación de integridad del entorno antes de cada disparo del piloto (autorización del usuario, 2026-11-22).

El piloto no debe arrancar si faltan archivos esenciales, están incompletos o no corresponden a la versión autorizada.
Si el entorno no es fiable, aborta limpiamente, lo registra y avisa por Telegram.

Cómo funciona
- `install` (en LAWNMOWER, una vez): congela el manifiesto de la versión autorizada y copia este archivo, el manifiesto y
  la configuración a <directorio del piloto>/guard/, en el disco de datos, FUERA de Dropbox; después cambia la acción de
  la tarea MicroE3Pilot para que ejecute `guard-tick` de esa copia (los disparadores y ajustes de la tarea no se tocan:
  se exporta su XML y solo se sustituye la acción; el XML original queda en guard/task_original.xml).
- `guard-tick` (lo que ejecuta la tarea): verifica; si todo cuadra, lanza `e3_pilot.py tick` con el mismo intérprete y
  espera; si no, no lanza nada, anota el bloqueo en guard/blocks.jsonl e integrity_blocks.jsonl del piloto y avisa por
  Telegram (una vez por problema distinto y día; y otra cuando se restablece).
- La copia instalada no depende de Dropbox: si la sincronización deja el repositorio a medias, el vigilante sigue
  pudiendo detectarlo y avisar.

Qué es «la versión autorizada» (manifiesto)
- Código: el cierre de importaciones locales de e3_pilot.py, e3_daily.py y de todo lo que hay en tests/ (lo que la
  batería del piloto ejecuta), resuelto con ast (micro/, lab/server.py, los scripts que importan las pruebas).
- Todos los archivos de tests/ (cualquier archivo nuevo ahí cambia lo que corre pytest: se trata como problema) y los
  archivos de configuración de pytest en el estudio y sus carpetas superiores hasta el repositorio.
- Configuración estática que el código lee: catalog/, lab/ (estáticos), retention_config.json, shadow_config.json,
  distribution_events_dev.csv y las referencias de otros estudios (constituents.json, wiki_revisions.json).
- No entran los datos de entrada que cambian a diario (portfolio.json, universe.json, snapshots del pipeline).
- Huella (`digest`): sha256 de las líneas «ruta sha256» ordenadas; no depende del equipo ni de la hora, así que la
  huella calculada en otro equipo con el mismo código debe coincidir (`--expect-digest`).

Comprobaciones de datos (en el disco del piloto, sin escribir nada)
- Rutas esenciales presentes y legibles: manifest/manifest.sqlite, raw/alpaca/bars, events/cat-v1,
  reference/universe_registry, results/e3, el directorio del piloto; manifest.sqlite se abre en solo lectura y debe
  pasar `PRAGMA quick_check`; pilot.json debe leerse y conservar las mismas jornadas fijadas.
- Avisos (no bloquean): versión de Python o de paquetes distinta de la congelada; copias en conflicto de Dropbox fuera
  de las carpetas vigiladas.

Uso (siempre con `py -3`; solo biblioteca estándar):
  py -3 e3_integrity.py digest                                  # huella del código en este equipo
  py -3 e3_integrity.py install --expect-digest HUELLA          # en LAWNMOWER: congela, copia y cambia la tarea
  py -3 e3_integrity.py install --no-task                       # igual sin tocar la tarea (prueba)
  py -3 "<pilot>/guard/e3_integrity.py" verify [--notify]       # comprobación a mano con la copia instalada
  py -3 "<pilot>/guard/e3_integrity.py" guard-tick              # lo que ejecuta la tarea
  py -3 e3_integrity.py uninstall                               # restaura la acción original de la tarea
Con MICRO_E3_PILOT_DIR definido (modo prueba del piloto) nunca se toca la tarea y los avisos van marcados.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GUARD_VERSION = "e3-integrity-1"
TASK = "MicroE3Pilot"
SELF = Path(__file__).resolve()
SEARCH_DIRS = ("", "lab", "tests")                 # sys.path efectivo de los scripts y de las pruebas
CODE_ROOTS = ("e3_pilot.py", "e3_daily.py", "e3_integrity.py")
WATCHED_DIRS = ("tests", "catalog")                # aquí un archivo no autorizado es un problema
STATIC = ("catalog", "lab", "retention_config.json", "shadow_config.json", "distribution_events_dev.csv",
          "../macd_combo_sp500_ndx_v1/constituents.json", "../sector_breadth_v1/data/wiki_revisions.json")
STATIC_EXT = {".json", ".csv", ".sha256", ".html", ".js", ".css", ".md", ".txt", ".py"}
PYTEST_CONFIGS = ("conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")
SKIP_PARTS = {"__pycache__", ".pytest_cache"}
PACKAGES = ("pandas", "numpy", "pyarrow", "requests", "psutil", "pytest", "python-dotenv")
ESSENTIAL_DATA = ("manifest/manifest.sqlite", "raw/alpaca/bars", "events/cat-v1", "reference/universe_registry",
                  "results/e3")
CONFLICT_RE = re.compile(r"(copia en conflicto|conflicted copy)", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _skip(p: Path) -> bool:
    return bool(SKIP_PARTS.intersection(p.parts)) or p.name.endswith((".pyc", ".tmp"))


# ── cierre de importaciones ─────────────────────────────────────────────────────────────────────────────────────
def _candidates(study: Path, parts: list) -> list:
    out = []
    for s in SEARCH_DIRS:
        base = study / s if s else study
        out += [base.joinpath(*parts).with_suffix(".py"), base.joinpath(*parts, "__init__.py")]
    return out


def _package_inits(study: Path, f: Path) -> list:
    """__init__.py de los paquetes que contienen f, dentro del estudio."""
    out, d = [], f.parent
    while d != study and study in d.parents:
        if (d / "__init__.py").exists():
            out.append(d / "__init__.py")
        d = d.parent
    return out


def imports_of(study: Path, f: Path) -> set:
    tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
    found = set()
    for node in ast.walk(tree):
        cands = []
        if isinstance(node, ast.Import):
            for a in node.names:
                cands += _candidates(study, a.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = f.parent
                for _ in range(node.level - 1):
                    base = base.parent
                mod = node.module.split(".") if node.module else []
                cands += [base.joinpath(*mod).with_suffix(".py") if mod else base / "__init__.py",
                          base.joinpath(*mod, "__init__.py")]
                cands += [base.joinpath(*mod, a.name).with_suffix(".py") for a in node.names]
            else:
                mod = node.module.split(".")
                cands += _candidates(study, mod)
                for a in node.names:
                    cands += _candidates(study, mod + [a.name])
        for c in cands:
            if c.exists() and (c.parent == study or study in c.parents):
                found.add(c.resolve())
    return found


def code_closure(study: Path) -> set:
    roots = [study / r for r in CODE_ROOTS if (study / r).exists()]
    roots += [p for p in (study / "tests").rglob("*.py") if not _skip(p)]
    seen, todo = set(), [r.resolve() for r in roots]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        for init in _package_inits(study, f):
            todo.append(init.resolve())
        try:
            todo += [g for g in imports_of(study, f) if g not in seen]
        except SyntaxError:
            pass                                   # la huella lo recoge igualmente
    return seen


def static_files(study: Path) -> set:
    out = set()
    for s in STATIC:
        p = (study / s).resolve()
        if p.is_dir():
            out |= {q.resolve() for q in p.rglob("*") if q.is_file() and not _skip(q) and q.suffix in STATIC_EXT}
        elif p.is_file():
            out.add(p)
    for d in WATCHED_DIRS:
        out |= {q.resolve() for q in (study / d).rglob("*") if q.is_file() and not _skip(q)}
    return out


def pytest_config_files(study: Path) -> list:
    """Archivos de configuración de pytest en el estudio y sus carpetas superiores hasta el repositorio."""
    out, d = [], study
    stop = study.parents[1]
    while True:
        out += [d / n for n in PYTEST_CONFIGS if (d / n).is_file()]
        if d == stop or d == d.parent:
            break
        d = d.parent
    return out


def _rel(study: Path, p: Path) -> str:
    return os.path.relpath(p, study).replace("\\", "/")


def digest_of(files: dict) -> str:
    lines = "".join(f"{k} {v['sha256']}\n" for k, v in sorted(files.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


def _versions() -> dict:
    from importlib import metadata
    pk = {}
    for name in PACKAGES:
        try:
            pk[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pk[name] = None
    return {"python": sys.version.split()[0], "executable": sys.executable, "packages": pk}


def _git(study: Path) -> dict:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=study, capture_output=True, text=True, timeout=30)
        st = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=study, capture_output=True, text=True,
                            timeout=60)
        return {"head": head.stdout.strip() or None, "dirty": [ln[3:] for ln in st.stdout.splitlines()]}
    except Exception as e:  # noqa: BLE001
        return {"head": None, "error": str(e)}


def build_manifest(study: Path) -> dict:
    study = study.resolve()
    paths = code_closure(study) | static_files(study) | {p.resolve() for p in pytest_config_files(study)}
    files = {_rel(study, p): {"sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted(paths)}
    return {"guard_version": GUARD_VERSION, "created_utc": now(), "host": os.environ.get("COMPUTERNAME"),
            "files": files, "digest": digest_of(files), "watched_dirs": list(WATCHED_DIRS),
            "pytest_configs": [_rel(study, p) for p in pytest_config_files(study)],
            "environment": _versions(), "git": _git(study)}


# ── entorno: .env y rutas de datos ──────────────────────────────────────────────────────────────────────────────
def read_env(study: Path) -> dict:
    env = {}
    f = study.parents[1] / ".env"
    try:
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", ln)
            if m:
                v = m.group(2).strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                env[m.group(1)] = v
    except OSError:
        pass
    return env


def getenv(study: Path, key: str) -> str:
    """Primero el entorno del proceso (aunque esté vacío: así una prueba puede desactivar Telegram); si no, el .env."""
    if key in os.environ:
        return os.environ[key].strip()
    return (read_env(study).get(key) or "").strip()


def data_paths(study: Path) -> tuple:
    root = getenv(study, "MICRO_DATA_DIR")
    if not root:
        raise SystemExit("falta MICRO_DATA_DIR en el entorno/.env")
    test_pilot = os.environ.get("MICRO_E3_PILOT_DIR")
    pilot = Path(test_pilot) if test_pilot else Path(root) / "results" / "e3" / "pilot"
    return Path(root), pilot, bool(test_pilot)


# ── comprobaciones ──────────────────────────────────────────────────────────────────────────────────────────────
def _readable(p: Path) -> str:
    """None si se puede leer; si no, el motivo."""
    try:
        if p.is_dir():
            with os.scandir(p) as it:
                next(it, None)
        else:
            with open(p, "rb") as f:
                f.read(4096)
        return None
    except OSError as e:
        return f"{type(e).__name__}: {e}"


def check_data(cfg: dict) -> tuple:
    problems, info = [], {}
    root, pilot = Path(cfg["data_root"]), Path(cfg["pilot_dir"])
    for rel in cfg.get("essential_data", []):
        p = root / rel
        if not p.exists():
            problems.append({"kind": "data_missing", "path": rel})
            continue
        why = _readable(p)
        if why:
            problems.append({"kind": "data_unreadable", "path": rel, "error": why})
    db = root / "manifest" / "manifest.sqlite"
    if "manifest/manifest.sqlite" in cfg.get("essential_data", []) and db.exists():
        t0 = time.time()
        try:
            con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=60)
            try:
                r = con.execute("PRAGMA quick_check").fetchall()
            finally:
                con.close()
            ok = len(r) == 1 and r[0][0] == "ok"
            info["sqlite_quick_check_s"] = round(time.time() - t0, 1)
            if not ok:
                problems.append({"kind": "sqlite_bad", "path": "manifest/manifest.sqlite", "detail": str(r[:5])})
        except sqlite3.Error as e:
            problems.append({"kind": "sqlite_bad", "path": "manifest/manifest.sqlite", "error": str(e)})
    pj = pilot / "pilot.json"
    try:
        days = json.loads(pj.read_text(encoding="utf-8"))["days"]
        if cfg.get("pilot_days") and days != cfg["pilot_days"]:
            problems.append({"kind": "pilot_days_changed", "expected": cfg["pilot_days"], "found": days})
    except Exception as e:  # noqa: BLE001
        problems.append({"kind": "pilot_json_bad", "path": str(pj), "error": f"{type(e).__name__}: {e}"})
    return problems, info


def check_code(study: Path, manifest: dict) -> tuple:
    problems, warnings = [], []
    study = study.resolve()
    for rel, want in manifest["files"].items():
        p = study / rel
        if not p.is_file():
            problems.append({"kind": "missing", "path": rel})
            continue
        try:
            size = p.stat().st_size
            if size != want["bytes"]:
                problems.append({"kind": "changed", "path": rel, "why": f"{size} bytes, autorizado {want['bytes']}"})
            elif sha256(p) != want["sha256"]:
                problems.append({"kind": "changed", "path": rel, "why": "sha256 distinto"})
        except OSError as e:
            problems.append({"kind": "unreadable", "path": rel, "error": str(e)})
    known = set(manifest["files"])
    for d in manifest.get("watched_dirs", WATCHED_DIRS):
        for q in (study / d).rglob("*"):
            if q.is_file() and not _skip(q) and _rel(study, q) not in known:
                problems.append({"kind": "extra", "path": _rel(study, q)})
    for p in pytest_config_files(study):
        if _rel(study, p) not in manifest.get("pytest_configs", []):
            problems.append({"kind": "pytest_config_added", "path": _rel(study, p)})
    conflicts = [q for q in study.rglob("*") if CONFLICT_RE.search(q.name) and not _skip(q)]
    if conflicts:
        warnings.append({"kind": "dropbox_conflict_copies", "paths": [_rel(study, q) for q in conflicts[:20]]})
    env = _versions()
    frozen = manifest.get("environment", {})
    diff = {k: (frozen.get("packages", {}).get(k), v) for k, v in env["packages"].items()
            if frozen.get("packages", {}).get(k) != v}
    if env["python"] != frozen.get("python"):
        diff["python"] = (frozen.get("python"), env["python"])
    if diff:
        warnings.append({"kind": "environment_changed", "diff": diff})
    return problems, warnings


def verify(study: Path, gdir: Path) -> dict:
    t0 = time.time()
    res = {"ts": now(), "guard_version": GUARD_VERSION, "problems": [], "warnings": []}
    try:
        cfg = json.loads((gdir / "guard.json").read_text(encoding="utf-8"))
        manifest = json.loads((gdir / "manifest.json").read_text(encoding="utf-8"))
        if digest_of(manifest["files"]) != manifest["digest"] or manifest["digest"] != cfg["digest"]:
            res["problems"].append({"kind": "guard_manifest_altered"})
    except Exception as e:  # noqa: BLE001
        res["problems"].append({"kind": "guard_config_unreadable", "error": f"{type(e).__name__}: {e}"})
        res["ok"], res["seconds"] = False, round(time.time() - t0, 1)
        return res
    if not study.is_dir():
        res["problems"].append({"kind": "study_dir_missing", "path": str(study)})
    else:
        p, w = check_code(study, manifest)
        res["problems"] += p
        res["warnings"] += w
    p, info = check_data(cfg)
    res["problems"] += p
    res.update(info)
    if SELF.parent == gdir.resolve() and manifest["files"].get("e3_integrity.py", {}).get("sha256") != sha256(SELF):
        res["warnings"].append({"kind": "installed_guard_differs_from_repo_copy",
                                "detail": "reinstalar (install) si se cambió e3_integrity.py"})
    res["digest"] = manifest["digest"]
    res["ok"] = not res["problems"]
    res["seconds"] = round(time.time() - t0, 1)
    return res


# ── avisos ──────────────────────────────────────────────────────────────────────────────────────────────────────
def notify(study: Path, text: str, test_mode: bool, log) -> bool:
    if test_mode:
        text = "[PRUEBA del piloto, no es una jornada del piloto]\n" + text
    tok, chat = getenv(study, "TELEGRAM_BOT_TOKEN"), getenv(study, "TELEGRAM_CHAT_ID")
    if not tok or not chat:
        log(f"[aviso SIN Telegram configurado] {text}")
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text[:3900]}).encode()
        with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=30) as r:
            ok = r.status == 200
    except Exception as e:  # noqa: BLE001
        log(f"Telegram falló: {e}")
        ok = False
    log(f"[aviso {'enviado' if ok else 'NO enviado'}] {text[:200]}")
    return ok


def describe(res: dict, limit=12) -> str:
    lines = []
    for p in res["problems"][:limit]:
        extra = p.get("why") or p.get("error") or p.get("detail") or ""
        lines.append(f"- {p['kind']}: {p.get('path', '')} {extra}".rstrip())
    if len(res["problems"]) > limit:
        lines.append(f"- … y {len(res['problems']) - limit} más")
    return "\n".join(lines)


def _signature(res: dict) -> str:
    keys = sorted(f"{p['kind']}|{p.get('path', '')}" for p in res["problems"])
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()[:16]


def _append(path: Path, rec: dict):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


# ── guard-tick ──────────────────────────────────────────────────────────────────────────────────────────────────
def guard_tick(gdir: Path) -> int:
    cfg = json.loads((gdir / "guard.json").read_text(encoding="utf-8"))
    study = Path(cfg["study_dir"])
    logf = open(gdir / f"guard_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log", "a", encoding="utf-8")

    def log(msg):
        logf.write(f"{now()} {msg}\n")
        logf.flush()

    log(f"guard-tick (pid {os.getpid()}, {sys.executable})")
    state_p = gdir / "state.json"
    try:
        state = json.loads(state_p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    try:
        res = verify(study, gdir)
    except Exception:  # noqa: BLE001
        res = {"ts": now(), "ok": False, "problems": [{"kind": "guard_crashed", "error": traceback.format_exc()[-800:]}],
               "warnings": []}
    log(f"verificación: {'OK' if res['ok'] else 'FALLO'} en {res.get('seconds')} s; "
        f"{len(res['problems'])} problemas, {len(res['warnings'])} avisos")
    for w in res["warnings"]:
        log(f"aviso: {json.dumps(w, ensure_ascii=False)}")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not res["ok"]:
        log("problemas:\n" + describe(res, limit=200))
        rec = {**res, "action": "pilot_not_started"}
        _append(gdir / "blocks.jsonl", rec)
        _append(Path(cfg["pilot_dir"]) / "integrity_blocks.jsonl", rec)
        sig = _signature(res)
        if state.get("alert_sig") != sig or state.get("alert_day") != today:
            notify(study, "E3 piloto: NO arranca, el entorno no coincide con la versión autorizada.\n"
                          f"{describe(res)}\nNo se ha lanzado ninguna pasada. Registro: {gdir}", cfg.get("test_mode"), log)
            state.update(alert_sig=sig, alert_day=today)
        state["failing_since"] = state.get("failing_since") or res["ts"]
        state_p.write_text(json.dumps(state, indent=1), encoding="utf-8")
        logf.close()
        return 2
    if state.get("failing_since"):
        notify(study, f"E3 piloto: integridad restablecida (fallaba desde {state['failing_since']}). "
                      "El piloto continúa.", cfg.get("test_mode"), log)
    state = {"last_ok": res["ts"]}
    state_p.write_text(json.dumps(state, indent=1), encoding="utf-8")
    env = dict(os.environ)
    if cfg.get("test_mode"):
        env["MICRO_E3_PILOT_DIR"] = cfg["pilot_dir"]
    log("lanzo e3_pilot.py tick")
    logf.flush()
    p = subprocess.run([sys.executable, str(study / "e3_pilot.py"), "tick"], cwd=study, env=env)
    log(f"e3_pilot.py tick terminó con código {p.returncode}")
    logf.close()
    return p.returncode


# ── instalación ─────────────────────────────────────────────────────────────────────────────────────────────────
def _task_xml_export() -> str:
    r = subprocess.run(["schtasks", "/Query", "/TN", TASK, "/XML"], capture_output=True, text=True)
    if r.returncode != 0 or "<Task" not in r.stdout:
        raise SystemExit(f"no encuentro la tarea {TASK}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def _task_create(xml: str, gdir: Path, name: str):
    p = gdir / name
    p.write_text(xml, encoding="utf-16")
    r = subprocess.run(["schtasks", "/Create", "/TN", TASK, "/XML", str(p), "/F"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"schtasks /Create falló: {(r.stderr or r.stdout).strip()[:300]}")


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def guarded_task_xml(xml: str, gdir: Path) -> str:
    """Mismo XML de la tarea con la acción cambiada a `guard-tick` de la copia instalada (el ejecutable, pyw, se
    conserva; disparadores, principal y ajustes no se tocan). Falla si el XML no tiene exactamente una acción."""
    if len(re.findall(r"<Exec>", xml)) != 1 or len(re.findall(r"<Arguments>", xml)) != 1:
        raise SystemExit("el XML de la tarea no tiene exactamente una acción con argumentos; no se toca nada")
    args = f'-3 "{gdir / "e3_integrity.py"}" guard-tick'
    new = re.sub(r"<Arguments>.*?</Arguments>", lambda _: f"<Arguments>{_xml_escape(args)}</Arguments>", xml, flags=re.S)
    wd = f"<WorkingDirectory>{_xml_escape(str(gdir))}</WorkingDirectory>"
    if "<WorkingDirectory>" in new:
        new = re.sub(r"<WorkingDirectory>.*?</WorkingDirectory>", lambda _: wd, new, flags=re.S)
    else:
        new = new.replace("</Arguments>", "</Arguments>" + wd, 1)
    if "guard-tick" not in new:
        raise SystemExit("no he podido sustituir la acción en el XML de la tarea; no se toca nada")
    return new


def install(study: Path, expect: str = None, no_task: bool = False):
    study = study.resolve()
    m = build_manifest(study)
    print(f"huella: {m['digest']} ({len(m['files'])} archivos)")
    if expect and expect != m["digest"]:
        raise SystemExit(f"la huella de este equipo NO coincide con la autorizada ({expect}): el código no es el mismo. "
                         "No se instala nada.")
    root, pilot, test_mode = data_paths(study)
    pj = pilot / "pilot.json"
    if not pj.exists():
        raise SystemExit(f"el piloto no está inicializado ({pj})")
    days = json.loads(pj.read_text(encoding="utf-8"))["days"]
    essential = [r for r in ESSENTIAL_DATA if (root / r).exists()]
    lost = sorted(set(ESSENTIAL_DATA) - set(essential))
    if lost:
        raise SystemExit(f"faltan rutas esenciales en {root}: {lost}. Revisar el disco antes de instalar.")
    cfg = {"guard_version": GUARD_VERSION, "installed_utc": now(), "host": os.environ.get("COMPUTERNAME"),
           "study_dir": str(study), "data_root": str(root), "pilot_dir": str(pilot), "test_mode": test_mode,
           "pilot_days": days, "essential_data": essential, "digest": m["digest"]}
    p, info = check_data(cfg)
    if p:
        raise SystemExit("las comprobaciones de datos fallan ya al instalar:\n" + describe({"problems": p}, 50))
    gdir = pilot / "guard"
    gdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SELF, gdir / "e3_integrity.py")
    (gdir / "manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")
    (gdir / "guard.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
    res = verify(study, gdir)
    if not res["ok"]:
        raise SystemExit("la verificación recién instalada falla:\n" + describe(res, 50))
    print(f"vigilante instalado en {gdir} (verificación OK en {res['seconds']} s; quick_check "
          f"{info.get('sqlite_quick_check_s')} s)")
    if test_mode or no_task:
        print("tarea programada NO modificada (modo prueba o --no-task)")
        return
    xml = _task_xml_export()
    if not (gdir / "task_original.xml").exists():
        (gdir / "task_original.xml").write_text(xml, encoding="utf-16")
    _task_create(guarded_task_xml(xml, gdir), gdir, "task_guarded.xml")
    q = _task_xml_export()
    print("tarea actualizada:" if "guard-tick" in q else "AVISO: la tarea no muestra la acción nueva:",
          re.search(r"<Exec>.*?</Exec>", q, re.S).group(0))


def uninstall(study: Path):
    _, pilot, test_mode = data_paths(study.resolve())
    gdir = pilot / "guard"
    orig = gdir / "task_original.xml"
    if test_mode or not orig.exists():
        print("nada que restaurar (modo prueba o sin task_original.xml)")
        return
    _task_create(orig.read_text(encoding="utf-16"), gdir, "task_restored.xml")
    print("acción original de la tarea restaurada; el vigilante queda en disco sin uso")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("digest")
    i = sp.add_parser("install")
    i.add_argument("--expect-digest")
    i.add_argument("--no-task", action="store_true")
    sp.add_parser("uninstall")
    v = sp.add_parser("verify")
    v.add_argument("--notify", action="store_true")
    sp.add_parser("guard-tick")
    a = ap.parse_args()
    installed = not (SELF.parent / "e3_pilot.py").exists()     # copia instalada (fuera del repositorio)
    if a.cmd == "digest":
        m = build_manifest(SELF.parent)
        print(json.dumps({"digest": m["digest"], "files": len(m["files"]), "git": m["git"],
                          "environment": m["environment"]}, indent=1))
    elif a.cmd == "install":
        if installed:
            raise SystemExit("install se ejecuta desde el repositorio, no desde la copia instalada")
        install(SELF.parent, a.expect_digest, a.no_task)
    elif a.cmd == "uninstall":
        uninstall(SELF.parent if not installed else Path(json.loads((SELF.parent / "guard.json").read_text())["study_dir"]))
    elif a.cmd == "verify":
        if installed:
            gdir = SELF.parent
        else:
            _, pilot, _ = data_paths(SELF.parent)
            gdir = pilot / "guard"
        cfg = json.loads((gdir / "guard.json").read_text(encoding="utf-8"))
        res = verify(Path(cfg["study_dir"]), gdir)
        print(json.dumps(res, indent=1, ensure_ascii=False, default=str))
        if a.notify and not res["ok"]:
            notify(Path(cfg["study_dir"]), "E3 piloto (verificación manual): el entorno NO coincide.\n" + describe(res),
                   cfg.get("test_mode"), print)
        sys.exit(0 if res["ok"] else 2)
    elif a.cmd == "guard-tick":
        if not installed:
            raise SystemExit("guard-tick se ejecuta desde la copia instalada (fuera de Dropbox)")
        try:
            rc = guard_tick(SELF.parent)
        except Exception:  # noqa: BLE001         # sin consola (pyw): que el fallo del propio vigilante quede escrito
            _append(SELF.parent / "guard_crash.jsonl", {"ts": now(), "error": traceback.format_exc()[-3000:]})
            rc = 3
        sys.exit(rc)


if __name__ == "__main__":
    main()
