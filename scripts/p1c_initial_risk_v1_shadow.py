"""
P1C -- INITIAL_RISK_V1 (Hoja de ruta consolidada v1.2, §5, wiki/, firmada
2026-08-30). Preregistro completo:
wiki/PREREGISTRO_P1C_INITIAL_RISK_V1.md

Pregunta: cuando puede reconocerse que una entrada no esta funcionando
ANTES de que el suelo de PCS la cierre -- el subconjunto MFE bajo -> perdida
grande que P1A no puede tocar por construccion (H4). Shadow puro -- nunca
escribe en ai_picks.json, nunca cierra nada real.

Ambito: mismo que P1A (§3/§5) -- HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS,
EARLY_ROTATION, MACRO_THEMATIC_BENEFICIARIES, CAVA_MACRO.

Cuatro brazos (§5, literal):
  A (control)  -> suelo de PCS actual, tal cual (mechanical_exit_trigger de P0).
  B (ATR stop) -> Cierre < entrada - 2.0*ATR(14)_entry (ATR congelado el dia
                  de entrada, ver p1_entry_snapshot.py).
  C (time stop)-> A las 7 sesiones, si MFE_price < 0.5*ATR(14)_entry (congelado)
                  Y retorno < 0 -> fallo. Evaluado UNA VEZ, en la primera fila
                  cuya sesion (indice dentro del historial capturado por P0
                  para esta posicion) sea >= 7 -- no se repite en dias
                  posteriores.
  D (structure)-> Cierre < minimo de Low en las 5 sesiones ANTERIORES a la
                  entrada (pre_entry_low_5d, ver p1_entry_snapshot.py).

Caveat de honestidad documentado (no oculto): "sesion" para el brazo C es el
INDICE DE FILA dentro del historial que P0 lleva capturando para esta
posicion, no el conteo real de sesiones NYSE desde la entrada -- para
posiciones abiertas ANTES de que P0 empezara a capturar (2026-08-30), este
indice subestima las sesiones reales transcurridas (el reloj de P0 empieza
tarde). Para posiciones abiertas EN o DESPUES de la firma (2026-08-30, que
es lo que cuenta para el criterio de promocion de §1.1), el indice coincide
con las sesiones reales porque P0 captura desde el mismo dia de entrada.

Uso:
    py -3 scripts/p1c_initial_risk_v1_shadow.py              # captura real
    py -3 scripts/p1c_initial_risk_v1_shadow.py --dry-run    # no escribe
    py -3 scripts/p1c_initial_risk_v1_shadow.py --report     # resume el jsonl existente
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

DECISION_STATE = DATA / "ai_picks_decision_state.jsonl"
OUT_PATH = DATA / "p1c_initial_risk_v1_shadow.jsonl"

sys.path.insert(0, str(Path(__file__).parent))
from p1_readiness_monitor import P1A_P1C_SCOPE as P1C_SCOPE
from p1_entry_snapshot import get_entry_snapshot

B_ATR_MULT = 2.0        # cierre < entrada - 2.0*ATR_entry
C_SESSIONS = 7          # time stop evaluado en la sesion 7
C_MFE_ATR_MULT = 0.5    # MFE_price < 0.5*ATR_entry


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def evaluate_position_history(rows: list[dict], atr_entry: float | None,
                                pre_entry_low_5d: float | None) -> list[dict]:
    out = []
    c_already_fired = False
    for idx, row in enumerate(rows, start=1):  # idx = "sesion" aproximada, ver caveat en docstring
        entry_price = row.get("entry_price")
        current_price = row.get("current_price")
        running_high = row.get("running_high")

        brazo_a = row.get("mechanical_exit_trigger")

        brazo_b = bool(atr_entry is not None and current_price is not None and entry_price is not None
                        and current_price < entry_price - B_ATR_MULT * atr_entry)

        brazo_c = False
        if not c_already_fired and idx >= C_SESSIONS:
            mfe_price = (running_high - entry_price) if (running_high is not None and entry_price is not None) else None
            retorno_pct = (round((current_price / entry_price - 1) * 100, 2)
                           if (current_price is not None and entry_price is not None) else None)
            cond_mfe = (atr_entry is not None and mfe_price is not None and mfe_price < C_MFE_ATR_MULT * atr_entry)
            cond_ret = (retorno_pct is not None and retorno_pct < 0)
            brazo_c = bool(cond_mfe and cond_ret)
            c_already_fired = True  # evaluacion puntual, una sola vez, dispare o no

        brazo_d = bool(pre_entry_low_5d is not None and current_price is not None
                        and current_price < pre_entry_low_5d)

        out.append({
            "position_id": row["position_id"], "ticker": row["ticker"], "portfolio": row["portfolio"],
            "date": row["date"], "event_id": row.get("event_id"), "session_index": idx,
            "entry_price": entry_price, "current_price": current_price,
            "atr_entry": atr_entry, "pre_entry_low_5d": pre_entry_low_5d,
            "brazo_A_control_exit": brazo_a, "brazo_A_exit_rule_id": row.get("exit_rule_id"),
            "brazo_B_atr_stop_exit": brazo_b,
            "brazo_C_time_stop_exit": brazo_c,
            "brazo_D_structure_exit": brazo_d,
        })
    return out


def run(dry_run: bool) -> int:
    all_rows = _load_jsonl(DECISION_STATE)
    if not all_rows:
        print("Sin datos en ai_picks_decision_state.jsonl todavia -- P0 debe correr primero.")
        return 1

    scoped = [r for r in all_rows if r["portfolio"] in P1C_SCOPE]
    by_position: dict[str, list[dict]] = {}
    for r in scoped:
        by_position.setdefault(r["position_id"], []).append(r)
    for pos_id in by_position:
        by_position[pos_id].sort(key=lambda r: r["date"])

    existing = _load_jsonl(OUT_PATH)
    already_logged = {(r["position_id"], r["date"]) for r in existing}

    new_rows = []
    for pos_id, pos_rows in by_position.items():
        first = pos_rows[0]
        entry_date = pos_id.split("__", 1)[1] if "__" in pos_id else first["date"]
        snap = get_entry_snapshot(pos_id, first["ticker"], entry_date)
        atr_entry = snap.get("atr_entry")
        pre_entry_low_5d = snap.get("pre_entry_low_5d")

        evaluated = evaluate_position_history(pos_rows, atr_entry, pre_entry_low_5d)
        for ev in evaluated:
            key = (ev["position_id"], ev["date"])
            if key not in already_logged:
                new_rows.append(ev)

    print(f"Posiciones en ambito P1C ({', '.join(P1C_SCOPE)}): {len(by_position)}")
    print(f"Filas nuevas a escribir: {len(new_rows)}")
    for r in new_rows[:10]:
        print(f"  {r['portfolio']:24s} {r['ticker']:10s} sesion={r['session_index']} A={r['brazo_A_control_exit']} "
              f"B={r['brazo_B_atr_stop_exit']} C={r['brazo_C_time_stop_exit']} D={r['brazo_D_structure_exit']}")
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
    print(f"p1c_initial_risk_v1_shadow.jsonl -- {len(rows)} filas")
    print(f"  rango de fechas: {dates[0]} -> {dates[-1]} ({len(dates)} dias distintos)")
    print(f"  posiciones distintas evaluadas: {len(positions)}")

    by_position: dict[str, list[dict]] = {}
    for r in rows:
        by_position.setdefault(r["position_id"], []).append(r)
    for pos_id in by_position:
        by_position[pos_id].sort(key=lambda r: r["date"])

    for brazo in ("brazo_A_control_exit", "brazo_B_atr_stop_exit",
                  "brazo_C_time_stop_exit", "brazo_D_structure_exit"):
        n = 0
        for pos_id, pos_rows in by_position.items():
            if any(r.get(brazo) for r in pos_rows):
                n += 1
        print(f"  {brazo}: {n}/{len(by_position)} posiciones con disparo")


if __name__ == "__main__":
    if "--report" in sys.argv:
        print_report()
    else:
        sys.exit(run(dry_run="--dry-run" in sys.argv))
