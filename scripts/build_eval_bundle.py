"""
Genera un bundle JSON listo para pasar a un evaluador externo.

El bundle contiene TODO lo que el evaluador necesita para juzgar la calidad
del razonamiento de Grok: reglas, datos de input, decisiones, y rúbrica.

Uso:
    py -3 scripts/build_eval_bundle.py
    py -3 scripts/build_eval_bundle.py --out mi_bundle.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ai_shared import HARD_RULES, compact_candidate as _compact_candidate

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

PORTFOLIOS = {
    "HIGH_CONVICTION": {
        "description":   "Solo las oportunidades con más alta convicción. Calidad sobre cantidad.",
        "pcs_threshold": 85.0,
        "pcs_min_entry": 82.0,
        "max_positions": 8,
        "size_range":    [8, 15],
    },
    "CONFIRMED_FLOW_LEADERS": {
        "description":   "Líderes con flujo confirmado en múltiples timeframes.",
        "pcs_threshold": 78.0,
        "pcs_min_entry": 75.0,
        "max_positions": 12,
        "size_range":    [5, 10],
    },
    "EARLY_ROTATION": {
        "description":   "Captura rotaciones tempranas antes de que sean obvias.",
        "pcs_threshold": 70.0,
        "pcs_min_entry": 68.0,
        "max_positions": 15,
        "size_range":    [4, 8],
    },
    "MACRO_THEMATIC_BENEFICIARIES": {
        "description":   "Beneficiarios del régimen macro actual.",
        "pcs_threshold": 65.0,
        "pcs_min_entry": 62.0,
        "max_positions": 20,
        "size_range":    [3, 6],
    },
}

REASONING_STYLE_RULES = [
    "Do NOT repeat input field names as reasoning (e.g. 'pcs_above_threshold', 'rs_strong_leader' are labels, not analysis).",
    "Write complete sentences citing actual numbers from the payload.",
    "reason_full must answer: why THIS ticker over the other high-PCS candidates NOT selected?",
    "comparative_edge must explicitly name at least one candidate NOT selected and state why it ranked lower.",
    "key_supporting_factors and key_risks_or_contradictions must each have 3–5 items with real numbers.",
]

DAILY_SIGNALS_RULES = [
    "dems (Daily Early Momentum Score 0-20): primary signal for EARLY_ROTATION only.",
    "dems >= 14 + spike_flag=false → can SELECT if PCS >= 68.",
    "dems 10-13 → prefer WATCH over SELECT.",
    "spike_flag=true → prefer WATCH unless outperform_d10 >= 6.",
    "For HIGH_CONVICTION and CONFIRMED_FLOW_LEADERS: weekly metrics (ret_4w, ret_13w, streak_weeks) are primary. Ignore dems.",
]

EVALUATION_RUBRIC = {
    "description": "Preguntas que el evaluador debe responder sobre el razonamiento de Grok.",
    "categories": {
        "hard_rule_compliance": {
            "weight": 30,
            "questions": [
                "¿Seleccionó solo tickers con eligible=true?",
                "¿Todos los candidatos con PCS >= 62 aparecen en selected, watch o rejected?",
                "¿Cada selected tiene reason_short, reason_full, comparative_edge y los campos requeridos?",
                "¿Cada rejected tiene reason y rejection_category válida?",
            ],
        },
        "reasoning_quality": {
            "weight": 35,
            "questions": [
                "¿El reasoning cita números reales (%, streaks, scores) o solo repite etiquetas del payload?",
                "¿El reason_full explica por qué ESE ticker sobre los otros de alta PCS?",
                "¿El comparative_edge nombra explícitamente al menos un peer y explica la diferencia en métricas concretas?",
                "¿Los watch_trigger son específicos y medibles (no vagas como 'si mejora')?",
            ],
        },
        "decision_consistency": {
            "weight": 25,
            "questions": [
                "¿Los tickers en HIGH_CONVICTION tienen PCS >= 82 y señales suficientemente fuertes?",
                "¿Las decisiones WATCH vs SELECT son consistentes con los umbrales de los portfolios?",
                "¿Las señales de riesgo (spike_flag, dist_52w_high) se reflejan en las decisiones?",
                "¿El market_read del decision_summary es coherente con las decisiones individuales?",
            ],
        },
        "coverage_and_balance": {
            "weight": 10,
            "questions": [
                "¿El número de SELECTs es apropiado para el régimen macro (Bull Maduro Improving)?",
                "¿Se justifica adecuadamente por qué no se seleccionaron más tickers?",
                "¿Los REJECTs tienen categorías correctas según las razones dadas?",
            ],
        },
    },
    "scoring_scale": "0-10 por pregunta. Multiplica por el peso de la categoría para el score total.",
    "output_requested": (
        "Para cada categoría: score (0-10), justificación breve, ejemplos específicos de lo que "
        "hizo bien o mal Grok. Al final: score_total/100 y recomendación de mejora principal."
    ),
}


def _load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build_bundle() -> dict:
    reasoning  = _load("ai_model_reasoning.json")
    cands_data = _load("ai_candidates.json")
    picks      = _load("ai_picks.json")
    prev       = _load("ai_candidates_prev.json")

    run_date   = reasoning.get("date", "?")
    run_id     = reasoning.get("run_id", "?")

    # ── Candidatos que recibió Grok (elegibles, top por PCS, máx 15) ──────────
    eligible = sorted(
        [c for c in cands_data.get("candidates", []) if c.get("eligible")],
        key=lambda x: x.get("pcs", 0), reverse=True,
    )[:15]

    # ── Contexto de posiciones abiertas al momento de la decisión ─────────────
    open_positions = [
        {**pos, "portfolio": pid}
        for pid, ptf in picks.get("portfolios", {}).items()
        for pos in ptf.get("positions", [])
    ]

    # ── Contexto previo (si hay fecha distinta) ────────────────────────────────
    prev_context = None
    if prev and prev.get("date") and prev.get("date") != run_date:
        prev_macro = prev.get("macro_context", {})
        prev_eligible = sorted(
            [c for c in prev.get("candidates", []) if c.get("eligible")],
            key=lambda x: x.get("pcs", 0), reverse=True,
        )[:15]
        prev_context = {
            "date":          prev.get("date"),
            "macro_context": prev_macro,
            "top_candidates": [_compact_candidate(c) for c in prev_eligible],
        }

    # ── Razonamiento por modelo ────────────────────────────────────────────────
    models_reasoning = {}
    for model_id, mr in (reasoning.get("models") or {}).items():
        models_reasoning[model_id] = {
            "quality_score":    mr.get("quality_score"),
            "decision_summary": mr.get("decision_summary"),
            "selected":         mr.get("selected", []),
            "watch":            mr.get("watch", []),
            "rejected":         mr.get("rejected", []),
        }

    bundle = {
        "bundle_meta": {
            "purpose": (
                "Evaluación de calidad del razonamiento de modelos de IA para selección "
                "de picks en un sistema de paper trading cuantitativo."
            ),
            "analysis_date": run_date,
            "run_id":        run_id,
            "generated_at":  datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "models_evaluated": list(models_reasoning.keys()),
        },

        "system_rules": {
            "description": "Reglas que el modelo debía seguir al generar sus decisiones.",
            "portfolio_mandates":    PORTFOLIOS,
            "hard_rules":            HARD_RULES,
            "reasoning_style_rules": REASONING_STYLE_RULES,
            "daily_signals_rules":   DAILY_SIGNALS_RULES,
        },

        "input_context": {
            "description":    "Datos que el modelo recibió como input para tomar sus decisiones.",
            "macro_context":  cands_data.get("macro_context", {}),
            "universe_summary": cands_data.get("summary", {}),
            "candidates_sent_to_model": [_compact_candidate(c) for c in eligible],
            "open_positions_at_decision": open_positions,
        },

        "previous_snapshot": prev_context,

        "model_decisions": models_reasoning,

        "evaluation_rubric": EVALUATION_RUBRIC,
    }

    return bundle


def main() -> None:
    args = sys.argv[1:]
    out_name = "eval_bundle_latest.json"
    if "--out" in args:
        idx = args.index("--out")
        if idx + 1 < len(args):
            out_name = args[idx + 1]

    bundle = build_bundle()

    run_date = bundle["bundle_meta"]["analysis_date"]
    run_id   = bundle["bundle_meta"]["run_id"]
    models   = bundle["bundle_meta"]["models_evaluated"]
    n_cands  = len(bundle["input_context"]["candidates_sent_to_model"])

    out_path = DATA / out_name
    out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Bundle generado: {out_path}")
    print(f"  Análisis:   {run_date} / {run_id}")
    print(f"  Modelos:    {', '.join(m.split('/')[-1] for m in models)}")
    print(f"  Candidatos: {n_cands} enviados al modelo")
    for model_id, mr in bundle["model_decisions"].items():
        short = model_id.split("/")[-1]
        sel   = len(mr.get("selected", []))
        wat   = len(mr.get("watch", []))
        rej   = len(mr.get("rejected", []))
        print(f"  [{short}]  {sel} selected / {wat} watch / {rej} rejected  "
              f"(Q={mr.get('quality_score','?')})")

    print(f"\nPasa este archivo al evaluador junto con el prompt:")
    print(f'  "Evalúa la calidad del razonamiento usando la rúbrica en evaluation_rubric. '
          f'Puntúa cada categoría 0-10 y da un score_total/100 con recomendación principal."')


if __name__ == "__main__":
    main()
