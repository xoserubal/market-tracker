"""
cava_state_history.py — reconstruye el estado macro de cualquier fecha histórica
para alimentar el motor de Cava AI.

Habilita tres cosas acordadas con su equipo (ver wiki/AGENTE_EXTERNO_*.md):

  1. Muestra de calibración — "con los datos del día X, esto es lo que
     codificamos", para que confirmen si refleja lo que diría Cava.
  2. Prueba de falsación (abril 2025) — meterle un estrés obvio (SPY -18.8%)
     con corpus completo y comprobar que lo diagnostica como tal. Si no lo
     hiciera, el fallo estaría en nuestra traducción, no en su motor.
  3. Prueba 1C — validación histórica de `deterministic_risk_posture` sobre
     2024-2026, incluidos los 5 episodios de estrés. Es la única prueba con
     muestra real, porque la capa determinista no depende de la densidad del
     corpus (que está concentrada en 2026).

CADA DIMENSIÓN A SU CADENCIA REAL
---------------------------------
La primera versión de este módulo reconstruía todo en semanal, porque es la
cadencia de `macro_history.parquet`. **Fue un error y lo detectó la propia
verificación:** sobre serie semanal, de los 5 episodios de estrés de 2024-2026
solo 2 llegaban a registrarse como tales (6 de 135 lecturas). Los demás eran
caídas rápidas que se recuperaban dentro de la semana, así que el cierre
semanal las borraba.

El caso más grave era agosto de 2024 (desarme del carry trade del yen): el VIX
diario tocó 38,6 —muy por encima del umbral de 30 que es la única regla sagrada
de la filosofía de Cava— pero el cierre semanal lo dejaba en zona normal. Ese
episodio desaparecía por completo, y es justo el tipo de evento que el marco de
Cava debería detectar.

Ahora cada dimensión usa su cadencia natural:

    precio, tendencia   diario     (es L1 en su jerarquía: manda y se mueve rápido)
    volatilidad         diario     (el VIX pica intradía; en semanal se pierde)
    crédito             diario     (spread HY de FRED)
    liquidez            semanal    (el balance de la Fed se publica semanal)
    régimen propio      semanal    (es la cadencia real del MacroScore)

No es una mezcla arbitraria: refleja a qué velocidad se mueve de verdad cada
señal. Los deltas (VIX a 2 semanas, HY a 4) se calculan sobre la serie diaria,
no se leen precalculados del parquet semanal.

SIN MIRAR AL FUTURO
-------------------
`macro_inputs_at(fecha)` solo usa observaciones con fecha <= la pedida. Las
ventanas móviles (máximo de 52 semanas, media de 40) se calculan sobre la serie
truncada, no sobre la serie completa. Es la misma disciplina que le pedimos a su
`as_of_date`: si nosotros filtramos su corpus por fecha pero le enviamos un
estado macro contaminado con datos posteriores, el sesgo entra por la otra
puerta y la validación no vale nada.
"""
from __future__ import annotations

import sys
from datetime import date as _date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from cava_mapping import MacroInputs, build_market_state, explain  # noqa: E402

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "backtest" / "data" / "processed"
# Caché de precios diarios. Prefijo "_" y sin trackear en git, mismo patrón que
# el `_baseline_price_cache.json` que ya usa compare_vs_baselines.py.
PRICE_CACHE = ROOT / "docs" / "data" / "_cava_price_cache.parquet"

SMA_DAYS = 200      # media larga clásica
HIGH_DAYS = 252     # máximo de 52 semanas en sesiones
RET_DAYS = 21       # retorno a ~1 mes
VIX_DELTA_DAYS = 10  # "2 semanas" en sesiones
HY_DELTA_DAYS = 21   # "4 semanas" en sesiones

# El MacroScore se calcula en dos modos. Usamos B porque es el que distingue
# Risk-OFF (31 semanas en 2024-2026); el modo A nunca lo emite en esa ventana,
# lo que dejaría la validación sin episodios de estrés que medir.
MACRO_MODE = "B"


CACHE_MAX_STALE_DAYS = 4   # margen para fin de semana + festivo


def _fetch_daily_prices(start: str = "2004-06-01") -> pd.DataFrame:
    """SPY y ^VIX diarios. Se cachean porque `prices_daily.parquet` se corta en
    2026-04-17 y no trae el VIX en ninguna cadencia — sin él no se puede evaluar
    la regla de VIX > 30, que es la única explícita de la filosofía de Cava.

    El caché se REFRESCA si su última sesión tiene más de CACHE_MAX_STALE_DAYS.
    Sin esa comprobación el primer uso congelaba los precios para siempre: en el
    pipeline no se notaría (el caché está en .gitignore, así que allí siempre se
    descarga de cero), pero en local la cartera habría seguido decidiendo con el
    VIX y el SPY del día que se creó el fichero — y el estado macro es
    precisamente lo que gobierna esta cartera.
    """
    if PRICE_CACHE.exists():
        try:
            cached = pd.read_parquet(PRICE_CACHE)
            edad = (pd.Timestamp.today().normalize() - cached.index.max()).days
            if edad <= CACHE_MAX_STALE_DAYS:
                return cached
            print(f"  (caché de precios con {edad} días, refrescando)")
        except Exception:
            pass
    import yfinance as yf
    raw = yf.download(["SPY", "^VIX"], start=start, auto_adjust=True,
                      progress=False, group_by="ticker")
    out = pd.DataFrame({
        "SPY": raw["SPY"]["Close"],
        "VIX": raw["^VIX"]["Close"],
    }).dropna(how="all").sort_index()
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    PRICE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PRICE_CACHE)
    return out


def _load() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    macro = pd.read_parquet(PROCESSED / "macro_history.parquet")
    macro = macro[macro["mode"] == MACRO_MODE].sort_index()
    prices = _fetch_daily_prices()
    # FRED publica el spread HY en puntos porcentuales; el resto del sistema
    # trabaja en puntos básicos (mismo ajuste que duration_monitor.py).
    hy = (pd.read_parquet(PROCESSED / "macro_daily.parquet")["BAMLH0A0HYM2"]
          .dropna().sort_index() * 100.0)
    return macro, prices, hy


_CACHE: tuple[pd.DataFrame, pd.DataFrame, pd.Series] | None = None


def _data() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load()
    return _CACHE


def _f(row: pd.Series, col: str) -> float | None:
    """Valor float o None si falta/NaN — nunca un 0 silencioso."""
    if col not in row.index:
        return None
    v = row[col]
    return None if pd.isna(v) else float(v)


def macro_inputs_at(when: str | _date) -> MacroInputs:
    """Estado macro tal como se veía en esa fecha, sin datos posteriores.

    Todas las ventanas móviles se calculan sobre la serie ya truncada en `when`.
    Es la misma disciplina que le exigimos a su `as_of_date`: filtrar su corpus
    por fecha no sirve de nada si el estado que le enviamos lleva dentro datos
    del futuro.
    """
    ts = pd.Timestamp(when)
    macro, prices, hy = _data()

    m_hist = macro.loc[:ts]
    if m_hist.empty:
        raise ValueError(f"Sin datos macro en o antes de {ts.date()}")
    row = m_hist.iloc[-1]

    # ── Precio y tendencia (diario) ──
    spy = prices["SPY"].dropna().loc[:ts]
    spy_high = spy_sma = spy_ret = None
    if len(spy) >= 2:
        last = float(spy.iloc[-1])
        high = float(spy.iloc[-HIGH_DAYS:].max())
        spy_high = (last / high - 1.0) * 100.0 if high else None
        if len(spy) >= SMA_DAYS:
            sma = float(spy.iloc[-SMA_DAYS:].mean())
            spy_sma = (last / sma - 1.0) * 100.0 if sma else None
        if len(spy) > RET_DAYS:
            prev = float(spy.iloc[-(RET_DAYS + 1)])
            spy_ret = (last / prev - 1.0) * 100.0 if prev else None

    # ── Volatilidad (diario) ──
    vix_s = prices["VIX"].dropna().loc[:ts]
    vix = float(vix_s.iloc[-1]) if len(vix_s) else None
    vix_d2w = None
    if len(vix_s) > VIX_DELTA_DAYS:
        vix_d2w = float(vix_s.iloc[-1]) - float(vix_s.iloc[-(VIX_DELTA_DAYS + 1)])

    # ── Crédito (diario) ──
    hy_s = hy.loc[:ts]
    hy_bps = float(hy_s.iloc[-1]) if len(hy_s) else None
    hy_d4w = None
    if len(hy_s) > HY_DELTA_DAYS:
        hy_d4w = float(hy_s.iloc[-1]) - float(hy_s.iloc[-(HY_DELTA_DAYS + 1)])

    # ── Liquidez y régimen propio (semanal — es su cadencia real) ──
    score_d4 = None
    score = _f(row, "macro_score")
    if score is not None and len(m_hist) > 4:
        prev_score = _f(m_hist.iloc[-5], "macro_score")
        if prev_score is not None:
            score_d4 = score - prev_score

    infl = row.get("flag_inflation_overlay")
    return MacroInputs(
        vix=vix,
        vix_d2w=vix_d2w,
        hy_bps=hy_bps,
        hy_d4w=hy_d4w,
        netliq_d4w=_f(row, "netliq_d4w"),
        netliq_d8w=_f(row, "netliq_d8w"),
        spy_vs_high_pct=spy_high,
        spy_vs_sma200_pct=spy_sma,
        spy_ret_4w_pct=spy_ret,
        inflation_overlay=bool(infl) if not pd.isna(infl) else False,
        macro_regime=row.get("regime"),
        macro_score_delta_4w=score_d4,
    )


def trading_dates(start: str, end: str) -> list[pd.Timestamp]:
    _, prices, _ = _data()
    return list(prices["SPY"].dropna().loc[start:end].index)


def state_series(start: str, end: str) -> pd.DataFrame:
    """Un estado codificado por sesión. Base de la Prueba 1C."""
    rows = []
    for ts in trading_dates(start, end):
        i = macro_inputs_at(ts)
        s = build_market_state(i)
        rows.append({
            "date": ts.date(),
            "regime_propio": i.macro_regime,
            **{k: (",".join(v) if isinstance(v, list) else v) for k, v in s.items()},
        })
    return pd.DataFrame(rows).set_index("date")


# ── Episodios de referencia (verificados contra SPY real) ──────────────────
STRESS_EPISODES = {
    "2024-04-26": "SPY -5.4%",
    "2024-08-09": "SPY -8.4%",
    "2025-04-06": "SPY -18.8% — el mayor desde 2024, corpus ciego (4 frames)",
    "2025-11-21": "SPY -5.1%",
    "2026-03-29": "SPY -8.9% — único con corpus denso (32 frames)",
}


def _cli() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--episodes":
        for d, label in STRESS_EPISODES.items():
            print(f"\n{'='*66}\n{d}  ({label})\n{'='*66}")
            print(explain(macro_inputs_at(d)))
        return
    if args and args[0] == "--series":
        start = args[1] if len(args) > 1 else "2024-01-01"
        end = args[2] if len(args) > 2 else "2026-07-31"
        df = state_series(start, end)
        print(df.to_string())
        return
    when = args[0] if args else "2026-07-31"
    i = macro_inputs_at(when)
    print(f"=== Estado macro reconstruido — {when} ===\n")
    print(f"  VIX {i.vix} (d2w {i.vix_d2w})   HY {i.hy_bps}bps (d4w {i.hy_d4w})")
    print(f"  SPY vs max52s {i.spy_vs_high_pct:.1f}%   vs media {i.spy_vs_sma200_pct:.1f}%   4s {i.spy_ret_4w_pct:+.1f}%"
          if i.spy_vs_high_pct is not None else "  SPY sin datos")
    print(f"  Régimen propio: {i.macro_regime}  (delta score 4s: {i.macro_score_delta_4w})\n")
    print(explain(i))


if __name__ == "__main__":
    _cli()
