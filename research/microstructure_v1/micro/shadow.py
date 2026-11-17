"""Captura prospectiva en sombra — CONSTRUIDA PERO DESACTIVADA.

Solo corre si shadow_config.json tiene "enabled": true (requiere autorización expresa) o con --dry-run, que
registra la selección del día sin descargar nada. No hay tarea programada ni servicio: se lanza a mano.

Por cada sesión cerrada:
 1. Comprueba que han pasado >= 20 min desde el cierre (plan Basic: nada de los últimos 15 min).
 2. Universo elegible = mismas reglas que el retrospectivo (miembros actuales del S&P 500 + EE. UU. del proyecto).
 3. REGISTRA la selección (semilla, fecha, hash del universo, probabilidad de inclusión) ANTES de descargar.
 4. Descarga barras 1 min del universo y trades de la muestra (download_unit: idempotente, manifiesto, calidad).
"""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import calendar, config, sampling, storage
from .download import config_for, download_unit

CONFIG_PATH = config.STUDY_DIR / "shadow_config.json"
DEFAULT = {"enabled": False, "master_seed": 20261115, "k_trades": 50, "rules_version": "shadow-v1",
           "universe": "sp500_current+project_us", "min_minutes_after_close": 20}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT, indent=1), encoding="utf-8")
    return {**DEFAULT, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}


def eligible_universe() -> list:
    ref = storage.root() / "reference" / "universe_intervals.parquet"
    u = pd.read_parquet(ref)
    last = u["end"].max()
    current = u[(u["source"] == "sp500") & (u["end"] == last)]["symbol"].tolist()
    proj = u[u["source"] == "project"]["symbol"].tolist()
    return sorted(set(current) | set(proj))


def run(day: str, provider=None, dry_run: bool = True) -> dict:
    cfg = load_config()
    if not cfg["enabled"] and not dry_run:
        raise SystemExit("Captura sombra DESACTIVADA (shadow_config.json enabled=false). Requiere autorización.")
    if not calendar.is_trading_day(day):
        return {"date": day, "status": "not_trading_day"}
    _, close = calendar.session_bounds(day, "regular")
    if datetime.now(timezone.utc) < close.to_pydatetime() + timedelta(minutes=cfg["min_minutes_after_close"]):
        return {"date": day, "status": "too_early"}
    elig = eligible_universe()
    sel = sampling.shadow_sample(elig, day, cfg["master_seed"], cfg["k_trades"])
    sel.update({"rules_version": cfg["rules_version"], "master_seed": cfg["master_seed"], "dry_run": dry_run,
                "registered_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "code_version": config.code_version()})
    d = storage.root() / "samples" / "shadow"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{day}.json"
    if f.exists() and not dry_run:
        prev = json.loads(f.read_text(encoding="utf-8"))
        if prev["selected"] != sel["selected"]:
            raise RuntimeError("La selección registrada para este día no coincide: no se sobrescribe.")
    elif not dry_run:
        f.write_text(json.dumps(sel, indent=1), encoding="utf-8")   # registro ANTES de descargar
    if dry_run:
        return {"status": "dry_run", **sel}
    results = []
    for s in elig:
        results.append(download_unit(provider, "bars", s, day, cfg=config_for("bars", bars_window="day")))
    for s in sel["selected"]:
        results.append(download_unit(provider, "trades", s, day, cfg=config_for("trades")))
    return {"status": "done", "units": len(results)}
