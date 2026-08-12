"""
force_analyze.py — Force deep-dive analysis of any ticker by AI models.

Reads:
  docs/data/ai_candidates.json            (PCS scores + macro context)
  docs/data/ai_picks.json                 (current open positions)
  docs/data/ai_model_payloads/DATE.json   (--audit mode: exact pipeline payload)
  docs/data/model_tests/DATE_*.json       (--audit mode: model responses)

Writes (with --save):
  docs/data/force_analysis/TICKER_YYYYMMDD_HHMM.json
  docs/data/force_analyses.json           (rolling viewer log, max 100)

Usage:
  py -3 scripts/force_analyze.py TICKER
  py -3 scripts/force_analyze.py TICKER --models grok mimo
  py -3 scripts/force_analyze.py TICKER --all-models
  py -3 scripts/force_analyze.py TICKER --compare-portfolio HIGH_CONVICTION
  py -3 scripts/force_analyze.py TICKER --compare-portfolio all
  py -3 scripts/force_analyze.py TICKER --all-models --compare-portfolio all --save

  # Audit mode — EXPORT (copy-paste into any LLM, no API cost):
  py -3 scripts/force_analyze.py SE --audit
  py -3 scripts/force_analyze.py SE --audit --date 2026-06-24 --save   # saves .txt

  # Audit mode — API (call a model automatically, costs credits):
  py -3 scripts/force_analyze.py SE --audit --models sonnet --save
  py -3 scripts/force_analyze.py SE --audit --date 2026-06-25 --models haiku

Model aliases: grok, mimo, haiku, sonnet (or full OpenRouter model IDs)
Portfolio names: HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS, EARLY_ROTATION,
                 MACRO_THEMATIC_BENEFICIARIES, MIMO_SHADOW, all
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package required (pip install openai)")
    sys.exit(1)

# ── Constants ──────────────────────────────────────────────────────────────────

MODEL_ALIASES: dict[str, str] = {
    "grok":   "x-ai/grok-4.3",
    "mimo":   "xiaomi/mimo-v2.5-pro",
    "haiku":  "anthropic/claude-haiku-4-5-20251001",
    "sonnet": "anthropic/claude-sonnet-4-6",
}

PORTFOLIO_IDS = [
    "HIGH_CONVICTION",
    "CONFIRMED_FLOW_LEADERS",
    "EARLY_ROTATION",
    "MACRO_THEMATIC_BENEFICIARIES",
    "MIMO_SHADOW",
]

PORTFOLIO_MANDATES = {
    "HIGH_CONVICTION": {
        "description": "Solo las oportunidades con más alta convicción. Calidad sobre cantidad.",
        "pcs_threshold": 85.0, "pcs_min_entry": 82.0, "max_positions": 8, "size_range": (8, 15),
    },
    "CONFIRMED_FLOW_LEADERS": {
        "description": "Líderes con flujo confirmado en múltiples timeframes.",
        "pcs_threshold": 78.0, "pcs_min_entry": 75.0, "max_positions": 12, "size_range": (5, 10),
    },
    "EARLY_ROTATION": {
        "description": "Captura rotaciones tempranas antes de que sean obvias.",
        "pcs_threshold": 70.0, "pcs_min_entry": 68.0, "max_positions": 15, "size_range": (4, 8),
    },
    "MACRO_THEMATIC_BENEFICIARIES": {
        "description": "Beneficiarios del régimen macro actual.",
        "pcs_threshold": 65.0, "pcs_min_entry": 62.0, "max_positions": 20, "size_range": (3, 6),
    },
    "MIMO_SHADOW": {
        "description": "Cartera shadow gestionada por Mimo.",
        "pcs_threshold": 70.0, "pcs_min_entry": 68.0, "max_positions": 20, "size_range": (3, 8),
    },
}

DEFAULT_ACTIVE_MODEL = os.environ.get("ACTIVE_MODEL", "x-ai/grok-4.3")
DEFAULT_SHADOW_MODELS: list[str] = json.loads(
    os.environ.get("AI_MODELS_TO_TEST", '["xiaomi/mimo-v2.5-pro"]')
)

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a quantitative investment analyst for AI Picks Lab, a paper-trading system.

Your task is a DEEP SINGLE-TICKER ANALYSIS. You receive data for ONE specific ticker and must:

1. Assess its current signal strength using ALL provided data (PCS components if available, technical metrics, macro context, extension risk).
2. Recommend an action: SELECT (add to portfolio), WATCH (promising but not yet ready), or REJECT (insufficient conviction).
3. If recommending SELECT, specify which portfolio and why that tier is appropriate given the metrics.
4. If portfolio comparison data is provided, DIRECTLY COMPARE this ticker against EACH listed open position:
   - Name the existing ticker explicitly
   - Give a clear verdict: NEW_TICKER_STRONGER | EXISTING_STRONGER | COMPLEMENTARY | REDUNDANT
   - Cite specific numbers from both tickers to justify the verdict

RULES:
- Cite real numbers from the data. Do not invent metrics or make up values not in the payload.
- If PCS data is not available (ticker outside the 91-ticker universe), base analysis on available data and flag the limitation explicitly.
- Be specific. "Strong momentum" without a number is not acceptable. "ret_4w_vs_spy of +34% with 7-week streak" is.
- Extension risk: if extension_risk is high or extreme, acknowledge it explicitly in signal_summary or key_risks.
- Spike flag: a spike_flag=true is a caution signal, not automatic rejection for strong weekly setups.
- In portfolio comparisons: compare EVERY open position listed, even if brief. Do not skip positions.

PORTFOLIO MANDATES (min PCS for entry):
- HIGH_CONVICTION: PCS >= 82, max 8 positions, size 8-15%. Only the clearest signals.
- CONFIRMED_FLOW_LEADERS: PCS >= 75, max 12 positions, size 5-10%. Strong confirmed flow.
- EARLY_ROTATION: PCS >= 68, max 15 positions, size 4-8%. Early signals, DEMS can contribute.
- MACRO_THEMATIC_BENEFICIARIES: PCS >= 62, max 20 positions, size 3-6%. Macro/thematic alignment.

Return ONLY valid JSON. No markdown fences, no explanation outside the JSON.

Response schema:
{
  "ticker": "<TICKER>",
  "date": "<YYYY-MM-DD>",
  "model": "<model_id>",
  "recommended_action": "SELECT | WATCH | REJECT",
  "recommended_portfolio": "HIGH_CONVICTION | CONFIRMED_FLOW_LEADERS | EARLY_ROTATION | MACRO_THEMATIC_BENEFICIARIES | null",
  "confidence": "high | medium | low",
  "signal_summary": "<2-4 sentences: what specifically drives or blocks this ticker. Cite numbers.>",
  "key_supporting_factors": ["<string, ≤80 chars each>"],
  "key_risks": ["<string, ≤80 chars each>"],
  "portfolio_comparisons": [
    {
      "compared_ticker": "<existing position ticker>",
      "portfolio": "<portfolio_id>",
      "verdict": "NEW_TICKER_STRONGER | EXISTING_STRONGER | COMPLEMENTARY | REDUNDANT",
      "reasoning": "<1-2 sentences with specific numbers from both tickers>"
    }
  ]
}

If no portfolio comparison was requested, return portfolio_comparisons as an empty list [].
"""


# ── Audit system prompt ────────────────────────────────────────────────────────

AUDIT_SYSTEM_PROMPT = """You are an independent investment analyst acting as an ARBITRATOR.

Two AI models analyzed the EXACT SAME ticker data and reached DIFFERENT conclusions.
Your task:
1. Assess the ticker independently using ticker_data (this is EXACTLY what both models received)
2. Deliver your own verdict: SELECT, WATCH, or REJECT
3. Critically evaluate each model's reasoning — what did they get right or wrong?

CRITICAL RULES:
- Cite specific numbers from ticker_data. Do not invent values.
- Base your verdict on the data alone, not on model reputation or label.
- EARLY_ROTATION and MIMO_SHADOW mandates allow entry on strong DEMS (≥14, no spike) even
  with short streak_weeks, as long as PCS ≥ 68. Higher tiers require confirmed weekly metrics.
- Distinguish "hard reject" (genuinely insufficient signal) from "timing disagreement"
  (signal exists but stage of development differs between models).
- Be explicit: name which model you agree with and precisely why.

PORTFOLIO MANDATES:
- HIGH_CONVICTION:              PCS ≥ 82, size 8-15%
- CONFIRMED_FLOW_LEADERS:       PCS ≥ 75, size 5-10%
- EARLY_ROTATION:               PCS ≥ 68, DEMS ≥ 14 can compensate short streak, size 4-8%
- MACRO_THEMATIC_BENEFICIARIES: PCS ≥ 62, size 3-6%
- MIMO_SHADOW:                  same as EARLY_ROTATION (PCS ≥ 68, size 3-8%)

Return ONLY valid JSON. No markdown, no text outside the JSON.

Response schema:
{
  "ticker": "<TICKER>",
  "date": "<YYYY-MM-DD>",
  "model": "<your model id>",
  "verdict": "SELECT | WATCH | REJECT",
  "recommended_portfolio": "HIGH_CONVICTION | CONFIRMED_FLOW_LEADERS | EARLY_ROTATION | MACRO_THEMATIC_BENEFICIARIES | MIMO_SHADOW | null",
  "confidence": "high | medium | low",
  "agrees_with": "<model_id of the model you agree with, or 'neither'>",
  "arbitration_summary": "<2-4 sentences: your own verdict and reasoning, citing specific numbers from the data>",
  "model_assessments": [
    {
      "model_id": "<model id>",
      "decision": "<SELECT | WATCH | REJECT>",
      "reasoning_quality": "sound | partially_sound | flawed",
      "critique": "<1-2 sentences: what they got right or wrong — cite numbers from ticker_data>"
    }
  ],
  "decisive_factors": ["<key factor, ≤80 chars>", "<key factor, ≤80 chars>"]
}
"""

# ── Data loading ───────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_ticker_data(ticker: str, candidates: list[dict]) -> dict | None:
    ticker_upper = ticker.upper()
    for c in candidates:
        if c.get("ticker", "").upper() == ticker_upper:
            return c
    return None


def get_open_positions(picks: dict, portfolio_filter: str) -> list[dict]:
    """Return open positions from ai_picks.json, filtered by portfolio or 'all'."""
    positions = []
    filter_upper = portfolio_filter.upper()
    for pid, ptf in picks.get("portfolios", {}).items():
        if filter_upper != "ALL" and pid != filter_upper:
            continue
        for pos in ptf.get("positions", []):
            positions.append({
                "ticker":       pos.get("ticker"),
                "portfolio":    pid,
                "entry_date":   pos.get("entry_date"),
                "entry_pcs":    pos.get("entry_pcs"),
                "size_pct":     pos.get("size_pct"),
                "conviction":   pos.get("conviction"),
                "rationale":    pos.get("rationale"),
            })
    return positions


def enrich_positions(positions: list[dict], cands_map: dict[str, dict]) -> list[dict]:
    """Add current PCS/rot_score/streak to each position if available in candidates."""
    for pos in positions:
        c = cands_map.get(pos.get("ticker", ""))
        if c:
            pos["current_pcs"]           = c.get("pcs")
            pos["current_rot_score"]     = c.get("rot_score")
            pos["current_streak_weeks"]  = c.get("streak_weeks")
            pos["current_ret_4w_vs_spy"] = c.get("ret_4w_vs_spy")
            pos["extension_risk"]        = c.get("extension_risk")
    return positions


# ── Audit data loaders ────────────────────────────────────────────────────────

_SECTION_TO_DECISION = {"selected": "SELECT", "watch": "WATCH", "rejected": "REJECT"}


def load_pipeline_payload(date_str: str) -> dict | None:
    path = ROOT / "docs" / "data" / "ai_model_payloads" / f"{date_str}.json"
    return _load_json(path) if path.exists() else None


def load_model_decisions(date_str: str, ticker: str) -> list[dict]:
    """Scan all model_tests files for a date and extract each model's decision on ticker."""
    tests_dir = ROOT / "docs" / "data" / "model_tests"
    decisions: list[dict] = []
    for path in sorted(tests_dir.glob(f"{date_str}_*.json")):
        data = _load_json(path)
        model_id = data.get("model", path.stem)
        resp = data.get("response", {})
        for section in ("selected", "watch", "rejected"):
            for item in resp.get(section, []):
                if item.get("ticker", "").upper() == ticker.upper():
                    decisions.append({
                        "model_id":      model_id,
                        "decision":      _SECTION_TO_DECISION[section],
                        "quality_score": data.get("quality_score"),
                        "details":       item,
                    })
                    break
    return decisions


def build_audit_payload(
    ticker: str,
    ticker_data: dict,
    macro_context: dict,
    active_picks: list[dict],
    model_decisions: list[dict],
    date_str: str,
) -> dict:
    return {
        "task":    "ARBITRATE_MODEL_DISAGREEMENT",
        "date":    date_str,
        "ticker":  ticker,
        "instruction": (
            f"Two models analyzed {ticker} from exactly the same pipeline data and reached "
            "DIFFERENT conclusions. Arbitrate: assess ticker_data below and give your own verdict."
        ),
        "ticker_data":            ticker_data,
        "macro_context":          macro_context,
        "active_picks_context":   active_picks,
        "model_decisions":        model_decisions,
    }


# ── Payload builder ────────────────────────────────────────────────────────────

def build_payload(
    ticker: str,
    ticker_data: dict | None,
    macro_context: dict,
    open_positions: list[dict],
    compare_portfolio: str | None,
    date_str: str,
) -> dict:
    payload: dict = {
        "task":                   "FORCE_SINGLE_TICKER_ANALYSIS",
        "date":                   date_str,
        "ticker_under_analysis":  ticker,
        "in_candidate_universe":  ticker_data is not None,
        "macro_context": {
            "macro_score":    macro_context.get("score"),
            "macro_regime":   macro_context.get("regime"),
            "macro_trend":    macro_context.get("trend"),
            "macro_delta_1w": macro_context.get("delta_1w"),
            "macro_delta_1m": macro_context.get("delta_1m"),
            "phase_quality":  macro_context.get("phase_quality"),
        },
    }

    if ticker_data:
        ds = ticker_data.get("daily_signals", {})
        payload["ticker_data"] = {
            "ticker":           ticker_data.get("ticker"),
            "name":             ticker_data.get("name"),
            "theme":            ticker_data.get("theme"),
            "subtheme":         ticker_data.get("subtheme"),
            "pcs":              ticker_data.get("pcs"),
            "eligible":         ticker_data.get("eligible"),
            "pcs_components":   ticker_data.get("pcs_components", {}),
            "rot_score":        ticker_data.get("rot_score"),
            "signal":           ticker_data.get("signal"),
            "streak_weeks":     ticker_data.get("streak_weeks"),
            "ret_4w_vs_spy":    ticker_data.get("ret_4w_vs_spy"),
            "ret_13w_vs_spy":   ticker_data.get("ret_13w_vs_spy"),
            "dist_52w_high":    ticker_data.get("dist_52w_high"),
            "flags":            ticker_data.get("flags", []),
            "extension_risk":   ticker_data.get("extension_risk"),
            "extension_points": ticker_data.get("extension_points"),
            "extension_flags":  ticker_data.get("extension_flags", []),
            # Daily signals
            "dems":             ds.get("daily_early_momentum_score"),
            "spike_flag":       ds.get("spike_flag"),
            "ret_5d_vs_spy":    ds.get("ret_5d_vs_spy"),
            "ret_10d_vs_spy":   ds.get("ret_10d_vs_spy"),
            "outperform_d10":   ds.get("outperform_days_10d"),
            "rsi_14":           ds.get("rsi_14"),
            "dist_sma20_atr":   ds.get("dist_sma20_atr"),
            "momentum_decay":   ds.get("momentum_decay"),
        }
    else:
        payload["ticker_data"] = {
            "ticker": ticker,
            "note":   (
                "This ticker is NOT in the 91-ticker candidate universe — no PCS data available. "
                "Assess based on macro context only and flag this limitation."
            ),
        }

    if compare_portfolio:
        payload["portfolio_comparison_request"] = {
            "filter": compare_portfolio,
            "instruction": (
                "Compare the ticker under analysis against EACH of the open positions below. "
                "For every position, give a direct verdict (NEW_TICKER_STRONGER / EXISTING_STRONGER / "
                "COMPLEMENTARY / REDUNDANT) with specific numbers from both tickers."
            ),
            "open_positions": open_positions,
            "portfolio_mandates": {
                pid: {
                    "pcs_threshold": m["pcs_threshold"],
                    "pcs_min_entry": m["pcs_min_entry"],
                    "size_range":    list(m["size_range"]),
                    "max_positions": m["max_positions"],
                }
                for pid, m in PORTFOLIO_MANDATES.items()
                if pid in [p.get("portfolio") for p in open_positions]
            },
        }

    return payload


# ── Model call ─────────────────────────────────────────────────────────────────

def call_model(
    model_id: str,
    payload: dict,
    max_tokens: int = 1500,
    system_prompt: str | None = None,
) -> tuple[str, float, int, int]:
    """Return (raw_text, latency_ms, input_tokens, output_tokens)."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/ai-picks-lab/market-tracker",
            "X-Title":      "AI Picks Lab - Force Analyze",
        },
    )

    user_msg = json.dumps(payload, ensure_ascii=True)
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    )
    latency_ms = (time.time() - t0) * 1000
    usage = resp.usage or {}
    return (
        resp.choices[0].message.content,
        latency_ms,
        getattr(usage, "prompt_tokens", 0),
        getattr(usage, "completion_tokens", 0),
    )


def parse_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines) - 1 if lines[-1].startswith("```") else len(lines)
        text = "\n".join(lines[1:end])
    return json.loads(text)


def _resolve_max_tokens(model_id: str, n_open_positions: int) -> int:
    """Output token budget for the normal-mode call.

    A single-ticker verdict fits comfortably in ~1500 tokens, but
    --compare-portfolio all asks the model for one verdict+reasoning per open
    position (28 as of 2026-08-12) on top of that — the fixed 1500 cap was
    truncating those responses mid-string (confirmed: two consecutive SE
    runs both cut off mid-JSON-string around token ~1500). Scale with
    n_open_positions and cap at a per-model ceiling.

    Grok's cap here (16000) is not xAI's true limit — queried OpenRouter's
    /models/x-ai/grok-4.3/endpoints on 2026-08-12 and both max_completion_tokens
    and max_prompt_tokens come back null (unreported, context_length=1,000,000),
    so paper_trading.py's "conservative default: 6144" for grok was never a
    verified ceiling, just a guess — kept the same shape (per-model cap) but
    raised it because 6144 was already tight against 28 positions' worth of
    verdicts (needed ~7660) and the true limit is evidently much higher.
    """
    needed = 1500 + 220 * n_open_positions
    m = model_id.lower()
    if "haiku" in m:
        cap = 8192   # Claude Haiku 4.5 native max
    elif "sonnet" in m:
        cap = 16000  # Claude Sonnet 4.x native max
    elif "mimo" in m:
        cap = 32000  # MiMo-V2.5-Pro: verbose reasoning model
    else:
        cap = 16000  # grok / others — no reported ceiling, see docstring
    return min(needed, cap)


# ── Model resolution ───────────────────────────────────────────────────────────

def resolve_models(args_models: list[str] | None, all_models: bool) -> list[str]:
    if args_models:
        return [MODEL_ALIASES.get(m.lower(), m) for m in args_models]
    if all_models:
        seen: dict[str, None] = {}
        for m in [DEFAULT_ACTIVE_MODEL] + DEFAULT_SHADOW_MODELS:
            seen[m] = None
        return list(seen)
    return [DEFAULT_ACTIVE_MODEL]


def model_short_name(model_id: str) -> str:
    rev = {v: k for k, v in MODEL_ALIASES.items()}
    return rev.get(model_id, model_id.split("/")[-1])


# ── Output formatting ──────────────────────────────────────────────────────────

W = 72

def _fmt_pcs(v) -> str:
    return f"{v:.1f}" if isinstance(v, (int, float)) else "N/A"

def _fmt_pct(v) -> str:
    if isinstance(v, (int, float)):
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.1f}%"
    return "N/A"

def print_header(ticker: str, ticker_data: dict | None, macro: dict, models: list[str], compare: str | None) -> None:
    print(f"\n{'=' * W}")
    print(f"  FORCE ANALYSIS: {ticker}")
    if ticker_data:
        pcs   = _fmt_pcs(ticker_data.get("pcs"))
        rot   = _fmt_pcs(ticker_data.get("rot_score"))
        streak = ticker_data.get("streak_weeks", "N/A")
        r4w   = _fmt_pct(ticker_data.get("ret_4w_vs_spy"))
        ext   = ticker_data.get("extension_risk", "N/A")
        ds    = ticker_data.get("daily_signals", {})
        dems  = ds.get("daily_early_momentum_score", "N/A")
        print(f"  PCS: {pcs}  rot_score: {rot}  streak: {streak}w  ret_4w: {r4w}  DEMS: {dems}")
        print(f"  Theme: {ticker_data.get('theme','?')}/{ticker_data.get('subtheme','?')}  "
              f"extension_risk: {ext}")
    else:
        print("  WARNING: ticker not in 91-ticker universe — no PCS data")
    score = macro.get("score")
    score_str = f"{score:.1f}" if isinstance(score, (int, float)) else "N/A"
    print(f"  Macro: {macro.get('regime','?')} {score_str}  trend: {macro.get('trend','?')}")
    print(f"  Models: {', '.join(model_short_name(m) for m in models)}")
    if compare:
        print(f"  Portfolio comparison: {compare}")
    print(f"{'=' * W}")


def print_result(result: dict, model_id: str, latency_ms: float) -> None:
    action    = result.get("recommended_action", "?")
    portfolio = result.get("recommended_portfolio") or "—"
    confidence = result.get("confidence", "?")
    action_pad = {"SELECT": "[SELECT]", "WATCH": "[WATCH ]", "REJECT": "[REJECT]"}.get(action, f"[{action}]")

    print(f"\n{'-' * W}")
    print(f"  {model_short_name(model_id).upper()}  ({latency_ms / 1000:.1f}s)")
    print(f"  {action_pad}  portfolio: {portfolio}  confidence: {confidence}")
    print(f"{'-' * W}")

    summary = result.get("signal_summary", "")
    if summary:
        print(f"\n{summary}")

    factors = result.get("key_supporting_factors") or []
    if factors:
        print("\nSUPPORTING:")
        for f in factors:
            print(f"  + {f}")

    risks = result.get("key_risks") or []
    if risks:
        print("\nRISKS:")
        for r in risks:
            print(f"  - {r}")

    comps = result.get("portfolio_comparisons") or []
    if comps:
        print("\nPORTFOLIO COMPARISONS:")
        for c in comps:
            verdict  = c.get("verdict", "?")
            cticker  = c.get("compared_ticker", "?")
            cport    = c.get("portfolio", "?")
            reasoning = c.get("reasoning", "")
            print(f"  vs {cticker} ({cport}): {verdict}")
            if reasoning:
                # indent multi-line
                for line in reasoning.split(". "):
                    line = line.strip()
                    if line:
                        print(f"     {line}.")


def print_error(model_id: str, error: str, raw: str | None = None) -> None:
    print(f"\n{'-' * W}")
    print(f"  {model_short_name(model_id).upper()}  ERROR")
    print(f"{'-' * W}")
    print(f"  {error}")
    if raw:
        preview = raw[:300].replace("\n", " ")
        print(f"  raw: {preview}...")


def print_audit_result(result: dict, model_id: str, latency_ms: float) -> None:
    verdict    = result.get("verdict", "?")
    portfolio  = result.get("recommended_portfolio") or "—"
    confidence = result.get("confidence", "?")
    agrees     = result.get("agrees_with", "?")
    verdict_pad = {"SELECT": "[SELECT]", "WATCH": "[WATCH ]", "REJECT": "[REJECT]"}.get(verdict, f"[{verdict}]")

    print(f"\n{'-' * W}")
    print(f"  ARBITRO: {model_short_name(model_id).upper()}  ({latency_ms / 1000:.1f}s)")
    print(f"  {verdict_pad}  portfolio: {portfolio}  confidence: {confidence}")
    print(f"  Agrees with: {model_short_name(agrees) if '/' in agrees else agrees}")
    print(f"{'-' * W}")

    summary = result.get("arbitration_summary", "")
    if summary:
        print(f"\n{summary}")

    assessments = result.get("model_assessments") or []
    if assessments:
        print("\nEVALUACION DE MODELOS:")
        for a in assessments:
            mid     = model_short_name(a.get("model_id", "?"))
            dec     = a.get("decision", "?")
            quality = a.get("reasoning_quality", "?")
            critique = a.get("critique", "")
            print(f"  {mid} [{dec}] -> {quality}")
            if critique:
                print(f"     {critique}")

    factors = result.get("decisive_factors") or []
    if factors:
        print("\nFACTORES DECISIVOS:")
        for f in factors:
            print(f"  * {f}")


# ── Audit text export ─────────────────────────────────────────────────────────

def generate_audit_prompt(
    ticker: str,
    ticker_data: dict,
    macro_context: dict,
    model_decisions: list[dict],
    audit_date: str,
) -> str:
    """Generate a self-contained text prompt ready to paste into any LLM chat."""

    def fmt(v, pct=False, dec=2):
        if v is None: return "N/A"
        if pct: return f"{'+' if v >= 0 else ''}{v:.{dec}f}%"
        return f"{v:.{dec}f}" if isinstance(v, float) else str(v)

    lines = []
    lines.append("=" * 70)
    lines.append(f"  MODEL ARBITRATION — {ticker}  (pipeline date: {audit_date})")
    lines.append("=" * 70)
    lines.append("")
    lines.append("You are an independent investment analyst acting as an ARBITRATOR.")
    lines.append("Two AI models analyzed the same ticker with EXACTLY the same data")
    lines.append("and reached OPPOSITE conclusions. Your task:")
    lines.append("  1. Assess the ticker using the data below (same data both models received)")
    lines.append("  2. Give your own verdict: SELECT, WATCH, or REJECT")
    lines.append("  3. Evaluate each model's reasoning critically, citing specific numbers")
    lines.append("  4. State which model you agree with and why")
    lines.append("")

    # ── Macro ──
    lines.append("─" * 70)
    lines.append("MACRO CONTEXT")
    lines.append("─" * 70)
    # Keys differ between pipeline payload (macro_score/macro_regime) and ai_candidates (score/regime)
    regime = macro_context.get('macro_regime') or macro_context.get('regime', '?')
    phase  = macro_context.get('phase_quality', '')
    score  = macro_context.get('macro_score') or macro_context.get('score')
    d1w    = macro_context.get('macro_delta_1w') or macro_context.get('delta_1w')
    d1m    = macro_context.get('macro_delta_1m') or macro_context.get('delta_1m')
    trend  = macro_context.get('macro_trend') or macro_context.get('trend', '?')
    lines.append(f"Regime:      {regime}{' (' + phase + ')' if phase else ''}")
    lines.append(f"MacroScore:  {fmt(score, dec=1)}  (delta_1w: {fmt(d1w, pct=True, dec=2)}  delta_1m: {fmt(d1m, pct=True, dec=2)})")
    lines.append(f"Trend:       {trend}")
    lines.append("")

    # ── Ticker data ──
    lines.append("─" * 70)
    lines.append(f"TICKER DATA: {ticker_data.get('ticker',ticker)}  —  {ticker_data.get('name','')}")
    lines.append("─" * 70)
    lines.append(f"Theme:          {ticker_data.get('theme','?')} / {ticker_data.get('subtheme','?')}")
    lines.append(f"PCS:            {fmt(ticker_data.get('pcs'), dec=1)}  (eligible: {ticker_data.get('eligible','?')})")
    lines.append(f"rot_score:      {fmt(ticker_data.get('rot_score'), dec=1)}")
    lines.append(f"streak_weeks:   {ticker_data.get('streak_weeks','?')}")
    lines.append(f"ret_4w_vs_spy:  {fmt(ticker_data.get('ret_4w_vs_spy'), pct=True)}")
    lines.append(f"ret_13w_vs_spy: {fmt(ticker_data.get('ret_13w_vs_spy'), pct=True)}")
    lines.append(f"dist_52w_high:  {fmt(ticker_data.get('dist_52w_high'), pct=True)}")
    lines.append("")
    lines.append(f"DEMS (daily early momentum, 0-20): {ticker_data.get('dems','?')}")
    lines.append(f"spike_flag:     {ticker_data.get('spike_flag','?')}")
    lines.append(f"ret_5d_vs_spy:  {fmt(ticker_data.get('ret_5d_vs_spy'), pct=True)}")
    lines.append(f"ret_10d_vs_spy: {fmt(ticker_data.get('ret_10d_vs_spy'), pct=True)}")
    lines.append(f"outperform_d10: {ticker_data.get('outperform_d10','?')}/10 days")
    lines.append(f"momentum_accel: {ticker_data.get('momentum_accel','?')}")
    lines.append("")
    lines.append(f"extension_risk:   {ticker_data.get('extension_risk','?')}  ({ticker_data.get('extension_points','?')} pts)")
    ext_flags = ticker_data.get('extension_flags') or []
    if ext_flags:
        lines.append(f"extension_flags:  {', '.join(ext_flags)}")
    lines.append(f"theme_concentration_risk:    {ticker_data.get('theme_concentration_risk','?')}")
    lines.append(f"subtheme_concentration_risk: {ticker_data.get('subtheme_concentration_risk','?')}")
    flags = [f for f in (ticker_data.get('flags') or []) if not f.startswith('macro_')]
    if flags:
        lines.append(f"flags:  {', '.join(flags)}")
    lines.append("")

    # ── Portfolio mandates ──
    lines.append("─" * 70)
    lines.append("PORTFOLIO MANDATES")
    lines.append("─" * 70)
    lines.append("HIGH_CONVICTION:              PCS >= 82, size 8-15%")
    lines.append("CONFIRMED_FLOW_LEADERS:       PCS >= 75, size 5-10%")
    lines.append("EARLY_ROTATION:               PCS >= 68, DEMS >= 14 can compensate")
    lines.append("                              short streak_weeks, size 4-8%")
    lines.append("MACRO_THEMATIC_BENEFICIARIES: PCS >= 62, size 3-6%")
    lines.append("MIMO_SHADOW:                  same as EARLY_ROTATION (PCS >= 68, size 3-8%)")
    lines.append("")

    # ── Model decisions ──
    lines.append("─" * 70)
    lines.append("MODEL DECISIONS")
    lines.append("─" * 70)
    for d in model_decisions:
        mid     = d.get("model_id", "?")
        dec     = d.get("decision", "?")
        details = d.get("details", {})
        qs      = d.get("quality_score")
        lines.append(f"")
        lines.append(f">>> {model_short_name(mid).upper()} ({mid})  Q={qs}")
        lines.append(f"    Decision: {dec}")

        if dec == "SELECT":
            lines.append(f"    Portfolio:  {details.get('portfolio','?')}")
            lines.append(f"    Confidence: {details.get('confidence','?')}")
            lines.append(f"    Signal:     {details.get('signal_type','?')}")
            rs = details.get("reason_short","")
            rf = details.get("reason_full","")
            ce = details.get("comparative_edge","")
            if rs: lines.append(f"    Short:  {rs}")
            if rf: lines.append(f"    Full:   {rf}")
            if ce: lines.append(f"    Peers:  {ce}")
            factors = details.get("key_supporting_factors") or []
            risks   = details.get("key_risks_or_contradictions") or details.get("key_risks") or []
            if factors:
                lines.append("    Supporting factors:")
                for f in factors: lines.append(f"      + {f}")
            if risks:
                lines.append("    Key risks:")
                for r in risks: lines.append(f"      - {r}")
        elif dec == "REJECT":
            lines.append(f"    Category: {details.get('rejection_category','?')}")
            lines.append(f"    Reason:   {details.get('reason','?')}")
        elif dec == "WATCH":
            lines.append(f"    Reason:  {details.get('reason','?')}")
            wt = details.get("watch_trigger","")
            if wt: lines.append(f"    Trigger: {wt}")

    lines.append("")
    lines.append("─" * 70)
    lines.append("YOUR ARBITRATION")
    lines.append("─" * 70)
    lines.append("Please respond with:")
    lines.append("  VERDICT:    SELECT / WATCH / REJECT")
    lines.append("  PORTFOLIO:  (if SELECT) which portfolio and why that tier")
    lines.append("  AGREES WITH: which model's reasoning is more sound")
    lines.append("  MODEL CRITIQUES: what each model got right and wrong (cite numbers)")
    lines.append("  DECISIVE FACTORS: 3-5 key factors that drove your verdict")
    lines.append("")

    return "\n".join(lines)


# ── Save helper ────────────────────────────────────────────────────────────────

def _save_results(ticker: str, entry: dict, all_results: list[dict]) -> None:
    """Write individual file + update rolling log. entry must NOT contain 'payload' key."""
    output_dir = ROOT / "docs" / "data" / "force_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts    = datetime.now().strftime("%Y%m%d_%H%M")
    fname = output_dir / f"{ticker}_{ts}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump({**entry, "results": all_results}, f, indent=2, ensure_ascii=False)
    print(f"\n[saved -> {fname.relative_to(ROOT)}]")

    log_path = ROOT / "docs" / "data" / "force_analyses.json"
    existing: list[dict] = []
    if log_path.exists():
        try:
            with open(log_path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    log_entry = {**entry, "results": all_results}
    existing = [log_entry] + existing
    existing = existing[:100]
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    print(f"[log   -> docs/data/force_analyses.json ({len(existing)} entries)]")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    # Ensure console handles non-ASCII characters from model responses (Windows)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Force AI deep-dive analysis of any ticker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("ticker", help="Ticker symbol to analyze (e.g. NVDA, CORZ, SASK.V)")
    parser.add_argument(
        "--models", nargs="+", metavar="MODEL",
        help="Models to use. Aliases: grok, mimo, haiku, sonnet. Or full OpenRouter IDs.",
    )
    parser.add_argument(
        "--all-models", action="store_true",
        help="Use active model + all configured shadow models",
    )
    parser.add_argument(
        "--compare-portfolio", metavar="PORTFOLIO",
        help=(
            "Compare ticker against open positions in this portfolio. "
            "Use 'all' for all portfolios, or a specific name: "
            "HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS, EARLY_ROTATION, "
            "MACRO_THEMATIC_BENEFICIARIES, MIMO_SHADOW"
        ),
    )
    parser.add_argument(
        "--audit", action="store_true",
        help=(
            "Audit mode: load the exact pipeline payload used today (or --date DATE) "
            "and ask an arbitrator model to resolve the disagreement between models."
        ),
    )
    parser.add_argument(
        "--date", metavar="YYYY-MM-DD",
        help="Pipeline run date to audit (default: today). Only used with --audit.",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save full results to docs/data/force_analysis/ and update force_analyses.json",
    )
    args = parser.parse_args()

    ticker   = args.ticker.upper()
    date_str = datetime.now().strftime("%Y-%m-%d")
    models   = resolve_models(args.models, args.all_models)

    # ── AUDIT MODE ──────────────────────────────────────────────────────────────
    if args.audit:
        audit_date = args.date or date_str
        print(f"\n{'=' * W}")
        print(f"  AUDIT MODE: {ticker}  (pipeline date: {audit_date})")
        print(f"  Arbitrator(s): {', '.join(model_short_name(m) for m in models)}")
        print(f"{'=' * W}")

        pipeline_payload = load_pipeline_payload(audit_date)
        if not pipeline_payload:
            print(f"ERROR: no payload found for {audit_date} in docs/data/ai_model_payloads/")
            sys.exit(1)

        # Find ticker in that day's candidates
        ticker_data = next(
            (c for c in pipeline_payload.get("candidates", [])
             if c.get("ticker", "").upper() == ticker),
            None,
        )
        macro = pipeline_payload.get("macro_context", {})
        active_picks = pipeline_payload.get("active_picks_relevant", [])

        if not ticker_data:
            print(f"WARNING: {ticker} not found in {audit_date} candidates — auditing with macro context only")
            ticker_data = {"ticker": ticker, "note": f"Not in {audit_date} candidate list"}

        # Collect what every model said about this ticker on that date
        model_decisions = load_model_decisions(audit_date, ticker)

        if not model_decisions:
            print(f"WARNING: no model decisions found for {ticker} on {audit_date}")
            print("  Available model_tests files:")
            for p in sorted((ROOT / "docs/data/model_tests").glob(f"{audit_date}_*.json")):
                print(f"    {p.name}")
        else:
            print(f"\nDecisions found:")
            for d in model_decisions:
                print(f"  {model_short_name(d['model_id'])} -> {d['decision']}"
                      f"  (Q={d.get('quality_score','?')})")

        # ── Export mode (no --models specified): print prompt for copy-paste ──
        if not args.models and not args.all_models:
            prompt_text = generate_audit_prompt(
                ticker=ticker,
                ticker_data=ticker_data,
                macro_context=macro,
                model_decisions=model_decisions,
                audit_date=audit_date,
            )
            print()
            print(prompt_text)
            if args.save:
                output_dir = ROOT / "docs" / "data" / "force_analysis"
                output_dir.mkdir(parents=True, exist_ok=True)
                ts    = datetime.now().strftime("%Y%m%d_%H%M")
                fname = output_dir / f"{ticker}_{ts}_audit_prompt.txt"
                fname.write_text(prompt_text, encoding="utf-8")
                print(f"[saved -> {fname.relative_to(ROOT)}]")
            print()
            return

        # ── API mode (--models specified): call arbitrator model ────────────
        # Warn if arbitrator is same as one of the evaluated models
        evaluated_ids = {d["model_id"] for d in model_decisions}
        for m in models:
            if m in evaluated_ids:
                print(f"\nNOTE: {model_short_name(m)} is also one of the evaluated models — consider using a different arbitrator.")

        payload = build_audit_payload(
            ticker=ticker,
            ticker_data=ticker_data,
            macro_context=macro,
            active_picks=active_picks,
            model_decisions=model_decisions,
            date_str=audit_date,
        )

        all_results: list[dict] = []
        for model_id in models:
            short = model_short_name(model_id)
            print(f"\n[{short}] arbitrating...", end="", flush=True)
            try:
                raw, latency_ms, in_tok, out_tok = call_model(
                    model_id, payload, max_tokens=1200,
                    system_prompt=AUDIT_SYSTEM_PROMPT,
                )
                result = parse_response(raw)
                print(f" done ({latency_ms / 1000:.1f}s, {in_tok}+{out_tok} tok)")
                print_audit_result(result, model_id, latency_ms)
                all_results.append({
                    "model":         model_id,
                    "success":       True,
                    "latency_ms":    round(latency_ms),
                    "input_tokens":  in_tok,
                    "output_tokens": out_tok,
                    "result":        result,
                })
            except json.JSONDecodeError as e:
                raw_val = locals().get("raw", "")
                print(f" PARSE ERROR")
                print_error(model_id, f"JSON parse error: {e}", raw_val)
                all_results.append({"model": model_id, "success": False, "error": str(e), "raw": raw_val})
            except Exception as e:
                print(f" ERROR")
                print_error(model_id, str(e))
                all_results.append({"model": model_id, "success": False, "error": str(e)})

        if args.save:
            _save_results(ticker, {
                "ticker":           ticker,
                "date":             date_str,
                "timestamp":        datetime.now().isoformat(timespec="seconds"),
                "type":             "audit",
                "audit_date":       audit_date,
                "compare_portfolio": None,
                "models":           models,
                "model_decisions":  model_decisions,
            }, all_results)

        print()
        return

    # ── NORMAL MODE ─────────────────────────────────────────────────────────────
    cands_data = _load_json(ROOT / "docs/data/ai_candidates.json")
    candidates = cands_data.get("candidates", [])
    macro      = cands_data.get("macro_context", {})
    cands_map  = {c["ticker"]: c for c in candidates}

    ticker_data = find_ticker_data(ticker, candidates)

    open_positions: list[dict] = []
    if args.compare_portfolio:
        picks = _load_json(ROOT / "docs/data/ai_picks.json")
        raw_pos = get_open_positions(picks, args.compare_portfolio)
        open_positions = enrich_positions(raw_pos, cands_map)
        if not open_positions:
            print(f"\nWARNING: no open positions found for portfolio filter '{args.compare_portfolio}'")

    print_header(ticker, ticker_data, macro, models, args.compare_portfolio)

    payload = build_payload(
        ticker=ticker,
        ticker_data=ticker_data,
        macro_context=macro,
        open_positions=open_positions,
        compare_portfolio=args.compare_portfolio,
        date_str=date_str,
    )

    all_results: list[dict] = []

    for model_id in models:
        short = model_short_name(model_id)
        print(f"\n[{short}] calling...", end="", flush=True)
        try:
            max_tok = _resolve_max_tokens(model_id, len(open_positions))
            raw, latency_ms, in_tok, out_tok = call_model(model_id, payload, max_tokens=max_tok)
            result = parse_response(raw)
            print(f" done ({latency_ms / 1000:.1f}s, {in_tok}+{out_tok} tok)")
            print_result(result, model_id, latency_ms)
            all_results.append({
                "model":         model_id,
                "success":       True,
                "latency_ms":    round(latency_ms),
                "input_tokens":  in_tok,
                "output_tokens": out_tok,
                "result":        result,
            })
        except json.JSONDecodeError as e:
            raw_val = locals().get("raw", "")
            print(f" PARSE ERROR")
            print_error(model_id, f"JSON parse error: {e}", raw_val)
            all_results.append({"model": model_id, "success": False, "error": str(e), "raw": raw_val})
        except Exception as e:
            print(f" ERROR")
            print_error(model_id, str(e))
            all_results.append({"model": model_id, "success": False, "error": str(e)})

    if args.save:
        _save_results(ticker, {
            "ticker":            ticker,
            "date":              date_str,
            "timestamp":         datetime.now().isoformat(timespec="seconds"),
            "type":              "analysis",
            "compare_portfolio": args.compare_portfolio,
            "models":            models,
        }, all_results)

    print()


if __name__ == "__main__":
    main()
