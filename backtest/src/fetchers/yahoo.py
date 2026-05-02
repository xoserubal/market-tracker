"""
Yahoo Finance fetcher con retry y backoff exponencial.
Descarga OHLCV diario y guarda en data/raw/yahoo_{ticker_safe}.parquet
"""

import logging
import time
import re
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

RETRY_DELAYS = [2, 4, 8]   # segundos entre intentos


def _ticker_to_filename(ticker: str) -> str:
    """Convierte un ticker en nombre de archivo seguro. ^VIX9D → VIX9D, GC=F → GCF"""
    return re.sub(r"[^A-Za-z0-9_\-]", "", ticker.replace("^", "").replace("=", ""))


def fetch_ticker(
    ticker: str,
    start: str,
    end: str,
    raw_dir: Path,
    use_adj_close: bool = True,
) -> pd.DataFrame | None:
    """
    Descarga datos diarios de Yahoo para un ticker.

    Args:
        ticker:       símbolo Yahoo (e.g. "XLK", "^VIX", "GC=F")
        start:        fecha inicio "YYYY-MM-DD"
        end:          fecha fin   "YYYY-MM-DD"
        raw_dir:      directorio donde guardar el parquet
        use_adj_close: si True, añade columna "price" = Adj Close; si False, "price" = Close

    Returns:
        DataFrame con columnas OHLCV + "price", indexed por fecha, o None si falló.
    """
    safe_name = _ticker_to_filename(ticker)
    out_path = raw_dir / f"yahoo_{safe_name}.parquet"

    t0 = time.time()
    df = None

    for attempt, delay in enumerate([0] + RETRY_DELAYS, start=1):
        if delay:
            logger.warning(f"  [{ticker}] reintento {attempt}/4 en {delay}s…")
            time.sleep(delay)
        try:
            raw = yf.download(
                ticker,
                start=start,
                end=end,
                auto_adjust=False,
                progress=False,
                actions=False,
            )
            if raw is None or raw.empty:
                logger.warning(f"  [{ticker}] respuesta vacía en intento {attempt}")
                continue

            # yfinance puede devolver MultiIndex de columnas si se pasa lista de tickers
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.droplevel(1)

            # Normalizar columnas: algunos tickers devuelven nombres en minúsculas
            raw.columns = [c.title() if c.lower() != "adj close" else "Adj Close"
                           for c in raw.columns]

            # Columna de precio principal
            if use_adj_close and "Adj Close" in raw.columns:
                raw["price"] = raw["Adj Close"]
            elif "Close" in raw.columns:
                raw["price"] = raw["Close"]
            else:
                logger.warning(f"  [{ticker}] no se encontró columna Close/Adj Close")
                continue

            # Asegurar que el índice es DatetimeIndex sin timezone
            raw.index = pd.to_datetime(raw.index).tz_localize(None)
            raw.index.name = "date"

            df = raw
            break

        except Exception as exc:
            logger.warning(f"  [{ticker}] intento {attempt} falló: {exc}")

    elapsed = time.time() - t0

    if df is None or df.empty:
        logger.error(f"  [{ticker}] DESCARGA FALLIDA tras {len(RETRY_DELAYS)+1} intentos ({elapsed:.1f}s)")
        return None

    # Guardar raw
    df.to_parquet(out_path, index=True)

    first = df.index.min().date()
    last  = df.index.max().date()
    nan_price = int(df["price"].isna().sum())
    logger.info(
        f"  [{ticker}] {len(df)} filas | {first} -> {last} | "
        f"NaN precio: {nan_price} | {elapsed:.1f}s -> {out_path.name}"
    )

    return df


def fetch_all_yahoo(config: dict, raw_dir: Path, start: str, end: str) -> dict[str, pd.DataFrame]:
    """
    Descarga todos los activos e índices definidos en config['yahoo'].

    Returns:
        dict {ticker: DataFrame}, solo los que se descargaron con éxito.
    """
    results: dict[str, pd.DataFrame] = {}
    failed: list[str] = []

    all_tickers = [
        (item["ticker"], item.get("adj_close", True))
        for item in config["yahoo"].get("assets", []) + config["yahoo"].get("indices", [])
    ]

    logger.info(f"Yahoo Finance: descargando {len(all_tickers)} tickers [{start} -> {end}]")

    for ticker, adj in all_tickers:
        df = fetch_ticker(ticker, start, end, raw_dir, use_adj_close=adj)
        if df is not None:
            results[ticker] = df
        else:
            failed.append(ticker)

    if failed:
        logger.warning(f"Tickers con fallo en Yahoo: {failed}")

    return results, failed
