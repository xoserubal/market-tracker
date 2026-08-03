"""
cava_portfolio.py — cartera CAVA_MACRO, gobernada por la capa determinista de
Cava AI. Contexto completo en wiki/AGENTE_EXTERNO_*.md.

QUÉ DECIDE CADA PARTE
---------------------
    Cava    →  CUÁNTO riesgo (exposición): deterministic_risk_posture
    Cava    →  QUÉ TEMAS son elegibles: favor/avoid_categories
    PCS     →  QUÉ TICKER concreto dentro de lo elegible
    Mecánico → CUÁNDO salir (Cava no opina por ticker; ver review_positions)

Cava **sustituye** al MacroScore en esta cartera, no se mezcla con él: mezclar
las dos lecturas macro haría inatribuible cualquier resultado. Las otras seis
carteras siguen exactamente igual.

POR QUÉ `risk_off` NO CIERRA POSICIONES
---------------------------------------
La Prueba 1C (5.408 sesiones, 2005-2026) midió esto con datos reales:

    postura      n     fwd 3m   peor 1m   vol 1m
    risk_on   2177      2.24%    -2.19%   12.20%
    risk_off   852      2.40%    -4.65%   26.63%

`risk_off` marca el doble de volatilidad y el doble de caída posterior — es un
buen detector de peligro. Pero el retorno posterior es **mejor** que el de
`risk_on`, porque los suelos rebotan con fuerza. Vender en `risk_off` sería
justo el error que los datos desaconsejan.

Por eso `risk_off` significa "no añadir riesgo aquí", no "salir corriendo".

POR QUÉ LA SEÑAL SE USA BINARIA (`risk_off` sí, el resto no)
-------------------------------------------------------------
El análisis de la alarma sobre esas mismas sesiones:

    alarma                          suena  captura  acierta
    Cava risk_off                     16%      34%      34%
    Cava risk_off + reduce_risk       49%      60%      20%
    Nuestro Risk-OFF + Transición     39%      61%      25%

Con la alarma estricta Cava bate claramente a nuestro MacroScore (34 % de
aciertos frente a 23 %, sobre una tasa base del 16 %). Pero al sumarle
`reduce_risk` el conjunto pasa a ser **peor** que nuestro propio régimen: suena
el 49 % del tiempo para capturar lo mismo.

Todo el valor está concentrado en el nivel máximo de alarma. Por eso la postura
se aplica de forma binaria y `reduce_risk` no recorta nada — el detalle y los
números están en el comentario de MAX_POSITIONS_BY_POSTURE.

MEDICIÓN
--------
Cada pick se registra en `shadow_picks.jsonl` **desde el primer día**. No es un
detalle administrativo: la cartera MIRROR_ESPEJO lleva 11 posiciones operadas y
cero rendimiento medido por habérselo saltado. Sin esa fila, `update_performance`
no rellena los `ret_*` y la cartera es infalsable.

Se guarda además el peso equiponderado junto al real, para poder comparar contra
las baselines (que son equiponderadas) sin discusión posterior.

USO
---
    py -3 scripts/cava_portfolio.py            # dry-run: enseña qué haría
    py -3 scripts/cava_portfolio.py --apply    # escribe ai_picks.json y shadow_picks
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from cava_mapping import (  # noqa: E402
    THEME_TO_CAVA_CATEGORY, apply_regime_guidance, build_market_state,
    validate_categories,
)
from cava_state_history import macro_inputs_at  # noqa: E402

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
CANDIDATES = DATA / "ai_candidates.json"
PICKS = DATA / "ai_picks.json"
SHADOW_LOG = DATA / "shadow_picks.jsonl"
RUN_LOG = DATA / "cava_portfolio_log.jsonl"

PORTFOLIO_NAME = "CAVA_MACRO"

# Traducción de postura a exposición. Deliberadamente mecánica: su equipo
# señaló (Ronda 3) que si este paso exigiera interpretación humana, la medición
# reflejaría nuestra traducción tanto como la calidad de Cava.
#
# ES BINARIA A PROPÓSITO, no una escalera de cuatro niveles. Medido sobre las
# 5.345 sesiones de la Prueba 1C con dato de futuro completo:
#
#   postura       %tiempo  caída media  mediana  % meses malos    vol   fwd 3m
#   risk_on           40%       -2.20%   -1.33%           12%   12.1%    2.24%
#   reduce_risk       34%       -2.29%   -1.19%           13%   14.2%    3.09%
#   neutral           11%       -2.63%   -1.80%           17%   17.1%    5.96%
#   risk_off          16%       -4.65%   -3.10%           34%   26.6%    2.40%
#
# Dos cosas se ven ahí y ninguna se ve leyendo los nombres de los estados:
#
# 1. `reduce_risk` NO es más peligroso que `risk_on`: 13 % de meses malos frente
#    a 12 %, y su caída mediana es incluso menor. Pero rinde bastante más
#    (3,09 % frente a 2,24 %). Recortar exposición ahí —un tercio del tiempo—
#    costaría retorno sin evitar riesgo. Por eso no recorta.
# 2. El orden de las etiquetas no sigue al riesgo: `neutral` es MÁS peligroso
#    que `reduce_risk` (17 % de meses malos frente a 13 %). Construir una
#    escalera sobre esas etiquetas sería levantar lógica sobre distinciones que
#    los datos no sostienen.
#
# Lo único que separa de verdad es `risk_off`: 34 % de meses malos, casi el
# triple que el resto y el doble de volatilidad. Ahí sí se corta.
MAX_POSITIONS_BY_POSTURE = {
    "risk_on":     10,   # límite superior que ellos mismos fijaron (B5: 8-10)
    "neutral":     10,
    "reduce_risk": 10,
    "risk_off":     0,   # cero entradas nuevas; las abiertas NO se tocan
}
MAX_PER_THEME = 3        # límite de concentración que fijaron en B5
# Tope adicional por categoría de Cava: dos temas nuestros pueden ser una sola
# categoría suya (sanidad), así que sin esto el tope por tema no la contiene.
MAX_PER_CATEGORY = 4
PCS_MIN_ENTRY = 62.0     # suelo absoluto del sistema, igual que el resto de carteras

# Tamaño por convicción, derivada del PCS: Cava no emite convicción por ticker
# (su lectura es de régimen, no de activo), así que la gradación la pone el PCS.
def size_for(pcs: float | None) -> float:
    if pcs is None:
        return 4.0
    if pcs >= 80:
        return 8.0
    if pcs >= 70:
        return 6.0
    return 4.0


def _load(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _append_jsonl(p: Path, rec: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def query_cava(when: str) -> dict:
    """Una sola consulta al motor con el estado macro del día. El régimen es
    global (confirmado por su equipo en P4), así que no se consulta por ticker."""
    from cava_engine import __version__, load_corpus, query_tree

    flat = build_market_state(macro_inputs_at(when))
    inputs: dict[str, dict] = {}
    spx = {k: flat[k] for k in ("price_state", "trend_state", "sentiment_state")
           if k in flat}
    ns = flat.get("narrative_state")
    if ns and ns != ["none"]:
        spx["narrative_state"] = ns
    if spx:
        inputs["SPX"] = spx
    if "volatility_state" in flat:
        inputs["VIX"] = {"volatility_state": flat["volatility_state"]}
    if "credit_state" in flat:
        inputs["HYG"] = {"credit_state": flat["credit_state"]}
    if "liquidity_state" in flat:
        inputs["LIQUIDITY_GLOBAL"] = {"liquidity_state": flat["liquidity_state"]}

    tree, index, timeline, meta = load_corpus("pilot_incremental")
    res = query_tree(tree, index, timeline, {"inputs": inputs}, corpus_meta=meta)

    sl = res.get("structural_logic", {})
    rg = res.get("regime_guidance", {})
    favor = [c for c in (rg.get("favor_categories") or []) if isinstance(c, str)]
    avoid = [c for c in (rg.get("avoid_categories") or []) if isinstance(c, str)]
    # Contrato duro: una categoría fuera de las 15 acordadas debe fallar de
    # forma ruidosa, nunca caer en silencio dejando un tema sin guía.
    validate_categories(favor)
    validate_categories(avoid)

    return {
        "state":         flat,
        "posture":       sl.get("deterministic_risk_posture", "neutral"),
        "L1":            sl.get("L1_primary_trend"),
        "L2":            sl.get("L2_confirmation"),
        "L3":            sl.get("L3_context"),
        "rule":          sl.get("applied_rule"),
        "favor":         favor,
        "avoid":         avoid,
        "corpus_health": res.get("corpus_health", {}),
        "agent_version": __version__,
        "corpus_meta":   meta,
    }


TRAILING_STOP_PCT = 0.25   # ver docstring de review_positions()


def fetch_last_closes(tickers: list[str]) -> dict[str, float]:
    """Último cierre por ticker. Best-effort: un fallo individual no debe
    impedir revisar el resto de la cartera."""
    if not tickers:
        return {}
    import yfinance as yf
    out: dict[str, float] = {}
    try:
        raw = yf.download(tickers, period="5d", auto_adjust=True,
                          progress=False, group_by="ticker")
    except Exception as e:
        print(f"  ⚠ no se pudieron descargar precios: {e}")
        return out
    for tk in tickers:
        try:
            s = raw[tk]["Close"].dropna()
            if len(s):
                out[tk] = float(s.iloc[-1])
        except Exception:
            continue
    return out


def review_positions(ptf: dict, cands: list[dict], today: str) -> list[dict]:
    """Salidas mecánicas. Cava no opina por ticker —su lectura es de régimen—
    así que las salidas no pueden venir de él.

    Se reutilizan los criterios que ya usa el resto del sistema (ver CLAUDE.md,
    "Cierre de posiciones") en vez de inventar otros nuevos:

      · `left_universe`  el ticker salió de ai_candidates.json y deja de poder
                         vigilarse — salida obligatoria
      · `pcs < 62`       suelo absoluto del sistema, el mismo que para entrar
      · `rot_score <= 2` el flujo del tema se ha agotado

    Más una red de seguridad propia: un trailing stop del 25 % desde el máximo
    de cierre alcanzado. Es un **cortacircuitos, no una regla de trading**: está
    ahí para que una posición no pueda irse a cero sin que nadie se entere, no
    para hacer timing. Por eso es ancho — nuestro universo son small caps con
    ATR diario de varios puntos, y un stop estrecho saltaría por ruido. Si
    resulta que salta a menudo, el dato estará en el log y habrá que revisarlo.
    """
    positions = ptf.get("positions", [])
    if not positions:
        return []

    by_ticker = {c["ticker"]: c for c in cands}
    closes = fetch_last_closes([p["ticker"] for p in positions])

    cerradas, siguen = [], []
    for pos in positions:
        tk = pos["ticker"]
        cur = by_ticker.get(tk)
        price = closes.get(tk)

        if price is not None:
            hwm = max(pos.get("high_water_mark") or pos.get("entry_price") or price, price)
            pos["high_water_mark"] = hwm
            if pos.get("entry_price") is None:
                pos["entry_price"] = price
        else:
            hwm = pos.get("high_water_mark")

        motivo = None
        if cur is None:
            motivo = "left_universe"
        elif (cur.get("pcs") or 0) < PCS_MIN_ENTRY:
            motivo = f"pcs {cur.get('pcs')} < {PCS_MIN_ENTRY} (suelo absoluto)"
        elif (cur.get("rot_score") or 99) <= 2:
            motivo = f"rot_score {cur.get('rot_score')} <= 2"
        elif price is not None and hwm and price <= hwm * (1 - TRAILING_STOP_PCT):
            motivo = (f"cortacircuitos: cierre {price:.2f} <= "
                      f"{(1-TRAILING_STOP_PCT)*100:.0f}% del máximo {hwm:.2f}")

        if motivo:
            ptf.setdefault("history", []).append({
                **pos, "close_date": today, "close_price": price,
                "close_reason": motivo,
            })
            cerradas.append({"ticker": tk, "reason": motivo, "close_price": price})
        else:
            siguen.append(pos)

    ptf["positions"] = siguen
    return cerradas


def select(cands: list[dict], cava: dict, held: set[str]) -> list[dict]:
    """Elegibles → reparto por guía de Cava → ranking por PCS → límites."""
    posture = cava["posture"]
    max_pos = MAX_POSITIONS_BY_POSTURE.get(posture, 0)
    if max_pos == 0:
        return []

    pool = [c for c in cands
            if c.get("eligible")
            and (c.get("pcs") or 0) >= PCS_MIN_ENTRY
            and c.get("ticker") not in held]

    split = apply_regime_guidance(pool, cava["favor"], cava["avoid"])
    # Los temas que Cava evita quedan fuera. Los que no tienen guía ("sin
    # opinión": salud, cannabis, inmobiliario…) sí pueden entrar, operados solo
    # por PCS — un "no opino" honesto no debe bloquear el tema.
    #
    # Pero van DESPUÉS de los favorecidos, no mezclados por PCS. Si se ordenan
    # todos juntos, los temas sin opinión copan la cartera cuando tienen buen
    # PCS, y acabaríamos con una cartera "de Cava" dominada por los sectores
    # donde Cava no opina — que es justo lo que impediría medir su aportación.
    # Observado en la primera versión: 6 de 10 posiciones en sanidad.
    porf = sorted(split["favor"], key=lambda c: c.get("pcs") or 0, reverse=True)
    resto = sorted(split["no_opinion"], key=lambda c: c.get("pcs") or 0, reverse=True)

    favor_tickers = {c["ticker"] for c in porf}
    seleccion: list[dict] = []
    por_tema: dict[str, int] = {}
    por_categoria: dict[str, int] = {}
    for c in porf + resto:
        if len(seleccion) >= max_pos:
            break
        th = c.get("theme") or "(sin tema)"
        # Segundo tope, por categoría de Cava: sanidad ocupa dos temas nuestros
        # (`healthcare_largecap` y `healthcare_special`) que son una sola
        # categoría suya, así que el tope por tema solo no la contiene.
        cat = THEME_TO_CAVA_CATEGORY.get(th) or "(sin categoria)"
        if por_tema.get(th, 0) >= MAX_PER_THEME:
            continue
        if por_categoria.get(cat, 0) >= MAX_PER_CATEGORY:
            continue
        por_tema[th] = por_tema.get(th, 0) + 1
        por_categoria[cat] = por_categoria.get(cat, 0) + 1
        c = {**c, "_cava_favored": c["ticker"] in favor_tickers}
        seleccion.append(c)
    return seleccion


def run(apply: bool) -> int:
    today = str(date.today())
    data = _load(CANDIDATES, {})
    cands = data.get("candidates", [])
    if not cands:
        print("ai_candidates.json vacío — nada que hacer.")
        return 1

    picks = _load(PICKS, {})
    ptf = picks.setdefault("portfolios", {}).setdefault(
        PORTFOLIO_NAME, {"positions": [], "history": []})

    # Las salidas se evalúan SIEMPRE y antes que las entradas, igual que en
    # mirror_portfolio.py: son mecánicas, no cuestan una llamada al motor, y
    # liberan hueco para entradas del mismo día.
    cerradas = review_positions(ptf, cands, today) if apply else []
    if cerradas:
        print(f"\n{len(cerradas)} salida(s) mecánica(s):")
        for c in cerradas:
            print(f"  EXIT {c['ticker']:<10} {c['reason']}")

    held = {p["ticker"] for p in ptf.get("positions", [])}

    try:
        cava = query_cava(today)
    except Exception as e:
        print(f"Error consultando el motor de Cava: {e}")
        return 1

    ch = cava["corpus_health"]
    print(f"=== CAVA_MACRO — {today} ===")
    print(f"  estado : {cava['state']}")
    print(f"  postura: {cava['posture']}  (L1={cava['L1']} L2={cava['L2']} L3={cava['L3']})")
    print(f"  favor  : {cava['favor'] or '—'}")
    print(f"  evitar : {cava['avoid'] or '—'}")
    if ch.get("insufficient_corpus"):
        # Solo afecta a favor/avoid; la postura es independiente del corpus
        # (invariante verificada en 8 combinaciones antes de fiarnos).
        print(f"  ⚠ corpus insuficiente ({ch.get('dated_frames_available')} frames "
              f"fechados): la guía por categorías no es fiable hoy, "
              f"la postura sí.")
    print(f"  abiertas: {len(held)} · máximo con esta postura: "
          f"{MAX_POSITIONS_BY_POSTURE.get(cava['posture'], 0)}")

    libres = MAX_POSITIONS_BY_POSTURE.get(cava["posture"], 0) - len(held)
    if libres <= 0:
        print("\nSin hueco para entradas nuevas con la postura actual.")
        nuevos: list[dict] = []
    else:
        nuevos = select(cands, cava, held)[:libres]

    if not nuevos:
        print("\nNinguna entrada nueva hoy.")
    else:
        print(f"\n{len(nuevos)} entrada(s):")
        for c in nuevos:
            print(f"  {c['ticker']:<10} PCS {c.get('pcs'):>5} · {c.get('theme')}"
                  f" · {size_for(c.get('pcs'))}%")

    if not apply:
        print("\nDry-run: no se ha escrito nada. Usa --apply para aplicar.")
        return 0

    eq_w = round(100.0 / max(len(nuevos), 1), 2) if nuevos else None
    run_id = f"{today}_{datetime.now().strftime('%H%M')}"
    for c in nuevos:
        pcs = c.get("pcs")
        ptf["positions"].append({
            "ticker":        c["ticker"],
            "entry_date":    today,
            "entry_price":   None,       # lo rellena update_performance.py
            "entry_pcs":     pcs,
            "size_pct":      size_for(pcs),
            "equal_weight_pct": eq_w,
            "theme":         c.get("theme"),
            "cava_favored":  bool(c.get("_cava_favored")),
            "cava_posture":  cava["posture"],
            "cava_favor":    cava["favor"],
            "agent_version": cava["agent_version"],
            "corpus_version": cava["corpus_meta"].get("corpus_version"),
            "corpus_date_range": cava["corpus_meta"].get("corpus_date_range"),
        })
        # Fila en shadow_picks: sin esto la cartera no se mide (ver docstring).
        _append_jsonl(SHADOW_LOG, {
            "date": today, "run_id": run_id, "model": f"cava-engine-{cava['agent_version']}",
            "ticker": c["ticker"], "portfolio": PORTFOLIO_NAME, "pcs": pcs,
            "signal_type": cava["posture"], "confidence": None,
            "reason_short": f"postura {cava['posture']}; tema {c.get('theme')}",
            "shadow": False, "active_model": True, "forced_run": False,
            "valid_for_performance_tracking": True,
            "size_pct": size_for(pcs), "equal_weight_pct": eq_w,
            "entry_price": None,
            "ret_1d": None, "ret_3d": None, "ret_1w": None,
            "ret_2w": None, "ret_1m": None, "ret_3m": None,
            "max_gain_1m": None, "max_drawdown_1m": None, "vs_spy_1m": None,
        })

    PICKS.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(RUN_LOG, {
        "date": today, "run_id": run_id, "posture": cava["posture"],
        "favor": cava["favor"], "avoid": cava["avoid"], "state": cava["state"],
        "n_new": len(nuevos), "n_held": len(held),
        "n_closed": len(cerradas),
        "closed": [{"ticker": c["ticker"], "reason": c["reason"]} for c in cerradas],
        # Cuántos picks vinieron de una categoría que Cava favorece frente a
        # cuántos de temas sobre los que no opina. Si esto se queda cerca de
        # cero durante meses, la capa de `regime_guidance` no aporta en nuestro
        # universo y la contribución real de Cava es solo la postura — que es
        # justamente lo que validó la Prueba 1C.
        "n_cava_favored": sum(1 for c in nuevos if c.get("_cava_favored")),
        "n_no_opinion":   sum(1 for c in nuevos if not c.get("_cava_favored")),
        "n_eligible_pool": sum(1 for c in cands
                               if c.get("eligible") and (c.get("pcs") or 0) >= PCS_MIN_ENTRY),
        "agent_version": cava["agent_version"],
        "corpus_health": ch,
    })
    print(f"\nAplicado: {len(nuevos)} posición(es) nueva(s) en {PORTFOLIO_NAME}.")
    return 0


if __name__ == "__main__":
    sys.exit(run(apply="--apply" in sys.argv))
