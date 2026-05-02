"""
Orquestador de Entrega 2: MacroScore histórico en modos A y B.

Uso:
    cd backtest
    py -m src.main_macro
"""
from __future__ import annotations
import sys
import os
import pandas as pd

# Añadir raíz del proyecto al path para imports relativos
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.macro.simulator import simulate_history

DATA_DIR   = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed')
OUTPUT_PATH = os.path.join(DATA_DIR, 'macro_history.parquet')

# Ground truth de la app (snapshot 2026-04-18 02:09)
APP_GROUND_TRUTH = {
    'date':        '2026-04-17',
    'macro_score':  71.0,
    'hy_pts':       25.0,
    'netliq_pts':   12.5,
    'vol_pts':      15.0,
    'curva_pts':    11.25,   # app muestra 11.3 (redondeado)
    'cfnai_pts':     7.5,
    'regime':       'Bull Maduro',
    'flag_credit_complacency':   False,
    'flag_inflation_overlay':    False,
    'flag_term_premium_extreme': False,
    'flag_emergency_mode':       False,
}

TOLERANCES = {
    'hy_pts': 0.5, 'netliq_pts': 0.5, 'vol_pts': 0.5,
    'curva_pts': 0.5, 'cfnai_pts': 0.5, 'macro_score': 1.0,
}


def load_data() -> dict:
    return {
        'prices_weekly': pd.read_parquet(os.path.join(DATA_DIR, 'prices_weekly.parquet')),
        'macro_daily':   pd.read_parquet(os.path.join(DATA_DIR, 'macro_daily.parquet')),
        'macro_weekly':  pd.read_parquet(os.path.join(DATA_DIR, 'macro_weekly.parquet')),
        'hy_real':       pd.read_parquet(os.path.join(DATA_DIR, 'hy_spread_real_only.parquet')),
    }


def validate_vs_app(df: pd.DataFrame, mode: str = 'A') -> None:
    ref_date = pd.Timestamp(APP_GROUND_TRUTH['date'])
    if ref_date not in df.index:
        print(f"  ⚠ Fecha {ref_date.date()} no encontrada en el output.")
        return

    row = df.loc[ref_date]
    print(f"\n=== Validación cruzada vs app (Modo {mode}, fecha {ref_date.date()}) ===")

    all_pass = True
    numeric_fields = ['hy_pts', 'netliq_pts', 'vol_pts', 'curva_pts', 'cfnai_pts', 'macro_score']
    for field in numeric_fields:
        expected = APP_GROUND_TRUTH[field]
        actual   = row.get(field, None)
        tol      = TOLERANCES[field]
        if actual is None:
            status = "!! None"
            all_pass = False
        elif abs(actual - expected) <= tol:
            status = "OK"
        else:
            status = f"FAIL  (diff={actual - expected:+.2f})"
            all_pass = False
        print(f"  {field:<20} app={expected:>6.2f}  py={actual!r:>8}  {status}")

    # Flags y regimen (exacto)
    for field in ['regime', 'flag_credit_complacency', 'flag_inflation_overlay',
                  'flag_term_premium_extreme', 'flag_emergency_mode']:
        expected = APP_GROUND_TRUTH[field]
        actual   = row.get(field, None)
        ok = actual == expected
        if not ok:
            all_pass = False
        print(f"  {field:<30} app={str(expected):<10} py={str(actual):<10} {'OK' if ok else 'FAIL'}")

    if all_pass:
        print("\n  [PASS] VALIDACION APROBADA")
    else:
        print("\n  [DIFF] VALIDACION CON DIFERENCIAS -- revisar antes de cerrar entrega")
        _print_validation_notes(row)


def _print_validation_notes(row: pd.Series) -> None:
    """Imprime hipótesis de causa para diferencias conocidas."""
    netliq_actual   = row.get('netliq_pts')
    netliq_expected = APP_GROUND_TRUTH['netliq_pts']
    if netliq_actual is not None and abs(netliq_actual - netliq_expected) > 0.5:
        print(
            "\n  [NetLiq] HIPOTESIS: diferencia de vintage de datos FRED.\n"
            "  La app consulta FRED live (con revisiones recientes de WALCL/WTREGEN).\n"
            "  El parquet es un snapshot historico. Ejemplo:\n"
            "    Python 2026-01-16 NetLiq = 5,802,524 M -> delta = +152B -> 18.75 pts\n"
            "    App live (revisado) -> delta aprox -1B -> 12.5 pts\n"
            "  Esta discrepancia es ESPERADA en el ultimo punto; no afecta la logica.\n"
        )


def print_summary(df: pd.DataFrame) -> None:
    print("\n=== RESUMEN MACRO HISTORY ===")
    for mode in ['A', 'B']:
        sub = df[df['mode'] == mode]
        print(f"\n-- Modo {mode} --")
        print(f"  Filas: {len(sub)}")
        print(f"  Rango: {sub.index.min().date()} -> {sub.index.max().date()}")

        # Distribucion de regimen
        regime_pct = sub['regime'].value_counts(normalize=True) * 100
        print("  Distribucion regimen:")
        for reg, pct in regime_pct.items():
            print(f"    {reg:<16} {pct:5.1f}%")

        # Reliability
        rel = sub['reliability'].value_counts(normalize=True) * 100
        print("  Reliability:")
        for r, pct in rel.items():
            if r is not None:
                print(f"    {r:.2f}  ->  {pct:5.1f}%")

        # Activaciones de flags
        for flag in ['flag_credit_complacency','flag_inflation_overlay',
                     'flag_term_premium_extreme','flag_emergency_mode']:
            n = sub[flag].astype(bool).sum()
            print(f"  {flag}: {n} semanas activo")

    # Sanity checks
    print("\n-- Sanity checks --")
    modeA = df[df['mode'] == 'A']
    bull_2021 = modeA.loc['2021-01-01':'2021-12-31']['regime'].value_counts()
    print(f"  2021 regímenes: {bull_2021.to_dict()}")

    crisis_2020 = modeA.loc['2020-02-21':'2020-04-30']['regime'].value_counts()
    print(f"  Feb-Apr 2020 regímenes: {crisis_2020.to_dict()}")

    infl_2022 = modeA.loc['2021-01-01':'2023-06-30']['flag_inflation_overlay'].astype(bool).sum()
    print(f"  INFLATION_OVERLAY activo en 2021-2023: {infl_2022} semanas")


def main():
    print("Cargando datos...")
    data = load_data()

    print("Simulando Modo A...")
    df_a = simulate_history(data, mode='A')
    print(f"  {len(df_a)} filas")

    print("Simulando Modo B...")
    df_b = simulate_history(data, mode='B')
    print(f"  {len(df_b)} filas")

    df = pd.concat([df_a, df_b]).sort_index()

    # Validación cruzada
    validate_vs_app(df_a, mode='A')

    # Resumen
    print_summary(df)

    # Guardar
    df.to_parquet(OUTPUT_PATH)
    print(f"\n[OK] Guardado: {OUTPUT_PATH}")
    print(f"   Shape: {df.shape}")
    print(f"""
Snippet de carga:
    import pandas as pd
    df = pd.read_parquet('data/processed/macro_history.parquet')
    mode_a = df[df['mode'] == 'A']
    mode_b = df[df['mode'] == 'B']
    print(mode_a.tail())
    """)


if __name__ == '__main__':
    main()
