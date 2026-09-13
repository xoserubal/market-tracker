"""
P1A -- PROFIT_PROTECTION_V1 (Hoja de ruta consolidada v1.2, §3, wiki/,
firmada 2026-08-30). Preregistro completo:
wiki/PREREGISTRO_P1A_PROFIT_PROTECTION_V1.md

Hipotesis: un trailing stop de proteccion de ganancias, superpuesto al
suelo de PCS (solo puede adelantar la salida), mejora el retorno del libro
sin danar el mandato de acompanamiento de flujo. Shadow puro -- nunca
escribe en ai_picks.json, nunca cierra nada real.

Ambito: mismo que P1C (§3, literal) -- HIGH_CONVICTION,
CONFIRMED_FLOW_LEADERS, EARLY_ROTATION, MACRO_THEMATIC_BENEFICIARIES,
CAVA_MACRO. MIRROR_ESPEJO excluida (ya tiene su propio mecanismo/experimento).

Dos brazos, congelados (§3, literal, correccion V1.2 del brazo ATR):
  FIXED: armado al alcanzar +10% no realizado desde entrada (MFE, sobre
         cierres); una vez armado, EXIT shadow si el cierre cae >=8% desde
         el maximo de cierre de la tenencia (running_high, ya en P0).
  ATR:   armado si MFE en unidades de precio >= 2.5*ATR(14)_entry (ATR
         congelado el dia de entrada, ver p1_entry_snapshot.py); trailing
         con ratchet monotono: Stop_t = max(Stop_{t-1}, RunningHigh_t -
         2.0*ATR_high_t), donde ATR_high_t se captura SOLO en dias con un
         running_high nuevo (nunca se actualiza en dias de caida -- asi
         una expansion de volatilidad durante el drawdown no afloja el stop).

Corre DESPUES de Step 10i (P0) -- reutiliza sus filas del dia
(entry_price/running_high/MFE/ATR/mechanical_exit_trigger) sin recalcular
nada de eso por separado.

Uso:
    py -3 scripts/p1a_profit_protection_v1_shadow.py              # captura real
    py -3 scripts/p1a_profit_protection_v1_shadow.py --dry-run    # no escribe
    py -3 scripts/p1a_profit_protection_v1_shadow.py --report     # resume el jsonl existente
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

DECISION_STATE = DATA / "ai_picks_decision_state.jsonl"
OUT_PATH = DATA / "p1a_profit_protection_v1_shadow.jsonl"

sys.path.insert(0, str(Path(__file__).parent))
from p1_readiness_monitor import P1A_P1C_SCOPE as P1A_SCOPE  # mismo ambito, una sola fuente
from p1_entry_snapshot import get_entry_snapshot

FIXED_ARM_TRIGGER_PCT = 10.0   # armado: MFE% >= +10%
FIXED_TRAIL_PCT = 8.0         # trailing: EXIT si drawdown desde high >= -8%
ATR_ARM_MULT = 2.5            # armado: MFE_price >= 2.5*ATR_entry
ATR_TRAIL_MULT = 2.0          # trailing: stop = running_high - 2.0*ATR_high


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def evaluate_position_history(rows: list[dict], atr_entry: float | None) -> list[dict]:
    """rows = filas de P0 de UNA posicion, ordenadas por fecha ascendente."""
    out = []
    atr_stop = None          # nivel de precio absoluto, ratchet, nunca baja
    prev_running_high = None
    for row in rows:
        entry_price = row.get("entry_price")
        running_high = row.get("running_high")
        current_price = row.get("current_price")
        mfe_pct = row.get("MFE")
        atr_today = row.get("ATR")

        armed_fixed = bool(mfe_pct is not None and mfe_pct >= FIXED_ARM_TRIGGER_PCT)
        drawdown_from_high = (round((current_price / running_high - 1) * 100, 2)
                               if (current_price and running_high) else None)
        exit_fixed = bool(armed_fixed and drawdown_from_high is not None
                           and drawdown_from_high <= -FIXED_TRAIL_PCT)

        mfe_price = (running_high - entry_price) if (running_high is not None and entry_price is not None) else None
        armed_atr = bool(atr_entry is not None and mfe_price is not None and mfe_price >= ATR_ARM_MULT * atr_entry)

        is_new_high = running_high is not None and (prev_running_high is None or running_high > prev_running_high)
        if is_new_high and atr_today is not None:
            candidate_stop = running_high - ATR_TRAIL_MULT * atr_today
            atr_stop = candidate_stop if atr_stop is None else max(atr_stop, candidate_stop)

        exit_atr = bool(armed_atr and atr_stop is not None and current_price is not None
                         and current_price <= atr_stop)

        out.append({
            "position_id": row["position_id"], "ticker": row["ticker"], "portfolio": row["portfolio"],
            "date": row["date"], "event_id": row.get("event_id"),
            "entry_price": entry_price, "current_price": current_price, "running_high": running_high,
            "MFE": mfe_pct, "atr_entry": atr_entry, "atr_today": atr_today,
            "drawdown_from_high_pct": drawdown_from_high,
            "armed_fixed": armed_fixed, "exit_fixed": exit_fixed,
            "armed_atr": armed_atr, "atr_stop_price": round(atr_stop, 4) if atr_stop is not None else None,
            "exit_atr": exit_atr,
            "control_exit": row.get("mechanical_exit_trigger"), "control_exit_rule_id": row.get("exit_rule_id"),
        })
        prev_running_high = running_high
    return out


def run(dry_run: bool) -> int:
    all_rows = _load_jsonl(DECISION_STATE)
    if not all_rows:
        print("Sin datos en ai_picks_decision_state.jsonl todavia -- P0 debe correr primero.")
        return 1

    scoped = [r for r in all_rows if r["portfolio"] in P1A_SCOPE]
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
        # position_id = f"{ticker}__{entry_date}" (P0) -- se extrae la fecha real de
        # entrada de ahi, no de la primera fila capturada (que puede ser posterior
        # a la entrada real para posiciones abiertas antes de que P0 empezara).
        entry_date = pos_id.split("__", 1)[1] if "__" in pos_id else first["date"]
        snap = get_entry_snapshot(pos_id, first["ticker"], entry_date)
        atr_entry = snap.get("atr_entry")

        evaluated = evaluate_position_history(pos_rows, atr_entry)
        for ev in evaluated:
            key = (ev["position_id"], ev["date"])
            if key not in already_logged:
                new_rows.append(ev)

    print(f"Posiciones en ambito P1A ({', '.join(P1A_SCOPE)}): {len(by_position)}")
    print(f"Filas nuevas a escribir: {len(new_rows)}")
    for r in new_rows[:10]:
        print(f"  {r['portfolio']:24s} {r['ticker']:10s} MFE={r['MFE']} armed_fixed={r['armed_fixed']} "
              f"exit_fixed={r['exit_fixed']} armed_atr={r['armed_atr']} exit_atr={r['exit_atr']} "
              f"control={r['control_exit']}")
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
    print(f"p1a_profit_protection_v1_shadow.jsonl -- {len(rows)} filas")
    print(f"  rango de fechas: {dates[0]} -> {dates[-1]} ({len(dates)} dias distintos)")
    print(f"  posiciones distintas evaluadas: {len(positions)}")

    by_position: dict[str, list[dict]] = {}
    for r in rows:
        by_position.setdefault(r["position_id"], []).append(r)
    for pos_id in by_position:
        by_position[pos_id].sort(key=lambda r: r["date"])

    for brazo in ("control_exit", "exit_fixed", "exit_atr"):
        first_dates = []
        for pos_id, pos_rows in by_position.items():
            for r in pos_rows:
                if r.get(brazo):
                    first_dates.append(r["date"])
                    break
        print(f"  {brazo}: {len(first_dates)}/{len(by_position)} posiciones con disparo (primera lectura)")


if __name__ == "__main__":
    if "--report" in sys.argv:
        print_report()
    else:
        sys.exit(run(dry_run="--dry-run" in sys.argv))
