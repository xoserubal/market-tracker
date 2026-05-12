"""
Chat interactivo con el modelo de picks sobre el último análisis.

Uso:  py -3 scripts/chat_picks.py
      py -3 scripts/chat_picks.py --model anthropic/claude-sonnet-4.6
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DATA       = ROOT / "docs" / "data"
CHAT_MODEL = os.getenv("ACTIVE_MODEL", "x-ai/grok-4.3")


def _load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build_system_prompt() -> tuple[str, str]:
    """Returns (system_prompt, context_date)."""
    reasoning  = _load("ai_model_reasoning.json")
    picks      = _load("ai_picks.json")
    cands_data = _load("ai_candidates.json")

    ctx_date = reasoning.get("date", "sin datos")
    lines: list[str] = []

    lines += [
        "You are the AI portfolio manager of the AI Picks Lab, a quantitative paper "
        "trading system. You have just completed your latest market analysis and the user "
        "wants to discuss your reasoning, challenge your decisions, and explore scenarios.",
        "Answer in the same language the user writes in (Spanish or English).",
        "Be specific — cite real numbers from the context below, not generic labels.",
        "",
    ]

    # ── Latest run ────────────────────────────────────────────────────────────
    if reasoning.get("models"):
        lines.append(f"## Latest Analysis — {reasoning.get('date','?')} / {reasoning.get('run_id','?')}")
        for model, mr in reasoning["models"].items():
            ds = mr.get("decision_summary", {})
            short = model.split("/")[-1]
            lines.append(f"\n### Model: {short}  (Q={mr.get('quality_score','?')})")
            lines.append(f"Market read:  {ds.get('market_read','—')}")
            lines.append(f"Risk posture: {ds.get('risk_posture','—')}")
            lines.append(f"Counts: {len(mr.get('selected',[]))} selected / "
                         f"{len(mr.get('watch',[]))} watch / "
                         f"{len(mr.get('rejected',[]))} rejected")

            if mr.get("selected"):
                lines.append("\nSelected:")
                for s in mr["selected"]:
                    lines.append(
                        f"  {s['ticker']} → {s['portfolio']} ({s.get('confidence','')})"
                    )
                    lines.append(f"    {s.get('reason_full') or s.get('reason_short','')}")
                    if s.get("comparative_edge"):
                        lines.append(f"    vs peers: {s['comparative_edge']}")
                    if s.get("key_risks_or_contradictions"):
                        for r in s["key_risks_or_contradictions"]:
                            lines.append(f"    [!] {r}")

            if mr.get("watch"):
                lines.append("\nWatch:")
                for w in mr["watch"]:
                    lines.append(f"  {w['ticker']}: {w.get('reason','')}")
                    if w.get("watch_trigger"):
                        lines.append(f"    trigger: {w['watch_trigger']}")

            if mr.get("rejected"):
                lines.append("\nRejected:")
                for r in mr["rejected"]:
                    lines.append(
                        f"  {r['ticker']} ({r.get('rejection_category','')}): "
                        f"{r.get('reason','')}"
                    )

    # ── Open positions ────────────────────────────────────────────────────────
    lines.append("\n## Current Open Positions")
    found_any = False
    for ptf_id, ptf in picks.get("portfolios", {}).items():
        for p in ptf.get("positions", []):
            found_any = True
            lines.append(
                f"  [{ptf_id}] {p['ticker']}: entry={p.get('entry_date','?')} "
                f"PCS={p.get('entry_pcs','?')} conviction={p.get('conviction','?')} "
                f"size={p.get('size_pct','?')}%"
            )
            if p.get("rationale"):
                lines.append(f"    rationale: {p['rationale']}")
    if not found_any:
        lines.append("  (no open positions)")

    # ── Macro + candidates ───────────────────────────────────────────────────
    macro = cands_data.get("macro_context", {})
    if macro:
        lines += [
            "\n## Macro Context",
            f"  Score={macro.get('score','?')}  Regime={macro.get('regime','?')}  "
            f"Trend={macro.get('trend','?')}  Delta1w={macro.get('delta_1w','?')}",
        ]

    cands = sorted(
        cands_data.get("candidates", []),
        key=lambda x: x.get("pcs", 0), reverse=True,
    )[:15]
    if cands:
        lines.append("\n## Top Candidates (PCS desc)")
        for c in cands:
            ds  = c.get("daily_signals") or {}
            row = (
                f"  {c['ticker']:<10} PCS={c.get('pcs','?'):>5}  "
                f"elig={c.get('eligible','?')}  sig={c.get('signal','?'):<10}  "
                f"rot={c.get('rot_score','?')}  streak={c.get('streak_weeks','?')}w  "
                f"r4w={c.get('ret_4w_vs_spy','?')}%  r13w={c.get('ret_13w_vs_spy','?')}%"
            )
            if ds.get("daily_early_momentum_score") is not None:
                row += f"  dems={ds['daily_early_momentum_score']}"
            if ds.get("spike_flag"):
                row += "  spike!"
            lines.append(row)

    return "\n".join(lines), ctx_date


def main() -> None:
    global CHAT_MODEL
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if "--model" in args:
        idx = args.index("--model")
        if idx + 1 < len(args):
            CHAT_MODEL = args[idx + 1]

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("Error: OPENROUTER_API_KEY no está en .env", file=sys.stderr)
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/market-tracker",
            "X-Title":      "AI Picks Lab Chat",
        },
    )

    system, ctx_date = build_system_prompt()
    messages: list[dict] = [{"role": "system", "content": system}]

    sep = "-" * 58
    print(f"\n{sep}")
    print(f"  AI Picks Lab | Chat con {CHAT_MODEL.split('/')[-1]}")
    print(f"  Contexto: analisis del {ctx_date}")
    print(f"  'q' para salir  |  Ctrl+C para interrumpir")
    print(f"{sep}\n")

    while True:
        try:
            user_input = input("Tú > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("q", "quit", "exit", "salir"):
            print("Hasta luego.")
            break

        messages.append({"role": "user", "content": user_input})
        print(f"\n{CHAT_MODEL.split('/')[-1]} > ", end="", flush=True)

        try:
            stream = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                max_tokens=1024,
                stream=True,
            )
            response_text = ""
            for chunk in stream:
                delta = (chunk.choices[0].delta.content or "")
                print(delta, end="", flush=True)
                response_text += delta
            print("\n")
            messages.append({"role": "assistant", "content": response_text})

        except Exception as exc:
            print(f"\n[Error: {exc}]\n")
            messages.pop()


if __name__ == "__main__":
    main()
