"""
Telegram Notifier — AI Picks Lab

Reads today's run results from ai_model_test_summary.jsonl and ai_picks.json.
Sends a Telegram message when new picks are applied or positions are closed today.
Silent if neither event occurred.

Env vars (GitHub Secrets):
  TELEGRAM_BOT_TOKEN   — bot token from @BotFather
  TELEGRAM_CHAT_ID     — your personal chat_id
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "docs" / "data"

PORTFOLIO_LABELS = {
    "HIGH_CONVICTION":              "Alta Conviccion",
    "CONFIRMED_FLOW_LEADERS":       "Flujo Confirmado",
    "EARLY_ROTATION":               "Rot. Temprana",
    "MACRO_THEMATIC_BENEFICIARIES": "Macro Tematico",
    "REJECTED_HIGH_SCORE":          "Rechazados (control)",
}

CONVICTION_EMOJI = {"high": "🟢", "medium": "🟡", "low": "⚪"}


def _load(name: str) -> dict | list:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_jsonl(name: str) -> list[dict]:
    p = DATA / name
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if not r.ok:
            print(f"Telegram error {r.status_code}: {r.text[:200]}")
        return r.ok
    except Exception as exc:
        print(f"Telegram request failed: {exc}")
        return False


def _find_closed_today(picks: dict, today: str) -> list[dict]:
    """Returns history events with event=close and close_date=today, with _ptf added."""
    closed = []
    for ptf_id, ptf in picks.get("portfolios", {}).items():
        for ev in ptf.get("history", []):
            if ev.get("event") == "close" and ev.get("close_date") == today:
                closed.append({**ev, "_ptf": ptf_id})
    return closed


def _pnl_str(entry: float | None, close: float | None) -> str:
    """Returns formatted P&L string like '+12.3%' or '' if prices unavailable."""
    if not entry or not close or entry == 0:
        return ""
    pnl = (close - entry) / entry * 100
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:.1f}%"


def build_message(today: str, picks: dict, summary_rows: list[dict]) -> str | None:
    """
    Returns a formatted HTML message if there are new picks or closures today, else None.
    """
    portfolios = picks.get("portfolios", {})

    # Collect all positions opened today
    new_positions: list[dict] = []
    for ptf_id, ptf in portfolios.items():
        for pos in ptf.get("positions", []):
            if pos.get("entry_date") == today:
                new_positions.append({**pos, "_ptf": ptf_id})

    closed_today = _find_closed_today(picks, today)

    if not new_positions and not closed_today:
        return None

    # Find today's active model run (first successful one)
    today_rows = [r for r in summary_rows if r.get("date") == today and r.get("json_valid")]
    active_row = next(
        (r for r in today_rows if not r.get("forced_run")), None
    ) or (today_rows[0] if today_rows else None)

    lines: list[str] = []
    lines.append("<b>AI Picks Lab</b>")
    lines.append("")

    # Model summary line
    if active_row:
        model = (active_row.get("model") or "").replace("anthropic/", "").replace("x-ai/", "")
        q     = active_row.get("quality_score", "—")
        cost  = active_row.get("cost_usd", 0)
        lat   = active_row.get("latency_ms", 0)
        lines.append(
            f"Modelo: <b>{model}</b>  Q={q}/100  "
            f"${cost:.4f}  {lat/1000:.0f}s"
        )
        lines.append("")

    # Macro context from picks
    review = picks.get("last_ai_review", {})
    if review.get("market_read"):
        lines.append(f"<i>{review['market_read']}</i>")
        lines.append("")

    # New positions grouped by portfolio
    if new_positions:
        lines.append("<b>Nuevas posiciones</b>")
        by_ptf: dict[str, list] = {}
        for p in new_positions:
            by_ptf.setdefault(p["_ptf"], []).append(p)

        for ptf_id, positions in by_ptf.items():
            label = PORTFOLIO_LABELS.get(ptf_id, ptf_id)
            lines.append(f"\n<b>{label}</b>")
            for p in positions:
                emoji    = CONVICTION_EMOJI.get(p.get("conviction", ""), "⚪")
                pcs      = p.get("entry_pcs")
                pcs_str  = f"PCS {pcs}" if pcs else ""
                size     = p.get("size_pct")
                size_str = f"{size}%" if size else ""
                meta     = " | ".join(x for x in [pcs_str, size_str] if x)
                line     = f"{emoji} <b>{p['ticker']}</b>"
                if meta:
                    line += f"  {meta}"
                lines.append(line)
                if p.get("rationale"):
                    lines.append(f"  <i>{p['rationale']}</i>")
        lines.append("")

    # Closed positions grouped by portfolio
    if closed_today:
        lines.append("<b>Posiciones cerradas</b>")
        by_ptf_closed: dict[str, list] = {}
        for c in closed_today:
            by_ptf_closed.setdefault(c["_ptf"], []).append(c)

        for ptf_id, positions in by_ptf_closed.items():
            label = PORTFOLIO_LABELS.get(ptf_id, ptf_id)
            lines.append(f"\n<b>{label}</b>")
            for p in positions:
                pnl = _pnl_str(p.get("entry_price"), p.get("close_price"))
                line = f"🔴 <b>{p['ticker']}</b>"
                if pnl:
                    line += f"  {pnl}"
                entry_date = p.get("entry_date", "")
                if entry_date:
                    line += f"  (desde {entry_date})"
                lines.append(line)
                if p.get("close_reason"):
                    lines.append(f"  <i>{p['close_reason']}</i>")
        lines.append("")

    lines.append(f"<i>{today} — AI Picks Lab</i>")
    return "\n".join(lines)


def check_reminders(token: str, chat_id: str, today: str) -> None:
    """Sends a reminder message if today matches any scheduled reminder date."""
    reminders_path = DATA / "reminders.json"
    if not reminders_path.exists():
        return
    try:
        reminders = json.loads(reminders_path.read_text(encoding="utf-8"))
    except Exception:
        return

    for reminder in reminders:
        if reminder.get("date") == today and reminder.get("message"):
            print(f"Sending reminder: {reminder.get('id', '?')}")
            ok = send_telegram(token, chat_id, reminder["message"])
            print("Reminder OK" if ok else "Reminder FAILED")


def run() -> None:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping notification")
        return

    today        = str(date.today())
    picks        = _load("ai_picks.json")
    summary_rows = _load_jsonl("ai_model_test_summary.jsonl")

    check_reminders(token, chat_id, today)

    if not isinstance(picks, dict):
        print("ai_picks.json not found or invalid — skipping")
        return

    msg = build_message(today, picks, summary_rows)
    if msg is None:
        print(f"No new picks today ({today}) — no notification sent")
        return

    print("Sending Telegram notification...")
    ok = send_telegram(token, chat_id, msg)
    print("OK" if ok else "FAILED")


if __name__ == "__main__":
    if "--test" in sys.argv:
        token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            print("Pon TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env")
            sys.exit(1)
        msg = (
            "<b>AI Picks Lab — TEST</b>\n\n"
            "Bot configurado correctamente.\n"
            "Recibiras avisos cuando haya picks nuevos o cierres de posicion.\n\n"
            "<b>Nuevas posiciones</b>\n\n"
            "<b>Alta Conviccion</b>\n"
            "🟢 <b>NVDA</b>  PCS 81.5 | 10%\n"
            "  <i>Ejemplo de notificacion real</i>\n\n"
            "<b>Posiciones cerradas</b>\n\n"
            "<b>Flujo Confirmado</b>\n"
            "🔴 <b>MARA</b>  +14.2%  (desde 2026-05-20)\n"
            "  <i>Ejemplo de cierre: rot_score caido a 2</i>"
        )
        ok = send_telegram(token, chat_id, msg)
        print("Mensaje de test enviado OK" if ok else "Error al enviar")
    else:
        run()
