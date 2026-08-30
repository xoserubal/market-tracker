"""
P1 readiness monitor — avisa por Telegram cuando los umbrales de la Hoja de
ruta consolidada (auditoría de carteras IA, firmada 2026-08-30) se cumplen,
para no tener que ir comprobando a mano si ya toca arrancar P1A/P1B/P1C/P2.

No decide nada por sí mismo — solo cuenta episodios/eventos acumulados desde
la firma y avisa. La decisión de arrancar cada experimento sigue siendo
manual (revisar el preregistro correspondiente antes de tocar código).

Umbrales vigentes (hoja de ruta v1.2):
  P1A/P1C — ámbito HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS, EARLY_ROTATION,
            MACRO_THEMATIC_BENEFICIARIES, CAVA_MACRO (MIRROR_ESPEJO excluida,
            §3). Listo cuando ≥40 cierres nuevos post-firma Y ≥30 eventos
            independientes (event_id = ticker+entry_date, §1.1).
  P1B     — ≥60 eventos de SELECT independientes post-firma, en cualquier
            cartera (§4, sin restricción de ámbito en el texto).
  P2      — ≥2 semanas de captura P0 (§6, gate simple de calendario).
  Cláusula de potencia calendario (§3, §6) — si a los 90 días de la firma
  P1A/P1C no ha alcanzado su umbral, avisa igual (para publicar el informe
  intermedio y alargar el plazo, NO para tocar parámetros).

Cada alerta se dispara UNA sola vez (dedup vía state file), igual que
duration_monitor.py / check_koncorde_alerts.py.

Uso:
    py -3 scripts/p1_readiness_monitor.py              # evalúa y avisa si toca
    py -3 scripts/p1_readiness_monitor.py --dry-run     # imprime, no envía ni persiste
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from notify_telegram import send_telegram  # reusa el sender ya existente, no reimplementa

# Los mensajes llevan emoji; consola Windows (cp1252) revienta en print() si no
# se fuerza UTF-8 — mismo incidente ya documentado y arreglado en
# duration_monitor.py / check_koncorde_alerts.py. GitHub Actions ya es UTF-8,
# esto solo importa para pruebas locales, pero tampoco debe reventar ahí.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

PICKS_JSON      = DATA / "ai_picks.json"
SHADOW_PICKS    = DATA / "shadow_picks.jsonl"
DECISION_STATE  = DATA / "ai_picks_decision_state.jsonl"
STATE_PATH      = DATA / "p1_readiness_state.json"

# Fecha de firma de la hoja de ruta = fecha en que arrancó P0 (2026-08-30).
# Todo "post-firma" de los preregistros se cuenta desde aquí, no desde el
# arranque del sistema en mayo.
FIRMA_DATE = "2026-08-30"

P1A_P1C_SCOPE = ["HIGH_CONVICTION", "CONFIRMED_FLOW_LEADERS", "EARLY_ROTATION",
                  "MACRO_THEMATIC_BENEFICIARIES", "CAVA_MACRO"]
P1A_P1C_MIN_OPS = 40
P1A_P1C_MIN_EVENTS = 30
P1B_MIN_EVENTS = 60
P2_MIN_DAYS = 14
POTENCIA_CALENDARIO_DAYS = 90


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load_state() -> dict:
    return _load(STATE_PATH)


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def days_since_firma(today: str) -> int:
    return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(FIRMA_DATE, "%Y-%m-%d")).days


def count_p1a_p1c(picks: dict) -> tuple[int, int]:
    """(cierres nuevos post-firma en el ámbito P1A/P1C, eventos independientes)."""
    closes = []
    for pf in P1A_P1C_SCOPE:
        ptf = picks.get("portfolios", {}).get(pf, {})
        for h in ptf.get("history", []):
            if h.get("event") != "close":
                continue
            close_date = h.get("close_date")
            entry_date = h.get("entry_date")
            ticker = h.get("ticker")
            if not close_date or close_date < FIRMA_DATE:
                continue
            closes.append((ticker, entry_date))
    n_ops = len(closes)
    n_events = len({f"{tk}_{ed}" for tk, ed in closes if ed})
    return n_ops, n_events


def count_p1b(picks: dict) -> int:
    """Eventos de SELECT independientes post-firma, en cualquier cartera —
    dedup por event_id = ticker+entry_date, contando posiciones abiertas Y
    cerradas (un cierre no borra el evento de haber entrado)."""
    events = set()
    for pf_name, ptf in picks.get("portfolios", {}).items():
        for pos in ptf.get("positions", []):
            ed = pos.get("entry_date")
            if ed and ed >= FIRMA_DATE:
                events.add(f"{pos.get('ticker')}_{ed}")
        for h in ptf.get("history", []):
            ed = h.get("entry_date")
            if ed and ed >= FIRMA_DATE:
                events.add(f"{h.get('ticker')}_{ed}")
    return len(events)


def evaluate(picks: dict, today: str, state: dict) -> list[str]:
    messages = []
    fired = state.setdefault("fired", {})
    d_since = days_since_firma(today)

    # P2 — gate simple de calendario
    if d_since >= P2_MIN_DAYS and "p2_ready" not in fired:
        messages.append(
            f"🟢 <b>P2 lista para arrancar</b>\n"
            f"Han pasado {d_since} días desde la firma ({FIRMA_DATE}) — ya hay "
            f"≥{P2_MIN_DAYS} días de captura P0. Revisa el preregistro de "
            f"PCS_FLOOR_FACTORIAL_V1 (§6) antes de desplegar los 4 brazos shadow."
        )
        fired["p2_ready"] = today

    # P1A/P1C — doble n (operaciones + eventos independientes)
    n_ops, n_events = count_p1a_p1c(picks)
    p1a_ready = n_ops >= P1A_P1C_MIN_OPS and n_events >= P1A_P1C_MIN_EVENTS
    if p1a_ready and "p1a_p1c_ready" not in fired:
        messages.append(
            f"🟢 <b>P1A/P1C listos para primera lectura</b>\n"
            f"{n_ops} cierres nuevos post-firma en el ámbito (HC/CFL/ER/MTB/Cava), "
            f"{n_events} eventos independientes — umbral ≥{P1A_P1C_MIN_OPS}/≥{P1A_P1C_MIN_EVENTS} cumplido. "
            f"Revisa los criterios de éxito en §3/§5 antes de decidir promoción."
        )
        fired["p1a_p1c_ready"] = today
    elif d_since >= POTENCIA_CALENDARIO_DAYS and not p1a_ready and "p1a_p1c_90day_checkpoint" not in fired:
        messages.append(
            f"🟡 <b>P1A/P1C — checkpoint de 90 días, umbral aún no cumplido</b>\n"
            f"{d_since} días desde la firma, {n_ops} cierres / {n_events} eventos "
            f"(hace falta {P1A_P1C_MIN_OPS}/{P1A_P1C_MIN_EVENTS}). Según la cláusula de "
            f"potencia calendario (§3): publica el informe intermedio y alarga el plazo — "
            f"NO toques ningún parámetro ni mires resultados por brazo todavía."
        )
        fired["p1a_p1c_90day_checkpoint"] = today

    # P1B — eventos de SELECT independientes
    n_select_events = count_p1b(picks)
    if n_select_events >= P1B_MIN_EVENTS and "p1b_ready" not in fired:
        messages.append(
            f"🟢 <b>P1B lista para primera lectura</b>\n"
            f"{n_select_events} eventos de SELECT independientes post-firma — umbral "
            f"≥{P1B_MIN_EVENTS} cumplido. Corre el test primario (Spearman "
            f"w1_ret_5d↔ret_21d, clusterizado por event_id) — recuerda: ret_21d se mide "
            f"sobre precio del ticker, nunca sobre la vida de la posición (H9)."
        )
        fired["p1b_ready"] = today

    state["last_check"] = {
        "date": today, "days_since_firma": d_since,
        "p1a_p1c_ops": n_ops, "p1a_p1c_events": n_events,
        "p1b_select_events": n_select_events,
    }
    return messages


def main():
    dry_run = "--dry-run" in sys.argv
    today = str(date.today())
    picks = _load(PICKS_JSON)
    if not picks:
        print("ai_picks.json vacío o no encontrado.")
        sys.exit(1)

    state = _load_state()
    messages = evaluate(picks, today, state)

    last = state["last_check"]
    print(f"días desde firma ({FIRMA_DATE}): {last['days_since_firma']}")
    print(f"P1A/P1C: {last['p1a_p1c_ops']} ops / {last['p1a_p1c_events']} eventos "
          f"(umbral {P1A_P1C_MIN_OPS}/{P1A_P1C_MIN_EVENTS})")
    print(f"P1B: {last['p1b_select_events']} eventos de SELECT (umbral {P1B_MIN_EVENTS})")

    if not messages:
        print("Sin umbrales nuevos cumplidos — nada que avisar.")
    else:
        token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        for msg in messages:
            if dry_run:
                print(f"[DRY RUN] Telegram:\n{msg}\n")
            elif not token or not chat_id:
                print(f"TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID no configurados, no se envía:\n{msg}",
                      file=sys.stderr)
                sys.exit(1)
            else:
                ok = send_telegram(token, chat_id, msg)
                print(f"Telegram {'enviado' if ok else 'FALLÓ'}: {msg[:60]}...")

    if not dry_run:
        _save_state(state)
    else:
        print("[DRY RUN] state no persistido.")


if __name__ == "__main__":
    main()
