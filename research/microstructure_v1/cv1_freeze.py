"""cat-v1 — congela los parámetros de las dos versiones del catálogo (aprobación del usuario, 2026-11-21).

Lee las cifras fijadas en E2 (results/e2_report.json, calibración 2016-2019) y en las comprobaciones de E2B
(results/e2b_criteria.json) y escribe, en el repo (sin datos de mercado: solo umbrales agregados):

- catalog/cat_v1_params.json + catalog/cat_v1_params.sha256
- catalog/cat_v0_params.json + catalog/cat_v0_params.sha256 (la versión anterior, tal como la aplica E1 y M0 de E2)

No cambia ninguna cifra: copia las ya fijadas. Si el fichero ya existe y su contenido coincide, no lo reescribe; si
difiere, se niega (una versión congelada no se edita: se crea otra).

Uso: py -3 cv1_freeze.py [--check]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import event_catalog as cat0, storage  # noqa: E402
import e2_normalize as N  # noqa: E402
import e2_analyze as A  # noqa: E402
import e2b_criteria as B  # noqa: E402

HERE = Path(__file__).resolve().parent / "catalog"
RES = storage.root() / "results"

# Paradas generales del mercado documentadas (cortacircuitos de nivel 1 del S&P 500, marzo de 2020).
DOCUMENTED_MARKET_HALTS = {"2020-03-09": "cortacircuito nivel 1 (09:34-09:49 ET)",
                           "2020-03-12": "cortacircuito nivel 1 (09:35-09:50 ET)",
                           "2020-03-16": "cortacircuito nivel 1 (09:30-09:45 ET)",
                           "2020-03-18": "cortacircuito nivel 1 (12:56-13:11 ET)"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_v1() -> dict:
    rep = json.loads((RES / "e2_report.json").read_text(encoding="utf-8"))
    crit = json.loads((RES / "e2b_criteria.json").read_text(encoding="utf-8"))
    th1 = rep["calibration"]["M1"]["thresholds"]
    names = sorted(th1)
    special = {m: {"abs_threshold_raw": crit["measures"][m]["abs_threshold_raw"],
                   "own_rule": "max" if m in B.DISCRETE else "p99",
                   "evaluable": {"V3_close_est": "requires_trades", "D3_gap": "min_liq"}.get(m, "eligible")}
               for m in B.SPECIAL}
    return {
        "catalog_version": "cat-v1", "detector_version": "ev-det-1.0", "approved_utc": "2026-11-21",
        "approval": "usuario, revisión de E2B_INFORME.md (2026-11-21): catálogo observacional, aplicación manual",
        "calibration_period": [A.E2_FIRST if hasattr(A, "E2_FIRST") else "2016-01-04", A.CALIB_END],
        "threshold_knowledge_note": "umbrales fijados en 2026 con datos de 2016-2019: en esos años no eran conocidos; "
                                    "2020-01-02 a 2026-11-21 = retrospectivo fuera de la calibración; después = prospectivo",
        "baseline": {"target_sessions": N.WIN, "max_age_days": N.MAX_AGE, "min_n": A.MIN_N, "min_cov": 0.2,
                     "m2_halflife": N.HALFLIFE, "m2_min_periods": 20},
        "transforms": {"log": list(N.LOG_MEASURES), "log1p": list(N.LOG1P_MEASURES)},
        "families": {m: A.family_of(m) for m in names},
        "m1_thresholds": {m: float(th1[m]) for m in names},
        "m1_mad_floors": {m: float(rep["mad_floors"][m]) for m in names},
        "m2_thresholds_context": {m: float(v) for m, v in rep["calibration"]["M2"]["thresholds"].items()},
        "special": special,
        "special_rules": {"abs_pct_calibration": B.ABS_PCT, "v3_min_nonzero_base": B.V3_MIN_NONZERO_BASE,
                          "d3_min_liq": B.D3_MIN_LIQ},
        "no_alert_measures": {"V3_close_est": "requires_trades: en NYSE la barra de las 16:00 no recoge la subasta "
                                              "de cierre (E2B §1); la medida se guarda"},
        "episodes": {"gap_minutes": 10, "grouping": "por tramo", "summary_measures_as_points": True},
        "simultaneity": {"market_wide_share": A.MARKET_WIDE, "suspected_outage_share": A.MARKET_WIDE},
        "structural": {"post_split_sessions_V2": A.SPLIT_WINDOW_SESSIONS},
        "documented_market_halts": DOCUMENTED_MARKET_HALTS,
        "data_delay_minutes_free_plan": 15,
        "display_groups": {"volumen": ["V1_1", "V1_5", "V1_15", "I2_stall"],
                           "desplazamiento": ["D1_15_up", "D1_15_dn", "D1_30_up", "D1_30_dn", "I3_vwap15_up",
                                              "I3_vwap15_dn"]},
        "sources": {"e2_report.json": sha((RES / "e2_report.json").read_bytes()),
                    "e2b_criteria.json": sha((RES / "e2b_criteria.json").read_bytes())},
    }


def build_v0() -> dict:
    return {"catalog_version": cat0.CATALOG_VERSION, "detector_version": cat0.DETECTOR_VERSION,
            "thresholds": cat0.THRESHOLDS,
            "rule": "percentil >= 99 de la línea base (con 60 sesiones: superar su máximo) o z robusto >= 4 con MAD > 0",
            "episodes": {"gap_minutes": cat0.THRESHOLDS["episode_gap_minutes"], "grouping": "por día"},
            "note": "versión de E1, conservada sin cambios; M0 de E2 la reproduce exactamente"}


def write(name: str, obj: dict, check: bool):
    HERE.mkdir(exist_ok=True)
    p = HERE / f"{name}.json"
    body = json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if p.exists():
        old = p.read_bytes()
        if old != body:
            raise SystemExit(f"{p.name} ya existe y difiere: una versión congelada no se reescribe")
        print(f"{p.name}: sin cambios, sha256 {sha(old)}")
        return
    if check:
        raise SystemExit(f"{p.name} no existe")
    p.write_bytes(body)
    (HERE / f"{name}.sha256").write_text(f"{sha(body)}  {p.name}\n", encoding="utf-8")
    print(f"{p.name}: escrito, sha256 {sha(body)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    write("cat_v0_params", build_v0(), a.check)
    write("cat_v1_params", build_v1(), a.check)


if __name__ == "__main__":
    main()
