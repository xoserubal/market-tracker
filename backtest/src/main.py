"""
Pipeline principal del backtest — Entrega 1: Data Pipeline

Descarga, limpia y almacena localmente todas las series históricas necesarias
para replicar el Market Tracker v2 desde 2005-01-01 hasta hoy.

Uso:
    python src/main.py [--log-file]

Flags opcionales:
    --log-file    Además de consola, escribe el log en data/fetch.log
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv

# -- Paths ---------------------------------------------------------------------
ROOT       = Path(__file__).resolve().parent.parent
DATA_DIR   = ROOT / "data"
RAW_DIR    = DATA_DIR / "raw"
PROC_DIR   = DATA_DIR / "processed"
CONFIG_FILE = ROOT / "config" / "series.yaml"

# -- Logging setup -------------------------------------------------------------

def setup_logging(to_file: bool = False) -> None:
    # Forzar UTF-8 en stdout para compatibilidad con Windows (cp1252 por defecto)
    import io
    stdout_utf8 = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    handlers: list[logging.Handler] = [logging.StreamHandler(stdout_utf8)]
    if to_file:
        RAW_DIR.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(DATA_DIR / "fetch.log", encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

logger = logging.getLogger(__name__)


# -- Importaciones tardías (necesitan dotenv cargado antes en algunos sistemas) -
def _import_fetchers():
    from fetchers.yahoo import fetch_all_yahoo
    from fetchers.fred  import fetch_all_fred
    return fetch_all_yahoo, fetch_all_fred


def _import_processors():
    from processors.alignment import (
        build_prices_weekly,
        build_macro_daily,
        build_macro_weekly,
    )
    from processors.hy_calibration import build_hy_real_only
    return build_prices_weekly, build_macro_daily, build_macro_weekly, build_hy_real_only


# -- Sanity checks -------------------------------------------------------------

def _expected_observations(start: pd.Timestamp, end: pd.Timestamp, frequency: str) -> int:
    """Calcula el número esperado de observaciones según la frecuencia nativa de la serie."""
    if frequency == "daily":
        return len(pd.bdate_range(start, end))
    elif frequency == "weekly":
        return len(pd.date_range(start, end, freq="W-FRI"))
    elif frequency == "monthly":
        return len(pd.date_range(start, end, freq="ME"))
    else:
        raise ValueError(f"Frecuencia desconocida: {frequency}")


def _build_fred_meta(config: dict) -> dict[str, dict]:
    """
    Construye un dict {series_id: {frequency, effective_start}} desde config.
    effective_start es la fecha desde la cual aplicar el check de cobertura.
    Para series con datos esporadicos pre-inicio real de la facilidad (ej. RRPONTSYD),
    effective_start restringe el rango del denominador.
    """
    meta: dict[str, dict] = {}
    for freq_key in ("daily", "weekly", "monthly"):
        for item in config.get("fred", {}).get(freq_key, []):
            sid = item["series_id"]
            meta[sid] = {
                "frequency": freq_key,
                "effective_start": item.get("effective_start"),
            }
    return meta


def run_sanity_checks(
    yahoo_data: dict,
    fred_data:  dict,
    prices_w:   pd.DataFrame,
    macro_d:    pd.DataFrame,
    macro_w:    pd.DataFrame,
    config:     dict | None = None,
) -> list[str]:
    """
    Ejecuta los 5 checks obligatorios. Devuelve lista de mensajes de error.
    Si la lista es vacía, todo OK.
    """
    errors: list[str] = []
    fred_meta = _build_fred_meta(config) if config else {}

    # -- Check 1: Cobertura mínima >=90% en rango de disponibilidad -------------
    for ticker, df in yahoo_data.items():
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df.index)
        biz_days = len(pd.bdate_range(idx.min(), idx.max()))
        coverage = len(df) / biz_days if biz_days > 0 else 0
        if coverage < 0.90:
            errors.append(
                f"[CHECK 1] {ticker}: cobertura {coverage:.1%} < 90% "
                f"({len(df)} filas, {biz_days} dias habiles esperados)"
            )

    for sid, df in fred_data.items():
        if df is None or df.empty:
            continue
        meta = fred_meta.get(sid, {})
        frequency = meta.get("frequency", "daily")  # default conservador
        effective_start_str = meta.get("effective_start")

        idx = pd.to_datetime(df.index)
        range_start = idx.min()
        range_end   = idx.max()

        # Si la serie tiene effective_start, recortar el rango y los datos
        if effective_start_str:
            eff_start = pd.Timestamp(effective_start_str)
            if eff_start > range_start:
                df_clipped = df[df.index >= eff_start]
                if df_clipped.empty:
                    continue
                idx_c = pd.to_datetime(df_clipped.index)
                range_start = idx_c.min()
                non_nan = int(df_clipped["value"].notna().sum())
                expected = _expected_observations(range_start, range_end, frequency)
                coverage = non_nan / expected if expected > 0 else 0
                if coverage < 0.90:
                    errors.append(
                        f"[CHECK 1] FRED {sid} ({frequency}, desde {effective_start_str}): "
                        f"cobertura {coverage:.1%} < 90% ({non_nan}/{expected})"
                    )
                continue

        non_nan  = int(df["value"].notna().sum())
        expected = _expected_observations(range_start, range_end, frequency)
        coverage = non_nan / expected if expected > 0 else 0
        if coverage < 0.90:
            errors.append(
                f"[CHECK 1] FRED {sid} ({frequency}): "
                f"cobertura {coverage:.1%} < 90% ({non_nan}/{expected} obs "
                f"en rango {range_start.date()} -> {range_end.date()})"
            )

    # -- Check 2: SPY >= 5000 filas diarias ------------------------------------
    spy = yahoo_data.get("SPY")
    if spy is None or len(spy) < 5000:
        n = len(spy) if spy is not None else 0
        errors.append(f"[CHECK 2] SPY: solo {n} filas (se esperan >=5000)")

    # -- Check 3: NetLiq negativa en <1% de observaciones ---------------------
    if "NetLiq" in macro_w.columns:
        netliq = macro_w["NetLiq"].dropna()
        if len(netliq) > 0:
            pct_negative = (netliq < 0).sum() / len(netliq)
            if pct_negative > 0.01:
                errors.append(
                    f"[CHECK 3] NetLiq negativa en {pct_negative:.1%} de observaciones "
                    f"({(netliq < 0).sum()} filas) — revisar fórmula o datos de FRED"
                )

    # -- Check 4: VIX siempre positivo ----------------------------------------
    vix = yahoo_data.get("^VIX")
    if vix is not None and "price" in vix.columns:
        vix_price = vix["price"].dropna()
        bad = (vix_price <= 0).sum()
        if bad > 0:
            errors.append(f"[CHECK 4] ^VIX: {bad} valores <=0 detectados — error de datos")

    # -- Check 5: Índices temporales monotónicos sin duplicados ---------------
    for name, df in [
        ("prices_weekly", prices_w),
        ("macro_daily",   macro_d),
        ("macro_weekly",  macro_w),
    ]:
        idx = df.index
        if not idx.is_monotonic_increasing:
            errors.append(f"[CHECK 5] {name}: índice no es estrictamente creciente")
        dupes = idx.duplicated().sum()
        if dupes > 0:
            errors.append(f"[CHECK 5] {name}: {dupes} fechas duplicadas en el índice")

    return errors


# -- Manifest ------------------------------------------------------------------

def build_manifest(
    yahoo_data:  dict,
    fred_data:   dict,
    yahoo_failed: list,
    fred_failed:  list,
    prices_w:    pd.DataFrame,
    macro_d:     pd.DataFrame,
    macro_w:     pd.DataFrame,
    start_date:  str,
    raw_dir:     Path,
    calib_meta:  dict | None = None,
) -> dict:
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    series_meta: dict = {}
    warnings: list[str] = []

    # Yahoo
    for ticker, df in yahoo_data.items():
        safe = re.sub(r"[^A-Za-z0-9_\-]", "", ticker.replace("^", "").replace("=", ""))
        fname = f"yahoo_{safe}.parquet"
        if df is None or df.empty:
            warnings.append(f"{ticker}: sin datos")
            continue
        idx = pd.to_datetime(df.index)
        first = str(idx.min().date())
        last  = str(idx.max().date())
        nan_c = int(df["price"].isna().sum()) if "price" in df.columns else -1

        note = None
        if first > start_date:
            note = f"Serie inicia {first}; NaN para fechas anteriores a {start_date}"
            warnings.append(f"{ticker}: {note}")

        entry = {
            "source": "yahoo",
            "rows": len(df),
            "first_date": first,
            "last_date": last,
            "nan_count": nan_c,
            "file": str(Path("data/raw") / fname),
        }
        if note:
            entry["note"] = note
        series_meta[ticker] = entry

    for ticker in yahoo_failed:
        series_meta[ticker] = {"source": "yahoo", "status": "FAILED"}
        warnings.append(f"{ticker}: descarga fallida")

    # FRED
    for sid, df in fred_data.items():
        if df is None or df.empty:
            warnings.append(f"FRED {sid}: sin datos")
            continue
        idx = pd.to_datetime(df.index)
        first = str(idx.min().date())
        last  = str(idx.max().date())
        nan_c = int(df["value"].isna().sum())

        # Detectar gaps en series diarias (>5 días hábiles consecutivos con NaN)
        if len(df) > 10:
            val_series = df["value"].copy()
            val_series.index = pd.to_datetime(val_series.index)
            # Buscar gaps largos
            biz = pd.bdate_range(val_series.index.min(), val_series.index.max())
            aligned = val_series.reindex(biz)
            run_len = 0
            for v in aligned:
                if pd.isna(v):
                    run_len += 1
                    if run_len > 5:
                        # No queremos anotar todos, solo avisar
                        warnings.append(f"FRED {sid}: gap de datos >5 días hábiles detectado")
                        break
                else:
                    run_len = 0

        series_meta[sid] = {
            "source": "fred",
            "rows": len(df),
            "first_date": first,
            "last_date": last,
            "nan_count": nan_c,
            "file": str(Path("data/raw") / f"fred_{sid}.parquet"),
        }

    for sid in fred_failed:
        series_meta[sid] = {"source": "fred", "status": "FAILED"}
        warnings.append(f"FRED {sid}: descarga fallida")

    # Processed files
    def _proc_meta(df: pd.DataFrame, name: str) -> dict:
        if df is None or df.empty:
            return {"status": "empty"}
        return {
            "rows": len(df),
            "columns": df.shape[1],
            "first_date": str(df.index.min().date()),
            "last_date":  str(df.index.max().date()),
        }

    processed_files = {
        "prices_weekly": _proc_meta(prices_w, "prices_weekly"),
        "macro_daily":   _proc_meta(macro_d,  "macro_daily"),
        "macro_weekly":  _proc_meta(macro_w,  "macro_weekly"),
    }

    if calib_meta:
        processed_files["hy_spread_real_only"] = {
            "derivation": (
                "BAMLH0A0HYM2 real en bps (FRED % x100). NaN pre-2023-04-18. "
                "Usado en Modo A (2023+) y Modo B (sin HY para 2005-2022)."
            ),
            "real_obs":   calib_meta["n_real"],
            "real_start": calib_meta["real_start"],
            "real_end":   calib_meta["real_end"],
            "proxy_aborted": True,
            "calibration_report": "data/calibration_report_failed.json",
            "file": "data/processed/hy_spread_real_only.parquet",
        }
        # Enriquecer entrada BAMLH0A0HYM2
        if "BAMLH0A0HYM2" in series_meta:
            series_meta["BAMLH0A0HYM2"]["note"] = (
                "FRED rolling 3y window desde abril 2026 (ICE licensing). "
                "ALFRED sin vintages pre-2023 (verificado empiricamente). "
                "Proxy NFCICREDIT abortado: 3 modelos fallaron spot-checks historicos. "
                "Ver calibration_report_failed.json."
            )

    manifest = {
        "download_timestamp": now_utc,
        "date_range": {
            "start": start_date,
            "end":   str(pd.Timestamp.now().date()),
        },
        "series": series_meta,
        "processed_files": processed_files,
        "warnings": warnings,
        "failed_series": yahoo_failed + fred_failed,
    }
    return manifest


# -- Entry point ---------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Market Tracker v2 — Data Pipeline (Entrega 1)")
    parser.add_argument("--log-file", action="store_true", help="Escribir log en data/fetch.log")
    args = parser.parse_args()

    setup_logging(to_file=args.log_file)

    # Cargar variables de entorno (.env en raíz del proyecto)
    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Variables de entorno cargadas desde {env_path}")
    else:
        load_dotenv()  # busca .env en directorio actual o padre

    # Crear directorios
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    # Leer configuración
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    start_date = config["start_date"]
    end_date   = str(pd.Timestamp.now().normalize().date())

    logger.info("=" * 60)
    logger.info("Market Tracker v2 — Data Pipeline (Entrega 1)")
    logger.info(f"Rango: {start_date} -> {end_date}")
    logger.info("=" * 60)

    # -- Importar módulos -------------------------------------------------------
    # Importación tardía para que dotenv ya esté cargado antes de que
    # los módulos accedan a FRED_API_KEY al importarse.
    import importlib, sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    fetch_all_yahoo, fetch_all_fred                                          = _import_fetchers()
    build_prices_weekly, build_macro_daily, build_macro_weekly, build_hy_real_only = _import_processors()

    # -- Fase 1: Descargas ------------------------------------------------------
    t_start = time.time()

    logger.info("\n-- FASE 1: Descargas --------------------------------------")
    yahoo_data, yahoo_failed = fetch_all_yahoo(config, RAW_DIR, start_date, end_date)
    fred_data,  fred_failed  = fetch_all_fred(config,  RAW_DIR, start_date, end_date)

    total_failed = len(yahoo_failed) + len(fred_failed)
    logger.info(
        f"\nDescargas completadas: {len(yahoo_data) + len(fred_data)} OK | "
        f"{total_failed} fallidas | {time.time()-t_start:.1f}s"
    )

    # -- Fase 2: Procesamiento -------------------------------------------------
    logger.info("\n-- FASE 2: Procesamiento ----------------------------------")

    asset_tickers = [item["ticker"] for item in config["yahoo"].get("assets", [])]
    index_tickers = [item["ticker"] for item in config["yahoo"].get("indices", [])]

    prices_w = build_prices_weekly(yahoo_data, asset_tickers, index_tickers, PROC_DIR)
    macro_d  = build_macro_daily(fred_data, PROC_DIR)
    macro_w  = build_macro_weekly(fred_data, PROC_DIR)

    # -- Fase 3: Sanity checks -------------------------------------------------
    logger.info("\n-- FASE 3: Validaciones -----------------------------------")
    errors = run_sanity_checks(yahoo_data, fred_data, prices_w, macro_d, macro_w, config)

    if errors:
        logger.error("\n[ERR] SANITY CHECKS FALLIDOS — abortando antes de escribir manifest:")
        for e in errors:
            logger.error(f"   {e}")
        return 1

    logger.info("[OK] Todos los sanity checks pasaron")

    # -- Fase 4: HY Spread real-only + reporte calibracion fallida ------------
    logger.info("\n-- FASE 4: HY Spread (real-only) + calibracion fallida ---")
    try:
        calib_meta = build_hy_real_only(RAW_DIR, PROC_DIR, DATA_DIR)
        logger.info(
            f"  [OK] hy_spread_real_only generado: {calib_meta['n_real']} obs "
            f"({calib_meta['real_start']} -> {calib_meta['real_end']}). "
            "Proxy abortado (ver calibration_report_failed.json)."
        )
    except Exception as exc:
        logger.error(f"\n[ERR] Fase 4 HY: {exc}")
        return 1

    # -- Fase 5: Manifest ------------------------------------------------------
    logger.info("\n-- FASE 5: Generando manifest.json ------------------------")
    manifest = build_manifest(
        yahoo_data, fred_data, yahoo_failed, fred_failed,
        prices_w, macro_d, macro_w, start_date, RAW_DIR,
        calib_meta=calib_meta,
    )

    manifest_path = DATA_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    logger.info(f"  manifest.json escrito -> {manifest_path}")

    # -- Resumen final ---------------------------------------------------------
    total_elapsed = time.time() - t_start
    logger.info("\n" + "=" * 60)
    logger.info(f"Pipeline completado en {total_elapsed:.1f}s")
    logger.info(f"  prices_weekly : {prices_w.shape[0]} semanas x {prices_w.shape[1]} activos")
    logger.info(f"  macro_daily   : {macro_d.shape[0]} dias x {macro_d.shape[1]} series")
    logger.info(f"  macro_weekly  : {macro_w.shape[0]} semanas x {macro_w.shape[1]} columnas")

    if manifest["warnings"]:
        logger.info(f"\n[WARN]  {len(manifest['warnings'])} warnings (ver manifest.json -> 'warnings'):")
        for w in manifest["warnings"][:10]:  # solo los primeros 10 en consola
            logger.warning(f"   {w}")
        if len(manifest["warnings"]) > 10:
            logger.warning(f"   ... y {len(manifest['warnings'])-10} más en manifest.json")

    if total_failed > 0:
        logger.warning(f"\n[WARN]  {total_failed} series fallaron: {yahoo_failed + fred_failed}")
        logger.warning("   El pipeline continuó — los datos faltantes aparecen como NaN")
        return 2   # exit code 2: completado con fallos parciales

    logger.info("[OK] Todas las series descargadas correctamente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
