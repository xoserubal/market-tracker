"""
Pick Conviction Score (PCS) Calculator — v1

Inputs:  docs/data/macro_history.json
         docs/data/rotation_signals.json   (sector ETFs / proxies)
         docs/data/stock_candidates.json   (individual stocks — 72 of 91 universe tickers)
         docs/data/universe.json

Output:  docs/data/ai_candidates.json
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"


def _load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── Daily Early Momentum fetch ────────────────────────────────────────────────

def fetch_daily_metrics(tickers: list[str]) -> dict[str, dict]:
    """
    Fetch ~2 months of daily OHLCV and compute early-rotation signals per ticker.
    All computations are relative to SPY.  Returns {} per ticker on any failure.
    Does NOT affect PCS — results go into daily_signals only.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return {}

    all_syms = sorted(set(tickers) | {"SPY"})
    try:
        raw = yf.download(all_syms, period="2mo", auto_adjust=True,
                          progress=False, threads=True)
    except Exception:
        return {}

    if raw is None or raw.empty:
        return {}

    try:
        import pandas as pd
        if isinstance(raw.columns, pd.MultiIndex):
            close_df = raw["Close"].dropna(how="all")
            high_df  = raw["High"].dropna(how="all")  if "High"   in raw else pd.DataFrame()
            low_df   = raw["Low"].dropna(how="all")   if "Low"    in raw else pd.DataFrame()
            vol_df   = raw["Volume"].dropna(how="all") if "Volume" in raw else pd.DataFrame()
        else:
            t0 = tickers[0] if tickers else "UNK"
            close_df = raw[["Close"]].rename(columns={"Close": t0})
            high_df  = raw[["High"]].rename(columns={"High": t0})   if "High"   in raw else pd.DataFrame()
            low_df   = raw[["Low"]].rename(columns={"Low": t0})     if "Low"    in raw else pd.DataFrame()
            vol_df   = raw[["Volume"]].rename(columns={"Volume": t0}) if "Volume" in raw else pd.DataFrame()
    except Exception:
        return {}

    if "SPY" not in close_df.columns or len(close_df) < 6:
        return {}

    results: dict[str, dict] = {}

    for t in tickers:
        if t not in close_df.columns:
            results[t] = {}
            continue
        try:
            import pandas as pd
            aligned = pd.concat(
                [close_df[t], close_df["SPY"]], axis=1, join="inner"
            ).dropna()
            aligned.columns = ["tk", "spy"]
            if len(aligned) < 6:
                results[t] = {}
                continue

            tc = aligned["tk"].values
            sc = aligned["spy"].values

            # Percentage returns per day
            tk_ret  = pd.Series(tc).pct_change().values[1:]
            spy_ret = pd.Series(sc).pct_change().values[1:]
            alpha   = tk_ret - spy_ret

            def _ret_nd(n: int) -> float | None:
                if len(tc) < n + 1:
                    return None
                return round((tc[-1] / tc[-(n+1)] - sc[-1] / sc[-(n+1)]) * 100, 2)

            r5  = _ret_nd(5)
            r10 = _ret_nd(10)
            r20 = _ret_nd(20)

            # outperform_days_10d: days in last 10 where ticker beat SPY
            window = alpha[-10:] if len(alpha) >= 10 else alpha
            opd10 = int((window > 0).sum())

            # streak_days: consecutive outperform days from today backwards
            streak = 0
            for a in reversed(alpha[-15:] if len(alpha) >= 15 else alpha):
                if a > 0:
                    streak += 1
                else:
                    break

            # spike_flag: one day accounts for > 70 % of the 5-day ticker move
            spike_flag = False
            if r5 is not None and r5 > 0 and len(tk_ret) >= 5:
                raw_5d = tc[-1] / tc[-6] - 1 if len(tc) >= 6 else 0
                if raw_5d > 0:
                    spike_flag = bool(max(tk_ret[-5:]) / raw_5d > 0.70)

            # momentum_accel (auditor formula)
            if r5 is not None and r10 is not None and r20 is not None:
                if r20 > 0:
                    momentum_accel = bool(r5 > 0 and r10 > 0 and r5 > 0.5 * r20)
                else:
                    momentum_accel = bool(r5 > 3.0)
            else:
                momentum_accel = bool((r5 or 0) > 3.0)

            # vol_5d_vs_20d
            vol_ratio: float | None = None
            if t in vol_df.columns:
                v = vol_df[t].dropna()
                if len(v) >= 20:
                    v5  = float(v.iloc[-5:].mean())
                    v20 = float(v.iloc[-20:].mean())
                    vol_ratio = round(v5 / v20, 2) if v20 > 0 else None

            # ATR14 + dist_sma20_atr (requires High/Low columns)
            dist_sma20_atr: float | None = None
            h_col = high_df.columns if not high_df.empty else []
            l_col = low_df.columns  if not low_df.empty  else []
            if t in h_col and t in l_col:
                hlc = pd.concat(
                    [high_df[t], low_df[t], close_df[t]], axis=1, join="inner"
                ).dropna()
                hlc.columns = ["h", "l", "c"]
                if len(hlc) >= 15:
                    prev_c = hlc["c"].shift(1)
                    tr = pd.concat([
                        hlc["h"] - hlc["l"],
                        (hlc["h"] - prev_c).abs(),
                        (hlc["l"] - prev_c).abs(),
                    ], axis=1).max(axis=1)
                    atr14 = float(tr.rolling(14).mean().iloc[-1])
                    sma20 = float(hlc["c"].rolling(20).mean().iloc[-1])
                    last_c = float(hlc["c"].iloc[-1])
                    if atr14 > 0 and pd.notna(atr14) and pd.notna(sma20):
                        dist_sma20_atr = round((last_c - sma20) / atr14, 2)

            # RSI14 (standard Wilder, close prices only)
            rsi_14: float | None = None
            c_s = pd.Series(tc)
            if len(c_s) >= 15:
                delta   = c_s.diff()
                gain    = delta.clip(lower=0).rolling(14).mean()
                loss    = (-delta).clip(lower=0).rolling(14).mean()
                avg_g   = float(gain.iloc[-1])
                avg_l   = float(loss.iloc[-1])
                if pd.notna(avg_g) and pd.notna(avg_l):
                    if avg_l > 0:
                        rsi_14 = round(100 - 100 / (1 + avg_g / avg_l), 1)
                    elif avg_g > 0:
                        rsi_14 = 100.0

            # momentum_decay: strong multi-week move but short-term fading
            momentum_decay = bool(
                r5  is not None and r5  < -1.0
                and r20 is not None and r20 > 20.0
            )

            results[t] = {
                "ret_5d_vs_spy":       r5,
                "ret_10d_vs_spy":      r10,
                "ret_20d_vs_spy":      r20,
                "outperform_days_10d": opd10,
                "streak_days":         streak,
                "momentum_accel":      momentum_accel,
                "vol_5d_vs_20d":       vol_ratio,
                "spike_flag":          spike_flag,
                "dist_sma20_atr":      dist_sma20_atr,
                "rsi_14":              rsi_14,
                "momentum_decay":      momentum_decay,
            }
        except Exception:
            results[t] = {}

    return results


# ── Daily Early Momentum Score (DEMS 0–20) ────────────────────────────────────
# Independent of PCS.  Used only for EARLY_ROTATION candidates.

def compute_dems(d: dict) -> tuple[int, list[str]]:
    if not d:
        return 0, []

    score = 0
    flags: list[str] = []

    r5  = d.get("ret_5d_vs_spy")  or 0.0
    r10 = d.get("ret_10d_vs_spy") or 0.0
    opd = d.get("outperform_days_10d") or 0
    mo  = bool(d.get("momentum_accel"))
    vol = d.get("vol_5d_vs_20d")
    spk = bool(d.get("spike_flag"))

    # 0–5 pts: 5-day alpha vs SPY
    if   r5 >= 12: score += 5; flags.append("dems_5d_very_strong")
    elif r5 >=  8: score += 4; flags.append("dems_5d_strong")
    elif r5 >=  5: score += 3; flags.append("dems_5d_good")
    elif r5 >=  2: score += 2
    elif r5 >=  0: score += 1

    # 0–4 pts: 10-day alpha vs SPY
    if   r10 >= 10: score += 4
    elif r10 >=  6: score += 3
    elif r10 >=  3: score += 2
    elif r10 >=  0: score += 1

    # 0–4 pts: consistency (how many of last 10 days beat SPY)
    if   opd >= 8: score += 4; flags.append("dems_consistent")
    elif opd >= 6: score += 3
    elif opd >= 4: score += 2
    elif opd >= 2: score += 1

    # 0–3 pts: acceleration (recent 5d > half of 20d alpha)
    if mo:
        score += 3; flags.append("dems_accel")

    # 0–2 pts: volume confirmation
    if vol is not None:
        if   vol >= 1.5: score += 2; flags.append("dems_vol_surge")
        elif vol >= 1.2: score += 1; flags.append("dems_vol_up")

    # 0–2 pts: anti-spike quality (distributed move = better)
    if not spk:
        score += 2
    else:
        flags.append("dems_spike")

    return min(score, 20), flags


# ── Extension Risk (informational — does not affect PCS) ─────────────────────
# Measures "am I entering late?" independently of signal strength.
# Phase: OBSERVATION. Fields are context for the model, not blockers.

def compute_extension_risk(d: dict) -> dict:
    """
    d must contain daily metrics (from fetch_daily_metrics) plus ret_4w_vs_spy.
    Returns extension_risk ("low"|"medium"|"high"|"extreme"), extension_points, extension_flags.
    """
    points = 0
    flags: list[str] = []

    dist = d.get("dist_sma20_atr")
    if dist is not None:
        if dist > 3.0:
            points += 3; flags.append("dist_sma20_atr_extreme")
        elif dist > 2.0:
            points += 2; flags.append("dist_sma20_atr_high")

    ret_4w = d.get("ret_4w_vs_spy")
    if ret_4w is not None:
        if ret_4w > 40:
            points += 3; flags.append("ret_4w_extreme")
        elif ret_4w > 25:
            points += 2; flags.append("ret_4w_extended")

    if d.get("momentum_decay"):
        points += 2; flags.append("momentum_decay")

    if d.get("spike_flag"):
        points += 2; flags.append("spike_flag")

    rsi = d.get("rsi_14")
    if rsi is not None:
        if rsi > 85:
            points += 2; flags.append("rsi_extreme")
        elif rsi > 78:
            points += 1; flags.append("rsi_high")

    if   points >= 6: risk = "extreme"
    elif points >= 4: risk = "high"
    elif points >= 2: risk = "medium"
    else:             risk = "low"

    return {"extension_risk": risk, "extension_points": points, "extension_flags": flags}


# ── A. Macro Permission (0–15) ────────────────────────────────────────────────
# What: Does the macro regime allow taking risk? Is it improving or deteriorating?
# Sources: macro_history.json → latest + last history row (for emergency flag)

def score_a(macro_latest: dict, last_hist: dict) -> tuple[float, list[str]]:
    score     = macro_latest.get("score") or 0
    trend     = macro_latest.get("trend", "Stable")
    emergency = bool(last_hist.get("flag_emergency_mode"))

    if   score >= 70: base = 13.0
    elif score >= 55: base = 10.0
    elif score >= 40: base =  6.0
    else:             base =  2.0

    flags = []
    if   trend == "Improving":      base += 1; flags.append("macro_improving")
    elif trend == "Deteriorating":  base -= 1; flags.append("macro_deteriorating")
    if emergency:                   base -= 3; flags.append("emergency_mode")

    return _clamp(base, 0, 15), flags


# ── B. Theme Flow (0–25) ──────────────────────────────────────────────────────
# What: Is capital entering the theme/sector this ticker belongs to?
# Primary: theme_proxy rot_score from rotation_signals (sector ETFs + futures)
# Fallback: average ret_13w_vs_spy of same-theme tickers in stock_candidates

def score_b(
    meta: dict,
    rot_idx: dict,
    cand_by_theme: dict[str, list],
) -> tuple[float, list[str]]:
    proxy  = meta.get("theme_proxy")
    theme  = meta.get("theme", "")
    flags  = []

    if proxy and proxy in rot_idx:
        rot = rot_idx[proxy].get("rot_score") or 0
        sig = rot_idx[proxy].get("signal") or ""
        if   rot >= 7: pts = 22.0; flags.append("theme_strong")
        elif rot >= 6: pts = 18.0; flags.append("theme_good")
        elif rot >= 5: pts = 14.0; flags.append("theme_moderate")
        elif rot >= 4: pts = 10.0; flags.append("theme_weak")
        elif rot >= 3: pts =  6.0; flags.append("theme_poor")
        else:          pts =  3.0; flags.append("theme_very_poor")
        if   sig == "COMPRA":    pts = min(25, pts + 2); flags.append("proxy_compra")
        elif sig == "ACUMULAR":  pts = min(25, pts + 1)
        return pts, flags

    # Fallback: average same-theme relative performance
    rets = cand_by_theme.get(theme, [])
    if rets:
        avg = sum(rets) / len(rets)
        if   avg >= 10: pts = 18.0; flags.append("theme_avg_strong")
        elif avg >= 5:  pts = 14.0; flags.append("theme_avg_good")
        elif avg >= 0:  pts = 11.0; flags.append("theme_avg_neutral")
        elif avg >= -5: pts =  8.0; flags.append("theme_avg_weak")
        else:           pts =  4.0; flags.append("theme_avg_poor")
        return pts, flags

    return 10.0, ["no_theme_data"]


# ── C. Individual Relative Strength (0–25) ────────────────────────────────────
# What: Is this specific ticker outperforming SPY on 4W and 13W timeframes?
# Sources: stock_candidates.json or rotation_signals.json (ret_4w_vs_spy, ret_13w_vs_spy)

def score_c(
    ticker: str, rot_idx: dict, cand_idx: dict
) -> tuple[float, list[str]]:
    d   = cand_idx.get(ticker) or rot_idx.get(ticker) or {}
    r4  = d.get("ret_4w_vs_spy")
    r13 = d.get("ret_13w_vs_spy")

    if r4 is None and r13 is None:
        return 8.0, ["rs_no_data"]

    combined = (r13 or 0) * 0.6 + (r4 or 0) * 0.4

    if   combined >= 15: pts = 23.0; flag = "rs_strong_leader"
    elif combined >= 7:  pts = 19.0; flag = "rs_leader"
    elif combined >= 2:  pts = 15.0; flag = "rs_outperform"
    elif combined >= -2: pts = 11.0; flag = "rs_neutral"
    elif combined >= -7: pts =  7.0; flag = "rs_underperform"
    else:                pts =  3.0; flag = "rs_laggard"

    return _clamp(pts, 0, 25), [flag]


# ── D. Individual Flow / Rotation Score (0–20) ────────────────────────────────
# What: Is money flowing into this ticker? Combines rot_score with CMF/OBV/volume.
# Sources: stock_candidates.json → rot_score + components

def score_d(
    ticker: str, rot_idx: dict, cand_idx: dict
) -> tuple[float, list[str]]:
    d   = cand_idx.get(ticker) or rot_idx.get(ticker) or {}
    rot = d.get("rot_score")

    if rot is None:
        return 7.0, ["flow_no_data"]

    comp   = d.get("components") or {}
    cmf    = comp.get("cmf_pts",     d.get("cmf_pts",     0)) or 0
    obv    = comp.get("obv_pts",     d.get("obv_pts",     0)) or 0
    vol    = comp.get("vol_rel_pts", d.get("vol_rel_pts", 0)) or 0
    no_ext = comp.get("no_ext_pts",  0) or 0

    if   rot >= 8: base = 17.0; flag = "rot_high"
    elif rot >= 6: base = 13.0; flag = "rot_good"
    elif rot >= 4: base =  9.0; flag = "rot_moderate"
    elif rot >= 2: base =  5.0; flag = "rot_weak"
    else:          base =  2.0; flag = "rot_low"

    flow_bonus   = min(3.0, (cmf + obv + vol) * 0.75)
    timing_bonus = 0.5 if no_ext >= 1 else 0.0

    flags = [flag]
    sig   = d.get("signal") or ""
    if   sig in ("CANDIDATO", "COMPRA"): flags.append("signal_candidato")
    elif sig == "EN_RADAR":              flags.append("signal_en_radar")
    elif sig == "ACUMULAR":              flags.append("signal_acumular")

    return _clamp(base + flow_bonus + timing_bonus, 0, 20), flags


# ── E. Early Acceleration (0–10) ─────────────────────────────────────────────
# What: Is this ticker accelerating before the move becomes obvious?
# Sources: cluster_has_rot_temprana, macd_pts, rsi_pts, streak_weeks

def score_e(
    ticker: str, rot_idx: dict, cand_idx: dict
) -> tuple[float, list[str]]:
    d    = cand_idx.get(ticker) or rot_idx.get(ticker) or {}
    comp = d.get("components") or {}

    is_early = bool(d.get("is_early_rotation") or d.get("cluster_has_rot_temprana"))
    macd     = comp.get("macd_pts", d.get("macd_pts", 0)) or 0
    rsi      = comp.get("rsi_pts",  d.get("rsi_pts",  0)) or 0
    streak   = d.get("streak_weeks") or 0

    if is_early:
        return 9.0, ["early_rotation_active"]
    if macd >= 1 and rsi >= 1:
        pts = 7.0 if streak >= 3 else 6.0
        flags = ["macd_rsi_positive"]
        if streak >= 3: flags.append("streak_3w")
        return pts, flags
    if macd >= 1 or rsi >= 1:
        return 4.0, ["partial_momentum"]
    if not d:
        return 3.0, ["no_early_data"]
    return 2.0, ["no_acceleration"]


# ── F. Data Quality / Tradability (0–5) ──────────────────────────────────────
# What: Is this ticker tradable and do we have enough signal data to trust the score?

def score_f(
    ticker: str, meta: dict, rot_idx: dict, cand_idx: dict
) -> tuple[float, list[str]]:
    if not meta.get("tradable", True):
        return 0.0, ["not_tradable"]

    has_cand = ticker in cand_idx
    has_rot  = ticker in rot_idx
    priority = meta.get("priority", "medium")

    pts   = 0.0
    flags = []
    if has_cand: pts += 3.0; flags.append("individual_data_ok")
    if has_rot:  pts += 1.5; flags.append("rotation_data_ok")
    if not has_cand and not has_rot: flags.append("no_signal_data")

    if   priority == "high": pts += 0.5
    elif priority == "low":  pts -= 1.0

    return _clamp(pts, 0, 5), flags


# ── PCS aggregation ───────────────────────────────────────────────────────────

def compute_pcs(
    ticker: str,
    meta: dict,
    macro_latest: dict,
    last_hist: dict,
    rot_idx: dict,
    cand_idx: dict,
    cand_by_theme: dict,
    daily: dict | None = None,
) -> dict:
    a, fa = score_a(macro_latest, last_hist)
    b, fb = score_b(meta, rot_idx, cand_by_theme)
    c, fc = score_c(ticker, rot_idx, cand_idx)
    d, fd = score_d(ticker, rot_idx, cand_idx)
    e, fe = score_e(ticker, rot_idx, cand_idx)
    f, ff = score_f(ticker, meta, rot_idx, cand_idx)

    pcs      = round(a + b + c + d + e + f, 1)
    eligible = meta.get("tradable", True) and f > 0

    raw  = cand_idx.get(ticker) or rot_idx.get(ticker) or {}
    comp = raw.get("components") or {}

    dems, dems_flags = compute_dems(daily or {})

    # Extension risk: needs both daily metrics and the weekly ret_4w_vs_spy
    ext_input = {**(daily or {}), "ret_4w_vs_spy": raw.get("ret_4w_vs_spy")}
    ext = compute_extension_risk(ext_input)

    return {
        "ticker":    ticker,
        "name":      meta.get("name", ""),
        "theme":     meta.get("theme", ""),
        "subtheme":  meta.get("subtheme", ""),
        "region":    meta.get("region", ""),
        "priority":  meta.get("priority", "medium"),
        "pcs":       pcs,
        "eligible":  eligible,
        "pcs_components": {
            "A_macro_permission":    round(a, 1),
            "B_theme_flow":          round(b, 1),
            "C_individual_rs":       round(c, 1),
            "D_individual_flow":     round(d, 1),
            "E_early_acceleration":  round(e, 1),
            "F_data_quality":        round(f, 1),
        },
        "flags":         fa + fb + fc + fd + fe + ff,
        "rot_score":     raw.get("rot_score"),
        "signal":        raw.get("signal"),
        "cluster":       raw.get("cluster"),
        "is_early":      bool(raw.get("is_early_rotation") or raw.get("cluster_has_rot_temprana")),
        "ret_4w_vs_spy": raw.get("ret_4w_vs_spy"),
        "ret_13w_vs_spy":raw.get("ret_13w_vs_spy"),
        "streak_weeks":  raw.get("streak_weeks"),
        "dist_52w_high": raw.get("dist_52w_high"),
        "macd_pts":      comp.get("macd_pts", raw.get("macd_pts")),
        "rsi_pts":       comp.get("rsi_pts",  raw.get("rsi_pts")),
        # Extension risk — informational, does not affect PCS
        "extension_risk":   ext["extension_risk"],
        "extension_points": ext["extension_points"],
        "extension_flags":  ext["extension_flags"],
        # Daily early-rotation signals — independent of PCS, only for EARLY_ROTATION
        "daily_signals": {
            "ret_5d_vs_spy":              (daily or {}).get("ret_5d_vs_spy"),
            "ret_10d_vs_spy":             (daily or {}).get("ret_10d_vs_spy"),
            "ret_20d_vs_spy":             (daily or {}).get("ret_20d_vs_spy"),
            "outperform_days_10d":        (daily or {}).get("outperform_days_10d"),
            "streak_days":                (daily or {}).get("streak_days"),
            "momentum_accel":             (daily or {}).get("momentum_accel"),
            "vol_5d_vs_20d":              (daily or {}).get("vol_5d_vs_20d"),
            "spike_flag":                 (daily or {}).get("spike_flag"),
            "dist_sma20_atr":             (daily or {}).get("dist_sma20_atr"),
            "rsi_14":                     (daily or {}).get("rsi_14"),
            "momentum_decay":             (daily or {}).get("momentum_decay", False),
            "daily_early_momentum_score": dems,
            "dems_flags":                 dems_flags,
        } if daily else None,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    universe  = _load("universe.json")
    macro_j   = _load("macro_history.json")
    rot_j     = _load("rotation_signals.json")
    cand_j    = _load("stock_candidates.json")

    macro_latest = macro_j.get("latest", {})
    macro_hist   = macro_j.get("history", [])
    last_hist    = macro_hist[-1] if macro_hist else {}

    rot_idx  = {s["ticker"]: s for s in rot_j.get("latest_signals", [])}

    # Build stock_candidates index with theme from universe
    u_meta   = {t["ticker"]: t for t in universe.get("tickers", [])}
    cand_idx = {}
    for c in cand_j.get("candidates", []):
        tk = c["ticker"]
        entry = dict(c)
        if tk in u_meta:
            entry["theme"] = u_meta[tk].get("theme", "")
        cand_idx[tk] = entry

    # Theme averages (ret_13w_vs_spy) for Component B fallback
    cand_by_theme: dict[str, list] = {}
    for c in cand_idx.values():
        th = c.get("theme", "")
        r  = c.get("ret_13w_vs_spy")
        if th and r is not None:
            cand_by_theme.setdefault(th, []).append(r)

    print("Fetching daily price data for DEMS...")
    daily_idx = fetch_daily_metrics(list(u_meta.keys()))
    dems_ok = sum(1 for d in daily_idx.values() if d)
    print(f"  Daily data: {dems_ok}/{len(u_meta)} tickers")

    candidates = []
    for ticker, meta in u_meta.items():
        result = compute_pcs(
            ticker, meta, macro_latest, last_hist,
            rot_idx, cand_idx, cand_by_theme,
            daily=daily_idx.get(ticker),
        )
        candidates.append(result)

    candidates.sort(key=lambda x: x["pcs"], reverse=True)

    eligible = [c for c in candidates if c["eligible"]]

    out = {
        "date":          str(date.today()),
        "macro_context": {
            "score":         macro_latest.get("score"),
            "regime":        macro_latest.get("regime"),
            "trend":         macro_latest.get("trend"),
            "phase_quality": macro_latest.get("phase_quality"),
            "delta_1w":      macro_latest.get("delta_1w"),
            "delta_1m":      macro_latest.get("delta_1m"),
        },
        "summary": {
            "total":     len(candidates),
            "eligible":  len(eligible),
            "pcs_ge_85": sum(1 for c in eligible if c["pcs"] >= 85),
            "pcs_ge_78": sum(1 for c in eligible if c["pcs"] >= 78),
            "pcs_ge_70": sum(1 for c in eligible if c["pcs"] >= 70),
            "pcs_lt_50": sum(1 for c in eligible if c["pcs"] < 50),
        },
        "candidates": candidates,
    }

    out_path = DATA / "ai_candidates.json"
    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    out_path.write_text(payload, encoding="utf-8")

    snap_dir = DATA / "universe_snapshots"
    snap_dir.mkdir(exist_ok=True)
    run_date = str(date.today())
    snap_path = snap_dir / f"{run_date}.json"
    snap_path.write_text(payload, encoding="utf-8")
    print(f"universe_snapshots/{run_date}.json — snapshot completo guardado")

    print(f"ai_candidates.json — {len(candidates)} tickers, {len(eligible)} elegibles")
    print(f"  PCS >= 85: {out['summary']['pcs_ge_85']}")
    print(f"  PCS >= 78: {out['summary']['pcs_ge_78']}")
    print(f"  PCS >= 70: {out['summary']['pcs_ge_70']}")
    top5 = eligible[:5]
    print("  Top 5:")
    for c in top5:
        comps = c["pcs_components"]
        print(f"    {c['ticker']:12} PCS={c['pcs']:5.1f}  "
              f"A={comps['A_macro_permission']} B={comps['B_theme_flow']} "
              f"C={comps['C_individual_rs']} D={comps['D_individual_flow']} "
              f"E={comps['E_early_acceleration']} F={comps['F_data_quality']}")


if __name__ == "__main__":
    run()
