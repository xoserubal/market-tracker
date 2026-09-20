"""
Market Analysis LLM — captura automatizada del análisis diario que el
usuario venía pidiendo manualmente en ChatGPT ("Sol", GPT-5.6) sobre los
snapshots de Market Tracker + Portfolio Tracker.

Fase 2 de la idea "automatizar el análisis para poder evaluar su
fiabilidad con el tiempo" (2026-09-13/14) — la Fase 1 (captura server-side
de los datos) ya estaba resuelta por market_daily_snapshot.js/
portfolio_daily_snapshot.js. Este script cierra el círculo: construye el
payload exacto que el usuario pegaba a mano, llama al modelo, y persiste
tanto la prosa como un bloque JSON estructurado para poder comprobar más
adelante si los TRIGGER/INVALIDATION de cada señal se cumplieron.

Decisiones de diseño (confirmadas con el usuario 2026-09-14):
  - Modelo: openai/gpt-5.6-sol vía OpenRouter (reutiliza OPENROUTER_API_KEY
    ya existente — sin credencial nueva), reasoning_effort="high"
    ("alto" tal como lo usaba el usuario en ChatGPT).
  - Cadencia: 1x/día, en el run de la tarde (una vez que el snapshot del
    día ya está completo).
  - Salida: prosa libre (fiel al prompt original, wiki/PROMPT_MARKET_ANALYST_SOL.md)
    + un bloque JSON al final con las señales estructuradas (SIGNAL/
    INTERPRETATION/ACTION/TRIGGER/INVALIDATION + GRADOS DE CONVICCIÓN que
    el propio prompt ya pide) — sin esto, evaluar fiabilidad más adelante
    significaría releer prosa a mano.

El system prompt (wiki/PROMPT_MARKET_ANALYST_SOL.md) es EXACTAMENTE el que
pegó el usuario, sin modificar — el addendum de formato de salida vive
aquí, no en ese archivo, para que quede claro qué es "el prompt original"
y qué es "requisito operativo añadido para poder automatizarlo".

Revisión 2026-09-21 (recorte de una propuesta externa de 19 secciones —
"registro persistente de hipótesis con IDs/estados/MFE-MAE" completo — a un
primer paso barato, mismo criterio de observar-antes-de-construir del resto
del proyecto): en vez de un backend de hipótesis con máquina de estados,
`build_recent_analysis_digest()` simplemente le pasa a Sol sus propias
señales estructuradas de los últimos RECENT_ANALYSIS_DAYS días y le pide
explícitamente que las revise antes de escribir. Sin esto, cada llamada era
una API call sin estado con memoria cero de lo que ya había dicho. Si tras
unas semanas la continuidad narrativa sigue siendo mala aun con esto, se
justificará el registro persistente de la propuesta original — no antes.
También se excluye `KNOWN_BAD_TICKERS` (FXPO.L, anomalía de escala
GBX/GBp confirmada) y se aclaró en el addendum que Portfolio Tracker es
watchlist, no posiciones reales verificadas — dos riesgos concretos que la
propuesta señalaba con precedente real en este mismo repo.

Reutiliza call_model()/compute_cost()/MODEL_PRICING de paper_trading.py
(mismo criterio de reuso que mirror_portfolio.py/cava_portfolio.py) —
call_model() ganó un parámetro opcional `reasoning_effort` para esto, sin
cambiar el comportamiento de ningún llamador existente.

Uso — a diferencia de mirror_portfolio.py/cava_portfolio.py (donde el modo
por defecto es dry-run pero basta con omitir la flag para no gastar), AQUÍ
el modo por defecto SIN flags es dry-run — hace falta pasar --apply
explícitamente para gastar crédito real. Deliberado: es integración nueva
con un modelo/proveedor que el pipeline nunca ha llamado, con coste por
llamada no trivial (persona larga + reasoning_effort=high) — mejor pecar
de explícito aquí que en el resto de scripts de picks, que ya llevan meses
en producción.
    py -3 scripts/market_analysis_llm.py             # dry-run (construye el payload, no llama a la API)
    py -3 scripts/market_analysis_llm.py --apply     # llama de verdad (gasta credito de OpenRouter)
    py -3 scripts/market_analysis_llm.py --apply --force  # salta la comprobacion de mercado abierto (ver _is_market_open_day)
    py -3 scripts/market_analysis_llm.py --report    # resume el jsonl existente
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Emojis/acentos rompen print() en consola Windows (cp1252) — mismo
# incidente ya documentado y arreglado en duration_monitor.py/
# check_koncorde_alerts.py. GitHub Actions ya es UTF-8, esto solo importa
# para pruebas locales.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
WIKI = ROOT / "wiki"

MARKET_EQUITIES = DATA / "market_equities_daily_snapshot.jsonl"
MARKET_MACRO    = DATA / "market_macro_daily_snapshot.jsonl"
PORTFOLIO_SNAP  = DATA / "portfolio_daily_snapshot.jsonl"
PORTFOLIO_JSON  = ROOT / "portfolio.json"
PROMPT_PATH     = WIKI / "PROMPT_MARKET_ANALYST_SOL.md"
OUT_PATH        = DATA / "market_analysis_llm.jsonl"

sys.path.insert(0, str(Path(__file__).parent))
from paper_trading import call_model, compute_cost  # reuso, ver docstring

MODEL = "openai/gpt-5.6-sol"
REASONING_EFFORT = "high"
MAX_TOKENS = 24000  # persona larga + reasoning_effort=high consumen mucho antes de
# llegar a la prosa visible -- verificado en vivo 2026-09-13: con 8000 se
# cortaba a mitad del bloque ```json final (13743 chars de prosa completa,
# JSON sin cerrar). Con margen amplio, peor caso ~$0.24/llamada ($10/M out).

# Tickers con anomalía de escala confirmada (bug GBX/GBp de Yahoo -- el
# mismo ya documentado en CLAUDE.md para el backtest de Cruce Rojo D:
# persistente desde 2026-05-18, nunca revertido, confirmado de nuevo aquí
# el 2026-09-21 -- m1/m3/fromLow de FXPO.L en portfolio_daily_snapshot.jsonl
# leen +9000% de forma sostenida). Se excluyen SOLO de lo que le llega a
# Sol, no de la captura server-side (market_daily_snapshot.js/
# portfolio_daily_snapshot.js) -- esos ficheros los consumen otros
# dashboards con su propio criterio de visualización, y tocar la captura
# habría sido un cambio de alcance mayor que el acordado.
KNOWN_BAD_TICKERS = {"FXPO.L"}

# Cuántos análisis previos (días naturales con captura, no sesiones NYSE)
# se le pasan a Sol como memoria explícita antes del snapshot de hoy.
RECENT_ANALYSIS_DAYS = 3

OUTPUT_FORMAT_ADDENDUM = """

---

# ADENDA OPERATIVA — FORMATO DE SALIDA (no forma parte del prompt original del usuario)

Esta llamada es automatizada (sin memoria de conversación) — el mensaje del
usuario incluye el snapshot de HOY, una tabla de deltas contra el día
anterior, y una sección "ANÁLISIS ANTERIORES" con tus propias señales
estructuradas de los últimos días. Revisa siempre esa sección antes de
escribir: para cada señal previa que siga siendo relevante, di
explícitamente si se ha fortalecido, debilitado, confirmado o invalidado.
No la sustituyas en silencio por una oportunidad nueva sin comentar qué
pasó con la anterior.

IMPORTANTE sobre "cartera": los tickers de la sección PORTFOLIO TRACKER son
una watchlist curada por el usuario, NO posiciones reales verificadas — hoy
por hoy `portfolio.json` no registra unidades ni coste real en ningún
ticker. No afirmes que el usuario tiene comprado un ticker concreto, no des
instrucciones de venta de una cantidad o peso específico, y no asumas que
está en liquidez total solo porque no haya datos de posición. Usa lenguaje
condicional ("si tienes posición en X...") para cualquier recomendación de
gestión de cartera real.

Después de tu análisis completo en prosa (sigue todas las instrucciones del
ROL/PRINCIPIO CENTRAL/etc. de arriba, en español, con la estructura
SIGNAL/INTERPRETATION/ACTION/TRIGGER/INVALIDATION donde corresponda),
termina tu respuesta con UN bloque ```json que contenga un resumen
estructurado de las señales que hayas identificado, con este esquema
exacto:

```json
{
  "market_regime": {
    "label": "risk-on expansion|late bull|late-cycle rotation|stagflationary squeeze|correction|risk-off|systemic stress",
    "confidence_pct": 45,
    "rationale": "una frase"
  },
  "signals": [
    {
      "subject": "ticker o par relativo o tema",
      "event_type": "libre, usa el vocabulario de ALPHA INFLECTION RADAR si aplica, o describe el tipo de evento",
      "conviction": "WATCH|EARLY|CONFIRMED|MATURE|EXTENDED|DISTRIBUTION|INVALIDATED",
      "signal": "qué se observa",
      "interpretation": "qué podría significar",
      "action": "qué harías",
      "trigger": "qué confirmaría/aumentaría convicción",
      "invalidation": "qué invalidaría la tesis",
      "confidence_pct": 45
    }
  ]
}
```

Incluye en `signals` solo las ideas con contenido real de esta sesión (no
rellenes con entradas vacías). Si no hay ninguna señal con convicción por
encima de WATCH, es válido devolver un array corto o vacío — no inventes
señales para rellenar el formato.
"""


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _today() -> str:
    # UTC explicito, no date.today() local -- mismo calendario que usan
    # market_daily_snapshot.js/portfolio_daily_snapshot.js (toISOString(),
    # siempre UTC) y que usa el runner de GitHub Actions. Necesario para no
    # desincronizar "hoy" al probar en local en una zona horaria distinta
    # de UTC (verificado: este mismo dia, local=2026-09-14, UTC=2026-09-13).
    return datetime.now(timezone.utc).date().isoformat()


def _prev_date(dates: set[str], today: str) -> str | None:
    earlier = sorted(d for d in dates if d < today)
    return earlier[-1] if earlier else None


# Índice de referencia para detectar si hubo sesión de mercado nueva —
# no un ETF (evita ruido de dividendos/roll de contrato).
MARKET_OPEN_BENCHMARK = "^GSPC"


def _is_market_open_day(today: str, existing: list[dict]) -> tuple[bool, str]:
    """Comprueba si hoy hubo mercado abierto, SIN calendario de festivos
    hardcodeado (evita mantenimiento y el sesgo de solo cubrir festivos de
    EE.UU.) — descubierto 2026-09-21: 3 de los 8 análisis ya generados
    corrieron en fin de semana (2026-09-13 domingo, 2026-09-19 sábado,
    2026-09-20 domingo), gastando ~$0.35 en analizar datos ya vistos el
    día anterior, porque el script nunca comprobaba el día de la semana.

    Dos filtros, en orden de coste creciente:
    1. Fin de semana (UTC) — barato, cubre la inmensa mayoría de los días
       sin mercado sin tocar ningún fichero.
    2. Si no es fin de semana: ¿avanzó el `asOf` (fecha de la última vela
       real, ya capturado por market_daily_snapshot.js en
       market_equities_daily_snapshot.jsonl) desde el último análisis ya
       registrado? Si sigue siendo la misma sesión que la última vez,
       no hay nada nuevo que analizar — probable festivo. Este segundo
       filtro es el que cubre festivos sin necesitar un calendario propio
       que mantener (ni asume solo festivos de EE.UU.)."""
    dow = datetime.now(timezone.utc).weekday()
    if dow >= 5:
        return False, f"fin de semana (UTC weekday={dow})"

    rows = _load_jsonl(MARKET_EQUITIES)
    today_row = next((r for r in rows if r.get("ticker") == MARKET_OPEN_BENCHMARK and r.get("date") == today), None)
    if today_row is None or not today_row.get("asOf"):
        # Sin dato de referencia todavía (p. ej. Step 9g2 no ha corrido hoy) —
        # no bloquea, se deja pasar en vez de fallar a ciegas.
        return True, "sin dato de referencia para comprobar sesión nueva, se permite"

    if not existing:
        return True, "primer análisis, sin historial previo contra el que comparar"
    last_analysis = max(existing, key=lambda r: r["date"])
    last_row = next((r for r in rows if r.get("ticker") == MARKET_OPEN_BENCHMARK and r.get("date") == last_analysis["date"]), None)
    if last_row is None or not last_row.get("asOf"):
        return True, "sin dato de referencia del último análisis, se permite"

    today_as_of, last_as_of = today_row["asOf"][:10], last_row["asOf"][:10]
    if today_as_of == last_as_of:
        return False, (f"sin sesión nueva desde el último análisis ({last_analysis['date']}): "
                        f"{MARKET_OPEN_BENCHMARK} sigue en la vela del {today_as_of} — probable festivo")
    return True, f"sesión nueva detectada: {MARKET_OPEN_BENCHMARK} avanzó de {last_as_of} a {today_as_of}"


def _fmt(v, suffix: str = "", none: str = "—") -> str:
    if v is None:
        return none
    if isinstance(v, float):
        return f"{v:+.1f}{suffix}" if suffix else f"{v:.2f}"
    return f"{v}{suffix}"


def _delta(cur, prev):
    if cur is None or prev is None:
        return None
    return round(cur - prev, 2)


def build_macro_table(today: str, prev: str | None) -> str:
    rows = _load_jsonl(MARKET_MACRO)
    today_rows = {r["id"]: r for r in rows if r["date"] == today}
    prev_rows  = {r["id"]: r for r in rows if prev and r["date"] == prev} if prev else {}
    if not today_rows:
        return "_(sin datos macro capturados hoy)_\n"

    lines = ["| Indicador | Valor | Δ 1S | Δ 1M | Lectura | Lectura ayer |",
             "|---|---:|---:|---:|---|---|"]
    for item_id, r in today_rows.items():
        p = prev_rows.get(item_id)
        reading_prev = p.get("reading") if p else None
        changed = " ← CAMBIO" if (reading_prev and reading_prev != r.get("reading")) else ""
        lines.append(
            f"| {r['name']} | {_fmt(r.get('value'))} | {_fmt(r.get('delta_1w'))} | "
            f"{_fmt(r.get('delta_1m'))} | {r.get('reading') or '—'} | {(reading_prev or '—') + changed} |"
        )
    return "\n".join(lines) + "\n"


def build_equities_table(today: str, prev: str | None) -> str:
    rows = _load_jsonl(MARKET_EQUITIES)
    today_rows = [r for r in rows if r["date"] == today and r["ticker"] not in KNOWN_BAD_TICKERS]
    prev_by_ticker = {r["ticker"]: r for r in rows if prev and r["date"] == prev} if prev else {}
    if not today_rows:
        return "_(sin datos de mercado capturados hoy)_\n"

    by_section: dict[str, list[dict]] = {}
    for r in today_rows:
        for sec in (r.get("sections") or ["(sin sección)"]):
            by_section.setdefault(sec, []).append(r)

    out = []
    for sec, sec_rows in by_section.items():
        out.append(f"### {sec}")
        out.append("| Ticker | Precio | 1D | 1W | 1M | 3M | RSI | MACD | ATR% | Konc | Flow | ΔFlow1d | Early | ΔEarly1d |")
        out.append("|---|---:|---:|---:|---:|---:|---:|:---:|---:|---|---:|---:|---:|---:|")
        for r in sec_rows:
            p = prev_by_ticker.get(r["ticker"])
            dflow  = _delta(r.get("flowScore"), p.get("flowScore") if p else None)
            dearly = _delta(r.get("earlyFlow"), p.get("earlyFlow") if p else None)
            macd = "—" if r.get("macdBull") is None else ("▲" if r["macdBull"] else "▼")
            out.append(
                f"| {r['ticker']} | {_fmt(r.get('price'))} | {_fmt(r.get('d1'),'%')} | {_fmt(r.get('w1'),'%')} | "
                f"{_fmt(r.get('m1'),'%')} | {_fmt(r.get('m3'),'%')} | {_fmt(r.get('rsi'))} | {macd} | "
                f"{_fmt(r.get('atrPct'),'%')} | {r.get('konc_alignment') or '—'} | {_fmt(r.get('flowScore'))} | "
                f"{_fmt(dflow)} | {_fmt(r.get('earlyFlow'))} | {_fmt(dearly)} |"
            )
        out.append("")
    return "\n".join(out)


def build_portfolio_table(today: str, prev: str | None) -> str:
    rows = _load_jsonl(PORTFOLIO_SNAP)
    today_rows = {r["ticker"]: r for r in rows if r["date"] == today and r["ticker"] not in KNOWN_BAD_TICKERS}
    prev_by_ticker = {r["ticker"]: r for r in rows if prev and r["date"] == prev} if prev else {}
    if not today_rows:
        return "_(sin datos de Portfolio Tracker capturados hoy)_\n"

    sections: dict[str, list[str]] = {}
    try:
        pf = json.loads(PORTFOLIO_JSON.read_text(encoding="utf-8"))
        for sec in pf.get("sections", []):
            for item in sec.get("items", []):
                tk = item.get("ticker")
                if tk:
                    sections.setdefault(sec.get("name", "?"), []).append(tk)
    except Exception:
        sections = {"Portfolio": list(today_rows.keys())}

    out = []
    for sec_name, tickers in sections.items():
        present = [t for t in tickers if t in today_rows]
        if not present:
            continue
        out.append(f"### {sec_name}")
        out.append("| Ticker | Precio | 1D | 1W | 1M | 3M | RSI | MACD | ATR% | Konc | Flow | ΔFlow1d | Early | ΔEarly1d |")
        out.append("|---|---:|---:|---:|---:|---:|---:|:---:|---:|---|---:|---:|---:|---:|")
        for tk in present:
            r = today_rows[tk]
            p = prev_by_ticker.get(tk)
            dflow  = _delta(r.get("flowScore"), p.get("flowScore") if p else None)
            dearly = _delta(r.get("earlyFlow"), p.get("earlyFlow") if p else None)
            macd = "—" if r.get("macdBull") is None else ("▲" if r["macdBull"] else "▼")
            out.append(
                f"| {tk} | {_fmt(r.get('price'))} | {_fmt(r.get('d1'),'%')} | {_fmt(r.get('w1'),'%')} | "
                f"{_fmt(r.get('m1'),'%')} | {_fmt(r.get('m3'),'%')} | {_fmt(r.get('rsi'))} | {macd} | "
                f"{_fmt(r.get('atrPct'),'%')} | {r.get('konc_alignment') or '—'} | {_fmt(r.get('flowScore'))} | "
                f"{_fmt(dflow)} | {_fmt(r.get('earlyFlow'))} | {_fmt(dearly)} |"
            )
        out.append("")
    return "\n".join(out)


def build_recent_analysis_digest(today: str, n: int = RECENT_ANALYSIS_DAYS) -> str:
    """Memoria explícita de los últimos `n` análisis ya guardados (fecha <
    hoy), como pide el punto acordado con el usuario 2026-09-21: cada
    llamada a Sol es una API call sin estado, así que sin esto el modelo no
    tiene forma de saber qué dijo ayer o antier salvo lo que se le repita
    aquí. Deliberadamente NO es el registro persistente de hipótesis con
    IDs/estados de la propuesta original del usuario (§2/§16) -- eso se
    dejó para más adelante, cuando haya semanas de histórico que digan si
    hace falta. Esto es solo pasarle a Sol su propia salida estructurada de
    los últimos días y pedirle que la revise antes de escribir hoy.

    Solo se incluyen los campos estructurados (subject/conviction/signal/
    trigger/invalidation), no la prosa completa (~10-14k caracteres por
    día) -- inflaría el payload sin aportar nada que Sol no haya resumido
    ya él mismo en el JSON."""
    rows = [r for r in _load_jsonl(OUT_PATH) if r["date"] < today]
    if not rows:
        return ""
    rows.sort(key=lambda r: r["date"])
    recent = rows[-n:]

    out = ["## ANÁLISIS ANTERIORES — revisa esto ANTES de escribir el de hoy\n",
           "Estas son tus propias señales de los últimos días. Para cada una que "
           "siga siendo relevante, di explícitamente si se ha fortalecido, "
           "debilitado o invalidado antes de introducir temas nuevos -- no la "
           "sustituyas en silencio por otra oportunidad distinta.\n"]
    for r in recent:
        structured = r.get("structured")
        out.append(f"### {r['date']}")
        if not structured:
            prose_excerpt = (r.get("prose") or "")[:400]
            out.append(f"_(sin JSON estructurado ese día -- extracto de la prosa)_\n{prose_excerpt}...\n")
            continue
        regime = structured.get("market_regime") or {}
        out.append(f"Régimen: **{regime.get('label', '—')}** — {regime.get('rationale', '')}\n")
        signals = structured.get("signals") or []
        if not signals:
            out.append("_(sin señales con contenido registradas ese día)_\n")
            continue
        out.append("| Subject | Convicción | Signal | Trigger | Invalidation |")
        out.append("|---|---|---|---|---|")
        for s in signals:
            out.append(
                f"| {s.get('subject', '—')} | {s.get('conviction', '—')} | "
                f"{(s.get('signal') or '—')[:120]} | {(s.get('trigger') or '—')[:120]} | "
                f"{(s.get('invalidation') or '—')[:120]} |"
            )
        out.append("")
    return "\n".join(out)


def build_user_message(today: str) -> tuple[str, str | None]:
    macro_dates = {r["date"] for r in _load_jsonl(MARKET_MACRO)}
    prev = _prev_date(macro_dates, today)

    msg = f"# SNAPSHOT — {today}\n"
    if prev:
        msg += f"_(comparando contra el snapshot de {prev} — el más reciente disponible antes de hoy)_\n"
    else:
        msg += "_(no hay snapshot previo todavia — primera captura, sin deltas)_\n"
    digest = build_recent_analysis_digest(today)
    if digest:
        msg += "\n" + digest
    msg += "\n## MACRO / CICLO\n" + build_macro_table(today, prev)
    msg += "\n## MERCADOS (Market Tracker)\n" + build_equities_table(today, prev)
    msg += "\n## PORTFOLIO TRACKER\n" + build_portfolio_table(today, prev)
    return msg, prev


def extract_json_block(text: str) -> dict | None:
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def run(dry_run: bool, force: bool = False) -> int:
    today = _today()
    existing = _load_jsonl(OUT_PATH)
    if any(r["date"] == today for r in existing):
        print(f"Ya hay un análisis registrado para hoy ({today}) — nada que hacer (dedup).")
        return 0

    market_open, reason = _is_market_open_day(today, existing)
    if not market_open and not force:
        print(f"Mercado cerrado hoy ({today}) — {reason}. No se llama al LLM (usa --force para saltarte esto).")
        return 0
    print(f"Comprobación de mercado abierto: {reason}" + (" (ignorada por --force)" if not market_open and force else ""))

    if not PROMPT_PATH.exists():
        print(f"Falta {PROMPT_PATH}")
        return 1
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8") + OUTPUT_FORMAT_ADDENDUM

    user_message, prev_date = build_user_message(today)
    print(f"Payload construido: {len(system_prompt)} chars system, {len(user_message)} chars user, prev_date={prev_date}")

    if dry_run:
        print("\n--- system prompt (primeras 500 chars) ---")
        print(system_prompt[:500])
        print("\n--- user message completo ---")
        print(user_message)
        print("\n--dry-run: no se ha llamado a la API.")
        return 0

    raw, in_tok, out_tok, latency_ms = call_model(
        MODEL, system_prompt, user_message, max_tokens=MAX_TOKENS, reasoning_effort=REASONING_EFFORT,
    )
    cost = compute_cost(MODEL, in_tok, out_tok)
    structured = extract_json_block(raw)
    prose = re.sub(r"```json\s*\{[\s\S]*?\}\s*```", "", raw).strip()

    row = {
        "date": today, "prev_date": prev_date, "model": MODEL, "reasoning_effort": REASONING_EFFORT,
        "input_tokens": in_tok, "output_tokens": out_tok, "cost_usd": round(cost, 4),
        "latency_ms": round(latency_ms), "prose": prose, "structured": structured,
        "structured_parse_ok": structured is not None,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Análisis guardado — {in_tok} in / {out_tok} out tokens, ${cost:.4f}, "
          f"{latency_ms:.0f}ms, JSON estructurado: {'OK' if structured else 'FALLO'}")
    if not structured:
        print("  ADVERTENCIA: no se pudo extraer el bloque JSON — revisar prose manualmente.")
    return 0


def print_report():
    rows = _load_jsonl(OUT_PATH)
    if not rows:
        print("Sin análisis todavía en", OUT_PATH)
        return
    total_cost = sum(r.get("cost_usd", 0) for r in rows)
    ok_json = sum(1 for r in rows if r.get("structured_parse_ok"))
    print(f"market_analysis_llm.jsonl — {len(rows)} análisis, {rows[0]['date']} -> {rows[-1]['date']}")
    print(f"  coste total: ${total_cost:.2f}  |  JSON estructurado OK: {ok_json}/{len(rows)}")
    for r in rows[-5:]:
        n_signals = len(r.get("structured", {}).get("signals", [])) if r.get("structured") else "?"
        regime = r.get("structured", {}).get("market_regime", {}).get("label") if r.get("structured") else "?"
        print(f"  {r['date']}: régimen={regime}, {n_signals} señales, ${r.get('cost_usd', 0):.4f}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        print_report()
    else:
        sys.exit(run(dry_run="--apply" not in sys.argv, force="--force" in sys.argv))
