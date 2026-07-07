"""
Duration Stress Monitor — BOJ/Treasury Supply Thesis (pipeline alert script)

Evaluates the same A/B/C/D state machine shown live in duration.html, but from
the GitHub Actions pipeline (2x/day), and sends a Telegram alert only on a NEW
phase transition or a NEW critical-trigger crossing — never on every run while
a condition merely persists.

Trigger levels are intentionally duplicated as constants in duration.html (JS,
`LEVELS`) and here (Python, `LEVELS`) — same precedent as calcCMF being
duplicated in server.js and Python elsewhere in this repo. Keep both in sync
if levels change.

Scope: only the metrics that feed the state machine (TLT, 10Y yield, HY
spread, VIX, MOVE) are fetched here. Treasury auction data and the Japan/gold
causality badges are live-display-only in duration.html (via server.js
proxies) and do not drive alerts in v1 — no critical trigger in the approved
plan depends on them.

State machine (invalidation checked FIRST, per user correction — a clear
reversal must never be masked by a stale confirmation reading):
    if invalidation:                Phase D — Invalidation
    elif core_break and confirmation: Phase C — Systemic Confirmation
    elif pressure:                   Phase B — Duration Pressure
    else:                            Phase A — Watch

Alerts:
  - Phase transition (any direction) — always, except on the very first ever
    run (bootstrap), where only the baseline state is recorded.
  - Critical trigger crossings (core_break_10y, core_break_tlt,
    invalidation_tlt, invalidation_10y) — deduped by condition_id + crossed
    direction, so a persisting condition is not re-alerted on every pipeline
    run. Context metrics (VIX/HY/MOVE individually, USDJPY, gold) never alert
    on their own — they only feed `confirmation`.

Dedup state: docs/data/duration_monitor_state.json

Usage:
  py -3 scripts/duration_monitor.py                    # evaluate + alert on new crossings
  py -3 scripts/duration_monitor.py --dry-run           # print instead of sending Telegram, state not persisted
  py -3 scripts/duration_monitor.py --alert-on-initial  # also alert on conditions already active on the bootstrap run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

# Alert messages contain emoji; Windows consoles default to cp1252 and crash on
# print() otherwise. GitHub Actions (ubuntu-latest) is already UTF-8, so this
# only matters for local testing, but it must not crash there either.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).parent))
from notify_telegram import send_telegram  # noqa: E402

DATA = ROOT / "docs" / "data"
STATE_PATH = DATA / "duration_monitor_state.json"

FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ── Trigger levels — mirror duration.html's `LEVELS` object exactly ─────────
LEVELS = {
    "core_break_10y": 4.60, "core_break_tlt": 84.0,
    "confirm_hy_bps": 300.0, "confirm_vix": 20.0, "confirm_move": 120.0,
    "pressure_tlt": 84.8, "pressure_10y": 4.55,
    "invalid_tlt": 86.5, "invalid_10y": 4.55,
}

PHASE_LABELS = {
    "A": "Fase A — Watch",
    "B": "Fase B — Duration Pressure",
    "C": "Fase C — Systemic Confirmation",
    "D": "Fase D — Invalidation",
}


def _fred_latest(series_id: str) -> tuple[float | None, str | None]:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise EnvironmentError("FRED_API_KEY no configurada (.env local o GitHub Secrets)")
    params = {
        "series_id": series_id, "api_key": key, "file_type": "json",
        "sort_order": "desc", "limit": 5,
    }
    r = requests.get(FRED_API_BASE, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "observations" not in data:
        raise ValueError(f"Respuesta inesperada de FRED para {series_id}: {data.get('error_message', data)}")
    obs = [o for o in data["observations"] if o["value"] != "."]
    if not obs:
        return None, None
    return float(obs[0]["value"]), obs[0]["date"]


def _yfinance_price(ticker: str) -> float | None:
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="5d", auto_adjust=True)
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as exc:
        print(f"  {ticker}: fetch failed ({exc})", file=sys.stderr)
        return None


def fetch_metrics() -> dict:
    tlt = _yfinance_price("TLT")
    vix = _yfinance_price("^VIX")
    move = _yfinance_price("^MOVE")  # best-effort — degrades gracefully if Yahoo lacks this ticker
    y10, y10_date = _fred_latest("DGS10")
    hy, hy_date = _fred_latest("BAMLH0A0HYM2")
    hy_bps = hy * 100 if hy is not None else None  # BAMLH0A0HYM2 comes in percentage points, not bps
    return {
        "tlt": tlt, "vix": vix, "move": move,
        "y10": y10, "y10_date": y10_date,
        "hy_bps": hy_bps, "hy_date": hy_date,
    }


def compute_phase(m: dict) -> tuple[str, dict]:
    tlt, y10 = m["tlt"], m["y10"]
    if tlt is None or y10 is None:
        return "A", {"invalidation": None, "core_break": None, "confirmation": None, "pressure": None}

    invalidation = tlt > LEVELS["invalid_tlt"] and y10 < LEVELS["invalid_10y"]
    core_break = y10 > LEVELS["core_break_10y"] and tlt < LEVELS["core_break_tlt"]
    confirmation = (
        (m["hy_bps"] is not None and m["hy_bps"] > LEVELS["confirm_hy_bps"])
        or (m["vix"] is not None and m["vix"] > LEVELS["confirm_vix"])
        or (m["move"] is not None and m["move"] > LEVELS["confirm_move"])
    )
    pressure = tlt < LEVELS["pressure_tlt"] or y10 > LEVELS["pressure_10y"]

    if invalidation:
        phase = "D"
    elif core_break and confirmation:
        phase = "C"
    elif pressure:
        phase = "B"
    else:
        phase = "A"
    return phase, {
        "invalidation": invalidation, "core_break": core_break,
        "confirmation": confirmation, "pressure": pressure,
    }


def critical_conditions(m: dict) -> dict:
    """Only the conditions that DEFINE phase transitions — not context metrics."""
    tlt, y10 = m["tlt"], m["y10"]
    if tlt is None or y10 is None:
        return {}
    return {
        "core_break_10y":   y10 > LEVELS["core_break_10y"],
        "core_break_tlt":   tlt < LEVELS["core_break_tlt"],
        "invalidation_tlt": tlt > LEVELS["invalid_tlt"],
        "invalidation_10y": y10 < LEVELS["invalid_10y"],
    }


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"phase": None, "conditions": {}}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def evaluate(state: dict, phase: str, conditions: dict, today: str,
             is_bootstrap: bool, alert_on_initial: bool) -> list[str]:
    """Mutates `state` in place; returns Telegram message lines to send."""
    messages: list[str] = []

    prev_phase = state.get("phase")
    if is_bootstrap:
        if alert_on_initial:
            messages.append(f"🔧 Duration Monitor bootstrap — fase inicial: {PHASE_LABELS[phase]}")
    elif prev_phase != phase:
        messages.append(f"🔔 <b>Duration Monitor</b>: transición de fase {prev_phase or '—'} → {phase}\n{PHASE_LABELS[phase]}")
    state["phase"] = phase

    prev_conditions: dict = state.get("conditions", {})
    new_conditions: dict = {}
    for condition_id, is_active in conditions.items():
        direction = "above" if is_active else "below"
        prev_entry = prev_conditions.get(condition_id)
        prev_direction = prev_entry.get("direction") if prev_entry else None

        if prev_direction is None:
            if is_bootstrap:
                if alert_on_initial and is_active:
                    messages.append(f"⚠️ Duration Monitor: {condition_id} ya activo en el arranque ({direction})")
            elif is_active:
                messages.append(f"⚠️ <b>Duration Monitor</b>: {condition_id} cruzado ({direction})")
        elif prev_direction != direction:
            messages.append(f"⚠️ <b>Duration Monitor</b>: {condition_id} cruzado ({direction}, antes {prev_direction})")

        new_conditions[condition_id] = {"direction": direction, "date": today}
    state["conditions"] = new_conditions

    return messages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print alerts instead of sending Telegram; state not persisted")
    parser.add_argument("--alert-on-initial", action="store_true", help="Also alert on conditions already active on the bootstrap run")
    args = parser.parse_args()

    is_bootstrap = not STATE_PATH.exists()
    state = _load_state()

    print("Fetching TLT/VIX/MOVE (yfinance) + DGS10/HY spread (FRED)...")
    metrics = fetch_metrics()
    phase, checks = compute_phase(metrics)
    conditions = critical_conditions(metrics)
    today = str(date.today())

    print(f"TLT={metrics['tlt']} VIX={metrics['vix']} MOVE={metrics['move']} "
          f"10Y={metrics['y10']}% ({metrics['y10_date']}) HY={metrics['hy_bps']}bps ({metrics['hy_date']})")
    print(f"-> {PHASE_LABELS[phase]} | checks={checks}")

    messages = evaluate(state, phase, conditions, today, is_bootstrap, args.alert_on_initial)

    if not messages:
        print("Sin cambios de fase ni cruces nuevos — nada que alertar.")
    else:
        token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        for msg in messages:
            if args.dry_run:
                print(f"[DRY RUN] Telegram: {msg}")
            elif not token or not chat_id:
                print(f"TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID no configurados, no se envía: {msg}", file=sys.stderr)
                sys.exit(1)
            else:
                ok = send_telegram(token, chat_id, msg)
                print(f"Telegram {'enviado' if ok else 'FALLÓ'}: {msg}")

    if args.dry_run:
        print("[DRY RUN] state no persistido.")
    else:
        _save_state(state)


if __name__ == "__main__":
    main()
