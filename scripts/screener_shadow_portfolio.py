"""
Cartera SCREENER_SHADOW — 100% mecánica, sin IA en ningún punto. Una SOLA cartera que registra las entradas de
los 5 filtros del Screener (cada posición lleva el filtro de origen en `filter`; el dashboard la muestra con una
pestaña por filtro). Regla fijada en wiki/PREREGISTRO_SCREENER_SHADOW_V0.md (firmada 2026-10-09).

Eventos: salen de docs/data/screener_signal_log.jsonl (Step 9g1). Un evento = primera aparición de un ticker en un
filtro tras >=10 días naturales sin ser candidato de ESE filtro. Solo cuentan eventos con fecha de captura
>= START_CAPTURE_DATE (los datos anteriores a la firma no se usan para evaluar).

Ejecución (sin look-ahead): entrada = cierre de la sesión SIGUIENTE a la barra de la señal. La fecha de captura del
snapshot NO es la fecha de la barra (`asOf` sí, y va 1-2 sesiones por detrás), así que todo se indexa por fecha de
barra, igual que scripts/screener_signal_report.js (makeExecTools).

Salida (evaluada sobre CIERRES de barra, una vez por barra; el pipeline no vigila el precio intradía), tamaño de
ATR congelado en la entrada:
  hard stop     cierre <= entrada - 1.5 x ATR
  trailing      se activa cuando el máximo cierre >= entrada x (1 + max(5%, 1.5 x ATR%)); después sale con
                cierre <= máximo - 2 x ATR
  time stop     primer cierre con >=14 días naturales desde la barra de entrada
Tamaño 5% fijo (provisional: "ya veremos los pesos si esto llega a ser algo más"), sin límite de posiciones.

La cartera NO es la medición estadística del filtro: esa es el retorno a 7/14/30 días sin stops de
screener_signal_report.js (`horizons_executable`). Aquí se ve qué haría una regla de salida concreta.

Idempotente: cada ejecución recalcula todos los eventos desde el log y el snapshot (el estado es determinista).

Uso:
    py -3 scripts/screener_shadow_portfolio.py             # dry-run
    py -3 scripts/screener_shadow_portfolio.py --apply     # escribe ai_picks.json
    py -3 scripts/screener_shadow_portfolio.py --report    # resumen por filtro
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
SNAPSHOT = DATA / "portfolio_daily_snapshot.jsonl"
LOG = DATA / "screener_signal_log.jsonl"
PICKS_JSON = DATA / "ai_picks.json"

NAME = "SCREENER_SHADOW"
START_CAPTURE_DATE = "2026-10-10"   # primer día de captura que cuenta (firma 2026-10-09)
COOLDOWN_DAYS = 10
SIZE_PCT = 5.0
HARD_STOP_ATR = 1.5
TRAIL_ATR = 2.0
ACTIVATE_MIN_PCT = 5.0
ACTIVATE_ATR = 1.5
TIME_STOP_DAYS = 14

FILTER_LABELS = {
    "flow_inflexion": "Flow Inflexión",
    "flow_continuacion": "Flow Continuación",
    "flow_reversion": "Flow Reversión",
    "line_near_zero_up": "MACD línea → 0",
    "hist_cross_confirmed": "MACD cruce histograma",
}


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def load_snapshot() -> tuple[dict, dict]:
    """(bars, bar_of): bars[ticker] = lista asc de (fecha_barra, precio, atr_pct), una por barra (la captura más
    tardía); bar_of[(ticker, fecha_captura)] = fecha de barra de esa fila."""
    raw: dict[str, dict[str, tuple]] = defaultdict(dict)
    bar_of: dict[tuple[str, str], str] = {}
    with SNAPSHOT.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            tk, cap, asof, price = r.get("ticker"), r.get("date"), r.get("asOf"), r.get("price")
            if not (tk and cap and asof) or not isinstance(price, (int, float)) or price <= 0:
                continue
            bar = str(asof)[:10]
            bar_of[(tk, cap)] = bar
            prev = raw[tk].get(bar)
            if prev is None or cap >= prev[0]:
                raw[tk][bar] = (cap, float(price), r.get("atrPct"))
    bars = {tk: sorted(((b, v[1], v[2]) for b, v in d.items()), key=lambda x: x[0]) for tk, d in raw.items()}
    return bars, bar_of


def load_events() -> list[dict]:
    rows = []
    if LOG.exists():
        with LOG.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    rows.sort(key=lambda r: r["date"])
    last_seen: dict[tuple[str, str], str] = {}
    events = []
    for r in rows:
        k = (r["filter"], r["ticker"])
        prev = last_seen.get(k)
        last_seen[k] = r["date"]
        if prev and _days(prev, r["date"]) < COOLDOWN_DAYS:
            continue
        if r["date"] >= START_CAPTURE_DATE:
            events.append(r)
    return events


def simulate(ev: dict, bars: dict, bar_of: dict) -> dict | None:
    """Estado determinista de un evento. None = todavía sin barra de entrada (pendiente) o sin datos."""
    tk = ev["ticker"]
    sig_bar = bar_of.get((tk, ev["date"]))
    series = bars.get(tk)
    if not sig_bar or not series:
        return None
    entry_i = next((i for i, x in enumerate(series) if x[0] > sig_bar), None)
    if entry_i is None:
        return None                      # la barra de entrada aún no existe
    e_bar, e_price, e_atr = series[entry_i]
    if not isinstance(e_atr, (int, float)) or e_atr <= 0:
        return {"skipped": "sin_atr_en_entrada", "ticker": tk}
    A = e_price * e_atr / 100.0
    hard_stop = e_price - HARD_STOP_ATR * A
    act_level = e_price * (1 + max(ACTIVATE_MIN_PCT, ACTIVATE_ATR * e_atr) / 100.0)
    M = e_price
    activated = False
    res = {
        "entry_bar": e_bar, "entry_price": e_price, "atr_pct": e_atr, "hard_stop": hard_stop,
        "act_level": act_level, "sig_bar": sig_bar, "status": "open",
    }
    last = series[entry_i]
    for bar, price, _ in series[entry_i + 1:]:
        last = (bar, price, None)
        M = max(M, price)
        if M >= act_level:
            activated = True
        reason = None
        if price <= hard_stop:
            reason = "hard_stop_1.5atr"
        elif activated and price <= M - TRAIL_ATR * A:
            reason = "trailing_2atr"
        elif _days(e_bar, bar) >= TIME_STOP_DAYS:
            reason = "time_stop_14d"
        if reason:
            res.update(status="closed", exit_bar=bar, exit_price=price, reason=reason, running_max=M)
            return res
    res.update(running_max=M, activated=activated, last_bar=last[0], last_price=last[1],
               trail_stop=(M - TRAIL_ATR * A) if activated else None)
    return res


def _position_record(ev: dict, s: dict) -> dict:
    fid = ev["filter"]
    return {
        "ticker": ev["ticker"],
        "entry_date": s["entry_bar"],
        "entry_price": round(s["entry_price"], 4),
        "size_pct": SIZE_PCT,
        "entry_signal": FILTER_LABELS.get(fid, fid),
        "filter": fid,
        "signal_date": ev["date"],
        "signal_bar": s["sig_bar"],
        "event_id": f"{fid}|{ev['ticker']}|{ev['date']}",
        "rationale": (f"Screener '{FILTER_LABELS.get(fid, fid)}' · entrada al cierre de la sesión siguiente a la señal · "
                      f"stops en ATR ({s['atr_pct']:.1f}%): hard {s['hard_stop']:.4f}"),
        "atr_pct_at_entry": s["atr_pct"],
        "hard_stop": round(s["hard_stop"], 4),
        "activation_level": round(s["act_level"], 4),
        "running_max": round(s["running_max"], 4),
        "trail_stop": None if s.get("trail_stop") is None else round(s["trail_stop"], 4),
    }


def run(apply: bool, report: bool) -> int:
    if not SNAPSHOT.exists() or not LOG.exists():
        print("Falta portfolio_daily_snapshot.jsonl o screener_signal_log.jsonl — nada que hacer.")
        return 1
    bars, bar_of = load_snapshot()
    events = load_events()
    picks = json.loads(PICKS_JSON.read_text(encoding="utf-8")) if PICKS_JSON.exists() else {}
    ptf = picks.setdefault("portfolios", {}).setdefault(NAME, {"positions": [], "history": []})
    hist_ids = {h.get("event_id") for h in ptf.get("history", []) if h.get("event") == "close"}

    positions, new_closes, pending, skipped = [], [], 0, 0
    for ev in events:
        s = simulate(ev, bars, bar_of)
        if s is None:
            pending += 1
            continue
        if s.get("skipped"):
            skipped += 1
            continue
        rec = _position_record(ev, s)
        if s["status"] == "open":
            positions.append(rec)
        elif rec["event_id"] not in hist_ids:
            ret = (s["exit_price"] / s["entry_price"] - 1) * 100
            new_closes.append({**rec, "event": "close", "close_date": s["exit_bar"],
                               "close_price": round(s["exit_price"], 4), "close_reason": s["reason"],
                               "ret_pct": round(ret, 2)})

    print(f"[{NAME}] eventos desde {START_CAPTURE_DATE}: {len(events)} · abiertas {len(positions)} · "
          f"cerradas nuevas {len(new_closes)} · pendientes de barra de entrada {pending} · sin ATR {skipped}")
    for c in new_closes:
        print(f"  CLOSE {c['ticker']:10s} [{c['filter']}] {c['ret_pct']:+.2f}% ({c['close_reason']})")

    if report:
        allc = ptf.get("history", []) + new_closes
        by = defaultdict(list)
        for h in allc:
            if h.get("event") == "close" and h.get("filter"):
                by[h["filter"]].append(h["ret_pct"])
        for fid in FILTER_LABELS:
            r = by.get(fid, [])
            op = sum(1 for p in positions if p["filter"] == fid)
            print(f"  {FILTER_LABELS[fid]:24s} abiertas={op:3d} cerradas={len(r):3d}" +
                  (f" media={sum(r)/len(r):+.2f}%" if r else ""))

    if not apply:
        print("Dry-run (sin --apply): no se ha escrito ai_picks.json.")
        return 0
    ptf["positions"] = positions
    ptf.setdefault("history", []).extend(new_closes)
    PICKS_JSON.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{NAME}] ai_picks.json actualizado.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(run(apply="--apply" in sys.argv, report="--report" in sys.argv))
