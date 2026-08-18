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
import html
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

# Some console prints can carry emoji (e.g. echoed LLM/transcription errors);
# Windows consoles default to cp1252 and crash on print() otherwise. Same fix
# already applied in duration_monitor.py / check_koncorde_alerts.py.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
from koncorde_alert_conditions import (
    CONDITIONS as KONC_CONDITIONS,
    TIMEFRAME_LABELS as KONC_TIMEFRAME_LABELS,
    VALID_TIMEFRAMES as KONC_VALID_TIMEFRAMES,
    describe as describe_koncorde_condition,
)
from paper_trading import call_model, parse_response  # lazy-imports openai internally

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

PORTFOLIO_FILE = ROOT / "portfolio.json"
STATE_FILE     = ROOT / "docs" / "data" / "telegram_bot_state.json"
CLAUDE_MD      = ROOT / "CLAUDE.md"
WATCHLIST_ID   = "watchlist"
WATCHLIST_NAME = "Watchlist"

KONC_PARSE_MODEL = "anthropic/claude-haiku-4.5"
GROQ_TRANSCRIBE_MODEL = "whisper-large-v3-turbo"

DOCS_START = "<!-- BOT_DOCS_START -->"
DOCS_END   = "<!-- BOT_DOCS_END -->"

# GitHub API — used when running on Railway (or USE_GITHUB_API=true)
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO", "")   # e.g. "owner/market-tracker"
USE_GITHUB_API = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("USE_GITHUB_API"))

# Paths relative to repo root used by the GitHub Contents API
_PORTFOLIO_PATH   = "portfolio.json"
_STATE_PATH       = "docs/data/telegram_bot_state.json"
_ALERTS_PATH      = "docs/data/bot_alerts.json"
_PICKS_PATH       = "docs/data/ai_picks.json"
_CANDIDATES_PATH  = "docs/data/ai_candidates.json"
_KONC_DATA_PATH   = "docs/data/koncorde_data.json"
# Deliberately a SEPARATE file from _ALERTS_PATH (price alerts): check_alerts()/
# cmd_alert_delete()/cmd_alerts_list() below iterate _load_alerts() assuming every
# entry has target/direction — mixing Koncorde alerts into that list would make
# check_alerts() misread a Koncorde entry as a price alert with target=0 and fire
# a bogus notification on the very first check. Full isolation, zero risk to the
# existing (live) price-alert feature.
_KONC_ALERTS_PATH = "docs/data/koncorde_bot_alerts.json"

ALERTS_CHECK_EVERY = 5   # check price alerts every N polling cycles (~2.5 min)

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
        "cmd":   "/picks",
        "usage": "/picks",
        "desc":  "Muestra las posiciones abiertas del AI Picks Lab con precio actual.",
    },
    {
        "cmd":   "/gainers",
        "usage": "/gainers",
        "desc":  "Top 5 tickers del portfolio con mayor subida en el día.",
    },
    {
        "cmd":   "/losers",
        "usage": "/losers",
        "desc":  "Top 5 tickers del portfolio con mayor caída en el día.",
    },
    {
        "cmd":   "/macro",
        "usage": "/macro",
        "desc":  "MacroScore actual, régimen y tendencia del pipeline.",
    },
    {
        "cmd":   "/alert",
        "usage": "/alert TICKER PRECIO",
        "desc":  "Activa una alerta de precio. El bot te avisa cuando TICKER cruce PRECIO.",
    },
    {
        "cmd":   "/alerts",
        "usage": "/alerts",
        "desc":  "Lista tus alertas de precio activas.",
    },
    {
        "cmd":   "/delalert",
        "usage": "/delalert TICKER",
        "desc":  "Elimina la alerta de precio de un ticker.",
    },
    {
        "cmd":   "/kalert",
        "usage": "/kalert TICKER TIMEFRAME CONDICION  |  /kalert <texto libre>",
        "desc":  "Crea una alerta sobre una condición de Koncorde (blue/green/estado, en D/3D/W). Acepta sintaxis exacta o una petición en lenguaje natural (se interpreta con IA). También se puede crear mandando una nota de voz al bot.",
    },
    {
        "cmd":   "/kalerts",
        "usage": "/kalerts",
        "desc":  "Lista tus alertas de Koncorde activas.",
    },
    {
        "cmd":   "/delkalert",
        "usage": "/delkalert TICKER",
        "desc":  "Elimina la(s) alerta(s) de Koncorde de un ticker.",
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


def _load_alerts() -> list:
    if USE_GITHUB_API:
        try:
            data, sha = _gh_read(_ALERTS_PATH)
            _sha_cache[_ALERTS_PATH] = sha
            return data if isinstance(data, list) else []
        except Exception:
            return []
    alerts_file = ROOT / "docs" / "data" / "bot_alerts.json"
    try:
        if alerts_file.exists():
            return json.loads(alerts_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_alerts(alerts: list) -> None:
    if USE_GITHUB_API:
        try:
            if _ALERTS_PATH not in _sha_cache:
                try:
                    _, sha = _gh_read(_ALERTS_PATH)
                    _sha_cache[_ALERTS_PATH] = sha
                except Exception:
                    _sha_cache[_ALERTS_PATH] = ""
            sha = _sha_cache.get(_ALERTS_PATH, "")
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{_ALERTS_PATH}"
            content_b64 = base64.b64encode(json.dumps(alerts, indent=2).encode()).decode()
            payload: dict = {"message": "bot: update alerts", "content": content_b64}
            if sha:
                payload["sha"] = sha
            r = requests.put(url, json=payload,
                             headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=15)
            r.raise_for_status()
            _sha_cache[_ALERTS_PATH] = r.json()["content"]["sha"]
        except Exception as exc:
            print(f"GitHub alerts write failed: {exc}")
        return
    alerts_file = ROOT / "docs" / "data" / "bot_alerts.json"
    alerts_file.write_text(json.dumps(alerts, indent=2), encoding="utf-8")


def _load_konc_alerts() -> list:
    if USE_GITHUB_API:
        try:
            data, sha = _gh_read(_KONC_ALERTS_PATH)
            _sha_cache[_KONC_ALERTS_PATH] = sha
            return data if isinstance(data, list) else []
        except Exception:
            return []
    alerts_file = ROOT / "docs" / "data" / "koncorde_bot_alerts.json"
    try:
        if alerts_file.exists():
            return json.loads(alerts_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_konc_alerts(alerts: list) -> bool:
    """Returns True on confirmed success — callers must not claim success to
    the user without checking this (previously cmd_kalert_set/cmd_kalert_delete
    always sent a success message regardless, so a GitHub API failure looked
    identical to a real save and left the user with no way to know)."""
    if USE_GITHUB_API:
        try:
            if _KONC_ALERTS_PATH not in _sha_cache:
                try:
                    _, sha = _gh_read(_KONC_ALERTS_PATH)
                    _sha_cache[_KONC_ALERTS_PATH] = sha
                except Exception:
                    _sha_cache[_KONC_ALERTS_PATH] = ""
            sha = _sha_cache.get(_KONC_ALERTS_PATH, "")
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{_KONC_ALERTS_PATH}"
            content_b64 = base64.b64encode(json.dumps(alerts, indent=2).encode()).decode()
            payload: dict = {"message": "bot: update koncorde alerts", "content": content_b64}
            if sha:
                payload["sha"] = sha
            r = requests.put(url, json=payload,
                             headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=15)
            r.raise_for_status()
            _sha_cache[_KONC_ALERTS_PATH] = r.json()["content"]["sha"]
            return True
        except Exception as exc:
            print(f"GitHub koncorde alerts write failed: {exc}")
            return False
    alerts_file = ROOT / "docs" / "data" / "koncorde_bot_alerts.json"
    try:
        alerts_file.write_text(json.dumps(alerts, indent=2), encoding="utf-8")
        return True
    except Exception as exc:
        print(f"Local koncorde alerts write failed: {exc}")
        return False


def _load_picks() -> dict:
    if USE_GITHUB_API:
        try:
            data, _ = _gh_read(_PICKS_PATH)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    picks_file = ROOT / "docs" / "data" / "ai_picks.json"
    try:
        if picks_file.exists():
            return json.loads(picks_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _load_macro() -> dict:
    if USE_GITHUB_API:
        try:
            data, _ = _gh_read(_CANDIDATES_PATH)
            return data.get("macro_context", {}) if isinstance(data, dict) else {}
        except Exception:
            return {}
    candidates_file = ROOT / "docs" / "data" / "ai_candidates.json"
    try:
        if candidates_file.exists():
            data = json.loads(candidates_file.read_text(encoding="utf-8"))
            return data.get("macro_context", {})
    except Exception:
        pass
    return {}


def _load_koncorde_data() -> dict:
    """Ticker -> konc_* fields, from the latest koncorde_calculator.py snapshot."""
    if USE_GITHUB_API:
        try:
            data, _ = _gh_read(_KONC_DATA_PATH)
            return data.get("tickers", {}) if isinstance(data, dict) else {}
        except Exception:
            return {}
    konc_file = ROOT / "docs" / "data" / "koncorde_data.json"
    try:
        if konc_file.exists():
            data = json.loads(konc_file.read_text(encoding="utf-8"))
            return data.get("tickers", {})
    except Exception:
        pass
    return {}


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


# ── New command handlers ──────────────────────────────────────────────────

def cmd_picks(token: str, chat_id: str) -> None:
    picks_data  = _load_picks()
    portfolios  = picks_data.get("portfolios", {})
    last_updated = picks_data.get("last_updated", "?")

    all_positions: list[tuple[str, str, dict]] = []  # (portfolio_name, ticker, position)
    for port_name, port in portfolios.items():
        for pos in port.get("positions", []):
            all_positions.append((port_name, pos.get("ticker", "?"), pos))

    if not all_positions:
        _send(token, chat_id, "No hay posiciones abiertas en AI Picks.")
        return

    lines = [f"<b>AI Picks Lab</b> — <i>{last_updated}</i>", ""]
    for port_name, ticker, pos in all_positions:
        quote = _get_quote(ticker)
        price_str = ""
        acum_str  = ""
        if quote:
            p          = quote["price"]
            chg        = quote.get("change_pct")
            sign_d     = "+" if (chg or 0) >= 0 else ""
            chg_s      = f"{sign_d}{chg}%" if chg is not None else "?"
            entry_price = pos.get("entry_price")
            if entry_price and entry_price > 0:
                acum = round((p - entry_price) / entry_price * 100, 2)
                sign_a = "+" if acum >= 0 else ""
                acum_str = f"  acum <b>{sign_a}{acum}%</b>"
            price_str = f" → <b>{p}</b>  hoy <b>{chg_s}</b>"
        conv  = pos.get("conviction", "")
        size  = pos.get("size_pct", "")
        entry = pos.get("entry_date", "")
        label = port_name.replace("_", " ").title()
        lines.append(f"<b>{ticker}</b>{price_str}{acum_str}")
        lines.append(f"  {label} · {size}% · {conv} · desde {entry}")
        lines.append("")

    _send(token, chat_id, "\n".join(lines).rstrip())


def cmd_movers(token: str, chat_id: str, portfolio: dict, top_n: int = 5, gainers: bool = True) -> None:
    tickers: list[str] = []
    for sec in portfolio.get("sections", []):
        for item in sec.get("items", []):
            t = item.get("ticker", "")
            if t and t not in tickers:
                tickers.append(t)

    if not tickers:
        _send(token, chat_id, "Portfolio vacío.")
        return

    results: list[tuple[float, str, float]] = []  # (change_pct, ticker, price)
    for t in tickers:
        q = _get_quote(t)
        if q and q.get("change_pct") is not None:
            results.append((q["change_pct"], t, q["price"]))

    if not results:
        _send(token, chat_id, "No se pudieron obtener precios.")
        return

    results.sort(key=lambda x: x[0], reverse=gainers)
    subset = results[:top_n]

    title = "Gainers" if gainers else "Losers"
    emoji = "▲" if gainers else "▼"
    lines = [f"<b>{emoji} Top {top_n} {title} hoy</b>", ""]
    for chg, ticker, price in subset:
        sign = "+" if chg >= 0 else ""
        lines.append(f"<b>{ticker}</b>  {price}  <b>{sign}{chg}%</b>")
    _send(token, chat_id, "\n".join(lines))


def cmd_macro(token: str, chat_id: str) -> None:
    macro = _load_macro()
    if not macro:
        _send(token, chat_id, "No se pudo obtener el MacroScore.")
        return

    score   = macro.get("score", "?")
    regime  = macro.get("regime", "?")
    trend   = macro.get("trend", "?")
    d1w     = macro.get("delta_1w")
    d1m     = macro.get("delta_1m")

    lines = [
        "<b>MacroScore</b>",
        "",
        f"Score: <b>{score}</b>",
        f"Régimen: <b>{regime}</b>",
        f"Tendencia: {trend}",
    ]
    if d1w is not None:
        sign = "+" if d1w >= 0 else ""
        lines.append(f"Δ 1 semana: {sign}{d1w}")
    if d1m is not None:
        sign = "+" if d1m >= 0 else ""
        lines.append(f"Δ 1 mes: {sign}{d1m}")

    _send(token, chat_id, "\n".join(lines))


def cmd_alert_set(token: str, chat_id: str, ticker: str, target: float) -> None:
    ticker  = ticker.upper()
    alerts  = _load_alerts()
    quote   = _get_quote(ticker)
    current = quote["price"] if quote else None
    direction = "above" if (current is None or target > current) else "below"

    alerts = [a for a in alerts if a.get("ticker") != ticker]  # replace if exists
    alerts.append({
        "ticker":    ticker,
        "target":    target,
        "direction": direction,
        "created":   str(date.today()),
    })
    _save_alerts(alerts)

    dir_str = "suba a" if direction == "above" else "baje a"
    curr_str = f" (ahora {current})" if current else ""
    _send(token, chat_id, f"Alerta activada: te aviso cuando <b>{ticker}</b> {dir_str} <b>{target}</b>{curr_str}.")


def cmd_alerts_list(token: str, chat_id: str) -> None:
    alerts = _load_alerts()
    if not alerts:
        _send(token, chat_id, "No tienes alertas activas.")
        return
    lines = ["<b>Alertas activas:</b>", ""]
    for a in alerts:
        dir_str = "↑" if a.get("direction") == "above" else "↓"
        lines.append(f"{dir_str} <b>{a['ticker']}</b> @ {a['target']}  <i>({a.get('created','')})</i>")
    _send(token, chat_id, "\n".join(lines))


def cmd_alert_delete(token: str, chat_id: str, ticker: str) -> None:
    ticker = ticker.upper()
    alerts = _load_alerts()
    before = len(alerts)
    alerts = [a for a in alerts if a.get("ticker") != ticker]
    if len(alerts) < before:
        _save_alerts(alerts)
        _send(token, chat_id, f"Alerta de <b>{ticker}</b> eliminada.")
    else:
        _send(token, chat_id, f"No hay alerta activa para <b>{ticker}</b>.")


_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


def _parse_koncorde_alert_strict(args_text: str) -> dict | None:
    """Exact 3-token form: TICKER TIMEFRAME CONDITION. No LLM call needed.
    TIMEFRAME accepts a comma-separated list (e.g. "d,w") to alert on any of
    several timeframes — each becomes its own independent alert row, so
    whichever fires first fires (OR semantics) without any evaluator changes."""
    tokens = args_text.split()
    if len(tokens) != 3:
        return None
    ticker, tf_raw, cond = tokens[0].upper(), tokens[1].lower(), tokens[2].lower()
    tfs = [t for t in dict.fromkeys(tf_raw.split(","))]  # dedupe, keep order
    if not tfs or any(tf not in KONC_VALID_TIMEFRAMES for tf in tfs) or cond not in KONC_CONDITIONS:
        return None
    if not _TICKER_RE.match(ticker):
        return None
    return {"ticker": ticker, "timeframes": tfs, "condition": cond}


def _parse_koncorde_alert_nl(text: str) -> dict | None:
    """Free-text (or voice-transcribed) request -> {ticker, timeframes, condition,
    ticker_guessed}. timeframes is always a list — a request naming several
    timeframes with "or" semantics ("o bien diario o bien semanal") becomes one
    entry per timeframe, later saved as independent alert rows (whichever fires
    first fires) rather than requiring any real multi-timeframe evaluator logic.
    ticker_guessed=True means the model had to infer the symbol from a
    company/asset name rather than the user stating the ticker literally
    (e.g. "Loma" -> LOMA) — the caller must NOT create the alert directly in that
    case, only propose it for confirmation via the exact-syntax command. This is
    the deliberate middle ground between never-guess (too rigid for voice) and
    silently trusting a guessed symbol (risk of alerting on the wrong ticker).

    Uses a cheap OpenRouter call (Haiku) constrained to the closed condition
    vocabulary in koncorde_alert_conditions.py. Returns None (never guesses
    condition) if OPENROUTER_API_KEY is missing, the call fails, or the model
    can't determine ticker/timeframes/condition with confidence.
    """
    if not os.environ.get("OPENROUTER_API_KEY", ""):
        return None

    cond_lines = "\n".join(f'  "{k}" — {v}' for k, v in KONC_CONDITIONS.items())
    system = (
        "Extraes una alerta sobre el indicador Koncorde a partir de una petición en "
        "español (texto libre, a veces transcrita de una nota de voz). Responde SOLO "
        "con JSON compacto, sin markdown ni explicación.\n\n"
        "Campos a extraer:\n"
        '- "ticker": símbolo bursátil en mayúsculas. Si el usuario ya dice el símbolo '
        'tal cual (ej. "CRESY", "AAPL", "GLEN.L"), úsalo directamente y pon '
        '"ticker_guessed": false. Si el usuario menciona el nombre de la empresa/activo '
        'en vez del símbolo (ej. "Loma", "Apple", "el banco Galicia"), puedes usar tu '
        'conocimiento general para proponer el ticker más probable (ej. "Loma"->LOMA, '
        '"Apple"->AAPL, "banco Galicia"->GGAL) y poner "ticker_guessed": true. Si no hay '
        'ningún candidato razonable, no inventes nada — responde con error (ver abajo).\n'
        f'- "timeframes": lista con uno o más de {list(KONC_VALID_TIMEFRAMES)!r} — '
        '"d"=diario, "3d"=3 días, "w"=semanal/"gráfico semanal". Si el usuario pide la '
        'condición en varios timeframes a la vez con sentido de "o bien uno o bien otro" '
        '(ej. "en diario o en semanal", "en cualquiera de las dos"), incluye todos los que '
        'mencione en la lista — se crea una alerta independiente por cada uno, así avisa '
        'con el primero que se cumpla. Si no queda claro qué timeframe(s) quiere, no lo '
        'adivines.\n'
        f'- "condition": exactamente uno de estos ids (no inventes otros):\n{cond_lines}\n'
        '  Ejemplos de mapeo: "señal azul positiva"/"blue en positivo" -> blue_positive; '
        '"blue cruza a positivo"/"cruce alcista" -> blue_cross_up; '
        '"acumulación"/"acumulando" -> state_accumulation; '
        '"distribución"/"distribuyendo" -> state_distribution.\n\n'
        'Si tienes los 3 campos con confianza, responde exactamente:\n'
        '{"ticker": "...", "ticker_guessed": true|false, "timeframes": ["..."], "condition": "..."}\n'
        'Si falta o es ambiguo timeframes/condition, o el ticker/nombre no es reconocible '
        'en absoluto, responde exactamente:\n'
        '{"error": "razón breve en español"}'
    )
    try:
        raw, _, _, _ = call_model(KONC_PARSE_MODEL, system, text, max_tokens=300)
    except Exception as exc:
        print(f"Koncorde NL parse call failed: {exc}")
        return None

    data, ok = parse_response(raw)
    if not ok or not isinstance(data, dict) or "error" in data:
        if isinstance(data, dict) and "error" in data:
            print(f"Koncorde NL parse: model reported {data['error']!r}")
        return None

    ticker = str(data.get("ticker", "")).strip().upper()
    tfs_raw = data.get("timeframes", [])
    tfs = list(dict.fromkeys(str(t).strip().lower() for t in tfs_raw)) if isinstance(tfs_raw, list) else []
    cond = str(data.get("condition", "")).strip().lower()
    if not ticker or not tfs or any(tf not in KONC_VALID_TIMEFRAMES for tf in tfs) or cond not in KONC_CONDITIONS:
        return None
    if not _TICKER_RE.match(ticker):
        return None
    return {
        "ticker": ticker,
        "timeframes": tfs,
        "condition": cond,
        "ticker_guessed": bool(data.get("ticker_guessed", False)),
    }


def cmd_kalert_set(token: str, chat_id: str, ticker: str, timeframes: list[str],
                    condition: str, raw_request: str) -> None:
    """Creates one independent alert row per timeframe in `timeframes` — a
    request for "diario o semanal" becomes 2 separate rows, so whichever
    fires first fires (OR semantics) without any multi-timeframe evaluator
    logic; each keeps working on its own even after the other one deletes
    itself on firing."""
    ticker = ticker.upper()
    konc_universe = _load_koncorde_data()
    known = ticker in konc_universe

    alerts = _load_konc_alerts()
    for tf in timeframes:
        alerts = [
            a for a in alerts
            if not (a.get("ticker") == ticker and a.get("timeframe") == tf
                    and a.get("condition") == condition)
        ]
        alerts.append({
            "ticker":      ticker,
            "timeframe":   tf,
            "condition":   condition,
            "raw_request": raw_request.strip(),
            "created":     str(date.today()),
        })
    if not _save_konc_alerts(alerts):
        _send(token, chat_id,
              "⚠️ No pude guardar la alerta (fallo al escribir en GitHub). "
              "Prueba de nuevo en un momento; si persiste, revisa los logs del bot.")
        return

    note = (
        "" if known else
        "\n⚠️ No tengo datos de Koncorde para ese ticker todavía — la alerta "
        "se evaluará en cuanto los haya en el próximo run del pipeline."
    )
    if len(timeframes) == 1:
        desc = describe_koncorde_condition(ticker, timeframes[0], condition)
        _send(token, chat_id,
              f"✅ Alerta creada: <b>{desc}</b>.\nTe aviso por Telegram cuando se cumpla "
              f"(una sola vez, se borra sola al dispararse).{note}")
    else:
        lines = [describe_koncorde_condition(ticker, tf, condition) for tf in timeframes]
        bullets = "\n".join(f"• {d}" for d in lines)
        _send(token, chat_id,
              f"✅ {len(timeframes)} alertas creadas (aviso con la que se cumpla primero):\n"
              f"{bullets}\nCada una se borra sola al dispararse; las demás siguen activas.{note}")


def cmd_kalerts_list(token: str, chat_id: str) -> None:
    alerts = _load_konc_alerts()
    if not alerts:
        _send(token, chat_id, "No tienes alertas de Koncorde activas.")
        return
    lines = ["<b>Alertas de Koncorde activas:</b>", ""]
    for a in alerts:
        desc = describe_koncorde_condition(
            a.get("ticker", "?"), a.get("timeframe", "?"), a.get("condition", "?")
        )
        lines.append(f"🔮 {desc}  <i>({a.get('created', '')})</i>")
    _send(token, chat_id, "\n".join(lines))


def cmd_kalert_delete(token: str, chat_id: str, ticker: str) -> None:
    ticker = ticker.upper()
    alerts = _load_konc_alerts()
    before = len(alerts)
    alerts = [a for a in alerts if a.get("ticker") != ticker]
    if len(alerts) < before:
        if not _save_konc_alerts(alerts):
            _send(token, chat_id,
                  "⚠️ No pude guardar el cambio (fallo al escribir en GitHub). "
                  "Prueba de nuevo en un momento.")
            return
        n = before - len(alerts)
        _send(token, chat_id, f"{n} alerta(s) de Koncorde de <b>{ticker}</b> eliminada(s).")
    else:
        _send(token, chat_id, f"No hay alerta de Koncorde activa para <b>{ticker}</b>.")


def cmd_kalert(token: str, chat_id: str, args_text: str) -> None:
    args_text = args_text.strip()
    if not args_text:
        _send(token, chat_id,
              "Uso: <code>/kalert TICKER TIMEFRAME CONDICION</code>  "
              "(ej: <code>/kalert CRESY w blue_positive</code>, o "
              "<code>/kalert CRESY d,w blue_positive</code> para avisar con el primero "
              "de varios timeframes que se cumpla)\n"
              "O en lenguaje natural: <code>/kalert avisa cuando CRESY tenga la señal "
              "azul de koncorde positiva en el gráfico semanal</code>\n"
              "También puedes mandar una nota de voz.")
        return

    parsed = _parse_koncorde_alert_strict(args_text)
    if parsed is None:
        if not os.environ.get("OPENROUTER_API_KEY", ""):
            _send(token, chat_id,
                  "No puedo interpretar lenguaje natural todavía (falta configurar "
                  "OPENROUTER_API_KEY en este servicio). Usa la sintaxis exacta:\n"
                  "<code>/kalert TICKER TIMEFRAME CONDICION</code>")
            return
        parsed = _parse_koncorde_alert_nl(args_text)
    if parsed is None:
        _send(token, chat_id,
              "No he podido entender la alerta. Prueba con la sintaxis exacta:\n"
              "<code>/kalert TICKER TIMEFRAME CONDICION</code>\n"
              f"TIMEFRAME: {', '.join(KONC_VALID_TIMEFRAMES)}\n"
              f"CONDICION: {', '.join(KONC_CONDITIONS)}")
        return

    if parsed.get("ticker_guessed"):
        desc = _describe_multi(parsed["ticker"], parsed["timeframes"], parsed["condition"])
        _pending_ticker_confirmation[chat_id] = {
            "ticker":      parsed["ticker"],
            "timeframes":  parsed["timeframes"],
            "condition":   parsed["condition"],
            "raw_request": args_text,
            "proposed_at": time.time(),
        }
        _send(token, chat_id,
              f"He entendido que quieres: <b>{desc}</b>.\n"
              f"El ticker <b>{parsed['ticker']}</b> lo he deducido del nombre, no lo has dicho "
              "tal cual. Responde <b>ok</b> para confirmarlo, o escribe directamente el ticker "
              "correcto si me he equivocado.")
        return

    cmd_kalert_set(token, chat_id, parsed["ticker"], parsed["timeframes"],
                    parsed["condition"], raw_request=args_text)


def _describe_multi(ticker: str, timeframes: list[str], condition: str) -> str:
    """Human-readable summary for one or several timeframes of the same
    ticker+condition — shared between the pending-confirmation prompt in
    cmd_kalert() and the success message in cmd_kalert_set()."""
    if len(timeframes) == 1:
        return describe_koncorde_condition(ticker, timeframes[0], condition)
    tf_labels = " o ".join(KONC_TIMEFRAME_LABELS.get(tf, tf) for tf in timeframes)
    cond_label = KONC_CONDITIONS.get(condition, condition)
    return f"{ticker} — {cond_label} en {tf_labels}"


# In-memory only (chat_id -> proposal) — a Railway redeploy mid-confirmation just
# means the user re-sends the original request, no worse than any other transient
# bot restart. Persisting this to GitHub would be overkill for a single-user,
# short-lived (few minutes) confirmation window.
_pending_ticker_confirmation: dict[str, dict] = {}
_KONC_CONFIRM_TIMEOUT_SECONDS = 15 * 60


def handle_plain_text(token: str, chat_id: str, text: str) -> bool:
    """Handles a non-command, non-empty text message as a reply to a pending
    ticker-guess confirmation (see cmd_kalert). Returns True if it consumed
    the message, False if the caller should ignore it as usual (no pending
    confirmation, or it expired)."""
    pending = _pending_ticker_confirmation.get(chat_id)
    if pending is None:
        return False
    if time.time() - pending["proposed_at"] > _KONC_CONFIRM_TIMEOUT_SECONDS:
        del _pending_ticker_confirmation[chat_id]
        return False

    stripped = text.strip()
    lowered  = stripped.lower()
    if lowered in ("ok", "okay", "vale", "si", "sí", "confirmo", "correcto"):
        del _pending_ticker_confirmation[chat_id]
        cmd_kalert_set(token, chat_id, pending["ticker"], pending["timeframes"],
                        pending["condition"], raw_request=pending["raw_request"])
        return True
    if _TICKER_RE.match(stripped.upper()) and " " not in stripped:
        del _pending_ticker_confirmation[chat_id]
        cmd_kalert_set(token, chat_id, stripped, pending["timeframes"],
                        pending["condition"], raw_request=pending["raw_request"])
        return True
    return False


# ── Voice messages (Koncorde alert creation only, v1) ─────────────────────

def _download_telegram_file(token: str, file_id: str) -> tuple[bytes | None, str | None]:
    """Returns (bytes, None) on success, (None, error_detail) on failure —
    the caller surfaces error_detail to the user instead of a bare generic
    message, so a real cause (file too big, timeout, ...) doesn't require
    pulling Railway logs to diagnose."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getFile",
                          params={"file_id": file_id}, timeout=15)
        if not r.ok:
            detail = r.text[:200]
            print(f"Telegram getFile failed {r.status_code}: {detail}")
            return None, f"getFile {r.status_code}: {detail}"
        file_path = r.json()["result"]["file_path"]
        r2 = requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=30)
        r2.raise_for_status()
        return r2.content, None
    except Exception as exc:
        print(f"Telegram file download failed: {exc}")
        return None, str(exc)


def _transcribe_voice_groq(audio_bytes: bytes) -> str | None:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("voice.ogg", audio_bytes, "audio/ogg")},
            data={"model": GROQ_TRANSCRIBE_MODEL, "language": "es"},
            timeout=30,
        )
        if not r.ok:
            print(f"Groq transcription error {r.status_code}: {r.text[:200]}")
            return None
        text = (r.json().get("text") or "").strip()
        return text or None
    except Exception as exc:
        print(f"Groq transcription failed: {exc}")
        return None


def handle_voice_message(token: str, chat_id: str, file_id: str) -> None:
    """Voice notes are interpreted as Koncorde alert requests — the only
    voice-driven feature in v1. Text commands remain unaffected."""
    if not os.environ.get("GROQ_API_KEY", ""):
        _send(token, chat_id,
              "No puedo transcribir notas de voz todavía (falta configurar el servicio "
              "de voz). Usa /kalert por texto mientras tanto.")
        return
    audio, error_detail = _download_telegram_file(token, file_id)
    if audio is None:
        _send(token, chat_id, f"No pude descargar la nota de voz.\n<code>{html.escape(error_detail or 'error desconocido')}</code>")
        return
    text = _transcribe_voice_groq(audio)
    if not text:
        _send(token, chat_id, "No pude transcribir la nota de voz.")
        return
    _send(token, chat_id, f"🎙️ Entendido: <i>{html.escape(text)}</i>")
    cmd_kalert(token, chat_id, text)


def check_alerts(token: str, chat_id: str) -> None:
    alerts = _load_alerts()
    if not alerts:
        return
    fired: list[str] = []
    updated = list(alerts)
    for a in alerts:
        ticker    = a.get("ticker", "")
        target    = a.get("target", 0)
        direction = a.get("direction", "above")
        quote     = _get_quote(ticker)
        if not quote:
            continue
        price = quote["price"]
        triggered = (direction == "above" and price >= target) or \
                    (direction == "below" and price <= target)
        if triggered:
            dir_str = "subió a" if direction == "above" else "bajó a"
            _send(token, chat_id, f"🔔 <b>Alerta: {ticker}</b> {dir_str} <b>{price}</b> (objetivo: {target})")
            fired.append(ticker)

    if fired:
        updated = [a for a in updated if a.get("ticker") not in fired]
        _save_alerts(updated)


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
    elif cmd == "picks":
        cmd_picks(token, chat_id)
    elif cmd == "gainers":
        cmd_movers(token, chat_id, portfolio, gainers=True)
    elif cmd == "losers":
        cmd_movers(token, chat_id, portfolio, gainers=False)
    elif cmd == "macro":
        cmd_macro(token, chat_id)
    elif cmd == "alert":
        if len(args) >= 2:
            try:
                cmd_alert_set(token, chat_id, args[0], float(args[1]))
            except ValueError:
                _send(token, chat_id, "Uso: /alert TICKER PRECIO  (ej: /alert AAPL 200)")
        else:
            _send(token, chat_id, "Uso: /alert TICKER PRECIO  (ej: /alert AAPL 200)")
    elif cmd == "alerts":
        cmd_alerts_list(token, chat_id)
    elif cmd == "delalert":
        if args:
            cmd_alert_delete(token, chat_id, args[0])
        else:
            _send(token, chat_id, "Uso: /delalert TICKER")
    elif cmd == "kalert":
        rest = text.strip().split(maxsplit=1)
        cmd_kalert(token, chat_id, rest[1] if len(rest) > 1 else "")
    elif cmd == "kalerts":
        cmd_kalerts_list(token, chat_id)
    elif cmd == "delkalert":
        if args:
            cmd_kalert_delete(token, chat_id, args[0])
        else:
            _send(token, chat_id, "Uso: /delkalert TICKER")
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
        voice     = msg.get("voice")
        from_chat = str(msg.get("chat", {}).get("id", ""))

        if from_chat == chat_id and text.startswith("/"):
            print(f"  Processing: {text.strip()}")
            dispatch(token, chat_id, text, portfolio)
            portfolio = _load_portfolio()
            processed += 1
        elif from_chat == chat_id and voice:
            print("  Processing: [voice note]")
            handle_voice_message(token, chat_id, voice["file_id"])
            processed += 1
        elif from_chat == chat_id and text.strip():
            if handle_plain_text(token, chat_id, text):
                print(f"  Processing: {text.strip()} [ticker confirmation reply]")
                processed += 1

        if uid is not None:
            state["offset"] = uid + 1

    _save_state(state)
    print(f"Processed {processed} command(s).")


def run_loop(token: str, chat_id: str, interval: int = 30) -> None:
    """Continuous polling loop. For local/daemon use."""
    print(f"Portfolio bot running. Polling every {interval}s. Ctrl+C to stop.")
    state        = _load_state()
    alert_cycles = 0

    while True:
        try:
            updates       = _get_updates(token, offset=state.get("offset"))
            offset_before = state.get("offset")
            portfolio     = _load_portfolio()

            for update in updates:
                uid       = update.get("update_id")
                msg       = update.get("message", {})
                text      = msg.get("text", "")
                voice     = msg.get("voice")
                from_chat = str(msg.get("chat", {}).get("id", ""))

                if from_chat == chat_id and text.startswith("/"):
                    print(f"[{date.today()}] {text.strip()}")
                    dispatch(token, chat_id, text, portfolio)
                    portfolio = _load_portfolio()
                elif from_chat == chat_id and voice:
                    print(f"[{date.today()}] [voice note]")
                    handle_voice_message(token, chat_id, voice["file_id"])
                elif from_chat == chat_id and text.strip():
                    if handle_plain_text(token, chat_id, text):
                        print(f"[{date.today()}] {text.strip()} [ticker confirmation reply]")

                if uid is not None:
                    state["offset"] = uid + 1

            if state.get("offset") != offset_before:
                _save_state(state)

            alert_cycles += 1
            if alert_cycles >= ALERTS_CHECK_EVERY:
                alert_cycles = 0
                try:
                    check_alerts(token, chat_id)
                except Exception as exc:
                    print(f"Alert check error: {exc}")

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
