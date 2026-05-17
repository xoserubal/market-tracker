"""
Telegram Portfolio Bot — processes pending commands from the user's Telegram chat.

Commands:
  /portfolio          — list all portfolio sections and tickers
  /check TICKER       — current price + position info
  /add TICKER [notes] — add ticker to Watchlist section
  /remove TICKER      — remove ticker from any section

Usage:
  py -3 scripts/telegram_portfolio_bot.py --once   # process pending, exit (CI/pipeline)
  py -3 scripts/telegram_portfolio_bot.py           # continuous polling, 30s (local)

Env vars (same as notify_telegram.py):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID

State (last processed update_id) is saved in docs/data/telegram_bot_state.json
so it survives across GitHub Actions runs.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

PORTFOLIO_FILE = ROOT / "portfolio.json"
STATE_FILE     = ROOT / "docs" / "data" / "telegram_bot_state.json"
CLAUDE_MD      = ROOT / "CLAUDE.md"
WATCHLIST_ID   = "watchlist"
WATCHLIST_NAME = "Watchlist"

DOCS_START = "<!-- BOT_DOCS_START -->"
DOCS_END   = "<!-- BOT_DOCS_END -->"

# GitHub API — used when running on Railway (or USE_GITHUB_API=true)
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO", "")   # e.g. "owner/market-tracker"
USE_GITHUB_API = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("USE_GITHUB_API"))

# Paths relative to repo root used by the GitHub Contents API
_PORTFOLIO_PATH = "portfolio.json"
_STATE_PATH     = "docs/data/telegram_bot_state.json"

_sha_cache: dict[str, str] = {}   # path → current sha


def _gh_read(path: str) -> tuple[dict | list, str]:
    """Fetch a JSON file from GitHub. Returns (parsed_data, sha)."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    r   = requests.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=10)
    r.raise_for_status()
    blob    = r.json()
    content = base64.b64decode(blob["content"]).decode("utf-8")
    return json.loads(content), blob["sha"]


def _gh_write(path: str, data: dict | list, message: str = "bot: update") -> None:
    """Write a JSON file to GitHub and refresh the sha cache."""
    sha = _sha_cache.get(path, "")
    if not sha:
        _, sha = _gh_read(path)
    url         = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    content_b64 = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
    r = requests.put(
        url,
        json={"message": message, "content": content_b64, "sha": sha},
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        timeout=15,
    )
    r.raise_for_status()
    _sha_cache[path] = r.json()["content"]["sha"]

COMMANDS = [
    {
        "cmd":   "/portfolio",
        "usage": "/portfolio",
        "desc":  "Lista todas las secciones y tickers del Portfolio Tracker, agrupados por sección (máx 12 por sección).",
    },
    {
        "cmd":   "/check",
        "usage": "/check TICKER",
        "desc":  "Precio actual Yahoo Finance (15 min delay) + sección, shares, avgCost y P&L si la posición tiene datos de coste.",
    },
    {
        "cmd":   "/add",
        "usage": "/add TICKER [notas opcionales]",
        "desc":  "Añade el ticker a la sección 'Watchlist' de portfolio.json. Crea la sección si no existe. Rechaza duplicados.",
    },
    {
        "cmd":   "/remove",
        "usage": "/remove TICKER",
        "desc":  "Elimina el ticker de cualquier sección del portfolio.",
    },
    {
        "cmd":   "/help",
        "usage": "/help",
        "desc":  "Muestra este mensaje de ayuda.",
    },
]


# ── Docs generator ────────────────────────────────────────────────────────

def _generate_docs_section() -> str:
    rows = "\n".join(
        f"| `{c['cmd']}` | `{c['usage']}` | {c['desc']} |"
        for c in COMMANDS
    )
    return f"""{DOCS_START}

## Telegram Portfolio Bot

> Sección auto-generada desde `scripts/telegram_portfolio_bot.py` — no editar manualmente.
> Se regenera en cada run del pipeline. Para añadir comandos: editar `COMMANDS` en el script.

Bot que procesa comandos de Telegram para gestionar el Portfolio Tracker
(`portfolio.json` / `localhost:3000/portfolio.html`).
Se ejecuta como Step 12 en el pipeline de GitHub Actions (2×/día, modo `--once`).
También se puede lanzar en modo continuo localmente: `py -3 scripts/telegram_portfolio_bot.py`

**Estado persistido en:** `docs/data/telegram_bot_state.json` (commiteado en cada run).

**IMPORTANTE:** Gestiona `portfolio.json` (Portfolio Tracker), independiente de `ai_picks.json` (AI Picks Lab).

### Comandos

| Comando | Uso | Descripción |
|---------|-----|-------------|
{rows}

### Flujo de datos (write commands)

```
Usuario → Telegram → getUpdates (pipeline 2×/día o local continuo)
        → modifica portfolio.json en disco
        → git commit + push  (paso "Commit updated data" del workflow)
        → server.js git pull (al arrancar o botón Sincronizar)
        → portfolio.html ve los cambios
```

{DOCS_END}"""


def update_claude_docs() -> None:
    text    = CLAUDE_MD.read_text(encoding="utf-8")
    start_i = text.find(DOCS_START)
    end_i   = text.find(DOCS_END)
    if start_i < 0 or end_i < 0:
        print("Markers not found in CLAUDE.md — skipping docs update")
        return
    new_text = text[:start_i] + _generate_docs_section() + text[end_i + len(DOCS_END):]
    CLAUDE_MD.write_text(new_text, encoding="utf-8")
    print("CLAUDE.md bot section updated.")


# ── Telegram helpers ──────────────────────────────────────────────────────

def _send(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if not r.ok:
            print(f"Telegram error {r.status_code}: {r.text[:200]}")
        return r.ok
    except Exception as exc:
        print(f"Telegram send failed: {exc}")
        return False


def _get_updates(token: str, offset: int | None) -> list[dict]:
    params: dict = {"timeout": 10, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params=params,
            timeout=20,
        )
        if r.ok:
            return r.json().get("result", [])
    except Exception as exc:
        print(f"getUpdates failed: {exc}")
    return []


# ── State / portfolio I/O ─────────────────────────────────────────────────

def _load_state() -> dict:
    if USE_GITHUB_API:
        try:
            data, sha = _gh_read(_STATE_PATH)
            _sha_cache[_STATE_PATH] = sha
            return data
        except Exception as exc:
            print(f"GitHub state read failed: {exc}")
            return {"offset": None}
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"offset": None}


def _save_state(state: dict) -> None:
    if USE_GITHUB_API:
        try:
            _gh_write(_STATE_PATH, state, "bot: update state")
        except Exception as exc:
            print(f"GitHub state write failed: {exc}")
        return
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_portfolio() -> dict:
    if USE_GITHUB_API:
        try:
            data, sha = _gh_read(_PORTFOLIO_PATH)
            _sha_cache[_PORTFOLIO_PATH] = sha
            return data
        except Exception as exc:
            print(f"GitHub portfolio read failed: {exc}")
            return {"sections": []}
    try:
        if PORTFOLIO_FILE.exists():
            return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"sections": []}


def _save_portfolio(data: dict) -> None:
    if USE_GITHUB_API:
        try:
            _gh_write(_PORTFOLIO_PATH, data, "bot: update portfolio")
        except Exception as exc:
            print(f"GitHub portfolio write failed: {exc}")
        return
    PORTFOLIO_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _next_item_id(portfolio: dict) -> str:
    max_n = 0
    for sec in portfolio.get("sections", []):
        for item in sec.get("items", []):
            m = re.match(r"i(\d+)$", item.get("id", ""))
            if m:
                max_n = max(max_n, int(m.group(1)))
    return f"i{max_n + 1:03d}"


# ── Yahoo Finance quote ───────────────────────────────────────────────────

def _get_quote(ticker: str) -> dict | None:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        "?interval=1d&range=5d&includePrePost=false"
    )
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=10,
        )
        if not r.ok:
            return None
        data   = r.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes if c is not None]
        if not closes:
            return None
        price = closes[-1]
        prev  = closes[-2] if len(closes) >= 2 else None
        chg   = round((price - prev) / prev * 100, 2) if prev else None
        meta  = result.get("meta", {})
        return {
            "price":      round(price, 4),
            "change_pct": chg,
            "currency":   meta.get("currency", ""),
            "name":       meta.get("longName") or meta.get("shortName") or "",
        }
    except Exception as exc:
        print(f"Quote error {ticker}: {exc}")
        return None


# ── Command handlers ──────────────────────────────────────────────────────

def cmd_portfolio(token: str, chat_id: str, portfolio: dict) -> None:
    sections = [s for s in portfolio.get("sections", []) if s.get("items")]
    if not sections:
        _send(token, chat_id, "Portfolio vacío.")
        return

    lines: list[str] = ["<b>Portfolio Tracker</b>", ""]
    total = 0
    for sec in sections:
        name  = sec.get("name", "?")
        items = sec.get("items", [])
        lines.append(f"<b>{name}</b> ({len(items)})")
        for item in items[:12]:
            t     = item.get("ticker", "?")
            notes = item.get("notes", "")
            line  = f"  • {t}"
            if notes:
                line += f"  — <i>{notes[:40]}</i>"
            lines.append(line)
        if len(items) > 12:
            lines.append(f"  … y {len(items) - 12} más")
        total += len(items)
        lines.append("")

    lines.append(f"<i>{total} tickers — {date.today()}</i>")
    _send(token, chat_id, "\n".join(lines))


def cmd_check(token: str, chat_id: str, ticker: str, portfolio: dict) -> None:
    ticker = ticker.upper()

    found_sections: list[str] = []
    found_item: dict | None   = None
    for sec in portfolio.get("sections", []):
        for item in sec.get("items", []):
            if item.get("ticker", "").upper() == ticker:
                found_sections.append(sec.get("name", "?"))
                if found_item is None:
                    found_item = item

    quote = _get_quote(ticker)
    lines: list[str] = []

    if quote and quote.get("name"):
        lines.append(f"<b>{ticker}</b> — <i>{quote['name']}</i>")
    else:
        lines.append(f"<b>{ticker}</b>")

    if quote:
        price = quote["price"]
        chg   = quote["change_pct"]
        curr  = quote.get("currency", "")
        sign  = "+" if (chg or 0) >= 0 else ""
        chg_s = f" ({sign}{chg}%)" if chg is not None else ""
        lines.append(f"Precio: <b>{price} {curr}</b>{chg_s}")
    else:
        lines.append("Precio: no disponible")

    if found_sections:
        lines.append(f"Sección: {', '.join(found_sections)}")
        if found_item:
            shares   = found_item.get("shares")
            avg_cost = found_item.get("avgCost")
            if shares and avg_cost:
                lines.append(f"Posición: {shares}u @ {avg_cost}")
                if quote:
                    pnl  = round((quote["price"] - avg_cost) / avg_cost * 100, 1)
                    sign = "+" if pnl >= 0 else ""
                    lines.append(f"P&L: {sign}{pnl}%")
            if found_item.get("notes"):
                lines.append(f"Nota: <i>{found_item['notes']}</i>")
    else:
        lines.append("No está en tu portfolio.")

    _send(token, chat_id, "\n".join(lines))


def cmd_add(token: str, chat_id: str, ticker: str, notes: str, portfolio: dict) -> bool:
    ticker = ticker.upper()

    for sec in portfolio.get("sections", []):
        for item in sec.get("items", []):
            if item.get("ticker", "").upper() == ticker:
                _send(
                    token, chat_id,
                    f"<b>{ticker}</b> ya está en tu portfolio ({sec.get('name', '?')}).",
                )
                return False

    watchlist: dict | None = None
    for sec in portfolio.get("sections", []):
        if sec.get("id") == WATCHLIST_ID or sec.get("name") == WATCHLIST_NAME:
            watchlist = sec
            break

    if watchlist is None:
        watchlist = {"id": WATCHLIST_ID, "name": WATCHLIST_NAME, "items": []}
        portfolio.setdefault("sections", []).append(watchlist)

    watchlist.setdefault("items", []).append({
        "id":      _next_item_id(portfolio),
        "ticker":  ticker,
        "shares":  0,
        "avgCost": 0,
        "notes":   notes,
        "addedAt": str(date.today()),
    })
    _save_portfolio(portfolio)

    msg = f"✓ <b>{ticker}</b> añadido a {WATCHLIST_NAME}."
    if notes:
        msg += f"\n<i>{notes}</i>"
    _send(token, chat_id, msg)
    return True


def cmd_remove(token: str, chat_id: str, ticker: str, portfolio: dict) -> bool:
    ticker        = ticker.upper()
    removed_from: list[str] = []

    for sec in portfolio.get("sections", []):
        before       = len(sec.get("items", []))
        sec["items"] = [i for i in sec.get("items", []) if i.get("ticker", "").upper() != ticker]
        if len(sec["items"]) < before:
            removed_from.append(sec.get("name", "?"))

    if removed_from:
        _save_portfolio(portfolio)
        _send(token, chat_id, f"✓ <b>{ticker}</b> eliminado de {', '.join(removed_from)}.")
        return True

    _send(token, chat_id, f"<b>{ticker}</b> no encontrado en el portfolio.")
    return False


# ── Dispatcher ────────────────────────────────────────────────────────────

def cmd_help(token: str, chat_id: str) -> None:
    lines = ["<b>Comandos disponibles:</b>", ""]
    for c in COMMANDS:
        lines.append(f"<code>{c['usage']}</code>")
        lines.append(f"  {c['desc']}")
        lines.append("")
    _send(token, chat_id, "\n".join(lines).rstrip())


def dispatch(token: str, chat_id: str, text: str, portfolio: dict) -> bool:
    """Returns True if portfolio.json was modified."""
    parts = text.strip().split()
    if not parts:
        return False

    cmd  = parts[0].lower().lstrip("/").split("@")[0]
    args = parts[1:]

    if cmd == "help":
        cmd_help(token, chat_id)
    elif cmd == "portfolio":
        cmd_portfolio(token, chat_id, portfolio)
    elif cmd == "check":
        if args:
            cmd_check(token, chat_id, args[0], portfolio)
        else:
            _send(token, chat_id, "Uso: /check TICKER")
    elif cmd == "add":
        if args:
            notes = " ".join(args[1:])
            return cmd_add(token, chat_id, args[0], notes, portfolio)
        else:
            _send(token, chat_id, "Uso: /add TICKER [notas opcionales]")
    elif cmd == "remove":
        if args:
            return cmd_remove(token, chat_id, args[0], portfolio)
        else:
            _send(token, chat_id, "Uso: /remove TICKER")
    return False


# ── Run modes ─────────────────────────────────────────────────────────────

def run_once(token: str, chat_id: str) -> None:
    """Process all pending Telegram commands and exit. For CI/pipeline use."""
    state   = _load_state()
    updates = _get_updates(token, offset=state.get("offset"))

    if not updates:
        print("No pending Telegram commands.")
        return

    portfolio = _load_portfolio()
    processed = 0

    for update in updates:
        uid       = update.get("update_id")
        msg       = update.get("message", {})
        text      = msg.get("text", "")
        from_chat = str(msg.get("chat", {}).get("id", ""))

        if from_chat == chat_id and text.startswith("/"):
            print(f"  Processing: {text.strip()}")
            dispatch(token, chat_id, text, portfolio)
            portfolio = _load_portfolio()
            processed += 1

        if uid is not None:
            state["offset"] = uid + 1

    _save_state(state)
    print(f"Processed {processed} command(s).")


def run_loop(token: str, chat_id: str, interval: int = 30) -> None:
    """Continuous polling loop. For local/daemon use."""
    print(f"Portfolio bot running. Polling every {interval}s. Ctrl+C to stop.")
    state = _load_state()

    while True:
        try:
            updates      = _get_updates(token, offset=state.get("offset"))
            offset_before = state.get("offset")
            portfolio    = _load_portfolio()

            for update in updates:
                uid       = update.get("update_id")
                msg       = update.get("message", {})
                text      = msg.get("text", "")
                from_chat = str(msg.get("chat", {}).get("id", ""))

                if from_chat == chat_id and text.startswith("/"):
                    print(f"[{date.today()}] {text.strip()}")
                    dispatch(token, chat_id, text, portfolio)
                    portfolio = _load_portfolio()

                if uid is not None:
                    state["offset"] = uid + 1

            if state.get("offset") != offset_before:
                _save_state(state)

        except KeyboardInterrupt:
            print("Bot stopped.")
            break
        except Exception as exc:
            print(f"Error: {exc}")

        time.sleep(interval)


if __name__ == "__main__":
    if "--docs" in sys.argv:
        update_claude_docs()
        sys.exit(0)

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping")
        sys.exit(0)

    if "--once" in sys.argv:
        run_once(token, chat_id)
    else:
        run_loop(token, chat_id)
