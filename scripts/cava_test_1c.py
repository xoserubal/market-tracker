"""
cava_test_1c.py — Prueba 1C: validación histórica de la capa determinista.

Qué mide
--------
Si `deterministic_risk_posture` del motor de Cava anticipa el comportamiento
posterior del mercado mejor que nuestro propio `MacroScore`/régimen.

Por qué se puede hacer sobre 20 años
------------------------------------
Porque la postura determinista NO depende del corpus: se deriva de la activación
de módulos y de las ~15 reglas de conflicto jerárquico, ambas en el motor.
Verificado empíricamente antes de escribir esto — misma entrada con el corpus
variando de 15 a 112 frames devuelve idéntica postura en las 8 combinaciones
probadas de `as_of_date` × `corpus_scope`.

Eso libera la prueba de la ventana del corpus (2024-04 en adelante, y con la
densidad concentrada en 2026) y permite cubrir 2008, 2011, 2020 y 2022.

Limitación que hay que tener presente al leer los resultados
------------------------------------------------------------
El spread HY solo está disponible desde 2023-08 (confirmado contra FRED). Antes
de esa fecha `credit_state` se omite, así que los módulos de crédito no se
activan y los episodios antiguos se evalúan con precio y volatilidad pero sin
crédito — que en la jerarquía de Cava es L1. El informe separa ambos tramos.

Uso
---
    py -3 scripts/cava_test_1c.py                    # 2005-2026
    # (arranca en feb-2005: macro_history empieza el 2005-01-07)
    py -3 scripts/cava_test_1c.py 2024-01-01 2026-07-31
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# La consola de Windows usa cp1252 y revienta con los caracteres de las tablas.
# Mismo arreglo que ya lleva duration_monitor.py por el mismo motivo (en GitHub
# Actions no hace falta, pero en local sí).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))

# `cava_engine` se instala como paquete desde el repo privado, fijado a un tag:
#   pip install "git+https://x-access-token:$CAVA_ENGINE_TOKEN@github.com/\
#                xoserubal/cava-decision-engine.git@v1.1.0"
# Nunca desde `main`: la versión se cambia de forma deliberada y se registra,
# porque un agente que cambia a mitad de un periodo de medición invalida los
# datos de rendimiento de ese periodo (acordado en la Ronda 2).

from cava_mapping import build_market_state  # noqa: E402
from cava_state_history import _data, macro_inputs_at, trading_dates  # noqa: E402

HORIZONS = {"1w": 5, "1m": 21, "3m": 63}
HY_START = pd.Timestamp("2023-08-01")   # antes de aquí no hay dimensión de crédito


def to_engine_inputs(flat: dict) -> dict:
    """Estado plano → formato anidado por activo canónico que espera el motor.

    La elección de activo importa: su `ASSET_TO_MODULE` activa módulos según el
    activo citado, así que colgar el crédito de HYG y la volatilidad de VIX no
    es decorativo, es lo que enciende `credito_spreads_cds` y `volatilidad`.
    """
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
    return {"inputs": inputs}


def run(start: str, end: str) -> pd.DataFrame:
    from cava_engine import core, load_corpus, query_tree

    # `as_of_date=None` es correcto aquí y no introduce sesgo: la postura
    # determinista es invariante al corpus (verificado), así que filtrarlo no
    # cambiaría el resultado. La parte que sí depende del corpus
    # (`regime_guidance`) no se usa en esta prueba.
    tree, index, timeline, meta = load_corpus(core.CORPUS_SCOPE_PILOT)

    _, prices, _ = _data()
    spy = prices["SPY"].dropna()

    cache: dict[str, str] = {}
    rows = []
    for ts in trading_dates(start, end):
        mi = macro_inputs_at(ts)
        flat = build_market_state(mi)
        key = "|".join(f"{k}={v}" for k, v in sorted(flat.items()))
        if key not in cache:
            res = query_tree(tree, index, timeline, to_engine_inputs(flat),
                             corpus_meta=meta)
            cache[key] = res.get("structural_logic", {}).get(
                "deterministic_risk_posture", "unknown")
        rows.append({
            "date": ts,
            "posture": cache[key],
            "regime_propio": mi.macro_regime,
            "vix": mi.vix,
            "spy": float(spy.loc[ts]),
            "has_credit": ts >= HY_START,
        })

    df = pd.DataFrame(rows).set_index("date")
    s = spy.reindex(df.index)
    for name, n in HORIZONS.items():
        df[f"fwd_{name}"] = (s.shift(-n) / df["spy"] - 1.0) * 100.0
    # Peor caída y volatilidad en el mes siguiente. Un marco de gestión de
    # riesgo no se juzga por el retorno medio posterior sino por el daño que
    # evita: si `risk_off` marca tramos con drawdown posterior mayor, la señal
    # sirve aunque el retorno medio a 3 meses sea bueno (los suelos rebotan).
    fwd_min = s[::-1].rolling(HORIZONS["1m"], min_periods=1).min()[::-1]
    df["fwd_dd_1m"] = (fwd_min / df["spy"] - 1.0) * 100.0
    ret = s.pct_change()
    fwd_vol = ret[::-1].rolling(HORIZONS["1m"], min_periods=5).std()[::-1]
    df["fwd_vol_1m"] = fwd_vol * (252 ** 0.5) * 100.0
    print(f"  ({len(cache)} estados distintos consultados al motor)")
    return df


_COLS = [f"fwd_{h}" for h in HORIZONS] + ["fwd_dd_1m", "fwd_vol_1m"]
_HEAD = [f"fwd {h}" for h in HORIZONS] + ["peor 1m", "vol 1m"]


def _table(df: pd.DataFrame, by: str, title: str) -> None:
    print(f"\n{title}")
    print(f"  {'valor':<24}{'n':>6}" + "".join(f"{h:>10}" for h in _HEAD))
    for val, sub in df.groupby(by):
        line = f"  {str(val):<24}{len(sub):>6}"
        for c in _COLS:
            m = sub[c].mean()
            line += f"{m:>9.2f}%" if pd.notna(m) else f"{'—':>10}"
        print(line)
    line = f"  {'[todas las sesiones]':<24}{len(df):>6}"
    for c in _COLS:
        line += f"{df[c].mean():>9.2f}%"
    print(line)


def report(df: pd.DataFrame) -> None:
    print("=" * 78)
    print(f"PRUEBA 1C — {df.index.min().date()} a {df.index.max().date()}  "
          f"({len(df)} sesiones)")
    print("=" * 78)

    _table(df, "posture", "▸ Retorno posterior del SPY según CAVA (deterministic_risk_posture)")
    _table(df, "regime_propio", "▸ Retorno posterior del SPY según NUESTRO régimen (MacroScore)")

    con = df[df.has_credit]
    if len(con) > 30:
        _table(con, "posture",
               f"▸ Solo tramo CON dimensión de crédito (desde {HY_START.date()}, {len(con)} sesiones)")

    print("\n▸ Cómo leerlo — son dos preguntas distintas, no una")
    print("  1) ¿Predice RETORNO?  Miren 'fwd 3m'. Si 'risk_on' no rinde más que")
    print("     'risk_off', la señal no sirve para decidir cuándo estar dentro.")
    print("  2) ¿Discrimina RIESGO? Miren 'peor 1m' y 'vol 1m'. Si 'risk_off'")
    print("     marca tramos con caídas y volatilidad posteriores mayores, la")
    print("     señal identifica peligro aunque el retorno medio sea bueno.")
    print("  Las dos pueden dar resultados opuestos, y de hecho lo hacen: los")
    print("  suelos son a la vez el momento más peligroso y el de mejor retorno")
    print("  posterior. Un marco de gestión de riesgo se juzga por (2).")
    print("  Y en ambos casos la vara es la misma: no si Cava acierta, sino si")
    print("  acierta MÁS que el MacroScore que ya tenemos.")


if __name__ == "__main__":
    a = sys.argv[1:]
    s, e = (a[0], a[1]) if len(a) >= 2 else ("2005-02-01", "2026-07-31")
    report(run(s, e))
