"""Registro de lo que se ha mirado del periodo de prueba (2022-01-03 → 2026-09-14, embargo desde 2021-10-29) y de la
ventana posterior (2026-09-15 → 2026-11-13), con su nivel de exposición (micro/exposure.py).

Fuentes: library/test_period_usage.jsonl (anotado por los scripts al usar fechas de prueba), library/access_log.jsonl
(laboratorio), planes congelados y las comprobaciones de G1. Salidas:
- research/microstructure_v1/test_exposure_registry.csv (en el repo: solo identificadores y fechas, sin datos de mercado)
- MICRO_DATA_DIR/results/g2_test_exposure.json (resumen y ventanas de exclusión con los parámetros provisionales)
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, storage  # noqa: E402
from micro.exposure import Exposure, exclusion_windows  # noqa: E402
from micro.library import EMBARGO_START, TEST_END, lib_dir  # noqa: E402

HERE = Path(__file__).resolve().parent
# Ventana de una observación con fecha de decisión t (PREREGISTRO_G2 / G2A_PROTOCOLO):
#   variables: [t - 259, t]  (C3 = 20 sesiones normalizadas con 120 previas, y C3 frente a sus 120 valores previos;
#              G2A_PROTOCOLO_ENMIENDAS, enmienda 1)
#   resultado: [t + 1, t + 40]  (entrada a la apertura de t + 1, horizonte máximo 40)
# Un día visto d la contamina si t está en [d - 40, d + 259] (exposure.exclusion_windows).
LOOKBACK, HORIZON = 260, 40


def after(day, n):
    """Sesión n posiciones después de day (el resultado a 5 sesiones de la criba llega hasta ahí)."""
    days = calendar.trading_days("2016-01-04", "2026-11-13")
    return days[min(len(days) - 1, days.index(day) + n)]


def build():
    ex = []
    # E1: comparación de clasificadores (G1.5), una fila por bloque
    u = pd.read_json(lib_dir() / "test_period_usage.jsonl", lines=True)
    for sym, g in u.groupby("symbol"):
        ex.append(Exposure("E1", sym, g["day"].min(), g["day"].max(),
                           f"comparación técnica de clasificadores, {len(g)} sesiones regulares: % sin clasificar, "
                           "concordancia entre métodos, TRF, odd lots, punto medio, antigüedad de la quote; "
                           "sin rentabilidades ni variables candidatas", "g15_classifier_comparison.py"))
    # laboratorio: accesos registrados
    acc = lib_dir() / "access_log.jsonl"
    if acc.exists():
        a = pd.read_json(acc, lines=True)
        for r in a[a.get("in_test_period", False) == True].itertuples():  # noqa: E712
            ex.append(Exposure("E2", r.symbol, r.day, r.day, "visto en el laboratorio", "lab/server.py"))
    # E0: comprobaciones de G1 con trades de fechas de prueba
    for sym, day, why in (("URI", "2025-11-28", "conciliación trades↔barras (cierre anticipado)"),
                          ("OSCR", "2026-03-09", "conciliación trades↔barras (cambio de hora)")):
        ex.append(Exposure("E0", sym, day, day, why, "g1_live_checks.py"))
    ex.append(Exposure("E0", "FI", "2024-01-16", "2024-02-12",
                       "descarga de trades y quotes del bloque test-024 corregido (plan v2); no entra en la "
                       "comparación de clasificadores", "g2_downloads.py"))
    # E0 de alcance amplio (sin filas por valor): descargas y cobertura
    for what, src in (("barras diarias de todo el universo 2016-2026: cobertura, identidad, liquidez previa para "
                       "muestrear, comprobación de los planes", "g1_universe_coverage.py, g1_plans.py, g2_plan_corrections.py"),
                      ("descarga del nivel A (barras de 1 min) y del piloto B1 (trades) con calificación de calidad",
                       "g2_downloads.py")):
        ex.append(Exposure("E0", "(universo)", EMBARGO_START, TEST_END, what, src))
    # posterior a la prueba (no confirmatorio): estudio de casos con resultado visto
    ex.append(Exposure("E3", "NVDA", "2026-11-12", "2026-11-13", "estudio de caso G1.5 con el recorrido posterior visto",
                       "g15_case_study.py"))
    ex.append(Exposure("E3", "GOOGL", "2026-10-29", "2026-11-05", "contraste G1.5 elegido por «sin recuperación» "
                       "(cierre a 5 sesiones)", "g15_contrast_select.py"))
    sel = json.loads((storage.root() / "results" / "g15_contrast_selection.json").read_text(encoding="utf-8"))
    for w in sel["windows"]:
        for c in w["gap_volume_candidates"]:
            ex.append(Exposure("E3", c["symbol"], c["date"], after(c["date"], 5),
                               "criba del contraste G1.5: hueco ≤ -7 % con volumen alto; se calculó su resultado "
                               "(recuperación en el día y a 5 sesiones)", "g15_contrast_select.py"))
    return ex


KNOWLEDGE = {"E0": "técnica: datos descargados o comprobados, sin estadísticos ni resultados",
             "E1": "técnica: estadísticos de clasificadores, sin rentabilidades",
             "E2": "visual: visto en el laboratorio",
             "E3": "resultado posterior visto (precio después del día)", "M": "dato de mercado visto"}

# La criba de G1.5 descargó las barras diarias de TODOS los miembros del S&P 500 de 2026-08-07 a 2026-11-13 y
# comprobó en cada valor-día de 2026-09-15 → 2026-11-05 si hubo hueco <= -7 % con volumen alto. Para los no
# candidatos solo se sabe «no hubo ese hueco»: conocimiento negativo y débil, que se trata como sensibilidad de
# mercado (excluir a todos los valores), no como exclusión principal.
SCREEN_SPAN = ("2026-09-15", "2026-11-12")


def audit(ex, days):
    """Una fila por exposición que excluye fechas de prueba, con la ventana exacta y su justificación."""
    pos = {d: i for i, d in enumerate(days)}
    t_end = pos[TEST_END]
    rows = []
    for e in ex:
        if e.level not in ("E2", "E3", "M") or e.symbol == "(universo)":
            continue
        a, b = pos[e.first], pos[e.last]
        lo, hi = max(0, a - HORIZON), b + LOOKBACK
        n_test = max(0, min(hi, t_end) - max(lo, pos[EMBARGO_START]) + 1) if lo <= t_end else 0
        rows.append({"level": e.level, "symbol": e.symbol, "seen_first": e.first, "seen_last": e.last,
                     "knowledge": KNOWLEDGE[e.level], "what": e.what, "source": e.source,
                     "exclude_from": days[lo], "exclude_to": days[min(hi, len(days) - 1)],
                     "test_sessions_excluded": n_test,
                     "test_excluded_from": days[max(lo, pos[EMBARGO_START])] if n_test else None,
                     "test_excluded_to": days[min(hi, t_end)] if n_test else None,
                     "justification": (f"d = {e.first}..{e.last}. Una observación de prueba con fecha t queda "
                                       f"contaminada si su resultado (t+1..t+{HORIZON}) incluye un día visto: "
                                       f"t >= d - {HORIZON} sesiones = {days[lo]}. Hacia delante (d + {LOOKBACK - 1}) "
                                       "queda fuera de la prueba." if n_test else
                                       "Ventana entera fuera de la prueba: no excluye nada.")})
    return pd.DataFrame(rows)


def main():
    ex = build()
    reg = pd.DataFrame([e.__dict__ for e in ex])
    reg["window"] = ["prueba" if EMBARGO_START <= r.first <= TEST_END else "posterior a la prueba"
                     if r.first > TEST_END else "desarrollo" for r in reg.itertuples()]
    reg = reg.sort_values(["level", "first", "symbol"])
    reg.to_csv(HERE / "test_exposure_registry.csv", index=False, encoding="utf-8")
    days = calendar.trading_days("2016-01-04", "2026-11-13")
    win = exclusion_windows([e for e in ex if e.symbol != "(universo)"], days, LOOKBACK, HORIZON)
    in_test = reg[reg["window"] == "prueba"]
    out = {"by_level_in_test_period": in_test.groupby("level").size().to_dict(),
           "e1_symbol_sessions": int(pd.read_json(lib_dir() / "test_period_usage.jsonl", lines=True).shape[0]),
           "exclusion_windows_provisional": {"lookback": LOOKBACK, "horizon": HORIZON, "windows": win,
                                             "in_test_period": [w for w in win if w["from"] <= TEST_END]},
           "registry_rows": len(reg),
           # valor-sesiones únicas: un valor con varias exposiciones (GOOGL, AMD, FICO...) cuenta cada día una vez
           "test_period_excluded_symbol_sessions": len({(w["symbol"], d) for w in win if w["from"] <= TEST_END
                                                         for d in days if max(w["from"], EMBARGO_START) <= d
                                                         <= min(w["to"], TEST_END)}),
           "test_period_excluded_symbol_sessions_summed_by_window": sum(
               sum(1 for d in days if w["from"] <= d <= min(w["to"], TEST_END)) for w in win if w["from"] <= TEST_END)}
    au = audit(ex, days)
    au.sort_values(["test_sessions_excluded", "symbol"], ascending=[False, True]).to_csv(
        HERE / "test_exclusion_audit.csv", index=False, encoding="utf-8")
    pos = {d: i for i, d in enumerate(days)}
    s0 = days[max(0, pos[SCREEN_SPAN[0]] - HORIZON)]
    members = pd.read_parquet(storage.root() / "reference" / "universe_intervals.parquet")
    members = members[members["source"] == "sp500"]
    sens_days = [d for d in days if s0 <= d <= TEST_END]
    sens_n = sum(int(((members["start"] <= d) & (members["end"] >= d)).sum()) for d in sens_days)
    out["audit"] = {"rows": int(len(au)), "rows_excluding_test": int((au["test_sessions_excluded"] > 0).sum()),
                    "test_symbol_sessions_unique": out["test_period_excluded_symbol_sessions"],
                    "test_symbol_sessions_summed_by_row": int(au["test_sessions_excluded"].sum()),
                    "by_level": au.groupby("level")["test_sessions_excluded"].sum().to_dict(),
                    "market_sensitivity_screen": {"seen": SCREEN_SPAN, "exclude_all_from": s0, "to": TEST_END,
                                                  "sessions": len(sens_days), "member_symbol_sessions": sens_n}}
    (storage.root() / "results" / "g2_test_exposure.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    t = out["exclusion_windows_provisional"]["in_test_period"]
    print({k: out[k] for k in ("by_level_in_test_period", "e1_symbol_sessions", "registry_rows",
                               "test_period_excluded_symbol_sessions")})
    print(len(t), sorted({w["symbol"] for w in t}), min(w["from"] for w in t) if t else None)
    print(out["audit"])


if __name__ == "__main__":
    main()
