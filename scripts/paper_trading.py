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
  AI_MODELS_TO_TEST         JSON list         (default: ["xiaomi/mimo-v2.5-pro"])
  ACTIVE_MODEL              model id          (default: x-ai/grok-4.3)
  FALLBACK_MODEL            model id          (default: xiaomi/mimo-v2.5-pro)
  ENABLE_SHADOW_MODELS      true|false        (default: true)
  MAX_CANDIDATES_PER_CALL   int               (default: 25)
"""
from __future__ import annotations

import json
import os
import html
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from ai_shared import (
    HARD_RULES,
    NON_TRADABLE_SUBTHEMES,
    VALID_REJECT_CATS,
    compact_candidate as _compact_candidate,
)

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
    "x-ai/grok-4.3":               (1.25,  2.50),
    "x-ai/grok-4.2":               (0.0,   0.0),
    "xiaomi/mimo-v2.5-pro":        (0.435, 0.87),
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
    "MIMO_SHADOW": {
        "description":      "Cartera shadow gestionada por Mimo — benchmark independiente vs Grok.",
        "pcs_threshold":    70.0,
        "pcs_min_entry":    68.0,
        "max_positions":    20,
        "size_range":       (3, 8),
        "target_ops_month": 8,
        "is_shadow_model":  True,  # gestionada por shadow model, no por el activo
    },
}

# Mapeo modelo shadow → su cartera exclusiva en ai_picks.json
SHADOW_MODEL_PORTFOLIOS: dict[str, str] = {
    "xiaomi/mimo-v2.5-pro": "MIMO_SHADOW",
}

VALID_PORTFOLIOS = frozenset(PORTFOLIOS) - {"REJECTED_HIGH_SCORE", "MIMO_SHADOW"}
VALID_SHADOW_PORTFOLIOS = frozenset({"MIMO_SHADOW"})

REQUIRED_RESPONSE_KEYS = {"date", "decision_summary", "selected", "watch", "rejected"}


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class Config:
    test_mode:            bool      = True
    models_to_test:       list[str] = field(default_factory=lambda: ["xiaomi/mimo-v2.5-pro"])
    active_model:         str       = "x-ai/grok-4.3"
    fallback_model:       str       = "xiaomi/mimo-v2.5-pro"
    enable_shadow_models: bool      = True
    max_candidates:       int       = 25

    @classmethod
    def from_env(cls) -> Config:
        test_mode = os.getenv("AI_MODEL_TEST_MODE", "true").lower() == "true"
        default_model = "xiaomi/mimo-v2.5-pro"
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
            max_candidates=int(os.getenv("MAX_CANDIDATES_PER_CALL", "25")),
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

def compute_theme_concentration(
    candidates: list[dict],
    picks: dict,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Cross-references open positions with candidates to compute theme concentration.

    Returns:
        conc_per_ticker: {ticker → {theme_risk, subtheme_risk}}
        theme_exposure:  {theme → {open_positions, open_tickers, open_weight_pct,
                                   new_candidates_today, risk}}
    """
    cand_theme = {c["ticker"]: (c.get("theme", ""), c.get("subtheme", "")) for c in candidates}

    theme_data:   dict[str, dict] = {}
    subtheme_data: dict[str, dict] = {}

    for ptf in picks.get("portfolios", {}).values():
        for pos in ptf.get("positions", []):
            tk   = pos.get("ticker", "")
            size = float(pos.get("size_pct") or 0)
            theme, subtheme = cand_theme.get(tk, ("", ""))
            if not theme:
                continue
            td = theme_data.setdefault(theme, {"tickers": [], "weight": 0.0})
            td["tickers"].append(tk)
            td["weight"] += size
            if subtheme:
                sd = subtheme_data.setdefault(subtheme, {"tickers": [], "weight": 0.0})
                sd["tickers"].append(tk)
                sd["weight"] += size

    def _theme_risk(n: int, w: float) -> str:
        if n >= 3 or w >= 30: return "high"
        if n >= 2 or w >= 20: return "medium"
        return "low"

    def _subtheme_risk(n: int, w: float) -> str:
        if n >= 2 or w >= 20: return "high"
        if n >= 1 or w >= 10: return "medium"
        return "low"

    conc_per_ticker: dict[str, dict] = {}
    for c in candidates:
        tk = c["ticker"]
        theme, subtheme = cand_theme.get(tk, ("", ""))
        td = theme_data.get(theme, {"tickers": [], "weight": 0.0})
        sd = subtheme_data.get(subtheme, {"tickers": [], "weight": 0.0})
        conc_per_ticker[tk] = {
            "theme_risk":    _theme_risk(len(td["tickers"]), td["weight"]),
            "subtheme_risk": _subtheme_risk(len(sd["tickers"]), sd["weight"]),
        }

    cands_per_theme: dict[str, int] = {}
    for c in candidates:
        th = cand_theme.get(c["ticker"], ("", ""))[0]
        if th:
            cands_per_theme[th] = cands_per_theme.get(th, 0) + 1

    theme_exposure: dict[str, dict] = {}
    for theme, td in theme_data.items():
        n = len(td["tickers"])
        w = round(td["weight"], 1)
        theme_exposure[theme] = {
            "open_positions":       n,
            "open_tickers":         td["tickers"],
            "open_weight_pct":      w,
            "new_candidates_today": cands_per_theme.get(theme, 0),
            "risk":                 _theme_risk(n, w),
        }

    return conc_per_ticker, theme_exposure


def _compact_candidates_with_concentration(
    eligible: list[dict], picks: dict
) -> list[dict]:
    conc_map, _ = compute_theme_concentration(eligible, picks)
    return [_compact_candidate(c, conc_map.get(c["ticker"])) for c in eligible]


def _build_theme_exposure(eligible: list[dict], picks: dict) -> dict:
    _, exposure = compute_theme_concentration(eligible, picks)
    return exposure


def build_payload(
    cands_data: dict,
    events: list[dict],
    picks: dict,
    config: Config,
) -> dict:
    macro         = cands_data.get("macro_context", {})
    all_cands_map = {c["ticker"]: c for c in cands_data.get("candidates", [])}

    # Tickers con posición abierta — siempre incluidos en candidates
    open_tickers: set[str] = {
        pos["ticker"]
        for ptf in picks.get("portfolios", {}).values()
        for pos in ptf.get("positions", [])
    }

    # Top-N elegibles por PCS
    top_n = sorted(
        [c for c in cands_data.get("candidates", []) if c.get("eligible")],
        key=lambda x: x.get("pcs", 0),
        reverse=True,
    )[:config.max_candidates]
    top_n_tickers = {c["ticker"] for c in top_n}

    # Añadir posiciones abiertas que no entran en el top-N (con o sin eligible)
    open_extras = [
        all_cands_map[tk]
        for tk in open_tickers
        if tk not in top_n_tickers and tk in all_cands_map
    ]
    eligible = top_n + open_extras

    prev_data = _load("ai_candidates_prev.json")
    prev_date = prev_data.get("date") if prev_data else None
    prev_snapshot_available = bool(prev_date and prev_date != cands_data.get("date"))
    active_positions = []
    for pid, ptf in picks.get("portfolios", {}).items():
        ptf_min = PORTFOLIOS.get(pid, {}).get("pcs_min_entry", 0)
        for pos in ptf.get("positions", []):
            tk = pos["ticker"]
            current = all_cands_map.get(tk)
            left_universe = current is None
            current = current or {}
            active_positions.append({
                **pos,
                "portfolio": pid,
                "pcs_min_entry": ptf_min,
                "left_universe": left_universe,
                "current_pcs": current.get("pcs"),
                "current_rot_score": current.get("rot_score"),
                "current_streak_weeks": current.get("streak_weeks"),
                "current_ret_4w_vs_spy": current.get("ret_4w_vs_spy"),
            })

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
        "candidates":               _compact_candidates_with_concentration(eligible, picks),
        "active_picks_relevant":    active_positions,
        "recent_rejected_relevant": [],
        "theme_exposure":           _build_theme_exposure(eligible, picks),
    }


# ── Prompt ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a disciplined quantitative portfolio manager for a paper trading system.

TASK: Review the market signals in the payload and return a structured JSON decision.

CRITICAL: Respond ONLY with valid JSON — no markdown fences, no explanation, \
no text before or after the JSON object.

RESPONSE LENGTH: Keep the total JSON under 3500 tokens. Use tight, specific \
language — one precise sentence beats three vague ones.

HARD RULES (violations are flagged automatically):
1. Only SELECT tickers present in candidates with eligible=true.
2. Do not SELECT futures, commodities, or macro indices.
3. Empty selected list is valid — do not fill portfolios with mediocre picks.
4. Use WATCH for uncertain/incomplete signals; REJECT for clearly insufficient ones.
5. Do not invent data. Use only information from the payload.
6. Every selected item needs: portfolio, signal_type, confidence, \
reason_short (≥20 chars), reason_full (≥100 chars), comparative_edge (≥30 chars).
7. Every rejected item needs: reason and a valid rejection_category.
8. Every candidate with pcs >= 62 not selected must appear in EXACTLY ONE of \
watch or rejected — never both. If you are torn between WATCH and REJECT for a \
candidate, that IS the decision: WATCH means "not yet, here is the trigger", \
REJECT means "no, for this reason". Pick one and commit. A ticker listed in \
two of selected/watch/rejected is treated as a hard rule violation.

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
- Every candidate with pcs >= 62 that you do not SELECT must appear in exactly
  one of watch or rejected — silence on a high-PCS candidate is not acceptable,
  and appearing in both is not acceptable either.

OBSERVATION FIELDS (informational — no hard rules, acknowledgement requested):
- extension_risk measures whether an entry might be a late chase. Values: low/medium/high/extreme.
  It does NOT block selections. If extension_risk is "high" or "extreme", acknowledge it briefly
  in reason_full or key_risks — explain why the signal still justifies entry despite the extension.
  If you SELECT a ticker with extension_risk "high"/"extreme" without any acknowledgement, that
  will be logged as "extension_risk_not_acknowledged" for later analysis (no quality score penalty).
- theme_exposure and theme_concentration_risk show how concentrated the open portfolio already is
  by sector. When a theme shows risk "high", note the concentration in your reasoning. You may
  still SELECT tickers in concentrated themes if the signal justifies it. When candidates are
  otherwise equivalent, prefer the less-concentrated theme.
- Koncorde 3D/W is a separate accumulation/distribution context feature — do not treat it as a
  standalone buy/sell signal. The 3D timeframe is the primary operational Koncorde reading; daily
  (konc_d_state) is tactical/noisier; weekly (konc_w_state) is structural confirmation.
  If konc_3d_state="distribution", selecting a new position requires explicit justification in
  reason_full or key_risks — this will be logged as "KONC_3D_DISTRIBUTION_WARNING" if you SELECT
  without acknowledging it (no quality score penalty).
  If DEMS is extreme (>=15) and extension_risk is "high"/"extreme" and konc_3d_state="distribution",
  prefer WATCH or REJECT unless there is very strong contrary evidence — this combination is logged
  as "DEMS_EXTREME_KONC_DISTRIBUTION_WARNING" when selected.
  konc_alignment summarizes 3D+W together (bullish_aligned/accumulation_setup/mixed/
  distribution_warning/bearish_aligned/neutral) — distribution_warning is the most urgent reading.
- These fields exist to collect data: after 30-50 picks we will analyze whether extension_risk,
  theme_concentration, and Koncorde 3D distribution correlate with worse returns. Until then,
  treat them as context only.

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
      "reason_short": "<specific, 20-80 chars>",
      "reason_full": "<100-250 chars: what drives this ticker's signal strength right now>",
      "comparative_edge": "<30-120 chars: name a peer with similar PCS you did NOT select and explain why this ranked higher on the deciding metrics>",
      "key_supporting_factors": ["<1 sentence each, ≤80 chars, 3-4 items>"],
      "key_risks_or_contradictions": ["<1 sentence each, ≤80 chars, 2-3 items>"]
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
  ],
  "open_picks_review": [
    {
      "ticker": "<ticker from active_picks_relevant>",
      "portfolio": "<portfolio_id>",
      "action": "HOLD|EXIT",
      "reason": "<1 brief sentence: why holding or why exiting>"
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

def _model_max_tokens(model: str) -> int:
    """Output token limit per model family (OpenRouter enforces the model's native cap)."""
    if "haiku" in model.lower():
        return 8192   # Claude Haiku 4.5 native max
    if "sonnet" in model.lower():
        return 16000  # Claude Sonnet 4.x native max
    if "mimo" in model.lower():
        return 32000  # MiMo-V2.5-Pro: verbose reasoning model, needs headroom
    return 6144       # conservative default for grok / others


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
        timeout=180.0,
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
    msg  = resp.choices[0].message
    text = msg.content or ""
    # Reasoning models (MIMO, DeepSeek-R1) sometimes return the visible response
    # in a separate field when content is empty — try both.
    if not text.strip():
        text = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
    in_tok  = resp.usage.prompt_tokens
    out_tok = resp.usage.completion_tokens
    return text, in_tok, out_tok, (time.monotonic() - t0) * 1000


def compute_cost(model: str, in_tok: int, out_tok: int) -> float:
    in_p, out_p = MODEL_PRICING.get(model, (0.0, 0.0))
    return (in_tok * in_p + out_tok * out_p) / 1_000_000


def parse_response(raw: str | None) -> tuple[dict | None, bool]:
    """Strip markdown fences and parse JSON. Returns (data, json_valid)."""
    if not raw:
        return None, False
    text = raw.strip()
    # Strip reasoning/thinking blocks emitted by models like MIMO and DeepSeek-R1
    # before attempting JSON extraction — otherwise the regex picks up { } inside thinking.
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"<reasoning>[\s\S]*?</reasoning>", "", text, flags=re.IGNORECASE).strip()
    # Strip markdown fences (handles both outer and inner-after-thinking fences)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    if text.startswith("{"):
        try:
            return json.loads(text), True
        except json.JSONDecodeError:
            pass
    # Try ```json ... ``` block that may appear after thinking text
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1)), True
        except json.JSONDecodeError:
            pass
    # Last resort: greedy match of outermost { ... }
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0)), True
        except json.JSONDecodeError:
            pass
    return None, False


# ── Validator ──────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    json_valid:             bool       = False
    schema_valid:           bool       = False
    hard_rule_violations:   int        = 0
    violations_detail:      list[str]  = field(default_factory=list)
    soft_warnings:          list[str]  = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.hard_rule_violations += 1
        self.violations_detail.append(msg)

    def warn(self, msg: str) -> None:
        self.soft_warnings.append(msg)


def validate_model_response(
    data: dict | None,
    payload: dict,
    json_valid: bool,
    raw_cands: dict[str, dict] | None = None,
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
        all_valid_ptfs = VALID_PORTFOLIOS | VALID_SHADOW_PORTFOLIOS
        if ptf not in all_valid_ptfs:
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
        if ptf in all_valid_ptfs and pcs_min > 0:
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

    # Soft warnings: extension_risk high/extreme not acknowledged (no penalty, log only)
    cand_by_ticker = {c["ticker"]: c for c in payload.get("candidates", [])}
    raw_cands = raw_cands or {}
    for s in data.get("selected", []):
        t = s.get("ticker", "")
        c = cand_by_ticker.get(t, {})
        ext = c.get("extension_risk")
        text_fields = " ".join([
            str(s.get("reason_full", "")),
            str(s.get("key_risks_or_contradictions", "")),
        ]).lower()
        if ext in ("high", "extreme"):
            if "extension" not in text_fields and "extend" not in text_fields and "chase" not in text_fields:
                r.warn(f"extension_risk_not_acknowledged: {t} has extension_risk={ext}")

        # Soft warnings: Koncorde 3D — observation only, no hard rule (hoja sección 2/2.1)
        konc_3d_state = c.get("konc_3d_state")
        if konc_3d_state == "distribution":
            if not any(kw in text_fields for kw in ("koncorde", "distribution", "institutional")):
                r.warn(f"KONC_3D_DISTRIBUTION_WARNING: {t} selected with konc_3d_state=distribution and no acknowledgement")

        if raw_cands.get(t, {}).get("konc_3d_blue_down_2_bars"):
            r.warn(f"KONC_3D_BLUE_DOWNTREND_WARNING: {t} selected with konc_3d_blue_down_2_bars=true")

        dems = c.get("dems")
        if (dems is not None and dems >= 15
                and ext in ("high", "extreme")
                and konc_3d_state == "distribution"):
            r.warn(f"DEMS_EXTREME_KONC_DISTRIBUTION_WARNING: {t} selected with dems={dems}, "
                   f"extension_risk={ext}, konc_3d_state=distribution")

    # Soft warnings: active positions not covered in open_picks_review (no penalty, log only)
    active_map = {p.get("ticker"): p for p in payload.get("active_picks_relevant", [])}
    reviewed_map = {rv.get("ticker"): rv for rv in data.get("open_picks_review", [])}
    for t in set(active_map) - set(reviewed_map):
        r.warn(f"open_picks_review_missing: {t} not included in open_picks_review")
    # Soft warning: HOLD on a position that should be EXITed per absolute floor rule
    for t, rv in reviewed_map.items():
        if rv.get("action") == "HOLD":
            pos = active_map.get(t, {})
            pcs = pos.get("current_pcs")
            if pcs is not None and pcs < 62:
                r.warn(f"hold_below_floor: {t} has pcs={pcs:.1f} (<62) but action=HOLD — should EXIT")

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
        "validation":       {
            "violations":   v.violations_detail,
            "soft_warnings": v.soft_warnings,
        },
        "quality_score":    quality,
        "response":         data,
        "raw_response_head": (raw or "")[:2000],
    })


def _log_shadow_picks(
    model: str,
    data: dict,
    is_active: bool,
    run_id: str,
    is_valid_run: bool,
    forced_run: bool,
    cand_pcs: dict | None = None,
    cand_snapshot: dict[str, dict] | None = None,
) -> None:
    today = str(date.today())
    valid_for_tracking = is_valid_run and not forced_run
    cand_snapshot = cand_snapshot or {}
    for s in data.get("selected", []):
        t = s.get("ticker", "")
        pcs_val = (cand_pcs.get(t) if isinstance(cand_pcs, dict) else None) or s.get("pcs")
        cand = cand_snapshot.get(t, {})
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
            # Extension risk at time of selection (for week-3 performance analysis)
            "extension_risk":   cand.get("extension_risk"),
            "extension_points": cand.get("extension_points"),
            "extension_flags":  cand.get("extension_flags"),
            # Theme concentration at time of selection
            "theme_concentration_risk":    cand.get("theme_concentration_risk"),
            "subtheme_concentration_risk": cand.get("subtheme_concentration_risk"),
            # Koncorde Plus at time of selection — richer than the model payload
            # (which only gets konc_alignment) so we can later check whether Konc 3D
            # distribution/deterioration correlated with worse ret_1w/2w/1m (hoja 16.2).
            "konc_3d_state":              cand.get("konc_3d_state"),
            "konc_3d_blue":               cand.get("konc_3d_blue"),
            "konc_3d_green":              cand.get("konc_3d_green"),
            "konc_3d_blue_slope":         cand.get("konc_3d_blue_slope"),
            "konc_3d_blue_down_2_bars":   cand.get("konc_3d_blue_down_2_bars"),
            "konc_3d_distribution_flag":  cand.get("konc_3d_distribution_flag"),
            "konc_w_blue":                cand.get("konc_w_blue"),
            "konc_w_state":               cand.get("konc_w_state"),
            "konc_alignment":             cand.get("konc_alignment"),
            "konc_3d_bar_date":           cand.get("konc_3d_bar_date"),
            "konc_w_bar_date":            cand.get("konc_w_bar_date"),
            "entry_price":  None,   # filled by a separate price-fetch step
            "ret_1d":  None, "ret_3d":  None, "ret_1w":  None,
            "ret_2w":  None, "ret_1m":  None, "ret_3m":  None,
            "max_gain_1m": None, "max_drawdown_1m": None, "vs_spy_1m": None,
        })


# ── Portfolio updater (active model only) ──────────────────────────────────────

def _get_entry_price(ticker: str) -> float | None:
    """Último cierre disponible: parquet si es reciente (<5d), yfinance si está obsoleto."""
    try:
        import pandas as pd
        ticker_safe = ticker.replace("^", "").replace("=", "").replace(".", "")
        path = ROOT / "backtest" / "data" / "raw" / f"yahoo_{ticker_safe}.parquet"
        stale_cutoff = pd.Timestamp.now() - pd.Timedelta(days=5)
        if path.exists():
            df = pd.read_parquet(path, columns=["Close"]).dropna()
            if not df.empty:
                df.index = pd.to_datetime(df.index)
                if df.index[-1] >= stale_cutoff:
                    return round(float(df["Close"].iloc[-1]), 2)
        # Parquet obsoleto o inexistente → yfinance
        import yfinance as yf
        hist = yf.download(ticker, period="5d", interval="1d",
                           auto_adjust=True, progress=False)
        if hist.empty:
            return None
        if hasattr(hist.columns, "get_level_values"):
            hist.columns = hist.columns.get_level_values(0)
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        return round(float(closes.iloc[-1]), 2)
    except Exception:
        return None


_PORTFOLIO_LABELS = {
    "HIGH_CONVICTION":              "Alta Conviccion",
    "CONFIRMED_FLOW_LEADERS":       "Flujo Confirmado",
    "EARLY_ROTATION":               "Rot. Temprana",
    "MACRO_THEMATIC_BENEFICIARIES": "Macro Tematico",
    "REJECTED_HIGH_SCORE":          "Rechazados (control)",
    "MIMO_SHADOW":                  "Mimo Shadow",
    "MIRROR_ESPEJO":                "Espejo (Grok)",
}
_CONVICTION_EMOJI = {"high": "🟢", "medium": "🟡", "low": "⚪"}


def _notify_changes(changes: dict, today: str, model_used: str, quality: int | None) -> None:
    """Send Telegram notification immediately when positions are opened or closed."""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("  Telegram: TELEGRAM_BOT_TOKEN/CHAT_ID not set — skipping")
        return
    if not changes["opened"] and not changes["closed"]:
        return

    lines: list[str] = ["<b>AI Picks Lab</b>", ""]
    m     = model_used.replace("anthropic/", "").replace("x-ai/", "")
    q_str = f"  Q={quality}/100" if quality is not None else ""
    lines.append(f"Modelo: <b>{m}</b>{q_str}")
    lines.append("")

    if changes["opened"]:
        lines.append("<b>Nuevas posiciones</b>")
        by_ptf: dict[str, list] = {}
        for p in changes["opened"]:
            by_ptf.setdefault(p["portfolio"], []).append(p)
        for ptf_id, positions in by_ptf.items():
            label = _PORTFOLIO_LABELS.get(ptf_id, ptf_id)
            lines.append(f"\n<b>{label}</b>")
            for p in positions:
                emoji    = _CONVICTION_EMOJI.get(p.get("conviction", ""), "⚪")
                pcs_str  = f"PCS {p['entry_pcs']}" if p.get("entry_pcs") else ""
                size_str = f"{p['size_pct']}%" if p.get("size_pct") else ""
                meta     = " | ".join(x for x in [pcs_str, size_str] if x)
                line     = f"{emoji} <b>{p['ticker']}</b>"
                if meta:
                    line += f"  {meta}"
                lines.append(line)
                if p.get("rationale"):
                    lines.append(f"  <i>{html.escape(p['rationale'])}</i>")
        lines.append("")

    if changes["closed"]:
        lines.append("<b>Posiciones cerradas</b>")
        by_ptf_closed: dict[str, list] = {}
        for c in changes["closed"]:
            by_ptf_closed.setdefault(c["portfolio"], []).append(c)
        for ptf_id, positions in by_ptf_closed.items():
            label = _PORTFOLIO_LABELS.get(ptf_id, ptf_id)
            lines.append(f"\n<b>{label}</b>")
            for p in positions:
                entry = p.get("entry_price")
                close = p.get("close_price")
                pnl   = ""
                if entry and close and entry != 0:
                    pct  = (close - entry) / entry * 100
                    sign = "+" if pct >= 0 else ""
                    pnl  = f"  {sign}{pct:.1f}%"
                line = f"🔴 <b>{p['ticker']}</b>{pnl}"
                if p.get("entry_date"):
                    line += f"  (desde {p['entry_date']})"
                lines.append(line)
                if p.get("close_reason"):
                    lines.append(f"  <i>{html.escape(p['close_reason'])}</i>")
        lines.append("")

    lines.append(f"<i>{today} — AI Picks Lab</i>")
    text = "\n".join(lines)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        print(f"  Telegram: {'OK' if r.ok else f'FAILED {r.status_code}: {r.text[:120]}'}")
    except Exception as exc:
        print(f"  Telegram: request failed: {exc}")


def _size_from_conviction(conviction: str, size_range: tuple) -> float:
    lo, hi = size_range
    if conviction == "high": return float(hi)
    if conviction == "low":  return float(lo)
    return round((lo + hi) / 2.0, 1)


def update_portfolio(
    picks: dict,
    data: dict,
    cand_pcs: dict | None = None,
    allowed_portfolios: frozenset | None = None,
) -> tuple[dict, dict]:
    today      = str(date.today())
    portfolios = picks.setdefault("portfolios", {})
    changes: dict[str, list] = {"opened": [], "closed": []}
    _valid = allowed_portfolios if allowed_portfolios is not None else VALID_PORTFOLIOS

    # Process EXIT decisions from open_picks_review
    for review in data.get("open_picks_review", []):
        if review.get("action") != "EXIT":
            continue
        tk  = review.get("ticker", "")
        pid = review.get("portfolio", "")
        if pid not in _valid:
            continue
        ptf = portfolios.get(pid)
        if ptf is None:
            continue
        positions = ptf.get("positions", [])
        pos_to_exit = next((p for p in positions if p["ticker"] == tk), None)
        if pos_to_exit is None:
            continue
        exit_price = _get_entry_price(tk)
        ptf["positions"] = [p for p in positions if p["ticker"] != tk]
        ptf.setdefault("history", []).append({
            **pos_to_exit,
            "event": "close",
            "close_date": today,
            "close_price": exit_price,
            "close_reason": review.get("reason", ""),
        })
        changes["closed"].append({
            **pos_to_exit,
            "portfolio":   pid,
            "close_price": exit_price,
            "close_reason": review.get("reason", ""),
        })

    for s in data.get("selected", []):
        ptf_id = s.get("portfolio", "")
        if ptf_id not in _valid:
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
        changes["opened"].append({**new_pos, "portfolio": ptf_id})

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
    return picks, changes


# ── Shadow model payload builder ───────────────────────────────────────────────

def _build_shadow_model_payload(
    full_payload: dict,
    picks: dict,
    shadow_portfolio_id: str,
    max_cands: int = 25,
) -> dict:
    """
    Construye el payload para un shadow model con cartera propia.

    Prioridad de candidatos (hasta max_cands):
      1. Posiciones abiertas en su propia cartera shadow
      2. Posiciones abiertas en las carteras de Grok
      3. Top PCS del resto de candidatos elegibles

    active_picks_relevant contiene solo sus propias posiciones
    (para que sepa qué tiene que revisar con HOLD/EXIT).
    Grok's positions aparecen en candidates como contexto, no en active_picks_relevant.
    """
    all_cands     = full_payload.get("candidates", [])
    all_cands_map = {c["ticker"]: c for c in all_cands}

    # 1. Posiciones propias del shadow model
    shadow_ptf   = picks.get("portfolios", {}).get(shadow_portfolio_id, {})
    shadow_pos   = shadow_ptf.get("positions", [])
    shadow_tickers = {p["ticker"] for p in shadow_pos}

    # active_picks_relevant — solo las suyas (con datos actuales del candidato)
    all_cands_full_map = {
        c["ticker"]: c
        for c in full_payload.get("candidates", [])
    }
    ptf_min = PORTFOLIOS.get(shadow_portfolio_id, {}).get("pcs_min_entry", 0)
    active_picks = []
    for pos in shadow_pos:
        tk      = pos["ticker"]
        current = all_cands_full_map.get(tk)
        left_universe = current is None
        current = current or {}
        active_picks.append({
            **pos,
            "portfolio":             shadow_portfolio_id,
            "pcs_min_entry":         ptf_min,
            "left_universe":         left_universe,
            "current_pcs":           current.get("pcs"),
            "current_rot_score":     current.get("rot_score"),
            "current_streak_weeks":  current.get("streak_weeks"),
            "current_ret_4w_vs_spy": current.get("ret_4w_vs_spy"),
        })

    # 2. Posiciones de Grok (carteras activas, excluidas las ya en shadow)
    grok_tickers: set[str] = set()
    for pid, ptf in picks.get("portfolios", {}).items():
        if pid == shadow_portfolio_id:
            continue
        if PORTFOLIOS.get(pid, {}).get("is_control"):
            continue
        if PORTFOLIOS.get(pid, {}).get("is_shadow_model"):
            continue
        for pos in ptf.get("positions", []):
            tk = pos["ticker"]
            if tk not in shadow_tickers:
                grok_tickers.add(tk)

    # 3. Construir lista de candidatos priorizada
    shadow_in_cands = [{**c, "_own_open": True}   for c in all_cands if c.get("ticker") in shadow_tickers]
    grok_in_cands   = [{**c, "_grok_open": True}  for c in all_cands if c.get("ticker") in grok_tickers]
    rest_cands      = [c for c in all_cands
                       if c.get("ticker") not in shadow_tickers
                       and c.get("ticker") not in grok_tickers]

    slots = max_cands
    candidates: list[dict] = []
    for pool in (shadow_in_cands, grok_in_cands, rest_cands):
        take = pool[:max(0, slots - len(candidates))]
        candidates.extend(take)
        if len(candidates) >= slots:
            break

    # Mandato simplificado: solo su cartera
    shadow_mandate = {
        shadow_portfolio_id: {
            k: v for k, v in PORTFOLIOS[shadow_portfolio_id].items()
            if k not in ("is_control", "is_shadow_model")
        }
    }

    # Reglas específicas del shadow model: el nombre de cartera es OBLIGATORIO
    shadow_hard_rules = list(HARD_RULES) + [
        f"CRITICAL: You manage ONLY the '{shadow_portfolio_id}' portfolio. "
        f"Every item in 'selected' MUST have portfolio='{shadow_portfolio_id}'. "
        "Do NOT use any other portfolio name (no HIGH_CONVICTION, no CONFIRMED_FLOW_LEADERS, etc.).",
        f"Tickers marked as [Grok open] in candidates are currently held by the active model. "
        "You may SELECT them independently if the signal justifies it for your portfolio.",
    ]

    return {
        **full_payload,
        "candidates":            candidates,
        "active_picks_relevant": active_picks,
        "portfolio_mandates":    shadow_mandate,
        "system_context": {
            **full_payload.get("system_context", {}),
            "hard_rules": shadow_hard_rules,
        },
        "_shadow_context": {
            "note": f"You manage only the {shadow_portfolio_id} portfolio. "
                    "Tickers from Grok portfolios are included as candidates for your consideration.",
            "grok_open_tickers": sorted(grok_tickers),
        },
    }


# ── Batched model call ─────────────────────────────────────────────────────────

BATCH_SIZE        = 25   # candidatos por llamada al hacer batching
SHADOW_MAX_CANDS  = 25   # los shadow models nunca ven más de 25 candidatos

def _trim_payload_candidates(payload: dict, limit: int) -> dict:
    """Devuelve una copia del payload con como máximo `limit` candidatos,
    garantizando que las posiciones abiertas siempre están incluidas."""
    cands = payload.get("candidates", [])
    if len(cands) <= limit:
        return payload
    open_tickers = {p.get("ticker") for p in payload.get("active_picks_relevant", [])}
    open_in_cands  = [c for c in cands if c.get("ticker") in open_tickers]
    rest           = [c for c in cands if c.get("ticker") not in open_tickers]
    slots_left     = max(0, limit - len(open_in_cands))
    trimmed        = open_in_cands + rest[:slots_left]
    return {**payload, "candidates": trimmed}


def _call_model_batched(
    payload: dict,
    model: str,
    run_id: str,
) -> tuple[str, dict | None, int, int, float]:
    """
    Si los candidatos superan BATCH_SIZE, divide en lotes de BATCH_SIZE y
    fusiona los resultados. Devuelve (raw_head, merged_data, in_tok, out_tok, latency_ms).
    """
    cands = payload.get("candidates", [])
    if len(cands) <= BATCH_SIZE:
        user_msg = build_user_message(payload, model, run_id)
        raw, in_tok, out_tok, lat = call_model(model, SYSTEM_PROMPT, user_msg, max_tokens=_model_max_tokens(model))
        data, _ = parse_response(raw)
        return raw or "", data, in_tok, out_tok, lat

    # Dividir en lotes
    batches = [cands[i:i + BATCH_SIZE] for i in range(0, len(cands), BATCH_SIZE)]
    n = len(batches)
    all_raw, all_data = [], []
    total_in, total_out, total_lat = 0, 0, 0.0

    for idx, batch_cands in enumerate(batches, 1):
        batch_payload = dict(payload)
        batch_payload["candidates"] = batch_cands
        batch_payload["_batch"] = f"{idx}/{n}"
        user_msg = build_user_message(batch_payload, model, run_id)
        raw, in_tok, out_tok, lat = call_model(model, SYSTEM_PROMPT, user_msg, max_tokens=_model_max_tokens(model))
        data, ok = parse_response(raw)
        all_raw.append(raw or "")
        all_data.append(data if ok else None)
        total_in  += in_tok
        total_out += out_tok
        total_lat += lat
        print(f"[batch {idx}/{n}: {in_tok}+{out_tok}tok]", end=" ", flush=True)

    # Fusionar resultados
    valid = [d for d in all_data if d]
    if not valid:
        return all_raw[0], None, total_in, total_out, total_lat

    merged: dict = {
        "model":            valid[0].get("model"),
        "run_id":           valid[0].get("run_id"),
        "date":             valid[0].get("date"),
        "decision_summary": valid[0].get("decision_summary", {}),
        "selected":         [],
        "watch":            [],
        "rejected":         [],
        "open_picks_review": [],
    }
    seen_open: set[str] = set()
    for d in valid:
        merged["selected"].extend(d.get("selected", []))
        merged["watch"].extend(d.get("watch", []))
        merged["rejected"].extend(d.get("rejected", []))
        for rev in d.get("open_picks_review", []):
            tk = rev.get("ticker")
            if tk and tk not in seen_open:
                seen_open.add(tk)
                merged["open_picks_review"].append(rev)

    return all_raw[0], merged, total_in, total_out, total_lat


# ── Main ───────────────────────────────────────────────────────────────────────

def run(force: bool = False, apply: bool = False) -> None:
    config = Config.from_env()
    today  = str(date.today())
    run_id = f"{today}_{datetime.now().strftime('%H%M')}"

    # Sincronizar archivos cloud-managed antes de un run local
    # (evita sobreescribir con datos locales obsoletos lo que CI mantiene actualizado)
    if not os.getenv("GITHUB_ACTIONS"):
        try:
            from sync_from_cloud import sync as _sync_cloud
            _sync_cloud(verbose=True)
        except Exception:
            pass  # no fatal: continúa con archivos locales

    events_raw = _load("ai_events.json")
    if isinstance(events_raw, dict):
        events_raw = []

    cands_data = _load("ai_candidates.json")
    cand_pcs   = {c["ticker"]: c.get("pcs") for c in cands_data.get("candidates", [])}
    picks      = _load("ai_picks.json")
    if not isinstance(picks, dict):
        picks = {}

    # Per-ticker snapshot for shadow_picks.jsonl logging: raw candidate fields
    # (extension_risk, konc_* — including the fields not sent to the model) plus
    # theme concentration at time of selection.
    _raw_cands = cands_data.get("candidates", [])
    _conc_map, _ = compute_theme_concentration(_raw_cands, picks)
    cand_snapshot: dict[str, dict] = {}
    for c in _raw_cands:
        tk = c.get("ticker")
        if not tk:
            continue
        merged = dict(c)
        conc = _conc_map.get(tk, {})
        merged["theme_concentration_risk"]    = conc.get("theme_risk")
        merged["subtheme_concentration_risk"] = conc.get("subtheme_risk")
        cand_snapshot[tk] = merged

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
    shadow_updated = False
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
            shadow_ptf_id = SHADOW_MODEL_PORTFOLIOS.get(model) if not is_active else None
            if shadow_ptf_id:
                model_payload = _build_shadow_model_payload(payload, picks, shadow_ptf_id, SHADOW_MAX_CANDS)
            elif is_active:
                model_payload = payload
            else:
                model_payload = _trim_payload_candidates(payload, SHADOW_MAX_CANDS)
            raw, data, in_tok, out_tok, latency = _call_model_batched(model_payload, model, run_id)
            json_valid = data is not None
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
                        config.fallback_model, SYSTEM_PROMPT, user_msg,
                        max_tokens=_model_max_tokens(config.fallback_model),
                    )
                    data, json_valid = parse_response(raw)
                    cost          = compute_cost(config.fallback_model, in_tok, out_tok)
                    fallback_used = True
                    model_used    = config.fallback_model
                    error         = None
                    print(f"ok {latency:.0f}ms", end="  ")
                except Exception as exc2:
                    error = f"primary={exc}; fallback={exc2}"

        v       = validate_model_response(data, model_payload, json_valid, raw_cands=cand_snapshot)
        quality = compute_quality_score(data, v, model_payload)
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
                              forced_run=force, cand_pcs=cand_pcs,
                              cand_snapshot=cand_snapshot)

        if is_active and data and is_valid_run:
            if force and not apply:
                print(f"  [{model_used}] ACTIVE -> picks NOT applied (forced run without --apply)")
            else:
                picks, changes = update_portfolio(picks, data, cand_pcs)
                active_updated = True
                n_sel = len(data.get("selected", []))
                print(f"  [{model_used}] ACTIVE -> {n_sel} picks applied to portfolio")
                _notify_changes(changes, today, model_used, quality)
        elif is_active:
            reasons = []
            if not json_valid:        reasons.append("json_invalid")
            elif not v.schema_valid:  reasons.append("schema_invalid")
            else:                     reasons.append(f"{v.hard_rule_violations} violations")
            print(f"  [{model_used}] ACTIVE -> portfolio NOT updated ({', '.join(reasons)})")
        elif shadow_ptf_id and data and is_valid_run:
            if force and not apply:
                n_sel = len(data.get("selected", []))
                print(f"  [{model_used}] SHADOW {shadow_ptf_id} -> {n_sel} picks NOT applied (forced run without --apply)")
            else:
                picks, changes = update_portfolio(picks, data, cand_pcs,
                                                  allowed_portfolios=VALID_SHADOW_PORTFOLIOS)
                shadow_updated = True
                n_sel = len(data.get("selected", []))
                print(f"  [{model_used}] SHADOW {shadow_ptf_id} -> {n_sel} picks applied")
                _notify_changes(changes, today, model_used, quality)
        elif shadow_ptf_id:
            reasons = []
            if not json_valid:        reasons.append("json_invalid")
            elif not v.schema_valid:  reasons.append("schema_invalid")
            else:                     reasons.append(f"{v.hard_rule_violations} violations")
            print(f"  [{model_used}] SHADOW {shadow_ptf_id} -> NOT updated ({', '.join(reasons)})")

    if reasoning_by_model:
        _write_json(DATA / "ai_model_reasoning.json", {
            "date":    today,
            "run_id":  run_id,
            "candidates": [c["ticker"] for c in payload.get("candidates", [])],
            "models":  reasoning_by_model,
        })
        print("  ai_model_reasoning.json saved")

    if active_updated or shadow_updated:
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
