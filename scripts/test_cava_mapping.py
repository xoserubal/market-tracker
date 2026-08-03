"""
Tests del mapping estado macro → vocabulario controlado de Cava AI.

Se ejecutan sin pytest para no añadir dependencias al pipeline:
    py -3 scripts/test_cava_mapping.py

Incluye dos anclajes con datos REALES de nuestro histórico (no sintéticos):
los episodios de estrés de abril de 2025 (SPY -18.8%) y marzo de 2026 (-8.9%).
Si el mapping deja de clasificarlos como estrés, algo se ha roto.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cava_mapping import (  # noqa: E402
    CAVA_CATEGORIES_ALL, CAVA_CATEGORIES_UNMAPPED,
    CAVA_CATEGORIES_WITH_OPINION, THEME_TO_CAVA_CATEGORY, MacroInputs,
    UnknownCavaCategory, apply_regime_guidance, build_market_state,
    credit_state, liquidity_state, narrative_state, price_state,
    sentiment_state, themes_for_categories, trend_state, volatility_state,
)

_passed = 0
_failed: list[str] = []


def check(name: str, got, want) -> None:
    global _passed
    if got == want:
        _passed += 1
    else:
        _failed.append(f"{name}\n     esperado: {want!r}\n     obtenido: {got!r}")


# ── Volatilidad ────────────────────────────────────────────────────────────
# La regla sagrada (VIX > 30) gana sobre todo lo demás, incluida la dirección.
check("vix extremo", volatility_state(MacroInputs(vix=45.3, vix_d2w=26.0)), "extreme")
check("vix extremo pero bajando sigue extremo",
      volatility_state(MacroInputs(vix=32.0, vix_d2w=-8.0)), "extreme")
check("vix justo por debajo del umbral sagrado",
      volatility_state(MacroInputs(vix=29.9, vix_d2w=0.0)), "elevated")
check("vix elevado", volatility_state(MacroInputs(vix=22.0)), "elevated")
check("vix subiendo desde nivel normal",
      volatility_state(MacroInputs(vix=18.0, vix_d2w=4.0)), "rising")
check("vix bajando desde nivel normal",
      volatility_state(MacroInputs(vix=16.0, vix_d2w=-5.0)), "falling")
check("vix contenido sin movimiento",
      volatility_state(MacroInputs(vix=16.4, vix_d2w=0.2)), "contained")
check("vix bajo", volatility_state(MacroInputs(vix=12.0, vix_d2w=-0.5)), "low")
check("sin dato de vix", volatility_state(MacroInputs()), None)

# ── Crédito ────────────────────────────────────────────────────────────────
check("hy critico por nivel", credit_state(MacroInputs(hy_bps=445.0, hy_d4w=148.0)), "critical")
check("nivel critico gana sobre velocidad",
      credit_state(MacroInputs(hy_bps=420.0, hy_d4w=5.0)), "critical")
check("ampliacion violenta sin nivel critico",
      credit_state(MacroInputs(hy_bps=350.0, hy_d4w=90.0)), "breaking_support")
check("ampliacion normal", credit_state(MacroInputs(hy_bps=342.0, hy_d4w=32.0)), "widening")
check("estrechamiento", credit_state(MacroInputs(hy_bps=280.0, hy_d4w=-30.0)), "tightening")
check("credito estable", credit_state(MacroInputs(hy_bps=298.0, hy_d4w=-5.0)), "stable")
check("sin datos de credito", credit_state(MacroInputs()), None)

# ── Liquidez ───────────────────────────────────────────────────────────────
check("liquidez tensa sostenida",
      liquidity_state(MacroInputs(netliq_d4w=-200_000.0, netliq_d8w=-300_000.0)), "tight")
check("liquidez favorable sostenida",
      liquidity_state(MacroInputs(netliq_d4w=200_000.0, netliq_d8w=250_000.0)), "favorable")
check("deterioro puntual (8w positivo)",
      liquidity_state(MacroInputs(netliq_d4w=-200_000.0, netliq_d8w=50_000.0)), "deteriorating")
check("liquidez neutra",
      liquidity_state(MacroInputs(netliq_d4w=-48_000.0, netliq_d8w=-97_000.0)), "neutral")
check("sin dato de liquidez", liquidity_state(MacroInputs()), None)

# ── Precio ─────────────────────────────────────────────────────────────────
check("capitulacion", price_state(MacroInputs(spy_vs_high_pct=-18.8)), "capitulation")
check("ruptura", price_state(MacroInputs(spy_vs_high_pct=-8.9)), "breakdown")
check("debil", price_state(MacroInputs(spy_vs_high_pct=-6.0)), "weak")
check("debil en el borde exacto", price_state(MacroInputs(spy_vs_high_pct=-5.0)), "weak")
# 'range' vive en la banda intermedia (-5, -3). Si alguien vuelve a igualar
# DRAWDOWN_WEAK y NEAR_HIGHS_PCT, este test lo detecta: el branch queda muerto.
check("rango", price_state(MacroInputs(spy_vs_high_pct=-4.0)), "range")
check("rango en el borde superior", price_state(MacroInputs(spy_vs_high_pct=-3.1)), "range")
check("cerca de maximos sin impulso",
      price_state(MacroInputs(spy_vs_high_pct=-1.0, spy_ret_4w_pct=0.5)), "bullish")
check("cerca de maximos con impulso",
      price_state(MacroInputs(spy_vs_high_pct=-0.5, spy_ret_4w_pct=5.0)), "strong")
check("sin dato de precio", price_state(MacroInputs()), None)

# ── Tendencia ──────────────────────────────────────────────────────────────
check("bajo la media larga", trend_state(MacroInputs(spy_vs_sma200_pct=-4.0, spy_vs_high_pct=-10.0)), "below_ma")
check("cerca de minimos", trend_state(MacroInputs(spy_vs_sma200_pct=-8.0, spy_vs_high_pct=-25.0)), "near_lows")
check("cerca de maximos", trend_state(MacroInputs(spy_vs_sma200_pct=6.0, spy_vs_high_pct=-1.0)), "near_highs")
check("recuperando", trend_state(MacroInputs(spy_vs_sma200_pct=2.0, spy_vs_high_pct=-8.0, spy_ret_4w_pct=6.0)), "recovery")
check("sobre la media sin mas", trend_state(MacroInputs(spy_vs_sma200_pct=3.0, spy_vs_high_pct=-6.0, spy_ret_4w_pct=0.5)), "above_ma")
check("sin datos de tendencia", trend_state(MacroInputs()), None)

# ── Sentimiento ────────────────────────────────────────────────────────────
check("miedo extremo", sentiment_state(MacroInputs(vix=45.3)), "extreme_fear")
check("miedo", sentiment_state(MacroInputs(vix=28.0)), "fear")
check("complacencia", sentiment_state(MacroInputs(vix=12.5, vix_d2w=-1.0)), "complacent")
check("sentimiento neutro", sentiment_state(MacroInputs(vix=17.0, vix_d2w=0.0)), "neutral")
# Nunca inventamos euforia ni escepticismo: exigen el indice de Fear & Greed.
for v in (11.0, 13.0, 16.0, 22.0, 40.0):
    got = sentiment_state(MacroInputs(vix=v, vix_d2w=0.0))
    check(f"nunca euforia/escepticismo (vix={v})", got in ("euphoria", "skepticism"), False)

# ── Narrativa ──────────────────────────────────────────────────────────────
check("narrativa por defecto", narrative_state(MacroInputs()), ["none"])
check("inflacion", narrative_state(MacroInputs(inflation_overlay=True)), ["inflation"])
check("liquidez", narrative_state(MacroInputs(netliq_d4w=-200_000.0)), ["liquidity"])
check("recesion requiere regimen Y caida de score",
      narrative_state(MacroInputs(macro_regime="Risk-OFF", macro_score_delta_4w=-2.0)), ["none"])
check("recesion confirmada",
      narrative_state(MacroInputs(macro_regime="Risk-OFF", macro_score_delta_4w=-20.0)), ["recession"])
check("narrativas multiples",
      narrative_state(MacroInputs(inflation_overlay=True, netliq_d4w=-200_000.0)),
      ["inflation", "liquidity"])

# ── Ensamblado: dimensiones ausentes se omiten, no van como None ───────────
st = build_market_state(MacroInputs(vix=16.0, vix_d2w=0.0))
check("omite dimensiones sin dato", "price_state" in st, False)
check("incluye las que si tienen dato", st.get("volatility_state"), "contained")
check("narrative_state siempre presente", st.get("narrative_state"), ["none"])

# ── ANCLAJES CON DATOS REALES ──────────────────────────────────────────────
# Abril 2025 — el mayor drawdown desde 2024 (SPY -18.8%).
# Valores reales de macro_history.parquet (modo B) al 2025-04-06.
abril_2025 = MacroInputs(
    vix=45.31, vix_d2w=26.03, hy_bps=445.0, hy_d4w=148.0,
    spy_vs_high_pct=-18.8, spy_vs_sma200_pct=-12.0, spy_ret_4w_pct=-14.0,
    macro_regime="Transición", macro_score_delta_4w=-25.0,
)
s25 = build_market_state(abril_2025)
check("abril 2025: volatilidad extrema", s25["volatility_state"], "extreme")
check("abril 2025: credito critico", s25["credit_state"], "critical")
check("abril 2025: capitulacion", s25["price_state"], "capitulation")
check("abril 2025: miedo extremo", s25["sentiment_state"], "extreme_fear")
check("abril 2025: bajo la media", s25["trend_state"], "below_ma")

# Marzo 2026 — segunda mayor caida (SPY -8.9%), la ventana con corpus denso.
marzo_2026 = MacroInputs(
    vix=31.0, vix_d2w=3.9, hy_bps=342.0, hy_d4w=32.0,
    spy_vs_high_pct=-8.9, spy_vs_sma200_pct=-2.0, spy_ret_4w_pct=-7.0,
    macro_regime="Transición", macro_score_delta_4w=-23.0,
)
s26 = build_market_state(marzo_2026)
check("marzo 2026: volatilidad extrema (cruza 30)", s26["volatility_state"], "extreme")
check("marzo 2026: credito ampliandose", s26["credit_state"], "widening")
check("marzo 2026: ruptura", s26["price_state"], "breakdown")

# Los dos episodios deben activar el modulo de gestion de riesgo de Cava, que
# segun su tabla M3 se enciende con price_state:breakdown|capitulation,
# trend_state:below_ma|lost_support|near_lows, volatility_state:extreme o
# credit_state:critical. Es la comprobacion de que la prueba de falsacion
# (abril 2025 con corpus completo) tiene sentido: si el estado que enviamos no
# encendiera ese modulo, el fallo seria nuestro, no del motor.
for nombre, s in (("abril 2025", s25), ("marzo 2026", s26)):
    activa = (
        s.get("price_state") in ("breakdown", "capitulation")
        or s.get("trend_state") in ("below_ma", "lost_support", "near_lows")
        or s.get("volatility_state") == "extreme"
        or s.get("credit_state") == "critical"
    )
    check(f"{nombre}: activa risk_management_invalidaciones", activa, True)

# Un mercado tranquilo NO debe activarlo (evita el falso positivo permanente).
tranquilo = MacroInputs(
    vix=14.5, vix_d2w=0.3, hy_bps=285.0, hy_d4w=-8.0,
    spy_vs_high_pct=-1.2, spy_vs_sma200_pct=8.0, spy_ret_4w_pct=2.0,
    netliq_d4w=20_000.0, netliq_d8w=30_000.0,
)
sq = build_market_state(tranquilo)
no_activa = not (
    sq.get("price_state") in ("breakdown", "capitulation")
    or sq.get("trend_state") in ("below_ma", "lost_support", "near_lows")
    or sq.get("volatility_state") == "extreme"
    or sq.get("credit_state") == "critical"
)
check("mercado tranquilo NO activa gestion de riesgo", no_activa, True)
check("mercado tranquilo: precio alcista", sq["price_state"], "bullish")
check("mercado tranquilo: credito estable", sq["credit_state"], "stable")


# ══════════════════════════════════════════════════════════════════════════
# DIRECCIÓN B — sus categorías → nuestros temas
# ══════════════════════════════════════════════════════════════════════════

# El contrato: 9 con opinión + 6 sin cobertura = 15 (v1.1.0 añadió
# `defense_aerospace` a la lista original de 14).
check("categorias con opinion", len(CAVA_CATEGORIES_WITH_OPINION), 9)
check("categorias sin cobertura", len(CAVA_CATEGORIES_UNMAPPED), 6)
check("total = suma de ambos conjuntos, sin solape",
      len(CAVA_CATEGORIES_ALL),
      len(CAVA_CATEGORIES_WITH_OPINION) + len(CAVA_CATEGORIES_UNMAPPED))
check("defense_aerospace esta en el contrato",
      "defense_aerospace" in CAVA_CATEGORIES_ALL, True)

# Toda categoría que asignemos debe existir en su enumeración: si alguien añade
# un tema nuestro apuntando a una categoría inventada, esto lo detecta.
for theme, cat in THEME_TO_CAVA_CATEGORY.items():
    if cat is not None:
        check(f"'{theme}' apunta a categoria valida", cat in CAVA_CATEGORIES_ALL, True)

# Una categoría desconocida tiene que fallar de forma ruidosa, no en silencio.
# Es el fallo concreto que motivó pedirles la lista cerrada.
try:
    themes_for_categories(["energy", "commodities"])  # 'commodities' no existe
    check("categoria desconocida lanza excepcion", "no lanzo", "UnknownCavaCategory")
except UnknownCavaCategory:
    check("categoria desconocida lanza excepcion", True, True)

check("temas de real_assets", themes_for_categories(["real_assets"]),
      {"silver_gold_miners", "commodities_metals", "commodities_copper"})
check("temas de emerging_markets", themes_for_categories(["emerging_markets"]),
      {"argentina", "china_em", "smallcap_em"})

# Reparto de candidatos
_cands = [
    {"ticker": "AG",   "theme": "silver_gold_miners"},   # real_assets
    {"ticker": "CVE",  "theme": "oil_gas"},              # energy
    {"ticker": "TMO",  "theme": "healthcare_largecap"},  # healthcare (sin opinion)
    {"ticker": "GGAL", "theme": "argentina"},            # emerging_markets
    {"ticker": "RCAT", "theme": "defense_space"},        # pendiente de resolucion
]
res = apply_regime_guidance(_cands, favor=["real_assets", "energy"], avoid=["emerging_markets"])
check("favorecidos", sorted(c["ticker"] for c in res["favor"]), ["AG", "CVE"])
check("evitados", [c["ticker"] for c in res["avoid"]], ["GGAL"])
check("sin opinion incluye healthcare y pendientes",
      sorted(c["ticker"] for c in res["no_opinion"]), ["RCAT", "TMO"])

# Resoluciones que dio su equipo en v1.1.0. El uranio va a `energy` (tesis
# energética estructural) y no a `real_assets` (cobertura monetaria): no es
# cosmético, decide de qué módulo recibe guía y por tanto puede acabar en favor
# o en avoid dentro del mismo régimen.
check("uranio -> energy", THEME_TO_CAVA_CATEGORY["uranium_nuclear"], "energy")
check("almacenamiento -> technology", THEME_TO_CAVA_CATEGORY["energy_storage"], "technology")
check("defensa -> sin cobertura", THEME_TO_CAVA_CATEGORY["defense_space"], "defense_aerospace")

res2 = apply_regime_guidance(
    [{"ticker": "CCJ", "theme": "uranium_nuclear"}],
    favor=["energy"], avoid=[],
)
check("uranio recibe guia de energy", [c["ticker"] for c in res2["favor"]], ["CCJ"])

# Un tema sin categoría con opinión nunca acaba en favor ni en avoid, aunque su
# categoría aparezca en la guía: `defense_aerospace` es de las declaradas sin
# cobertura, así que esos candidatos se operan solo con PCS.
res2b = apply_regime_guidance(
    [{"ticker": "RCAT", "theme": "defense_space"}],
    favor=["defense_aerospace", "energy"], avoid=[],
)
check("tema sin cobertura no entra en favor aunque el motor lo cite",
      [c["ticker"] for c in res2b["favor"]], [])
check("tema sin cobertura queda sin opinion",
      [c["ticker"] for c in res2b["no_opinion"]], ["RCAT"])

# Ya no queda ningún tema nuestro sin categoría asignada.
check("no quedan temas sin resolver",
      [t for t, c in THEME_TO_CAVA_CATEGORY.items() if c is None], [])

# Guía vacía = todo sin opinión (el sistema opera solo con PCS).
res3 = apply_regime_guidance(_cands, favor=[], avoid=[])
check("guia vacia deja todo sin opinion", len(res3["no_opinion"]), 5)


# ── Resultado ──────────────────────────────────────────────────────────────
print(f"\n{_passed} tests pasados, {len(_failed)} fallidos")
if _failed:
    print("\nFALLOS:")
    for f in _failed:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
