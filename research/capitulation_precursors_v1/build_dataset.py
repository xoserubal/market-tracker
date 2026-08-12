"""
Builds the full capitulation-event dataset (both outcomes: rebound and no
rebound) for the preregistered study in
wiki/PREREGISTRO_CAPITULACION_PRECURSORES_V1.md.

Event/outcome/feature definitions are copied verbatim from that document --
do not tune thresholds here after seeing results, change the doc first.

Usage:
    py -3 build_dataset.py                 # download + build
    py -3 build_dataset.py --save-cache     # also cache raw prices for reruns
    py -3 build_dataset.py --no-fetch       # reuse cached prices
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

HERE = Path(__file__).parent
CACHE_PATH = HERE / "_price_cache.parquet"
OUT_PATH = HERE / "outputs" / "capitulation_events.jsonl"

TICKERS = ("FDR.AX,EOS.AX,MLX.AX,R9U2.F,GSP.MI,HFG.DE,ASM.AS,FXPO.L,SLP.L,KIST.L,"
           "SEDANA.ST,JD,BABA,AFM.V,DMX.V,VAL,BNKR.TO,UCO,QQQ,VLE.TO,TNZ.TO,UVXY,"
           "BTCC-B.TO,ROOT,SE,AAG.V,GRSL.V,EXK,COIN,CORZ,DPM.TO,NVDA,QXO,GDXJ,KWEB,"
           "FXI,AG,TDOC,NBIS,ASTS,VFF,HIMS,III.TO,OSCR,AWX.V,SLS.TO,WRN.TO,USAU,VGZ,"
           "PNPN.V,IE,RCAT,BOGO.V,EOSE,ASPI,MSTR,SSV.V,KOS,SASK.V,LCX.V,TAL.TO,VAR.OL,"
           "TTI,CRON,TSND.V,PLNHF,MAPS,MSOS,GTBIF,CVE,SU,TOU.TO,WCP.TO,FRU.TO,VNOM,OXY,"
           "SUPV,GGAL,CRESY,CEPU,YPF,VIST,PAM,BBAR,IRS,LOMA,TGS,GLNG,BUR,TSLA,AMD,URA,"
           "URI,LLY,ISRG,SYK,TMO,DHR,BSX,VRTX,UNH,HUM,CI,CVS,JNJ,MRK,ABBV,PFE,SLS,ACMR,"
           "MU,GLEN.L").split(",")
TICKERS = sorted(set(TICKERS))

# --- frozen event/outcome/feature definitions (wiki/PREREGISTRO_CAPITULACION_PRECURSORES_V1.md) ---
LOOKBACK_PEAK = 40
MAX_DROP_WINDOW = 15
MIN_DROP_PCT = 18.0
RALLY_WINDOW = 45
MIN_RALLY_PCT = 18.0
MIN_RALLY_SUSTAIN_DAYS = 5
SUSTAIN_PCT = 10.0
MIN_BARS_REQUIRED = LOOKBACK_PEAK + RALLY_WINDOW + 50


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr_pct(df, period=14):
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr / close * 100


def find_events(ticker, df):
    close = df["Close"].dropna()
    if len(close) < MIN_BARS_REQUIRED:
        return []

    volume = df["Volume"].reindex(close.index)
    vol_reliable = not (volume.fillna(0) == 0).all()
    vol_ma20 = volume.rolling(20).mean()
    vol_ratio = volume / vol_ma20

    r = rsi(close)
    atrp = atr_pct(df.reindex(close.index))

    n = len(close)
    events = []
    i = LOOKBACK_PEAK
    while i < n:
        window = close.iloc[max(0, i - LOOKBACK_PEAK):i + 1]
        peak_val = window.max()
        peak_idx_pos = int(window.values.argmax())
        pos_gap = i - (max(0, i - LOOKBACK_PEAK) + peak_idx_pos)

        if not (1 <= pos_gap <= MAX_DROP_WINDOW):
            i += 1
            continue

        trough_val = close.iloc[i]
        drop_pct = (trough_val / peak_val - 1) * 100
        if drop_pct > -MIN_DROP_PCT:
            i += 1
            continue

        # short local-minimum confirmation (2 sessions forward, defines the trough only)
        if i + 2 < n and close.iloc[i + 1:i + 3].min() < trough_val * 0.99:
            i += 1
            continue

        trough_date = close.index[i]
        peak_date = window.index[peak_idx_pos]

        # --- outcome label (forward-looking, used ONLY for the label) ---
        fwd = close.iloc[i:i + RALLY_WINDOW + 1]
        if len(fwd) < MIN_RALLY_SUSTAIN_DAYS + 2:
            i += 1
            continue
        rally_peak_val = fwd.max()
        rally_pct = (rally_peak_val / trough_val - 1) * 100
        sustain_level = trough_val * (1 + SUSTAIN_PCT / 100)
        sustain_days = int((fwd >= sustain_level).sum())
        rebound = int(rally_pct >= MIN_RALLY_PCT and sustain_days >= MIN_RALLY_SUSTAIN_DAYS)

        # --- features (backward-looking only, up to T0 inclusive) ---
        def at(series, offset):
            j = i + offset
            if j < 0 or j >= len(series):
                return None
            v = series.iloc[j]
            return None if pd.isna(v) else float(v)

        rsi_t0 = at(r, 0)
        rsi_t5 = at(r, -5)
        rsi_delta = None if rsi_t0 is None or rsi_t5 is None else rsi_t0 - rsi_t5

        divergence = None
        lb_start, lb_end = max(0, i - 20), max(0, i - 3)
        if lb_end > lb_start:
            seg_close = close.iloc[lb_start:lb_end]
            if len(seg_close) > 0:
                prior_low_pos = lb_start + int(seg_close.values.argmin())
                prior_low_close = close.iloc[prior_low_pos]
                prior_low_rsi = r.iloc[prior_low_pos]
                if pd.notna(prior_low_rsi) and rsi_t0 is not None and trough_val < prior_low_close:
                    divergence = bool(rsi_t0 > prior_low_rsi)

        vol_ratio_max = None
        if vol_reliable:
            vals = [at(vol_ratio, off) for off in (-2, -1, 0)]
            vals = [v for v in vals if v is not None]
            if vals:
                vol_ratio_max = max(vals)

        streak = 0
        j = i
        while j > 0 and close.iloc[j] < close.iloc[j - 1]:
            streak += 1
            j -= 1

        daily_ret = close.pct_change() * 100
        w_start = max(0, i - 5)
        seg = daily_ret.iloc[w_start:i + 1]
        worst_day = None if seg.empty or seg.isna().all() else float(seg.min())

        atr_t0 = at(atrp, 0)
        atr_avg60 = atrp.iloc[max(0, i - 60):i].mean()
        atr_ratio = None if atr_t0 is None or pd.isna(atr_avg60) or atr_avg60 <= 0 else atr_t0 / atr_avg60

        days_peak_to_trough = (trough_date - peak_date).days

        events.append({
            "ticker": ticker,
            "peak_date": str(peak_date.date()),
            "trough_date": str(trough_date.date()),
            "drop_pct": round(drop_pct, 2),
            "days_peak_to_trough": days_peak_to_trough,
            "rebound": rebound,
            "rally_pct_realized": round(rally_pct, 2),
            "rsi14_T0": None if rsi_t0 is None else round(rsi_t0, 2),
            "rsi14_delta_T-5_T0": None if rsi_delta is None else round(rsi_delta, 2),
            "bullish_divergence": divergence,
            "vol_ratio_max_T-2_T0": None if vol_ratio_max is None else round(vol_ratio_max, 3),
            "down_day_streak_into_trough": streak,
            "worst_single_day_pct_T-5_T0": None if worst_day is None else round(worst_day, 2),
            "atr_pct_ratio_vs_avg60": None if atr_ratio is None else round(atr_ratio, 3),
        })

        # non-overlap: skip past the outcome window before looking for the next event
        i += RALLY_WINDOW

    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save-cache", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()

    if args.no_fetch and CACHE_PATH.exists():
        print("Loading cached prices...", file=sys.stderr)
        raw = pd.read_parquet(CACHE_PATH)
        data = {t: raw[t] for t in TICKERS if t in raw.columns.get_level_values(0)}
    else:
        print(f"Downloading {len(TICKERS)} tickers, 5y daily...", file=sys.stderr)
        bulk = yf.download(TICKERS, period="5y", interval="1d", group_by="ticker",
                            auto_adjust=True, threads=True, progress=False)
        data = {}
        for t in TICKERS:
            try:
                data[t] = bulk[t] if len(TICKERS) > 1 else bulk
            except Exception:
                continue
        if args.save_cache:
            combined = pd.concat(data, axis=1)
            combined.to_parquet(CACHE_PATH)
            print(f"Cached to {CACHE_PATH}", file=sys.stderr)

    all_events = []
    skipped = []
    for t in TICKERS:
        df = data.get(t)
        if df is None or df.empty:
            skipped.append(t)
            continue
        evs = find_events(t, df)
        all_events.extend(evs)

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w") as f:
        for ev in all_events:
            f.write(json.dumps(ev) + "\n")

    n_rebound = sum(e["rebound"] for e in all_events)
    print(f"\n{len(all_events)} events from {len(TICKERS) - len(skipped)} tickers "
          f"({len(skipped)} skipped: {skipped})", file=sys.stderr)
    print(f"Rebound=1: {n_rebound} ({n_rebound / len(all_events) * 100:.1f}%)  "
          f"Rebound=0: {len(all_events) - n_rebound}", file=sys.stderr)
    print(f"Written to {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
