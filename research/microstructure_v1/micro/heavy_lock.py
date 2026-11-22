"""Cerrojo de procesos intensivos (2026-11-22): evita que el piloto E3 y un cálculo pesado (perfiles VP2, recálculos)
corran a la vez. No bloquea: cada proceso comprueba y decide (el piloto sale y lo reintenta en su siguiente disparo)."""
import json
import os
from datetime import datetime, timezone

from . import storage


def _path():
    p = storage.root() / "results" / "_heavy.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def holder():
    """Proceso vivo que tiene el cerrojo, o None (un cerrojo de un proceso muerto se ignora)."""
    p = _path()
    if not p.exists():
        return None
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
        import psutil
        if psutil.pid_exists(int(info["pid"])):
            return info
    except Exception:  # noqa: BLE001
        return None
    return None


def e3_running():
    p = storage.root() / "results" / "e3" / "run.lock"
    if not p.exists():
        return None
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
        import psutil
        return info if psutil.pid_exists(int(info["pid"])) else None
    except Exception:  # noqa: BLE001
        return None


class HeavyJob:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        h = holder()
        if h and h.get("pid") != os.getpid():
            raise RuntimeError(f"otro proceso intensivo en marcha: {h}")
        e = e3_running()
        if e:
            raise RuntimeError(f"hay una pasada E3 en marcha: {e}")
        _path().write_text(json.dumps({"pid": os.getpid(), "job": self.name,
                                       "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                           encoding="utf-8")
        return self

    def __exit__(self, *a):
        try:
            if json.loads(_path().read_text(encoding="utf-8")).get("pid") == os.getpid():
                _path().unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return False
