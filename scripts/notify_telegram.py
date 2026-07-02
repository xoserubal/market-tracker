"""
Telegram Notifier — AI Picks Lab (fallback)

Primary notifications are sent directly from paper_trading.py when positions change.
This script acts as a fallback: it detects any positions not yet notified (using a
persistent state file) and sends them, regardless of when they were opened/closed.

State file: docs/data/notify_state.json
  - tracks every ticker+portfolio+event already sent so there are no duplicates

Env vars (GitHub Secrets):
  TELEGRAM_BOT_TOKEN   — bot token from @BotFather
  TELEGRAM_CHAT_ID     — your personal chat_id
"""
from __future__ import annotations

import html
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DATA       = ROOT / "docs" / "data"
STATE_FILE = DATA / "notify_state.json"


def _load_state() -> dict:
    """Load the set of already-notified events from disk."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"opens": [], "closes": []}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _open_key(ptf_id: str, ticker: str, entry_date: str) -> str:
    return f"{ptf_id}:{ticker}:{entry_date}"


def _close_key(ptf_id: str, ticker: str, close_date: str) -> str:
    return f"{ptf_id}:{ticker}:close:{close_date}"

PORTFOLIO_LABELS = {
    "HIGH_CONVICTION":              "Alta Conviccion",
    "CONFIRMED_FLOW_LEADERS":       "Flujo Confirmado",
    "EARLY_ROTATION":               "Rot. Temprana",
    "MACRO_THEMATIC_BENEFICIARIES": "Macro Tematico",
    "REJECTED_HIGH_SCORE":          "Rechazados (control)",
    "MIMO_SHADOW":                  "Mimo Shadow",
    "MIRROR_ESPEJO":                "Espejo (Grok)",
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


def _find_unnotified(picks: dict, state: dict) -> tuple[list[dict], list[dict]]:
    """
    Returns (new_opens, new_closes) that are NOT yet in the state file.
    Checks all open positions and all history close events — not just today's.
    """
    notified_opens  = set(state.get("opens", []))
    notified_closes = set(state.get("closes", []))

    new_opens: list[dict]  = []
    new_closes: list[dict] = []

    for ptf_id, ptf in picks.get("portfolios", {}).items():
        for pos in ptf.get("positions", []):
            key = _open_key(ptf_id, pos["ticker"], pos.get("entry_date", ""))
            if key not in notified_opens:
                new_opens.append({**pos, "_ptf": ptf_id, "_key": key})

        for ev in ptf.get("history", []):
            if ev.get("event") != "close":
                continue
            key = _close_key(ptf_id, ev["ticker"], ev.get("close_date", ""))
            if key not in notified_closes:
                new_closes.append({**ev, "_ptf": ptf_id, "_key": key})

    return new_opens, new_closes


def _pnl_str(entry: float | None, close: float | None) -> str:
    """Returns formatted P&L string like '+12.3%' or '' if prices unavailable."""
    if not entry or not close or entry == 0:
        return ""
    pnl = (close - entry) / entry * 100
    sign = "+" if pnl >= 0 else ""
    return f"{sign}{pnl:.1f}%"


def build_message(
    today: str,
    new_opens: list[dict],
    new_closes: list[dict],
    summary_rows: list[dict],
    picks: dict,
) -> str | None:
    """
    Returns a formatted HTML message for any un-notified opens/closes, else None.
    Uses state-based detection instead of entry_date == today.
    """
    if not new_opens and not new_closes:
        return None

    # Find the most recent active model run for context
    recent_rows = sorted(
        [r for r in summary_rows if r.get("json_valid")],
        key=lambda r: r.get("date", ""),
        reverse=True,
    )
    active_row = next((r for r in recent_rows if not r.get("forced_run")), None) or (
        recent_rows[0] if recent_rows else None
    )

    lines: list[str] = ["<b>AI Picks Lab</b> — aviso pendiente", ""]

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

    review = picks.get("last_ai_review", {})
    if review.get("market_read"):
        lines.append(f"<i>{html.escape(review['market_read'])}</i>")
        lines.append("")

    if new_opens:
        lines.append("<b>Nuevas posiciones</b>")
        by_ptf: dict[str, list] = {}
        for p in new_opens:
            by_ptf.setdefault(p["_ptf"], []).append(p)
        for ptf_id, positions in by_ptf.items():
            label = PORTFOLIO_LABELS.get(ptf_id, ptf_id)
            lines.append(f"\n<b>{label}</b>")
            for p in positions:
                emoji    = CONVICTION_EMOJI.get(p.get("conviction", ""), "⚪")
                pcs_str  = f"PCS {p['entry_pcs']}" if p.get("entry_pcs") else ""
                size_str = f"{p['size_pct']}%" if p.get("size_pct") else ""
                meta     = " | ".join(x for x in [pcs_str, size_str] if x)
                line     = f"{emoji} <b>{p['ticker']}</b>"
                if meta:
                    line += f"  {meta}"
                if p.get("entry_date") and p["entry_date"] != today:
                    line += f"  <i>(entrada {p['entry_date']})</i>"
                lines.append(line)
                if p.get("rationale"):
                    lines.append(f"  <i>{html.escape(p['rationale'])}</i>")
        lines.append("")

    if new_closes:
        lines.append("<b>Posiciones cerradas</b>")
        by_ptf_closed: dict[str, list] = {}
        for c in new_closes:
            by_ptf_closed.setdefault(c["_ptf"], []).append(c)
        for ptf_id, positions in by_ptf_closed.items():
            label = PORTFOLIO_LABELS.get(ptf_id, ptf_id)
            lines.append(f"\n<b>{label}</b>")
            for p in positions:
                pnl  = _pnl_str(p.get("entry_price"), p.get("close_price"))
                line = f"🔴 <b>{p['ticker']}</b>"
                if pnl:
                    line += f"  {pnl}"
                if p.get("entry_date"):
                    line += f"  (desde {p['entry_date']})"
                lines.append(line)
                if p.get("close_reason"):
                    lines.append(f"  <i>{html.escape(p['close_reason'])}</i>")
        lines.append("")

    lines.append(f"<i>{today} — AI Picks Lab (fallback notifier)</i>")
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
        # Exit non-zero so the GitHub Actions step shows as failed (visible in the
        # Actions tab) instead of silently missing notifications for weeks. The
        # workflow step uses continue-on-error so this never blocks later steps
        # (Step 12 Telegram commands, Commit updated data).
        sys.exit(1)

    today        = str(date.today())
    picks        = _load("ai_picks.json")
    summary_rows = _load_jsonl("ai_model_test_summary.jsonl")

    check_reminders(token, chat_id, today)

    if not isinstance(picks, dict):
        print("ai_picks.json not found or invalid — skipping")
        return

    state = _load_state()
    new_opens, new_closes = _find_unnotified(picks, state)

    if not new_opens and not new_closes:
        print("No unnotified positions — no fallback notification needed")
        return

    print(
        f"Fallback: {len(new_opens)} open(s), {len(new_closes)} close(s) not yet notified"
    )
    msg = build_message(today, new_opens, new_closes, summary_rows, picks)
    if msg is None:
        return

    ok = send_telegram(token, chat_id, msg)
    print("OK" if ok else "FAILED")

    if ok:
        state.setdefault("opens", []).extend(p["_key"] for p in new_opens)
        state.setdefault("closes", []).extend(c["_key"] for c in new_closes)
        _save_state(state)
        print(f"  notify_state.json updated ({len(state['opens'])} opens, {len(state['closes'])} closes tracked)")


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
