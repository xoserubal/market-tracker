"""
cava_mapping.py — traducción del estado macro de AI Picks Lab al vocabulario
controlado del motor de decisión de Cava AI.

Contexto completo en wiki/AGENTE_EXTERNO_*.md (rondas 1-5 de la integración).

POR QUÉ ESTE MÓDULO VIVE EN NUESTRO REPO Y NO EN EL SUYO
---------------------------------------------------------
El motor de Cava es determinista: mismo input → mismo output. Pero la traducción
de nuestros números a sus enums NO lo es — decidir que VIX 31 es "extreme" y VIX
29 es "elevated" son umbrales que alguien elige. Ahí es donde se cuela el error,
no en su árbol. Por eso el mapping es código nuestro, auditable y con tests, en
vez de lógica escondida dentro de su wrapper.

Precedente que lo justifica: el indicador CMF estuvo duplicado en JavaScript y
Python durante meses con umbrales distintos, y un criterio del RotScore no puntuó
para ningún ticker sin que nadie lo detectara. Una sola fuente de verdad, con
tests, y umbrales con su calibración escrita al lado.

CALIBRACIÓN DE UMBRALES
-----------------------
Los umbrales de nivel salen de dos sitios, nunca "a ojo":

1. Reglas explícitas de la filosofía de Cava, cuando existen. La única realmente
   sagrada es VIX > 30 ("si el VIX supera 30 el playbook cambia totalmente"),
   documentada por su equipo en la Ronda 2 (M2).
2. Distribución real de nuestra serie 2024-2026 (macro_history.parquet, modo B),
   cuando no hay regla explícita. Percentiles medidos el 2026-08-02:

     vix        min 11.9  p25 14.8  p50 16.4  p75 19.4  max 45.3
     hy_bps     min 260   p25 281   p50 298   p75 320   max 445
     vix_d2w    p25 -2.2  p50 +0.2  p75 +2.2
     hy_d4w     p25 -18   p50 -5    p75 +12
     netliq_d4w p25 -111k p50 -48k  p75 +55k

Dos episodios de estrés reales sirven de anclaje (ambos cruzan VIX > 30):

     2025-04-06  VIX 45.3 (d2w +26.0)  HY 445bps (d4w +148)  → SPY -18.8%
     2026-03-29  VIX 31.0 (d2w  +3.9)  HY 342bps (d4w  +32)  → SPY  -8.9%

DATOS AUSENTES
--------------
Su motor degrada de forma elegante (M4): una dimensión que no se envía
simplemente no activa módulos, no falla. Por eso preferimos devolver None a
inventar un valor — un `sentiment_state` fabricado activaría módulos con
información que no tenemos. Ver `SENTIMENT_LIMITATION` más abajo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Umbrales de volatilidad ────────────────────────────────────────────────
# VIX_EXTREME es la única regla dictada por la filosofía de Cava, no por la
# distribución: "si el VIX supera 30, el playbook cambia totalmente — prefiero
# cubrir o estar en cash". El resto de cortes (20 / 14) son los que su equipo
# describió en M2 y encajan con nuestra distribución (p75 = 19.4).
VIX_EXTREME  = 30.0
VIX_ELEVATED = 20.0
VIX_CONTAINED = 14.0
# ±3 puntos en 2 semanas ≈ fuera del rango intercuartílico (p25 -2.2, p75 +2.2),
# es decir un movimiento que no es ruido normal.
VIX_MOVE_SIGNIFICANT = 3.0

# ── Umbrales de crédito (HY spread, en puntos básicos) ─────────────────────
# 400bps queda por encima de todo nuestro histórico 2024-2026 salvo el pico de
# abril de 2025 (445) — reservado para estrés genuino, no para ruido.
HY_CRITICAL = 400.0
# +75bps en 4 semanas es una ampliación violenta: solo ocurrió en abril de 2025
# (+148). Es la firma de una ruptura, de ahí "breaking_support".
HY_BREAKING = 75.0
# ±20bps queda fuera del rango intercuartílico (p25 -18, p75 +12).
HY_MOVE_SIGNIFICANT = 20.0

# ── Umbrales de liquidez (NetLiq, variación en millones USD) ───────────────
# 150k queda fuera del rango intercuartílico de la variación a 4 semanas
# (p25 -111k, p75 +55k).
NETLIQ_MOVE_SIGNIFICANT = 150_000.0

# ── Umbrales de precio ─────────────────────────────────────────────────────
DRAWDOWN_CAPITULATION = -15.0   # caída desde máximos que Cava trataría como pánico
DRAWDOWN_BREAKDOWN    = -8.0    # ruptura confirmada
DRAWDOWN_WEAK         = -5.0    # presión sin ruptura
NEAR_HIGHS_PCT        = -3.0    # a menos de un 3% del máximo
NEAR_LOWS_PCT         = -20.0
# Nota: DRAWDOWN_WEAK y NEAR_HIGHS_PCT tienen que dejar hueco entre ambos o
# 'range' queda inalcanzable. En la primera versión los dos valían -3.0 y el
# branch estaba muerto; lo detectó el test. Con -5.0 / -3.0, 'range' ocupa la
# banda intermedia (caída de entre el 3 % y el 5 % desde máximos), que es
# justamente la lectura de "ni cerca de máximos ni con daño real".

SENTIMENT_LIMITATION = (
    "No hay histórico de Fear & Greed en el pipeline Python (vive en la capa de "
    "visualización, solo en vivo). El sentimiento se aproxima desde VIX y "
    "drawdown, que es lo que su equipo autorizó en M2. En consecuencia NUNCA "
    "emitimos 'euphoria' ni 'skepticism': ambos requieren divergencia entre "
    "sentimiento y precio, que no se puede medir sin el índice. Devolver None "
    "para esos casos es preferible a inventarlos."
)


@dataclass
class MacroInputs:
    """Estado macro crudo en una fecha. Todos los campos son opcionales: lo que
    falte se traduce en una dimensión ausente, no en un valor inventado."""
    vix: float | None = None
    vix_d2w: float | None = None
    hy_bps: float | None = None
    hy_d4w: float | None = None
    netliq_d4w: float | None = None
    netliq_d8w: float | None = None
    # Precio del índice de referencia
    spy_vs_high_pct: float | None = None   # % desde el máximo de 52 semanas
    spy_vs_sma200_pct: float | None = None
    spy_ret_4w_pct: float | None = None
    # Contexto propio (solo para narrativa; no sustituye a su lectura)
    inflation_overlay: bool = False
    macro_regime: str | None = None
    macro_score_delta_4w: float | None = None


def volatility_state(i: MacroInputs) -> str | None:
    """Cascada (el orden ES la prioridad, igual que su _konc_alignment):

        extreme    VIX > 30            ← regla sagrada de Cava, siempre gana
        elevated   VIX > 20
        rising     subida significativa desde nivel no alarmante
        falling    bajada significativa
        contained  VIX >= 14
        low        resto

    El nivel manda sobre la dirección en la zona alarmante: un VIX de 32 que
    baja sigue siendo 'extreme', no 'falling'. Por debajo de 20 la dirección
    informa más que el nivel, porque es donde se gestan los cambios de régimen.
    """
    if i.vix is None:
        return None
    if i.vix > VIX_EXTREME:
        return "extreme"
    if i.vix > VIX_ELEVATED:
        return "elevated"
    if i.vix_d2w is not None:
        if i.vix_d2w >= VIX_MOVE_SIGNIFICANT:
            return "rising"
        if i.vix_d2w <= -VIX_MOVE_SIGNIFICANT:
            return "falling"
    if i.vix >= VIX_CONTAINED:
        return "contained"
    return "low"


def credit_state(i: MacroInputs) -> str | None:
    """Cascada:

        critical          spread en nivel de alerta sistémica
        breaking_support  ampliación violenta (la firma de una ruptura)
        widening / tightening   dirección significativa
        stable            resto

    'critical' se evalúa antes que 'breaking_support' porque un nivel ya crítico
    es más grave que la velocidad a la que se llegó a él.
    """
    if i.hy_bps is None and i.hy_d4w is None:
        return None
    if i.hy_bps is not None and i.hy_bps >= HY_CRITICAL:
        return "critical"
    if i.hy_d4w is not None:
        if i.hy_d4w >= HY_BREAKING:
            return "breaking_support"
        if i.hy_d4w >= HY_MOVE_SIGNIFICANT:
            return "widening"
        if i.hy_d4w <= -HY_MOVE_SIGNIFICANT:
            return "tightening"
    return "stable"


def liquidity_state(i: MacroInputs) -> str | None:
    """Distingue nivel sostenido (tight / favorable, mirando 4 y 8 semanas) de
    movimiento puntual (deteriorating / improving, solo 4 semanas). Una
    contracción sostenida es una condición; una puntual es un evento."""
    if i.netliq_d4w is None:
        return None
    d4, d8 = i.netliq_d4w, i.netliq_d8w
    if d8 is not None:
        if d4 < 0 and d8 < 0 and abs(d4) > NETLIQ_MOVE_SIGNIFICANT:
            return "tight"
        if d4 > 0 and d8 > 0 and d4 > NETLIQ_MOVE_SIGNIFICANT:
            return "favorable"
    if d4 <= -NETLIQ_MOVE_SIGNIFICANT:
        return "deteriorating"
    if d4 >= NETLIQ_MOVE_SIGNIFICANT:
        return "improving"
    return "neutral"


def price_state(i: MacroInputs) -> str | None:
    """Cascada. Los estados de deterioro se evalúan primero para que una caída
    seria nunca quede enmascarada por una lectura benigna."""
    dd = i.spy_vs_high_pct
    if dd is None:
        return None
    if dd <= DRAWDOWN_CAPITULATION:
        return "capitulation"
    if dd <= DRAWDOWN_BREAKDOWN:
        return "breakdown"
    if dd <= DRAWDOWN_WEAK:
        return "weak"
    if dd >= NEAR_HIGHS_PCT:
        # Cerca de máximos: 'strong' si además viene con impulso, si no 'bullish'
        if i.spy_ret_4w_pct is not None and i.spy_ret_4w_pct >= 3.0:
            return "strong"
        return "bullish"
    return "range"


def trend_state(i: MacroInputs) -> str | None:
    """Posición estructural respecto a medias y extremos."""
    if i.spy_vs_sma200_pct is None and i.spy_vs_high_pct is None:
        return None
    dd, sma = i.spy_vs_high_pct, i.spy_vs_sma200_pct
    if sma is not None and sma < 0:
        # Por debajo de la media larga: distinguir pérdida de soporte de mínimos
        if dd is not None and dd <= NEAR_LOWS_PCT:
            return "near_lows"
        return "below_ma"
    if dd is not None and dd >= NEAR_HIGHS_PCT:
        return "near_highs"
    if sma is not None and sma > 0:
        # Sobre la media larga pero lejos de máximos y recuperando
        if i.spy_ret_4w_pct is not None and i.spy_ret_4w_pct >= 3.0 and dd is not None and dd < NEAR_HIGHS_PCT:
            return "recovery"
        return "above_ma"
    return None


def sentiment_state(i: MacroInputs) -> str | None:
    """Aproximado desde VIX. Ver SENTIMENT_LIMITATION: nunca emitimos 'euphoria'
    ni 'skepticism' porque ambos exigen divergencia sentimiento/precio y no
    tenemos el índice de Fear & Greed en histórico."""
    if i.vix is None:
        return None
    if i.vix > 35.0:
        return "extreme_fear"
    if i.vix > 25.0:
        return "fear"
    if i.vix < VIX_CONTAINED and (i.vix_d2w is None or i.vix_d2w <= 0):
        return "complacent"
    return "neutral"


def narrative_state(i: MacroInputs) -> list[str]:
    """Su M2 recomienda explícitamente ser conservador aquí: 'es mejor
    subestimar las narrativas que inventarlas — L3 es el nivel más bajo de la
    jerarquía y nunca invalida L1'. Solo activamos lo que podemos sostener con
    un dato concreto."""
    out: list[str] = []
    if i.inflation_overlay:
        out.append("inflation")
    if i.netliq_d4w is not None and i.netliq_d4w <= -NETLIQ_MOVE_SIGNIFICANT:
        out.append("liquidity")
    if i.macro_regime in ("Risk-OFF", "Capitulación") and (
        i.macro_score_delta_4w is not None and i.macro_score_delta_4w < -10
    ):
        out.append("recession")
    return out or ["none"]


def build_market_state(i: MacroInputs) -> dict[str, Any]:
    """Ensambla el estado en el formato que espera el motor. Las dimensiones sin
    dato se omiten del dict (no se envían como None): según su M4, una dimensión
    ausente simplemente no activa módulos, mientras que un valor desconocido se
    registraría en `unknown_query_states`. Omitir es más limpio."""
    dims = {
        "price_state":      price_state(i),
        "trend_state":      trend_state(i),
        "volatility_state": volatility_state(i),
        "credit_state":     credit_state(i),
        "sentiment_state":  sentiment_state(i),
        "liquidity_state":  liquidity_state(i),
    }
    state: dict[str, Any] = {k: v for k, v in dims.items() if v is not None}
    state["narrative_state"] = narrative_state(i)
    return state


# ══════════════════════════════════════════════════════════════════════════
# DIRECCIÓN B — sus categorías de `regime_guidance` → nuestros `theme`
# ══════════════════════════════════════════════════════════════════════════
# La enumeración es CERRADA y la fijó su equipo (nota pre-desarrollo, 2026-08).
# Cualquier categoría que llegue y no esté aquí provoca un fallo ruidoso, nunca
# un silencio: ese era justamente el riesgo que motivó pedirles la lista.

CAVA_CATEGORIES_WITH_OPINION = frozenset({
    "equity_general", "energy", "real_assets", "technology", "crypto",
    "emerging_markets", "duration_long", "corporate_credit", "volatility_hedges",
})
CAVA_CATEGORIES_UNMAPPED = frozenset({
    "healthcare", "cannabis", "defensive_consumption", "financials_ex_crypto",
    "real_estate",
    # Añadida por ellos en v1.1.0, después de la lista inicial de 14: resuelve
    # nuestra consulta sobre `defense_space`. Queda sin cobertura, es decir esos
    # candidatos se operan solo con PCS. Lo detectamos al verificar el paquete
    # entregado, no porque nos avisaran — y lo detectamos precisamente porque
    # `validate_categories` lanza excepción ante lo desconocido en vez de
    # ignorarlo. Es el contrato duro haciendo su trabajo.
    "defense_aerospace",
})
CAVA_CATEGORIES_ALL = CAVA_CATEGORIES_WITH_OPINION | CAVA_CATEGORIES_UNMAPPED

# Nuestros 21 `theme` → su categoría. `None` = pendiente de resolución por su
# parte (ver PENDING_CATEGORY_RULINGS); esos temas se tratan como sin opinión
# hasta que lo aclaren, nunca se fuerzan a un cajón genérico.
THEME_TO_CAVA_CATEGORY: dict[str, str | None] = {
    "silver_gold_miners":   "real_assets",
    "commodities_metals":   "real_assets",
    "commodities_copper":   "real_assets",
    "oil_gas":              "energy",
    "us_tech_ai":           "technology",
    "crypto":               "crypto",
    "argentina":            "emerging_markets",
    "china_em":             "emerging_markets",
    "smallcap_em":          "emerging_markets",
    "us_cyclical":          "equity_general",
    "europa":               "equity_general",
    "global_etf":           "equity_general",
    "smallcap_speculative": "equity_general",
    # Sin opinión declarada por ellos — se operan solo con PCS
    "healthcare_largecap":  "healthcare",
    "healthcare_special":   "healthcare",
    "cannabis":             "cannabis",
    "reits":                "real_estate",
    "us_defensive":         "defensive_consumption",
    # Pendientes de que ellos decidan
    "defense_space":        "defense_aerospace",
    "uranium_nuclear":      "energy",
    "energy_storage":       "technology",
}

# Todas las consultas de categoría quedaron resueltas por su equipo en v1.1.0:
#   defense_space   -> defense_aerospace (sin cobertura declarada)
#   uranium_nuclear -> energy      (tesis energética estructural, no cobertura monetaria)
#   energy_storage  -> technology
# Se deja el dict vacío en vez de borrarlo: si aparece un tema nuevo en nuestro
# universo sin categoría asignada, este es el sitio donde anotarlo.
PENDING_CATEGORY_RULINGS: dict[str, str] = {}


class UnknownCavaCategory(ValueError):
    """La categoría recibida no está en la enumeración cerrada acordada.

    Se lanza a propósito en vez de ignorar la categoría en silencio: si su
    motor empieza a emitir un identificador nuevo sin avisar, queremos que el
    pipeline falle de forma visible, no que un tema deje de recibir guía y
    nadie se entere durante meses.
    """


def validate_categories(categories: list[str]) -> None:
    """Comprueba contra la enumeración cerrada. Lanza si hay alguna desconocida."""
    unknown = [c for c in categories if c not in CAVA_CATEGORIES_ALL]
    if unknown:
        raise UnknownCavaCategory(
            f"Categorías fuera del contrato acordado: {unknown}. "
            f"Permitidas: {sorted(CAVA_CATEGORIES_ALL)}. "
            "Si su motor ha añadido categorías, hay que actualizar "
            "CAVA_CATEGORIES_* y THEME_TO_CAVA_CATEGORY a la vez."
        )


def themes_for_categories(categories: list[str]) -> set[str]:
    """Nuestros `theme` que corresponden a una lista de categorías suyas."""
    validate_categories(categories)
    wanted = set(categories)
    return {t for t, c in THEME_TO_CAVA_CATEGORY.items() if c in wanted}


def apply_regime_guidance(
    candidates: list[dict],
    favor: list[str],
    avoid: list[str],
) -> dict[str, list[dict]]:
    """Reparte candidatos en favorecidos / evitados / sin opinión según la guía.

    Mecánico a propósito, sin interpretación: su equipo señaló (Ronda 3) que si
    este paso exigiera juicio humano, la validación mediría nuestra traducción
    tanto como la calidad de Cava. Un candidato cuyo tema no tenga categoría
    asignada, o cuya categoría no aparezca ni en favor ni en avoid, cae en
    `no_opinion` y se opera solo con PCS.
    """
    validate_categories(favor)
    validate_categories(avoid)
    # Defensa en profundidad: las categorías declaradas "sin cobertura" nunca
    # deben dirigir una decisión, ni aunque el motor las cite por error en
    # favor/avoid. Su propio contrato dice que sobre ellas no tiene criterio;
    # actuar sobre ellas contradiría lo acordado. En la práctica el motor las
    # devuelve en `unmapped_or_no_opinion` (verificado en v1.1.0), así que esto
    # solo cubre el caso de que eso cambie sin avisar.
    favor_set = set(favor) & CAVA_CATEGORIES_WITH_OPINION
    avoid_set = set(avoid) & CAVA_CATEGORIES_WITH_OPINION
    out: dict[str, list[dict]] = {"favor": [], "avoid": [], "no_opinion": []}
    for c in candidates:
        cat = THEME_TO_CAVA_CATEGORY.get(c.get("theme"))
        if cat is not None and cat in favor_set:
            out["favor"].append(c)
        elif cat is not None and cat in avoid_set:
            out["avoid"].append(c)
        else:
            out["no_opinion"].append(c)
    return out


def explain(i: MacroInputs) -> str:
    """Salida legible para la muestra de calibración que acordamos enviarles
    (Ronda 2): 'con estos datos, esto es lo que hemos codificado'."""
    s = build_market_state(i)
    lines = ["Estado de mercado codificado:"]
    for k, v in s.items():
        lines.append(f"  {k:18s} = {v}")
    missing = [k for k in ("price_state", "trend_state", "volatility_state",
                           "credit_state", "sentiment_state", "liquidity_state")
               if k not in s]
    if missing:
        lines.append(f"  (sin dato, omitidas: {', '.join(missing)})")
    return "\n".join(lines)
