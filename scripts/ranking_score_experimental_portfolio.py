"""
ranking_score_experimental_portfolio.py -- cartera RANKING_SHADOW_EXPERIMENTAL
+ las 7 baselines shadow obligatorias (Fase 2, texto pegado 2026-09-04,
secciones 2.3/2.5, sobre wiki/PREREGISTRO_RANKING_SCORE_V0.md Sec.2-3).

Cartera 100% MECANICA/DETERMINISTA -- el LLM NO participa en la seleccion
(ni HARD_RULES ni ranking). Requiere que scripts/ranking_score_calculator.py
ya haya corrido en este mismo pase del pipeline (necesita
candidate_ranking_score_shadow/ranking_score_eligible ya escritos en
ai_candidates.json).

Cadencia (regla fija, seccion 2.3): la SELECCION de nuevas posiciones y las
7 baselines solo corren los viernes (UTC) -- el resto de la semana el script
solo revisa salidas mecanicas de las posiciones ya abiertas. Auto-gate
interno (no vive en el workflow YAML, a diferencia del gate is_morning de
Mirror Espejo/Insider Activity) -- usar --force para saltarselo en pruebas
manuales.

Reglas de salida (seccion 2.3, literal -- "No hay salida basada en Ranking
Score. El experimento evalua entrada, no salida."): la UNICA salida
automatica es "hard failure" (el ticker desaparece por completo del
universo de candidatos de hoy). PCS<55 y la revision a las 4 semanas se
guardan como FLAGS visibles (`pcs_review_flag`, `review_due`), nunca cierran
la posicion -- "Cuando exista el Follow-through engine (Fase 4), integrarlo
aqui" implica que hoy no hay regla determinista para decidir HOLD/EXIT en
esos dos casos, asi que no se inventa una.

Uso:
    py -3 scripts/ranking_score_experimental_portfolio.py              # dry-run
    py -3 scripts/ranking_score_experimental_portfolio.py --apply       # aplica de verdad (solo hace algo nuevo en viernes, salvo --force)
    py -3 scripts/ranking_score_experimental_portfolio.py --apply --force  # ignora el gate de viernes (pruebas manuales)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

CANDIDATES_JSON = DATA / "ai_candidates.json"
PICKS_JSON      = DATA / "ai_picks.json"
SHADOW_PICKS    = DATA / "shadow_picks.jsonl"
BASELINES_LOG   = DATA / "ranking_score_baselines.jsonl"
WEEKLY_METRICS  = DATA / "ranking_score_weekly_metrics.jsonl"

sys.path.insert(0, str(Path(__file__).parent))
from ai_shared import NON_TRADABLE_SUBTHEMES  # reuso, no reimplemento

PORTFOLIO_NAME = "RANKING_SHADOW_EXPERIMENTAL"
CLASSIC_PORTFOLIOS = [
    "HIGH_CONVICTION", "CONFIRMED_FLOW_LEADERS", "EARLY_ROTATION", "MACRO_THEMATIC_BENEFICIARIES",
]

PCS_MIN_UNIVERSE = 62.0
TOP_N = 5
MAX_POSITIONS = 10
SIZE_PCT = 5.0
COOLDOWN_DAYS = 28  # 4 semanas, mismo horizonte que el resto del sistema
PCS_REVIEW_FLOOR = 55.0
REVIEW_WEEKS = 4
RANDOM_SEEDS = [0, 1, 2, 3, 4]

# HARD_RULE explicita (ejemplo literal del texto de Fase 2) -- ademas de
# NON_TRADABLE_SUBTHEMES (ya excluye crude_oil_leveraged/futures/etc a nivel
# de subtheme), un denylist directo de ticker por si algun apalancado
# entrase bajo otro subtheme.
LEVERAGED_ETF_TICKERS = frozenset({
    "UCO", "SCO", "TQQQ", "SQQQ", "SOXL", "SOXS", "LABU", "LABD",
    "JNUG", "JDST", "NUGT", "DUST", "BOIL", "KOLD", "UPRO", "SPXU",
    "TNA", "TZA", "FAS", "FAZ", "TMF", "TMV", "YINN", "YANG",
})


# -- I/O ------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def fetch_last_closes(tickers: list[str]) -> dict[str, float]:
    if not tickers:
        return {}
    out: dict[str, float] = {}
    try:
        raw = yf.download(tickers, period="5d", auto_adjust=True, progress=False, group_by="ticker")
    except Exception as e:
        print(f"  ⚠ fetch_last_closes error: {e}")
        return out
    for tk in tickers:
        try:
            series = raw[tk]["Close"].dropna()
            if len(series):
                out[tk] = float(series.iloc[-1])
        except Exception:
            continue
    return out


# -- Universo elegible (seccion 2.3) --------------------------------------------

def build_open_elsewhere(picks: dict) -> set[str]:
    open_tickers: set[str] = set()
    for name in CLASSIC_PORTFOLIOS:
        ptf = picks.get("portfolios", {}).get(name, {})
        for pos in ptf.get("positions", []):
            if pos.get("ticker"):
                open_tickers.add(pos["ticker"])
    return open_tickers


def build_own_cooldown(ptf: dict, today_str: str) -> set[str]:
    """Tickers cerrados por esta misma cartera hace menos de COOLDOWN_DAYS."""
    blocked = set()
    today = date.fromisoformat(today_str)
    for ev in ptf.get("history", []):
        if ev.get("event") != "close":
            continue
        cd = ev.get("close_date")
        if not cd:
            continue
        try:
            days = (today - date.fromisoformat(cd)).days
        except ValueError:
            continue
        if 0 <= days < COOLDOWN_DAYS:
            blocked.add(ev["ticker"])
    return blocked


def is_leveraged_or_nontradable(c: dict) -> bool:
    if c.get("ticker") in LEVERAGED_ETF_TICKERS:
        return True
    if c.get("subtheme") in NON_TRADABLE_SUBTHEMES:
        return True
    return False


def build_universe(candidates: list[dict], picks: dict, ptf: dict, today_str: str,
                    require_ranking_eligible: bool) -> list[dict]:
    open_elsewhere = build_open_elsewhere(picks)
    own_positions = {p["ticker"] for p in ptf.get("positions", [])}
    own_cooldown = build_own_cooldown(ptf, today_str)

    universe = []
    for c in candidates:
        if not c.get("eligible"):
            continue
        pcs = c.get("pcs")
        if pcs is None or pcs < PCS_MIN_UNIVERSE:
            continue
        if require_ranking_eligible and not c.get("ranking_score_eligible"):
            continue
        if is_leveraged_or_nontradable(c):
            continue
        tk = c["ticker"]
        if tk in open_elsewhere or tk in own_positions or tk in own_cooldown:
            continue
        universe.append(c)
    return universe


# -- Salidas mecanicas (seccion 2.3) --------------------------------------------

def review_positions(ptf: dict, candidates_by_ticker: dict[str, dict], today_str: str) -> list[dict]:
    """Hard failure -> EXIT (unica salida automatica). PCS<55 y >=4 semanas
    mantenidas solo se marcan como flags visibles, nunca cierran la posicion
    (ver docstring del modulo)."""
    positions = ptf.get("positions", [])
    if not positions:
        return []
    tickers = [p["ticker"] for p in positions]
    closes = fetch_last_closes(tickers)

    remaining, closed = [], []
    today = date.fromisoformat(today_str)
    for pos in positions:
        tk = pos["ticker"]
        cand = candidates_by_ticker.get(tk)
        if cand is None:
            price = closes.get(tk)
            ptf.setdefault("history", []).append({
                **pos, "event": "close", "close_date": today_str,
                "close_price": price,
                "close_reason": "left_universe (hard failure -- ticker ya no aparece en ai_candidates.json)",
            })
            closed.append({"ticker": tk, "close_price": price})
            print(f"  [{PORTFOLIO_NAME}] EXIT {tk}: left_universe (hard failure)")
            continue

        pos["current_pcs"] = cand.get("pcs")
        pos["pcs_review_flag"] = bool(cand.get("pcs") is not None and cand["pcs"] < PCS_REVIEW_FLOOR)
        try:
            weeks_held = (today - date.fromisoformat(pos["entry_date"])).days / 7.0
        except (KeyError, ValueError):
            weeks_held = None
        pos["weeks_held"] = round(weeks_held, 1) if weeks_held is not None else None
        pos["review_due"] = bool(weeks_held is not None and weeks_held >= REVIEW_WEEKS)
        remaining.append(pos)

    ptf["positions"] = remaining
    return closed


# -- Entradas (seccion 2.3, solo viernes salvo --force) -------------------------

def select_entries(universe: list[dict], ptf: dict) -> list[dict]:
    ranked = sorted(
        universe,
        key=lambda c: (c.get("candidate_ranking_score_shadow") or 0.0, c.get("pcs") or 0.0),
        reverse=True,
    )
    room = MAX_POSITIONS - len(ptf.get("positions", []))
    if room <= 0:
        return []
    return ranked[:min(TOP_N, room)]


def log_to_shadow_picks(c: dict, today_str: str, entry_price: float | None) -> None:
    """Para que update_performance.py rellene ret_1w/2w/1m/3m/MFE/MAE igual
    que al resto de carteras -- mismo patron ya usado por cava_portfolio.py."""
    append_jsonl(SHADOW_PICKS, {
        "date": today_str,
        "run_id": f"ranking-score-{today_str}",
        "model": "ranking-score-shadow-v0",
        "ticker": c["ticker"],
        "portfolio": PORTFOLIO_NAME,
        "pcs": c.get("pcs"),
        "signal_type": "ranking_score_mechanical",
        "confidence": None,
        "reason_short": f"Ranking Score {c.get('candidate_ranking_score_shadow')} (mecanico, sin LLM)",
        "shadow": True,
        "active_model": False,
        "forced_run": False,
        "valid_for_performance_tracking": True,
        "extension_risk":   c.get("extension_risk"),
        "extension_points": c.get("extension_points"),
        "extension_flags":  c.get("extension_flags"),
        "konc_3d_state":    c.get("konc_3d_state"),
        "konc_w_state":     c.get("konc_w_state"),
        "konc_alignment":   c.get("konc_alignment"),
        "pcs_raw": c.get("pcs_raw"), "pcs_ex_macro": c.get("pcs_ex_macro"),
        "pcs_ceiling": c.get("pcs_ceiling"), "pcs_normalized": c.get("pcs_normalized"),
        "component_A": c.get("component_A"), "component_B": c.get("component_B"),
        "component_C": c.get("component_C"), "component_D": c.get("component_D"),
        "component_E": c.get("component_E"), "component_F": c.get("component_F"),
        "candidate_ranking_score_shadow": c.get("candidate_ranking_score_shadow"),
        "entry_quality_score": c.get("entry_quality_score"),
        "flow_institutional_score": c.get("flow_institutional_score"),
        "signal_change_score": c.get("signal_change_score"),
        "sectoral_context_score": c.get("sectoral_context_score"),
        "cooldown_score": c.get("cooldown_score"),
        "ranking_score_reason_flags": c.get("ranking_score_reason_flags"),
    })


def apply_entries(ptf: dict, to_add: list[dict], today_str: str) -> int:
    if not to_add:
        return 0
    closes = fetch_last_closes([c["ticker"] for c in to_add])
    for c in to_add:
        entry_price = closes.get(c["ticker"])
        pos = {
            "ticker": c["ticker"],
            "entry_date": today_str,
            "entry_price": entry_price,
            "size_pct": SIZE_PCT,
            "entry_ranking_score_shadow": c.get("candidate_ranking_score_shadow"),
            "entry_pcs": c.get("pcs"),
            "entry_ranking_score_components": c.get("ranking_score_components"),
            "entry_ranking_score_reason_flags": c.get("ranking_score_reason_flags"),
            "current_pcs": c.get("pcs"),
            "pcs_review_flag": False,
            "weeks_held": 0.0,
            "review_due": False,
        }
        ptf.setdefault("positions", []).append(pos)
        log_to_shadow_picks(c, today_str, entry_price)
        print(f"  [{PORTFOLIO_NAME}] SELECT {c['ticker']}: "
              f"ranking_score={c.get('candidate_ranking_score_shadow')} pcs={c.get('pcs')}")
    return len(to_add)


# -- 7 baselines shadow (seccion 2.5) -------------------------------------------

def baseline_universe(candidates: list[dict]) -> list[dict]:
    # "mismo universo (PCS >= 62)" -- literal, sin exigir ranking_score_eligible
    return [c for c in candidates if c.get("eligible") and (c.get("pcs") or 0) >= PCS_MIN_UNIVERSE]


def compute_baselines(candidates: list[dict], today_str: str) -> list[dict]:
    uni = baseline_universe(candidates)
    rows = []

    def top_by(key, label):
        ranked = sorted((c for c in uni if c.get(key) is not None), key=lambda c: c[key], reverse=True)
        rows.append({
            "date": today_str, "baseline_type": label, "n_universe": len(uni),
            "tickers": [c["ticker"] for c in ranked[:TOP_N]],
        })

    top_by("pcs", "top_pcs")
    top_by("pcs_ex_macro", "top_pcs_ex_macro")
    top_by("rot_score", "top_rot_score")
    top_by("ret_13w_vs_spy", "top_ret_13w_vs_spy")
    top_by("ret_4w_vs_spy", "top_ret_4w_vs_spy")
    top_by("entry_quality_score", "top_entry_quality_score")

    tickers_pool = [c["ticker"] for c in uni]
    for seed in RANDOM_SEEDS:
        rng = random.Random(seed)
        picked = rng.sample(tickers_pool, min(TOP_N, len(tickers_pool))) if tickers_pool else []
        rows.append({
            "date": today_str, "baseline_type": "random", "seed": seed,
            "n_universe": len(uni), "tickers": picked,
        })
    return rows


# -- Metricas semanales (seccion 2.4) -------------------------------------------

def compute_weekly_metrics(today_str: str, experimental_tickers: list[str]) -> dict:
    """Overlap rate vs las 4 clasicas, sobre los SELECT de hoy (mismo dia,
    todas las carteras) en shadow_picks.jsonl."""
    picks_today = [p for p in load_jsonl(SHADOW_PICKS) if p.get("date") == today_str]
    classic_tickers = {
        p["ticker"] for p in picks_today
        if p.get("portfolio") in CLASSIC_PORTFOLIOS and p.get("ticker")
    }
    exp_set = set(experimental_tickers)
    overlap = exp_set & classic_tickers
    only_experimental = exp_set - classic_tickers
    only_classic = classic_tickers - exp_set
    overlap_rate = (len(overlap) / len(exp_set)) if exp_set else None
    return {
        "date": today_str,
        "n_experimental": len(exp_set),
        "n_classic_today": len(classic_tickers),
        "overlap_rate": round(overlap_rate, 3) if overlap_rate is not None else None,
        "overlap_tickers": sorted(overlap),
        "only_experimental_tickers": sorted(only_experimental),
        "only_classic_tickers": sorted(only_classic),
    }


# -- main -----------------------------------------------------------------------

def run(apply: bool, force: bool) -> int:
    today_str = str(date.today())
    is_friday = datetime.now(timezone.utc).weekday() == 4
    do_selection = is_friday or force

    data = load_json(CANDIDATES_JSON)
    candidates = data.get("candidates", [])
    if not candidates:
        print("ai_candidates.json vacio -- corre pcs_calculator.py y "
              "ranking_score_calculator.py primero.")
        return 1
    candidates_by_ticker = {c["ticker"]: c for c in candidates}

    picks = load_json(PICKS_JSON)
    if not isinstance(picks, dict):
        picks = {}
    ptf = picks.setdefault("portfolios", {}).setdefault(PORTFOLIO_NAME, {"positions": [], "history": []})

    # Salidas mecanicas -- SIEMPRE, cualquier dia, antes de considerar entradas nuevas.
    closed = review_positions(ptf, candidates_by_ticker, today_str)
    if closed:
        print(f"  [{PORTFOLIO_NAME}] {len(closed)} posicion(es) cerrada(s) por hard failure.")

    n_added = 0
    to_add: list[dict] = []
    if do_selection:
        universe = build_universe(candidates, picks, ptf, today_str, require_ranking_eligible=True)
        print(f"[{PORTFOLIO_NAME}] Universo elegible hoy "
              f"(PCS>={PCS_MIN_UNIVERSE}, ranking_score_eligible, sin duplicar clasicas/cooldown): "
              f"{len(universe)} candidatos.")
        to_add = select_entries(universe, ptf)
        for c in to_add:
            print(f"  candidato: {c['ticker']:10s} ranking_score={c.get('candidate_ranking_score_shadow')} "
                  f"pcs={c.get('pcs')}")
    else:
        print(f"[{PORTFOLIO_NAME}] Hoy no es viernes (UTC) -- solo se revisan salidas. "
              f"Usa --force para forzar la seleccion semanal fuera de calendario.")

    if apply:
        if do_selection:
            n_added = apply_entries(ptf, to_add, today_str)
        write_json(PICKS_JSON, picks)
        print(f"  wrote {PICKS_JSON}")
    else:
        print("Dry-run (sin --apply): no se ha escrito ai_picks.json.")

    if do_selection:
        baselines = compute_baselines(candidates, today_str)
        weekly = compute_weekly_metrics(today_str, [c["ticker"] for c in to_add])
        if apply:
            for row in baselines:
                append_jsonl(BASELINES_LOG, row)
            append_jsonl(WEEKLY_METRICS, weekly)
            print(f"  wrote {len(baselines)} baseline rows -> {BASELINES_LOG}")
            print(f"  wrote weekly metrics -> {WEEKLY_METRICS} "
                  f"(overlap_rate={weekly['overlap_rate']})")
        else:
            print(f"  (dry-run) would write {len(baselines)} baseline rows + 1 weekly metrics row")

    print(f"\n[{PORTFOLIO_NAME}] {n_added} nueva(s) posicion(es), {len(closed)} cerrada(s), "
          f"{len(ptf.get('positions', []))} abiertas ahora.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true",
                     help="ignora el gate de viernes (seleccion + baselines fuera de calendario)")
    args = ap.parse_args()
    sys.exit(run(apply=args.apply, force=args.force))


if __name__ == "__main__":
    main()
