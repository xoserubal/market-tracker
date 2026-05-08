"""
Paper Trading — AI Picks Lab
Calls Claude API with current market signals and portfolio state.
Produces structured buy/sell/size decisions for each portfolio mandate.

Inputs:
  docs/data/ai_candidates.json   (PCS scores)
  docs/data/ai_events.json       (signal events from event_detector.py)
  docs/data/ai_picks.json        (current open positions per portfolio)

Output:
  docs/data/ai_picks.json        (updated with new decisions)
  docs/data/ai_rejected.json     (high-score rejected picks for calibration)
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
DATA = ROOT / "docs" / "data"

MODEL = "claude-opus-4-7"  # Use most capable model for trading decisions

# Portfolio mandates
PORTFOLIOS = {
    "HIGH_CONVICTION": {
        "description": "Solo las oportunidades con más alta convicción. Calidad sobre cantidad.",
        "pcs_threshold":     85.0,
        "pcs_min_entry":     82.0,
        "max_positions":     8,
        "size_range":        (8, 15),   # % portfolio per position
        "target_ops_month":  1,
    },
    "CONFIRMED_FLOW_LEADERS": {
        "description": "Líderes con flujo confirmado en múltiples timeframes. Balance entre convicción y diversificación.",
        "pcs_threshold":     78.0,
        "pcs_min_entry":     75.0,
        "max_positions":     12,
        "size_range":        (5, 10),
        "target_ops_month":  4,
    },
    "EARLY_ROTATION": {
        "description": "Captura rotaciones tempranas antes de que sean obvias. Mayor riesgo, mayor upside.",
        "pcs_threshold":     70.0,
        "pcs_min_entry":     68.0,
        "max_positions":     15,
        "size_range":        (4, 8),
        "target_ops_month":  8,
    },
    "MACRO_THEMATIC_BENEFICIARIES": {
        "description": "Beneficiarios del régimen macro actual. Posiciones temáticas diversificadas.",
        "pcs_threshold":     65.0,
        "pcs_min_entry":     62.0,
        "max_positions":     20,
        "size_range":        (3, 6),
        "target_ops_month":  10,
    },
    "REJECTED_HIGH_SCORE": {
        "description": "Control: picks rechazados con PCS alto. Para medir el coste del filtro AI.",
        "pcs_threshold":     75.0,
        "pcs_min_entry":     75.0,
        "max_positions":     20,
        "size_range":        (5, 5),
        "target_ops_month":  5,
        "is_control": True,
    },
}

MAX_CANDIDATES_IN_PROMPT = 30  # Keep prompt focused


def _load(name: str) -> dict | list:
    p = DATA / name
    if not p.exists():
        return {} if name.endswith(".json") else []
    return json.loads(p.read_text(encoding="utf-8"))


def _write(name: str, data):
    (DATA / name).write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _build_candidates_text(candidates: list[dict], threshold: float) -> str:
    """Format top candidates for the prompt."""
    eligible = [c for c in candidates if c.get("eligible") and c.get("pcs", 0) >= threshold - 15]
    eligible.sort(key=lambda x: x["pcs"], reverse=True)
    top = eligible[:MAX_CANDIDATES_IN_PROMPT]

    lines = []
    for c in top:
        comp = c.get("pcs_components", {})
        lines.append(
            f"  {c['ticker']:12} PCS={c['pcs']:5.1f}  "
            f"theme={c.get('theme',''):20}  rot={c.get('rot_score','?')}  "
            f"sig={c.get('signal','?'):12}  "
            f"r4w={c.get('ret_4w_vs_spy','?'):6}  r13w={c.get('ret_13w_vs_spy','?'):6}  "
            f"early={c.get('is_early',False)}  "
            f"flags=[{','.join((c.get('flags') or [])[:4])}]"
        )
    return "\n".join(lines)


def _build_open_positions_text(picks: dict, portfolio_id: str) -> str:
    positions = picks.get("portfolios", {}).get(portfolio_id, {}).get("positions", [])
    if not positions:
        return "  (ninguna — cartera vacía)"
    lines = []
    for p in positions:
        lines.append(
            f"  {p['ticker']:12} entry_pcs={p.get('entry_pcs','?')}  "
            f"entry_date={p.get('entry_date','?')}  size={p.get('size_pct','?')}%  "
            f"entry_signal={p.get('entry_signal','?')}"
        )
    return "\n".join(lines)


def _build_events_text(events: list[dict]) -> str:
    if not events:
        return "  (ningún evento nuevo)"
    recent = [e for e in events if e.get("type") != "first_snapshot"][-20:]
    lines = []
    for e in recent:
        ticker = e.get("ticker", "—")
        lines.append(f"  [{e.get('type','?'):28}] {ticker:12} {e.get('detail', e.get('pcs',''))}")
    return "\n".join(lines) if lines else "  (sin eventos relevantes)"


def call_claude_for_portfolio(
    portfolio_id: str,
    mandate: dict,
    macro_context: dict,
    candidates: list[dict],
    picks: dict,
    events: list[dict],
    client: anthropic.Anthropic,
) -> dict:
    """Call Claude API and return structured decisions for one portfolio."""
    today = str(date.today())
    cands_text = _build_candidates_text(candidates, mandate["pcs_threshold"])
    open_pos_text = _build_open_positions_text(picks, portfolio_id)
    events_text = _build_events_text(events)
    open_positions = picks.get("portfolios", {}).get(portfolio_id, {}).get("positions", [])
    n_open = len(open_positions)
    max_pos = mandate["max_positions"]
    size_lo, size_hi = mandate["size_range"]

    system = """Eres un gestor de cartera cuantitativo disciplinado. Tu trabajo es revisar señales de mercado y tomar decisiones de compra/venta/tamaño para carteras de paper trading.

Siempre responde en JSON puro (sin markdown, sin texto extra). El JSON debe seguir exactamente el esquema indicado.

Principios:
- Solo actúas cuando hay convicción real. No operas por operar.
- El PCS (Pick Conviction Score) es la señal principal, pero debes interpretarla en contexto macro y de momentum.
- Las salidas las decides solo tú: no hay stop-loss automático. Si una posición ya no merece estar, la cierras.
- El tamaño refleja la convicción: mayor PCS → mayor tamaño dentro del rango del mandato."""

    user = f"""Fecha: {today}
Portfolio: {portfolio_id}
Mandato: {mandate['description']}
PCS mínimo entrada: {mandate['pcs_min_entry']}
Máximo posiciones: {max_pos} (actualmente {n_open} abiertas)
Tamaño por posición: {size_lo}–{size_hi}% del portfolio
Operaciones objetivo/mes: {mandate.get('target_ops_month', '?')}

CONTEXTO MACRO:
  Score={macro_context.get('score')}  Régimen={macro_context.get('regime')}
  Tendencia={macro_context.get('trend')}  Fase={macro_context.get('phase_quality')}
  Delta1W={macro_context.get('delta_1w')}  Delta1M={macro_context.get('delta_1m')}

EVENTOS DE SEÑAL (últimas 24h):
{events_text}

POSICIONES ABIERTAS:
{open_pos_text}

CANDIDATOS (PCS >= {mandate['pcs_threshold'] - 15:.0f}, ordenados por PCS):
{cands_text}

TAREA:
Revisa las posiciones abiertas: ¿alguna debe cerrarse? ¿ha perdido convicción, ha invertido señal, o hay una oportunidad mejor?
Luego decide si abrir nuevas posiciones. Solo abre si el PCS supera {mandate['pcs_min_entry']} y los eventos/momentum lo justifican.

Responde con este JSON exacto:
{{
  "portfolio": "{portfolio_id}",
  "date": "{today}",
  "macro_summary": "<1 frase sobre el régimen macro actual>",
  "decisions": [
    {{
      "action": "BUY" | "SELL" | "HOLD",
      "ticker": "<ticker>",
      "size_pct": <número entre {size_lo} y {size_hi}, solo para BUY>,
      "pcs": <número>,
      "conviction": "HIGH" | "MEDIUM" | "LOW",
      "rationale": "<1-2 frases concretas>"
    }}
  ],
  "no_action_reason": "<si decisions está vacío, explica por qué no actúas>"
}}

Solo incluye tickers con acción real (BUY o SELL). No incluyas HOLD en la lista.
Para BUYs: solo tickers con PCS >= {mandate['pcs_min_entry']}.
Para SELLs: solo posiciones actualmente abiertas que deben cerrarse."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "portfolio": portfolio_id,
            "date": today,
            "error": "JSON parse failed",
            "raw": raw[:500],
            "decisions": [],
        }


def apply_decisions(picks: dict, result: dict) -> dict:
    """Apply Claude's decisions to the picks state."""
    portfolio_id = result["portfolio"]
    today = result["date"]
    decisions = result.get("decisions", [])

    if "portfolios" not in picks:
        picks["portfolios"] = {}
    if portfolio_id not in picks["portfolios"]:
        picks["portfolios"][portfolio_id] = {"positions": [], "history": []}

    positions = picks["portfolios"][portfolio_id]["positions"]
    history   = picks["portfolios"][portfolio_id].setdefault("history", [])

    pos_by_ticker = {p["ticker"]: p for p in positions}

    for d in decisions:
        action = d.get("action", "").upper()
        ticker = d.get("ticker", "")
        if not ticker:
            continue

        if action == "BUY" and ticker not in pos_by_ticker:
            new_pos = {
                "ticker":        ticker,
                "entry_date":    today,
                "entry_pcs":     d.get("pcs"),
                "entry_signal":  None,
                "size_pct":      d.get("size_pct"),
                "conviction":    d.get("conviction"),
                "rationale":     d.get("rationale"),
            }
            positions.append(new_pos)
            history.append({**new_pos, "event": "open"})

        elif action == "SELL" and ticker in pos_by_ticker:
            closed = pos_by_ticker.pop(ticker)
            history.append({
                **closed,
                "event":       "close",
                "exit_date":   today,
                "exit_pcs":    d.get("pcs"),
                "exit_reason": d.get("rationale"),
            })
            positions[:] = [p for p in positions if p["ticker"] != ticker]

    # Save latest Claude output
    picks["portfolios"][portfolio_id]["last_review"] = {
        "date":          today,
        "macro_summary": result.get("macro_summary"),
        "no_action_reason": result.get("no_action_reason"),
        "raw_decisions": decisions,
    }
    return picks


def run(force: bool = False):
    """
    force=True: run even if no events (useful for initial population or manual trigger).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping paper trading")
        return

    events_data = _load("ai_events.json")
    if isinstance(events_data, dict):
        events_data = []

    # Only run if there are new events (or forced)
    today = str(date.today())
    todays_events = [e for e in events_data if e.get("date") == today]

    if not todays_events and not force:
        print("No new events today — skipping Claude API call")
        return

    cands_data = _load("ai_candidates.json")
    candidates = cands_data.get("candidates", [])
    macro_context = cands_data.get("macro_context", {})

    picks = _load("ai_picks.json")
    if not isinstance(picks, dict):
        picks = {}

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Running paper trading ({len(todays_events)} events, {len(candidates)} candidates)...")

    for portfolio_id, mandate in PORTFOLIOS.items():
        if mandate.get("is_control"):
            continue  # Control portfolio handled separately
        print(f"  {portfolio_id}...", end=" ", flush=True)
        try:
            result = call_claude_for_portfolio(
                portfolio_id, mandate, macro_context,
                candidates, picks, todays_events, client,
            )
            picks = apply_decisions(picks, result)
            n_dec = len(result.get("decisions", []))
            print(f"{n_dec} decisions")
        except Exception as e:
            print(f"ERROR: {e}")

    picks["last_updated"] = today
    _write("ai_picks.json", picks)
    print(f"ai_picks.json updated")


if __name__ == "__main__":
    force = "--force" in sys.argv
    run(force=force)
