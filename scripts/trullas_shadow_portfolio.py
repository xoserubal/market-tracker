"""
Cartera TRULLAS_SHADOW — 100% mecánica, sin IA en ningún punto (entrada ni
salida), igual que CRUCE_ROJO_D/CRUCE_ROJO_D_25. Implementa exactamente la
regla ganadora del backtest de research/trullas_divergence_backtest_v1/
(TP fijo al 38.2% de Fibonacci — bate a "dejar correr hasta cruce MACD" y a
cualquier otro nivel de la escalera probada, ver README de esa carpeta).

Lanzada en modo SHADOW a propósito (acordado con el usuario 2026-09-20): el
backtest tiene n=82 señales en 6.5 años sobre 118 tickers — muy por debajo
del umbral que este proyecto ya se exige antes de operar capital real
(~40-150 eventos, ver wiki/PREREGISTRO_PCS_FLOOR_FACTORIAL_V1.md). Esta
cartera acumula muestra real en paralelo mientras el usuario usa la pestaña
trullas.html de forma discrecional — no es una recomendación de trading.

Entrada: scripts/trullas_signal_calculator.py marca signal_state="entry_today"
para un ticker cuando su APERTURA de HOY es la primera apertura, dentro de
la ventana de 15 sesiones desde el segundo pivote, que cae en la zona de
retroceso 23-25% de Fibonacci de una divergencia alcista confirmada por
MACD (obligatorio) + opcionalmente RSI/Volumen (niveles de confianza
T1/T2/T3, ver docstring del calculador). El fill se hace a esa apertura
(`c["open"]`), no al cierre — corregido 2026-09-21 a raíz de una revisión
externa que encontró que el modelo anterior (fill al mismo cierre que
genera la señal) sobreestimaba el resultado real ejecutable: solo el 41%
de las señales del backtest tenían una apertura siguiente realmente válida
en la zona; el resto ya la había rebasado o roto el stop (ver CLAUDE.md,
"corrección de V1_OPEN", y research/trullas_early_detector_v1/README.md).
Se guarda `tier_at_entry` para poder analizar más adelante si T3 (máxima
confianza) rinde mejor que el resto, tal como sugiere el propio método de
Trullás.

Salida — igual que el backtest ganador, contra los valores YA CONGELADOS al
momento de la entrada (`tp_at_entry`/`stop_at_entry`), no contra un pivote
nuevo que pueda haberse formado después:
  1. precio <= stop_at_entry (ruptura del pivote de origen)
  2. precio >= tp_at_entry (38.2% de Fibonacci)
  3. bars_held_since_entry >= 20 sesiones (time-stop)

Tamaño 5% fijo, sin límite de posiciones — mismo patrón que MIRROR_ESPEJO/
CRUCE_ROJO_D. Universo: el de trullas_signal_calculator.py (portfolio.json).

Uso:
    py -3 scripts/trullas_shadow_portfolio.py              # dry-run
    py -3 scripts/trullas_shadow_portfolio.py --apply       # aplica de verdad
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

SIGNALS_JSON = DATA / "trullas_signals.json"
PICKS_JSON = DATA / "ai_picks.json"
LOG_PATH = DATA / "trullas_shadow_log.jsonl"

NAME = "TRULLAS_SHADOW"
SIZE_PCT = 5.0
MAX_POSITIONS = 999
TIME_STOP_BARS = 20


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def qualifies_for_entry(sig: dict) -> bool:
    return sig.get("signal_state") == "entry_today"


def build_candidates(signals: dict[str, dict], already_held: set[str]) -> list[dict]:
    out = []
    for tk, sig in signals.items():
        if tk in already_held:
            continue
        if not qualifies_for_entry(sig):
            continue
        out.append(sig)
    return out


def check_exits(picks: dict, signals: dict[str, dict], today: str) -> list[dict]:
    ptf = picks.setdefault("portfolios", {}).setdefault(NAME, {"positions": [], "history": []})
    positions = ptf.get("positions", [])
    if not positions:
        return []

    closed_events = []
    remaining = []
    for pos in positions:
        tk = pos["ticker"]
        sig = signals.get(tk)
        if sig is None or sig.get("price") is None:
            # sin dato hoy (fallo puntual de descarga) — se reintenta el
            # próximo run, mismo criterio que mirror_portfolio.py/CRUCE_ROJO_D
            remaining.append(pos)
            continue

        price = sig["price"]
        tp = pos.get("tp_at_entry")
        stop = pos.get("stop_at_entry")
        bars_held = sig.get("bars_held_since_entry")

        reason = None
        if stop is not None and price <= stop:
            reason = "stop_pivot_break"
        elif tp is not None and price >= tp:
            reason = "tp_fib_38.2"
        elif bars_held is not None and bars_held >= TIME_STOP_BARS:
            reason = "time_stop_20d"

        if reason:
            ptf.setdefault("history", []).append({
                **pos,
                "event": "close",
                "close_date": today,
                "close_price": price,
                "close_reason": reason,
            })
            closed_events.append({"ticker": tk, "close_price": price, "close_reason": reason})
            print(f"  [{NAME}] EXIT {tk}: {reason} (price={price:.4f}, tp={tp}, stop={stop}, "
                  f"bars_held={bars_held})")
        else:
            remaining.append(pos)

    ptf["positions"] = remaining
    return closed_events


def run(apply: bool) -> int:
    today = str(date.today())
    data = _load(SIGNALS_JSON)
    signals = data.get("tickers", {})
    if not signals:
        print("trullas_signals.json vacío o no encontrado — corre trullas_signal_calculator.py primero.")
        return 1

    picks = _load(PICKS_JSON)
    if not isinstance(picks, dict):
        picks = {}
    ptf = picks.setdefault("portfolios", {}).setdefault(NAME, {"positions": [], "history": []})

    already_held = {p["ticker"] for p in ptf.get("positions", [])}
    closed = check_exits(picks, signals, today)
    if closed:
        print(f"  [{NAME}] {len(closed)} posición(es) cerrada(s).")
    already_held -= {c["ticker"] for c in closed}

    candidates = build_candidates(signals, already_held)
    print(f"[{NAME}] Candidatos hoy (signal_state=entry_today, no en cartera): {len(candidates)}")
    for c in candidates:
        print(f"  {c['ticker']:10s} tier={c['tier']} swing={c['swing_pct']}% "
              f"entry_zone=[{c['entry_low']:.4f},{c['entry_high']:.4f}] tp={c['tp']:.4f} stop={c['stop']:.4f}")

    n_open = len(already_held)
    room = MAX_POSITIONS - n_open
    to_add = candidates[:room] if room > 0 else []
    if room <= 0 and candidates:
        print(f"  ⚠ [{NAME}] MAX_POSITIONS={MAX_POSITIONS} alcanzado — {len(candidates)} sin entrar hoy.")

    n_added = 0
    if apply:
        for c in to_add:
            tk = c["ticker"]
            ptf["positions"].append({
                "ticker": tk,
                "entry_date": today,
                "entry_price": c["open"],  # apertura, no cierre -- ver docstring del módulo
                "size_pct": SIZE_PCT,
                "tier_at_entry": c["tier"],
                "rsi_div_at_entry": c["rsi_div"],
                "vol_div_at_entry": c["vol_div"],
                "pivot1_date_at_entry": c["pivot1_date"],
                "pivot1_close_at_entry": c["pivot1_close"],
                "pivot2_date_at_entry": c["pivot2_date"],
                "pivot2_close_at_entry": c["pivot2_close"],
                "swing_pct_at_entry": c["swing_pct"],
                "entry_low_at_entry": c["entry_low"],
                "entry_high_at_entry": c["entry_high"],
                "tp_at_entry": c["tp"],
                "stop_at_entry": c["stop"],
            })
            n_added += 1
            print(f"  [{NAME}] SELECT {tk}: tier={c['tier']} entry={c['open']:.4f} "
                  f"tp={c['tp']:.4f} stop={c['stop']:.4f}")

    summary = {
        "portfolio": NAME, "date": today, "dry_run": not apply,
        "n_candidates": len(candidates), "n_added": n_added, "n_closed": len(closed),
        "added": [c["ticker"] for c in to_add], "closed": [c["ticker"] for c in closed],
    }
    _append_jsonl(LOG_PATH, summary)

    if not apply:
        print("\nDry-run (sin --apply): no se ha escrito ai_picks.json.")
        return 0

    # Persistir siempre que --apply esté activo, aunque no haya cambios hoy —
    # así la cartera aparece en el dashboard desde el primer run, incluso
    # vacía (mismo criterio que mirror_portfolio.py/cruce_rojo_d_portfolio.py).
    _write_json(PICKS_JSON, picks)
    print(f"\n[{NAME}] {n_added} nueva(s) posición(es) añadida(s), {len(closed)} cerrada(s).")
    return 0


if __name__ == "__main__":
    sys.exit(run(apply="--apply" in sys.argv))
