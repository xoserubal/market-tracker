"""
Procesadores de alineación temporal.

Genera tres datasets consolidados en data/processed/:
  - prices_weekly.parquet  : cierres semanales (viernes) de los 20 activos + VIX + DXY
  - macro_daily.parquet    : series FRED diarias alineadas con forward-fill ≤5 días
  - macro_weekly.parquet   : series semanales/mensuales + NetLiq calculado
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Columna de precio que Yahoo fetcher añade en cada DataFrame
PRICE_COL = "price"

# Series que van en macro_daily
MACRO_DAILY_SERIES = ["BAMLH0A0HYM2", "T10Y3M", "T5YIE", "DFII10", "THREEFYTP10", "RRPONTSYD"]

# Series que van en macro_weekly (alineadas a viernes)
MACRO_WEEKLY_SERIES = ["WALCL", "WTREGEN", "CFNAI"]


def _last_friday_of_week(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Retorna las fechas de viernes que cierran cada semana natural."""
    return dates[dates.weekday == 4]


def build_prices_weekly(
    yahoo_data: dict[str, pd.DataFrame],
    asset_tickers: list[str],
    index_tickers: list[str],
    processed_dir: Path,
) -> pd.DataFrame:
    """
    Construye prices_weekly.parquet con cierres semanales (viernes).

    Para cada ticker, toma el valor de "price" del último día hábil
    de cada semana (si el viernes es festivo, usa el jueves o miércoles).
    """
    all_tickers = asset_tickers + index_tickers
    series: dict[str, pd.Series] = {}

    for ticker in all_tickers:
        df = yahoo_data.get(ticker)
        if df is None or PRICE_COL not in df.columns:
            logger.warning(f"  prices_weekly: datos no disponibles para {ticker}, columna vacía")
            series[ticker] = pd.Series(dtype=float, name=ticker)
            continue

        s = df[PRICE_COL].copy()
        s.index = pd.to_datetime(s.index).normalize()  # eliminar hora si la hubiera
        # Resample a semanal tomando el último valor disponible de cada semana
        # W-FRI: semana termina en viernes
        weekly = s.resample("W-FRI").last()
        series[ticker] = weekly

    # Combinar todas las series en un DataFrame
    prices_w = pd.DataFrame(series)
    prices_w.index.name = "date"
    prices_w = prices_w.sort_index()

    # Eliminar filas donde TODOS los valores son NaN
    prices_w = prices_w.dropna(how="all")

    out = processed_dir / "prices_weekly.parquet"
    prices_w.to_parquet(out, index=True)
    logger.info(
        f"  prices_weekly: {prices_w.shape[0]} semanas x {prices_w.shape[1]} activos | "
        f"{prices_w.index.min().date()} -> {prices_w.index.max().date()} -> {out.name}"
    )
    return prices_w


def build_macro_daily(
    fred_data: dict[str, pd.DataFrame],
    processed_dir: Path,
    max_ffill_days: int = 5,
) -> pd.DataFrame:
    """
    Construye macro_daily.parquet con series FRED diarias alineadas.

    Forward-fill máximo max_ffill_days días para gaps puntuales (fines de semana,
    festivos, datos tardíos). Los gaps más largos quedan como NaN.
    """
    series: dict[str, pd.Series] = {}

    for sid in MACRO_DAILY_SERIES:
        df = fred_data.get(sid)
        if df is None:
            logger.warning(f"  macro_daily: {sid} no disponible, columna vacía")
            series[sid] = pd.Series(dtype=float, name=sid)
            continue

        s = df["value"].copy()
        s.index = pd.to_datetime(s.index).normalize()
        s.name = sid
        series[sid] = s

    if not series:
        raise RuntimeError("macro_daily: ninguna serie FRED disponible")

    # Crear índice de días hábiles desde el mínimo al máximo disponible
    all_dates = sorted(
        {d for s in series.values() if not s.empty for d in s.index}
    )
    if not all_dates:
        raise RuntimeError("macro_daily: sin fechas válidas en las series")

    biz_index = pd.bdate_range(start=all_dates[0], end=all_dates[-1])
    macro_d = pd.DataFrame(index=biz_index)
    macro_d.index.name = "date"

    for sid, s in series.items():
        if s.empty:
            macro_d[sid] = float("nan")
            continue
        # Reindexar al calendario hábil y forward-fill limitado
        macro_d[sid] = s.reindex(biz_index).ffill(limit=max_ffill_days)

    out = processed_dir / "macro_daily.parquet"
    macro_d.to_parquet(out, index=True)
    logger.info(
        f"  macro_daily: {macro_d.shape[0]} dias habiles x {macro_d.shape[1]} series | "
        f"{macro_d.index.min().date()} -> {macro_d.index.max().date()} -> {out.name}"
    )
    return macro_d


def build_macro_weekly(
    fred_data: dict[str, pd.DataFrame],
    processed_dir: Path,
) -> pd.DataFrame:
    """
    Construye macro_weekly.parquet con series semanales/mensuales alineadas a viernes.

    WALCL y WTREGEN: semanales, se alinean directamente.
    CFNAI: mensual, se forward-fill dentro del mes (valor constante hasta siguiente publicación).
    NetLiq = WALCL - RRPONTSYD - WTREGEN se añade como columna derivada.
    RRPONTSYD (diaria) se toma del viernes correspondiente.
    """
    weekly_frames: dict[str, pd.Series] = {}

    # ── Semanales: WALCL, WTREGEN ─────────────────────────────────────────────
    for sid in ["WALCL", "WTREGEN"]:
        df = fred_data.get(sid)
        if df is None:
            logger.warning(f"  macro_weekly: {sid} no disponible, columna vacía")
            weekly_frames[sid] = pd.Series(dtype=float, name=sid)
            continue
        s = df["value"].copy()
        s.index = pd.to_datetime(s.index).normalize()
        s.name = sid
        # Resamplear a viernes: tomar el último valor de cada semana
        weekly_frames[sid] = s.resample("W-FRI").last()

    # ── Mensual: CFNAI ────────────────────────────────────────────────────────
    cfnai_df = fred_data.get("CFNAI")
    if cfnai_df is not None:
        s = cfnai_df["value"].copy()
        s.index = pd.to_datetime(s.index).normalize()
        s.name = "CFNAI"
        # Forward-fill mensual a viernes: el valor se mantiene hasta el siguiente
        weekly_frames["CFNAI"] = s.resample("W-FRI").last().ffill()
    else:
        logger.warning("  macro_weekly: CFNAI no disponible, columna vacía")
        weekly_frames["CFNAI"] = pd.Series(dtype=float, name="CFNAI")

    # ── Construir DataFrame semanal base ──────────────────────────────────────
    macro_w = pd.DataFrame(weekly_frames)
    macro_w.index.name = "date"
    macro_w = macro_w.sort_index().dropna(how="all")

    # ── RRPONTSYD (diaria) → valor del viernes ────────────────────────────────
    rrp_df = fred_data.get("RRPONTSYD")
    if rrp_df is not None:
        rrp = rrp_df["value"].copy()
        rrp.index = pd.to_datetime(rrp.index).normalize()
        # Resamplear a viernes: último valor disponible de esa semana
        rrp_weekly = rrp.resample("W-FRI").last()
        macro_w["RRPONTSYD"] = rrp_weekly.reindex(macro_w.index)
    else:
        logger.warning("  macro_weekly: RRPONTSYD no disponible, NetLiq será NaN")
        macro_w["RRPONTSYD"] = float("nan")

    # ── Net Liquidity: WALCL - RRPONTSYD - WTREGEN (todo en USD millions) ────
    macro_w["NetLiq"] = macro_w["WALCL"] - macro_w["RRPONTSYD"] - macro_w["WTREGEN"]

    out = processed_dir / "macro_weekly.parquet"
    macro_w.to_parquet(out, index=True)

    netliq_valid = macro_w["NetLiq"].notna().sum()
    logger.info(
        f"  macro_weekly: {macro_w.shape[0]} semanas x {macro_w.shape[1]} columnas | "
        f"{macro_w.index.min().date()} -> {macro_w.index.max().date()} | "
        f"NetLiq valido: {netliq_valid} semanas -> {out.name}"
    )
    return macro_w
