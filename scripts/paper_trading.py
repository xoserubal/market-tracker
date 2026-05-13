"""
Paper Trading + Model A/B Test Framework — AI Picks Lab

Reads:
  docs/data/ai_events.json        (signal events)
  docs/data/ai_candidates.json    (PCS scores + macro context)
  docs/data/ai_picks.json         (current open positions)

Writes:
  docs/data/ai_model_payloads/YYYY-MM-DD.json     common payload (one per day)
  docs/data/model_tests/YYYY-MM-DD_{model}.json   full result per model
  docs/data/ai_model_test_summary.jsonl            one line per call (append)
  docs/data/shadow_picks.jsonl                     all picks for perf tracking
  docs/data/ai_picks.json                          updated by active_model only

Env vars (add to .env or GitHub Secrets):
  ANTHROPIC_API_KEY
  XAI_API_KEY
  AI_MODEL_TEST_MODE        true|false        (default: true)
  AI_MODELS_TO_TEST         JSON list         (default: ["claude-haiku-4-5-20251001"])
  ACTIVE_MODEL              model id          (default: claude-haiku-4-5-20251001)
  FALLBACK_MODEL            model id          (default: claude-haiku-4-5-20251001)
  ENABLE_SHADOW_MODELS      true|false        (default: true)
  MAX_CANDIDATES_PER_CALL   int               (default: 15)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DATA        = ROOT / "docs" / "data"
PAYLOAD_DIR   = DATA / "ai_model_payloads"
TESTS_DIR     = DATA / "model_tests"
SUMMARY_LOG   = DATA / "ai_model_test_summary.jsonl"
SHADOW_LOG    = DATA / "shadow_picks.jsonl"
BASELINES_LOG = DATA / "baselines.jsonl"

# ── Pricing  (USD / 1M tokens) — OpenRouter prices: openrouter.ai/models ──────
# Use OpenRouter model slugs as keys (e.g. "anthropic/claude-haiku-4-5-20251001")
# Defaults to (0.0, 0.0) for unknown models — cost shows as $0 until filled in.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "anthropic/claude-haiku-4.5":  (1.00,  5.00),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
    "anthropic/claude-opus-4.7":   (15.00, 75.00),
    "x-ai/grok-4.3":                       (1.25,  2.50),
    "x-ai/grok-4.2":                       (0.0,   0.0),  # TODO: fill from openrouter.ai/models
}

PORTFOLIOS: dict[str, dict] = {
    "HIGH_CONVICTION": {
        "description":      "Solo las oportunidades con más alta convicción. Calidad sobre cantidad.",
        "pcs_threshold":    85.0,
        "pcs_min_entry":    82.0,
        "max_positions":    8,
        "size_range":       (8, 15),
        "target_ops_month": 1,
    },
    "CONFIRMED_FLOW_LEADERS": {
        "description":      "Líderes con flujo confirmado en múltiples timeframes.",
        "pcs_threshold":    78.0,
        "pcs_min_entry":    75.0,
        "max_positions":    12,
        "size_range":       (5, 10),
        "target_ops_month": 4,
    },
    "EARLY_ROTATION": {
        "description":      "Captura rotaciones tempranas antes de que sean obvias.",
        "pcs_threshold":    70.0,
        "pcs_min_entry":    68.0,
        "max_positions":    15,
        "size_range":       (4, 8),
        "target_ops_month": 8,
    },
    "MACRO_THEMATIC_BENEFICIARIES": {
        "description":      "Beneficiarios del régimen macro actual.",
        "pcs_threshold":    65.0,
        "pcs_min_entry":    62.0,
        "max_positions":    20,
        "size_range":       (3, 6),
        "target_ops_month": 10,
    },
    "REJECTED_HIGH_SCORE": {
        "description":      "Control: picks rechazados con PCS alto.",
        "pcs_threshold":    75.0,
        "pcs_min_entry":    75.0,
        "max_positions":    20,
        "size_range":       (5, 5),
        "target_ops_month": 5,
        "is_control":       True,
    },
}

HARD_RULES = [
    "Only SELECT tickers present in the candidates list.",
    "Only SELECT tickers with eligible=true.",
    "Do not SELECT futures, commodities, or macro indices directly.",
    "If a signal comes from a commodity/macro theme, SELECT the related stock or ETF.",
    "Do not fill portfolios with mediocre picks — empty selected list is valid.",
    "Return valid JSON only. No markdown, no explanation, no extra text.",
    "Do not invent data not present in the payload. If prev_snapshot_available=false, do not speculate on PCS or score changes between weeks.",
    "With strong contradictions, use WATCH or REJECT, not SELECT.",
    "Every selected item must have: portfolio, signal_type, confidence, reason_short (≥20 chars), reason_full (≥100 chars), comparative_edge (≥30 chars, must name at least one peer candidate and explain why it ranked lower).",
    "Every rejected item must have: reason and a valid rejection_category.",
    "Every candidate with pcs >= 62 that you do not SELECT must appear in watch or rejected with a reason.",
    "Do not SELECT a ticker already present in active_picks_relevant — it is already an open position. Mention it in decision_summary if still relevant, but do not add it to selected.",
    "For HIGH_CONVICTION and CONFIRMED_FLOW_LEADERS portfolios, do not REJECT based primarily on dems or spike_flag when weekly metrics (ret_4w_vs_spy, ret_13w_vs_spy, streak_weeks) are strong. Use WATCH instead.",
]

NON_TRADABLE_SUBTHEMES = frozenset({
    "futures", "commodity", "macro_index", "crude_oil_leveraged",
})

VALID_PORTFOLIOS = frozenset(PORTFOLIOS) - {"REJECTED_HIGH_SCORE"}

VALID_REJECT_CATS = frozenset({
    "insufficient_conviction", "macro_conflict", "weak_flow",
    "weak_relative_strength", "technical_overextension", "data_quality",
    "not_tradable", "better_alternative_available",
})

REQUIRED_RESPONSE_KEYS = {"date", "decision_summary", "selected", "watch", "rejected"}


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class Config:
    test_mode:            bool      = True
    models_to_test:       list[str] = field(default_factory=lambda: ["claude-haiku-4-5-20251001"])
    active_model:         str       = "claude-haiku-4-5-20251001"
    fallback_model:       str       = "claude-haiku-4-5-20251001"
    enable_shadow_models: bool      = True
    max_candidates:       int       = 15

    @classmethod
    def from_env(cls) -> Config:
        test_mode = os.getenv("AI_MODEL_TEST_MODE", "true").lower() == "true"
        default_model = "anthropic/claude-haiku-4.5"
        try:
            models = json.loads(os.getenv("AI_MODELS_TO_TEST", f'["{default_model}"]'))
        except json.JSONDecodeError:
            models = [default_model]
        return cls(
            test_mode=test_mode,
            models_to_test=models,
            active_model=os.getenv("ACTIVE_MODEL",   default_model),
            fallback_model=os.getenv("FALLBACK_MODEL", default_model),
            enable_shadow_models=os.getenv("ENABLE_SHADOW_MODELS", "true").lower() == "true",
            max_candidates=int(os.getenv("MAX_CANDIDATES_PER_CALL", "15")),
        )


# ── I/O helpers ────────────────────────────────────────────────────────────────

def _load(name: str) -> Any:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Payload builder ────────────────────────────────────────────────────────────

def _compact_candidate(c: dict) -> dict:
    ds = c.get("daily_signals") or {}
    return {
        "ticker":         c["ticker"],
        "name":           c.get("name", ""),
        "theme":          c.get("theme", ""),
        "subtheme":       c.get("subtheme", ""),
        "pcs":            c.get("pcs"),
        "eligible":       c.get("eligible"),
        "signal":         c.get("signal"),
        "rot_score":      c.get("rot_score"),
        "ret_4w_vs_spy":  c.get("ret_4w_vs_spy"),
        "ret_13w_vs_spy": c.get("ret_13w_vs_spy"),
        "streak_weeks":   c.get("streak_weeks"),
        "dist_52w_high":  c.get("dist_52w_high"),
        "is_early":       c.get("is_early", False),
        "flags":          (c.get("flags") or [])[:5],
        # Daily signals — populated only when pcs_calculator fetched prices
        "dems":           ds.get("daily_early_momentum_score"),
        "ret_5d_vs_spy":  ds.get("ret_5d_vs_spy"),
        "ret_10d_vs_spy": ds.get("ret_10d_vs_spy"),
        "outperform_d10": ds.get("outperform_days_10d"),
        "streak_days":    ds.get("streak_days"),
        "momentum_accel": ds.get("momentum_accel"),
        "vol_5d_20d":     ds.get("vol_5d_vs_20d"),
        "spike_flag":     ds.get("spike_flag"),
    }


def build_payload(
    cands_data: dict,
    events: list[dict],
    picks: dict,
    config: Config,
) -> dict:
    macro    = cands_data.get("macro_context", {})
    eligible = sorted(
        [c for c in cands_data.get("candidates", []) if c.get("eligible")],
        key=lambda x: x.get("pcs", 0),
        reverse=True,
    )[:config.max_candidates]

    prev_data = _load("ai_candidates_prev.json")
    prev_date = prev_data.get("date") if prev_data else None
    prev_snapshot_available = bool(prev_date and prev_date != cands_data.get("date"))

    active_positions = [
        {**pos, "portfolio": pid}
        for pid, ptf in picks.get("portfolios", {}).items()
        for pos in ptf.get("positions", [])
    ]

    mandates = {
        pid: {k: v for k, v in m.items() if k != "is_control"}
        for pid, m in PORTFOLIOS.items()
        if not m.get("is_control")
    }

    meaningful_events = [
        e for e in events if e.get("type") != "first_snapshot"
    ][-30:]

    return {
        "date": str(date.today()),
        "system_context": {
            "project":   "AI Picks Lab",
            "objective": "select high-conviction paper-trading picks from prefiltered quantitative events",
            "hard_rules": HARD_RULES,
            "prev_snapshot_available": prev_snapshot_available,
        },
        "macro_context": {
            "macro_score":    macro.get("score"),
            "macro_regime":   macro.get("regime"),
            "macro_trend":    macro.get("trend"),
            "macro_delta_1w": macro.get("delta_1w"),
            "macro_delta_1m": macro.get("delta_1m"),
            "phase_quality":  macro.get("phase_quality"),
        },
        "portfolio_mandates":       mandates,
        "events":                   meaningful_events,
        "candidates":               [_compact_candidate(c) for c in eligible],
        "active_picks_relevant":    active_positions,
        "recent_rejected_relevant": [],
    }


# ── Prompt ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a disciplined quantitative portfolio manager for a paper trading system.

TASK: Review the market signals in the payload and return a structured JSON decision.

CRITICAL: Respond ONLY with valid JSON — no markdown fences, no explanation, \
no text before or after the JSON object.

HARD RULES (violations are flagged automatically):
1. Only SELECT tickers present in candidates with eligible=true.
2. Do not SELECT futures, commodities, or macro indices.
3. Empty selected list is valid — do not fill portfolios with mediocre picks.
4. Use WATCH for uncertain/incomplete signals; REJECT for clearly insufficient ones.
5. Do not invent data. Use only information from the payload.
6. Every selected item needs: portfolio, signal_type, confidence, \
reason_short (≥20 chars), reason_full (≥100 chars), comparative_edge (≥30 chars).
7. Every rejected item needs: reason and a valid rejection_category.
8. Every candidate with pcs >= 62 not selected must appear in watch or rejected.

REASONING STYLE (applies to all text fields in selected, watch, rejected):
- Do not use input field names or flag labels as content. "rs_strong_leader",
  "pcs_above_threshold", "macro_improving" are data labels from the payload,
  not reasoning. A label repeated back is not analysis.
- Write complete sentences a portfolio manager could read aloud. Cite the actual
  numbers, not the category names.
  BAD:  ["pcs_above_threshold", "rs_strong_leader", "macro_improving"]
  GOOD: ["13-week return of +93% vs SPY (highest in the candidate set)",
         "Rotation score 8/10 with 6 consecutive weeks of outperformance",
         "Macro delta improving 3 weeks in a row supports the crypto theme"]
- key_supporting_factors and key_risks_or_contradictions must each have 3–5
  items written as full, specific sentences with real numbers from the payload.

COMPARATIVE REASONING (mandatory — most common failure mode):
- "PCS = 81 exceeds threshold of 82" is NOT a valid reason. PCS is a pre-filter;
  every candidate in the list already cleared minimum eligibility. Repeating the
  threshold is noise, not analysis.
- reason_full must answer: "Why THIS ticker over the other high-PCS candidates
  I did NOT select?" Cite specific differentiating metrics: streak_weeks vs peers,
  rot_score vs peers, ret_13w_vs_spy vs peers, spike_flag, momentum_accel, dems.
- comparative_edge must explicitly name at least one candidate you did NOT select
  and state why it ranked lower on the deciding factors.
  BAD:  "Strong relative strength and high PCS."
  GOOD: "Selected over MARA (PCS=80) because streak_weeks=12 vs MARA's 2 and
         rot_score=9 vs MARA's 4. MARA rejected as better_alternative_available."
- Every candidate with pcs >= 62 that you do not SELECT must appear in watch or
  rejected — silence on a high-PCS candidate is not acceptable.

EARLY_ROTATION — daily signals guidance (dems, ret_5d_vs_spy, etc.):
- dems (Daily Early Momentum Score 0-20): PRIMARY signal for EARLY_ROTATION.
  dems >= 14 + spike_flag=false → can SELECT if PCS >= 68.
  dems 10-13 → prefer WATCH over SELECT.
  dems < 10 → do not use daily momentum as the primary reason to SELECT.
- spike_flag=true means most of the 5d move came from one day. Prefer WATCH, \
not SELECT, unless there is clear multi-day continuation (outperform_d10 >= 6).
- outperform_d10 >= 6 is more robust than streak_days alone: it allows small \
pauses without invalidating the setup.
- For HIGH_CONVICTION and CONFIRMED_FLOW_LEADERS, weekly metrics (ret_4w, \
ret_13w, streak_weeks) are the primary signal. Ignore dems for these portfolios.

REQUIRED OUTPUT SCHEMA (fill in all fields):
{
  "date": "YYYY-MM-DD",
  "model": "<model_name>",
  "run_id": "<run_id>",
  "decision_summary": {
    "market_read": "<1 sentence on current regime>",
    "risk_posture": "aggressive|normal|cautious|defensive",
    "should_select_picks": true|false
  },
  "selected": [
    {
      "ticker": "<ticker>",
      "portfolio": "HIGH_CONVICTION|CONFIRMED_FLOW_LEADERS|EARLY_ROTATION|MACRO_THEMATIC_BENEFICIARIES",
      "signal_type": "confirmed_leader|early_rotation|macro_thematic|high_conviction",
      "confidence": "low|medium|high",
      "reason_short": "<specific, ≥20 chars>",
      "reason_full": "<≥100 chars: what drives this ticker's signal strength right now>",
      "comparative_edge": "<≥30 chars: name a peer with similar PCS you did NOT select and explain why this ranked higher on the deciding metrics>",
      "key_supporting_factors": ["<string>"],
      "key_risks_or_contradictions": ["<string>"]
    }
  ],
  "watch": [
    {
      "ticker": "<ticker>",
      "reason": "<why watching, not selecting>",
      "watch_trigger": "<what would make this a SELECT>"
    }
  ],
  "rejected": [
    {
      "ticker": "<ticker>",
      "reason": "<why rejected>",
      "rejection_category": \
"insufficient_conviction|macro_conflict|weak_flow|weak_relative_strength|\
technical_overextension|data_quality|not_tradable|better_alternative_available"
    }
  ]
}"""


def compute_baselines(cands_data: dict, n: int = 3) -> dict:
    """Computes simple mechanical baselines to compare against AI picks."""
    eligible = [c for c in cands_data.get("candidates", []) if c.get("eligible")]

    def top_n(key: str) -> list[dict]:
        ranked = sorted(
            [c for c in eligible if c.get(key) is not None],
            key=lambda x: x.get(key, 0), reverse=True,
        )
        return [{"ticker": c["ticker"], "value": c.get(key)} for c in ranked[:n]]

    return {
        "top_pcs":       top_n("pcs"),
        "top_rot_score": top_n("rot_score"),
        "top_ret_4w":    top_n("ret_4w_vs_spy"),
        "top_ret_13w":   top_n("ret_13w_vs_spy"),
    }


def build_user_message(payload: dict, model: str, run_id: str) -> str:
    annotated = dict(payload)
    annotated["_meta"] = {
        "model":       model,
        "run_id":      run_id,
        "instruction": "Set model and run_id fields in your JSON response to these values.",
    }
    return json.dumps(annotated, ensure_ascii=False, indent=2)


# ── Model caller ───────────────────────────────────────────────────────────────

def call_model(
    model: str,
    system: str,
    user_message: str,
    max_tokens: int = 2048,
) -> tuple[str, int, int, float]:
    """Returns (raw_text, input_tokens, output_tokens, latency_ms).

    All models are routed through OpenRouter (openrouter.ai).
    Use OpenRouter model slugs, e.g. "anthropic/claude-haiku-4-5-20251001".
    """
    from openai import OpenAI
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/market-tracker",
            "X-Title":      "AI Picks Lab",
        },
    )
    t0   = time.monotonic()
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_message},
        ],
    )
    text    = resp.choices[0].message.content
    in_tok  = resp.usage.prompt_tokens
    out_tok = resp.usage.completion_tokens
    return text, in_tok, out_tok, (time.monotonic() - t0) * 1000


def compute_cost(model: str, in_tok: int, out_tok: int) -> float:
    in_p, out_p = MODEL_PRICING.get(model, (0.0, 0.0))
    return (in_tok * in_p + out_tok * out_p) / 1_000_000


def parse_response(raw: str) -> tuple[dict | None, bool]:
    """Strip markdown fences and parse JSON. Returns (data, json_valid)."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    if not text.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", text)
        text = m.group(0) if m else text
    try:
        return json.loads(text), True
    except json.JSONDecodeError:
        return None, False


# ── Validator ──────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    json_valid:             bool       = False
    schema_valid:           bool       = False
    hard_rule_violations:   int        = 0
    violations_detail:      list[str]  = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.hard_rule_violations += 1
        self.violations_detail.append(msg)


def validate_model_response(
    data: dict | None,
    payload: dict,
    json_valid: bool,
) -> ValidationResult:
    r = ValidationResult(json_valid=json_valid)
    if not json_valid or data is None:
        return r

    if REQUIRED_RESPONSE_KEYS - set(data.keys()):
        r.add(f"Missing top-level keys: {REQUIRED_RESPONSE_KEYS - set(data.keys())}")
        return r
    r.schema_valid = True

    cand_tickers = {c["ticker"] for c in payload.get("candidates", [])}
    eligible     = {c["ticker"] for c in payload.get("candidates", []) if c.get("eligible")}
    non_tradable = {
        c["ticker"] for c in payload.get("candidates", [])
        if c.get("subtheme", "") in NON_TRADABLE_SUBTHEMES
    }
    cand_pcs_map = {c["ticker"]: c.get("pcs", 0.0) for c in payload.get("candidates", [])}
    open_tickers = {p.get("ticker") for p in payload.get("active_picks_relevant", [])}

    seen: set[str]           = set()
    ptf_counts: dict[str, int] = {}

    for s in data.get("selected", []):
        t = s.get("ticker", "")
        if t in seen:              r.add(f"Duplicate ticker: {t}")
        seen.add(t)
        if t not in cand_tickers:  r.add(f"SELECT {t}: not in candidates")
        if t not in eligible:      r.add(f"SELECT {t}: not eligible")
        if t in non_tradable:      r.add(f"SELECT {t}: non-tradable subtheme")
        if t in open_tickers:      r.add(f"SELECT {t}: already an open position (use HOLD, not SELECT)")
        ptf = s.get("portfolio", "")
        if ptf not in VALID_PORTFOLIOS:
            r.add(f"SELECT {t}: invalid portfolio '{ptf}'")
        if len(str(s.get("reason_short", ""))) < 10:
            r.add(f"SELECT {t}: reason_short too short")
        if len(str(s.get("reason_full",  ""))) < 30:
            r.add(f"SELECT {t}: reason_full too short")
        ptf_counts[ptf] = ptf_counts.get(ptf, 0) + 1
        max_p = PORTFOLIOS.get(ptf, {}).get("max_positions", 999)
        if ptf_counts[ptf] > max_p:
            r.add(f"Portfolio {ptf}: exceeds max_positions ({max_p})")
        pcs_min = PORTFOLIOS.get(ptf, {}).get("pcs_min_entry", 0)
        if ptf in VALID_PORTFOLIOS and pcs_min > 0:
            ticker_pcs = cand_pcs_map.get(t, 0.0)
            if ticker_pcs < pcs_min:
                r.add(f"SELECT {t}: PCS {ticker_pcs} below {ptf} minimum ({pcs_min})")

    for w in data.get("watch", []):
        t = w.get("ticker", "")
        if t in seen: r.add(f"Duplicate ticker: {t}")
        seen.add(t)

    for rj in data.get("rejected", []):
        t = rj.get("ticker", "")
        if t in seen: r.add(f"Duplicate ticker: {t}")
        seen.add(t)
        cat = rj.get("rejection_category", "")
        if cat not in VALID_REJECT_CATS:
            r.add(f"REJECT {t}: invalid rejection_category '{cat}'")

    return r


# ── Quality scorer ─────────────────────────────────────────────────────────────

def compute_quality_score(
    data: dict | None,
    v: ValidationResult,
    payload: dict,
) -> int:
    if not v.json_valid or data is None:
        return 0

    score = 0

    # 30 pts: JSON + schema valid
    if v.json_valid:    score += 15
    if v.schema_valid:  score += 15

    # 20 pts: no hard rule violations
    if v.hard_rule_violations == 0:    score += 20
    elif v.hard_rule_violations <= 2:  score += 10

    selected  = data.get("selected", [])
    watch     = data.get("watch",    [])
    rejected  = data.get("rejected", [])
    n_cands   = max(len(payload.get("candidates", [])), 1)

    # 15 pts: parsimony (≤30% selected is ideal)
    ratio = len(selected) / n_cands
    if ratio <= 0.30:    score += 15
    elif ratio <= 0.50:  score += 8

    # 15 pts: reason quality — rewards comparative_edge and longer reason_full
    if selected:
        reason_q = [
            min(1.0, len(str(s.get("reason_short",    ""))) / 40)  * 0.25
            + min(1.0, len(str(s.get("reason_full",   ""))) / 150) * 0.50
            + min(1.0, len(str(s.get("comparative_edge", ""))) / 80) * 0.25
            for s in selected
        ]
        score += int(15 * (sum(reason_q) / len(reason_q)))
    else:
        score += 10  # empty selected with explanation is acceptable

    # 10 pts: discriminates (uses WATCH or REJECT, not just SELECT)
    if watch or rejected:
        score += 10

    # 5 pts: coherence — PCS ≥ portfolio pcs_min_entry for each selected
    cand_pcs = {c["ticker"]: c.get("pcs", 0) for c in payload.get("candidates", [])}
    if selected:
        coherent = sum(
            1 for s in selected
            if cand_pcs.get(s.get("ticker", ""), 0)
            >= PORTFOLIOS.get(s.get("portfolio", ""), {}).get("pcs_min_entry", 999)
        )
        score += int(5 * coherent / len(selected))
    else:
        score += 3

    # 5 pts: coverage — all candidates with pcs>=62 must appear in selected/watch/rejected
    disposed = (
        {s.get("ticker") for s in selected}
        | {w.get("ticker") for w in watch}
        | {r.get("ticker") for r in rejected}
    )
    high_pcs_cands = [c for c in payload.get("candidates", []) if c.get("pcs", 0) >= 62]
    if high_pcs_cands:
        coverage = sum(1 for c in high_pcs_cands if c["ticker"] in disposed)
        score += int(5 * coverage / len(high_pcs_cands))
    else:
        score += 5

    return min(score, 100)


# ── Logger ─────────────────────────────────────────────────────────────────────

def _build_summary_record(
    run_id:        str,
    model:         str | None,
    payload:       dict,
    data:          dict | None,
    v:             ValidationResult,
    quality:       int,
    in_tok:        int,
    out_tok:       int,
    cost:          float,
    latency:       float,
    fallback_used: bool,
    error:         str | None,
    should_call:   bool,
    forced_run:    bool = False,
) -> dict:
    return {
        "date":                 str(date.today()),
        "run_id":               run_id,
        "model":                model,
        "provider":             "openrouter",
        "should_call_ai":       should_call,
        "forced_run":           forced_run,
        "event_count":          len(payload.get("events", [])),
        "candidate_count":      len(payload.get("candidates", [])),
        "input_tokens":         in_tok,
        "output_tokens":        out_tok,
        "cost_usd":             round(cost, 6),
        "latency_ms":           round(latency, 0),
        "json_valid":           v.json_valid,
        "schema_valid":         v.schema_valid,
        "hard_rule_violations": v.hard_rule_violations,
        "quality_score":        quality,
        "selected_count":       len(data.get("selected", [])) if data else 0,
        "watch_count":          len(data.get("watch",    [])) if data else 0,
        "rejected_count":       len(data.get("rejected", [])) if data else 0,
        "fallback_used":        fallback_used,
        "error":                error,
    }


def _log_no_call(run_id: str) -> None:
    _append_jsonl(SUMMARY_LOG, {
        "date": str(date.today()), "run_id": run_id, "model": None,
        "provider": None, "should_call_ai": False,
        "event_count": 0, "candidate_count": 0,
        "input_tokens": 0, "output_tokens": 0,
        "cost_usd": 0.0, "latency_ms": 0.0,
        "json_valid": None, "schema_valid": None,
        "hard_rule_violations": 0, "quality_score": None,
        "selected_count": 0, "watch_count": 0, "rejected_count": 0,
        "fallback_used": False, "error": None,
    })


def _save_test_result(
    run_id: str, model: str,
    data: dict | None, v: ValidationResult, quality: int,
    raw: str, summary: dict,
) -> None:
    slug = re.sub(r"[^\w.-]", "-", model)
    _write_json(TESTS_DIR / f"{date.today()}_{slug}.json", {
        "run_id":           run_id,
        "model":            model,
        "date":             str(date.today()),
        "summary":          summary,
        "validation":       {"violations": v.violations_detail},
        "quality_score":    quality,
        "response":         data,
        "raw_response_head": raw[:2000],
    })


def _log_shadow_picks(
    model: str,
    data: dict,
    is_active: bool,
    run_id: str,
    is_valid_run: bool,
    forced_run: bool,
    cand_pcs: dict | None = None,
) -> None:
    today = str(date.today())
    valid_for_tracking = is_valid_run and not forced_run
    for s in data.get("selected", []):
        t = s.get("ticker", "")
        pcs_val = (cand_pcs.get(t) if cand_pcs else None) or s.get("pcs")
        _append_jsonl(SHADOW_LOG, {
            "date":         today,
            "run_id":       run_id,
            "model":        model,
            "ticker":       t,
            "portfolio":    s.get("portfolio"),
            "pcs":          pcs_val,
            "signal_type":  s.get("signal_type"),
            "confidence":   s.get("confidence"),
            "reason_short": s.get("reason_short"),
            "shadow":       not is_active,
            "active_model": is_active,
            "forced_run":   forced_run,
            "valid_for_performance_tracking": valid_for_tracking,
            "entry_price":  None,   # filled by a separate price-fetch step
            "ret_1d":  None, "ret_3d":  None, "ret_1w":  None,
            "ret_2w":  None, "ret_1m":  None, "ret_3m":  None,
            "max_gain_1m": None, "max_drawdown_1m": None, "vs_spy_1m": None,
        })


# ── Portfolio updater (active model only) ──────────────────────────────────────

def _get_entry_price(ticker: str) -> float | None:
    """Lee el último cierre disponible del parquet raw del ticker."""
    try:
        import pandas as pd
        ticker_safe = ticker.replace("^", "").replace("=", "")
        path = ROOT / "backtest" / "data" / "raw" / f"yahoo_{ticker_safe}.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path, columns=["Close"]).dropna()
        if df.empty:
            return None
        return round(float(df["Close"].iloc[-1]), 2)
    except Exception:
        return None


def _size_from_conviction(conviction: str, size_range: tuple) -> float:
    lo, hi = size_range
    if conviction == "high": return float(hi)
    if conviction == "low":  return float(lo)
    return round((lo + hi) / 2.0, 1)


def update_portfolio(picks: dict, data: dict, cand_pcs: dict | None = None) -> dict:
    today      = str(date.today())
    portfolios = picks.setdefault("portfolios", {})

    for s in data.get("selected", []):
        ptf_id = s.get("portfolio", "")
        if ptf_id not in VALID_PORTFOLIOS:
            continue
        ptf       = portfolios.setdefault(ptf_id, {"positions": [], "history": [], "last_review": None})
        positions = ptf.setdefault("positions", [])
        t = s["ticker"]
        if any(p["ticker"] == t for p in positions):
            continue

        pcs_val = (cand_pcs.get(t) if cand_pcs else None) or s.get("pcs")
        new_pos = {
            "ticker":                  t,
            "entry_date":              today,
            "entry_price":             _get_entry_price(t),
            "entry_pcs":               pcs_val,
            "entry_signal":            s.get("signal_type"),
            "size_pct":                _size_from_conviction(
                                           s.get("confidence", "medium"),
                                           PORTFOLIOS[ptf_id]["size_range"],
                                       ),
            "conviction":              s.get("confidence"),
            "rationale":               s.get("reason_short"),
            "reason_full":             s.get("reason_full"),
            "comparative_edge":        s.get("comparative_edge"),
            "key_supporting_factors":  s.get("key_supporting_factors", []),
            "key_risks":               s.get("key_risks_or_contradictions", []),
        }
        positions.append(new_pos)
        ptf.setdefault("history", []).append({**new_pos, "event": "open"})

    ds = data.get("decision_summary", {})
    picks["last_ai_review"] = {
        "date":          today,
        "market_read":   ds.get("market_read"),
        "risk_posture":  ds.get("risk_posture"),
        "should_select": ds.get("should_select_picks"),
        "watch":         data.get("watch", []),
        "rejected":      data.get("rejected", []),
    }
    picks["last_updated"] = today
    return picks


# ── Main ───────────────────────────────────────────────────────────────────────

def run(force: bool = False, apply: bool = False) -> None:
    config = Config.from_env()
    today  = str(date.today())
    run_id = f"{today}_{datetime.now().strftime('%H%M')}"

    events_raw = _load("ai_events.json")
    if isinstance(events_raw, dict):
        events_raw = []

    cands_data = _load("ai_candidates.json")
    cand_pcs   = {c["ticker"]: c.get("pcs") for c in cands_data.get("candidates", [])}
    picks      = _load("ai_picks.json")
    if not isinstance(picks, dict):
        picks = {}

    meaningful_today = [
        e for e in events_raw
        if e.get("date") == today and e.get("type") != "first_snapshot"
    ]
    should_call_ai = bool(meaningful_today) or force

    if not should_call_ai:
        print(f"[{run_id}] No meaningful events today — skipping AI calls")
        _log_no_call(run_id)
        return

    events_for_payload = meaningful_today or [
        e for e in events_raw if e.get("type") != "first_snapshot"
    ][-20:]

    payload = build_payload(cands_data, events_for_payload, picks, config)
    _write_json(PAYLOAD_DIR / f"{today}.json", payload)

    baselines = compute_baselines(cands_data)
    _append_jsonl(BASELINES_LOG, {"date": today, "run_id": run_id, **baselines})

    print(
        f"[{run_id}] Payload ready - "
        f"{len(payload['candidates'])} candidates, {len(payload['events'])} events"
    )

    models = list(config.models_to_test) if config.test_mode else [config.active_model]
    if config.active_model not in models:
        models.insert(0, config.active_model)

    active_updated = False
    reasoning_by_model: dict = {}  # accumulated for ai_model_reasoning.json

    for model in models:
        is_active = (model == config.active_model)
        if not is_active and not config.enable_shadow_models:
            continue

        print(f"  [{model}]", end=" ", flush=True)

        raw, data             = "", None
        in_tok, out_tok       = 0, 0
        latency, cost         = 0.0, 0.0
        json_valid            = False
        fallback_used, error  = False, None
        model_used            = model

        try:
            user_msg = build_user_message(payload, model, run_id)
            raw, in_tok, out_tok, latency = call_model(model, SYSTEM_PROMPT, user_msg, max_tokens=6144)
            data, json_valid = parse_response(raw)
            cost = compute_cost(model, in_tok, out_tok)
            print(f"{latency:.0f}ms  ${cost:.5f}  {in_tok}+{out_tok}tok", end="  ")

        except Exception as exc:
            error      = str(exc)
            json_valid = False
            print(f"ERROR({exc})", end="  ")

            if is_active and config.fallback_model and config.fallback_model != model:
                print(f"-> fallback={config.fallback_model}", end="  ")
                try:
                    user_msg = build_user_message(payload, config.fallback_model, run_id)
                    raw, in_tok, out_tok, latency = call_model(
                        config.fallback_model, SYSTEM_PROMPT, user_msg, max_tokens=6144
                    )
                    data, json_valid = parse_response(raw)
                    cost          = compute_cost(config.fallback_model, in_tok, out_tok)
                    fallback_used = True
                    model_used    = config.fallback_model
                    error         = None
                    print(f"ok {latency:.0f}ms", end="  ")
                except Exception as exc2:
                    error = f"primary={exc}; fallback={exc2}"

        v       = validate_model_response(data, payload, json_valid)
        quality = compute_quality_score(data, v, payload)
        print(f"q={quality}/100  viol={v.hard_rule_violations}")

        is_valid_run = v.schema_valid and v.hard_rule_violations == 0
        summary_rec = _build_summary_record(
            run_id, model_used, payload, data, v,
            quality, in_tok, out_tok, cost, latency,
            fallback_used, error, True, forced_run=force,
        )
        _append_jsonl(SUMMARY_LOG, summary_rec)
        _save_test_result(run_id, model_used, data, v, quality, raw, summary_rec)

        if data and json_valid:
            reasoning_by_model[model_used] = {
                "quality_score":    quality,
                "decision_summary": data.get("decision_summary", {}),
                "selected":         data.get("selected", []),
                "watch":            data.get("watch", []),
                "rejected":         data.get("rejected", []),
            }

        if data and json_valid:
            _log_shadow_picks(model_used, data, is_active,
                              run_id=run_id, is_valid_run=is_valid_run,
                              forced_run=force, cand_pcs=cand_pcs)

        if is_active and data and is_valid_run:
            if force and not apply:
                print(f"  [{model_used}] ACTIVE -> picks NOT applied (forced run without --apply)")
            else:
                picks          = update_portfolio(picks, data, cand_pcs)
                active_updated = True
                n_sel = len(data.get("selected", []))
                print(f"  [{model_used}] ACTIVE -> {n_sel} picks applied to portfolio")
        elif is_active:
            reasons = []
            if not json_valid:        reasons.append("json_invalid")
            elif not v.schema_valid:  reasons.append("schema_invalid")
            else:                     reasons.append(f"{v.hard_rule_violations} violations")
            print(f"  [{model_used}] ACTIVE -> portfolio NOT updated ({', '.join(reasons)})")

    if reasoning_by_model:
        _write_json(DATA / "ai_model_reasoning.json", {
            "date":    today,
            "run_id":  run_id,
            "candidates": [c["ticker"] for c in payload.get("candidates", [])],
            "models":  reasoning_by_model,
        })
        print("  ai_model_reasoning.json saved")

    if active_updated:
        _write_json(DATA / "ai_picks.json", picks)
        print("  ai_picks.json saved")
        # Regenerar prices_picks.json con los nuevos tickers (para sparklines inmediatos)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "export_to_json", Path(__file__).parent / "export_to_json.py"
            )
            exp = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(exp)
            exp.export_picks_prices()
        except Exception as _e:
            print(f"  ⚠ prices_picks.json no actualizado: {_e}")


if __name__ == "__main__":
    run(force="--force" in sys.argv, apply="--apply" in sys.argv)
