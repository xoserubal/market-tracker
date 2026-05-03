"""
Pipeline Step 7: Stock scanner de acciones individuales por cluster.

Lee backtest/config/individual_stocks.yaml, descarga datos frescos de Yahoo
para cada acción, calcula RotationScore (criterios relajados) y beta 52w,
y guarda el resultado en backtest/data/processed/stock_candidates.json.

Uso:
    python backtest/src/main_stocks.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rotation.indicators import (
    compute_daily_indicators,
    load_daily_ohlcv,
    sample_to_friday,
)
from rotation.stock_scanner import load_stock_config, scan_stocks

RAW_DIR       = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CONFIG_PATH   = ROOT / "config" / "individual_stocks.yaml"
OUT_PATH      = PROCESSED_DIR / "stock_candidates.json"

START_DATE = "2022-01-01"   # mínimo 3 años para beta + historial score


def _safe_filename(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "", ticker.replace("^", "").replace("=", ""))


def download_stock(ticker: str, start: str) -> bool:
    """
    Descarga datos diarios de Yahoo y los guarda en raw_dir.
    Devuelve True si tuvo éxito. Omite la descarga si el archivo
    tiene menos de 12 horas de antigüedad.
    """
    safe     = _safe_filename(ticker)
    out_path = RAW_DIR / f"yahoo_{safe}.parquet"

    # Saltar si el archivo es reciente (ejecución de hoy)
    if out_path.exists():
        age_hours = (time.time() - out_path.stat().st_mtime) / 3600
        if age_hours < 12:
            return True

    for attempt in range(3):
        if attempt:
            time.sleep(4 * attempt)
        try:
            raw = yf.download(
                ticker,
                start=start,
                end=str(pd.Timestamp.now().normalize().date()),
                auto_adjust=False,
                progress=False,
                multi_level_index=False,
            )
            if raw is None or raw.empty:
                continue

            # Normalizar columnas
            raw.columns = [c.strip() for c in raw.columns]
            close_col = "Adj Close" if "Adj Close" in raw.columns else "Close"
            df = pd.DataFrame({
                "price":  raw[close_col],
                "High":   raw.get("High",   raw[close_col]),
                "Low":    raw.get("Low",    raw[close_col]),
                "Close":  raw.get("Close",  raw[close_col]),
                "Volume": raw.get("Volume", pd.Series(0.0, index=raw.index)),
                "Adj Close": raw[close_col],
            })
            df.index = pd.to_datetime(df.index).normalize()
            df.index.name = "date"
            df = df.dropna(subset=["price"])
            if len(df) < 60:
                continue

            RAW_DIR.mkdir(parents=True, exist_ok=True)
            df.to_parquet(out_path)
            return True

        except Exception as exc:
            print(f"    ⚠ {ticker} intento {attempt+1}: {exc}")

    return False


def get_active_rot_temprana_clusters() -> set[str]:
    """Lee rotation_history.parquet y devuelve clusters con ROT.TEMPRANA activa."""
    rot_path = PROCESSED_DIR / "rotation_history.parquet"
    if not rot_path.exists():
        return set()

    df = pd.read_parquet(rot_path)
    df.index = pd.to_datetime(df.index)

    if "mode" in df.columns:
        df = df[df["mode"] == "A"]

    if df.empty or "ticker" not in df.columns:
        return set()

    # Última fecha con conjunto completo de tickers
    counts = df.groupby(df.index)["ticker"].count()
    latest_date = counts[counts == counts.max()].index.max()
    latest = df[df.index == latest_date]

    if "is_early_rotation" not in latest.columns or "cluster" not in latest.columns:
        return set()

    active = latest[latest["is_early_rotation"] == True]["cluster"].dropna().unique()
    return set(active)


def load_spy_weekly() -> pd.DataFrame:
    """Carga indicadores semanales de SPY desde el parquet ya descargado."""
    daily = load_daily_ohlcv("SPY", RAW_DIR)
    if daily is None or daily.empty:
        return pd.DataFrame()
    return sample_to_friday(compute_daily_indicators(daily))


def main() -> int:
    print("Paso 7: Stock scanner — acciones individuales por cluster")

    # Colectar todos los tickers del config
    stock_config = load_stock_config(CONFIG_PATH)
    if not stock_config:
        print("  ⚠ No se encontró config en", CONFIG_PATH)
        return 1

    all_tickers = [
        s["ticker"]
        for stocks in stock_config.values()
        for s in stocks
    ]
    print(f"  Tickers a escanear: {len(all_tickers)}")

    # Descargar datos frescos
    print("  Descargando datos...")
    failed = []
    for ticker in all_tickers:
        ok = download_stock(ticker, START_DATE)
        if ok:
            print(f"    ✓ {ticker}")
        else:
            print(f"    ✗ {ticker} — fallido, se omitirá")
            failed.append(ticker)

    # Cargar SPY semanal
    spy_weekly = load_spy_weekly()
    if spy_weekly.empty:
        print("  ⚠ No se pudo cargar SPY — abortando")
        return 1

    # Clusters activos con ROT.TEMPRANA
    active_clusters = get_active_rot_temprana_clusters()
    label = ", ".join(sorted(active_clusters)) if active_clusters else "ninguno"
    print(f"  Clusters con ROT.TEMPRANA activa: {label}")

    # Escanear
    candidates = scan_stocks(active_clusters, spy_weekly, CONFIG_PATH, RAW_DIR)

    # Guardar JSON
    out = {
        "updated":                      str(pd.Timestamp.now().date()),
        "active_rot_temprana_clusters": sorted(active_clusters),
        "failed_downloads":             failed,
        "candidates":                   candidates,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Resumen
    signal_counts = {}
    for c in candidates:
        signal_counts[c["signal"]] = signal_counts.get(c["signal"], 0) + 1

    print(f"\n  ✓ {len(candidates)} stocks procesados → {OUT_PATH.name}")
    for sig in ("CANDIDATO", "EN_RADAR", "VIGILAR", "IGNORAR"):
        n = signal_counts.get(sig, 0)
        if n:
            prefix = "⚡" if sig == "CANDIDATO" else "→" if sig == "EN_RADAR" else " "
            print(f"    {prefix} {sig}: {n}")

    for c in candidates:
        if c["signal"] in ("CANDIDATO", "EN_RADAR"):
            print(
                f"    {'⚡' if c['cluster_has_rot_temprana'] else '→'} "
                f"{c['ticker']:8s}  cluster={c['cluster']:15s}  "
                f"score={c['rot_score']}  beta={c['beta_52w']}  "
                f"streak={c['streak_weeks']}w  signal={c['signal']}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
