"""
MIRROR_ESPEJO — cartera experimental gestionada exclusivamente por Grok, basada
únicamente en la señal Koncorde "espejo" (konc_mirror_signal), sin mirar PCS,
rot_score, DEMS ni ninguna otra métrica del resto del sistema. Ver CLAUDE.md
("Koncorde 'espejo'") para el contexto completo del patrón.

Entrada: llamada dedicada a Grok (no la llamada multi-cartera de paper_trading.py)
con únicamente los tickers en konc_mirror_signal="mirror_reversal_confirmed" hoy
que no estén ya en cartera. Universo: todo lo que koncorde_calculator.py rastrea
(no solo los candidatos PCS-elegibles de ai_candidates.json).

Salida: mecánica, en código, SIN intervención de la IA — trailing stop del 5%
desde el máximo de cierre diario alcanzado desde la entrada (high_water_mark).
Se evalúa en cada run, antes de considerar nuevas entradas.

Uso:
    py -3 scripts/mirror_portfolio.py              # dry-run: muestra candidatos, no llama a Grok ni escribe
    py -3 scripts/mirror_portfolio.py --apply       # llama a Grok y aplica entradas/salidas de verdad
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from paper_trading import call_model, compute_cost, parse_response, _model_max_tokens

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

KONCORDE_JSON = DATA / "koncorde_data.json"
PICKS_JSON    = DATA / "ai_picks.json"
UNIVERSE_JSON = DATA / "universe.json"
LOG_PATH      = DATA / "mirror_portfolio_log.jsonl"

PORTFOLIO_NAME     = "MIRROR_ESPEJO"
MODEL              = "x-ai/grok-4.3"   # fijo: esta cartera la gestiona Grok, independiente de ACTIVE_MODEL
SIZE_PCT           = 5.0
TRAILING_STOP_PCT  = 0.05              # -5% desde el máximo de cierre desde la entrada
MAX_POSITIONS      = 999               # sin límite práctico (decisión del usuario 2026-07-03)

SYSTEM_PROMPT = """Eres el gestor de una cartera de paper trading experimental llamada MIRROR_ESPEJO.

Esta cartera tiene una única regla de entrada: solo puedes seleccionar tickers que
muestren la señal Koncorde "espejo", que ya viene filtrada en la lista de candidatos
que recibes. NO se usa PCS, rot_score, DEMS, ni ninguna otra métrica del resto del
sistema para esta cartera — evalúa únicamente en base al contexto de la señal espejo
y tu propio juicio sobre si el giro parece creíble.

Qué es la señal espejo: el activo estaba sobrevendido (blue y green de Koncorde Plus
ambos negativos). De repente gira: blue cruza de negativo a positivo mientras green
sigue negativo. Cada candidato trae un campo "signal" con el nivel de confirmación:
- "mirror_reversal_confirmed": el cruce es fresco simultáneamente en el timeframe
  diario (D) y en el de 3 días (3D) — más confirmado, no es ruido de un solo día.
- "mirror_reversal_daily_only": el cruce solo se ve en D todavía; el 3D aún no lo
  confirma — señal más temprana pero también más especulativa, con más riesgo de
  que sea un rebote de un día que se apague antes de confirmarse en 3D.
En ambos casos, el timeframe semanal (W) todavía tiene blue negativo, es decir la
tendencia de fondo aún no ha girado — esto sugiere que puede ser el inicio de una
mini-tendencia, no solo un rebote de un día, porque todavía hay margen antes de que
el timeframe lento lo refleje.

No toda señal espejo es un giro real — algunas serán ruido o rebotes que se apagan,
especialmente las "daily_only". Usa los valores numéricos de blue/green/trend
proporcionados, el nivel de confirmación (signal) y cualquier contexto de precio para
juzgar si el giro parece limpio o si hay señales de que es débil.

La salida de estas posiciones NO la decides tú — es mecánica: se cierran automáticamente
cuando el precio cierra un 5% por debajo del máximo alcanzado desde la entrada. No
incluyas recomendaciones de salida.

Responde SOLO con JSON válido, sin markdown ni texto adicional, con este schema exacto:
{
  "date": "YYYY-MM-DD",
  "selected": [
    {"ticker": "XXX", "reason": "1-2 frases citando los valores concretos de blue/green/trend que ves"}
  ],
  "skipped": [
    {"ticker": "XXX", "reason": "por qué no la seleccionas pese a la señal espejo"}
  ]
}
Puedes seleccionar 0 o más tickers. Una lista "selected" vacía es una respuesta válida
si ningún candidato te convence.
"""


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_universe_map() -> dict[str, dict]:
    data = _load(UNIVERSE_JSON)
    return {t["ticker"]: t for t in data.get("tickers", []) if t.get("ticker")}


def fetch_last_closes(tickers: list[str]) -> dict[str, float]:
    """Último cierre diario para una lista de tickers. Best-effort, ignora fallos individuales."""
    if not tickers:
        return {}
    out: dict[str, float] = {}
    try:
        raw = yf.download(tickers, period="5d", auto_adjust=True, progress=False,
                           group_by="ticker" if len(tickers) > 1 else None)
    except Exception as e:
        print(f"  ⚠ fetch_last_closes error: {e}")
        return out
    for tk in tickers:
        try:
            if len(tickers) == 1:
                series = raw["Close"].dropna()
            else:
                series = raw[tk]["Close"].dropna()
            if len(series):
                out[tk] = float(series.iloc[-1])
        except Exception:
            continue
    return out


def check_trailing_stops(picks: dict, today: str) -> list[dict]:
    """
    Evalúa el trailing stop del 5% para cada posición abierta en MIRROR_ESPEJO.
    Mecánico, sin IA. Actualiza high_water_mark siempre; cierra si el cierre de
    hoy queda <= high_water_mark * (1 - TRAILING_STOP_PCT). Devuelve los cierres.
    """
    ptf = picks.setdefault("portfolios", {}).setdefault(
        PORTFOLIO_NAME, {"positions": [], "history": []}
    )
    positions = ptf.get("positions", [])
    if not positions:
        return []

    tickers = [p["ticker"] for p in positions]
    closes = fetch_last_closes(tickers)

    closed_events = []
    remaining = []
    for pos in positions:
        tk = pos["ticker"]
        price = closes.get(tk)
        if price is None:
            remaining.append(pos)  # sin dato hoy: no tocar, reintentar el próximo run
            continue

        hwm = max(pos.get("high_water_mark", pos.get("entry_price", price)), price)
        pos["high_water_mark"] = hwm
        stop_price = hwm * (1 - TRAILING_STOP_PCT)

        if price <= stop_price:
            close_reason = f"trailing_stop_{int(TRAILING_STOP_PCT*100)}pct_from_high (hwm={hwm:.2f}, close={price:.2f})"
            ptf.setdefault("history", []).append({
                **pos,
                "close_date":   today,
                "close_price":  price,
                "close_reason": close_reason,
            })
            closed_events.append({"ticker": tk, "close_price": price, "high_water_mark": hwm})
            print(f"  EXIT {tk}: cierre {price:.2f} <= stop {stop_price:.2f} (hwm {hwm:.2f})")
        else:
            remaining.append(pos)

    ptf["positions"] = remaining
    return closed_events


MIRROR_ELIGIBLE_SIGNALS = ("mirror_reversal_confirmed", "mirror_reversal_daily_only")


def build_candidates(koncorde_out: dict[str, dict], already_held: set[str],
                      universe_map: dict[str, dict]) -> list[dict]:
    """
    Candidatos elegibles: mirror_reversal_confirmed (D+3D fresco) y también
    mirror_reversal_daily_only (solo D, 3D aún no confirma) — decisión del
    usuario 2026-07-03: incluir daily_only también, no solo confirmed, para no
    perderse señales tempranas como la de VAL (2026-07-03, daily_only). Grok
    recibe el nivel de cada candidato (signal) para poder ponderarlo.
    """
    candidates = []
    for tk, k in koncorde_out.items():
        signal = k.get("konc_mirror_signal")
        if signal not in MIRROR_ELIGIBLE_SIGNALS:
            continue
        if tk in already_held:
            continue
        u = universe_map.get(tk, {})
        candidates.append({
            "ticker":         tk,
            "signal":         signal,
            "name":           u.get("name", ""),
            "theme":          u.get("theme", ""),
            "subtheme":       u.get("subtheme", ""),
            "konc_d_blue":    k.get("konc_d_blue"),
            "konc_d_green":   k.get("konc_d_green"),
            "konc_3d_blue":   k.get("konc_3d_blue"),
            "konc_3d_green":  k.get("konc_3d_green"),
            "konc_3d_trend":  k.get("konc_3d_trend"),
            "konc_w_blue":    k.get("konc_w_blue"),
        })
    return candidates


def run(apply: bool) -> int:
    today = str(date.today())
    koncorde = _load(KONCORDE_JSON)
    koncorde_out = koncorde.get("tickers", {})
    if not koncorde_out:
        print("koncorde_data.json vacío o no encontrado — corre koncorde_calculator.py primero.")
        return 1

    picks = _load(PICKS_JSON)
    if not isinstance(picks, dict):
        picks = {}
    universe_map = _load_universe_map()

    # ── 1. Salidas mecánicas (siempre se aplican, no dependen de --apply ni de Grok) ──
    ptf = picks.setdefault("portfolios", {}).setdefault(
        PORTFOLIO_NAME, {"positions": [], "history": []}
    )
    already_held = {p["ticker"] for p in ptf.get("positions", [])}
    closed = check_trailing_stops(picks, today)
    if closed:
        print(f"  {len(closed)} posición(es) cerrada(s) por trailing stop.")
    already_held -= {c["ticker"] for c in closed}

    # Persistir siempre que --apply esté activo, aunque no haya cambios hoy —
    # así la cartera aparece en el dashboard desde el primer run, incluso vacía.
    if apply:
        _write_json(PICKS_JSON, picks)

    # ── 2. Candidatos nuevos de hoy ──
    candidates = build_candidates(koncorde_out, already_held, universe_map)
    print(f"Candidatos MIRROR_ESPEJO hoy (confirmed + daily_only, no en cartera): {len(candidates)}")
    for c in candidates:
        print(f"  {c['ticker']:8s} [{c['signal']}] D(blue={c['konc_d_blue']}, green={c['konc_d_green']})  "
              f"3D(blue={c['konc_3d_blue']}, green={c['konc_3d_green']})  W(blue={c['konc_w_blue']})")

    if not candidates:
        print("Sin candidatos nuevos hoy — nada que llamar a Grok.")
        return 0

    if not apply:
        print("\nDry-run (sin --apply): no se ha llamado a Grok ni escrito ai_picks.json.")
        return 0

    # ── 3. Llamada dedicada a Grok ──
    user_message = json.dumps({
        "date": today,
        "portfolio": PORTFOLIO_NAME,
        "mirror_candidates": candidates,
        "open_positions": [{"ticker": p["ticker"], "entry_date": p.get("entry_date"),
                             "days_held": (datetime.strptime(today, "%Y-%m-%d").date()
                                           - datetime.strptime(p["entry_date"], "%Y-%m-%d").date()).days
                             if p.get("entry_date") else None}
                            for p in ptf.get("positions", [])],
    }, ensure_ascii=False)

    t0 = time.monotonic()
    try:
        raw, in_tok, out_tok, latency = call_model(
            MODEL, SYSTEM_PROMPT, user_message, max_tokens=_model_max_tokens(MODEL),
        )
    except Exception as e:
        print(f"  ⚠ Error llamando a {MODEL}: {e}")
        return 1

    data, json_valid = parse_response(raw)
    cost = compute_cost(MODEL, in_tok, out_tok)
    _append_jsonl(LOG_PATH, {
        "date": today, "model": MODEL, "json_valid": json_valid,
        "in_tokens": in_tok, "out_tokens": out_tok, "cost_usd": round(cost, 5),
        "latency_ms": round(latency, 0), "n_candidates": len(candidates),
        "n_selected": len(data.get("selected", [])) if json_valid and data else 0,
        "raw_response_head": (raw or "")[:1500],
    })

    if not json_valid or data is None:
        print(f"  ⚠ Respuesta de Grok no es JSON válido. Ver {LOG_PATH} para el raw.")
        return 1

    cand_tickers = {c["ticker"] for c in candidates}
    n_added = 0
    for sel in data.get("selected", []):
        tk = sel.get("ticker", "")
        if tk not in cand_tickers:
            print(f"  ⚠ Grok seleccionó {tk}, que no estaba en la lista de candidatos — ignorado.")
            continue
        c = next(c for c in candidates if c["ticker"] == tk)
        entry_price = fetch_last_closes([tk]).get(tk)
        ptf["positions"].append({
            "ticker":            tk,
            "entry_date":        today,
            "entry_price":       entry_price,
            "entry_signal":      c["signal"],
            "size_pct":          SIZE_PCT,
            "high_water_mark":   entry_price,
            "reason":            sel.get("reason", ""),
            "konc_d_blue_at_entry":  c["konc_d_blue"],
            "konc_d_green_at_entry": c["konc_d_green"],
            "konc_3d_blue_at_entry": c["konc_3d_blue"],
            "konc_w_blue_at_entry":  c["konc_w_blue"],
        })
        n_added += 1
        print(f"  SELECT {tk}: {sel.get('reason', '')[:100]}")

    for sk in data.get("skipped", []):
        print(f"  skip {sk.get('ticker')}: {sk.get('reason', '')[:100]}")

    if n_added:
        _write_json(PICKS_JSON, picks)
        print(f"\n{n_added} nueva(s) posición(es) añadida(s) a {PORTFOLIO_NAME}, ai_picks.json actualizado. "
              f"Coste: ${cost:.4f}")
    else:
        print(f"\nGrok no seleccionó ningún candidato hoy. Coste: ${cost:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(run(apply="--apply" in sys.argv))
