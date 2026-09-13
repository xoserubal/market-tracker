"""
P1B -- ENTRY_TIMING_V1 (Hoja de ruta consolidada v1.2, §4, wiki/, firmada
2026-08-30). Preregistro completo:
wiki/PREREGISTRO_P1B_ENTRY_TIMING_V1.md

Pregunta: entre valores ya seleccionados por el sistema, ¿que discrimina
follow-through de failed entry? Hipotesis primaria (H7): la sobreextension
de corto plazo en la fecha de entrada (w1_ret_5d del ticker en la fecha del
SELECT) predice negativamente el follow-through (ret_21d sobre precio,
NUNCA sobre vida de la posicion -- H9, restriccion obligatoria).

A diferencia de P1A/P1C, esto NO es un shadow de reglas de salida -- es una
captura de correlacion. Solo registra; el test primario (Spearman) se
imprime en --report cuando hay muestra suficiente (>=60 eventos, §4), nunca
se aplica a ninguna cartera.

Ambito y fuente de datos (decision de implementacion, la hoja de ruta dice
"cualquier cartera, sin restriccion" pero eso es el ambito del CONTADOR de
p1_readiness_monitor.py, que cuenta sobre ai_picks.json -- incluye tambien
MIRROR_ESPEJO/CRUCE_ROJO_D*, que NO tienen ret_1m/ret_2w calculados via
shadow_picks.jsonl porque no pasan por ese log). Este script usa como
universo analizable los eventos que SI aparecen en shadow_picks.jsonl
(HIGH_CONVICTION, CONFIRMED_FLOW_LEADERS, EARLY_ROTATION,
MACRO_THEMATIC_BENEFICIARIES, CAVA_MACRO, MIMO_SHADOW,
RANKING_SHADOW_EXPERIMENTAL) -- son las carteras que seleccionan vehiculo
via PCS/candidatos, el mismo mecanismo de "SELECT" al que H7 se refiere.
MIRROR_ESPEJO/CRUCE_ROJO_D* quedan fuera por el mismo motivo que P1A/P1C
las excluyen (mecanismo de entrada categoricamente distinto, ya tienen sus
propios experimentos P6/futuro). Consecuencia declarada: el n que cuenta
hacia el umbral de 60 en p1_readiness_monitor puede ir por delante del n
realmente analizable aqui -- documentado, no oculto.

Reutiliza ret_2w (10 sesiones) y ret_1m (21 sesiones) YA calculados por
update_performance.py (Step 10b) como ret_10d/ret_21d -- NO se recalculan
aqui. update_performance.py ya opera sobre precio de ticker
independientemente de si la posicion sigue abierta (mismo criterio que H9
exige), verificado leyendo su codigo (usa entry_price + precio N sesiones
despues via yfinance, no el estado de la posicion).

Uso:
    py -3 scripts/p1b_entry_timing_v1_shadow.py              # captura real
    py -3 scripts/p1b_entry_timing_v1_shadow.py --dry-run    # no escribe
    py -3 scripts/p1b_entry_timing_v1_shadow.py --report     # test primario si hay n suficiente
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

SHADOW_PICKS = DATA / "shadow_picks.jsonl"
OUT_PATH = DATA / "p1b_entry_timing_v1_shadow.jsonl"

sys.path.insert(0, str(Path(__file__).parent))
from p1_entry_snapshot import get_entry_snapshot
from ranking_score_readiness_monitor import spearman  # sin scipy, ya existe

FIRMA_DATE = "2026-08-30"
P1B_MIN_EVENTS = 60
C_SESSIONS_MONTH_MIN_EVENTS = 10  # un mes solo computa para estabilidad de signo con >=10 eventos


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def dedup_events(shadow_rows: list[dict]) -> dict[str, dict]:
    """event_id = ticker+date, deduplicado ENTRE carteras y modelos (§4,
    literal) -- si el mismo ticker se selecciona el mismo dia en varias
    carteras/modelos, es un solo evento de mercado. Prefiere la fila no-shadow
    (activa) si existe, mismo criterio que _shadow_model_lookup en
    ai_picks_decision_state.py."""
    out: dict[str, dict] = {}
    for r in shadow_rows:
        if r.get("date", "") < FIRMA_DATE:
            continue
        if r.get("valid_for_performance_tracking") is False:
            continue
        ticker, date = r.get("ticker"), r.get("date")
        if not ticker or not date:
            continue
        event_id = f"{ticker}_{date}"
        if event_id not in out or (r.get("shadow") is False and out[event_id].get("shadow") is not False):
            out[event_id] = r
    return out


def run(dry_run: bool) -> int:
    shadow_rows = _load_jsonl(SHADOW_PICKS)
    if not shadow_rows:
        print("Sin datos en shadow_picks.jsonl.")
        return 1

    events = dedup_events(shadow_rows)
    print(f"Eventos SELECT unicos post-firma en shadow_picks.jsonl (ambito analizable): {len(events)}")

    out_rows = []
    for event_id, r in events.items():
        ticker, entry_date = r["ticker"], r["date"]
        snap = get_entry_snapshot(event_id, ticker, entry_date)
        out_rows.append({
            "event_id": event_id, "ticker": ticker, "entry_date": entry_date,
            "portfolio": r.get("portfolio"), "model": r.get("model"), "pcs": r.get("pcs"),
            "w1_ret_5d_at_entry": snap.get("w1_ret_5d_at_entry"),
            "extension_risk_points_at_entry": r.get("extension_points"),
            "extension_risk_level_at_entry": r.get("extension_risk"),
            "ret_10d": r.get("ret_2w"), "ret_21d": r.get("ret_1m"),
            "MFE_1m": r.get("max_gain_1m"), "MAE_1m": r.get("max_drawdown_1m"),
            "snapshot_error": snap.get("error"),
        })

    n_with_outcome = sum(1 for r in out_rows if r["ret_21d"] is not None)
    n_with_predictor = sum(1 for r in out_rows if r["w1_ret_5d_at_entry"] is not None)
    print(f"  con predictor (w1_ret_5d_at_entry): {n_with_predictor}/{len(out_rows)}")
    print(f"  con outcome maduro (ret_21d): {n_with_outcome}/{len(out_rows)}")

    if dry_run:
        print("\nDry-run: no se ha escrito nada.")
        return 0

    # Reconstruye el fichero entero cada vez (no append-only) -- mismo motivo
    # que cfl_reentry_cooldown_shadow.py: ret_21d llega asincronamente dias
    # despues via update_performance.py, y un log append-only congelaria el
    # valor con informacion parcial del dia en que se capturo por primera vez.
    _write_jsonl(OUT_PATH, sorted(out_rows, key=lambda r: (r["entry_date"], r["ticker"])))
    print(f"\n{len(out_rows)} evento(s) escrito(s) en {OUT_PATH}")
    return 0


def print_report():
    rows = _load_jsonl(OUT_PATH)
    if not rows:
        print("Sin datos todavia en", OUT_PATH, "-- correr sin --report primero.")
        return

    usable = [r for r in rows if r["w1_ret_5d_at_entry"] is not None and r["ret_21d"] is not None]
    print(f"p1b_entry_timing_v1_shadow.jsonl -- {len(rows)} eventos totales, {len(usable)} con "
          f"predictor+outcome maduros (umbral de promocion: >={P1B_MIN_EVENTS})")

    if len(usable) < P1B_MIN_EVENTS:
        print(f"Faltan {P1B_MIN_EVENTS - len(usable)} eventos para el umbral de §4 -- "
              f"sin test primario todavia (no se calcula con muestra insuficiente).")
        return

    xs = [r["w1_ret_5d_at_entry"] for r in usable]
    ys = [r["ret_21d"] for r in usable]
    rho = spearman(xs, ys)
    print(f"Spearman(w1_ret_5d_at_entry, ret_21d) sobre {len(usable)} eventos: rho={rho}")

    by_month: dict[str, list[tuple[float, float]]] = {}
    for r in usable:
        month = r["entry_date"][:7]
        by_month.setdefault(month, []).append((r["w1_ret_5d_at_entry"], r["ret_21d"]))
    print("Estabilidad de signo mensual (solo meses con >=%d eventos, §4):" % C_SESSIONS_MONTH_MIN_EVENTS)
    computable_months = 0
    negative_months = 0
    for month in sorted(by_month):
        pairs = by_month[month]
        if len(pairs) < C_SESSIONS_MONTH_MIN_EVENTS:
            print(f"  {month}: n={len(pairs)} -- no computable (<{C_SESSIONS_MONTH_MIN_EVENTS})")
            continue
        m_rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
        computable_months += 1
        if m_rho is not None and m_rho < 0:
            negative_months += 1
        print(f"  {month}: n={len(pairs)} rho={m_rho}")
    print(f"Meses computables: {computable_months} (criterio de §4: signo negativo en >=3 de los "
          f"meses computables, minimo 3 meses computables) -- meses negativos: {negative_months}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        print_report()
    else:
        sys.exit(run(dry_run="--dry-run" in sys.argv))
