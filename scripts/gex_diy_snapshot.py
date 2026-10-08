"""
GEX DIY — gamma flip de SPX y QQQ, calculado en casa (yfinance + Black-Scholes).

Sustituye a ZeroGEX tras la calibración de Fase 2 (wiki/PREREGISTRO_GEX_ZEROGEX_V1.md,
enmienda 2026-10-08): el flip DIY replicó al de pago con diferencia mediana ~0.3%
del spot (SPX) y ~0.2% (QQQ). Reutiliza literalmente gex_pilot.py
(research/gex_monitor_pilot) — mismos parámetros que en la calibración, sin
retocar (grid ±15%, paso 0.5%, horizonte 60 días).

Qué NO es: no es una señal de compra/venta, no se usa el SIGNO del Net GEX
(la convención "todo el OI de puts es venta de dealers" no es fiable, ver
research/gex_monitor_pilot/HALLAZGOS.md) — solo la posición del flip respecto
al spot, que es lo que sí se validó contra ZeroGEX.

Comprobación de cordura: un flip a más de SANITY_MAX_DIST_PCT del spot se
descarta (flip=null, sanity="out_of_range"). Motivo: el 2026-10-05 el DIY dio
8699 con SPX en 7774 (+12%) por una cadena desequilibrada — sin esta guarda
ese valor habría llegado al dashboard.

Salida: docs/data/gex_diy_history.jsonl (una fila por símbolo y día ET, dedup:
se conserva la primera fila con sanity ok; una fila fuera de rango se sustituye
si un run posterior da un valor válido) y docs/data/gex_diy_latest.json.

Uso:
  py -3 scripts/gex_diy_snapshot.py            # solo dentro de la ventana de mercado
  py -3 scripts/gex_diy_snapshot.py --force    # ignora la ventana horaria
  py -3 scripts/gex_diy_snapshot.py --dry-run
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
HISTORY = DATA / "gex_diy_history.jsonl"
LATEST = DATA / "gex_diy_latest.json"

sys.path.insert(0, str(ROOT / "research" / "gex_monitor_pilot"))
from gex_pilot import fetch_chain_rows, find_gamma_flip  # noqa: E402

ET = ZoneInfo("America/New_York")
SYMBOLS = {"SPX": "^SPX", "QQQ": "QQQ"}  # etiqueta -> ticker yfinance con cadena de opciones

TRANSITION_BAND_PCT = 0.5   # misma banda congelada en el preregistro §2.1
SANITY_MAX_DIST_PCT = 5.0
HORIZON_DAYS, GRID_PCT, GRID_STEP_PCT = 60, 15.0, 0.5

# Ventana de recogida (ET, días laborables). El OI de opciones se actualiza
# por sesión, pero la IV de yfinance antes de la apertura es poco fiable: se
# exige >= 15:30 ET. Límite superior holgado porque el pipeline de GitHub
# suele correr entre 16:30 y 20:30 ET.
WINDOW_START = (15, 30)
WINDOW_END = (21, 0)


def in_window(now_et: datetime) -> bool:
    if now_et.weekday() >= 5:
        return False
    t = (now_et.hour, now_et.minute)
    return WINDOW_START <= t <= WINDOW_END


def classify(distance_pct: float | None) -> str:
    if distance_pct is None:
        return "unknown"
    if distance_pct >= TRANSITION_BAND_PCT:
        return "positive_gamma"
    if distance_pct <= -TRANSITION_BAND_PCT:
        return "negative_gamma"
    return "transition"


def load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    out = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def compute_symbol(label: str, yf_ticker: str, today: str, now_et: datetime) -> dict:
    spot, rows = fetch_chain_rows(yf_ticker, HORIZON_DAYS)
    flip = find_gamma_flip(rows, spot, GRID_PCT, GRID_STEP_PCT)
    sanity = "ok"
    dist = None
    if flip is None:
        sanity = "no_crossing"
    else:
        dist = (spot - flip) / spot * 100
        if abs(dist) > SANITY_MAX_DIST_PCT:
            sanity = "out_of_range"
            flip, dist = None, None
    return {
        "date": today, "symbol": label, "spot": round(spot, 2),
        "gamma_flip": round(flip, 2) if flip is not None else None,
        "distance_to_flip_pct": round(dist, 3) if dist is not None else None,
        "regime": classify(dist), "sanity": sanity,
        "contracts_used": len(rows), "collected_at": now_et.isoformat(),
        "source": "diy_yfinance_bs",
    }


def main() -> int:
    force, dry = "--force" in sys.argv, "--dry-run" in sys.argv
    now_et = datetime.now(ET)
    today = now_et.date().isoformat()
    if not force and not in_window(now_et):
        print(f"Fuera de ventana ({now_et:%a %H:%M} ET) — nada que hacer (usa --force).")
        return 0

    history = load_history()
    new_rows = []
    for label, yft in SYMBOLS.items():
        existing = next((r for r in history if r["symbol"] == label and r["date"] == today), None)
        if existing and existing.get("sanity") == "ok":
            print(f"{label}: ya hay fila válida de hoy — omitido")
            continue
        try:
            row = compute_symbol(label, yft, today, now_et)
        except Exception as e:  # yfinance puede fallar; nunca tumba el pipeline
            print(f"{label}: error {type(e).__name__}: {e}")
            continue
        print(f"{label}: spot={row['spot']} flip={row['gamma_flip']} dist={row['distance_to_flip_pct']} "
              f"{row['regime']} sanity={row['sanity']}")
        new_rows.append(row)

    if not new_rows or dry:
        if dry:
            print("[dry-run] nada escrito")
        return 0

    replaced = {(r["symbol"], r["date"]) for r in new_rows}
    history = [r for r in history if (r["symbol"], r["date"]) not in replaced] + new_rows
    history.sort(key=lambda r: (r["date"], r["symbol"]))
    HISTORY.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in history) + "\n", encoding="utf-8")

    latest = {}
    for label in SYMBOLS:
        rows = [r for r in history if r["symbol"] == label]
        valid = [r for r in rows if r["sanity"] == "ok"]
        latest[label] = {
            "latest": valid[-1] if valid else (rows[-1] if rows else None),
            "series": [{"date": r["date"], "distance_to_flip_pct": r["distance_to_flip_pct"],
                        "gamma_flip": r["gamma_flip"], "spot": r["spot"]} for r in valid[-60:]],
        }
    latest["generated_at"] = now_et.isoformat()
    LATEST.write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Escrito: {HISTORY.name} ({len(history)} filas), {LATEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
