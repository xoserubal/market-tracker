"""
Exporta los parquets procesados a JSON optimizados para el dashboard web.
Genera archivos en docs/data/ que son leídos por GitHub Pages.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "backtest" / "data" / "processed"
OUT_DIR  = ROOT / "docs" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def clean(obj):
    """Convierte NaN/inf/Timestamp a tipos JSON válidos."""
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj.date())
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return round(obj, 4)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else round(v, 4)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.NaT.__class__,)):
        return None
    return obj


def df_to_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for idx, row in df.iterrows():
        rec = {"date": str(idx.date()) if hasattr(idx, "date") else str(idx)}
        for col in df.columns:
            rec[col] = clean(row[col])
        records.append(rec)
    return records


# ── 1. MacroScore history ────────────────────────────────────────────────────
def export_macro():
    path = DATA_DIR / "macro_history.parquet"
    if not path.exists():
        print("  ⚠ macro_history.parquet no encontrado, saltando")
        return

    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Columnas esenciales para el dashboard
    cols_macro = [c for c in [
        "macro_score", "regime",
        "hy_pts", "netliq_pts", "vol_pts", "curva_pts", "cfnai_pts",
        "flag_credit_complacency", "flag_inflation_overlay",
        "flag_term_premium_extreme", "flag_emergency_mode",
    ] if c in df.columns]

    # Exportar modo A (principal) si existe columna de modo
    if "mode" in df.columns:
        df_a = df[df["mode"] == "A"][cols_macro].copy()
    else:
        df_a = df[cols_macro].copy()

    # Descartar filas del final donde macro_score es null (semana en curso sin datos completos)
    if "macro_score" in df_a.columns:
        last_valid = df_a["macro_score"].last_valid_index()
        if last_valid is not None:
            df_a = df_a.loc[:last_valid]

    # ── Trend fields (delta 1W / 1M, macro_trend, macro_phase_quality) ───────
    if "macro_score" in df_a.columns:
        df_a["macro_delta_1w"] = df_a["macro_score"].diff(1).round(2)
        df_a["macro_delta_1m"] = df_a["macro_score"].diff(4).round(2)
        improving    = (df_a["macro_delta_1w"] > 2)  | (df_a["macro_delta_1m"] > 5)
        deteriorating = (df_a["macro_delta_1w"] < -2) | (df_a["macro_delta_1m"] < -5)
        df_a["macro_trend"] = np.select(
            [improving, deteriorating],
            ["Improving", "Deteriorating"],
            default="Stable",
        )
        if "regime" in df_a.columns:
            df_a["macro_phase_quality"] = (
                df_a["regime"].astype(str) + " " + df_a["macro_trend"]
            )

    latest_row = df_a.iloc[-1]
    out = {
        "updated": str(df_a.index[-1].date()),
        "latest": {
            "score":         clean(latest_row.get("macro_score")),
            "regime":        str(latest_row["regime"]) if "regime" in df_a.columns and pd.notna(latest_row.get("regime")) else None,
            "delta_1w":      clean(latest_row.get("macro_delta_1w")),
            "delta_1m":      clean(latest_row.get("macro_delta_1m")),
            "trend":         str(latest_row.get("macro_trend", "Stable")),
            "phase_quality": str(latest_row.get("macro_phase_quality", "")) if "macro_phase_quality" in df_a.columns else None,
        },
        "history": df_to_records(df_a),
    }
    write_json(out, "macro_history.json")
    print(f"  ✓ macro_history.json  ({len(df_a)} semanas)")


# ── 2. Rotation signals ──────────────────────────────────────────────────────
def export_rotation():
    path = DATA_DIR / "rotation_history.parquet"
    if not path.exists():
        print("  ⚠ rotation_history.parquet no encontrado, saltando")
        return

    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Usar solo Modo A
    if "mode" in df.columns:
        df = df[df["mode"] == "A"]

    # Usar la última fecha con el conjunto completo de tickers (evita fechas parciales)
    ticker_counts = df.groupby(df.index)["ticker"].count()
    max_tickers = ticker_counts.max()
    complete_dates = ticker_counts[ticker_counts == max_tickers].index
    latest_date = complete_dates.max()

    # Señales más recientes por ticker
    latest = df[df.index == latest_date].copy()
    cols_rot = [c for c in [
        "ticker", "rot_score", "signal", "fit", "regime", "cluster",
        "rs_13w_pts", "rs_4w_pts", "trend_abs_pts", "cmf_pts", "obv_pts",
        "vol_rel_pts", "macd_pts", "rsi_pts", "is_early_rotation",
        "ret_4w_vs_spy", "ret_13w_vs_spy",
    ] if c in latest.columns]
    latest_records = []
    for _, row in latest[cols_rot].iterrows():
        rec = {}
        for c in cols_rot:
            v = row[c]
            if c in ("ticker", "signal", "regime", "cluster"):
                rec[c] = str(v) if pd.notna(v) else None
            else:
                rec[c] = clean(v)
        latest_records.append(rec)

    # Heatmap rot_score: últimas 52 semanas × todos los tickers
    cutoff = latest_date - pd.Timedelta(weeks=52)
    hist = df[(df.index >= cutoff) & ("rot_score" in df.columns or True)]
    score_col = "rot_score" if "rot_score" in hist.columns else "score"
    if score_col in hist.columns and "ticker" in hist.columns:
        pivot = hist.pivot_table(index=hist.index, columns="ticker", values=score_col, aggfunc="first")
        pivot.index = pivot.index.strftime("%Y-%m-%d")
        heatmap = {
            "dates": list(pivot.index),
            "tickers": list(pivot.columns),
            "scores": [[clean(v) for v in row] for row in pivot.values],
        }
    else:
        heatmap = {}

    out = {
        "updated": str(latest_date.date()),
        "latest_signals": latest_records,
        "heatmap_52w": heatmap,
    }
    write_json(out, "rotation_signals.json")
    print(f"  ✓ rotation_signals.json  ({len(latest_records)} tickers)")


# ── 3. Portfolio equity curves ───────────────────────────────────────────────
def export_portfolio():
    path_hist = DATA_DIR / "portfolio_rot_temprana_history.parquet"
    path_metrics = DATA_DIR / "portfolio_metrics.parquet"

    metrics_records = []
    if path_metrics.exists():
        df_m = pd.read_parquet(path_metrics)
        for _, row in df_m.iterrows():
            rec = {col: clean(row[col]) if not isinstance(row[col], str) else str(row[col])
                   for col in df_m.columns}
            metrics_records.append(rec)

    equity_curves = {}
    if path_hist.exists():
        df_h = pd.read_parquet(path_hist)
        df_h["date"] = pd.to_datetime(df_h["date"])
        df_h = df_h.sort_values("date")

        # Normalizar equity a base 100
        df_h["equity_norm"] = df_h.groupby("strategy")["equity"].transform(lambda x: x / x.iloc[0] * 100)

        # Usar solo Modo A, período completo, sin BTC para comparabilidad limpia
        mask = (df_h["mode"] == "A") & (df_h["period"] == "2005-2026") & (df_h["include_btc"] == False)
        if mask.sum() == 0:
            mask = (df_h["mode"] == "A") & (df_h["period"] == "2005-2026")
        df_filt = df_h[mask].copy()

        # Top estrategias por Sharpe
        top_strats = []
        if metrics_records and path_metrics.exists():
            df_m2 = pd.read_parquet(path_metrics)
            mask_m = (df_m2["mode"] == "A") & (df_m2["period"] == "2005-2026")
            if mask_m.sum() > 0:
                top_strats = df_m2[mask_m].nlargest(5, "sharpe")["strategy"].tolist()

        if not top_strats:
            top_strats = df_filt["strategy"].unique()[:5].tolist()

        curves = {}
        dates = None
        for strat in [s for s in top_strats if s != "spy_benchmark"]:
            sub = df_filt[df_filt["strategy"] == strat].set_index("date")
            # Muestrear semanalmente (viernes)
            sub_w = sub["equity_norm"].resample("W-FRI").last().dropna()
            if dates is None:
                dates = [str(d.date()) for d in sub_w.index]
            curves[strat] = [clean(v) for v in sub_w.tolist()]

        # Añadir SPY y QQQ benchmark desde prices_daily
        prices_path = DATA_DIR / "prices_daily.parquet"
        if dates and prices_path.exists():
            try:
                prices = pd.read_parquet(prices_path)
                prices.index = pd.to_datetime(prices.index)
                date_start = pd.Timestamp(dates[0])
                date_index = pd.Index(pd.to_datetime(dates))
                for ticker, key in [("SPY", "spy_benchmark"), ("QQQ", "qqq_benchmark")]:
                    if ticker in prices.columns:
                        series = prices[ticker].dropna()
                        series = series[series.index >= date_start]
                        series_w = series.resample("W-FRI").last().dropna()
                        if not series_w.empty:
                            norm = series_w / series_w.iloc[0] * 100
                            aligned = norm.reindex(date_index, method="ffill")
                            curves[key] = [clean(v) for v in aligned.tolist()]
            except Exception:
                pass

        equity_curves = {
            "dates": dates or [],
            "strategies": curves,
        }

    out = {
        "updated": str(pd.Timestamp.now().date()),
        "metrics": metrics_records,
        "equity_curves": equity_curves,
    }
    write_json(out, "portfolio.json")
    print(f"  ✓ portfolio.json  ({len(metrics_records)} estrategias, {len(equity_curves.get('dates', []))} semanas)")


# ── 4. Confluence ────────────────────────────────────────────────────────────
def export_confluence():
    path_hist = DATA_DIR / "confluence_history.parquet"
    path_alerts = DATA_DIR / "confluence_alerts.parquet"

    history_records = []
    if path_hist.exists():
        df = pd.read_parquet(path_hist)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        cols = [c for c in df.columns if c in [
            "confluence_score", "macro_tension", "sector_tension",
            "alert_structural", "alert_tactical", "regime_label"
        ]]
        history_records = df_to_records(df[cols]) if cols else df_to_records(df)

    alerts_records = []
    if path_alerts.exists():
        df_a = pd.read_parquet(path_alerts)
        df_a.index = pd.to_datetime(df_a.index)
        df_a = df_a.sort_index()
        alerts_records = df_to_records(df_a)

    out = {
        "updated": str(pd.Timestamp.now().date()),
        "history": history_records,
        "alerts": alerts_records,
    }
    write_json(out, "confluence.json")
    print(f"  ✓ confluence.json  ({len(history_records)} semanas, {len(alerts_records)} alertas)")


# ── 5. Prices weekly (relative strength) ────────────────────────────────────
def export_prices():
    path = DATA_DIR / "prices_weekly.parquet"
    if not path.exists():
        print("  ⚠ prices_weekly.parquet no encontrado, saltando")
        return

    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Solo últimos 3 años para el dashboard de relative strength
    cutoff = df.index.max() - pd.Timedelta(weeks=156)
    df = df[df.index >= cutoff]

    # Normalizar a base 100 desde el inicio del período
    df_norm = (df / df.iloc[0] * 100).round(2)

    out = {
        "updated": str(df.index.max().date()),
        "dates": [str(d.date()) for d in df_norm.index],
        "tickers": list(df_norm.columns),
        "prices": {col: [clean(v) for v in df_norm[col].tolist()] for col in df_norm.columns},
    }
    write_json(out, "prices_relative.json")
    print(f"  ✓ prices_relative.json  ({len(df_norm)} semanas, {len(df_norm.columns)} tickers)")


# ── 5b. Prices for open picks (absolute closes, last 10 días) ────────────────
def export_picks_prices():
    picks_path = OUT_DIR / "ai_picks.json"
    if not picks_path.exists():
        print("  ⚠ ai_picks.json no encontrado, saltando picks prices")
        return

    with open(picks_path, "r", encoding="utf-8") as f:
        picks = json.load(f)

    tickers: set[str] = set()
    for ptf in (picks.get("portfolios") or {}).values():
        for pos in (ptf.get("positions") or []):
            if pos.get("ticker"):
                tickers.add(pos["ticker"])

    if not tickers:
        print("  ⚠ No hay posiciones abiertas, saltando picks prices")
        return

    RAW_DIR = ROOT / "backtest" / "data" / "raw"
    result: dict = {}

    for ticker in sorted(tickers):
        ticker_safe = ticker.replace("^", "").replace("=", "")
        path = RAW_DIR / f"yahoo_{ticker_safe}.parquet"
        if not path.exists():
            print(f"  ⚠ {ticker}: raw parquet no encontrado")
            continue
        try:
            df = pd.read_parquet(path, columns=["Close"])
            df.index = pd.to_datetime(df.index)
            df = df.sort_index().dropna()
            recent = df.tail(10)
            result[ticker] = {
                "dates":  [str(d.date()) for d in recent.index],
                "closes": [round(float(v), 2) for v in recent["Close"]],
            }
        except Exception as e:
            print(f"  ⚠ {ticker}: {e}")

    out = {"updated": str(pd.Timestamp.now().date()), "tickers": result}
    write_json(out, "prices_picks.json")
    print(f"  ✓ prices_picks.json  ({len(result)} tickers)")


# ── helpers ──────────────────────────────────────────────────────────────────
def write_json(data: dict, filename: str):
    path = OUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


# ── 6. Stock candidates ──────────────────────────────────────────────────────
def export_stock_candidates():
    path = DATA_DIR / "stock_candidates.json"
    if not path.exists():
        print("  ⚠ stock_candidates.json no encontrado, saltando")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Re-serializar con el mismo clean() para consistencia de tipos
    candidates = data.get("candidates", [])
    cleaned = []
    for c in candidates:
        rec = {}
        for k, v in c.items():
            if k == "components" and isinstance(v, dict):
                rec[k] = {ck: clean(cv) for ck, cv in v.items()}
            elif isinstance(v, (int, float, np.floating, np.integer)):
                rec[k] = clean(v)
            else:
                rec[k] = v
        cleaned.append(rec)

    out = {
        "updated":                      data.get("updated", ""),
        "active_rot_temprana_clusters": data.get("active_rot_temprana_clusters", []),
        "candidates":                   cleaned,
    }
    write_json(out, "stock_candidates.json")
    n_cand = sum(1 for c in cleaned if c.get("signal") in ("CANDIDATO", "EN_RADAR"))
    print(f"  ✓ stock_candidates.json  ({len(cleaned)} stocks, {n_cand} activos)")


if __name__ == "__main__":
    print("Exportando datos para dashboard...")
    export_macro()
    export_rotation()
    export_portfolio()
    export_confluence()
    export_prices()
    export_picks_prices()
    export_stock_candidates()
    print(f"\nDatos exportados en: {OUT_DIR}")

    # Run PCS calculator after all source JSONs are fresh
    try:
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "pcs_calculator",
            pathlib.Path(__file__).parent / "pcs_calculator.py",
        )
        pcs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pcs)
        pcs.run()
    except Exception as e:
        print(f"  ⚠ pcs_calculator skipped: {e}")
