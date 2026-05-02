"""
FRED fetcher con retry y backoff exponencial.
Usa fredapi si está disponible; hace fallback a requests directo si no.
Descarga y guarda en data/raw/fred_{series_id}.parquet
"""

import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

RETRY_DELAYS = [2, 4, 8]
FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"


def _get_api_key() -> str:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise EnvironmentError(
            "FRED_API_KEY no está configurada. "
            "Crea un archivo .env con FRED_API_KEY=tu_clave "
            "o expórtala como variable de entorno. "
            "Obtén tu clave gratuita en: https://fred.stlouisfed.org/docs/api/api_key.html"
        )
    return key


def _fetch_via_requests(series_id: str, start: str, end: str, api_key: str) -> pd.DataFrame:
    """Descarga una serie FRED directamente via HTTP."""
    params = {
        "series_id": series_id,
        "observation_start": start,
        "observation_end": end,
        "api_key": api_key,
        "file_type": "json",
        "units": "lin",
    }
    resp = requests.get(FRED_API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "observations" not in data:
        raise ValueError(f"Respuesta inesperada de FRED para {series_id}: {data.get('error_message', data)}")

    rows = [
        {"date": obs["date"], "value": obs["value"]}
        for obs in data["observations"]
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    # FRED devuelve "." para valores faltantes
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.set_index("date").sort_index()
    df["series_id"] = series_id
    return df


def fetch_series(
    series_id: str,
    start: str,
    end: str,
    raw_dir: Path,
) -> pd.DataFrame | None:
    """
    Descarga una serie de FRED y la guarda en raw_dir.

    Returns:
        DataFrame con columnas ['value', 'series_id'], indexed por date, o None si falló.
    """
    api_key = _get_api_key()
    out_path = raw_dir / f"fred_{series_id}.parquet"

    t0 = time.time()
    df = None

    for attempt, delay in enumerate([0] + RETRY_DELAYS, start=1):
        if delay:
            logger.warning(f"  [{series_id}] reintento {attempt}/4 en {delay}s…")
            time.sleep(delay)
        try:
            df = _fetch_via_requests(series_id, start, end, api_key)
            break
        except Exception as exc:
            logger.warning(f"  [{series_id}] intento {attempt} falló: {exc}")

    elapsed = time.time() - t0

    if df is None or df.empty:
        logger.error(f"  [{series_id}] DESCARGA FALLIDA tras {len(RETRY_DELAYS)+1} intentos ({elapsed:.1f}s)")
        return None

    # Asegurar índice limpio
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"

    df.to_parquet(out_path, index=True)

    first = df.index.min().date()
    last  = df.index.max().date()
    nan_count = int(df["value"].isna().sum())
    logger.info(
        f"  [{series_id}] {len(df)} filas | {first} -> {last} | "
        f"NaN: {nan_count} | {elapsed:.1f}s -> {out_path.name}"
    )

    return df


def fetch_all_fred(config: dict, raw_dir: Path, start: str, end: str) -> tuple[dict, list]:
    """
    Descarga todas las series FRED definidas en config['fred'].

    Returns:
        (results: dict {series_id: DataFrame}, failed: list[str])
    """
    results: dict[str, pd.DataFrame] = {}
    failed: list[str] = []

    all_series = (
        config["fred"].get("daily", [])
        + config["fred"].get("weekly", [])
        + config["fred"].get("monthly", [])
    )

    logger.info(f"FRED: descargando {len(all_series)} series [{start} -> {end}]")

    for item in all_series:
        sid = item["series_id"]
        df = fetch_series(sid, start, end, raw_dir)
        if df is not None:
            results[sid] = df
        else:
            failed.append(sid)

    if failed:
        logger.warning(f"Series con fallo en FRED: {failed}")

    return results, failed
