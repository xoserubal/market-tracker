"""
Koncorde Plus Calculator — AI Picks Lab

Computes Koncorde Plus (OskarGallard, MPL 2.0) for each ticker in
ai_candidates.json and portfolio.json across 3 timeframes: D, 3D, W.

Formulas ported from Pine Script v6 by OskarGallard:
  tiburones (blue)  = NVI oscillator (institutional money)
  pececillos (green) = tendencia + PVI oscillator (retail money)
  tendencia (trend)  = composite RSI + MFI + BB + Stochastic
  ma_trend           = EMA(15) of tendencia

Outputs:
  docs/data/koncorde_data.json   — all tickers, served to portfolio.html via server.js
  docs/data/ai_candidates.json   — konc_* fields injected per candidate for AI model

This script is Step 9b in the pipeline (after event_detector.py, before paper_trading.py).

MPL 2.0 notice: original Pine Script formulas by OskarGallard, ported to Python.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
MIRROR_LOG = DATA / "mirror_signals.jsonl"
RESEARCH_LOG = DATA / "koncorde_signals_history.jsonl"

# ── Parameters matching Pine Script defaults ───────────────────────────────
PVI_NVI_LEN  = 15    # EMA length for PVI/NVI smoothing
NORM_PERIOD  = 90    # Min-Max normalization window
MFI_RSI_LEN  = 14   # RSI and MFI period
BB_LEN       = 25    # Bollinger Band period
BB_MULT      = 2.0   # BB multiplier
STOCH_LEN    = 21    # Stochastic period (uses bar high/low for range)
STOCH_SMOOTH = 3     # Stochastic SMA smoothing
MA_TREND_LEN = 15    # EMA period for ma_trend
MIN_BARS     = 120   # Minimum bars needed for valid readings
HISTORY_DAYS = 820   # ~3.3 years; enough for W indicator warmup


# ── Math helpers ───────────────────────────────────────────────────────────

def _ema(series: np.ndarray, period: int) -> np.ndarray:
    """Standard EMA seeded with SMA of first `period` values."""
    n = len(series)
    out = np.full(n, np.nan)
    if n < period:
        return out
    k = 2.0 / (period + 1)
    seed_vals = series[:period]
    if np.any(np.isnan(seed_vals)):
        return out
    out[period - 1] = float(np.mean(seed_vals))
    for i in range(period, n):
        v = series[i]
        out[i] = v * k + out[i - 1] * (1 - k) if not np.isnan(v) else out[i - 1]
    return out


def _rma(series: np.ndarray, period: int) -> np.ndarray:
    """Wilder RMA (alpha = 1/period) — used in RSI to match ta.rsi in Pine."""
    n = len(series)
    out = np.full(n, np.nan)
    if n < period:
        return out
    valid = series[:period]
    if np.any(np.isnan(valid)):
        return out
    out[period - 1] = float(np.mean(valid))
    a = 1.0 / period
    for i in range(period, n):
        v = series[i]
        out[i] = v * a + out[i - 1] * (1 - a) if not np.isnan(v) else out[i - 1]
    return out


def _sma(series: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(series).rolling(period, min_periods=period).mean().to_numpy()


def _highest(series: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(series).rolling(period, min_periods=period).max().to_numpy()


def _lowest(series: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(series).rolling(period, min_periods=period).min().to_numpy()


# ── PVI / NVI ──────────────────────────────────────────────────────────────

def _pvi_nvi(closes: np.ndarray, volumes: np.ndarray):
    """
    Paul Dysart's Positive/Negative Volume Index starting at 1000.
    PVI: updates when volume increases (tracks uninformed/retail money).
    NVI: updates when volume decreases (tracks informed/institutional money).
    """
    n = len(closes)
    pvi = np.full(n, 1000.0)
    nvi = np.full(n, 1000.0)
    for i in range(1, n):
        c0, c1 = closes[i], closes[i - 1]
        v0, v1 = volumes[i], volumes[i - 1]
        if np.isnan(c0) or np.isnan(c1) or c1 == 0 or np.isnan(v0) or np.isnan(v1):
            pvi[i] = pvi[i - 1]
            nvi[i] = nvi[i - 1]
            continue
        roc = (c0 - c1) / c1
        if v0 > v1:
            pvi[i] = pvi[i - 1] * (1 + roc)
            nvi[i] = nvi[i - 1]
        elif v0 < v1:
            pvi[i] = pvi[i - 1]
            nvi[i] = nvi[i - 1] * (1 + roc)
        else:
            pvi[i] = pvi[i - 1]
            nvi[i] = nvi[i - 1]
    return pvi, nvi


def _norm_osc(index_vals: np.ndarray, ema_vals: np.ndarray, period: int) -> np.ndarray:
    """(index - EMA) * 100 / (highest(EMA, period) - lowest(EMA, period))"""
    h = _highest(ema_vals, period)
    lo = _lowest(ema_vals, period)
    denom = h - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denom != 0, (index_vals - ema_vals) * 100.0 / denom, 0.0)


# ── Indicator components ───────────────────────────────────────────────────

def _rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder RSI matching ta.rsi() in Pine Script."""
    delta = np.diff(prices, prepend=np.nan)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = _rma(gain, period)
    avg_loss = _rma(loss, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(avg_loss != 0, avg_gain / avg_loss, np.inf)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi[np.isinf(rs)] = 100.0
    return rsi


def _mfi(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
         volumes: np.ndarray, period: int = 14) -> np.ndarray:
    """MFI using hlc3 as typical price, matching ta.mfi(hlc3, period) in Pine."""
    tp = (highs + lows + closes) / 3.0
    raw_mf = tp * volumes
    tp_prev = np.roll(tp, 1)
    tp_prev[0] = tp[0]
    pos_mf = np.where(tp > tp_prev, raw_mf, 0.0)
    neg_mf = np.where(tp < tp_prev, raw_mf, 0.0)
    pos_mf[0] = 0.0
    neg_mf[0] = 0.0
    s_pos = pd.Series(pos_mf).rolling(period, min_periods=period).sum().to_numpy()
    s_neg = pd.Series(neg_mf).rolling(period, min_periods=period).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        mfr = np.where(s_neg != 0, s_pos / s_neg, np.inf)
    mfi = 100.0 - 100.0 / (1.0 + mfr)
    mfi[np.isinf(mfr)] = 100.0
    return mfi


def _bb_osc(prices: np.ndarray, period: int = 25, mult: float = 2.0) -> np.ndarray:
    """
    BB oscillator: (price - basis) / (upper - lower) * 100
    where upper-lower = 2 * mult * stdev (population std, matching Pine's ta.stdev).
    Equivalent to f_bb(source, length) in the Pine Script.
    """
    s = pd.Series(prices)
    basis = s.rolling(period, min_periods=period).mean().to_numpy()
    std = s.rolling(period, min_periods=period).std(ddof=0).to_numpy()  # population stdev
    dev = mult * std
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dev != 0, (prices - basis) / (2.0 * dev) * 100.0, 0.0)


def _stoch(src: np.ndarray, highs: np.ndarray, lows: np.ndarray,
           period: int = 21, smooth: int = 3) -> np.ndarray:
    """
    Stochastic of src within actual bar high/low range, SMA-smoothed.
    Matches f_stoch(src, length, smoothFastD) in Pine, which uses bar
    high/low (not src) for the %K range.
    """
    hh = _highest(highs, period)
    ll = _lowest(lows, period)
    denom = hh - ll
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where(denom != 0, 100.0 * (src - ll) / denom, 50.0)
    return _sma(k, smooth)


# ── Full Koncorde Plus (one timeframe) ────────────────────────────────────

def _calc_koncorde_plus(opens: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                        closes: np.ndarray, volumes: np.ndarray):
    """
    Returns (blue, green, trend, trend_ma) arrays.
    NaN where insufficient data.

    blue      = tiburones = NVI oscillator (institutional)
    green     = pececillos = tendencia + PVI oscillator (retail)
    trend     = tendencia = (RSI + MFI + BB_osc + Stoch/3) / 2
    trend_ma  = EMA(15) of trend
    """
    ohlc4 = (opens + highs + lows + closes) / 4.0

    # PVI / NVI oscillators
    pvi, nvi = _pvi_nvi(closes, volumes)
    pvi_ema = _ema(pvi, PVI_NVI_LEN)
    nvi_ema = _ema(nvi, PVI_NVI_LEN)
    osc_pos = _norm_osc(pvi, pvi_ema, NORM_PERIOD)  # PVI-based (retail)
    osc_neg = _norm_osc(nvi, nvi_ema, NORM_PERIOD)  # NVI-based (institutional)

    blue = osc_neg  # tiburones = SMA(1) of osc_neg = osc_neg

    # Trend composite
    rsi_val = _rsi(ohlc4, MFI_RSI_LEN)
    mfi_val = _mfi(highs, lows, closes, volumes, MFI_RSI_LEN)
    osc_bb  = _bb_osc(ohlc4, BB_LEN, BB_MULT)
    stoc    = _stoch(ohlc4, highs, lows, STOCH_LEN, STOCH_SMOOTH)

    # tendencia = (RSI + MFI + BB_osc + Stoch/3) / 2  (Pine formula verbatim)
    trend = (rsi_val + mfi_val + osc_bb + stoc / 3.0) / 2.0
    green = trend + osc_pos     # pececillos
    trend_ma = _ema(trend, MA_TREND_LEN)

    return blue, green, trend, trend_ma


# ── Resampling helpers ─────────────────────────────────────────────────────

def _resample_3d(df: pd.DataFrame) -> pd.DataFrame:
    """
    Non-overlapping 3-session OHLCV blocks anchored so that the most
    recent complete block = the last 3 closed sessions.
    Any leading partial block (< 3 sessions) is discarded.
    """
    n = len(df)
    remainder = n % 3
    rows = []
    dates = []
    for i in range(remainder, n, 3):
        block = df.iloc[i:i + 3]
        if len(block) < 3:
            break
        rows.append({
            "open":   float(block["open"].iloc[0]),
            "high":   float(block["high"].max()),
            "low":    float(block["low"].min()),
            "close":  float(block["close"].iloc[-1]),
            "volume": float(block["volume"].sum()),
        })
        dates.append(block.index[-1])
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.DataFrame(rows, index=pd.Index(dates))


def _resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily bars to weekly (Mon–Fri, closing on Friday)."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame(columns=["open","high","low","close","volume"])
    idx = df.index
    if idx.tz is not None:
        df = df.copy()
        df.index = idx.tz_localize(None)
    wk = df.resample("W-FRI").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])
    return wk


# ── Slope helper ───────────────────────────────────────────────────────────

def _slope(arr: np.ndarray):
    """Returns (delta_1, slope_3bar) from last element, or (None, None)."""
    if len(arr) < 3:
        return None, None
    if any(np.isnan(arr[i]) for i in (-1, -2, -3)):
        return None, None
    d1 = float(arr[-1]) - float(arr[-2])
    s3 = (float(arr[-1]) - float(arr[-3])) / 2.0
    return round(d1, 4), round(s3, 4)


def _last(arr: np.ndarray):
    if len(arr) == 0:
        return None
    v = float(arr[-1])
    return round(v, 2) if not np.isnan(v) else None


def _down_2_bars(arr: np.ndarray) -> bool:
    """True if the last 3 closed bars show strictly decreasing values (persistent deterioration)."""
    if len(arr) < 3:
        return False
    if any(np.isnan(arr[i]) for i in (-1, -2, -3)):
        return False
    return bool(arr[-1] < arr[-2] < arr[-3])


def _cross_up(arr: np.ndarray) -> bool:
    """True if the last closed bar crosses from negative to non-negative (fresh flip)."""
    if len(arr) < 2:
        return False
    if np.isnan(arr[-1]) or np.isnan(arr[-2]):
        return False
    return bool(arr[-1] >= 0 and arr[-2] < 0)


def _state(blue, green) -> str:
    if blue is None or green is None:
        return "neutral"
    if blue >= 0 and green < 0:
        return "accumulation"
    if blue >= 0 and green >= 0:
        return "up"
    if blue < 0 and green > 0:
        return "distribution"
    return "down"


def _konc_alignment(state_d, state_3d, state_w, blue_down_2_bars_3d: bool) -> str:
    """
    Summary reading across D/3D/W timeframes. Evaluated top-to-bottom, first match
    wins — this order IS the priority (kept as a single source of truth instead of
    a prose list that can drift from the actual if/elif order):

      1. distribution_warning              — 3D weak, corroborated by D or W
      2. bullish_pending_3d_confirmation    — 3D weak in isolation, D+W both bullish
      3. bearish_aligned                    — 3D down, W bearish
      4. accumulation_setup                 — 3D accumulation, W not bearish
      5. bullish_aligned                    — 3D and W both bullish
      6. mixed                              — none of the above
      7. neutral                            — missing 3D/W data

    2026-07-21 fix (TNZ.TO retrospective): a single 3D=="distribution" reading (or a
    2-bar declining 3D blue trend) used to veto straight to distribution_warning with
    no exception, even when D and W both read bullish. 3D is a non-overlapping
    3-session block, so during multi-week accumulations it can be more sensitive to
    exactly which session lands on the block boundary than to the actual trend — in
    TNZ.TO's case it flip-flopped distribution/up 5 times in 10 sessions while D and W
    both trended up. An uncorroborated 3D-only weak reading is now demoted to
    bullish_pending_3d_confirmation instead of triggering the strongest alarm; it still
    takes priority over accumulation_setup/bullish_aligned/mixed, since a real conflict
    with 3D is still worth flagging, just not as "distribution_warning".
    """
    bullish = ("up", "accumulation")
    bearish = ("distribution", "down")

    if state_3d is None or state_w is None:
        return "neutral"

    d_w_bullish = state_d in bullish and state_w in bullish
    tf3d_weak = state_3d == "distribution" or blue_down_2_bars_3d

    if state_3d == "distribution" and (state_w in bearish or state_d in bearish):
        return "distribution_warning"
    if blue_down_2_bars_3d and state_w in bearish:
        return "distribution_warning"
    if tf3d_weak and d_w_bullish:
        return "bullish_pending_3d_confirmation"
    if state_3d == "down" and state_w in bearish:
        return "bearish_aligned"
    if state_3d == "accumulation" and state_w not in bearish:
        return "accumulation_setup"
    if state_3d in bullish and state_w in bullish:
        return "bullish_aligned"
    return "mixed"


# ── Per-ticker computation ─────────────────────────────────────────────────

def _compute_tf(df: pd.DataFrame, tf_name: str) -> tuple[dict, np.ndarray | None]:
    """
    Compute Koncorde Plus for one timeframe df. Returns (flat dict of konc_{tf}_*
    fields, raw blue array) — the array is exposed so compute_for_ticker can feed
    the D-timeframe blue series into _compute_research_fields() without a second
    (duplicate) call to _calc_koncorde_plus().
    """
    pfx = f"konc_{tf_name}"
    nulls = {k: None for k in [
        f"{pfx}_blue", f"{pfx}_green", f"{pfx}_trend", f"{pfx}_trend_ma", f"{pfx}_state",
        f"{pfx}_blue_delta1", f"{pfx}_blue_slope", f"{pfx}_green_delta1", f"{pfx}_green_slope",
        f"{pfx}_trend_delta1", f"{pfx}_trend_slope", f"{pfx}_bar_date",
    ]}
    nulls[f"{pfx}_blue_down_2_bars"]  = False
    nulls[f"{pfx}_blue_cross_up"]     = False
    nulls[f"{pfx}_accumulation_flag"] = False
    nulls[f"{pfx}_distribution_flag"] = False
    nulls[f"{pfx}_bar_closed"]        = True
    if len(df) < MIN_BARS:
        return nulls, None
    try:
        o = df["open"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        lo = df["low"].to_numpy(dtype=float)
        c = df["close"].to_numpy(dtype=float)
        v = df["volume"].to_numpy(dtype=float)

        blue_a, green_a, trend_a, tma_a = _calc_koncorde_plus(o, h, lo, c, v)

        b  = _last(blue_a)
        g  = _last(green_a)
        t  = _last(trend_a)
        tm = _last(tma_a)
        b_d1, b_s  = _slope(blue_a)
        g_d1, g_s  = _slope(green_a)
        t_d1, t_s  = _slope(trend_a)
        state = _state(b, g)

        last_idx = df.index[-1]
        bar_date = last_idx.strftime("%Y-%m-%d") if hasattr(last_idx, "strftime") else str(last_idx)

        return {
            f"{pfx}_blue":               b,
            f"{pfx}_green":              g,
            f"{pfx}_trend":              t,
            f"{pfx}_trend_ma":           tm,
            f"{pfx}_state":              state,
            f"{pfx}_blue_delta1":        b_d1,
            f"{pfx}_blue_slope":         b_s,
            f"{pfx}_green_delta1":       g_d1,
            f"{pfx}_green_slope":        g_s,
            f"{pfx}_trend_delta1":       t_d1,
            f"{pfx}_trend_slope":        t_s,
            # Deterioration/flags — see hoja sección 1.5/1.7
            f"{pfx}_blue_down_2_bars":   _down_2_bars(blue_a),
            # Fresh negative->positive flip — used by the "espejo" mirror-reversal signal
            f"{pfx}_blue_cross_up":      _cross_up(blue_a),
            f"{pfx}_accumulation_flag":  state == "accumulation",
            f"{pfx}_distribution_flag":  state == "distribution",
            # This pipeline runs end-of-day on yf.download() — always a closed bar.
            # Flip to false if this is ever run intraday on a partial bar.
            f"{pfx}_bar_closed":         True,
            f"{pfx}_bar_date":           bar_date,
        }, blue_a
    except Exception as e:
        print(f"    compute_tf({tf_name}) error: {e}")
        return nulls, None


def _mirror_signal(
    d_state, d_cross_up, d_green,
    td_state, td_cross_up, td_green,
    w_blue,
) -> str:
    """
    "Espejo" reversal — patrón de seguimiento (2026-07-03), no HARD_RULE, no en el
    payload IA todavía: blue cruza de negativo a positivo mientras green sigue
    negativo (estado accumulation), simultáneamente en D y 3D — el cruce fresco en
    ambos timeframes es lo que confirma que no es ruido de un solo día — con W
    (blue) todavía negativo, es decir la tendencia semanal de fondo aún no ha
    girado. Eso último sugiere que puede ser el inicio de una mini-tendencia (al
    menos a nivel 3D) en vez de solo un rebote de un día, porque todavía hay
    margen antes de que el timeframe lento lo refleje.
    """
    d_ok = (d_state == "accumulation" and d_cross_up
            and d_green is not None and d_green < 0)
    td_ok = (td_state == "accumulation" and td_cross_up
             and td_green is not None and td_green < 0)
    w_ok = w_blue is not None and w_blue < 0

    if d_ok and td_ok and w_ok:
        return "mirror_reversal_confirmed"
    if d_ok and w_ok:
        return "mirror_reversal_daily_only"
    return "none"


def _compute_research_fields(df: pd.DataFrame, blue_d: np.ndarray | None) -> dict:
    """
    Koncorde Research Log (2026-07-21, TNZ.TO retrospective follow-up) — objective,
    self-contained "stealth accumulation" ingredients logged for every ticker in the
    universe. Deliberately NOT gated into any signal, WATCH tier, radar, or
    HARD_RULE yet: accumulation_ramp/flush_reclaim were proposed based on a single
    case (TNZ.TO) and the project's own principle is to not add complexity before
    there's data to justify it (see CLAUDE.md "Evaluación general del método").
    Plan: accumulate 4-8 weeks of these fields + ret_1w/2w/1m, then decide whether
    to promote any combination to an operational signal.

    All fields are computed from the ticker's own daily OHLCV history only (no
    cross-ticker or benchmark dependency) — Flow Score / Early Flow Score are
    deliberately NOT ported here, because a faithful port needs SPY-relative
    returns, price RSI/MACD and 52w-high distance that this pipeline doesn't
    compute for the full ~197-ticker Koncorde universe (only for the narrower
    ai_candidates.json PCS universe). Defaulting those inputs to zero would
    produce Flow Score values that don't match what the dashboard actually shows
    — fabricating numbers is worse than not logging them. Left as a documented
    follow-up, not silently dropped.
    """
    nulls = {
        "konc_d_blue_positive_days_6": None,
        "konc_d_blue_up_count_6":      None,
        "konc_d_blue_slope_6":         None,
        "volume_vs_20d":               None,
        "low_break_20d":               False,
        "close_reclaim_3d":            False,
        "distance_to_sma20_atr":       None,
        "price_range_20d_position":    None,
    }
    if len(df) < 26 or blue_d is None or len(blue_d) < 7:
        return nulls
    try:
        h  = df["high"].to_numpy(dtype=float)
        lo = df["low"].to_numpy(dtype=float)
        c  = df["close"].to_numpy(dtype=float)
        v  = df["volume"].to_numpy(dtype=float)
        n  = len(c)

        last6 = blue_d[-6:]
        pos_days_6 = None if np.any(np.isnan(last6)) else int(np.sum(last6 > 0))
        last7 = blue_d[-7:]
        up_count_6 = None if np.any(np.isnan(last7)) else int(np.sum(np.diff(last7) > 0))
        blue_slope_6 = None
        if not (np.isnan(blue_d[-1]) or np.isnan(blue_d[-6])):
            blue_slope_6 = round((float(blue_d[-1]) - float(blue_d[-6])) / 5.0, 4)

        # ATR14 (Wilder) + distance to SMA20 in ATR units — same formula as
        # pcs_calculator.py's dist_sma20_atr, recomputed here (not reused) because
        # this needs to cover the full Koncorde universe, not just the 128 PCS
        # candidates that pcs_calculator.py has data for.
        prev_c = np.roll(c, 1)
        prev_c[0] = c[0]
        tr = np.maximum(h - lo, np.maximum(np.abs(h - prev_c), np.abs(lo - prev_c)))
        atr14 = _rma(tr, 14)
        sma20 = _sma(c, 20)
        dist_atr = None
        if not np.isnan(atr14[-1]) and atr14[-1] != 0 and not np.isnan(sma20[-1]):
            dist_atr = round((float(c[-1]) - float(sma20[-1])) / float(atr14[-1]), 2)

        vol_sma20 = _sma(v, 20)
        vol_ratio = None
        if not np.isnan(vol_sma20[-1]) and vol_sma20[-1] != 0:
            vol_ratio = round(float(v[-1]) / float(vol_sma20[-1]), 2)

        hh20 = _highest(h, 20)
        ll20 = _lowest(lo, 20)
        range_pos = None
        if not np.isnan(hh20[-1]) and not np.isnan(ll20[-1]) and hh20[-1] != ll20[-1]:
            range_pos = round((float(c[-1]) - float(ll20[-1])) / (float(hh20[-1]) - float(ll20[-1])), 4)

        def _is_fresh_20d_low(i: int) -> bool:
            if i < 21:
                return False
            prior_low = float(np.min(lo[i - 20:i]))
            return bool(lo[i] <= prior_low)

        low_break_today = _is_fresh_20d_low(n - 1)

        # Reclaim within 3 sessions: a fresh 20d low happened in the last 3 bars,
        # and today's close has since recovered back above that prior low.
        reclaim = False
        for i in range(max(0, n - 3), n):
            if i < 21:
                continue
            prior_low = float(np.min(lo[i - 20:i]))
            if lo[i] <= prior_low and float(c[-1]) > prior_low:
                reclaim = True
                break

        return {
            "konc_d_blue_positive_days_6": pos_days_6,
            "konc_d_blue_up_count_6":      up_count_6,
            "konc_d_blue_slope_6":         blue_slope_6,
            "volume_vs_20d":               vol_ratio,
            "low_break_20d":               bool(low_break_today),
            "close_reclaim_3d":            bool(reclaim),
            "distance_to_sma20_atr":       dist_atr,
            "price_range_20d_position":    range_pos,
        }
    except Exception as e:
        print(f"    compute_research_fields error: {e}")
        return nulls


def compute_for_ticker(df: pd.DataFrame) -> dict:
    """Compute all 3 timeframes for a single daily OHLCV DataFrame."""
    result: dict = {}

    # Daily (D)
    d_dict, blue_d = _compute_tf(df, "d")
    result.update(d_dict)

    # 3D — non-overlapping 3-session blocks
    df_3d = _resample_3d(df)
    dict_3d, _ = _compute_tf(df_3d, "3d")
    result.update(dict_3d)

    # Weekly
    df_w = _resample_weekly(df)
    # For weekly, use 100 as minimum (slightly lower — weekly bars are fewer)
    orig_min = MIN_BARS
    globals()["MIN_BARS"] = 100
    dict_w, _ = _compute_tf(df_w, "w")
    globals()["MIN_BARS"] = orig_min
    result.update(dict_w)

    result["konc_alignment"] = _konc_alignment(
        result.get("konc_d_state"),
        result.get("konc_3d_state"),
        result.get("konc_w_state"),
        result.get("konc_3d_blue_down_2_bars", False),
    )

    result["konc_mirror_signal"] = _mirror_signal(
        result.get("konc_d_state"), result.get("konc_d_blue_cross_up"), result.get("konc_d_green"),
        result.get("konc_3d_state"), result.get("konc_3d_blue_cross_up"), result.get("konc_3d_green"),
        result.get("konc_w_blue"),
    )

    result.update(_compute_research_fields(df, blue_d))

    return result


# ── Download ───────────────────────────────────────────────────────────────

def download_ohlcv(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Download HISTORY_DAYS of daily OHLCV from Yahoo Finance."""
    end   = datetime.today()
    start = (end - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")
    results: dict[str, pd.DataFrame] = {}

    batch_size = 25
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            raw = yf.download(
                batch, start=start, end=end_s,
                auto_adjust=True, progress=False,
                group_by="ticker",
            )
        except Exception as e:
            print(f"  Download error (batch {i // batch_size + 1}): {e}")
            continue

        if len(batch) == 1:
            tk = batch[0]
            try:
                df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
                df.columns = ["open", "high", "low", "close", "volume"]
                if hasattr(df.index, "tz") and df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                df = df.dropna(subset=["close"])
                if not df.empty:
                    results[tk] = df
            except Exception:
                pass
        else:
            for tk in batch:
                try:
                    sub = raw[tk][["Open", "High", "Low", "Close", "Volume"]].copy()
                    sub.columns = ["open", "high", "low", "close", "volume"]
                    if hasattr(sub.index, "tz") and sub.index.tz is not None:
                        sub.index = sub.index.tz_localize(None)
                    sub = sub.dropna(subset=["close"])
                    if not sub.empty:
                        results[tk] = sub
                except Exception:
                    pass

    return results


# ── Main ───────────────────────────────────────────────────────────────────

MARKET_TRACKER_TICKERS = {
    # Major indices (ETF proxies where index has no volume)
    "^GSPC", "^IXIC", "URTH", "FEZ", "EEM", "IWM", "RSP",
    # MAG 6
    "AAPL", "GOOGL", "MSFT", "AMZN",
    # Bonds / commodities / crypto
    "TLT", "BTC-USD",
    # Europe (indices included — fail gracefully if no volume)
    "^FTSE", "^FCHI", "^GDAXI", "^AEX", "^IBEX", "FTSEMIB.MI",
    # Asia ETFs
    "EWJ", "EWY", "MCHI", "EWH",
    # LATAM ETFs
    "EWW", "ARGT",
    # US Sector ETFs
    "XLK", "XLV", "XLF", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE",
    # EU Sector ETFs
    "EXV1.DE", "IQQH.DE", "EXV6.DE", "EXH1.DE", "EXH4.DE",
    "EXV5.DE", "EXV2.DE", "EXH7.DE", "EXH8.DE", "IPRP.AS",
    # Uranium
    "URNM", "U-U.TO", "CCJ", "NXE", "DNN", "LEU",
    # Coal stocks
    "HCC", "AMR", "BTU",
}


def _log_mirror_signals(
    koncorde_out: dict[str, dict],
    price_data: dict[str, pd.DataFrame],
    today: str,
) -> None:
    """
    Fase de seguimiento del patrón "espejo" (2026-07-03): registra en
    docs/data/mirror_signals.jsonl CADA ticker del universo (no solo picks de la
    IA) que muestre mirror_reversal_confirmed hoy, para poder evaluar más adelante
    si el patrón anticipa subidas — mismo enfoque que compare_vs_baselines.py con
    las baselines mecánicas. ret_1w/2w/1m se dejan en null aquí; rellenarlos
    requeriría un script de seguimiento propio (al estilo update_performance.py),
    no incluido en este cambio.

    Deduplicado por (ticker, date): el pipeline corre 2x/día, pero el cruce en D
    (konc_d_blue_cross_up) solo puede ser true el día exacto en que ocurre — al
    día siguiente el valor anterior ya es positivo — así que el mismo evento no
    debería repetirse más de un día salvo casos límite raros.
    """
    seen: set[tuple[str, str]] = set()
    if MIRROR_LOG.exists():
        for line in MIRROR_LOG.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                seen.add((rec.get("ticker"), rec.get("date")))
            except json.JSONDecodeError:
                continue

    MIRROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    n_logged = 0
    with MIRROR_LOG.open("a", encoding="utf-8") as f:
        for tk, k in koncorde_out.items():
            if k.get("konc_mirror_signal") != "mirror_reversal_confirmed":
                continue
            if (tk, today) in seen:
                continue
            df = price_data.get(tk)
            price = float(df["close"].iloc[-1]) if df is not None and not df.empty else None
            f.write(json.dumps({
                "date":             today,
                "ticker":           tk,
                "price":            price,
                "konc_d_blue":      k.get("konc_d_blue"),
                "konc_d_green":     k.get("konc_d_green"),
                "konc_3d_blue":     k.get("konc_3d_blue"),
                "konc_3d_green":    k.get("konc_3d_green"),
                "konc_w_blue":      k.get("konc_w_blue"),
                "konc_3d_bar_date": k.get("konc_3d_bar_date"),
                "ret_1w": None, "ret_2w": None, "ret_1m": None,
            }, ensure_ascii=False) + "\n")
            seen.add((tk, today))
            n_logged += 1
    if n_logged:
        print(f"  mirror_signals.jsonl: {n_logged} nueva(s) señal(es) 'espejo' confirmada(s)")


def _log_research_history(koncorde_out: dict[str, dict], today: str) -> None:
    """
    Koncorde Research Log (2026-07-21) — one row per ticker per day, for EVERY
    ticker in the universe (not just AI candidates), so patterns like TNZ.TO's
    multi-week stealth accumulation can be studied after the fact without git
    archaeology. Purely observational — see _compute_research_fields() docstring
    for why nothing here gates a signal yet.

    Deduplicated by (ticker, date): the pipeline runs 2x/day but these are all
    end-of-day daily-bar readings, so the second run of a given day would
    otherwise duplicate every row.
    """
    seen: set[tuple[str, str]] = set()
    if RESEARCH_LOG.exists():
        for line in RESEARCH_LOG.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                seen.add((rec.get("ticker"), rec.get("date")))
            except json.JSONDecodeError:
                continue

    RESEARCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    n_logged = 0
    with RESEARCH_LOG.open("a", encoding="utf-8") as f:
        for tk, k in koncorde_out.items():
            if (tk, today) in seen:
                continue
            f.write(json.dumps({
                "date":                        today,
                "ticker":                      tk,
                "konc_d_state":                k.get("konc_d_state"),
                "konc_3d_state":               k.get("konc_3d_state"),
                "konc_w_state":                k.get("konc_w_state"),
                "konc_alignment":              k.get("konc_alignment"),
                "konc_mirror_signal":          k.get("konc_mirror_signal"),
                "konc_d_blue_slope_3":         k.get("konc_d_blue_slope"),
                "konc_d_blue_slope_6":         k.get("konc_d_blue_slope_6"),
                "konc_w_blue_slope":           k.get("konc_w_blue_slope"),
                "konc_d_blue_positive_days_6": k.get("konc_d_blue_positive_days_6"),
                "konc_d_blue_up_count_6":      k.get("konc_d_blue_up_count_6"),
                "volume_vs_20d":               k.get("volume_vs_20d"),
                "low_break_20d":               k.get("low_break_20d"),
                "close_reclaim_3d":            k.get("close_reclaim_3d"),
                "distance_to_sma20_atr":       k.get("distance_to_sma20_atr"),
                "price_range_20d_position":    k.get("price_range_20d_position"),
                # Filled in later by a follow-up script (update_performance.py
                # pattern) once enough sessions have passed — not computed here.
                "ret_1w": None, "ret_2w": None, "ret_1m": None,
            }, ensure_ascii=False) + "\n")
            seen.add((tk, today))
            n_logged += 1
    if n_logged:
        print(f"  koncorde_signals_history.jsonl: {n_logged} ticker(s) logged")


def run() -> None:
    today = datetime.today().strftime("%Y-%m-%d")
    tickers: set[str] = set(MARKET_TRACKER_TICKERS)

    # Collect tickers from ai_candidates.json
    cands_path = DATA / "ai_candidates.json"
    cands_data: dict = {}
    cands: list[dict] = []
    if cands_path.exists():
        cands_data = json.loads(cands_path.read_text(encoding="utf-8"))
        cands = cands_data.get("candidates", [])
        for c in cands:
            tk = c.get("ticker")
            if tk:
                tickers.add(tk)

    # Collect tickers from portfolio.json
    portfolio_path = ROOT / "portfolio.json"
    if portfolio_path.exists():
        portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
        for sec in portfolio.get("sections", []):
            for item in sec.get("items", []):
                tk = item.get("ticker")
                if tk:
                    tickers.add(tk)

    # Collect tickers from open AI picks (all portfolios, including MIMO_SHADOW) —
    # so a ticker that drops out of the 91-candidate universe (left_universe=true)
    # keeps getting Koncorde computed while the position stays open (needed for
    # shadow exit tracking in koncorde_shadow_exits.py).
    picks_path = DATA / "ai_picks.json"
    if picks_path.exists():
        picks = json.loads(picks_path.read_text(encoding="utf-8"))
        for ptf in picks.get("portfolios", {}).values():
            for pos in ptf.get("positions", []):
                tk = pos.get("ticker")
                if tk:
                    tickers.add(tk)

    ticker_list = sorted(tickers)
    print(f"Koncorde Plus: downloading OHLCV for {len(ticker_list)} tickers…")

    price_data = download_ohlcv(ticker_list)
    print(f"  Downloaded {len(price_data)} tickers OK")

    # Compute Koncorde for each ticker
    koncorde_out: dict[str, dict] = {}
    failed: list[str] = []
    for tk in ticker_list:
        df = price_data.get(tk)
        if df is None or df.empty:
            failed.append(tk)
            continue
        try:
            k = compute_for_ticker(df)
            k["updated"] = today
            koncorde_out[tk] = k
        except Exception as e:
            print(f"  {tk}: computation error — {e}")
            failed.append(tk)

    computed = len(koncorde_out)
    print(f"  Computed: {computed}  Failed: {len(failed)}")
    if failed:
        show = failed[:10]
        print(f"  Failed: {show}{'…' if len(failed) > 10 else ''}")

    _log_mirror_signals(koncorde_out, price_data, today)
    _log_research_history(koncorde_out, today)

    # Write docs/data/koncorde_data.json (served to portfolio.html via server.js)
    out_path = DATA / "koncorde_data.json"
    out_path.write_text(
        json.dumps({"date": today, "tickers": koncorde_out}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  koncorde_data.json written ({computed} tickers)")

    # Inject konc_* fields into ai_candidates.json (for the AI model payload)
    if cands and cands_data:
        updated = 0
        for c in cands:
            tk = c.get("ticker")
            if tk and tk in koncorde_out:
                for key, val in koncorde_out[tk].items():
                    if key != "updated":
                        c[key] = val
                updated += 1
        cands_path.write_text(
            json.dumps(cands_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  ai_candidates.json updated with konc_* fields ({updated} candidates)")


if __name__ == "__main__":
    run()
