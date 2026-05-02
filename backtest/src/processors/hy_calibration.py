"""
HY Spread — generacion de archivos procesados y reporte de calibracion fallida.

Genera:
  - data/processed/hy_spread_real_only.parquet  : BAMLH0A0HYM2 real (NaN pre-2023-04-18)
  - data/calibration_report_failed.json          : documentacion de los tres modelos probados

NO genera hy_spread_combined.parquet. La calibracion NFCICREDIT->HY fue abortada porque
ninguno de los tres modelos paso los spot-checks historicos (ver reporte JSON).

Historia: se probaron tres modelos para usar NFCICREDIT como proxy de HY spread pre-2023:
  - Lineal:               HY_bps = alpha + beta * NFCICREDIT                  (2/5 spot-checks)
  - Log-lineal (3A):      log(HY_bps) = alpha + beta * NFCICREDIT             (1/5 spot-checks)
  - Cuadratico asim (3B): HY_bps = alpha + beta*NFCI + gamma*max(NFCI,0)^2   (1/5 spot-checks)

Causa raiz: la relacion NFCICREDIT->HY spread no es estable en el tiempo. El periodo de
calibracion (2023-2026) tiene spreads estructuralmente mas bajos que periodos historicos
para el mismo nivel de NFCICREDIT. Ningun modelo parametrico puede resolver este problema.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CUTOFF_DATE   = pd.Timestamp("2023-04-18")
PROXY_START   = pd.Timestamp("2005-01-03")   # primer dia habil del pipeline

# Rangos plausibles para spot-checks (actualizados con datos verificados)
SPOT_CHECKS = {
    "2008-10-15": {"range": (1400, 2100), "nfci_actual": None},
    "2020-03-20": {"range": (850,  1250), "nfci_actual": None},
    "2011-09-30": {"range": (600,  1000), "nfci_actual": None},
    "2015-02-13": {"range": (350,   550), "nfci_actual": None},
    "2017-05-05": {"range": (280,   450), "nfci_actual": None},
}


def _load_series(raw_dir: Path) -> tuple[pd.Series, pd.Series]:
    nfci_df = pd.read_parquet(raw_dir / "fred_NFCICREDIT.parquet")
    hy_df   = pd.read_parquet(raw_dir / "fred_BAMLH0A0HYM2.parquet")

    nfci = nfci_df["value"].copy()
    nfci.index = pd.to_datetime(nfci.index).normalize()

    # FRED reporta BAMLH0A0HYM2 en porcentaje (4.37 = 437 bps). Convertir a bps.
    hy = hy_df["value"].copy() * 100
    hy.index = pd.to_datetime(hy.index).normalize()

    return nfci, hy


def _make_overlap(nfci: pd.Series, hy: pd.Series) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    hy_w    = hy.resample("W-FRI").mean()
    overlap = pd.concat([nfci, hy_w], axis=1, join="inner").dropna()
    overlap.columns = ["nfci_credit", "hy_bps"]
    return overlap["nfci_credit"].values, overlap["hy_bps"].values, overlap


def _r2(y: np.ndarray, y_hat: np.ndarray) -> float:
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def _spot_check_model(predict_fn, nfci: pd.Series) -> dict:
    results = {}
    passes  = 0
    for date_str, meta in SPOT_CHECKS.items():
        lo, hi = meta["range"]
        ts  = pd.Timestamp(date_str)
        pos = nfci.index.get_indexer([ts], method="nearest")[0]
        actual_date = nfci.index[pos]
        nv  = float(nfci.iloc[pos])
        pred = float(predict_fn(nv))
        ok  = lo <= pred <= hi
        if ok:
            passes += 1
        results[date_str] = {
            "nearest_date":    str(actual_date.date()),
            "nfci_credit":     round(nv, 4),
            "hy_predicted_bps": round(pred, 1),
            "plausible_range": [lo, hi],
            "pass":            ok,
        }
    return results, passes


def _fit_linear(x: np.ndarray, y: np.ndarray) -> dict:
    beta, alpha = np.polyfit(x, y, 1)
    y_hat = alpha + beta * x
    r2    = _r2(y, y_hat)
    return {
        "name":    "linear",
        "formula": "HY_bps = alpha + beta * NFCICREDIT",
        "alpha":   round(float(alpha), 2),
        "beta":    round(float(beta),  4),
        "r_squared": round(r2, 4),
        "predict": lambda nv, a=alpha, b=beta: a + b * nv,
    }


def _fit_log_linear(x: np.ndarray, y: np.ndarray) -> dict:
    y_log = np.log(y)
    beta, alpha = np.polyfit(x, y_log, 1)
    y_hat_log = alpha + beta * x
    r2_log    = _r2(y_log, y_hat_log)
    return {
        "name":    "log_linear_3A",
        "formula": "log(HY_bps) = alpha_log + beta_log * NFCICREDIT",
        "alpha_log": round(float(alpha), 6),
        "beta_log":  round(float(beta),  6),
        "exp_alpha": round(float(np.exp(alpha)), 2),
        "r_squared_log": round(r2_log, 4),
        "predict": lambda nv, a=alpha, b=beta: float(np.exp(a + b * nv)),
    }


def _fit_quadratic_asym(x: np.ndarray, y: np.ndarray) -> dict:
    x2 = np.maximum(x, 0) ** 2
    A  = np.column_stack([np.ones(len(x)), x, x2])
    coeffs, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
    alpha, beta, gamma = coeffs
    y_hat = alpha + beta * x + gamma * np.maximum(x, 0) ** 2
    r2    = _r2(y, y_hat)
    return {
        "name":    "quadratic_asymmetric_3B",
        "formula": "HY_bps = alpha + beta*NFCI + gamma*max(NFCI,0)^2",
        "alpha":   round(float(alpha), 2),
        "beta":    round(float(beta),  4),
        "gamma":   round(float(gamma), 4),
        "r_squared": round(r2, 4),
        "predict": lambda nv, a=alpha, b=beta, g=gamma: a + b * nv + g * max(nv, 0) ** 2,
    }


def build_hy_real_only(
    raw_dir: Path,
    processed_dir: Path,
    data_dir: Path,
) -> dict:
    """
    Genera hy_spread_real_only.parquet y calibration_report_failed.json.

    Returns:
        dict con metadata para el manifest.
    """
    logger.info("  HY: cargando series NFCICREDIT y BAMLH0A0HYM2...")
    nfci, hy = _load_series(raw_dir)

    # -- hy_spread_real_only ------------------------------------------------------
    # Serie real en bps (ya convertida), rango diario desde PROXY_START.
    # NaN para todos los dias anteriores a CUTOFF_DATE.
    biz_range = pd.bdate_range(PROXY_START, hy.index.max())
    real_only  = hy.reindex(biz_range)
    real_only.index.name = "date"

    real_df = pd.DataFrame({"hy_bps": real_only})
    out_real = processed_dir / "hy_spread_real_only.parquet"
    real_df.to_parquet(out_real, index=True)

    n_real = int(real_df["hy_bps"].notna().sum())
    real_start = str(hy.index.min().date())
    real_end   = str(hy.index.max().date())
    logger.info(
        f"  hy_spread_real_only: {n_real} obs reales ({real_start} -> {real_end}) "
        f"| {real_df['hy_bps'].isna().sum()} NaN pre-{CUTOFF_DATE.date()} "
        f"-> {out_real.name}"
    )

    # -- Calibracion fallida: probar y documentar los 3 modelos ------------------
    logger.info("  HY: documentando calibracion fallida (3 modelos)...")
    x, y, overlap = _make_overlap(nfci, hy)

    ov_start = str(overlap.index.min().date())
    ov_end   = str(overlap.index.max().date())
    n_weeks  = len(overlap)

    models_raw = [
        _fit_linear(x, y),
        _fit_log_linear(x, y),
        _fit_quadratic_asym(x, y),
    ]

    models_report = []
    for m in models_raw:
        spot_results, passes = _spot_check_model(m["predict"], nfci)
        entry = {k: v for k, v in m.items() if k != "predict"}
        entry["spot_checks"]   = spot_results
        entry["spot_passes"]   = passes
        entry["spot_total"]    = len(SPOT_CHECKS),
        entry["verdict"]       = "FAILED" if passes < len(SPOT_CHECKS) else "PASSED",
        models_report.append(entry)
        logger.info(
            f"    {m['name']}: {passes}/{len(SPOT_CHECKS)} spot-checks PASS"
        )

    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = {
        "calibration_timestamp": now_utc,
        "conclusion": "ABORTED — all three models failed spot-checks. No proxy generated.",
        "root_cause": (
            "The calibration period (2023-2026) has structurally lower HY spreads than "
            "historical periods for the same NFCICREDIT level. "
            "NFCICREDIT range in overlap: [{:.3f}, {:.3f}]. "
            "HY range in overlap: [{:.0f}, {:.0f}] bps. "
            "No parametric model calibrated on this narrow benign window can "
            "reliably extrapolate to historical stress regimes."
        ).format(float(x.min()), float(x.max()), float(y.min()), float(y.max())),
        "overlap_period": {
            "start":   ov_start,
            "end":     ov_end,
            "n_weeks": n_weeks,
            "nfci_range": [round(float(x.min()), 4), round(float(x.max()), 4)],
            "hy_range_bps": [round(float(y.min()), 1), round(float(y.max()), 1)],
        },
        "spot_check_dates_and_ranges": {
            k: v["range"] for k, v in SPOT_CHECKS.items()
        },
        "models_tested": models_report,
        "backtest_implication": (
            "MacroScore credit component (25pts) will be NaN for 2005-2023-04-17. "
            "Primary backtest uses Modo B (reduced MacroScore on 75-pt base, see README). "
            "Modo A (full MacroScore with real HY data) applies only from 2023-04-18 onwards."
        ),
    }

    report_path = data_dir / "calibration_report_failed.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"  calibration_report_failed.json escrito -> {report_path}")

    return {
        "n_real":    n_real,
        "real_start": real_start,
        "real_end":   real_end,
        "proxy_aborted": True,
    }
