"""
Healthcare Sector First Filter — One-off Analysis
==================================================
Fetches fresh price data for 15 large-cap healthcare tickers, computes
relative-strength and momentum metrics vs SPY and XLV, then calls the AI
model to rank and filter them by category.

Categories:
  - Calidad/Growth:     LLY, ISRG, SYK, TMO, DHR, BSX, VRTX
  - Value/Turnaround:   UNH, HUM, CI, CVS
  - Defensivo Pharma:   JNJ, MRK, ABBV, PFE

Writes:  docs/data/healthcare_analysis_YYYY-MM-DD.json

Usage:
  py -3 scripts/analyze_healthcare.py
  py -3 scripts/analyze_healthcare.py --model anthropic/claude-sonnet-4.6
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "docs" / "data"

# ── Ticker universe ─────────────────────────────────────────────────────────────

HEALTHCARE_TICKERS: dict[str, dict] = {
    # category, full name, key thesis
    "LLY":  {"cat": "quality_growth",   "name": "Eli Lilly",                "thesis": "GLP-1 leader (Mounjaro/Zepbound), Alzheimer pipeline"},
    "ISRG": {"cat": "quality_growth",   "name": "Intuitive Surgical",       "thesis": "Surgical robotics monopoly, da Vinci platform"},
    "SYK":  {"cat": "quality_growth",   "name": "Stryker",                  "thesis": "Medical devices, serial acquirer"},
    "TMO":  {"cat": "quality_growth",   "name": "Thermo Fisher",            "thesis": "Life science instruments & reagents"},
    "DHR":  {"cat": "quality_growth",   "name": "Danaher",                  "thesis": "Scientific instruments, post-Veralto spinoff"},
    "BSX":  {"cat": "quality_growth",   "name": "Boston Scientific",        "thesis": "Cardiovascular & structural heart devices"},
    "VRTX": {"cat": "quality_growth",   "name": "Vertex Pharmaceuticals",   "thesis": "CF franchise dominant, pain/APOL1 pipeline"},
    "UNH":  {"cat": "value_turnaround", "name": "UnitedHealth Group",       "thesis": "Largest US insurer; regulatory/MLR pressure, possible turnaround"},
    "HUM":  {"cat": "value_turnaround", "name": "Humana",                   "thesis": "Medicare Advantage focus, elevated MLR turnaround play"},
    "CI":   {"cat": "value_turnaround", "name": "Cigna Group",              "thesis": "M&A blocked, aggressive buyback underway"},
    "CVS":  {"cat": "value_turnaround", "name": "CVS Health",               "thesis": "Most challenged: high debt, Aetna integration difficulties"},
    "JNJ":  {"cat": "defensive_pharma", "name": "Johnson & Johnson",        "thesis": "Talc litigation resolving, split MedTech+Pharma"},
    "MRK":  {"cat": "defensive_pharma", "name": "Merck",                    "thesis": "Keytruda patent cliff 2028, oncology pipeline bridge"},
    "ABBV": {"cat": "defensive_pharma", "name": "AbbVie",                   "thesis": "Post-Humira cliff executed, Skyrizi/Rinvoq growing"},
    "PFE":  {"cat": "defensive_pharma", "name": "Pfizer",                   "thesis": "Post-COVID restructuring, pipeline under scrutiny"},
}

TICKERS_LIST = list(HEALTHCARE_TICKERS.keys())

MODEL_PRICING: dict[str, tuple[float, float]] = {
    "anthropic/claude-haiku-4.5":  (1.00,  5.00),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
    "anthropic/claude-opus-4.7":   (15.00, 75.00),
    "x-ai/grok-4.3":               (1.25,  2.50),
}


# ── Data fetching ───────────────────────────────────────────────────────────────

def fetch_metrics(tickers: list[str]) -> dict[str, dict]:
    """
    Fetches ~3 months OHLCV data and computes:
      - ret_1w_vs_spy, ret_4w_vs_spy, ret_13w_vs_spy
      - ret_1w_vs_xlv, ret_4w_vs_xlv, ret_13w_vs_xlv
      - rsi_14, dist_52w_high_pct, sma50_vs_sma200 (golden/death cross)
      - current_price, market_cap_approx (skipped — needs separate call)
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        print("ERROR: yfinance or pandas not installed")
        return {}

    all_syms = sorted(set(tickers) | {"SPY", "XLV"})
    print(f"  Fetching data for {len(all_syms)} symbols…")
    try:
        raw = yf.download(all_syms, period="6mo", auto_adjust=True,
                          progress=False, threads=True)
    except Exception as e:
        print(f"  yfinance error: {e}")
        return {}

    if raw is None or raw.empty:
        print("  No data returned from yfinance")
        return {}

    try:
        if isinstance(raw.columns, pd.MultiIndex):
            close_df = raw["Close"].dropna(how="all")
            high_df  = raw["High"].dropna(how="all") if "High" in raw else pd.DataFrame()
            low_df   = raw["Low"].dropna(how="all")  if "Low"  in raw else pd.DataFrame()
        else:
            t0 = tickers[0] if tickers else "UNK"
            close_df = raw[["Close"]].rename(columns={"Close": t0})
            high_df  = raw[["High"]].rename(columns={"High": t0}) if "High" in raw else pd.DataFrame()
            low_df   = raw[["Low"]].rename(columns={"Low": t0})   if "Low"  in raw else pd.DataFrame()
    except Exception as e:
        print(f"  DataFrame parsing error: {e}")
        return {}

    if "SPY" not in close_df.columns or "XLV" not in close_df.columns:
        print("  Missing SPY or XLV data")
        return {}

    spy = close_df["SPY"]
    xlv = close_df["XLV"]

    def _pct(series: "pd.Series", n: int) -> float | None:
        """n-period return in %."""
        if len(series) < n + 1:
            return None
        try:
            return round(float((series.iloc[-1] / series.iloc[-n]) - 1) * 100, 2)
        except Exception:
            return None

    def _vs_spy(tkr_ret: float | None, spy_ret: float | None) -> float | None:
        if tkr_ret is None or spy_ret is None:
            return None
        return round(tkr_ret - spy_ret, 2)

    def _rsi(series: "pd.Series", period: int = 14) -> float | None:
        if len(series) < period + 1:
            return None
        try:
            delta  = series.diff().dropna()
            gains  = delta.clip(lower=0)
            losses = (-delta).clip(lower=0)
            avg_g  = gains.ewm(com=period - 1, adjust=False).mean().iloc[-1]
            avg_l  = losses.ewm(com=period - 1, adjust=False).mean().iloc[-1]
            if avg_l == 0:
                return 100.0
            rs = avg_g / avg_l
            return round(float(100 - (100 / (1 + rs))), 1)
        except Exception:
            return None

    def _dist_52w_high(tkr_close: "pd.Series", hi_df: "pd.DataFrame", tkr: str) -> float | None:
        """(current - 52w_high) / 52w_high as %."""
        try:
            last = float(tkr_close.iloc[-1])
            if not hi_df.empty and tkr in hi_df.columns:
                h52 = float(hi_df[tkr].tail(252).max())
            else:
                h52 = float(tkr_close.tail(252).max())
            return round((last / h52 - 1) * 100, 2)
        except Exception:
            return None

    def _sma_trend(series: "pd.Series") -> str | None:
        """50-day SMA vs 200-day SMA: 'above' (bullish) or 'below' (bearish)."""
        if len(series) < 200:
            return None
        try:
            sma50  = float(series.tail(50).mean())
            sma200 = float(series.tail(200).mean())
            return "above" if sma50 > sma200 else "below"
        except Exception:
            return None

    # approximate weekly/monthly periods
    W1, W4, W13 = 5, 21, 65

    results: dict[str, dict] = {}

    spy_1w  = _pct(spy, W1)
    spy_4w  = _pct(spy, W4)
    spy_13w = _pct(spy, W13)
    xlv_1w  = _pct(xlv, W1)
    xlv_4w  = _pct(xlv, W4)
    xlv_13w = _pct(xlv, W13)

    for tkr in tickers:
        if tkr not in close_df.columns:
            results[tkr] = {"error": "no_data"}
            continue
        s = close_df[tkr].dropna()
        if s.empty:
            results[tkr] = {"error": "empty_series"}
            continue

        t_1w  = _pct(s, W1)
        t_4w  = _pct(s, W4)
        t_13w = _pct(s, W13)

        results[tkr] = {
            "price":          round(float(s.iloc[-1]), 2),
            "ret_1w":         t_1w,
            "ret_4w":         t_4w,
            "ret_13w":        t_13w,
            "ret_1w_vs_spy":  _vs_spy(t_1w,  spy_1w),
            "ret_4w_vs_spy":  _vs_spy(t_4w,  spy_4w),
            "ret_13w_vs_spy": _vs_spy(t_13w, spy_13w),
            "ret_1w_vs_xlv":  _vs_spy(t_1w,  xlv_1w),
            "ret_4w_vs_xlv":  _vs_spy(t_4w,  xlv_4w),
            "ret_13w_vs_xlv": _vs_spy(t_13w, xlv_13w),
            "rsi_14":         _rsi(s),
            "dist_52w_high":  _dist_52w_high(s, high_df, tkr),
            "sma50_vs_sma200": _sma_trend(s),
        }

    # XLV metrics for context
    results["_xlv_context"] = {
        "ret_1w":   xlv_1w,
        "ret_4w":   xlv_4w,
        "ret_13w":  xlv_13w,
        "ret_1w_vs_spy":  _vs_spy(xlv_1w,  spy_1w),
        "ret_4w_vs_spy":  _vs_spy(xlv_4w,  spy_4w),
        "ret_13w_vs_spy": _vs_spy(xlv_13w, spy_13w),
        "rsi_14":   _rsi(xlv),
    }

    return results


def load_macro_context() -> dict:
    """Pull latest macro score and regime from macro_history.json."""
    p = DATA / "macro_history.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            latest = data[-1]
        elif isinstance(data, dict):
            latest = data.get("latest") or (data.get("history") or [{}])[-1]
        else:
            return {}
        return {
            "macro_score":   latest.get("score"),
            "macro_regime":  latest.get("regime"),
            "macro_trend":   latest.get("trend"),
            "macro_delta_1w": latest.get("delta_1w"),
        }
    except Exception:
        return {}


def load_xlv_rotation() -> dict:
    """Pull XLV rotation signal from rotation_signals.json."""
    p = DATA / "rotation_signals.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        sigs = data.get("latest_signals", [])
        for s in sigs:
            if s.get("ticker") == "XLV":
                return {
                    "xlv_rot_score": s.get("rot_score"),
                    "xlv_signal":    s.get("signal"),
                    "xlv_regime":    s.get("regime"),
                    "xlv_ret_4w_vs_spy":  s.get("ret_4w_vs_spy"),
                    "xlv_ret_13w_vs_spy": s.get("ret_13w_vs_spy"),
                }
    except Exception:
        pass
    return {}


# ── Prompt builder ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior portfolio manager specializing in US healthcare equities.

TASK: Given fresh price/momentum data for 15 large-cap healthcare stocks across
three categories, provide a structured first-pass analysis to help determine
which names and categories offer the best current risk/reward entry points.

CRITICAL: Respond ONLY with valid JSON — no markdown fences, no explanation,
no text before or after the JSON object.

CONTEXT: These are established large-cap companies, NOT momentum/speculative plays.
The analysis should combine:
1. Technical momentum (how are they performing vs XLV and SPY right now?)
2. Fundamental context (category dynamics, key risks per name)
3. Macro fit (does the current regime favor this style of healthcare?)

CATEGORIES:
- quality_growth: Compounding growers with durable competitive moats (LLY, ISRG, SYK, TMO, DHR, BSX, VRTX)
- value_turnaround: Managed care names under pressure — potential contrarian plays (UNH, HUM, CI, CVS)
- defensive_pharma: Dividend-payers with patent cliff risks — defensive positioning (JNJ, MRK, ABBV, PFE)

OUTPUT SCHEMA (strict JSON, fill all fields):
{
  "date": "YYYY-MM-DD",
  "analysis_type": "healthcare_first_filter",
  "sector_read": {
    "xlv_posture": "favorable|neutral|unfavorable",
    "xlv_vs_spy_trend": "<1 sentence on XLV momentum vs broad market>",
    "macro_fit": "<1 sentence: does current macro regime favor defensive healthcare, growth healthcare, or neither?>"
  },
  "category_rankings": [
    {
      "category": "quality_growth|value_turnaround|defensive_pharma",
      "attractiveness": "high|medium|low",
      "rationale": "<2-3 sentences citing specific data>",
      "best_entry_timing": "now|wait_for_pullback|avoid_near_term"
    }
  ],
  "ticker_analysis": [
    {
      "ticker": "...",
      "category": "...",
      "verdict": "buy_candidate|watch|avoid",
      "momentum_score": "strong|moderate|weak|negative",
      "key_positives": ["<specific sentence with numbers>"],
      "key_risks": ["<specific sentence with numbers>"],
      "entry_note": "<1 sentence on timing/conditions for entry>"
    }
  ],
  "top_picks": {
    "immediate_watchlist": ["ticker1", "ticker2", "ticker3"],
    "wait_and_monitor": ["ticker1", "ticker2"],
    "avoid_for_now": ["ticker1"]
  },
  "summary": "<3-4 sentences overall conclusion>"
}"""


def build_user_message(metrics: dict, macro: dict, xlv_rot: dict) -> str:
    tickers_data = []
    for tkr, meta in HEALTHCARE_TICKERS.items():
        m = metrics.get(tkr, {})
        tickers_data.append({
            "ticker":          tkr,
            "name":            meta["name"],
            "category":        meta["cat"],
            "thesis":          meta["thesis"],
            "price":           m.get("price"),
            "ret_1w":          m.get("ret_1w"),
            "ret_4w":          m.get("ret_4w"),
            "ret_13w":         m.get("ret_13w"),
            "ret_1w_vs_spy":   m.get("ret_1w_vs_spy"),
            "ret_4w_vs_spy":   m.get("ret_4w_vs_spy"),
            "ret_13w_vs_spy":  m.get("ret_13w_vs_spy"),
            "ret_1w_vs_xlv":   m.get("ret_1w_vs_xlv"),
            "ret_4w_vs_xlv":   m.get("ret_4w_vs_xlv"),
            "ret_13w_vs_xlv":  m.get("ret_13w_vs_xlv"),
            "rsi_14":          m.get("rsi_14"),
            "dist_52w_high":   m.get("dist_52w_high"),
            "sma50_vs_sma200": m.get("sma50_vs_sma200"),
        })

    payload = {
        "date":     str(date.today()),
        "context":  "First-pass healthcare sector analysis — portfolio seeding",
        "macro_context": macro,
        "xlv_sector_rotation": xlv_rot,
        "xlv_price_metrics": metrics.get("_xlv_context", {}),
        "tickers": tickers_data,
        "notes": {
            "CVS": "flagged as most problematic — high debt load and Aetna integration challenges",
            "managed_care_group": "UNH, HUM, CI, CVS all under pressure from MLR deterioration and regulatory scrutiny",
            "quality_growth_group": "some names (LLY, BSX) may be extended — consider dist_52w_high carefully",
        },
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


# ── Model call ──────────────────────────────────────────────────────────────────

def call_model(
    model: str,
    system: str,
    user_message: str,
    max_tokens: int = 4096,
) -> tuple[str, int, int, float]:
    """Call model via OpenRouter. Returns (raw_text, in_tokens, out_tokens, latency_ms)."""
    from openai import OpenAI
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set — check your .env file")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/market-tracker",
            "X-Title":      "AI Picks Lab - Healthcare Analysis",
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
    text    = resp.choices[0].message.content or ""
    in_tok  = resp.usage.prompt_tokens
    out_tok = resp.usage.completion_tokens
    return text, in_tok, out_tok, (time.monotonic() - t0) * 1000


def compute_cost(model: str, in_tok: int, out_tok: int) -> float:
    in_p, out_p = MODEL_PRICING.get(model, (0.0, 0.0))
    return (in_tok * in_p + out_tok * out_p) / 1_000_000


def parse_json(raw: str) -> dict | None:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$",       "", text)
    if not text.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", text)
        text = m.group(0) if m else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ── Pretty printer ──────────────────────────────────────────────────────────────

def print_results(analysis: dict, metrics: dict) -> None:
    print("\n" + "═" * 72)
    print("  HEALTHCARE SECTOR — FIRST FILTER ANALYSIS")
    print(f"  {analysis.get('date', date.today())}")
    print("═" * 72)

    sr = analysis.get("sector_read", {})
    print(f"\n📊 XLV POSTURE: {sr.get('xlv_posture', '?').upper()}")
    print(f"   {sr.get('xlv_vs_spy_trend', '')}")
    print(f"   {sr.get('macro_fit', '')}")

    print("\n📂 CATEGORY RANKINGS:")
    for cat in analysis.get("category_rankings", []):
        label = {
            "quality_growth":   "Calidad/Growth",
            "value_turnaround": "Value/Turnaround",
            "defensive_pharma": "Defensivo Pharma",
        }.get(cat.get("category", ""), cat.get("category", ""))
        att   = cat.get("attractiveness", "?").upper()
        timing = cat.get("best_entry_timing", "?")
        print(f"\n  [{att}] {label} — timing: {timing}")
        print(f"  {cat.get('rationale', '')}")

    print("\n🔍 TICKER ANALYSIS:")
    for t in analysis.get("ticker_analysis", []):
        tkr   = t.get("ticker", "?")
        meta  = HEALTHCARE_TICKERS.get(tkr, {})
        m     = metrics.get(tkr, {})
        verd  = t.get("verdict", "?")
        mom   = t.get("momentum_score", "?")
        icon  = {"buy_candidate": "✅", "watch": "👀", "avoid": "❌"}.get(verd, "·")
        r4w   = m.get("ret_4w_vs_spy")
        r13w  = m.get("ret_13w_vs_spy")
        rsi   = m.get("rsi_14")
        d52   = m.get("dist_52w_high")
        print(f"\n  {icon} {tkr:5s} ({meta.get('name', '')})")
        print(f"     momentum: {mom}  |  4w vs SPY: {r4w:+.1f}%  |  13w vs SPY: {r13w:+.1f}%  |  RSI: {rsi}  |  52w: {d52:+.1f}%" if all(x is not None for x in [r4w, r13w, rsi, d52]) else f"     momentum: {mom}")
        for pos in (t.get("key_positives") or []):
            print(f"     + {pos}")
        for neg in (t.get("key_risks") or []):
            print(f"     - {neg}")
        print(f"     → {t.get('entry_note', '')}")

    tp = analysis.get("top_picks", {})
    print("\n🏆 TOP PICKS SUMMARY:")
    now  = tp.get("immediate_watchlist", [])
    wait = tp.get("wait_and_monitor", [])
    avoid = tp.get("avoid_for_now", [])
    print(f"  Immediate watchlist : {', '.join(now) if now else '—'}")
    print(f"  Wait & monitor      : {', '.join(wait) if wait else '—'}")
    print(f"  Avoid for now       : {', '.join(avoid) if avoid else '—'}")

    print(f"\n📝 SUMMARY:")
    print(f"  {analysis.get('summary', '')}")
    print("═" * 72 + "\n")


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    # Ensure UTF-8 output on Windows terminals
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    parser = argparse.ArgumentParser(description="Healthcare sector first-filter analysis")
    parser.add_argument(
        "--model",
        default=os.getenv("ACTIVE_MODEL", "anthropic/claude-haiku-4.5"),
        help="OpenRouter model slug (default: ACTIVE_MODEL env or claude-haiku-4.5)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save output to docs/data/",
    )
    args = parser.parse_args()

    model = args.model
    today = str(date.today())

    print(f"\n🔬 Healthcare First Filter — {today}")
    print(f"   Model: {model}")

    # 1. Fetch metrics
    print("\n[1/4] Fetching price & momentum data…")
    metrics = fetch_metrics(TICKERS_LIST)
    if not metrics:
        print("ERROR: Could not fetch metrics. Aborting.")
        sys.exit(1)

    ok_count = sum(1 for t in TICKERS_LIST if "error" not in metrics.get(t, {"error": "x"}))
    print(f"       Got data for {ok_count}/{len(TICKERS_LIST)} tickers")

    # 2. Load macro & XLV rotation
    print("[2/4] Loading macro context…")
    macro   = load_macro_context()
    xlv_rot = load_xlv_rotation()
    if macro:
        print(f"       Macro: {macro.get('macro_score')} / regime: {macro.get('macro_regime')} / trend: {macro.get('macro_trend')}")
    if xlv_rot:
        print(f"       XLV  : rot_score={xlv_rot.get('xlv_rot_score')} / signal={xlv_rot.get('xlv_signal')}")

    # 3. Build prompt & call model
    print("[3/4] Building prompt & calling model…")
    user_msg  = build_user_message(metrics, macro, xlv_rot)
    print(f"       Payload size: ~{len(user_msg)//1000}k chars")

    try:
        raw, in_tok, out_tok, latency_ms = call_model(model, SYSTEM_PROMPT, user_msg)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR calling model: {e}")
        sys.exit(1)

    cost = compute_cost(model, in_tok, out_tok)
    print(f"       Tokens: {in_tok} in / {out_tok} out  |  cost: ${cost:.4f}  |  latency: {latency_ms:.0f}ms")

    # 4. Parse & display
    print("[4/4] Parsing response…")
    analysis = parse_json(raw)

    if not analysis:
        print("WARNING: Could not parse JSON response. Raw output saved.")
        analysis = {"_raw": raw, "date": today, "parse_error": True}

    # Display
    if not analysis.get("parse_error"):
        print_results(analysis, metrics)

    # Save
    if not args.no_save:
        out_path = DATA / f"healthcare_analysis_{today}.json"
        result = {
            "date":      today,
            "model":     model,
            "cost_usd":  round(cost, 6),
            "latency_ms": round(latency_ms),
            "in_tokens":  in_tok,
            "out_tokens": out_tok,
            "metrics":   {t: metrics[t] for t in TICKERS_LIST if t in metrics},
            "xlv_context": metrics.get("_xlv_context", {}),
            "macro":     macro,
            "xlv_rotation": xlv_rot,
            "analysis":  analysis,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n💾 Saved → {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
