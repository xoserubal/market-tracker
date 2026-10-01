"""
flow_state_lib.py — motor compartido de disciplina de promoción sobre
Flow Score (Flow es estado, ΔFlow es cambio de estado, ninguno de los dos
es señal de entrada por sí solo).

Usado por:
  1. market_analysis_llm.py — añade columnas mecánicas a las tablas que ya
     recibe Sol (el LLM narrador), para que no pueda etiquetar EARLY/
     CONFIRMED desde los números crudos sin reconciliar contra un cálculo
     de verdad.
  2. shared/screener-lib.js (espejo en JS, mismos umbrales/constantes) —
     3 screeners nuevos en screeners.html: Inflexión / Continuación /
     Reversión, aplicados a diario sobre el universo de Portfolio Tracker.

Origen (2026-10-01): una auditoría externa sobre market_analysis_llm.jsonl
señaló que Sol etiqueta EARLY el mismo día que aparece un ΔFlow positivo de
un solo día, sin exigir que el Flow haya cruzado realmente por encima de
cero ni que el cambio persista — la auditoría del día siguiente tiene que
deshacerlo. Verificado contra los datos crudos antes de implementar nada
(no solo contra la narrativa de Sol, ver memoria del proyecto sobre
verificar entregables externos): BSX real, flowScore=-2.9 el 2026-09-24,
etiquetado EARLY por Sol ese mismo día ("antes de un zero-cross de Flow" —
literal en su propia prosa); el cruce real no llegó hasta el 2026-09-25
(+0.7) y se revirtió enseguida (negativo otra vez 9/26→10/1). Mismo patrón
en Cannabis (EARLY 9/24-28, INVALIDATED 9/30) y Uranio (EARLY 9/18 con
"Uranium Regime Score" en cero — un término que Sol se inventa en su propia
narrativa, no existe como campo calculado en ningún sitio del proyecto;
aquí se construye de verdad como breadth sobre la cesta real de la sección/
tema, no se narra).

Principio: mismo que ya rige el suelo de PCS desde el 2026-09-22
(histéresis + confirmación en real, ver CLAUDE.md "Suelo de PCS") — exigir
persistencia de varias sesiones y ausencia de veto antes de promocionar,
en vez de dejar que un LLM libre decida desde números de un solo día.

Diseño: SIN máquina de estados con memoria persistida (no se guarda "el
estado de ayer" en ningún sitio) — cada día se reclasifica desde cero a
partir de la ventana de datos ya capturada (portfolio_daily_snapshot.jsonl
+ market_equities_daily_snapshot.jsonl), mismo criterio que
trullas_signal_calculator.py/koncorde_calculator.py. Evita construir el
backend de hipótesis con IDs ya descartado explícitamente el 2026-09-21
("recorte deliberado... mismo criterio de observar antes de construir").

Cestas de tema: NO se inventa una estructura nueva tipo CYCLE_MAP — se
reutilizan las secciones ya curadas de portfolio.json (p. ej. "Cannabis",
"Petróleo", "Argentina") y las `sections` ya persistidas por
market_daily_snapshot.js en cada fila de market_equities_daily_snapshot.jsonl
(p. ej. "URANIO", "GAS NATURAL") — son literalmente las cestas que ya
agrupan las tablas que ve Sol (build_equities_table/build_portfolio_table).
Evita mantener una segunda definición de "qué tickers forman este tema" que
podría desincronizarse de la primera.

Umbrales (ΔFlow a 5 sesiones, persistencia 2/3, RSI 40-58/55-68, Flow entre
-5/+8, percentil ATR 80, etc.) son los que proponía la auditoría externa —
primera pasada, sin calibrar contra rendimiento posterior, mismo criterio
que el resto de señales nuevas del proyecto (extension_risk, ATLAS Mini,
Koncorde mirror…).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
PORTFOLIO_JSON = ROOT / "portfolio.json"
PORTFOLIO_SNAP = DATA / "portfolio_daily_snapshot.jsonl"
MARKET_EQUITIES = DATA / "market_equities_daily_snapshot.jsonl"

# Secciones/temas que son buckets de gestión o paraguas demasiado amplios
# para servir de "cesta de tema" — no representan un tema sectorial/
# narrativo coherente. El resto de secciones (Cannabis, Petróleo, Argentina,
# URANIO, GAS NATURAL...) cuentan como cesta tal cual, sin lista blanca que
# mantener aparte.
EXCLUDED_BASKET_SECTIONS = {
    "Cartera", "Watchlist", "Opciones",
    "MAJOR INDICES", "MAG 6", "BONDS / COMMODITIES",
}

# Koncorde — veto duro (ver koncorde_calculator.py → _konc_alignment()).
KONC_BEARISH = {"distribution_warning", "bearish_aligned"}
KONC_BULLISH_CONFIRMED = "bullish_aligned"  # distinto de bullish_pending_3d_confirmation

# Vehículos apalancados — no heredan la etiqueta de continuación del
# subyacente (sección 7 de la auditoría). Lista corta y explícita, mismo
# patrón que el denylist de ranking_score_experimental_portfolio.py.
LEVERAGED_TICKERS = {"UCO", "UVXY", "TQQQ", "SOXL", "TNA", "SPXL", "BTCC-B.TO"}

DELTA_WINDOW = 5
EARLY_PERSIST_SESSIONS = 2
CONFIRM_PERSIST_SESSIONS = 3
ZERO_CROSS_RECENCY = 3
FLOW_MIN, FLOW_MAX = -5.0, 8.0
RSI_INFLEXION = (40.0, 58.0)
RSI_CONTINUACION = (55.0, 68.0)
RSI_EXTENDED = 70.0
RSI_REVERSION_MAX = 55.0
ATR_PCTILE_WINDOW = 60
ATR_PCTILE_MIN_ROWS = 20  # por debajo de esto no se calcula — "sizing reducido", no exclusión (igual que pide la propia auditoría)
ATR_PCTILE_BLOCK = 80.0
FLOW_EXTENDED_LOOKBACK = 10
FLOW_EXTENDED_THRESHOLD = 15.0
REVERSION_DEEP_NEGATIVE = -10.0
REVERSION_LOOKBACK = 10
CONTINUACION_MIN_ABOVE_ZERO_DAYS = 5


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── Cestas de tema ──────────────────────────────────────────────────────

def load_basket_membership(root: Path = ROOT) -> dict[str, set[str]]:
    """ticker -> set de nombres de cesta/tema (secciones no excluidas).
    Fuente: portfolio.json (secciones curadas por el usuario) +
    `sections` ya persistidas en market_equities_daily_snapshot.jsonl
    (agrupación de market_daily_snapshot.js) — ninguna cesta nueva."""
    membership: dict[str, set[str]] = defaultdict(set)
    try:
        pf = json.loads((root / "portfolio.json").read_text(encoding="utf-8"))
        for sec in pf.get("sections", []):
            name = sec.get("name", "")
            if name in EXCLUDED_BASKET_SECTIONS:
                continue
            for item in sec.get("items", []):
                tk = item.get("ticker")
                if tk:
                    membership[tk].add(name)
    except Exception:
        pass

    for r in _load_jsonl(root / "docs" / "data" / "market_equities_daily_snapshot.jsonl"):
        for sec in (r.get("sections") or []):
            if sec in EXCLUDED_BASKET_SECTIONS:
                continue
            membership[r["ticker"]].add(sec)
    return dict(membership)


def _basket_to_tickers(membership: dict[str, set[str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for tk, baskets in membership.items():
        for b in baskets:
            out[b].add(tk)
    return dict(out)


def compute_theme_breadth(
    ticker: str,
    membership: dict[str, set[str]],
    basket_to_tickers: dict[str, set[str]],
    flow_today: dict[str, float],
    konc_today: dict[str, str | None],
) -> dict:
    """Breadth = % de la cesta (propio ticker incluido) con Flow>0 y sin
    veto de Koncorde. `blocked=True` solo si breadth es literalmente 0 —
    interpretación literal de "regime score = 0" de la auditoría, no un
    umbral bajo arbitrario."""
    baskets = membership.get(ticker)
    if not baskets:
        return {"baskets": [], "breadth_pct": None, "confirmed": None, "total": None, "blocked": False}

    peers: set[str] = {ticker}
    for b in baskets:
        peers |= basket_to_tickers.get(b, set())

    confirmed = 0
    total = 0
    for p in peers:
        f = flow_today.get(p)
        if f is None:
            continue
        total += 1
        if f > 0 and konc_today.get(p) not in KONC_BEARISH:
            confirmed += 1

    if total == 0:
        return {"baskets": sorted(baskets), "breadth_pct": None, "confirmed": None, "total": None, "blocked": False}

    pct = confirmed / total
    return {
        "baskets": sorted(baskets), "breadth_pct": round(pct, 3),
        "confirmed": confirmed, "total": total, "blocked": confirmed == 0,
    }


# ── Historial de Flow por ticker (merge portfolio + market_equities) ────

_FLOW_FIELDS = ("date", "flowScore", "rsi", "konc_alignment", "macdHist", "macdHistDelta1", "atrPct", "price", "m1")


def load_flow_history(root: Path = ROOT) -> dict[str, list[dict]]:
    """ticker -> filas (date, flowScore, rsi, konc_alignment, macdHist,
    macdHistDelta1, atrPct, price, m1), ordenadas ascendente por fecha,
    fusionando portfolio_daily_snapshot.jsonl y
    market_equities_daily_snapshot.jsonl (un ticker normalmente solo vive
    en uno de los dos, pero se fusiona por si acaso)."""
    by_ticker: dict[str, dict[str, dict]] = defaultdict(dict)  # ticker -> date -> row
    for path in (root / "docs" / "data" / "portfolio_daily_snapshot.jsonl",
                 root / "docs" / "data" / "market_equities_daily_snapshot.jsonl"):
        for r in _load_jsonl(path):
            tk, dt = r.get("ticker"), r.get("date")
            if not tk or not dt:
                continue
            row = {k: r.get(k) for k in _FLOW_FIELDS}
            by_ticker[tk][dt] = row  # última fuente gana si hay colisión real

    out: dict[str, list[dict]] = {}
    for tk, by_date in by_ticker.items():
        out[tk] = [by_date[d] for d in sorted(by_date.keys())]
    return out


# ── Métricas derivadas de la propia serie ───────────────────────────────

def compute_series_metrics(rows_asc: list[dict]) -> list[dict]:
    """Añade a cada fila: delta5 (Flow_t − Flow_{t-DELTA_WINDOW}, en filas
    capturadas, no sesiones de calendario exactas — misma aproximación ya
    aceptada en el resto del proyecto cuando la captura puede tener huecos),
    zero_cross_up/down, flow_above_zero_days, delta5_persist_up,
    delta5_persist_nonneg, days_since_zero_cross_up."""
    flows = [r.get("flowScore") for r in rows_asc]
    out = []
    for i, r in enumerate(rows_asc):
        f = flows[i]
        f_prev = flows[i - 1] if i >= 1 else None
        f_back = flows[i - DELTA_WINDOW] if i >= DELTA_WINDOW else None
        delta5 = round(f - f_back, 3) if (f is not None and f_back is not None) else None
        zero_cross_up = bool(f is not None and f_prev is not None and f_prev <= 0 < f)
        zero_cross_down = bool(f is not None and f_prev is not None and f_prev >= 0 > f)
        out.append({**r, "delta5": delta5, "zero_cross_up": zero_cross_up, "zero_cross_down": zero_cross_down})

    for i in range(len(out)):
        up = 0
        j = i
        while j >= 0 and out[j]["delta5"] is not None and out[j]["delta5"] > 0:
            up += 1
            j -= 1
        out[i]["delta5_persist_up"] = up

        nonneg = 0
        j = i
        while j >= 0 and out[j]["delta5"] is not None and out[j]["delta5"] >= 0:
            nonneg += 1
            j -= 1
        out[i]["delta5_persist_nonneg"] = nonneg

        above = 0
        j = i
        while j >= 0 and out[j].get("flowScore") is not None and out[j]["flowScore"] > 0:
            above += 1
            j -= 1
        out[i]["flow_above_zero_days"] = above

        days_since_cross = None
        for k in range(i, -1, -1):
            if out[k]["zero_cross_up"]:
                days_since_cross = i - k
                break
        out[i]["days_since_zero_cross_up"] = days_since_cross
    return out


def atr_percentile_today(rows_asc: list[dict]) -> float | None:
    """Percentil del ATR% de hoy contra su propia ventana (hasta
    ATR_PCTILE_WINDOW sesiones). None si hay menos de ATR_PCTILE_MIN_ROWS
    disponibles — "sizing reducido", no exclusión (igual que pide la propia
    auditoría para este caso)."""
    vals = [r.get("atrPct") for r in rows_asc[-ATR_PCTILE_WINDOW:] if r.get("atrPct") is not None]
    if len(vals) < ATR_PCTILE_MIN_ROWS:
        return None
    today = vals[-1]
    rank = sum(1 for v in vals if v <= today) / len(vals)
    return round(rank * 100, 1)


# ── Los 3 filtros ────────────────────────────────────────────────────────

def evaluate_inflexion(today: dict, rows_asc: list[dict], atr_pctile: float | None, theme: dict) -> dict:
    flow = today.get("flowScore")
    reasons: list[str] = []
    ok = True
    if flow is None:
        return {"pass": False, "reasons": ["sin dato de Flow"], "sizing_reduced": atr_pctile is None}

    if not (FLOW_MIN <= flow <= FLOW_MAX):
        ok = False
        reasons.append(f"Flow {flow} fuera del rango de inflexión [-5, +8]")

    persist_up = today.get("delta5_persist_up") or 0
    recent_cross = today.get("days_since_zero_cross_up") is not None and today["days_since_zero_cross_up"] <= ZERO_CROSS_RECENCY
    recent_positive = flow is not None and flow > 0 and (today.get("flow_above_zero_days") or 0) <= ZERO_CROSS_RECENCY
    # Relajación deliberada frente a la regla 1 original de la auditoría
    # ("cruza hoy, o ya cruzó hace poco"): verificado contra datos reales
    # (ASM.AS, 2026-09-19/20) que aplicada literal en AND con la regla 2 de
    # persistencia NUNCA se cumple cuando el Flow salta de negativo a muy
    # extendido en una sola sesión, sin pasar nunca por un cruce clásico
    # antes de extenderse — justo el caso que la propia auditoría exige
    # seguir detectando. Si el Flow sigue negativo pero ya lleva la
    # persistencia de ΔFlow que exige la regla 2, cuenta igual: es la
    # situación que describe el propio objetivo de esta sección ("pillar
    # el cambio de estado, no el movimiento ya hecho").
    approaching = flow is not None and flow <= 0 and persist_up >= EARLY_PERSIST_SESSIONS
    if not (recent_cross or recent_positive or approaching):
        ok = False
        reasons.append("sin zero-cross reciente, Flow positivo reciente ni persistencia de ΔFlow hacia cero")

    if persist_up < EARLY_PERSIST_SESSIONS:
        ok = False
        reasons.append(f"ΔFlow no lleva {EARLY_PERSIST_SESSIONS} sesiones consecutivas positivo")

    rsi = today.get("rsi")
    if rsi is None or not (RSI_INFLEXION[0] <= rsi <= RSI_INFLEXION[1]):
        ok = False
        reasons.append(f"RSI {rsi} fuera de 40-58")

    konc = today.get("konc_alignment")
    if konc in KONC_BEARISH:
        ok = False
        reasons.append(f"Koncorde en veto ({konc})")

    if theme.get("blocked"):
        ok = False
        reasons.append("tema con breadth 0 (ningún miembro de la cesta confirma)")

    recent10 = [r.get("flowScore") for r in rows_asc[-FLOW_EXTENDED_LOOKBACK:] if r.get("flowScore") is not None]
    if recent10 and max(recent10) > FLOW_EXTENDED_THRESHOLD:
        ok = False
        reasons.append(f"Flow ya superó {FLOW_EXTENDED_THRESHOLD} en las últimas {FLOW_EXTENDED_LOOKBACK} sesiones (extensión, no inflexión)")

    sizing_reduced = atr_pctile is None
    if atr_pctile is not None and atr_pctile > ATR_PCTILE_BLOCK:
        ok = False
        reasons.append(f"ATR% en percentil {atr_pctile} (>80, extensión)")

    return {"pass": ok, "reasons": reasons, "sizing_reduced": sizing_reduced}


def evaluate_continuacion(today: dict, rows_asc: list[dict], rel_strength: float | None, ticker: str) -> dict:
    flow = today.get("flowScore")
    reasons: list[str] = []
    ok = True

    if flow is None or not (flow > 0):
        ok = False
        reasons.append("Flow no positivo")

    if (today.get("flow_above_zero_days") or 0) < CONTINUACION_MIN_ABOVE_ZERO_DAYS:
        ok = False
        reasons.append(f"Flow no lleva {CONTINUACION_MIN_ABOVE_ZERO_DAYS} sesiones por encima de cero")

    last5 = rows_asc[-5:]
    deltas = [r.get("delta5") for r in last5 if r.get("delta5") is not None]
    nonneg_count = sum(1 for d in deltas if d >= 0)
    if len(deltas) < 3 or nonneg_count < 3:
        ok = False
        reasons.append("ΔFlow no es ≥0 en al menos 3 de las últimas 5 sesiones")

    konc = today.get("konc_alignment")
    if konc != KONC_BULLISH_CONFIRMED:
        ok = False
        reasons.append(f"Koncorde no bullish_aligned ({konc})")

    rsi = today.get("rsi")
    extended = rsi is not None and rsi > RSI_EXTENDED
    if rsi is None or not (RSI_CONTINUACION[0] <= rsi <= RSI_CONTINUACION[1]):
        ok = False
        reasons.append(f"RSI {rsi} fuera de 55-68")

    if rel_strength is None or rel_strength <= 0:
        ok = False
        reasons.append("fuerza relativa 1M no positiva (aproximada: m1 del ticker − m1 de ^GSPC)")

    hist = today.get("macdHist")
    hist_delta = today.get("macdHistDelta1")
    hist_decel = hist_delta is not None and hist_delta < 0
    if hist is None or hist < 0 or hist_decel:
        ok = False
        reasons.append("histograma MACD no confirma (negativo o decelerando)")

    if ticker in LEVERAGED_TICKERS:
        ok = False
        reasons.append("vehículo apalancado — no hereda la etiqueta de continuación del subyacente")

    # MATURE (sección 5 de la auditoría, literal: "ΔFlow negativo 2
    # sesiones seguidas, aunque Flow siga alto" -> MATURE, protección de
    # beneficios en vez de entrada nueva). Encontrado durante la
    # verificación contra ASM.AS real (2026-09-26/29: flow se mantiene
    # ~10.9, claramente positivo, pero ΔFlow-5d cae a negativo 2+ sesiones
    # seguidas tras el pico del 22-23/09 -- consolidación real, no
    # aceleración, exactamente el caso que esta regla describe) -- faltaba
    # en la primera versión de este motor, ok sin más devolvía False sin
    # distinguir "consolidando" de "nunca llegó a confirmar".
    last2_d5 = [r.get("delta5") for r in rows_asc[-2:]]
    delta_flip_high = (
        flow is not None and flow > 0
        and len(last2_d5) == 2 and all(d is not None and d < 0 for d in last2_d5)
    )
    mature = extended or delta_flip_high or (hist_decel and flow is not None and flow > FLOW_EXTENDED_THRESHOLD)
    return {"pass": ok and not mature, "mature": bool(mature), "reasons": reasons}


def evaluate_reversion(today: dict, rows_asc: list[dict]) -> dict:
    reasons: list[str] = []
    ok = True

    window10 = rows_asc[-REVERSION_LOOKBACK:]
    had_deep_negative = any(
        r.get("flowScore") is not None and r["flowScore"] < REVERSION_DEEP_NEGATIVE for r in window10
    )
    if not had_deep_negative:
        ok = False
        reasons.append(f"Flow no estuvo por debajo de {REVERSION_DEEP_NEGATIVE} en las últimas {REVERSION_LOOKBACK} sesiones")

    last3 = rows_asc[-3:]
    deltas = [r.get("delta5") for r in last3]
    if len(last3) < 3 or any(d is None or d <= 0 for d in deltas):
        ok = False
        reasons.append("ΔFlow no es positivo en las 3 últimas sesiones consecutivas")

    prices = [r.get("price") for r in last3]
    if len(prices) == 3 and None not in prices and len(rows_asc) >= 6:
        prior_window = rows_asc[-6:-3]
        prior_prices = [r.get("price") for r in prior_window if r.get("price") is not None]
        if prior_prices and min(prices) < min(prior_prices):
            ok = False
            reasons.append("el precio ha hecho un mínimo nuevo en esas 3 sesiones")

    konc = today.get("konc_alignment")
    if konc in KONC_BEARISH:
        ok = False
        reasons.append(f"Koncorde sigue en veto ({konc})")

    rsi = today.get("rsi")
    if rsi is None or rsi >= RSI_REVERSION_MAX:
        ok = False
        reasons.append(f"RSI {rsi} no está saliendo de sobreventa por debajo de {RSI_REVERSION_MAX}")

    return {"pass": ok, "reasons": reasons}


# ── API de alto nivel ────────────────────────────────────────────────────

def build_context(root: Path = ROOT) -> dict:
    """Precalcula lo que se reutiliza entre tickers: cestas, historial de
    Flow completo, y el m1 de ^GSPC de la fecha más reciente (benchmark de
    fuerza relativa — simplificación: no hay mapeo ticker→benchmark
    sectorial en el proyecto, se usa el índice general)."""
    membership = load_basket_membership(root)
    basket_to_tickers = _basket_to_tickers(membership)
    history = load_flow_history(root)
    benchmark_m1 = None
    gspc_rows = history.get("^GSPC")
    if gspc_rows:
        benchmark_m1 = gspc_rows[-1].get("m1")
    return {
        "membership": membership, "basket_to_tickers": basket_to_tickers,
        "history": history, "benchmark_m1": benchmark_m1,
    }


def evaluate_ticker(ticker: str, ctx: dict) -> dict:
    rows_asc = ctx["history"].get(ticker, [])
    if len(rows_asc) < 6:
        return {"ticker": ticker, "data_status": "insufficient_data"}

    rows_asc = compute_series_metrics(rows_asc)
    today = rows_asc[-1]

    flow_today = {tk: rows[-1]["flowScore"] for tk, rows in ctx["history"].items() if rows and rows[-1].get("flowScore") is not None}
    konc_today = {tk: rows[-1].get("konc_alignment") for tk, rows in ctx["history"].items() if rows}
    theme = compute_theme_breadth(ticker, ctx["membership"], ctx["basket_to_tickers"], flow_today, konc_today)

    atr_pctile = atr_percentile_today(rows_asc)
    rel_strength = None
    if ctx.get("benchmark_m1") is not None and today.get("m1") is not None:
        rel_strength = round(today["m1"] - ctx["benchmark_m1"], 2)

    inflexion = evaluate_inflexion(today, rows_asc, atr_pctile, theme)
    continuacion = evaluate_continuacion(today, rows_asc, rel_strength, ticker)
    reversion = evaluate_reversion(today, rows_asc)

    return {
        "ticker": ticker, "date": today.get("date"), "data_status": "ok",
        "flow": today.get("flowScore"), "delta5": today.get("delta5"),
        "zero_cross_up": today.get("zero_cross_up"), "days_since_zero_cross_up": today.get("days_since_zero_cross_up"),
        "flow_above_zero_days": today.get("flow_above_zero_days"), "rsi": today.get("rsi"),
        "konc_alignment": today.get("konc_alignment"), "atr_pctile": atr_pctile, "rel_strength_1m": rel_strength,
        "theme": theme, "inflexion": inflexion, "continuacion": continuacion, "reversion": reversion,
    }


def evaluate_universe(tickers: list[str], root: Path = ROOT) -> dict[str, dict]:
    ctx = build_context(root)
    return {tk: evaluate_ticker(tk, ctx) for tk in tickers}


if __name__ == "__main__":
    import sys
    ctx = build_context()
    tickers = sys.argv[1:] or sorted(ctx["history"].keys())
    for tk in tickers:
        r = evaluate_ticker(tk, ctx)
        if r.get("data_status") != "ok":
            continue
        tags = []
        if r["inflexion"]["pass"]:
            tags.append("INFLEXION")
        if r["continuacion"]["pass"]:
            tags.append("CONTINUACION")
        if r["continuacion"].get("mature"):
            tags.append("MATURE")
        if r["reversion"]["pass"]:
            tags.append("REVERSION")
        if tags:
            print(f"{r['ticker']:10s} flow={r['flow']:>7.1f} d5={r['delta5']}  "
                  f"konc={r['konc_alignment']}  tema={r['theme'].get('baskets')}  -> {', '.join(tags)}")
