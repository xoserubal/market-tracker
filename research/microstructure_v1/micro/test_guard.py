"""Bloqueo por defecto del periodo de prueba de G2A (con su embargo) para los scripts de investigación.

Cualquier código de la línea de eventos que vaya a leer o calcular algo sobre fechas debe pasar por aquí:
- `reserved(day)`: ¿la fecha está reservada?
- `allowed(days)`: quita las fechas reservadas (uso normal: líneas base, búsquedas).
- `check(days, ...)`: falla si alguna fecha está reservada, salvo `allow=True`; con `allow=True` el uso queda
  anotado en library/test_period_usage.jsonl (el registro que alimenta test_exposure_registry.csv).

El periodo reservado es el del preregistro de G2 (prueba 2022-01-03 a 2026-09-14) más el embargo de 40 sesiones
previas (desde 2021-10-29). Nada de esto cambia los resultados de G2A: solo impide tocarlos por accidente.
"""
import json
from datetime import datetime, timezone

from . import storage
from .library import EMBARGO_START, TEST_END, TEST_START

RESERVED_START, RESERVED_END = EMBARGO_START, TEST_END


class TestPeriodLocked(RuntimeError):
    pass


def reserved(day: str) -> bool:
    return RESERVED_START <= str(day)[:10] <= RESERVED_END


def allowed(days) -> list:
    return [d for d in days if not reserved(d)]


def log_usage(symbol: str, days, purpose: str, script: str):
    p = storage.root() / "library" / "test_period_usage.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(p, "a", encoding="utf-8") as f:
        for d in days:
            f.write(json.dumps({"ts": ts, "symbol": symbol, "day": d, "purpose": purpose, "script": script},
                               ensure_ascii=False) + "\n")


def check(days, *, symbol: str = "*", purpose: str = "", script: str = "", allow: bool = False) -> list:
    """Devuelve las fechas reservadas encontradas. Sin allow, lanza TestPeriodLocked si hay alguna."""
    bad = sorted({str(d)[:10] for d in days if reserved(d)})
    if bad and not allow:
        raise TestPeriodLocked(
            f"{len(bad)} fecha(s) dentro del periodo reservado de G2A ({RESERVED_START} a {RESERVED_END}), p. ej. "
            f"{bad[0]}. Está bloqueado por defecto. Si de verdad hace falta, usa la opción explícita de "
            f"desbloqueo: el acceso quedará anotado en el registro de exposiciones.")
    if bad and allow:
        log_usage(symbol, bad, purpose or "acceso explícito", script or "?")
    return bad


__all__ = ["reserved", "allowed", "check", "TestPeriodLocked", "TEST_START", "TEST_END", "RESERVED_START",
           "RESERVED_END"]
