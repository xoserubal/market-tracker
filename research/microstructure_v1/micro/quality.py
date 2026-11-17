"""Controles de integridad y calidad por unidad.

La conciliación trades↔barras usa las reglas oficiales de agregación (conditions.py), no una igualdad ingenua:
- volumen y nº de trades de cada barra = trades con regla de volumen 'Y' en ese minuto;
- una barra solo existe si algún trade del minuto actualiza precio (O/C y H/L) y hay volumen > 0
  (un minuto con solo odd lots no genera barra).
Calificación: A (sin incidencias), B (menores), C (materiales), F (inservible o vacío en día de mercado).
"""
import numpy as np
import pandas as pd

from . import calendar


def grade(issues: list) -> str:
    sev = [i["severity"] for i in issues]
    if "fatal" in sev:
        return "F"
    if "major" in sev:
        return "C"
    if "minor" in sev:
        return "B"
    return "A"


def check_trades(tr: pd.DataFrame, day: str, window: tuple) -> dict:
    issues = []
    if not calendar.is_trading_day(day):
        issues.append({"check": "trading_day", "severity": "fatal", "detail": "no es sesión de mercado"})
    if tr.empty:
        issues.append({"check": "empty", "severity": "fatal", "detail": "sin trades en día de mercado"})
        return {"grade": grade(issues), "issues": issues, "rows": 0}
    dup = int(tr.duplicated(["t", "exchange", "trade_id", "price", "size", "tape"]).sum())
    if dup:
        issues.append({"check": "duplicates", "severity": "major" if dup / len(tr) > 1e-3 else "minor", "detail": dup})
    out_win = int(((tr["t"] < window[0]) | (tr["t"] >= window[1])).sum())
    if out_win:
        issues.append({"check": "outside_window", "severity": "major", "detail": out_win})
    if not tr["t"].is_monotonic_increasing:
        issues.append({"check": "non_monotonic", "severity": "minor", "detail": "timestamps no ordenados"})
    unk = tr.loc[tr["unknown_cond"] != "", "unknown_cond"].value_counts().to_dict()
    if unk:
        issues.append({"check": "unknown_conditions", "severity": "minor", "detail": unk})
    gaps = tr.loc[tr["session"] == "regular", "t"].diff().dt.total_seconds()
    max_gap = float(gaps.max()) if len(gaps) > 1 else None
    vol = tr["size"].sum()
    stats = {
        "rows": int(len(tr)), "volume": int(vol),
        "share_trf_volume": round(float(tr.loc[tr["trf"], "size"].sum() / vol), 4) if vol else None,
        "share_odd_lot_trades": round(float(tr["odd_lot"].mean()), 4),
        "share_odd_lot_volume": round(float(tr.loc[tr["odd_lot"], "size"].sum() / vol), 4) if vol else None,
        "share_extended_cond_volume": round(float(tr.loc[tr["extended_cond"], "size"].sum() / vol), 4) if vol else None,
        "max_gap_regular_s": max_gap,
        "canceled_trades": int(tr["canceled"].sum()) if "canceled" in tr else None,
        "sessions": tr["session"].value_counts().to_dict(),
    }
    return {"grade": grade(issues), "issues": issues, **stats}


def reconcile_trades_bars(tr: pd.DataFrame, br: pd.DataFrame) -> dict:
    """Compara, minuto a minuto, volumen y nº de trades esperados según las reglas con las barras del proveedor."""
    issues = []
    live = ~tr["canceled"] if "canceled" in tr else True
    g = tr.assign(vol_y=np.where(tr["upd_vol"] & live, tr["size"], 0), n_y=(tr["upd_vol"] & live).astype(int),
                  price_y=(tr["upd_oc"] != "N") & tr["upd_hl"] & live)
    m = g.groupby("minute").agg(vol=("vol_y", "sum"), n=("n_y", "sum"), price_trades=("price_y", "sum"))
    m["bar_expected"] = (m["price_trades"] > 0) & (m["vol"] > 0)
    b = br.set_index("t")[["volume", "n_trades"]]
    j = m.join(b, how="outer")
    exp = j["bar_expected"].fillna(False).astype(bool)
    has_bar = j["volume"].notna()
    missing_bar = int((exp & ~has_bar).sum())
    unexpected_bar = int((~exp & has_bar & j["vol"].fillna(0).eq(0)).sum())
    both = j[has_bar & j["vol"].notna()]
    vol_diff = float((both["vol"] - both["volume"]).abs().sum())
    vol_tot = float(both["volume"].sum()) or 1.0
    n_diff = float((both["n"] - both["n_trades"]).abs().sum())
    n_tot = float(both["n_trades"].sum()) or 1.0
    mism_min = int(((both["vol"] - both["volume"]).abs() > 0).sum())
    rel_v = vol_diff / vol_tot
    if rel_v > 0.02 or missing_bar > 5:
        issues.append({"check": "trades_vs_bars", "severity": "major", "detail": {"vol_rel_diff": rel_v, "missing": missing_bar}})
    elif rel_v > 0.001 or missing_bar or unexpected_bar:
        issues.append({"check": "trades_vs_bars", "severity": "minor", "detail": {"vol_rel_diff": rel_v, "missing": missing_bar,
                                                                                  "unexpected": unexpected_bar}})
    return {"grade": grade(issues), "issues": issues, "minutes_compared": int(len(both)),
            "minutes_volume_mismatch": mism_min, "volume_rel_diff": round(rel_v, 6),
            "count_rel_diff": round(n_diff / n_tot, 6), "bars_missing_vs_expected": missing_bar,
            "bars_unexpected": unexpected_bar}


def check_bars_session(br: pd.DataFrame, day: str) -> dict:
    """Cobertura de la sesión regular por barras de 1 min (huecos = minutos sin trades que actualicen precio)."""
    issues = []
    o, c = calendar.session_bounds(day, "regular")
    reg = br[(br["t"] >= o) & (br["t"] < c)]
    expected = int((c - o).total_seconds() // 60)
    cov = len(reg) / expected if expected else 0.0
    zero_v = int((br["volume"] == 0).sum()) if "volume" in br else 0
    if reg.empty:
        issues.append({"check": "no_regular_bars", "severity": "fatal", "detail": day})
    elif cov < 0.5:
        issues.append({"check": "low_minute_coverage", "severity": "minor", "detail": round(cov, 3)})
    if zero_v:
        issues.append({"check": "zero_volume_bars", "severity": "major", "detail": zero_v})
    return {"grade": grade(issues), "issues": issues, "regular_minutes_expected": expected,
            "regular_bars": int(len(reg)), "minute_coverage": round(cov, 4), "early_close": calendar.is_early_close(day)}


def check_quotes(q: pd.DataFrame) -> dict:
    issues = []
    if q.empty:
        issues.append({"check": "empty", "severity": "fatal", "detail": "sin quotes"})
        return {"grade": grade(issues), "issues": issues}
    reg = q[q["session"] == "regular"]
    valid = reg[~reg["zero_side"]]
    rel_spread = (valid["spread"] / valid["mid"]).replace([np.inf, -np.inf], np.nan)
    stats = {"rows": int(len(q)), "rows_regular": int(len(reg)),
             "share_zero_side": round(float(reg["zero_side"].mean()), 5) if len(reg) else None,
             "share_crossed": round(float(reg["crossed"].mean()), 5) if len(reg) else None,
             "share_locked": round(float(reg["locked"].mean()), 5) if len(reg) else None,
             "median_rel_spread_bps": round(float(rel_spread.median() * 1e4), 2) if len(valid) else None,
             "share_rel_spread_gt_5pct": round(float((rel_spread > 0.05).mean()), 5) if len(valid) else None}
    if stats["share_crossed"] and stats["share_crossed"] > 0.01:
        issues.append({"check": "crossed", "severity": "major", "detail": stats["share_crossed"]})
    if stats["share_zero_side"] and stats["share_zero_side"] > 0.01:
        issues.append({"check": "zero_side", "severity": "minor", "detail": stats["share_zero_side"]})
    return {"grade": grade(issues), "issues": issues, **stats}
