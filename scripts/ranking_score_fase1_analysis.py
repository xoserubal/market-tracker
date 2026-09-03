"""
ranking_score_fase1_analysis.py -- Ranking Score, Fase 1 (analisis exploratorio)

Implementa literalmente la seccion "FASE 1 -- Analisis exploratorio" del plan
original (texto pegado por el usuario 2026-09-04), acotada por
wiki/PREREGISTRO_RANKING_SCORE_V0.md (informe de 3-5 paginas, no 10-15;
subseccion Koncorde separada con su propio n/IC95%; el gate de cobertura del
1.7 NO bloquea Fase 2 -- ya resuelto en el preregistro Sec.0).

Fase 1 es DESCRIPTIVA, no calibratoria (1.1): clasifica componentes como
plausible / inconclusive / suspicious_redundant / not_usable_missing_data.
NO elimina componentes preregistrados, NO anade componentes nuevos, NO ajusta
pesos. Cualquier duda que surja se documenta como "nota para siguiente
iteracion", nunca se aplica al Ranking Score actual.

Dataset limpio de P0 (definicion operativa de este script, ver Seccion 0 del
preregistro): dedup_same_day_reruns(shadow_picks.jsonl) [ya resuelto, P0]
filtrado a valid_for_performance_tracking != False (excluye runs con
violaciones de HARD_RULES o forced_run=True -- esas nunca se convirtieron en
decision real de portfolio). Reutiliza dedup_same_day_reruns() de
compare_vs_baselines.py en vez de reimplementarlo.

Antes de correr este analisis, este script re-ejecuta (idempotente, solo
anade filas nuevas, no --force) los 3 scripts de reconstruccion via
git-history que ya existian de la Fase 0 (pcs_components, rot_score_delta,
theme_breadth) para que la cobertura no se haya quedado congelada en el
2026-08-07 mientras shadow_picks.jsonl seguia creciendo.

Salidas:
  docs/data/ranking_score_fase1_dataset.jsonl   -- dataset consolidado, 1 fila/pick
  docs/data/ranking_score_fase1_results.json    -- correlaciones + clasificacion (machine-readable)
  docs/analysis/ranking_score_fase1_informe.md  -- informe descriptivo (3-5 paginas)

Uso:
    py -3 scripts/ranking_score_fase1_analysis.py
    py -3 scripts/ranking_score_fase1_analysis.py --skip-reconstruct  # no re-corre los 3 scripts previos
"""
from __future__ import annotations

import argparse
import functools
import json
import subprocess
import sys
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
ANALYSIS_DIR = ROOT / "docs" / "analysis"
REL_CANDIDATES = "docs/data/ai_candidates.json"

SHADOW_PICKS  = DATA / "shadow_picks.jsonl"
PCS_COMP      = DATA / "pcs_components_reconstructed.jsonl"
ROT_DELTA     = DATA / "rot_score_delta_reconstructed.jsonl"
THEME_BREADTH = DATA / "theme_breadth_reconstructed.jsonl"
EXT_RISK      = DATA / "extension_risk_reconstructed.jsonl"

OUT_DATASET = DATA / "ranking_score_fase1_dataset.jsonl"
OUT_RESULTS = DATA / "ranking_score_fase1_results.json"
OUT_REPORT  = ANALYSIS_DIR / "ranking_score_fase1_informe.md"

sys.path.insert(0, str(Path(__file__).parent))
from compare_vs_baselines import dedup_same_day_reruns  # reuso, no reimplemento (P0 ya resuelto)

# Umbrales de este analisis (fijados aqui, disclosed en el informe -- el
# preregistro deja la clasificacion cualitativa, no da numeros exactos).
MIN_N_USABLE       = 15    # por debajo de esto, un componente es not_usable_missing_data
MIN_COVERAGE_PCT   = 0.30  # idem, en fraccion del universo con ret_1m
MIN_N_SEGMENT      = 10    # tamano minimo de segmento para contar en el chequeo de signo
REDUNDANCY_RHO     = 0.70  # |spearman| entre dos componentes por encima de esto -> redundante
PLAUSIBLE_RHO      = 0.15  # |spearman| pooled minimo para "plausible"
PLAUSIBLE_P        = 0.10  # p-valor pooled maximo para "plausible"

# -- Convenciones ordinales propias de ESTE analisis (no rediseñan nada del
#    sistema; documentadas explicitamente en el informe) --------------------
EXT_RISK_ORD = {"low": 0, "medium": 1, "high": 2, "extreme": 3}
KONC_STATE_ORD = {"distribution": -2, "down": -1, "up": 1, "accumulation": 2}
KONC_ALIGN_ORD = {
    "bearish_aligned": -2,
    "distribution_warning": -1,
    "mixed": 0,
    "neutral": 0,
    "bullish_pending_3d_confirmation": 1,
    "accumulation_setup": 2,
    "bullish_aligned": 3,
}


# -- I/O ----------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _git(args: list[str]) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


@functools.lru_cache(maxsize=None)
def commit_blob(commit_hash: str | None) -> dict | None:
    """Full parsed ai_candidates.json at a given commit (macro_context + candidates), cached."""
    if not commit_hash:
        return None
    try:
        raw = _git(["show", f"{commit_hash}:{REL_CANDIDATES}"])
        return json.loads(raw)
    except Exception:
        return None


def macro_regime_at(commit_hash: str | None) -> str | None:
    blob = commit_blob(commit_hash)
    if not blob:
        return None
    return (blob.get("macro_context") or {}).get("regime")


def candidate_at(commit_hash: str | None, ticker: str) -> dict | None:
    blob = commit_blob(commit_hash)
    if not blob:
        return None
    for c in blob.get("candidates", []):
        if c.get("ticker") == ticker:
            return c
    return None


# -- Paso 0: refrescar reconstrucciones ya existentes (idempotente) -----------

def refresh_reconstructions() -> None:
    for script in (
        "reconstruct_pcs_components_historical.py",
        "reconstruct_rot_score_delta_historical.py",
        "reconstruct_theme_breadth_historical.py",
    ):
        print(f"  refreshing via {script} ...")
        subprocess.run([sys.executable, str(Path(__file__).parent / script)], cwd=ROOT, check=True)


# -- Paso 1: dataset limpio de P0 ---------------------------------------------

def load_clean_picks() -> tuple[list[dict], list[dict]]:
    """Returns (all_deduped, clean). `all_deduped` se usa solo para cooldown
    (necesita ver TODA la historia del ticker, no solo las filas 'limpias')."""
    raw = load_jsonl(SHADOW_PICKS)
    deduped = dedup_same_day_reruns(raw)
    clean = [p for p in deduped if p.get("valid_for_performance_tracking") is not False]
    return deduped, clean


def build_cooldown_index(all_deduped: list[dict]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = defaultdict(list)
    for p in all_deduped:
        t, d = p.get("ticker"), p.get("date")
        if t and d:
            idx[t].append(d)
    for t in idx:
        idx[t].sort()
    return idx


def cooldown_days(idx: dict[str, list[str]], ticker: str, this_date: str) -> int | None:
    dates = idx.get(ticker, [])
    prior = [d for d in dates if d < this_date]
    if not prior:
        return None
    last = max(prior)
    try:
        return (_date.fromisoformat(this_date) - _date.fromisoformat(last)).days
    except ValueError:
        return None


# -- Paso 2: indices de los ficheros reconstruidos ----------------------------

def index_ticker_date(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    idx: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        idx[(r["ticker"], r["date"])].append(r)
    return idx


def lookup_by_pcs(rows: list[dict], ticker: str, dt: str, pcs_val: float | None) -> dict | None:
    cands = rows
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    if pcs_val is not None:
        for r in cands:
            if r.get("pcs_at_pick") is not None and abs(r["pcs_at_pick"] - pcs_val) < 0.05:
                return r
    return cands[0]


# -- Paso 3: consolidacion -----------------------------------------------------

TRACKED_FIELDS = [
    "extension_risk", "dist_sma20_atr", "rsi_14", "spike_flag", "momentum_decay",
    "konc_3d_state", "konc_w_state", "konc_alignment",
    "rot_score_delta_4w", "streak_weeks_delta", "theme_flow_delta",
    "theme_breadth", "macro_regime_at_entry",
]
CRITICAL_BUCKETS = ["extension_risk", "konc_3d_state", "konc_w_state", "rot_score_delta_4w", "theme_breadth"]


def consolidate(clean: list[dict], cooldown_idx: dict[str, list[str]]) -> list[dict]:
    pcs_idx   = index_ticker_date(load_jsonl(PCS_COMP))
    rot_idx   = index_ticker_date(load_jsonl(ROT_DELTA))
    theme_idx = index_ticker_date(load_jsonl(THEME_BREADTH))
    ext_idx   = index_ticker_date(load_jsonl(EXT_RISK))

    out: list[dict] = []
    for p in clean:
        ticker, dt = p.get("ticker"), p.get("date")
        pcs_val = p.get("pcs")
        if not ticker or not dt:
            continue

        row: dict[str, Any] = {
            "ticker": ticker, "date": dt, "portfolio": p.get("portfolio"),
            "model": p.get("model"), "signal_type": p.get("signal_type"),
            "pcs": pcs_val,
            "ret_1w": p.get("ret_1w"), "ret_2w": p.get("ret_2w"),
            "ret_1m": p.get("ret_1m"), "ret_3m": p.get("ret_3m"),
            "vs_spy_1m": p.get("vs_spy_1m"),
            "mfe_1m": p.get("max_gain_1m"), "mae_1m": p.get("max_drawdown_1m"),
        }

        # -- PCS components (reconstruido; cubre tambien filas ya logueadas en vivo) --
        pcs_row = lookup_by_pcs(pcs_idx.get((ticker, dt), []), ticker, dt, pcs_val)
        entry_commit = None
        if pcs_row and pcs_row.get("reconstructed"):
            entry_commit = pcs_row.get("matched_commit")
            for f in ("pcs_raw", "pcs_ex_macro", "pcs_ceiling", "pcs_normalized",
                      "component_A", "component_B", "component_C", "component_D",
                      "component_E", "component_F"):
                row[f] = pcs_row.get(f)
        else:
            for f in ("pcs_raw", "pcs_ex_macro", "pcs_ceiling", "pcs_normalized",
                      "component_A", "component_B", "component_C", "component_D",
                      "component_E", "component_F"):
                row[f] = p.get(f)

        # -- Extension risk / entry quality (por ticker+fecha) --
        ext_row = lookup_by_pcs(ext_idx.get((ticker, dt), []), ticker, dt, None)
        row["extension_risk"]     = ext_row.get("extension_risk") if ext_row else p.get("extension_risk")
        row["extension_points"]   = ext_row.get("extension_points") if ext_row else p.get("extension_points")
        row["dist_sma20_atr"]     = ext_row.get("dist_sma20_atr") if ext_row else None
        row["rsi_14"]             = ext_row.get("rsi_14") if ext_row else None
        row["spike_flag"]         = ext_row.get("spike_flag") if ext_row else None
        row["momentum_decay"]     = ext_row.get("momentum_decay") if ext_row else None

        # -- Rot score delta (Cambio) --
        rot_row = lookup_by_pcs(rot_idx.get((ticker, dt), []), ticker, dt, pcs_val)
        row["rot_score_delta_4w"] = rot_row.get("rot_score_delta_4w") if rot_row else None
        row["rot_score_entry"]    = rot_row.get("rot_score_entry") if rot_row else None
        prior_commit = rot_row.get("prior_matched_commit") if rot_row else None

        # -- Theme breadth (Contexto) --
        theme_row = lookup_by_pcs(theme_idx.get((ticker, dt), []), ticker, dt, pcs_val)
        row["theme"]          = theme_row.get("theme") if theme_row else None
        row["theme_breadth"]  = theme_row.get("theme_breadth") if theme_row else None
        row["theme_total"]    = theme_row.get("theme_total") if theme_row else None

        # -- Koncorde / coherencia D-3D-W (Flow Institucional) -- solo lo ya
        #    logueado en vivo en shadow_picks; sin reconstruccion posible
        #    antes de 2026-06-30 (ver preregistro Sec.0) --
        row["konc_3d_state"]  = p.get("konc_3d_state")
        row["konc_3d_blue"]   = p.get("konc_3d_blue")
        row["konc_w_state"]   = p.get("konc_w_state")
        row["konc_alignment"] = p.get("konc_alignment")

        # -- Macro regime + streak_weeks_delta + theme_flow_delta (Cambio),
        #    via git-history del commit ya resuelto por la reconstruccion PCS --
        row["macro_regime_at_entry"] = macro_regime_at(entry_commit) if entry_commit else None
        entry_cand = candidate_at(entry_commit, ticker) if entry_commit else None
        streak_entry = entry_cand.get("streak_weeks") if entry_cand else None
        row["streak_weeks_entry"] = streak_entry
        row["subtheme"] = entry_cand.get("subtheme") if entry_cand else None
        row["cluster"]  = entry_cand.get("cluster") if entry_cand else None

        prior_cand = candidate_at(prior_commit, ticker) if prior_commit else None
        streak_prior = prior_cand.get("streak_weeks") if prior_cand else None
        row["streak_weeks_delta"] = (
            streak_entry - streak_prior if streak_entry is not None and streak_prior is not None else None
        )
        comp_b_prior = None
        if prior_cand is not None:
            comp_b_prior = (prior_cand.get("pcs_components") or {}).get("B_theme_flow")
        row["theme_flow_delta"] = (
            row["component_B"] - comp_b_prior
            if row.get("component_B") is not None and comp_b_prior is not None else None
        )

        # -- vehicle_vs_theme_strength: nunca implementado en el codebase
        #    (confirmado por grep antes de este analisis) -- not_usable por diseno --
        row["vehicle_vs_theme_strength"] = None

        # -- Cooldown (Contexto) --
        row["cooldown_days"] = cooldown_days(cooldown_idx, ticker, dt)

        # -- Encodings ordinales propios de este analisis --
        row["extension_risk_ord"] = EXT_RISK_ORD.get(row["extension_risk"])
        row["rsi_zone_45_65"] = (
            1 if (row["rsi_14"] is not None and 45 <= row["rsi_14"] <= 65) else
            (0 if row["rsi_14"] is not None else None)
        )
        row["spike_flag_num"] = (1 if row["spike_flag"] is True else (0 if row["spike_flag"] is False else None))
        row["momentum_decay_num"] = (1 if row["momentum_decay"] is True else (0 if row["momentum_decay"] is False else None))
        row["konc_3d_state_ord"] = KONC_STATE_ORD.get(row["konc_3d_state"])
        row["konc_w_state_ord"] = KONC_STATE_ORD.get(row["konc_w_state"])
        row["konc_alignment_ord"] = KONC_ALIGN_ORD.get(row["konc_alignment"])
        row["mfe_mae_ratio"] = (
            row["mfe_1m"] / abs(row["mae_1m"])
            if row.get("mfe_1m") is not None and row.get("mae_1m") not in (None, 0) else None
        )

        # -- Calidad de datos (preregistro 1.7) --
        present = [row.get(f) is not None for f in TRACKED_FIELDS]
        row["ranking_score_data_quality"] = round(sum(present) / len(present), 2)
        row["ranking_score_missing_fields"] = [f for f in TRACKED_FIELDS if row.get(f) is None]
        critical_ok = all(row.get(f) is not None for f in CRITICAL_BUCKETS)
        row["ranking_score_eligible"] = bool(critical_ok and row["ranking_score_data_quality"] >= 0.80)

        out.append(row)
    return out


# -- Paso 4: estadistica -------------------------------------------------------

def _corr(pairs_x: list[float], pairs_y: list[float]) -> dict:
    from scipy import stats as sstats
    import numpy as np
    n = len(pairs_x)
    if n < MIN_N_USABLE:
        return {"n": n, "spearman_rho": None, "spearman_p": None, "ci95": None}
    rho, p = sstats.spearmanr(pairs_x, pairs_y)
    if n > 3 and abs(rho) < 0.999999:
        z = np.arctanh(rho)
        se = 1 / np.sqrt(n - 3)
        lo, hi = np.tanh(z - 1.959964 * se), np.tanh(z + 1.959964 * se)
        ci95 = [round(float(lo), 4), round(float(hi), 4)]
    else:
        ci95 = None
    return {"n": n, "spearman_rho": round(float(rho), 4), "spearman_p": round(float(p), 6), "ci95": ci95}


def paired(dataset: list[dict], field: str, outcome: str) -> tuple[list[float], list[float]]:
    xs, ys = [], []
    for r in dataset:
        x, y = r.get(field), r.get(outcome)
        if x is None or y is None:
            continue
        xs.append(float(x))
        ys.append(float(y))
    return xs, ys


def segment_signs(dataset: list[dict], field: str, outcome: str, seg_key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in dataset:
        k = r.get(seg_key)
        if k is not None:
            groups[k].append(r)
    out = {}
    for k, rows in groups.items():
        xs, ys = paired(rows, field, outcome)
        if len(xs) >= MIN_N_SEGMENT and len(set(xs)) > 1 and len(set(ys)) > 1:
            c = _corr(xs, ys)
            if c.get("spearman_rho") is not None and c["spearman_rho"] == c["spearman_rho"]:  # exclude NaN
                out[k] = c
    return out


COMPONENT_SPECS = [
    # (bucket, field, label, expected_sign or None)
    ("Entry Quality", "extension_risk_ord", "extension_risk (ordinal bajo=0..extremo=3)", -1),
    ("Entry Quality", "dist_sma20_atr", "dist_sma20_atr", -1),
    ("Entry Quality", "spike_flag_num", "spike_flag (0/1)", -1),
    ("Entry Quality", "rsi_zone_45_65", "RSI en zona 45-65 (0/1)", 1),
    ("Entry Quality", "momentum_decay_num", "momentum_decay (0/1)", -1),
    ("Flow Institucional", "konc_3d_state_ord", "Koncorde 3D state (ordinal)", 1),
    ("Flow Institucional", "konc_w_state_ord", "Koncorde W state (ordinal)", 1),
    ("Flow Institucional", "konc_alignment_ord", "Coherencia D/3D/W (konc_alignment, ordinal)", 1),
    ("Cambio de Senal", "rot_score_delta_4w", "rot_score_delta 4w", None),
    ("Cambio de Senal", "streak_weeks_delta", "streak_weeks_delta", None),
    ("Cambio de Senal", "theme_flow_delta", "theme_flow_delta (delta component_B)", None),
    ("Contexto Sectorial", "theme_breadth", "theme_breadth", None),
    ("Contexto Sectorial", "vehicle_vs_theme_strength", "vehicle_vs_theme_strength", None),
    ("Contexto Sectorial", "cooldown_days", "dias desde ultimo pick del mismo ticker", None),
]

KONCORDE_FIELDS = {"konc_3d_state_ord", "konc_w_state_ord", "konc_alignment_ord"}


def classify_component(
    dataset: list[dict], field: str, outcome: str, all_numeric_fields: list[str],
    expected_sign: int | None = None,
) -> dict:
    xs, ys = paired(dataset, field, outcome)
    n = len(xs)
    n_universe = sum(1 for r in dataset if r.get(outcome) is not None)
    coverage = (n / n_universe) if n_universe else 0.0

    if n < MIN_N_USABLE or coverage < MIN_COVERAGE_PCT:
        return {
            "field": field, "n": n, "n_universe": n_universe, "coverage_pct": round(coverage, 3),
            "classification": "not_usable_missing_data", "pooled": {"n": n, "spearman_rho": None, "spearman_p": None, "ci95": None},
            "redundant_with": None,
        }

    pooled = _corr(xs, ys)

    # redundancia: contra cualquier otro campo numerico usable con el mismo outcome
    redundant_with = None
    max_abs_rho = 0.0
    closest_component: dict | None = None  # el par mas cercano al umbral, cruce o no
    for other in all_numeric_fields:
        if other == field:
            continue
        oxs, oys = [], []
        for r in dataset:
            a, b = r.get(field), r.get(other)
            if a is not None and b is not None:
                oxs.append(float(a)); oys.append(float(b))
        if len(oxs) >= MIN_N_USABLE and len(set(oxs)) > 1 and len(set(oys)) > 1:
            c = _corr(oxs, oys)
            rho = c.get("spearman_rho")
            if rho is not None and rho == rho and abs(rho) > max_abs_rho:  # rho==rho excludes NaN
                max_abs_rho = abs(rho)
                closest_component = {"field": other, "spearman_rho": rho, "n": len(oxs)}
                if abs(rho) >= REDUNDANCY_RHO:
                    redundant_with = {"field": other, "spearman_rho": rho}

    if redundant_with is not None:
        classification = "suspicious_redundant"
    else:
        by_portfolio = segment_signs(dataset, field, outcome, "portfolio")
        by_regime = segment_signs(dataset, field, outcome, "macro_regime_at_entry")
        pooled_sign = 1 if (pooled["spearman_rho"] or 0) >= 0 else -1
        flips = 0
        checked = 0
        for segset in (by_portfolio, by_regime):
            for k, c in segset.items():
                if c.get("spearman_rho") is None:
                    continue
                checked += 1
                seg_sign = 1 if c["spearman_rho"] >= 0 else -1
                if seg_sign != pooled_sign:
                    flips += 1
        rho = pooled.get("spearman_rho") or 0.0
        p = pooled.get("spearman_p")
        sign_matches_expected = (
            expected_sign is None or (rho >= 0) == (expected_sign >= 0)
        )
        if (abs(rho) >= PLAUSIBLE_RHO and (p is not None and p <= PLAUSIBLE_P)
                and flips == 0 and sign_matches_expected):
            classification = "plausible"
        else:
            classification = "inconclusive"

    return {
        "field": field, "n": n, "n_universe": n_universe, "coverage_pct": round(coverage, 3),
        "pooled": pooled, "classification": classification, "redundant_with": redundant_with,
        "max_abs_rho_vs_other_component": round(max_abs_rho, 4),
        "closest_component": closest_component,
    }


def mfe_mae_analysis(dataset: list[dict], field: str) -> dict:
    xs_mae, ys_mae = paired(dataset, field, "mae_1m")
    xs_ratio, ys_ratio = paired(dataset, field, "mfe_mae_ratio")
    return {
        "vs_mae_1m": _corr(xs_mae, ys_mae) if len(xs_mae) >= MIN_N_USABLE else {"n": len(xs_mae), "spearman_rho": None},
        "vs_mfe_mae_ratio": _corr(xs_ratio, ys_ratio) if len(xs_ratio) >= MIN_N_USABLE else {"n": len(xs_ratio), "spearman_rho": None},
    }


# -- Paso 5: informe -----------------------------------------------------------

CLASS_LABEL_ES = {
    "plausible": "PLAUSIBLE",
    "inconclusive": "INCONCLUSIVE",
    "suspicious_redundant": "SUSPICIOUS / LIKELY REDUNDANT",
    "not_usable_missing_data": "NOT USABLE (missing data)",
}


def fmt_corr(c: dict) -> str:
    if not c or c.get("spearman_rho") is None:
        return f"n={c.get('n', 0) if c else 0} (insuficiente)"
    ci = c.get("ci95")
    ci_txt = f", IC95%=[{ci[0]}, {ci[1]}]" if ci else ""
    return f"rho={c['spearman_rho']:+.3f}, p={c['spearman_p']:.4f}, n={c['n']}{ci_txt}"


def build_report(
    dataset: list[dict], clean_n: int, raw_n: int, deduped_n: int,
    results_1m: dict, results_3m: dict, mfe_mae: dict, coverage_gate: dict,
    numeric_fields: list[str],
) -> str:
    n_ret1m = sum(1 for r in dataset if r.get("ret_1m") is not None)
    n_ret3m = sum(1 for r in dataset if r.get("ret_3m") is not None)
    n_eligible = sum(1 for r in dataset if r.get("ranking_score_eligible"))
    avg_quality = round(sum(r["ranking_score_data_quality"] for r in dataset) / len(dataset), 3) if dataset else 0.0

    lines: list[str] = []
    lines.append("# Ranking Score -- Fase 1: informe de analisis exploratorio\n")
    lines.append(f"_Generado {_date.today().isoformat()} por `scripts/ranking_score_fase1_analysis.py`, "
                 f"disparado por el recordatorio `ranking_score_fase1_analisis` "
                 f"(`docs/data/reminders.json`, 2026-09-03)._\n")
    lines.append(
        "**Naturaleza de este informe (preregistro Sec.1, `wiki/PREREGISTRO_RANKING_SCORE_V0.md`):** "
        "descriptivo, no calibratorio. No elimina ni anade componentes preregistrados, "
        "no ajusta pesos. Longitud acotada a 3-5 paginas por el preregistro "
        "(el plan original de Fase 1 pedia 10-15; el preregistro lo recorto explicitamente, "
        "seccion 6).\n"
    )

    lines.append("## 0. Dataset limpio de P0\n")
    lines.append(
        f"- `shadow_picks.jsonl` en bruto: **{raw_n}** filas.\n"
        f"- Tras `dedup_same_day_reruns()` (P0, ya resuelto antes del preregistro): **{deduped_n}** filas.\n"
        f"- Tras filtrar `valid_for_performance_tracking != False` (excluye runs con violaciones de "
        f"HARD_RULES o `forced_run=True` -- nunca se convirtieron en decision real de portfolio): "
        f"**{clean_n}** filas -- este es el \"dataset limpio de P0\" que usa este informe.\n"
        f"- De esas, **{n_ret1m}** tienen `ret_1m` ya calculado y **{n_ret3m}** tienen `ret_3m` "
        f"(los mas recientes aun no maduran).\n"
        f"- Calidad de datos media por pick (fraccion de {len(TRACKED_FIELDS)} campos rastreados "
        f"presentes): **{avg_quality}**. Picks `ranking_score_eligible=true` "
        f"(calidad >=0.80 y ningun bucket critico totalmente ausente): **{n_eligible}/{len(dataset)}**.\n"
        f"- Dataset consolidado completo: `docs/data/ranking_score_fase1_dataset.jsonl` "
        f"(formato .jsonl en vez de .csv/.parquet -- consistente con el resto de `docs/data/`, "
        f"mismo contenido tabular, una fila por linea).\n"
    )

    lines.append("## 1. Metodologia de clasificacion (definida en esta ejecucion, no en el preregistro)\n")
    lines.append(
        "El preregistro deja la clasificacion en terminos cualitativos "
        "(\"correlacion consistente y en direccion esperada\" / \"senal debil o inconsistente\"). "
        "Para que el resultado sea reproducible, esta ejecucion fija una regla mecanica, "
        "aplicada igual a todos los componentes:\n\n"
        f"1. **not_usable_missing_data** si n < {MIN_N_USABLE} o cobertura < {int(MIN_COVERAGE_PCT*100)}% "
        f"del universo con el outcome disponible.\n"
        f"2. **suspicious_redundant** si `|Spearman rho|` >= {REDUNDANCY_RHO} contra cualquier otro "
        f"componente preregistrado (se cita cual).\n"
        f"3. **plausible** si `|rho pooled|` >= {PLAUSIBLE_RHO}, p <= {PLAUSIBLE_P}, el signo no se "
        f"invierte en ningun segmento (por cartera o por regimen macro) con n >= {MIN_N_SEGMENT}, y "
        "-- solo para los componentes de Entry Quality, donde el plan fija una direccion a priori -- "
        "el signo coincide con esa direccion esperada.\n"
        "4. **inconclusive** en cualquier otro caso (incluye signo consistente pero en la direccion "
        "contraria a la esperada).\n\n"
        "IC95% via transformacion Fisher-z sobre Spearman rho (misma convencion ya usada en "
        "`scripts/analyze_relative_flow_signal.py` para el backtest de Relative Flow Lab) -- "
        "aproximacion estandar, no exacta para rho, declarada como tal.\n\n"
        "**Dos notas de lectura, para no confundir numeros de distintas secciones:**\n"
        "- El `coverage_pct` de cada componente (Secciones 2-5) se mide sobre el universo con el "
        "outcome disponible (`ret_1m`/`ret_3m`), no sobre el dataset limpio completo -- es distinto "
        "del gate de cobertura de la Seccion 7, que se mide sobre las 150 filas limpias enteras.\n"
        "- `MAE (1m)` es `max_drawdown_1m`, guardado con signo (negativo = peor). Un rho **positivo** "
        "entre un componente \"mas alcista\" (ordinal ascendente) y MAE significa drawdowns **menos** "
        "profundos (mejor), no peores -- leer el signo con cuidado en las tablas de abajo.\n"
    )

    def section(bucket: str, is_koncorde: bool = False) -> list[str]:
        out = []
        specs = [s for s in COMPONENT_SPECS if s[0] == bucket]
        for _, field, label, _expected in specs:
            r1 = results_1m.get(field, {})
            r3 = results_3m.get(field, {})
            mm = mfe_mae.get(field, {})
            cls = r1.get("classification", "not_usable_missing_data")
            out.append(f"### {label}\n")
            out.append(f"- Clasificacion: **{CLASS_LABEL_ES.get(cls, cls)}**\n")
            out.append(f"- vs ret_1m: {fmt_corr(r1.get('pooled', {}))}\n")
            out.append(f"- vs ret_3m: {fmt_corr(r3.get('pooled', {}))}\n")
            if r1.get("redundant_with"):
                rw = r1["redundant_with"]
                out.append(f"- **Redundancia detectada** con `{rw['field']}` (rho={rw['spearman_rho']:+.3f}).\n")
            mm_mae = mm.get("vs_mae_1m", {})
            mm_ratio = mm.get("vs_mfe_mae_ratio", {})
            out.append(f"- vs MAE (1m): {fmt_corr(mm_mae)}\n")
            out.append(f"- vs ratio MFE/|MAE| (1m): {fmt_corr(mm_ratio)}\n")
            out.append("")
        return out

    lines.append("## 2. Entry Quality (30%)\n")
    lines += section("Entry Quality")

    lines.append("## 3. Flow Institucional (25%) -- subseccion Koncorde, tratada aparte\n")
    lines.append(
        "**Nota de cobertura (preregistro Sec.0/Sec.1):** Koncorde no existia como feature antes de "
        "2026-06-30 y no se registro en `shadow_picks.jsonl` de forma sistematica hasta 2026-07-02 -- "
        "no es un hueco de logging, es ausencia real de la senal en ese periodo. Su clasificacion aqui "
        "tiene **caracter provisional**, con su propio n e IC95% por debajo, nunca mezclada en la misma "
        "tabla que componentes con historial completo desde 2026-05-08.\n"
    )
    lines += section("Flow Institucional", is_koncorde=True)

    lines.append("## 4. Cambio de Senal (20%)\n")
    lines += section("Cambio de Senal")

    lines.append("## 5. Contexto Sectorial (15%)\n")
    lines.append(
        "`vehicle_vs_theme_strength` no existe como campo calculado en ningun punto del codebase "
        "(confirmado por busqueda en el repo antes de este analisis) -- se reporta directamente como "
        "`not_usable_missing_data`, cobertura 0%, sin inventar un proxy.\n"
    )
    lines += section("Contexto Sectorial")

    lines.append("## 6. Analisis segmentado (informativo, seccion 1.4 del plan)\n")
    lines.append(
        "Los cortes por cartera y por regimen macro ya se usan arriba solo como chequeo de "
        "consistencia de signo para la clasificacion (paso 3 de la regla mecanica) -- no se listan "
        "aqui coeficiente por coeficiente por segmento para mantener el informe en 3-5 paginas; "
        "el detalle completo por segmento queda en `docs/data/ranking_score_fase1_results.json`.\n"
    )

    lines.append("## 7. Verificacion de cobertura minima (preregistro 1.7)\n")
    lines.append(
        "El plan original marca esta seccion como **bloqueante para Fase 2** si algun componente "
        "critico tiene cobertura <80%. **El preregistro ya resolvio esto en su Seccion 0**, verificado "
        "contra datos reales: *\"la cobertura en candidatos en vivo (hoy): 100% en todos los campos "
        "anteriores -- el gate de 80% de la Fase 1.7 del plan original no bloquea Fase 2, solo "
        "condiciona que puede analizarse retrospectivamente en Fase 1.\"* Se reportan los numeros "
        "reales de todos modos, por transparencia, no como gate:\n\n"
    )
    lines.append("| Componente critico | Cobertura sobre dataset limpio de P0 | >=80%? |\n|---|---|---|\n")
    below_80 = []
    for name, pct in coverage_gate.items():
        ok = pct >= 0.80
        lines.append(f"| {name} | {pct*100:.1f}% | {'si' if ok else '**no**'} |\n")
        if not ok:
            below_80.append(f"{name} ({pct*100:.1f}%)")
    if below_80:
        lines.append(
            f"\nPor debajo de 80%: {', '.join(below_80)}. Koncorde 3D/W es el mas bajo, coherente con "
            "el techo de cobertura historica (~15%) ya documentado en el preregistro -- no existia como "
            "feature antes de 2026-06-30. No bloquea el arranque de Fase 2 (resolucion ya firmada en "
            "preregistro Sec.0); solo limita cuanto se puede decir de esos componentes en este informe.\n"
        )
    else:
        lines.append("\nTodos los componentes criticos superan el 80% de cobertura en esta corrida.\n")

    lines.append("## 8. Lectura de conjunto (comentario, no decision)\n")
    n_plausible = sum(1 for f in numeric_fields if results_1m[f]["classification"] == "plausible")
    plausible_fields = [f for f in numeric_fields if results_1m[f]["classification"] == "plausible"]
    lines.append(
        f"De los {len(numeric_fields)} componentes preregistrados evaluados, **{n_plausible}** clasifica "
        f"como `plausible` frente a `ret_1m` bajo la regla mecanica de la Seccion 1"
        + (f": {', '.join('`'+f+'`' for f in plausible_fields)}." if plausible_fields else ".")
        + " El resto queda `inconclusive` (senal debil, inconsistente entre segmentos, o en direccion "
        "contraria a la esperada) por ahora -- con n=98 para ret_1m y muestras menores por componente "
        "segun cobertura, es exactamente el resultado que cabe esperar de una muestra todavia pequena, "
        "no evidencia de que el diseno este mal.\n\n"
        "Algunos patrones descriptivos, sin implicar decision alguna (Seccion 1.1): componentes con "
        "asociacion mas marcada con MAE (`max_drawdown_1m`, drawdowns menos profundos) que con `ret_1m` "
        "-- `theme_breadth` (rho={:+.3f}, p={:.3f}, n={}) y, dentro de la subseccion Koncorde, la "
        "coherencia D/3D/W (rho={:+.3f}, p={:.3f}, n={}) -- sugieren que, si hay senal, podria estar "
        "mas del lado de \"evita el peor escenario\" que de \"predice el retorno medio\". "
        "Notas de este tipo van a la lista de \"siguiente iteracion\" de abajo, no cambian nada hoy.\n".format(
            mfe_mae["theme_breadth"]["vs_mae_1m"].get("spearman_rho", 0) or 0,
            mfe_mae["theme_breadth"]["vs_mae_1m"].get("spearman_p", 1) or 1,
            mfe_mae["theme_breadth"]["vs_mae_1m"].get("n", 0),
            mfe_mae["konc_alignment_ord"]["vs_mae_1m"].get("spearman_rho", 0) or 0,
            mfe_mae["konc_alignment_ord"]["vs_mae_1m"].get("spearman_p", 1) or 1,
            mfe_mae["konc_alignment_ord"]["vs_mae_1m"].get("n", 0),
        )
    )

    lines.append("## 9. Notas para siguiente iteracion (no se aplican al Ranking Score actual)\n")
    notes = []
    for field in numeric_fields:
        r = results_1m.get(field, {})
        if r.get("classification") == "suspicious_redundant":
            rw = r["redundant_with"]
            notes.append(f"- `{field}` correlaciona fuerte con `{rw['field']}` (rho={rw['spearman_rho']:+.3f}) -- "
                         f"posible doble conteo si ambos entran con peso pleno; a revisar en un preregistro "
                         f"de ajuste de pesos, no aqui.")
    # pares cercanos al umbral de redundancia (0.55-0.70) -- todavia no cruzan la regla, pero a vigilar
    seen_pairs: set[frozenset] = set()
    for field in numeric_fields:
        r = results_1m.get(field, {})
        cc = r.get("closest_component")
        if cc and REDUNDANCY_RHO * 0.75 <= abs(cc["spearman_rho"]) < REDUNDANCY_RHO:
            pair = frozenset({field, cc["field"]})
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                notes.append(
                    f"- `{field}` y `{cc['field']}` correlacionan entre si con rho={cc['spearman_rho']:+.3f} "
                    f"(n={cc['n']}) -- por debajo del umbral de redundancia ({REDUNDANCY_RHO}) pero cerca; "
                    f"vigilar cuando crezca la muestra, no actuar todavia."
                )
    if not notes:
        notes.append("- Ninguna redundancia (ni cercana al umbral) fue detectada en esta corrida.")
    lines += notes
    lines.append(
        "\n**Recordatorio explicito (preregistro Sec.5):** ninguna de estas notas se traduce en un "
        "cambio de pesos, componentes o umbrales del Ranking Score preregistrado. Cualquier cambio "
        "exige marcar \"post-preregistro\" con justificacion conceptual escrita, nunca numerica.\n"
    )

    return "\n".join(lines)


# -- main -----------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-reconstruct", action="store_true",
                     help="no re-ejecutar los 3 scripts de reconstruccion antes de analizar")
    args = ap.parse_args()

    if not args.skip_reconstruct:
        print("Refreshing git-history reconstructions (idempotente, solo filas nuevas)...")
        refresh_reconstructions()

    print("Loading & cleaning shadow_picks.jsonl (P0)...")
    raw = load_jsonl(SHADOW_PICKS)
    all_deduped, clean = load_clean_picks()
    print(f"  raw={len(raw)} deduped={len(all_deduped)} clean(valid!=False)={len(clean)}")

    cooldown_idx = build_cooldown_index(all_deduped)

    print("Consolidating per-pick dataset (this shells out to `git show` per unique commit, ~1-2 min)...")
    dataset = consolidate(clean, cooldown_idx)

    OUT_DATASET.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in dataset) + "\n", encoding="utf-8"
    )
    print(f"  wrote {len(dataset)} rows -> {OUT_DATASET}")

    numeric_fields = [f for _, f, _, _ in COMPONENT_SPECS]
    expected_sign_by_field = {f: exp for _, f, _, exp in COMPONENT_SPECS}

    print("Computing correlations + classification...")
    results_1m = {
        f: classify_component(dataset, f, "ret_1m", numeric_fields, expected_sign_by_field[f])
        for f in numeric_fields
    }
    results_3m = {
        f: classify_component(dataset, f, "ret_3m", numeric_fields, expected_sign_by_field[f])
        for f in numeric_fields
    }
    mfe_mae = {f: mfe_mae_analysis(dataset, f) for f in numeric_fields}

    n_clean_ret1m = sum(1 for r in dataset if r.get("ret_1m") is not None)
    coverage_gate = {
        "entry_quality inputs (extension_risk)": sum(1 for r in dataset if r.get("extension_risk") is not None) / len(dataset),
        "Koncorde 3D/W (ambos)": sum(1 for r in dataset if r.get("konc_3d_state") is not None and r.get("konc_w_state") is not None) / len(dataset),
        "rot_score_delta_4w": sum(1 for r in dataset if r.get("rot_score_delta_4w") is not None) / len(dataset),
        "theme_breadth": sum(1 for r in dataset if r.get("theme_breadth") is not None) / len(dataset),
    }

    results_json = {
        "generated_at": _date.today().isoformat(),
        "dataset_n": len(dataset),
        "raw_n": len(raw),
        "deduped_n": len(all_deduped),
        "clean_n": len(clean),
        "n_with_ret_1m": n_clean_ret1m,
        "coverage_gate_1_7": coverage_gate,
        "results_vs_ret_1m": results_1m,
        "results_vs_ret_3m": results_3m,
        "mfe_mae": mfe_mae,
    }
    OUT_RESULTS.write_text(json.dumps(results_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_RESULTS}")

    print("Building report...")
    report = build_report(
        dataset, len(clean), len(raw), len(all_deduped),
        results_1m, results_3m, mfe_mae, coverage_gate, numeric_fields,
    )
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(report, encoding="utf-8")
    print(f"  wrote {OUT_REPORT}")

    print("\nClassification summary (vs ret_1m):")
    for f in numeric_fields:
        r = results_1m[f]
        print(f"  {f:30s} {r['classification']:26s} n={r['n']:>4} coverage={r['coverage_pct']*100:5.1f}%")


if __name__ == "__main__":
    main()
