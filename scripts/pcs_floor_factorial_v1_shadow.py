"""
P2 — `PCS_FLOOR_FACTORIAL_V1` (Hoja de ruta consolidada v1.2, §6, wiki/).

Factorial 2x2 (histeresis x confirmacion) + breach severity sobre el suelo
de PCS ("regla 13" real). Shadow puro: nunca escribe en ai_picks.json, nunca
cierra nada real — igual que koncorde_shadow_exits.py / cfl_followthrough_shadow.py.

Corre DESPUES de Step 10i (P0, ai_picks_decision_state.py) porque reutiliza
sus filas del dia (trigger_threshold/event_id/mechanical_exit_trigger ya
calculados ahi) en vez de recalcularlos por separado -- mismo principio de
no duplicar logica que motivo ai_shared.py.

Preregistro completo: wiki/PREREGISTRO_PCS_FLOOR_FACTORIAL_V1.md

Cuatro brazos (todo evaluado sobre T_active = trigger_threshold de P0):
  A (control)    -> mechanical_exit_trigger de P0, tal cual (regla 13 real).
  B (histeresis)  -> EXIT si PCS < T_active - 1.5, una sola lectura basta.
  C (confirmacion)-> EXIT si PCS < T_active en la lectura de hoy Y en la
                     lectura anterior disponible de esa misma posicion.
  D (ambos)       -> EXIT si PCS < T_active - 1.5 en las dos lecturas.

Breach severity (bypassa histeresis/confirmacion en B/C/D, no en A porque la
regla 13 real de A ya incluye rot_score<=2 y el suelo absoluto por su cuenta):
  SEVERE:   PCS < T_active - 3.0  O  rot_score <= 2  -> EXIT inmediato en B/C/D.
  MARGINAL: T_active - 3.0 <= PCS < T_active         -> aplica la regla propia de cada brazo.

Ambito (decision de implementacion, ver preregistro §5): mismo que P1A/P1C
(§3 de la hoja de ruta) -- importado de p1_readiness_monitor.py para que no
puedan desincronizarse. CAVA_MACRO no es PCS-gated en el esquema de P0
(compute_t_active devuelve None ahi) pero SI tiene suelo real (pcs<62) --
aqui se le asigna T_active=ABSOLUTE_FLOOR de forma trivial, sin tocar P0.

"2 lecturas consecutivas" = 2 filas diarias consecutivas en
ai_picks_decision_state.jsonl para la misma posicion (P0 ya dedupea a 1
fila/dia) -- no 2 corridas del pipeline el mismo dia. Decision de
implementacion documentada en el preregistro §5, no en la hoja de ruta
original (que no precisa la granularidad).

Uso:
    py -3 scripts/pcs_floor_factorial_v1_shadow.py              # captura real
    py -3 scripts/pcs_floor_factorial_v1_shadow.py --dry-run    # no escribe
    py -3 scripts/pcs_floor_factorial_v1_shadow.py --report     # resume el jsonl existente
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

DECISION_STATE = DATA / "ai_picks_decision_state.jsonl"
OUT_PATH = DATA / "pcs_floor_factorial_v1_shadow.jsonl"

sys.path.insert(0, str(Path(__file__).parent))
from ai_picks_decision_state import ABSOLUTE_FLOOR  # mismo suelo absoluto, sin duplicar
from p1_readiness_monitor import P1A_P1C_SCOPE as P2_SCOPE  # mismo ambito que P1A/P1C (§3)

HYSTERESIS_BUFFER = 1.5
SEVERE_BUFFER = 3.0


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def t_active_for_row(row: dict) -> float | None:
    """T_active ya viene calculado por P0 (trigger_threshold) para las
    carteras PCS-gated. Para CAVA_MACRO (no PCS-gated en el esquema de P0,
    pero con suelo real pcs<62) se asigna el suelo absoluto trivialmente."""
    if row.get("trigger_threshold") is not None:
        return row["trigger_threshold"]
    if row["portfolio"] == "CAVA_MACRO":
        return ABSOLUTE_FLOOR
    return None


def classify_severity(pcs: float | None, rot_score: float | None, t_active: float | None) -> str | None:
    if pcs is None or t_active is None:
        return None
    if pcs < t_active - SEVERE_BUFFER or (rot_score is not None and rot_score <= 2):
        return "severe"
    if pcs < t_active:
        return "marginal"
    return "none"


def evaluate_position_history(rows: list[dict]) -> list[dict]:
    """rows = filas de P0 de UNA posicion, ordenadas por fecha ascendente.
    Devuelve una fila de evaluacion por dia, con el estado de los 4 brazos."""
    out = []
    prev_pcs = None
    prev_breach = None       # PCS < T_active en la lectura anterior
    prev_breach_1_5 = None   # PCS < T_active - 1.5 en la lectura anterior
    for row in rows:
        pcs = row.get("PCS")
        rot_score = row.get("rot_score")
        t_active = t_active_for_row(row)
        severity = classify_severity(pcs, rot_score, t_active)

        breach = (pcs is not None and t_active is not None and pcs < t_active)
        breach_1_5 = (pcs is not None and t_active is not None and pcs < t_active - HYSTERESIS_BUFFER)

        brazo_a = row.get("mechanical_exit_trigger")  # control = regla 13 real, ya calculada por P0

        if t_active is None or pcs is None:
            brazo_b = brazo_c = brazo_d = None
        else:
            brazo_b = (severity == "severe") or breach_1_5
            brazo_c = (severity == "severe") or (breach and bool(prev_breach))
            brazo_d = (severity == "severe") or (breach_1_5 and bool(prev_breach_1_5))

        out.append({
            "position_id": row["position_id"], "ticker": row["ticker"], "portfolio": row["portfolio"],
            "date": row["date"], "event_id": row.get("event_id"),
            "PCS": pcs, "rot_score": rot_score, "streak_weeks": row.get("streak_weeks"),
            "trigger_threshold": t_active, "severity": severity,
            "brazo_A_control_exit": brazo_a, "brazo_A_exit_rule_id": row.get("exit_rule_id"),
            "brazo_B_hysteresis_exit": brazo_b,
            "brazo_C_confirmation_exit": brazo_c,
            "brazo_D_both_exit": brazo_d,
            "current_price": row.get("current_price"), "MFE": row.get("MFE"), "MAE": row.get("MAE"),
        })
        prev_pcs = pcs
        prev_breach = breach
        prev_breach_1_5 = breach_1_5
    return out


def run(dry_run: bool) -> int:
    all_rows = _load_jsonl(DECISION_STATE)
    if not all_rows:
        print("Sin datos en ai_picks_decision_state.jsonl todavia -- P0 debe correr primero.")
        return 1

    scoped = [r for r in all_rows if r["portfolio"] in P2_SCOPE]
    by_position: dict[str, list[dict]] = {}
    for r in scoped:
        by_position.setdefault(r["position_id"], []).append(r)
    for pos_id in by_position:
        by_position[pos_id].sort(key=lambda r: r["date"])

    existing = _load_jsonl(OUT_PATH)
    already_logged = {(r["position_id"], r["date"]) for r in existing}

    new_rows = []
    for pos_id, pos_rows in by_position.items():
        evaluated = evaluate_position_history(pos_rows)
        for ev in evaluated:
            key = (ev["position_id"], ev["date"])
            if key not in already_logged:
                new_rows.append(ev)

    print(f"Posiciones en ambito P2 ({', '.join(P2_SCOPE)}): {len(by_position)}")
    print(f"Filas nuevas a escribir: {len(new_rows)}")
    for r in new_rows[:10]:
        print(f"  {r['portfolio']:24s} {r['ticker']:10s} PCS={r['PCS']} T_active={r['trigger_threshold']} "
              f"severity={r['severity']} A={r['brazo_A_control_exit']} B={r['brazo_B_hysteresis_exit']} "
              f"C={r['brazo_C_confirmation_exit']} D={r['brazo_D_both_exit']}")
    if len(new_rows) > 10:
        print(f"  ... y {len(new_rows) - 10} mas")

    if dry_run:
        print("\nDry-run: no se ha escrito nada.")
        return 0

    if new_rows:
        _append_jsonl(OUT_PATH, new_rows)
        print(f"\n{len(new_rows)} fila(s) anadida(s) a {OUT_PATH}")
    else:
        print("\nSin filas nuevas (ya capturado hoy o sin posiciones en ambito).")
    return 0


def print_report():
    rows = _load_jsonl(OUT_PATH)
    if not rows:
        print("Sin datos todavia en", OUT_PATH)
        return
    dates = sorted(set(r["date"] for r in rows))
    positions = set(r["position_id"] for r in rows)
    print(f"pcs_floor_factorial_v1_shadow.jsonl -- {len(rows)} filas")
    print(f"  rango de fechas: {dates[0]} -> {dates[-1]} ({len(dates)} dias distintos)")
    print(f"  posiciones distintas evaluadas: {len(positions)}")

    sev_counts: dict[str, int] = {}
    for r in rows:
        sev_counts[r["severity"] or "none/na"] = sev_counts.get(r["severity"] or "none/na", 0) + 1
    print(f"  severidad (todas las filas): {sev_counts}")

    # Primer disparo por posicion y brazo -- evento independiente, no fila.
    first_exit: dict[str, dict[str, str]] = {}
    by_position: dict[str, list[dict]] = {}
    for r in rows:
        by_position.setdefault(r["position_id"], []).append(r)
    for pos_id, pos_rows in by_position.items():
        pos_rows.sort(key=lambda r: r["date"])
        first_exit[pos_id] = {}
        for brazo in ("brazo_A_control_exit", "brazo_B_hysteresis_exit",
                      "brazo_C_confirmation_exit", "brazo_D_both_exit"):
            for r in pos_rows:
                if r.get(brazo):
                    first_exit[pos_id][brazo] = r["date"]
                    break

    for brazo in ("brazo_A_control_exit", "brazo_B_hysteresis_exit",
                  "brazo_C_confirmation_exit", "brazo_D_both_exit"):
        n = sum(1 for pos_id in first_exit if brazo in first_exit[pos_id])
        print(f"  {brazo}: {n}/{len(by_position)} posiciones con disparo (primera lectura)")

    print("\n  n(operaciones) y n(eventos independientes) -- doble criterio de §1.1/§6:")
    print(f"    posiciones evaluadas: {len(by_position)}  |  event_id distintos: "
          f"{len(set(r.get('event_id') for r in rows if r.get('event_id')))}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        print_report()
    else:
        sys.exit(run(dry_run="--dry-run" in sys.argv))
