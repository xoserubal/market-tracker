"""
Carteras MACD_COMBO — 100% mecánicas, sin IA. Entran cuando un valor es candidato a la vez de los filtros del Screener
`hist_cross_confirmed` ("Cruce confirmado") y `line_near_zero_up` ("Cerca de 0"); salen cuando el histograma MACD cruza
a la baja. Regla fijada en wiki/PREREGISTRO_MACD_COMBO_V0.md.

Dos carteras, mismas señales de entrada y misma salida; solo cambia la regla de re-entrada:
  MACD_COMBO_CD  "con cooldown": evento = primera aparición como candidato combinado tras >=10 días naturales sin serlo
                 (mismo criterio que el resto del proyecto).
  MACD_COMBO_SD  "sin cooldown": cada día candidato es una señal de entrada válida.
En ambas, un ticker no puede tener dos posiciones abiertas a la vez (una señal con posición abierta se ignora) y solo
se vuelve a entrar con una barra de entrada posterior a la de salida.

Entrada (sin look-ahead): cierre de la sesión SIGUIENTE a la barra de la señal. Todo se indexa por fecha de barra
(`asOf`), no por fecha de captura (ver screener_shadow_portfolio.py).
Salida: primera barra posterior a la de entrada con macdHist <= 0 (cruce a la baja); se ejecuta al cierre de la barra
SIGUIENTE. Sin stops, sin límite de días: mientras el histograma siga en positivo la posición continúa. Tamaño 5% fijo.

Datos para estudiar salidas alternativas: `docs/data/macd_combo_tracking.jsonl` guarda, por posición y barra (desde la
barra de la señal hasta la salida), TODOS los campos escalares del snapshot (volumen, RSI, Koncorde, SMA, OBV, MACD...)
más el PCS de ese día (`pcs_daily_log.jsonl`, que esta misma ejecución alimenta desde ai_candidates.json).
Se reescribe entero en cada ejecución (determinista).

Fases: eventos con fecha de captura >= START_FORMAL son la prueba preregistrada (`phase=preregistered`); los anteriores
se reconstruyen con los datos disponibles y son solo exploratorios (`phase=backfill_exploratory`).

Uso:
    py -3 scripts/macd_combo_portfolio.py             # dry-run
    py -3 scripts/macd_combo_portfolio.py --apply     # escribe ai_picks.json, tracking y pcs_daily_log
    py -3 scripts/macd_combo_portfolio.py --backfill-pcs --apply   # además reconstruye PCS pasado desde git (local)
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
SNAPSHOT = DATA / "portfolio_daily_snapshot.jsonl"
LOG = DATA / "screener_signal_log.jsonl"
PICKS_JSON = DATA / "ai_picks.json"
CANDIDATES = DATA / "ai_candidates.json"
PCS_LOG = DATA / "pcs_daily_log.jsonl"
TRACKING = DATA / "macd_combo_tracking.jsonl"

FILTERS = ("hist_cross_confirmed", "line_near_zero_up")
START_FORMAL = "2026-10-23"     # primer día de captura de la prueba preregistrada (firma 2026-10-22)
COOLDOWN_DAYS = 10
SIZE_PCT = 5.0
EXIT_REASON = "macd_hist_cross_down"
SNAPSHOT_START = "2026-08-20"

PORTFOLIOS = {
    "MACD_COMBO_CD": {"cooldown": True, "label": "MACD combo (con cooldown)"},
    "MACD_COMBO_SD": {"cooldown": False, "label": "MACD combo (sin cooldown)"},
}


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


# ── PCS diario ──────────────────────────────────────────────────────────────
def _pcs_rows(cand: dict) -> list[dict]:
    d = cand.get("date")
    rows = []
    for c in cand.get("candidates", []):
        if not c.get("ticker"):
            continue
        rows.append({
            "date": d, "ticker": c["ticker"], "pcs": c.get("pcs"), "pcs_normalized": c.get("pcs_normalized"),
            "pcs_ex_macro": c.get("pcs_ex_macro"), "eligible": c.get("eligible"), "signal": c.get("signal"),
            "theme": c.get("theme"), "components": c.get("pcs_components"),
        })
    return rows


def load_pcs_log() -> list[dict]:
    rows = []
    if PCS_LOG.exists():
        with PCS_LOG.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    return rows


def update_pcs_log(backfill: bool, apply: bool) -> dict:
    """Añade el PCS de ai_candidates.json (y, con --backfill-pcs, el de commits pasados). Idempotente por fecha."""
    rows = load_pcs_log()
    have = {r["date"] for r in rows}
    new: list[dict] = []
    if CANDIDATES.exists():
        cur = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        if cur.get("date") and cur["date"] not in have:
            new += _pcs_rows(cur)
            have.add(cur["date"])
    if backfill:
        out = subprocess.run(["git", "log", "--format=%H %cs", "--", "docs/data/ai_candidates.json"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split("\n")
        by_day: dict[str, str] = {}
        for ln in out:                       # más reciente primero: se conserva el último commit de cada día
            if ln.strip():
                h, d = ln.split()
                by_day.setdefault(d, h)
        for d, h in sorted(by_day.items()):
            if d < SNAPSHOT_START:
                continue
            blob = subprocess.run(["git", "show", f"{h}:docs/data/ai_candidates.json"], cwd=ROOT,
                                  capture_output=True, text=True, encoding="utf-8").stdout
            try:
                cand = json.loads(blob)
            except Exception:
                continue
            if cand.get("date") != d or d in have:   # el contenido debe corresponder al día del commit
                continue
            new += _pcs_rows(cand)
            have.add(d)
    if new and apply:
        with PCS_LOG.open("a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"nuevas_filas": len(new), "fechas_total": len(have)}


# ── Datos ───────────────────────────────────────────────────────────────────
def load_snapshot() -> tuple[dict, dict]:
    """bars[ticker] = lista asc de filas por barra (la captura más tardía de cada barra, con `_cap` y `_bar`);
    bar_of[(ticker, fecha_captura)] = fecha de barra."""
    raw: dict[str, dict[str, dict]] = defaultdict(dict)
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
            if prev is None or cap >= prev["_cap"]:
                raw[tk][bar] = {**r, "_cap": cap, "_bar": bar}
    bars = {tk: [d[b] for b in sorted(d)] for tk, d in raw.items()}
    return bars, bar_of


def load_combined_days() -> list[tuple[str, str]]:
    """(fecha_captura, ticker) en los que el valor es candidato de TODOS los filtros a la vez."""
    per: dict[str, set] = {f: set() for f in FILTERS}
    if LOG.exists():
        with LOG.open(encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("filter") in per:
                    per[r["filter"]].add((r["date"], r["ticker"]))
    both = set.intersection(*per.values())
    return sorted(both)


def build_events(combined: list[tuple[str, str]], cooldown: bool) -> list[dict]:
    last_seen: dict[str, str] = {}
    events = []
    for d, tk in combined:
        prev = last_seen.get(tk)
        last_seen[tk] = d
        if cooldown and prev and _days(prev, d) < COOLDOWN_DAYS:
            continue
        events.append({"date": d, "ticker": tk})
    return events


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def simulate(ev: dict, series: list[dict], bar_of: dict) -> dict | None:
    """None = sin barra de entrada todavía o sin datos."""
    sig_bar = bar_of.get((ev["ticker"], ev["date"]))
    if not sig_bar or not series:
        return None
    entry_i = next((i for i, x in enumerate(series) if x["_bar"] > sig_bar), None)
    if entry_i is None:
        return None
    entry = series[entry_i]
    res = {"sig_bar": sig_bar, "entry_i": entry_i, "entry_bar": entry["_bar"], "entry_price": float(entry["price"]),
           "status": "open", "exit_signal_bar": None}
    for i in range(entry_i + 1, len(series)):
        h = series[i].get("macdHist")
        if not _num(h) or h > 0:
            continue
        res["exit_signal_bar"] = series[i]["_bar"]
        res["exit_signal_i"] = i
        if i + 1 < len(series):
            x = series[i + 1]
            res.update(status="closed", exit_i=i + 1, exit_bar=x["_bar"], exit_price=float(x["price"]))
        else:
            res["status"] = "exit_pending"      # señal de salida emitida; la barra de ejecución aún no existe
        break
    last = series[res.get("exit_i", len(series) - 1)]
    res.update(last_bar=last["_bar"], last_price=float(last["price"]))
    return res


def run_portfolio(pid: str, cfg: dict, combined, bars, bar_of) -> list[tuple[dict, dict]]:
    out: list[tuple[dict, dict]] = []
    busy_until: dict[str, str | None] = {}      # ticker -> barra de salida (None = abierta)
    for ev in build_events(combined, cfg["cooldown"]):
        tk = ev["ticker"]
        s = simulate(ev, bars.get(tk, []), bar_of)
        if s is None:
            continue
        if tk in busy_until:
            ex = busy_until[tk]
            if ex is None or s["entry_bar"] <= ex:
                continue                         # posición abierta (o aún no posterior a la salida): se ignora
        busy_until[tk] = s.get("exit_bar") if s["status"] == "closed" else None
        out.append((ev, s))
    return out


# ── Salidas ─────────────────────────────────────────────────────────────────
def _scalars(row: dict) -> dict:
    return {k: v for k, v in row.items() if not isinstance(v, (list, dict)) and not k.startswith("_")}


def tracking_rows(pid, ev, s, series, pcs_idx) -> list[dict]:
    eid = f"{pid}|{ev['ticker']}|{ev['date']}"
    end_i = s.get("exit_i", len(series) - 1)
    rows = []
    for i in range(max(s["entry_i"] - 1, 0), end_i + 1):
        r = series[i]
        if i == s["entry_i"] - 1:
            role = "signal"
        elif i == s["entry_i"]:
            role = "entry"
        elif i == s.get("exit_i"):
            role = "exit"
        elif i == s.get("exit_signal_i"):
            role = "exit_signal"
        else:
            role = "hold"
        p = pcs_idx.get((r["_cap"], ev["ticker"]))
        rows.append({
            "portfolio": pid, "event_id": eid, "ticker": ev["ticker"], "bar": r["_bar"], "capture_date": r["_cap"],
            "role": role, "pcs": None if not p else p.get("pcs"),
            "pcs_normalized": None if not p else p.get("pcs_normalized"),
            "pcs_components": None if not p else p.get("components"),
            "pcs_signal": None if not p else p.get("signal"),
            "snapshot": _scalars(r),
        })
    return rows


def run(apply: bool, backfill_pcs: bool) -> int:
    if not SNAPSHOT.exists() or not LOG.exists():
        print("Falta portfolio_daily_snapshot.jsonl o screener_signal_log.jsonl — nada que hacer.")
        return 1
    print("[PCS log]", update_pcs_log(backfill_pcs, apply))
    pcs_idx = {(r["date"], r["ticker"]): r for r in load_pcs_log()}
    if not apply:   # en dry-run las filas nuevas no se han escrito: solo informativo
        pass

    bars, bar_of = load_snapshot()
    combined = load_combined_days()
    picks = json.loads(PICKS_JSON.read_text(encoding="utf-8")) if PICKS_JSON.exists() else {}
    all_tracking: list[dict] = []

    for pid, cfg in PORTFOLIOS.items():
        ptf = picks.setdefault("portfolios", {}).setdefault(pid, {"positions": [], "history": []})
        hist_ids = {h.get("event_id") for h in ptf.get("history", []) if h.get("event") == "close"}
        positions, new_closes = [], []
        for ev, s in run_portfolio(pid, cfg, combined, bars, bar_of):
            series = bars[ev["ticker"]]
            eid = f"{pid}|{ev['ticker']}|{ev['date']}"
            all_tracking += tracking_rows(pid, ev, s, series, pcs_idx)
            phase = "preregistered" if ev["date"] >= START_FORMAL else "backfill_exploratory"
            rec = {
                "ticker": ev["ticker"], "entry_date": s["entry_bar"], "entry_price": round(s["entry_price"], 4),
                "size_pct": SIZE_PCT, "entry_signal": "Cruce confirmado + Cerca de 0", "filter": "macd_combo",
                "signal_date": ev["date"], "signal_bar": s["sig_bar"], "event_id": eid, "phase": phase,
                "cooldown": cfg["cooldown"],
                "rationale": "Candidato a la vez de 'Cruce confirmado' y 'Cerca de 0' · entrada al cierre de la sesión "
                             "siguiente a la señal · salida al cruzar a la baja el histograma MACD (sin stops ni límite de días)",
            }
            if s["status"] == "closed":
                if eid not in hist_ids:
                    ret = (s["exit_price"] / s["entry_price"] - 1) * 100
                    new_closes.append({**rec, "event": "close", "close_date": s["exit_bar"],
                                       "close_price": round(s["exit_price"], 4), "close_reason": EXIT_REASON,
                                       "exit_signal_bar": s["exit_signal_bar"], "ret_pct": round(ret, 2)})
            else:
                positions.append({**rec, "last_bar": s["last_bar"], "last_price": round(s["last_price"], 4),
                                  "exit_signal_bar": s["exit_signal_bar"],
                                  "status": "exit_pending" if s["status"] == "exit_pending" else "open"})
        print(f"[{pid}] abiertas {len(positions)} · cerradas nuevas {len(new_closes)} · "
              f"ya en historial {len(hist_ids)}")
        for c in new_closes:
            print(f"  CLOSE {c['ticker']:10s} {c['ret_pct']:+.2f}% ({c['phase']})")
        for p in positions:
            print(f"  OPEN  {p['ticker']:10s} desde {p['entry_date']} ({p['phase']}){' · salida pendiente' if p['status']!='open' else ''}")
        if apply:
            ptf["positions"] = positions
            ptf.setdefault("history", []).extend(new_closes)

    if not apply:
        print(f"Dry-run (sin --apply). Filas de seguimiento que se escribirían: {len(all_tracking)}")
        return 0
    PICKS_JSON.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")
    with TRACKING.open("w", encoding="utf-8") as f:
        for r in all_tracking:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"ai_picks.json actualizado · {TRACKING.name}: {len(all_tracking)} filas")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(run(apply="--apply" in sys.argv, backfill_pcs="--backfill-pcs" in sys.argv))
