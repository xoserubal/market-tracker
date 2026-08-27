"""
Evaluates user-defined alerts — both the simple single-condition Koncorde
alerts created via /kalert in Telegram (text or voice — see
scripts/telegram_portfolio_bot.py) and the composite multi-condition
"situaciones especiales" (theses) created from the Portfolio Tracker web UI —
against the latest data, and notifies + auto-removes the ones that fire.

Generalized 2026-08-26 from a Koncorde-only single-condition evaluator to a
composite AND-over-typed-conditions one (see koncorde_alert_conditions.py's
`get_conditions`/`evaluate_conditions`/`evaluate_single_condition`) — same
storage file, same evaluator entry point, one alert can now require any mix
of Koncorde state, Flow Score crossing, and custom ticker-ratio trend
conditions simultaneously. Old-format rows (flat ticker/timeframe/condition)
keep working unmodified via the read-time compatibility shim.

Reads:
  docs/data/koncorde_bot_alerts.json         (alerts; both formats, see above)
  docs/data/koncorde_data.json               (konc_* fields per ticker, latest run)
  docs/data/portfolio_daily_snapshot.jsonl   (flowScore history — only read if
                                                any alert has a "flow" condition)
  live yfinance fetch via ratio_signal.py    (only for alerts with a "ratio" condition)

Writes:
  docs/data/koncorde_bot_alerts.json   (fired alerts removed — one-shot, same
                                          UX as the existing price alerts)

Koncorde only changes when koncorde_calculator.py runs (2x/day pipeline +
the 2h retry workflow); portfolio_daily_snapshot.jsonl and ratios are also
at most daily-granularity data — no point checking more often than that, so
this runs as a pipeline step, not in the bot's continuous polling loop.

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
from koncorde_alert_conditions import describe_conditions, evaluate_conditions, get_conditions
from ratio_signal import fetch_ratio_trend

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

ALERTS_PATH   = ROOT / "docs" / "data" / "koncorde_bot_alerts.json"
KONC_PATH     = ROOT / "docs" / "data" / "koncorde_data.json"
SNAPSHOT_PATH = ROOT / "docs" / "data" / "portfolio_daily_snapshot.jsonl"


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


def _load_flow_rows_by_ticker() -> dict[str, list[dict]]:
    """Last 2 rows (by date) per ticker from portfolio_daily_snapshot.jsonl —
    all that evaluate_flow() ever needs. Reads the whole file once per run
    (only called at all if some alert actually has a "flow" condition)."""
    if not SNAPSHOT_PATH.exists():
        return {}
    by_ticker: dict[str, list[dict]] = {}
    with SNAPSHOT_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = row.get("ticker")
            if not t:
                continue
            by_ticker.setdefault(t, []).append({"date": row.get("date"), "flowScore": row.get("flowScore")})
    for t, rows in by_ticker.items():
        rows.sort(key=lambda r: r["date"] or "")
        by_ticker[t] = rows[-2:]
    return by_ticker


def run(dry_run: bool = False) -> None:
    alerts = _load_json(ALERTS_PATH, [])
    if not alerts:
        print("No hay alertas activas.")
        return

    konc_tickers = _load_json(KONC_PATH, {}).get("tickers", {})

    # Only pay for flow-snapshot / ratio-fetch work if some alert actually needs it.
    all_conditions = [c for a in alerts for c in get_conditions(a)]
    needs_flow = any(c.get("type") == "flow" for c in all_conditions)
    flow_rows_by_ticker = _load_flow_rows_by_ticker() if needs_flow else {}

    ratio_trend_cache: dict[tuple[str, str], dict | None] = {}

    def _cached_ratio_trend(ticker_a: str, ticker_b: str) -> dict | None:
        key = (ticker_a, ticker_b)
        if key not in ratio_trend_cache:
            ratio_trend_cache[key] = fetch_ratio_trend(ticker_a, ticker_b)
        return ratio_trend_cache[key]

    fired: list[dict]   = []
    pending: list[dict] = []

    for a in alerts:
        ticker = a.get("ticker", "")
        try:
            conditions = get_conditions(a)
        except KeyError as exc:
            print(f"Alerta inválida descartada ({ticker}): falta campo {exc}")
            continue  # malformed entry, drop it rather than loop on it forever

        ratio_pairs = a.get("ratio_pairs", [])
        ratio_trends = {
            rp["key"]: _cached_ratio_trend(ticker, rp["other_ticker"])
            for rp in ratio_pairs
        }
        ctx = {
            "koncorde_ticker_data": konc_tickers.get(ticker),
            "flow_rows": flow_rows_by_ticker.get(ticker, []),
            "ratio_trends": ratio_trends,
        }

        try:
            result = evaluate_conditions(conditions, ctx)
        except ValueError as exc:
            print(f"Alerta inválida descartada ({ticker}): {exc}")
            continue

        if result is True:
            fired.append(a)
        else:
            pending.append(a)  # False, or None (no data yet for some condition)

    for a in fired:
        ticker = a.get("ticker", "?")
        desc = describe_conditions(ticker, get_conditions(a))
        label = a.get("label")
        title = f"🔮 <b>Alerta:</b> {label}" if label else "🔮 <b>Alerta Koncorde:</b>"
        msg  = f"{title}\n{desc}"
        raw  = a.get("raw_request", "")
        if raw:
            msg += f"\n<i>({raw})</i>"
        print(f"FIRED: {desc}")
        if not dry_run:
            _send_telegram(msg)

    if fired and not dry_run:
        ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALERTS_PATH.write_text(json.dumps(pending, indent=2), encoding="utf-8")

    print(f"Alertas: {len(alerts)} evaluada(s), {len(fired)} disparada(s), "
          f"{len(pending)} siguen activas.")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
