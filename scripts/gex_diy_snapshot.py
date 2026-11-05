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

CAMBIO DE MÉTODO 2026-11-05 (ver enmienda en wiki/PREREGISTRO_GEX_ZEROGEX_V1.md):
la IV por contrato de yfinance fuera de horario es basura (IV ATM del SPX 0,016
a las 18:30 ET cuando la real rondaba 0,28) y el pipeline siempre recoge tras el
cierre. Consecuencias medidas: el mismo día y con el mismo OI el flip salía
−3,86% a las 17:11 y −1,35% a las 18:30; flip == spot exacto en 4 de 12 días de
finales de octubre; y cadenas casi vacías (18-65 contratos) que una vez pasaron
la guarda (2026-11-04, 65 contratos → el "pico" del dashboard). Ahora:
  - IV plana por vencimiento interpolada (en varianza total) de ^VIX9D/^VIX/^VIX3M
    (SPX); QQQ usa la misma curva escalada por ^VXN/^VIX. Cierres diarios
    publicados: el resultado ya no depende de la hora de recogida.
  - Se excluyen los vencimientos ya expirados (antes el 0DTE del día entraba
    tras el cierre con T forzada a 1 hora).
  - MIN_CONTRACTS por símbolo (sanity="thin_chain").
  - SANITY_MAX_DIST_PCT 5 → 10: con 5 se descartaba un QQQ legítimo en días de
    caída fuerte (2026-11-05, flip >5% por encima según la referencia externa).
Validación 2026-11-05: SPX flip 7675,6 frente a 7674,8 de una fuente externa
independiente (Philosopher Investor, consultada a mano; su web prohíbe extraer
datos con scripts). QQQ +3,8% sobre la referencia: la cadena de QQQ en
yfinance trae los vencimientos diarios incompletos.

Uso:
  py -3 scripts/gex_diy_snapshot.py            # solo dentro de la ventana de mercado
  py -3 scripts/gex_diy_snapshot.py --force    # ignora la ventana horaria
  py -3 scripts/gex_diy_snapshot.py --replace  # recalcula aunque ya haya fila válida de hoy
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
from gex_pilot import find_gamma_flip, _valid  # noqa: E402

ET = ZoneInfo("America/New_York")
SYMBOLS = {"SPX": "^SPX", "QQQ": "QQQ"}  # etiqueta -> ticker yfinance con cadena de opciones

TRANSITION_BAND_PCT = 0.5   # misma banda congelada en el preregistro §2.1
SANITY_MAX_DIST_PCT = 10.0
HORIZON_DAYS, GRID_PCT, GRID_STEP_PCT = 60, 15.0, 0.5
# Cadena normal: SPX 5.000-9.000 contratos, QQQ 3.000-4.000. Por debajo de esto
# yfinance ha devuelto una cadena rota (casos reales de 18-65 contratos).
MIN_CONTRACTS = {"SPX": 2000, "QQQ": 1000}
SOURCE = "diy_yfinance_oi_vix_iv"

# Curva de volatilidad: plazo en días -> índice de volatilidad (cierre diario).
VIX_TERM = {9: "^VIX9D", 30: "^VIX", 93: "^VIX3M"}
IV_SCALE_INDEX = {"QQQ": "^VXN"}  # QQQ: curva del SPX escalada por VXN/VIX


def _last_close(ticker: str) -> float | None:
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="5d")["Close"].dropna()
    return float(h.iloc[-1]) if len(h) else None


def vix_term_curve(label: str) -> tuple[dict[int, float], float]:
    """{días: IV decimal} y factor de escala para el símbolo. Lanza si falta el VIX."""
    curve = {d: v / 100 for d, t in VIX_TERM.items() if (v := _last_close(t))}
    if 30 not in curve:
        raise RuntimeError("sin cierre de ^VIX — no se calcula con IV de yfinance")
    scale = 1.0
    if label in IV_SCALE_INDEX:
        alt = _last_close(IV_SCALE_INDEX[label])
        if alt is None:
            raise RuntimeError(f"sin cierre de {IV_SCALE_INDEX[label]}")
        scale = (alt / 100) / curve[30]
    return curve, scale


def iv_for_days(curve: dict[int, float], days: float) -> float:
    """Interpolación lineal en varianza total entre plazos; plana fuera del rango."""
    pts = sorted(curve.items())
    if days <= pts[0][0]:
        return pts[0][1]
    if days >= pts[-1][0]:
        return pts[-1][1]
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= days <= d1:
            w0, w1 = v0 * v0 * d0, v1 * v1 * d1
            return ((w0 + (w1 - w0) * (days - d0) / (d1 - d0)) / days) ** 0.5
    return pts[-1][1]


def fetch_chain_rows_vix_iv(label: str, yf_ticker: str, now_et: datetime) -> tuple[float, list[dict], float]:
    """Como gex_pilot.fetch_chain_rows pero con IV de la familia VIX y sin
    vencimientos ya expirados. Devuelve (spot, rows, iv_30d_usada)."""
    import yfinance as yf
    curve, scale = vix_term_curve(label)
    tk = yf.Ticker(yf_ticker)
    spot = float(tk.history(period="1d", auto_adjust=True)["Close"].iloc[-1])
    rows: list[dict] = []
    for exp in tk.options:
        expiry = datetime.strptime(exp, "%Y-%m-%d").replace(hour=16, tzinfo=ET)
        days = (expiry - now_et).total_seconds() / 86400
        if days <= 0 or days > HORIZON_DAYS:
            continue
        iv = iv_for_days(curve, max(days, 1.0)) * scale
        chain = tk.option_chain(exp)
        for side, df in (("call", chain.calls), ("put", chain.puts)):
            for _, r in df.iterrows():
                oi = r["openInterest"]
                if not _valid(oi) or oi <= 0:
                    continue
                rows.append({"expiry": exp, "side": side, "strike": float(r["strike"]),
                             "oi": float(oi), "iv": iv, "t_years": days / 365})
    return spot, rows, curve[30] * scale

# Ventana de recogida (ET, días laborables). La IV ya no sale de yfinance (ver
# docstring), así que la hora no altera el resultado; la ventana se mantiene
# para que la fila de hoy use el OI y el cierre del VIX de la sesión de hoy y no
# los de ayer (un run de madrugada). Límite superior holgado: el pipeline de
# GitHub suele correr entre 16:30 y 20:30 ET.
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
    spot, rows, iv30 = fetch_chain_rows_vix_iv(label, yf_ticker, now_et)
    flip, dist = None, None
    if len(rows) < MIN_CONTRACTS.get(label, 0):
        sanity = "thin_chain"
    else:
        flip = find_gamma_flip(rows, spot, GRID_PCT, GRID_STEP_PCT)
        sanity = "ok"
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
        "contracts_used": len(rows), "iv_30d": round(iv30, 4),
        "collected_at": now_et.isoformat(), "source": SOURCE,
    }


def write_latest(history: list[dict], now_et: datetime) -> None:
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


def main() -> int:
    force, dry, replace = "--force" in sys.argv, "--dry-run" in sys.argv, "--replace" in sys.argv
    now_et = datetime.now(ET)
    today = now_et.date().isoformat()
    if not force and not in_window(now_et):
        print(f"Fuera de ventana ({now_et:%a %H:%M} ET) — nada que hacer (usa --force).")
        return 0

    history = load_history()
    new_rows = []
    for label, yft in SYMBOLS.items():
        existing = next((r for r in history if r["symbol"] == label and r["date"] == today), None)
        if existing and existing.get("sanity") == "ok" and not replace:
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
    write_latest(history, now_et)
    print(f"Escrito: {HISTORY.name} ({len(history)} filas), {LATEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
