"""
Koncorde 3D shadow exit signals — counterfactual only, never touches real positions.

For every OPEN position (all portfolios, including MIMO_SHADOW), watches whether
Koncorde 3D deteriorates and logs a shadow exit signal to shadow_exits.jsonl. Purely
observational: the goal is to measure, after the fact, whether Koncorde 3D anticipates
deterioration earlier than the weekly PCS/rot_score EXIT criteria already used in
open_picks_review (paper_trading.py) — see hoja sección 3/16.2.

Reads Koncorde from koncorde_data.json (not ai_candidates.json) so tickers that
dropped out of the 91-candidate universe (left_universe=true) are still covered,
as long as koncorde_calculator.py keeps computing them for open positions (it does —
see the ai_picks.json ticker collection in koncorde_calculator.py's run()).

Dedup: a (position, signal) pair is only logged once per unique konc_3d_bar_date.
The 3D bar only rolls every 3 sessions but this script may run 2x/day (pipeline
cadence), so without this a persistent condition like BLUE_SLOPE_NEGATIVE_2_BARS
would otherwise be re-logged on every run while it stays active.

Usage:
    py -3 scripts/koncorde_shadow_exits.py
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

PICKS_PATH = DATA / "ai_picks.json"
KONC_PATH  = DATA / "koncorde_data.json"
STATE_PATH = DATA / "koncorde_shadow_state.json"
EXITS_LOG  = DATA / "shadow_exits.jsonl"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _days_held(entry_date: str | None, today: str) -> int | None:
    if not entry_date:
        return None
    try:
        d0 = datetime.strptime(entry_date, "%Y-%m-%d").date()
        d1 = datetime.strptime(today, "%Y-%m-%d").date()
        return (d1 - d0).days
    except ValueError:
        return None


def run() -> None:
    today = str(date.today())
    picks      = _load(PICKS_PATH)
    konc_data  = _load(KONC_PATH)
    konc_tickers: dict = konc_data.get("tickers", {})
    state: dict = _load(STATE_PATH)

    positions = [
        {**pos, "portfolio": pid}
        for pid, ptf in picks.get("portfolios", {}).items()
        for pos in ptf.get("positions", [])
    ]

    n_signals = 0
    n_no_data = 0

    for pos in positions:
        ticker = pos.get("ticker")
        if not ticker:
            continue
        portfolio   = pos.get("portfolio")
        entry_date  = pos.get("entry_date")
        position_id = f"{portfolio}:{ticker}:{entry_date}"

        k = konc_tickers.get(ticker)
        if not k:
            n_no_data += 1
            continue

        cur_3d_blue  = k.get("konc_3d_blue")
        cur_3d_state = k.get("konc_3d_state")
        bar_date     = k.get("konc_3d_bar_date")
        down_2_bars  = bool(k.get("konc_3d_blue_down_2_bars", False))

        prev = state.get(ticker, {})
        prev_3d_blue  = prev.get("prev_3d_blue")
        prev_3d_state = prev.get("prev_3d_state")
        logged: dict  = prev.get("logged_signals", {})

        signals: list[str] = []
        if (prev_3d_blue is not None and cur_3d_blue is not None
                and prev_3d_blue >= 0 and cur_3d_blue < 0):
            signals.append("EXIT_SHADOW_KONC3_BLUE_CROSS_DOWN")
        if (cur_3d_state == "distribution"
                and prev_3d_state is not None and prev_3d_state != "distribution"):
            signals.append("EXIT_SHADOW_KONC3_DISTRIBUTION")
        if down_2_bars:
            signals.append("EXIT_SHADOW_KONC3_BLUE_SLOPE_NEGATIVE_2_BARS")

        for sig in signals:
            dedup_key = f"{position_id}:{sig}"
            if bar_date is not None and logged.get(dedup_key) == bar_date:
                continue  # already logged this exact 3D bar for this position+signal
            _append_jsonl(EXITS_LOG, {
                "date":             today,
                "ticker":           ticker,
                "portfolio":        portfolio,
                "entry_date":       entry_date,
                "position_id":      position_id,
                "signal":           sig,
                "days_held":        _days_held(entry_date, today),
                "konc_3d_blue":     cur_3d_blue,
                "konc_3d_state":    cur_3d_state,
                "konc_3d_bar_date": bar_date,
            })
            logged[dedup_key] = bar_date
            n_signals += 1

        state[ticker] = {
            "prev_3d_blue":   cur_3d_blue,
            "prev_3d_state":  cur_3d_state,
            "logged_signals": logged,
        }

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Koncorde shadow exits: {len(positions)} open position(s), "
          f"{n_signals} new signal(s) logged, {n_no_data} without Koncorde data.")


if __name__ == "__main__":
    run()
