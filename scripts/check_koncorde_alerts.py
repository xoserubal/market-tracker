"""
Evaluates user-defined Koncorde alerts (created via /kalert in Telegram, text
or voice — see scripts/telegram_portfolio_bot.py) against the latest
koncorde_calculator.py snapshot, and notifies + auto-removes the ones that fire.

Reads:
  docs/data/koncorde_bot_alerts.json   (alerts created by the bot; separate file
                                          from bot_alerts.json — see the comment
                                          next to _KONC_ALERTS_PATH in
                                          telegram_portfolio_bot.py for why)
  docs/data/koncorde_data.json         (konc_* fields per ticker, latest run)

Writes:
  docs/data/koncorde_bot_alerts.json   (fired alerts removed — one-shot, same
                                          UX as the existing price alerts)

Koncorde only changes when koncorde_calculator.py runs (2x/day pipeline +
the 2h retry workflow) — no point checking more often than that, so this
runs as a pipeline step, not in the bot's continuous polling loop.

Usage:
    py -3 scripts/check_koncorde_alerts.py
    py -3 scripts/check_koncorde_alerts.py --dry-run
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Alert messages contain emoji; Windows consoles default to cp1252 and crash on
# print() otherwise. GitHub Actions (ubuntu-latest) is already UTF-8, so this
# only matters for local testing, but it must not crash there either.
# Same fix already applied in duration_monitor.py.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
from koncorde_alert_conditions import describe, evaluate

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

ALERTS_PATH = ROOT / "docs" / "data" / "koncorde_bot_alerts.json"
KONC_PATH   = ROOT / "docs" / "data" / "koncorde_data.json"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to read {path}: {exc}")
        return default


def _send_telegram(text: str) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print(f"TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID no configurados, no se envía: {text}",
              file=sys.stderr)
        sys.exit(1)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if not r.ok:
            print(f"Telegram error {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as exc:
        print(f"Telegram send failed: {exc}")
        return False


def run(dry_run: bool = False) -> None:
    alerts = _load_json(ALERTS_PATH, [])
    if not alerts:
        print("No hay alertas de Koncorde activas.")
        return

    konc_tickers = _load_json(KONC_PATH, {}).get("tickers", {})

    fired: list[dict]   = []
    pending: list[dict] = []

    for a in alerts:
        ticker    = a.get("ticker", "")
        timeframe = a.get("timeframe", "")
        condition = a.get("condition", "")
        ticker_data = konc_tickers.get(ticker)

        if ticker_data is None:
            pending.append(a)
            continue

        try:
            result = evaluate(ticker_data, timeframe, condition)
        except ValueError as exc:
            print(f"Alerta inválida descartada ({ticker}/{timeframe}/{condition}): {exc}")
            continue  # malformed entry, drop it rather than loop on it forever

        if result is True:
            fired.append(a)
        else:
            pending.append(a)  # False, or None (no data yet for this field)

    for a in fired:
        desc = describe(a.get("ticker", "?"), a.get("timeframe", "?"), a.get("condition", "?"))
        msg  = f"🔮 <b>Alerta Koncorde:</b> {desc}"
        raw  = a.get("raw_request", "")
        if raw:
            msg += f"\n<i>({raw})</i>"
        print(f"FIRED: {desc}")
        if not dry_run:
            _send_telegram(msg)

    if fired and not dry_run:
        ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALERTS_PATH.write_text(json.dumps(pending, indent=2), encoding="utf-8")

    print(f"Koncorde alerts: {len(alerts)} evaluada(s), {len(fired)} disparada(s), "
          f"{len(pending)} siguen activas.")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
