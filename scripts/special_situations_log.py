"""Registro de Situaciones Especiales / alertas compuestas DISPARADAS.

check_koncorde_alerts.py dispara cada alerta una sola vez y la borra de
docs/data/koncorde_bot_alerts.json (one-shot). Hasta 2026-10-03 eso no dejaba
ningún rastro más allá del aviso de Telegram, así que no había forma de medir
si las situaciones que "se armaban" acababan funcionando. Este módulo añade
cada disparo a docs/data/special_situations_fired.jsonl; el rendimiento
posterior lo calcula scripts/screener_signal_report.js con la misma serie de
precios y la misma referencia (mediana del universo) que los filtros del
Screener.

Solo librería estándar a propósito: se puede probar sin yfinance ni dotenv
(check_koncorde_alerts.py importa requests/dotenv al cargarse).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # línea corrupta: no se pierde el resto del registro
    return out


def _fingerprint(entry: dict) -> str:
    """Identidad de un disparo: día + (id de la alerta, o ticker + condiciones)."""
    ident = entry.get("alert_id") or (
        entry.get("ticker", "") + "|" + json.dumps(entry.get("conditions", []), sort_keys=True)
    )
    return f"{entry.get('date')}|{ident}"


def build_entry(alert: dict, conditions: list[dict], description: str,
                price: float | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "fired_at": now.isoformat(timespec="seconds"),
        "ticker": alert.get("ticker"),
        "alert_id": alert.get("id"),
        "label": alert.get("label"),
        # 'situation' = creada desde portfolio.html (lleva id/label); 'kalert' =
        # creada por Telegram (/kalert o voz), formato plano antiguo.
        "kind": "situation" if (alert.get("id") or alert.get("label")) else "kalert",
        "conditions": conditions,
        "description": description,
        "price": price,
    }


def append_fired(path: Path, entries: list[dict]) -> int:
    """Añade los disparos nuevos (dedup por día + identidad). Devuelve cuántos."""
    if not entries:
        return 0
    existing = _read_jsonl(path)
    seen = {_fingerprint(e) for e in existing}
    new = []
    for e in entries:
        fp = _fingerprint(e)
        if fp in seen:
            continue
        seen.add(fp)
        new.append(e)
    if not new:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for e in new:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(new)
