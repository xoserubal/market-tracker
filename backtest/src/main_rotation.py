"""
Entrypoint para Entrega 3: RotationScore + señales históricas.

Uso:
  cd backtest
  py src/main_rotation.py [--mode A|B|both] [--validate]

Produce:
  data/processed/prices_daily.parquet
  data/processed/rotation_history.parquet
  data/processed/cluster_health_history.parquet
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Ajustar sys.path para imports relativos
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rotation.clusters import TICKERS_NO_SPY
from src.rotation.indicators import load_daily_ohlcv
from src.rotation.simulator import simulate_rotation_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE   = Path(__file__).parent.parent
DATA   = BASE / "data"
PROC   = DATA / "processed"
RAW    = DATA / "raw"

ALL_TICKERS = TICKERS_NO_SPY + ['SPY']


def build_prices_daily() -> pd.DataFrame:
    """
    Construye (o carga del cache) prices_daily.parquet con close diario
    de todos los tickers. Reporta fecha de inicio por ticker.
    """
    out_path = PROC / "prices_daily.parquet"

    logger.info("Construyendo prices_daily.parquet desde raws...")
    frames = {}
    for ticker in ALL_TICKERS + ['DX-Y.NYB']:
        ohlcv = load_daily_ohlcv(ticker, RAW)
        if ohlcv is None or ohlcv.empty:
            logger.warning(f"  [{ticker}] sin datos diarios")
            continue
        frames[ticker] = ohlcv['close']
        logger.info(f"  [{ticker}] {ohlcv.index.min().date()} — {ohlcv.index.max().date()} ({len(ohlcv)} dias)")

    pd_df = pd.DataFrame(frames)
    pd_df.index.name = 'date'
    pd_df.to_parquet(out_path)
    logger.info(f"  Guardado: {out_path}  shape={pd_df.shape}")
    return pd_df


def load_data() -> dict:
    logger.info("Cargando datos...")
    mh  = pd.read_parquet(PROC / "macro_history.parquet")
    md  = pd.read_parquet(PROC / "macro_daily.parquet")
    logger.info(f"  macro_history:  {mh.shape}")
    logger.info(f"  macro_daily:    {md.shape}")

    pd_path = PROC / "prices_daily.parquet"
    if pd_path.exists():
        pd_df = pd.read_parquet(pd_path)
        logger.info(f"  prices_daily:   {pd_df.shape} (cache)")
    else:
        pd_df = build_prices_daily()

    return {'prices_daily': pd_df, 'macro_history': mh, 'macro_daily': md}


def run_mode(data: dict, mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    return simulate_rotation_history(
        prices_daily  = data['prices_daily'],
        macro_history = data['macro_history'],
        macro_daily   = data['macro_daily'],
        raw_dir       = RAW,
        mode          = mode,
    )


def print_validation_report(rotation_df: pd.DataFrame, mode: str) -> None:
    """
    Compara la última semana disponible contra el snapshot de la app (2026-04-17).
    Ground truth del checkpoint 0.3.
    """
    GROUND_TRUTH = {
        'XLF':     {'score': 3,  'blockA': 0, 'blockB': 1, 'blockC': 2, 'signal': 'VIGILAR',  'fit': True},
        'XLI':     {'score': 3,  'blockA': 1, 'blockB': 0, 'blockC': 2, 'signal': 'VIGILAR',  'fit': True},
        'TLT':     {'score': 3,  'blockA': 0, 'blockB': 0, 'blockC': 3, 'signal': 'VIGILAR',  'fit': False},
        'XLC':     {'score': 4,  'blockA': 1, 'blockB': 1, 'blockC': 2, 'signal': 'VIGILAR',  'fit': False},
        'XLE':     {'score': 4,  'blockA': 3, 'blockB': 1, 'blockC': 0, 'signal': 'VIGILAR',  'fit': True},
        'XLV':     {'score': 4,  'blockA': 1, 'blockB': 0, 'blockC': 3, 'signal': 'VIGILAR',  'fit': False},
        'IWM':     {'score': 4,  'blockA': 2, 'blockB': 1, 'blockC': 1, 'signal': 'VIGILAR',  'fit': False},
        'XLY':     {'score': 5,  'blockA': 2, 'blockB': 1, 'blockC': 2, 'signal': 'VIGILAR',  'fit': False},
        'XLB':     {'score': 5,  'blockA': 3, 'blockB': 0, 'blockC': 2, 'signal': 'ACUMULAR', 'fit': True},
        'XLRE':    {'score': 5,  'blockA': 3, 'blockB': 1, 'blockC': 1, 'signal': 'VIGILAR',  'fit': False},
        'XLP':     {'score': 5,  'blockA': 1, 'blockB': 1, 'blockC': 3, 'signal': 'VIGILAR',  'fit': False},
        'QQQ':     {'score': 5,  'blockA': 2, 'blockB': 2, 'blockC': 1, 'signal': 'VIGILAR',  'fit': False},
        'SI=F':    {'score': 5,  'blockA': 2, 'blockB': 0, 'blockC': 3, 'signal': 'ACUMULAR', 'fit': True},
        'BZ=F':    {'score': 5,  'blockA': 3, 'blockB': 1, 'blockC': 1, 'signal': 'ACUMULAR', 'fit': True},
        'XLK':     {'score': 7,  'blockA': 4, 'blockB': 2, 'blockC': 1, 'signal': 'VIGILAR',  'fit': False},
        'XLU':     {'score': 7,  'blockA': 3, 'blockB': 2, 'blockC': 2, 'signal': 'VIGILAR',  'fit': False},
        'GC=F':    {'score': 7,  'blockA': 1, 'blockB': 3, 'blockC': 3, 'signal': 'VIGILAR',  'fit': False},
        'EEM':     {'score': 8,  'blockA': 4, 'blockB': 2, 'blockC': 2, 'signal': 'VIGILAR',  'fit': False},
        'BTC-USD': {'score': 8,  'blockA': 3, 'blockB': 2, 'blockC': 3, 'signal': 'VIGILAR',  'fit': False},
    }

    TARGET_DATE = pd.Timestamp('2026-04-17')
    # Use TARGET_DATE if available, otherwise last date that has full ticker coverage
    available = rotation_df.index.unique()
    if TARGET_DATE in available:
        snap_date = TARGET_DATE
    else:
        snap_date = rotation_df.index.max()

    print(f"\n{'='*72}")
    print(f"VALIDACION CRUZADA vs APP - modo {mode} - fecha snapshot: {snap_date.date()}")
    print(f"{'='*72}")

    df_last = rotation_df[rotation_df.index == snap_date].copy()
    if df_last.empty:
        print("  Sin datos en la última fecha")
        return

    mismatches = []
    header = f"{'Ticker':<10} {'Score':>5} {'AppSc':>5} {'d':>4} | {'A':>2} {'B':>2} {'C':>2} | {'Signal':<14} {'AppSig':<14} | {'Fit':>3} {'AppFit':>6}"
    print(header)
    print('-' * len(header))

    for ticker, gt in sorted(GROUND_TRUTH.items()):
        row = df_last[df_last['ticker'] == ticker]
        if row.empty:
            print(f"  {ticker:<10} SIN DATOS")
            continue
        row = row.iloc[0]

        sc   = row['rot_score']
        blkA = (row['rs_13w_pts'] or 0) + (row['rs_4w_pts'] or 0) + (row['trend_abs_pts'] or 0)
        blkB = (row['cmf_pts'] or 0) + (row['obv_pts'] or 0) + (row['vol_rel_pts'] or 0)
        blkC = (row['macd_pts'] or 0) + (row['rsi_pts'] or 0) + (row['no_ext_pts'] or 0)

        sc_str  = f"{sc:.1f}" if sc is not None else "-"
        delta   = f"{sc - gt['score']:+.1f}" if sc is not None else "?"
        sig     = row['signal'] or '-'
        fit_str = 'Y' if row['fit'] else 'N'

        ok_score  = sc is not None and abs(sc - gt['score']) <= 0.5
        ok_signal = sig == gt['signal']
        ok_fit    = bool(row['fit']) == gt['fit']

        flag = '' if (ok_score and ok_signal and ok_fit) else ' [!]'
        if not (ok_score and ok_signal and ok_fit):
            mismatches.append(ticker)

        print(
            f"{ticker:<10} {sc_str:>5} {gt['score']:>5} {delta:>4} | "
            f"{int(blkA):>2} {int(blkB):>2} {int(blkC):>2} | "
            f"{sig:<14} {gt['signal']:<14} | "
            f"{fit_str:>3} {'Y' if gt['fit'] else 'N':>6}"
            f"{flag}"
        )

    print()
    if mismatches:
        print(f"  [!] Divergencias en: {', '.join(mismatches)}")
        print("  Diagnostico recomendado: ver S12.3 del brief (CMF daily vs weekly, MACD EMA, etc.)")
    else:
        print("  [OK] Validacion cruzada PASADA - todos los tickers dentro de tolerancia")


def print_summary_report(rotation_df: pd.DataFrame, cluster_df: pd.DataFrame, mode: str) -> None:
    print(f"\n{'='*60}")
    print(f"REPORTE RESUMEN - modo {mode}")
    print(f"{'='*60}")

    # Distribucion de senales
    sig_counts = rotation_df['signal'].fillna('IGNORAR').value_counts()
    total = len(rotation_df)
    print("\nDistribucion de senales:")
    for sig, cnt in sig_counts.items():
        print(f"  {sig:<16} {cnt:>6} ({100*cnt/total:.1f}%)")

    # Senales ROT. TEMPRANA
    er_rows = rotation_df[rotation_df['is_early_rotation'] == True]
    print(f"\nSenales ROT. TEMPRANA emitidas: {len(er_rows)}")
    if len(er_rows) > 0:
        for idx, r in er_rows.sort_index().iterrows():
            print(f"  {idx.date()}  {r['ticker']:<10}  cluster:{r['cluster']}  "
                  f"peers:{r['er_cluster_peers']}  via:{r['er_benchmark_condition']}")

    # Sanity checks
    print("\nSanity checks:")
    buys_xle_2022 = rotation_df[
        (rotation_df['ticker'] == 'XLE') &
        (rotation_df.index.year == 2022) &
        (rotation_df['signal'].isin(['COMPRA', 'ACUMULAR']))
    ]
    print(f"  XLE senales COMPRA/ACUMULAR en 2022: {len(buys_xle_2022)} "
          f"{'[OK]' if len(buys_xle_2022) > 0 else '[!]'}")

    buys_xlk_2021 = rotation_df[
        (rotation_df['ticker'] == 'XLK') &
        (rotation_df.index.year == 2021) &
        (rotation_df['signal'] == 'COMPRA')
    ]
    print(f"  XLK senales COMPRA en 2021:          {len(buys_xlk_2021)} "
          f"{'[OK]' if len(buys_xlk_2021) > 0 else '[!]'}")

    # Cluster health media
    print("\nAvg RotationScore por cluster (ultimo anio):")
    last_year = cluster_df[cluster_df.index >= cluster_df.index.max() - pd.DateOffset(years=1)]
    for cluster in last_year['cluster'].unique():
        avg = last_year[last_year['cluster'] == cluster]['avg_rotation_score'].mean()
        print(f"  {cluster:<16} {avg:.2f}" if avg is not None else f"  {cluster:<16} -")


def main():
    parser = argparse.ArgumentParser(description='Entrega 3: RotationScore histórico')
    parser.add_argument('--mode', choices=['A', 'B', 'both'], default='both')
    parser.add_argument('--validate', action='store_true', help='Mostrar reporte de validación vs app')
    parser.add_argument('--no-save', action='store_true', help='No guardar parquets')
    args = parser.parse_args()

    data   = load_data()
    modes  = ['A', 'B'] if args.mode == 'both' else [args.mode]

    all_rotation = []
    all_cluster  = []

    for mode in modes:
        logger.info(f"\n{'─'*50}")
        logger.info(f"Modo {mode}")
        rot_df, cl_df = run_mode(data, mode)
        all_rotation.append(rot_df)
        all_cluster.append(cl_df)

        if args.validate:
            print_validation_report(rot_df, mode)

        print_summary_report(rot_df, cl_df, mode)

    # Concatenar ambos modos
    rotation_full = pd.concat(all_rotation).sort_index()
    cluster_full  = pd.concat(all_cluster).sort_index()

    logger.info(f"\nTotal rotation_history: {rotation_full.shape}")
    logger.info(f"Total cluster_health:    {cluster_full.shape}")

    if not args.no_save:
        rot_out = PROC / "rotation_history.parquet"
        cl_out  = PROC / "cluster_health_history.parquet"
        rotation_full.to_parquet(rot_out)
        cluster_full.to_parquet(cl_out)
        logger.info(f"Guardado: {rot_out}")
        logger.info(f"Guardado: {cl_out}")
    else:
        logger.info("--no-save: parquets no guardados")


if __name__ == '__main__':
    main()
