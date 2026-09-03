"""
ranking_score_calculator.py -- Ranking Score SHADOW (Fase 2)

Implementa la seccion "2.1/2.2 Diseno del Ranking Score / Calculo shadow"
del texto de Fase 2 (pegado por el usuario 2026-09-04), sobre los pesos de
bucket congelados en wiki/PREREGISTRO_RANKING_SCORE_V0.md Sec.1. Corre en
CADA corrida del pipeline (no solo semanalmente -- eso es la cartera
experimental, en scripts/ranking_score_experimental_portfolio.py).

"shadow" es literal: estos campos NO entran en `compact_candidate()`
(scripts/ai_shared.py), asi que nunca llegan al payload del LLM ni pueden
influir en las 4 carteras clasicas -- solo se guardan en
docs/data/ai_candidates.json para el experimento.

FORMULA -- decision de esta sesion (2026-09-04), NO parte del preregistro
ni del texto de Fase 2: ninguno de los dos fija sub-pesos dentro de cada
bucket, solo los pesos de bucket (30/25/20/15/10) y la lista de componentes
por bucket. Documentado tambien en CLAUDE.md, seccion "Ranking Score --
Fase 2". Regla: media equitativa (renormalizada si falta algun componente)
de sub-scores 0-100 dentro de cada bucket; suma ponderada de buckets
(renormalizada sobre los buckets con dato) para el score final.

rot_score_delta_4w / streak_weeks_delta / theme_flow_delta se calculan
contra el commit de docs/data/ai_candidates.json mas cercano a "hoy - 28
dias" (ventana +-5 dias) -- reutiliza list_commits()/candidates_at_commit()
de reconstruct_pcs_components_historical.py en vez de mantener un fichero
de serie temporal propio: el historico ya existe en git (commiteado 2x/dia
desde 2026-05-08), asi que no hace falta esperar semanas a que se acumule
un fichero nuevo desde cero.

Uso:
    py -3 scripts/ranking_score_calculator.py              # calcula y escribe
    py -3 scripts/ranking_score_calculator.py --dry-run     # calcula, no escribe
    py -3 scripts/ranking_score_calculator.py --report      # resumen de cobertura/distribucion
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
CANDIDATES_JSON = DATA / "ai_candidates.json"
SHADOW_PICKS = DATA / "shadow_picks.jsonl"

sys.path.insert(0, str(Path(__file__).parent))
from reconstruct_pcs_components_historical import list_commits, candidates_at_commit  # reuso
from compare_vs_baselines import dedup_same_day_reruns  # reuso

LOOKBACK_DAYS = 28
LOOKBACK_WINDOW = 5  # +-dias de tolerancia, mismo criterio que la reconstruccion historica

BUCKET_WEIGHTS = {
    "entry_quality_score": 0.30,
    "flow_institutional_score": 0.25,
    "signal_change_score": 0.20,
    "sectoral_context_score": 0.15,
    "cooldown_score": 0.10,
}

# Los mismos 5 campos criticos que ya definio scripts/ranking_score_fase1_analysis.py
CRITICAL_FIELDS = ["extension_risk", "konc_3d_state", "konc_w_state", "rot_score_delta_4w", "theme_breadth"]
TRACKED_FIELDS = [
    "extension_risk", "dist_sma20_atr", "rsi_14", "spike_flag", "momentum_decay",
    "konc_3d_state", "konc_w_state", "konc_alignment",
    "rot_score_delta_4w", "streak_weeks_delta", "theme_flow_delta",
    "theme_breadth", "vehicle_vs_theme_strength",
]


# -- I/O ------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# -- Lookback (28 dias) via git-history, sin fichero de serie temporal propio ----

def build_commit_index() -> dict[str, list[str]]:
    by_date: dict[str, list[str]] = {}
    for h, d in list_commits():
        by_date.setdefault(d, []).append(h)
    return by_date


def closest_commit_for_date(by_date: dict[str, list[str]], target_date_str: str,
                             window: int = LOOKBACK_WINDOW) -> str | None:
    target = datetime.strptime(target_date_str, "%Y-%m-%d")
    best, best_diff = None, None
    for d, hashes in by_date.items():
        diff = abs((datetime.strptime(d, "%Y-%m-%d") - target).days)
        if diff <= window and (best_diff is None or diff < best_diff):
            best_diff, best = diff, hashes[-1]
    return best


def get_lookback_candidates(today_str: str) -> dict[str, dict]:
    by_date = build_commit_index()
    target = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    commit = closest_commit_for_date(by_date, target)
    if not commit:
        return {}
    return candidates_at_commit(commit)


# -- Cooldown (dias desde el ultimo pick del mismo ticker, cualquier cartera) ---

def build_cooldown_index() -> dict[str, list[str]]:
    picks = dedup_same_day_reruns(load_jsonl(SHADOW_PICKS))
    idx: dict[str, list[str]] = {}
    for p in picks:
        t, d = p.get("ticker"), p.get("date")
        if t and d:
            idx.setdefault(t, []).append(d)
    for t in idx:
        idx[t].sort()
    return idx


def cooldown_days_for(idx: dict[str, list[str]], ticker: str, today_str: str) -> int | None:
    dates = idx.get(ticker, [])
    prior = [d for d in dates if d < today_str]
    if not prior:
        return None
    last = max(prior)
    try:
        return (date.fromisoformat(today_str) - date.fromisoformat(last)).days
    except ValueError:
        return None


# -- Theme breadth (live) -- misma definicion exacta que reconstruct_theme_breadth_historical.py --

def build_theme_breadth_index(candidates: list[dict]) -> dict[str, tuple[int, int]]:
    breadth: dict[str, int] = {}
    total: dict[str, int] = {}
    for c in candidates:
        th = c.get("theme")
        if not th:
            continue
        total[th] = total.get(th, 0) + 1
        if c.get("eligible"):
            breadth[th] = breadth.get(th, 0) + 1
    return {th: (breadth.get(th, 0), total.get(th, 0)) for th in total}


# -- Sub-scores 0-100 por componente (ver docstring del modulo) -----------------

def score_extension_risk(v: str | None) -> float | None:
    return {"low": 100.0, "medium": 66.7, "high": 33.3, "extreme": 0.0}.get(v)


def score_dist_sma20_atr(v: float | None) -> float | None:
    # 100 en dist<=0, 0 en dist>=3.0 ATR (mismo umbral "extreme" que pcs_calculator.compute_extension_risk)
    if v is None:
        return None
    return round(100.0 * (1 - min(max(v, 0.0), 3.0) / 3.0), 1)


def score_bool_good_if_false(v: bool | None) -> float | None:
    # spike_flag, momentum_decay: bueno si NO ocurre
    if v is None:
        return None
    return 0.0 if v else 100.0


def score_rsi_zone(v: float | None) -> float | None:
    if v is None:
        return None
    return 100.0 if 45.0 <= v <= 65.0 else 0.0


def score_konc_state(v: str | None) -> float | None:
    return {"accumulation": 100.0, "up": 75.0, "down": 25.0, "distribution": 0.0}.get(v)


def score_konc_alignment(v: str | None) -> float | None:
    return {
        "bearish_aligned": 0.0,
        "distribution_warning": 16.7,
        "mixed": 50.0,
        "neutral": 50.0,
        "bullish_pending_3d_confirmation": 66.7,
        "accumulation_setup": 83.3,
        "bullish_aligned": 100.0,
    }.get(v)


def score_signed_delta(v: float | None, cap: float) -> float | None:
    if v is None:
        return None
    return round(50.0 + 50.0 * min(max(v, -cap), cap) / cap, 1)


def score_theme_breadth(v: int | None, cap: float = 15.0) -> float | None:
    if v is None:
        return None
    return round(100.0 * min(max(v, 0), cap) / cap, 1)


def score_cooldown(days: int | None, horizon: float = float(LOOKBACK_DAYS)) -> float:
    if days is None:
        return 100.0  # nunca pickeado -> sin conflicto de cooldown
    return round(100.0 * min(max(days, 0), horizon) / horizon, 1)


def bucket_avg(scores: list[float | None]) -> float | None:
    vals = [s for s in scores if s is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def build_reason_flags(raw: dict) -> list[str]:
    flags = []
    if raw.get("extension_risk") == "low":
        flags.append("low_extension_risk")
    if raw.get("extension_risk") in ("high", "extreme"):
        flags.append("high_extension_risk")
    if raw.get("konc_3d_state") == "accumulation":
        flags.append("koncorde_3d_accumulation")
    if raw.get("konc_w_state") == "accumulation":
        flags.append("koncorde_w_accumulation")
    if raw.get("konc_3d_state") == "distribution" or raw.get("konc_w_state") == "distribution":
        flags.append("koncorde_distribution_warning")
    rsd = raw.get("rot_score_delta_4w")
    if rsd is not None and rsd > 0:
        flags.append("rot_score_improving")
    elif rsd is not None and rsd < 0:
        flags.append("rot_score_weakening")
    swd = raw.get("streak_weeks_delta")
    if swd is not None and swd > 0:
        flags.append("streak_extending")
    tfd = raw.get("theme_flow_delta")
    if tfd is not None and tfd > 0:
        flags.append("theme_flow_improving")
    if raw.get("spike_flag"):
        flags.append("spike_risk")
    if raw.get("momentum_decay"):
        flags.append("momentum_decaying")
    rsi = raw.get("rsi_14")
    if rsi is not None and 45.0 <= rsi <= 65.0:
        flags.append("rsi_sweet_spot")
    cd = raw.get("cooldown_days")
    if cd is not None and cd < LOOKBACK_DAYS:
        flags.append("recent_pick_cooldown_active")
    return flags


def compute_for_candidate(
    c: dict, lookback_cands: dict[str, dict], theme_idx: dict[str, tuple[int, int]],
    cooldown_idx: dict[str, list[str]], today_str: str,
) -> dict:
    ticker = c.get("ticker")
    daily = c.get("daily_signals") or {}
    prior = lookback_cands.get(ticker)

    rot_entry = c.get("rot_score")
    rot_prior = prior.get("rot_score") if prior else None
    rot_delta = (rot_entry - rot_prior) if (rot_entry is not None and rot_prior is not None) else None

    streak_entry = c.get("streak_weeks")
    streak_prior = prior.get("streak_weeks") if prior else None
    streak_delta = (
        streak_entry - streak_prior if (streak_entry is not None and streak_prior is not None) else None
    )

    comp_b_entry = c.get("component_B")
    comp_b_prior = (prior.get("pcs_components") or {}).get("B_theme_flow") if prior else None
    theme_flow_delta = (
        comp_b_entry - comp_b_prior if (comp_b_entry is not None and comp_b_prior is not None) else None
    )

    theme_breadth, theme_total = theme_idx.get(c.get("theme"), (None, None))
    cooldown_days = cooldown_days_for(cooldown_idx, ticker, today_str)

    raw = {
        "extension_risk":       c.get("extension_risk"),
        "dist_sma20_atr":       daily.get("dist_sma20_atr"),
        "rsi_14":               daily.get("rsi_14"),
        "spike_flag":           daily.get("spike_flag"),
        "momentum_decay":       daily.get("momentum_decay"),
        "konc_3d_state":        c.get("konc_3d_state"),
        "konc_w_state":         c.get("konc_w_state"),
        "konc_alignment":       c.get("konc_alignment"),
        "rot_score_delta_4w":   rot_delta,
        "streak_weeks_delta":   streak_delta,
        "theme_flow_delta":     theme_flow_delta,
        "theme_breadth":        theme_breadth,
        "theme_total":          theme_total,
        "vehicle_vs_theme_strength": None,  # nunca implementado, ver Fase 1
        "cooldown_days":        cooldown_days,
    }

    entry_quality_score = bucket_avg([
        score_extension_risk(raw["extension_risk"]),
        score_dist_sma20_atr(raw["dist_sma20_atr"]),
        score_bool_good_if_false(raw["spike_flag"]),
        score_rsi_zone(raw["rsi_14"]),
        score_bool_good_if_false(raw["momentum_decay"]),
    ])
    flow_institutional_score = bucket_avg([
        score_konc_state(raw["konc_3d_state"]),
        score_konc_state(raw["konc_w_state"]),
        score_konc_alignment(raw["konc_alignment"]),
    ])
    signal_change_score = bucket_avg([
        score_signed_delta(raw["rot_score_delta_4w"], 5.0),
        score_signed_delta(raw["streak_weeks_delta"], 4.0),
        score_signed_delta(raw["theme_flow_delta"], 12.0),
    ])
    sectoral_context_score = bucket_avg([
        score_theme_breadth(raw["theme_breadth"]),
        None,  # vehicle_vs_theme_strength
    ])
    cooldown_score = score_cooldown(raw["cooldown_days"])

    bucket_scores = {
        "entry_quality_score": entry_quality_score,
        "flow_institutional_score": flow_institutional_score,
        "signal_change_score": signal_change_score,
        "sectoral_context_score": sectoral_context_score,
        "cooldown_score": cooldown_score,
    }
    avail = {k: v for k, v in bucket_scores.items() if v is not None}
    if avail:
        wsum = sum(BUCKET_WEIGHTS[k] for k in avail)
        candidate_ranking_score_shadow = round(
            sum(BUCKET_WEIGHTS[k] * v for k, v in avail.items()) / wsum, 1
        )
    else:
        candidate_ranking_score_shadow = None

    present = [raw.get(f) is not None for f in TRACKED_FIELDS]
    data_quality = round(sum(present) / len(present), 2)
    missing_fields = [f for f in TRACKED_FIELDS if raw.get(f) is None]
    critical_ok = all(raw.get(f) is not None for f in CRITICAL_FIELDS)
    eligible_flag = bool(critical_ok and data_quality >= 0.80)

    return {
        "candidate_ranking_score_shadow": candidate_ranking_score_shadow,
        **bucket_scores,
        "ranking_score_components": raw,
        "ranking_score_reason_flags": build_reason_flags(raw),
        "ranking_score_data_quality": data_quality,
        "ranking_score_missing_fields": missing_fields,
        "ranking_score_eligible": eligible_flag,
    }


def run(dry_run: bool, report: bool) -> int:
    today_str = str(date.today())
    data = load_json(CANDIDATES_JSON)
    candidates = data.get("candidates", [])
    if not candidates:
        print("ai_candidates.json vacio o no encontrado -- corre pcs_calculator.py primero.")
        return 1

    print("Building 28-day lookback index (git-history)...")
    lookback_cands = get_lookback_candidates(today_str)
    print(f"  {len(lookback_cands)} candidatos en el commit de referencia (~{LOOKBACK_DAYS}d atras).")

    theme_idx = build_theme_breadth_index(candidates)
    cooldown_idx = build_cooldown_index()

    n_eligible = 0
    scores = []
    for c in candidates:
        result = compute_for_candidate(c, lookback_cands, theme_idx, cooldown_idx, today_str)
        c.update(result)
        if result["ranking_score_eligible"]:
            n_eligible += 1
        if result["candidate_ranking_score_shadow"] is not None:
            scores.append(result["candidate_ranking_score_shadow"])

    print(f"Ranking Score calculado para {len(candidates)} candidatos "
          f"({n_eligible} ranking_score_eligible=true).")
    if scores:
        scores.sort()
        print(f"  score: min={scores[0]:.1f} p50={scores[len(scores)//2]:.1f} max={scores[-1]:.1f}")

    if report:
        return 0

    if dry_run:
        print("Dry-run: no se ha escrito ai_candidates.json.")
        return 0

    write_json(CANDIDATES_JSON, data)
    print(f"  wrote {CANDIDATES_JSON}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true", help="calcula e imprime, no escribe")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run, report=args.report))


if __name__ == "__main__":
    main()
