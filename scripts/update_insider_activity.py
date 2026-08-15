"""
update_insider_activity.py — Form4API insider-activity confirmation layer
                              (pilot phase, Portfolio Tracker only)

Adds a "did insiders confirm this?" context layer on top of Koncorde
accumulation signals, scoped to portfolio.json (the user's Portfolio
Tracker) — NOT the AI Picks Lab candidate universe (ai_candidates.json /
ai_picks.json), and NOT a BUY/SELL signal. Decided explicitly with the user
2026-08-16 before implementing, because the project has two independent
position systems (see CLAUDE.md) and the plan's "posiciones abiertas"
trigger was ambiguous between them.

Universe scoping (also a deliberate decision, not fully spelled out in the
original plan — documented here so it's auditable):
  - The Koncorde-based triggers (P1/P2) evaluate EVERY ticker in
    portfolio.json (112 tickers across all sections as of 2026-08-16) —
    Koncorde is already computed for all of them by koncorde_calculator.py,
    which builds its own universe from portfolio.json directly.
  - **Koncorde-only queuing, single criterion** (final state after 4 rounds
    of narrowing in the same 2026-08-16 session, all at the user's explicit
    request): 99/112 ("posiciones abiertas") -> 89/112 (dropped
    `open_position` as a standalone trigger, kept only for cache cadence)
    -> 89/112 (dropped `watchlist_principal`, redundant) -> 86/112 (dropped
    `PCS >= 75`, ai_candidates.json no longer read at all) -> **7/112**
    (this change: dropped the looser daily-blue-trend triggers —
    `konc_d_blue_positive_days_6_ge4`/`konc_d_blue_up_count_6_ge4`, which
    also fire in plain "up" state, not just accumulation — plus the
    alignment/transition derivatives, redundant with a plain state check).
    The queue now checks exactly one thing: is `konc_w_state`,
    `konc_3d_state` or `konc_d_state` literally `"accumulation"` today
    (blue>=0, green<0)? `is_open_position` still exists in the universe
    metadata purely for cache cadence (refreshed every 2 days instead of
    7/10 once a ticker is ALREADY queued via Koncorde).
  - `candidate_ranking_score_shadow`/`EarlyFlow improving`/`RFL/sector
    favorable` (all originally P3 ideas): moot now that P3 itself was
    removed — kept as a historical note, not reintroduced.

Field-name caution: two independent lookups of the Form4API docs returned
conflicting field names for a couple of boolean flags (isTenPercentOwner vs
is10PctOwner, directOrIndirect vs directIndirect). normalize_transaction()
reads both variants defensively via _pick(), and the FULL raw transaction is
always stored (never trust a summarized field list over the live payload —
same lesson as the TIPS-vs-nominal mislabeling in /api/treasury-auctions and
the CFTC contract-name bug documented elsewhere in this project). The first
non-empty response in a run prints its raw key list to stdout so a human can
confirm/correct field names against the real API during the pilot.

Reads:
  portfolio.json                      (universe + section membership)
  docs/data/koncorde_data.json        (trigger conditions + confirmation context)
  docs/data/insider_activity_snapshot.json  (prior last_fetch, for cache/dedup)
  docs/data/form4api_usage_log.jsonl        (today's request count so far)

Writes:
  docs/data/insider_activity_snapshot.json      (rewritten each run, keyed by ticker)
  docs/data/insider_activity_transactions.jsonl (append-only, dedup by accession+code+date+shares+price)
  docs/data/form4api_usage_log.jsonl            (append-only, one row per ticker considered)
  docs/analysis/insider_activity_pilot_report.md (--pilot-report only)

Usage:
  py -3 scripts/update_insider_activity.py --dry-run              # show queue, no API calls
  py -3 scripts/update_insider_activity.py                        # real run (needs FORM4API_KEY)
  py -3 scripts/update_insider_activity.py --max-requests 20      # pilot: cap this run tightly
  py -3 scripts/update_insider_activity.py --tickers HIMS,NVDA,ASML.AS --force
  py -3 scripts/update_insider_activity.py --priority P1
  py -3 scripts/update_insider_activity.py --report               # console summary, no API calls
  py -3 scripts/update_insider_activity.py --pilot-report          # writes docs/analysis/insider_activity_pilot_report.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
ANALYSIS_DIR = ROOT / "docs" / "analysis"

PORTFOLIO_PATH   = ROOT / "portfolio.json"
KONCORDE_PATH    = DATA / "koncorde_data.json"
SNAPSHOT_PATH    = DATA / "insider_activity_snapshot.json"
TRANSACTIONS_LOG = DATA / "insider_activity_transactions.jsonl"
USAGE_LOG        = DATA / "form4api_usage_log.jsonl"
PILOT_REPORT     = ANALYSIS_DIR / "insider_activity_pilot_report.md"

FORM4API_BASE = "https://api.form4api.com"
FORM4API_KEY_ENV = "FORM4API_KEY"

# Free plan: 500/day, 20/min, 15,000/month (=500*30, not a separate hard cap).
# Kept well under the real ceiling on purpose.
MAX_FORM4API_REQUESTS_PER_DAY   = 400
FORM4API_SAFETY_STOP            = 450
MAX_FORM4API_REQUESTS_PER_MINUTE = 15
MAX_PAGES_PER_TICKER = 3   # 3 x per_page(100) = 300 rows/ticker safety cap

LOOKBACK_DAYS = 380   # slightly over 12M so the 9-12M window is never short a few days

REFRESH_DAYS_OPEN_POSITION = 2    # "Cartera" section / shares>0
REFRESH_DAYS_P1 = 7
REFRESH_DAYS_P2 = 10

WINDOWS = [("0_3m", 0, 90), ("3_6m", 91, 180), ("6_9m", 181, 270), ("9_12m", 271, 365)]

BUY_SELL_CODES = {"P", "S"}

_CEO_PAT = re.compile(r"\bCEO\b|chief executive officer", re.IGNORECASE)
_CFO_PAT = re.compile(r"\bCFO\b|chief financial officer", re.IGNORECASE)


# ── IO helpers ───────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _pick(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


# ── Universe / triggers ──────────────────────────────────────────────────

def load_universe() -> dict[str, dict]:
    """ticker -> {sections: [...], shares: float, is_open_position: bool}"""
    data = load_json(PORTFOLIO_PATH)
    out: dict[str, dict] = {}
    for sec in data.get("sections", []):
        name = sec.get("name", "")
        for item in sec.get("items", []):
            tk = item.get("ticker")
            if not tk:
                continue
            entry = out.setdefault(tk, {"sections": [], "shares": 0})
            entry["sections"].append(name)
            entry["shares"] = max(entry["shares"], item.get("shares") or 0)
    for entry in out.values():
        entry["is_open_position"] = entry["shares"] > 0 or "Cartera" in entry["sections"]
    return out


def load_open_positions(universe: dict[str, dict]) -> list[str]:
    return [tk for tk, meta in universe.items() if meta["is_open_position"]]


def load_koncorde_features() -> dict[str, dict]:
    return load_json(KONCORDE_PATH).get("tickers", {})


def build_insider_request_queue(universe: dict[str, dict], koncorde: dict[str, dict]) -> list[dict]:
    """One entry per ticker that has >=1 trigger reason, at its highest
    matching priority (P1 > P2). Tickers with zero reasons are simply
    absent — this is the "don't query the whole universe" gate.

    Single criterion, narrowed further 2026-08-16 (4th round, same session,
    user request): a timeframe must be LITERALLY in `accumulation` state
    today (blue>=0, green<0) — not "blue trending up" (konc_d_blue_positive_days_6/
    konc_d_blue_up_count_6, dropped: those also fire in plain "up" state,
    not just accumulation), not alignment/transition derivatives (dropped:
    both are redundant with the plain state check below — a fresh
    transition INTO accumulation means the current state already IS
    accumulation, and konc_alignment=="accumulation_setup" already requires
    3D==accumulation). Verified against real data: this reproduces exactly
    the 7/112 tickers with any of D/3D/W in accumulation right now (down
    from 86 with the looser daily-trend criteria).

    P1 = W or 3D (the less noisy timeframes, per this project's own
    documented stance on Koncorde D vs 3D/W — see "Koncorde Plus en el
    payload del modelo" in CLAUDE.md). P2 = D only (noisier, kept as a
    lower-priority signal rather than dropped entirely)."""
    queue = []
    for tk in universe:
        k = koncorde.get(tk, {})
        p1, p2 = [], []

        if k.get("konc_w_state") == "accumulation":
            p1.append("konc_w_accumulation")
        if k.get("konc_3d_state") == "accumulation":
            p1.append("konc_3d_accumulation")
        if k.get("konc_d_state") == "accumulation":
            p2.append("konc_d_accumulation")

        if p1:
            queue.append({"ticker": tk, "priority": "P1", "reasons": p1})
        elif p2:
            queue.append({"ticker": tk, "priority": "P2", "reasons": p2})
    return queue


# ── Ticker mapping ───────────────────────────────────────────────────────

def map_ticker_to_form4api(ticker: str) -> tuple[str, bool, bool]:
    """Returns (form4api_ticker, mapping_applied, likely_unsupported).

    Form4API is SEC Form 4 (EDGAR) only -> US-listed issuers. Any Yahoo-style
    foreign-exchange suffix (.TO, .V, .AX, .L, .DE, .AS, .MI, .F, .ST, ...)
    is flagged unsupported WITHOUT spending a request — verified against the
    real portfolio.json universe (34/112 tickers carry such a suffix as of
    2026-08-16; none are US SEC filers under that exact symbol).

    Dash-to-dot dual-class mapping (BRK-B -> BRK.B) is a best-effort guess —
    no such ticker exists in this project's universe today to verify against
    a real response, so this is UNCONFIRMED. If wrong, the live API will
    return no-data/unsupported and coverage_status reflects that instead of
    silently producing a false positive.
    """
    if "." in ticker:
        return ticker, False, True
    if "-" in ticker:
        return ticker.replace("-", "."), True, False
    return ticker, False, False


# ── Rate limiting ────────────────────────────────────────────────────────

class RateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self._stamps: list[float] = []

    def wait_if_needed(self) -> None:
        now = time.time()
        self._stamps = [t for t in self._stamps if now - t < 60]
        if len(self._stamps) >= self.max_per_minute:
            sleep_for = 60 - (now - self._stamps[0]) + 0.1
            if sleep_for > 0:
                time.sleep(sleep_for)

    def record(self) -> None:
        self._stamps.append(time.time())


# ── Fetch ────────────────────────────────────────────────────────────────

_diagnosed_keys = False


def fetch_form4api_transactions(form4_ticker: str, api_key: str, from_date: str, to_date: str,
                                 rate_limiter: RateLimiter) -> tuple[list[dict], dict]:
    global _diagnosed_keys
    rows_all: list[dict] = []
    meta = {"coverage_status": "covered", "pages_fetched": 0, "truncated": False, "error": None}
    page = 1
    while page <= MAX_PAGES_PER_TICKER:
        rate_limiter.wait_if_needed()
        try:
            resp = requests.get(
                f"{FORM4API_BASE}/v1/transactions",
                headers={"X-Api-Key": api_key},
                params={"ticker": form4_ticker, "from": from_date, "to": to_date,
                        "per_page": 100, "page": page},
                timeout=20,
            )
        except requests.RequestException as e:
            meta["error"] = f"request_exception: {e}"
            return rows_all, meta
        rate_limiter.record()
        meta["pages_fetched"] = page

        if resp.status_code == 404:
            meta["coverage_status"] = "unsupported_non_us_or_no_data"
            return rows_all, meta
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", {})
                meta["error"] = f"http_{resp.status_code}: {err.get('code')} {err.get('message')}"
            except Exception:
                meta["error"] = f"http_{resp.status_code}"
            return rows_all, meta

        try:
            rows = resp.json()
        except ValueError:
            meta["error"] = "invalid_json_response"
            return rows_all, meta
        if not isinstance(rows, list):
            meta["error"] = "unexpected_response_shape"
            return rows_all, meta

        if rows and not _diagnosed_keys:
            print(f"  [diagnostic] first live transaction raw fields: {sorted(rows[0].keys())}")
            _diagnosed_keys = True

        rows_all.extend(rows)
        if len(rows) < 100:
            break
        page += 1
    else:
        meta["truncated"] = True
    return rows_all, meta


# ── Normalize / classify ─────────────────────────────────────────────────

def normalize_transaction(raw: dict, ticker: str) -> dict:
    code = raw.get("transactionCode")
    is_open_market = raw.get("isOpenMarket")
    if is_open_market is None:
        is_open_market = code in BUY_SELL_CODES and not raw.get("isDerivative", False)
    shares = _pick(raw, "sharesAmount")
    price  = _pick(raw, "pricePerShare")
    value  = _pick(raw, "value", "totalValue")
    if value is None and shares is not None and price is not None:
        value = shares * price
    return {
        "source": "form4api",
        "ticker": ticker,
        "companyName": raw.get("companyName"),
        "insiderName": raw.get("insiderName"),
        "insiderCik": raw.get("insiderCik"),
        "insiderTitle": raw.get("insiderTitle"),
        "isDirector": raw.get("isDirector"),
        "isOfficer": raw.get("isOfficer"),
        "isTenPercentOwner": _pick(raw, "isTenPercentOwner", "is10PctOwner"),
        "transactionCode": code,
        "isBuyOrSell": code in BUY_SELL_CODES,
        "isOpenMarket": is_open_market,
        "isDerivative": bool(raw.get("isDerivative", False)),
        "is10b5Plan": bool(raw.get("is10b5Plan", False)),
        "securityTitle": raw.get("securityTitle"),
        "sharesAmount": shares,
        "pricePerShare": price,
        "value": value,
        "totalValue": _pick(raw, "totalValue", "value"),
        "sharesOwnedAfter": raw.get("sharesOwnedAfter"),
        "directOrIndirect": _pick(raw, "directOrIndirect", "directIndirect"),
        "accessionNumber": raw.get("accessionNumber"),
        "filedAt": raw.get("filedAt"),
        "transactionDate": raw.get("transactionDate"),
        "periodOfReport": raw.get("periodOfReport"),
        "raw": raw,
    }


def classify_transaction(tx: dict) -> str:
    """noise | discretionary_open_market_buy | discretionary_open_market_sell
    | planned_open_market_sell"""
    code = tx.get("transactionCode")
    if code not in BUY_SELL_CODES or tx.get("isDerivative") or not tx.get("isOpenMarket"):
        return "noise"
    if code == "P":
        return "noise" if tx.get("is10b5Plan") else "discretionary_open_market_buy"
    return "planned_open_market_sell" if tx.get("is10b5Plan") else "discretionary_open_market_sell"


def _is_ceo(title): return bool(_CEO_PAT.search(title or ""))
def _is_cfo(title): return bool(_CFO_PAT.search(title or ""))


def _empty_window() -> dict:
    return {
        "open_market_buy_value": 0.0, "open_market_sell_value": 0.0,
        "planned_10b5_sell_value": 0.0, "net_open_market_value": 0.0,
        "buy_count": 0, "sell_count": 0,
        "unique_buyers": 0, "unique_sellers": 0,
        "ceo_cfo_buy_count": 0, "director_buy_count": 0, "ten_percent_owner_buy_count": 0,
        "largest_buy_value": 0.0, "largest_sell_value": 0.0,
        "latest_transaction_date": None,
    }


def _window_for(days_ago: int) -> str | None:
    for name, lo, hi in WINDOWS:
        if lo <= days_ago <= hi:
            return name
    return None


def aggregate_windows(transactions: list[dict], as_of: date) -> dict:
    windows = {name: _empty_window() for name, _, _ in WINDOWS}
    buyers: dict[str, set] = {name: set() for name, _, _ in WINDOWS}
    sellers: dict[str, set] = {name: set() for name, _, _ in WINDOWS}

    for tx in transactions:
        td = tx.get("transactionDate")
        if not td:
            continue
        try:
            tdate = datetime.strptime(td[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        days_ago = (as_of - tdate).days
        if days_ago < 0:
            continue
        wname = _window_for(days_ago)
        if wname is None:
            continue
        w = windows[wname]
        cls = classify_transaction(tx)
        value = tx.get("value") or 0
        insider = tx.get("insiderName") or tx.get("insiderCik") or "?"

        if cls == "discretionary_open_market_buy":
            w["open_market_buy_value"] += value
            w["buy_count"] += 1
            buyers[wname].add(insider)
            w["largest_buy_value"] = max(w["largest_buy_value"], value)
            if _is_ceo(tx.get("insiderTitle")) or _is_cfo(tx.get("insiderTitle")):
                w["ceo_cfo_buy_count"] += 1
            if tx.get("isDirector"):
                w["director_buy_count"] += 1
            if tx.get("isTenPercentOwner"):
                w["ten_percent_owner_buy_count"] += 1
        elif cls == "discretionary_open_market_sell":
            w["open_market_sell_value"] += value
            w["sell_count"] += 1
            sellers[wname].add(insider)
            w["largest_sell_value"] = max(w["largest_sell_value"], value)
        elif cls == "planned_open_market_sell":
            w["planned_10b5_sell_value"] += value
            w["sell_count"] += 1
            sellers[wname].add(insider)

        if cls != "noise" and (w["latest_transaction_date"] is None or td[:10] > w["latest_transaction_date"]):
            w["latest_transaction_date"] = td[:10]

    for name, w in windows.items():
        # Deliberate: 10b5-1 planned sells do NOT subtract from net_open_market_value
        # (they're pre-scheduled, not a discretionary signal) — kept as a separate
        # field instead, per the plan's own "no deben penalizar igual" instruction.
        w["net_open_market_value"] = round(w["open_market_buy_value"] - w["open_market_sell_value"], 2)
        w["unique_buyers"] = len(buyers[name])
        w["unique_sellers"] = len(sellers[name])
        for f in ("open_market_buy_value", "open_market_sell_value", "planned_10b5_sell_value",
                  "largest_buy_value", "largest_sell_value"):
            w[f] = round(w[f], 2)
    return windows


def _has_cluster_buying(disc_buys: list[dict]) -> bool:
    dated = sorted(
        [(datetime.strptime(t["transactionDate"][:10], "%Y-%m-%d"), t.get("insiderName") or t.get("insiderCik") or "?")
         for t in disc_buys if t.get("transactionDate")],
        key=lambda x: x[0],
    )
    for i, (d0, who0) in enumerate(dated):
        window_insiders = {who0}
        for d1, who1 in dated[i + 1:]:
            if (d1 - d0).days > 30:
                break
            window_insiders.add(who1)
        if len(window_insiders) >= 2:
            return True
    return False


def compute_flags(transactions: list[dict], windows: dict) -> list[str]:
    flags = []
    disc_buys  = [t for t in transactions if classify_transaction(t) == "discretionary_open_market_buy"]

    if _has_cluster_buying(disc_buys):
        flags.append("cluster_buying")
    if any(_is_ceo(t.get("insiderTitle")) for t in disc_buys):
        flags.append("ceo_purchase")
    if any(_is_cfo(t.get("insiderTitle")) for t in disc_buys):
        flags.append("cfo_purchase")
    if any(t.get("isDirector") for t in disc_buys):
        flags.append("director_purchase")
    if any(t.get("isTenPercentOwner") for t in disc_buys):
        flags.append("ten_percent_owner_purchase")

    if windows["0_3m"]["net_open_market_value"] > 0:
        flags.append("net_buying_last_3m")
    if windows["0_3m"]["net_open_market_value"] + windows["3_6m"]["net_open_market_value"] > 0:
        flags.append("net_buying_last_6m")

    sell_0_3m = windows["0_3m"]["open_market_sell_value"]
    buy_0_3m  = windows["0_3m"]["open_market_buy_value"]
    if sell_0_3m > 0 and (buy_0_3m == 0 or sell_0_3m > 3 * buy_0_3m):
        flags.append("heavy_discretionary_selling")

    planned_0_3m = windows["0_3m"]["planned_10b5_sell_value"]
    if (planned_0_3m + sell_0_3m) > 0 and planned_0_3m > sell_0_3m:
        flags.append("mostly_10b5_1_selling")

    if not any(w["buy_count"] or w["sell_count"] for w in windows.values()):
        flags.append("no_recent_activity")

    return flags


def compute_insider_activity_score(coverage_status: str, flags: list[str], windows: dict) -> int:
    """0-5, first pass — not calibrated against forward performance, same
    "observe first" posture as extension_risk/Koncorde before either had
    enough data to justify a real threshold. Single ordered cascade,
    documented order = priority (same convention as _konc_alignment)."""
    if coverage_status != "covered":
        return 0
    if "cluster_buying" in flags:
        return 5
    if "net_buying_last_3m" in flags:
        return 4
    if windows["0_3m"]["buy_count"] >= 1:
        return 3
    if "heavy_discretionary_selling" in flags:
        return 1
    return 2


def compute_koncorde_insider_context(k: dict, coverage_status: str, flags: list[str], windows: dict) -> str:
    """strong_confirmation | moderate_confirmation | neutral | warning |
    ignored_selling | not_evaluable — ordered cascade, first match wins."""
    if coverage_status != "covered" or not k:
        return "not_evaluable"
    accumulation_now = k.get("konc_3d_state") == "accumulation" or k.get("konc_w_state") == "accumulation"
    accumulation_d    = k.get("konc_d_state") == "accumulation"
    buy_0_3m = windows["0_3m"]["buy_count"] > 0
    buy_0_6m = buy_0_3m or windows["3_6m"]["buy_count"] > 0

    if accumulation_now and buy_0_3m:
        return "strong_confirmation"
    if accumulation_d and buy_0_6m:
        return "moderate_confirmation"
    if accumulation_now or accumulation_d:
        if "heavy_discretionary_selling" in flags:
            return "warning"
        if "mostly_10b5_1_selling" in flags:
            return "ignored_selling"
        return "neutral"
    return "neutral"


# ── Cache / dedup ────────────────────────────────────────────────────────

def _cache_skip_reason(prior_entry: dict | None, is_open_position: bool, priority: str,
                        today: date, force: bool) -> str | None:
    if force or not prior_entry:
        return None
    last_fetch = prior_entry.get("last_fetch")
    if not last_fetch:
        return None
    if last_fetch == today.isoformat():
        return "skipped_cached"
    days_since = (today - date.fromisoformat(last_fetch)).days
    cadence = (REFRESH_DAYS_OPEN_POSITION if is_open_position
               else REFRESH_DAYS_P1 if priority == "P1"
               else REFRESH_DAYS_P2)
    return "skipped_cached" if days_since < cadence else None


def _count_requests_today(today: date) -> int:
    return sum(r.get("requests_made_count", 0) for r in load_jsonl(USAGE_LOG)
               if r.get("date") == today.isoformat())


def _tx_dedup_key(tx: dict) -> tuple:
    return (tx.get("accessionNumber"), tx.get("transactionCode"), tx.get("transactionDate"),
            tx.get("sharesAmount"), tx.get("pricePerShare"))


# ── Snapshot entries for non-fetched outcomes ────────────────────────────

def _placeholder_entry(tk: str, form4_ticker: str, mapping_applied: bool, today: date,
                        q: dict, coverage_status: str, activity_status: str,
                        flags: list[str], error: str | None = None) -> dict:
    return {
        "ticker": tk, "form4api_ticker": form4_ticker, "mapping_applied": mapping_applied,
        "source": "form4api", "as_of": today.isoformat(), "last_fetch": today.isoformat(),
        "coverage_status": coverage_status, "insider_activity_status": activity_status,
        "fetch_priority": q["priority"], "fetch_trigger_reasons": q["reasons"],
        "windows": {name: _empty_window() for name, _, _ in WINDOWS},
        "latest_transactions": [], "flags": flags,
        "insider_activity_score": 0, "koncorde_insider_context": "not_evaluable",
        "koncorde_snapshot": None, "pages_fetched": 0, "truncated": False,
        "error": error,
    }


def _usage_row(today: date, ticker: str, form4_ticker: str, mapping_applied: bool,
               request_made: bool, requests_made_count: int, priority: str, reasons: list[str],
               status: str, requests_used_today: int, error: str | None) -> dict:
    return {
        "date": today.isoformat(), "ticker": ticker, "form4api_ticker": form4_ticker,
        "mapping_applied": mapping_applied, "request_made": request_made,
        "requests_made_count": requests_made_count, "priority": priority,
        "trigger_reasons": reasons, "status": status,
        "requests_used_today": requests_used_today, "error": error,
    }


# ── Report mode ───────────────────────────────────────────────────────────

def _console_report() -> None:
    snap = load_json(SNAPSHOT_PATH)
    tickers = snap.get("tickers", {})
    if not tickers:
        print("insider_activity_snapshot.json: no data yet.")
        return
    covered = [t for t in tickers.values() if t.get("coverage_status") == "covered"]
    unsupported = [t for t in tickers.values() if t.get("coverage_status") == "unsupported_non_us_or_no_data"]
    errors = [t for t in tickers.values() if t.get("coverage_status") == "error"]
    with_buys = [t for t in covered if any((t.get("windows", {}).get(w) or {}).get("buy_count", 0) > 0
                                            for w in ("0_3m", "3_6m", "6_9m", "9_12m"))]
    cluster = [t for t in covered if "cluster_buying" in (t.get("flags") or [])]
    mostly_10b5 = [t for t in covered if "mostly_10b5_1_selling" in (t.get("flags") or [])]
    print(f"insider_activity_snapshot.json: {len(tickers)} ticker(s) tracked (as_of {snap.get('as_of')})")
    print(f"  covered: {len(covered)}  unsupported: {len(unsupported)}  error: {len(errors)}")
    print(f"  with any P/S buys in window: {len(with_buys)}")
    print(f"  cluster_buying: {len(cluster)}  mostly_10b5_1_selling: {len(mostly_10b5)}")
    today_used = _count_requests_today(date.today())
    print(f"  requests used today so far: {today_used}")


def _write_pilot_report() -> None:
    snap = load_json(SNAPSHOT_PATH)
    tickers = snap.get("tickers", {})
    usage = load_jsonl(USAGE_LOG)
    today_str = date.today().isoformat()
    today_rows = [r for r in usage if r.get("date") == today_str]

    n_queried = len(tickers)
    covered = [t for t in tickers.values() if t.get("coverage_status") == "covered"]
    unsupported = [t for t in tickers.values() if t.get("coverage_status") == "unsupported_non_us_or_no_data"]
    errors = [t for t in tickers.values() if t.get("coverage_status") == "error"]
    with_p_buys = [t for t in covered if (t.get("windows", {}).get("0_3m") or {}).get("buy_count", 0) > 0
                   or (t.get("windows", {}).get("3_6m") or {}).get("buy_count", 0) > 0
                   or (t.get("windows", {}).get("6_9m") or {}).get("buy_count", 0) > 0
                   or (t.get("windows", {}).get("9_12m") or {}).get("buy_count", 0) > 0]
    cluster = [t for t in covered if "cluster_buying" in (t.get("flags") or [])]
    mostly_10b5 = [t for t in covered if "mostly_10b5_1_selling" in (t.get("flags") or [])]
    requests_used = sum(r.get("requests_made_count", 0) for r in today_rows)
    error_rows = [r for r in today_rows if r.get("status") == "error"]

    lines = [
        "# Insider Activity — piloto Form4API",
        "",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. Tickers consultados",
        f"{n_queried} tickers con datos en `insider_activity_snapshot.json`.",
        "",
        "## 2. Con datos (covered)",
        f"{len(covered)} / {n_queried}",
        "",
        "## 3. Unsupported / sin datos",
        f"unsupported_non_us_or_no_data: {len(unsupported)}  ·  error: {len(errors)}",
        "",
        "## 4. Compras P discrecionales",
        f"{len(with_p_buys)} ticker(s) con al menos una compra/venta P/S en alguna ventana.",
        "",
        "## 5. Cluster buying",
        f"{len(cluster)} ticker(s) con flag `cluster_buying`.",
        (", ".join(t["ticker"] for t in cluster) if cluster else "(ninguno)"),
        "",
        "## 6. Ventas mayoritariamente 10b5-1",
        f"{len(mostly_10b5)} ticker(s) con flag `mostly_10b5_1_selling`.",
        "",
        "## 7. Requests usadas hoy",
        f"{requests_used} (límite operativo: {MAX_FORM4API_REQUESTS_PER_DAY}/día, safety stop: {FORM4API_SAFETY_STOP})",
        "",
        "## 8. Errores",
        (f"{len(error_rows)} fila(s) con status=error:\n" + "\n".join(
            f"- {r['ticker']}: {r.get('error')}" for r in error_rows) if error_rows else "Ninguno."),
        "",
        "## 9. ¿Pasar de piloto a integración diaria?",
        "_(criterio a completar manualmente tras revisar los puntos 1-8 — el script no toma esta decisión)_",
        "",
    ]
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    PILOT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Pilot report written -> {PILOT_REPORT}")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--tickers", type=str, default=None, help="comma-separated, overrides trigger gating")
    ap.add_argument("--priority", choices=["P1", "P2"], default=None)
    ap.add_argument("--from-date", default=None)
    ap.add_argument("--to-date", default=None)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--pilot-report", action="store_true")
    args = ap.parse_args()

    if args.report:
        _console_report()
        return
    if args.pilot_report:
        _write_pilot_report()
        return

    today = date.today()
    universe = load_universe()
    koncorde = load_koncorde_features()

    queue = build_insider_request_queue(universe, koncorde)

    if args.priority:
        queue = [q for q in queue if q["priority"] == args.priority]
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
        filtered = [q for q in queue if q["ticker"] in wanted]
        present = {q["ticker"] for q in filtered}
        for tk in wanted - present:
            filtered.append({"ticker": tk, "priority": "manual", "reasons": ["manual_override"]})
        queue = filtered

    order = {"P1": 0, "P2": 1, "manual": 2}
    queue.sort(key=lambda q: order.get(q["priority"], 9))

    if not queue:
        print("No tickers triggered today (no Koncorde/PCS/section trigger matched). Nothing to do.")
        return

    existing_snapshot = load_json(SNAPSHOT_PATH)
    tickers_snapshot: dict = dict(existing_snapshot.get("tickers", {}))

    if args.dry_run:
        print(f"[DRY-RUN] {len(queue)} ticker(s) triggered today:")
        for q in queue:
            skip = _cache_skip_reason(tickers_snapshot.get(q["ticker"]),
                                       universe[q["ticker"]]["is_open_position"],
                                       q["priority"], today, args.force)
            tag = f" -> {skip}" if skip else ""
            print(f"  {q['ticker']:10} priority={q['priority']:6} reasons={','.join(q['reasons'])}{tag}")
        return

    load_dotenv(ROOT / ".env")
    api_key = os.getenv(FORM4API_KEY_ENV)
    if not api_key:
        print(f"{FORM4API_KEY_ENV} not set (checked environment and .env) — aborting. "
              f"Use --dry-run to preview the queue without a key.")
        sys.exit(1)

    max_daily = args.max_requests if args.max_requests is not None else MAX_FORM4API_REQUESTS_PER_DAY
    requests_used_today = _count_requests_today(today)
    rate_limiter = RateLimiter(MAX_FORM4API_REQUESTS_PER_MINUTE)

    from_date = args.from_date or (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    to_date   = args.to_date or today.isoformat()

    existing_tx = load_jsonl(TRANSACTIONS_LOG)
    tx_seen = {_tx_dedup_key(r) for r in existing_tx}

    usage_rows: list[dict] = []
    tx_new: list[dict] = []
    n_success = n_skipped_cached = n_skipped_limit = n_unsupported = n_error = 0

    for q in queue:
        tk = q["ticker"]
        is_open = universe[tk]["is_open_position"]
        prior = tickers_snapshot.get(tk)

        skip = _cache_skip_reason(prior, is_open, q["priority"], today, args.force)
        if skip:
            n_skipped_cached += 1
            usage_rows.append(_usage_row(today, tk, tk, False, False, 0, q["priority"], q["reasons"],
                                          skip, requests_used_today, None))
            continue

        if requests_used_today >= FORM4API_SAFETY_STOP or requests_used_today >= max_daily:
            n_skipped_limit += 1
            usage_rows.append(_usage_row(today, tk, tk, False, False, 0, q["priority"], q["reasons"],
                                          "skipped_limit", requests_used_today, None))
            continue

        form4_ticker, mapping_applied, likely_unsupported = map_ticker_to_form4api(tk)
        if likely_unsupported:
            n_unsupported += 1
            tickers_snapshot[tk] = _placeholder_entry(tk, form4_ticker, mapping_applied, today, q,
                                                       "unsupported_non_us_or_no_data", "unsupported",
                                                       ["unsupported_ticker"])
            usage_rows.append(_usage_row(today, tk, form4_ticker, mapping_applied, False, 0,
                                          q["priority"], q["reasons"], "unsupported",
                                          requests_used_today, None))
            continue

        rows, meta = fetch_form4api_transactions(form4_ticker, api_key, from_date, to_date, rate_limiter)
        requests_used_today += meta["pages_fetched"]

        if meta["error"]:
            n_error += 1
            tickers_snapshot[tk] = _placeholder_entry(tk, form4_ticker, mapping_applied, today, q,
                                                        "error", "error", [], error=meta["error"])
            usage_rows.append(_usage_row(today, tk, form4_ticker, mapping_applied, True,
                                          meta["pages_fetched"], q["priority"], q["reasons"],
                                          "error", requests_used_today, meta["error"]))
            continue

        if meta["coverage_status"] == "unsupported_non_us_or_no_data":
            n_unsupported += 1
            tickers_snapshot[tk] = _placeholder_entry(tk, form4_ticker, mapping_applied, today, q,
                                                        "unsupported_non_us_or_no_data", "unsupported",
                                                        ["unsupported_ticker"])
            usage_rows.append(_usage_row(today, tk, form4_ticker, mapping_applied, True,
                                          meta["pages_fetched"], q["priority"], q["reasons"],
                                          "unsupported", requests_used_today, None))
            continue

        normalized = [normalize_transaction(r, tk) for r in rows]
        for n in normalized:
            n["form4api_ticker"] = form4_ticker
            n["mapping_applied"] = mapping_applied
            key = _tx_dedup_key(n)
            if key not in tx_seen:
                tx_seen.add(key)
                tx_new.append(n)

        windows = aggregate_windows(normalized, today)
        flags = compute_flags(normalized, windows)
        activity_status = "has_activity" if any(w["buy_count"] or w["sell_count"] for w in windows.values()) else "none_found"
        score = compute_insider_activity_score("covered", flags, windows)
        k = koncorde.get(tk, {})
        context = compute_koncorde_insider_context(k, "covered", flags, windows)
        latest = sorted(normalized, key=lambda t: t.get("transactionDate") or "", reverse=True)[:10]
        latest_public = [{kk: vv for kk, vv in t.items() if kk != "raw"} for t in latest]

        tickers_snapshot[tk] = {
            "ticker": tk, "form4api_ticker": form4_ticker, "mapping_applied": mapping_applied,
            "source": "form4api", "as_of": today.isoformat(), "last_fetch": today.isoformat(),
            "coverage_status": "covered", "insider_activity_status": activity_status,
            "fetch_priority": q["priority"], "fetch_trigger_reasons": q["reasons"],
            "windows": windows, "latest_transactions": latest_public, "flags": flags,
            "insider_activity_score": score, "koncorde_insider_context": context,
            "koncorde_snapshot": {
                "konc_d_state": k.get("konc_d_state"), "konc_3d_state": k.get("konc_3d_state"),
                "konc_w_state": k.get("konc_w_state"), "konc_alignment": k.get("konc_alignment"),
                "konc_d_blue_slope": k.get("konc_d_blue_slope"),
                "konc_d_blue_positive_days_6": k.get("konc_d_blue_positive_days_6"),
                "konc_d_blue_up_count_6": k.get("konc_d_blue_up_count_6"),
            },
            "pages_fetched": meta["pages_fetched"], "truncated": meta["truncated"],
        }
        n_success += 1
        usage_rows.append(_usage_row(today, tk, form4_ticker, mapping_applied, True,
                                      meta["pages_fetched"], q["priority"], q["reasons"],
                                      "success", requests_used_today, None))

    for r in usage_rows:
        append_jsonl(USAGE_LOG, r)
    for r in tx_new:
        append_jsonl(TRANSACTIONS_LOG, r)
    write_json(SNAPSHOT_PATH, {"as_of": today.isoformat(), "tickers": tickers_snapshot})

    print(f"Insider Activity: {len(queue)} ticker(s) in today's queue -> "
          f"{n_success} fetched, {n_skipped_cached} cached, {n_skipped_limit} limit-skipped, "
          f"{n_unsupported} unsupported, {n_error} error. "
          f"Requests used today: {requests_used_today}/{max_daily} "
          f"(safety stop {FORM4API_SAFETY_STOP}). New transactions logged: {len(tx_new)}.")


if __name__ == "__main__":
    main()
