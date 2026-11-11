"""Estudio principal del preregistro wiki/PREREGISTRO_EARLY_FLOW_7_V1.md (§3-§6).
Early Flow >= 7 (versión corregida, reconstruida en research/macd_combo_filters_v1) frente a benchmarks
emparejados por fecha y número de señales. Solo lectura de datos ya descargados. Salida: results.json"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FB = os.path.join(HERE, "..", "macd_combo_filters_v1")
COST = 0.002
HORIZONS = (5, 10, 20, 40)
PRIMARY = 20
COOLDOWN = 10
DEV = ("2016-01-01", "2020-12-31")
TEST = ("2021-01-01", "2026-11-09")
BENCH = ["M5", "M20", "RSM63", "RSS63", "RSS20", "RSV"]
METHODS = ["EF7"] + BENCH + ["RND"]
BONF_T = 2.64


def nw_t(x, lag):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 3:
        return np.nan, n
    m = x.mean()
    e = x - m
    v = e @ e / n
    for j in range(1, min(lag, n - 1) + 1):
        v += 2 * (1 - j / (lag + 1)) * (e[j:] @ e[:-j]) / n
    se = np.sqrt(v / n)
    return (m / se if se > 0 else np.nan), n


def main():
    px = pd.read_parquet(os.path.join(FB, "prices_cache.parquet"))
    px = px.drop_duplicates(["ticker", "date"])
    sectors = json.load(open(os.path.join(FB, "sectors.json")))
    uni = sorted(sectors["sector"])
    f = px.adj_close / px.close
    px = px.assign(ao=px.open * f, ah=px.high * f, al=px.low * f, ac=px.adj_close)
    W = {k: px.pivot(index="date", columns="ticker", values=k).sort_index() for k in ("ao", "ah", "al", "ac", "volume")}
    cal = W["ac"]["SPY"].dropna().index
    W = {k: v.reindex(cal) for k, v in W.items()}
    dates = np.array([str(d.date()) for d in cal])
    T = len(cal)
    ef = pd.read_csv(os.path.join(FB, "_work", "earlyflow_out.csv"))
    ef["date"] = pd.to_datetime(ef.date)
    ef_tick = set(ef.ticker.unique())   # valores con < 250 sesiones no tienen Early Flow (excluidos, como en el estudio previo)
    tick = [t for t in uni if t in W["ac"].columns and t in ef_tick]
    AO, AH, AL, AC = (W[k][tick].to_numpy(float) for k in ("ao", "ah", "al", "ac"))
    VOL = W["volume"][tick].to_numpy(float)
    N = len(tick)
    col = {t: i for i, t in enumerate(tick)}

    EF = ef.pivot(index="date", columns="ticker", values="ef").reindex(cal)[tick].to_numpy(float)

    # elegibilidad: >= 250 sesiones con cierre hasta t
    hist = np.cumsum(~np.isnan(AC), axis=0)
    elig = (hist >= 250) & ~np.isnan(AC)
    nxt_open = np.vstack([AO[1:], np.full((1, N), np.nan)])
    can_enter = elig & ~np.isnan(nxt_open)

    def ret(arr, k):
        out = np.full_like(arr, np.nan)
        out[k:] = arr[k:] / arr[:-k] - 1
        return out
    spy = W["ac"]["SPY"].to_numpy(float)
    spy63 = np.full(T, np.nan); spy63[63:] = spy[63:] / spy[:-63] - 1
    spy_sma200 = pd.Series(spy).rolling(200).mean().to_numpy()
    bull = spy > spy_sma200
    r5, r20, r63 = ret(AC, 5), ret(AC, 20), ret(AC, 63)
    sec_etf = [sectors["etf"][sectors["sector"][t]] for t in tick]
    ETF = W["ac"][sorted(set(sec_etf))]
    E20 = {e: (ETF[e] / ETF[e].shift(20) - 1).to_numpy() for e in ETF}
    E63 = {e: (ETF[e] / ETF[e].shift(63) - 1).to_numpy() for e in ETF}
    S20 = np.column_stack([E20[e] for e in sec_etf])
    S63 = np.column_stack([E63[e] for e in sec_etf])
    v20 = pd.DataFrame(VOL).rolling(20, min_periods=15).mean().to_numpy()
    v60 = pd.DataFrame(VOL).rolling(60, min_periods=45).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rvol = v20 / v60
    rsm63 = r63 - spy63[:, None]

    def pct_rank(m):
        return pd.DataFrame(m).rank(axis=1, pct=True).to_numpy()
    rsm_masked = np.where(can_enter, rsm63, np.nan)
    rvol_masked = np.where(can_enter, rvol, np.nan)
    scores = {"M5": r5, "M20": r20, "RSM63": rsm63, "RSS63": r63 - S63, "RSS20": r20 - S20,
              "RSV": (pct_rank(rsm_masked) + pct_rank(rvol_masked)) / 2}

    # ── eventos EF7 ──
    sel = {m: np.zeros((T, N), bool) for m in METHODS}
    ev_ok = (EF >= 7) & (np.vstack([np.full((1, N), np.nan), EF[:-1]]) < 7) & can_enter
    for j in range(N):
        last = -10 ** 9
        for t in np.flatnonzero(ev_ok[:, j]):
            if t - last > COOLDOWN:
                sel["EF7"][t, j] = True
                last = t
    sel["EF7"][dates < DEV[0], :] = False
    k_t = sel["EF7"].sum(axis=1)

    # ── emparejamiento ──
    rng = np.random.default_rng(7)
    for m in BENCH + ["RND"]:
        recent = np.full(N, -10 ** 9)
        for t in np.flatnonzero(k_t):
            ok = can_enter[t] & (t - recent > COOLDOWN)
            if m == "RND":
                cand = np.flatnonzero(ok)
                pick = rng.choice(cand, size=min(k_t[t], len(cand)), replace=False) if len(cand) else []
            else:
                s = np.where(ok, scores[m][t], np.nan)
                cand = np.flatnonzero(~np.isnan(s))
                pick = cand[np.argsort(-s[cand])[:k_t[t]]]
            sel[m][t, pick] = True
            recent[pick] = t

    # ── retornos ──
    out = {"meta": {"n_tickers": N, "calendar": [dates[0], dates[-1]], "cost": COST, "cooldown": COOLDOWN}}
    per_event = []
    for h in HORIZONS:
        fut = np.full((T, N), np.nan)
        fut[:-h] = AC[h:] / nxt_open[:-h] - 1
        fut[:-h][np.isnan(AC[h:])] = np.nan
        umean = np.nanmean(np.where(elig, fut, np.nan), axis=1)
        # sector ETF misma ventana (apertura no disponible para comparar igual: se usa cierre t -> cierre t+h)
        etf_fut = {e: np.concatenate([(ETF[e].shift(-h) / ETF[e] - 1).to_numpy()]) for e in ETF}
        SF = np.column_stack([etf_fut[e] for e in sec_etf])
        lowmin = np.full((T, N), np.nan); highmax = np.full((T, N), np.nan)
        LL = pd.DataFrame(AL).rolling(h, min_periods=1).min().to_numpy()
        HH = pd.DataFrame(AH).rolling(h, min_periods=1).max().to_numpy()
        lowmin[:-h] = LL[h:]; highmax[:-h] = HH[h:]
        with np.errstate(invalid="ignore", divide="ignore"):
            mae = lowmin / nxt_open - 1
            mfe = highmax / nxt_open - 1
        net = fut - COST
        exc = net - umean[:, None]
        exc_sec = net - SF
        valid_t = np.arange(T) < T - h
        for per_name, (lo, hi) in (("dev", DEV), ("test", TEST)):
            pmask = (dates >= lo) & (dates <= hi) & valid_t
            daily = {}
            for m in METHODS:
                msk = sel[m] & pmask[:, None] & ~np.isnan(exc)
                e = exc[msk]; r = net[msk]
                dmean = np.array([np.nanmean(np.where(msk[t], exc[t], np.nan)) if msk[t].any() else np.nan for t in range(T)])
                daily[m] = dmean
                tt, nd = nw_t(dmean, h)
                rec = out.setdefault(per_name, {}).setdefault(str(h), {}).setdefault(m, {})
                rec.update({
                    "n": int(msk.sum()), "n_dates": nd,
                    "mean_excess": float(np.nanmean(e) * 100) if len(e) else None,
                    "median_excess": float(np.nanmedian(e) * 100) if len(e) else None,
                    "t_nw_excess": float(tt) if not np.isnan(tt) else None,
                    "hit_rate": float(np.mean(e > 0)) if len(e) else None,
                    "mean_net_return": float(np.nanmean(r) * 100) if len(r) else None,
                    "pct_ret": {p: float(np.nanpercentile(r, p) * 100) for p in (5, 25, 50, 75, 95)} if len(r) else None,
                    "pct_loss_gt10": float(np.mean(r < -0.10)) if len(r) else None,
                    "median_mae": float(np.nanmedian(mae[msk]) * 100) if len(r) else None,
                    "median_mfe": float(np.nanmedian(mfe[msk]) * 100) if len(r) else None,
                    "mean_excess_vs_sector": float(np.nanmean(exc_sec[msk]) * 100) if len(r) else None,
                })
            for m in BENCH + ["RND"]:
                d = daily["EF7"] - daily[m]
                tt, nd = nw_t(d, h)
                out[per_name][str(h)]["EF7"].setdefault("paired_vs", {})[m] = {
                    "mean_diff": float(np.nanmean(d) * 100), "t_nw": float(tt) if not np.isnan(tt) else None, "n_dates": nd}
        if h == PRIMARY:
            # por año y régimen (todas las fechas válidas desde 2016)
            years = np.array([d[:4] for d in dates])
            for m in METHODS:
                byy = {}
                for y in sorted(set(years[dates >= DEV[0]])):
                    msk = sel[m] & ((years == y) & valid_t)[:, None] & ~np.isnan(exc)
                    if msk.sum():
                        byy[y] = {"n": int(msk.sum()), "mean_excess": float(np.mean(exc[msk]) * 100),
                                  "hit": float(np.mean(exc[msk] > 0))}
                byr = {}
                for rname, rmask in (("SPY>SMA200", bull), ("SPY<SMA200", ~bull & ~np.isnan(spy_sma200))):
                    for per_name, (lo, hi) in (("dev", DEV), ("test", TEST)):
                        pm = (dates >= lo) & (dates <= hi) & valid_t & rmask
                        msk = sel[m] & pm[:, None] & ~np.isnan(exc)
                        if msk.sum():
                            byr[f"{per_name} {rname}"] = {"n": int(msk.sum()), "mean_excess": float(np.mean(exc[msk]) * 100),
                                                          "hit": float(np.mean(exc[msk] > 0))}
                out.setdefault("by_year_20", {})[m] = byy
                out.setdefault("by_regime_20", {})[m] = byr
            for t, j in zip(*np.nonzero(sel["EF7"] & valid_t[:, None])):
                per_event.append((dates[t], tick[j], float(exc[t, j]) if not np.isnan(exc[t, j]) else None))

    # ── sector mix ──
    secname = np.array([sectors["sector"][t] for t in tick])
    out["sector_mix"] = {}
    for m in METHODS:
        c = pd.Series(secname[np.nonzero(sel[m])[1]]).value_counts(normalize=True).round(3).to_dict()
        out["sector_mix"][m] = c

    # ── anticipación (§5) ──
    pr = pct_rank(np.where(elig & ~np.isnan(rsm63), rsm63, np.nan))
    top = pr >= 0.80
    low = pr < 0.60
    onsets = []
    for j in range(N):
        col_top, col_low = top[:, j], low[:, j]
        for t in np.flatnonzero(col_top):
            if t < 20 or t + 20 > T or dates[t] < DEV[0]:
                continue
            if col_low[t - 20:t].all():
                sustained = col_top[t:t + 20].sum() >= 16
                onsets.append((t, j, sustained))
    out["anticipation_onsets"] = {"n": len(onsets), "sustained": int(sum(s for *_, s in onsets))}
    sust_by = {}
    for t, j, s in onsets:
        if s:
            sust_by.setdefault(j, []).append(t)
    for per_name, (lo, hi) in (("dev", DEV), ("test", TEST)):
        res = {}
        for m in METHODS:
            evs = np.nonzero(sel[m])
            ev_by = {}
            for t, j in zip(*evs):
                ev_by.setdefault(j, []).append(t)
            cov, leads = 0, []
            n_on = 0
            for t, j, s in onsets:
                if not s or not (lo <= dates[t] <= hi):
                    continue
                n_on += 1
                prior = [x for x in ev_by.get(j, []) if t - 40 <= x <= t - 1]
                if prior:
                    cov += 1
                    leads.append(t - min(prior))
            prec, risen20, risen60, remaining, ret40 = [], [], [], [], []
            for t, j in zip(*evs):
                if not (lo <= dates[t] <= hi) or t + 41 > T:
                    continue
                prec.append(any(t + 1 <= x <= t + 40 for x in sust_by.get(j, [])))
                if t >= 60:
                    risen20.append(AC[t, j] / AC[t - 20, j] - 1)
                    risen60.append(AC[t, j] / np.nanmin(AC[t - 60:t + 1, j]) - 1)
                o = nxt_open[t, j]
                remaining.append(np.nanmax(AC[t + 1:t + 41, j]) / o - 1)
                ret40.append(AC[t + 40, j] / o - 1)
            res[m] = {"n_sustained_onsets": n_on, "coverage": cov / n_on if n_on else None,
                      "median_lead_sessions": float(np.median(leads)) if leads else None,
                      "precision": float(np.mean(prec)) if prec else None, "n_events": len(prec),
                      "median_risen_20d": float(np.nanmedian(risen20) * 100) if risen20 else None,
                      "median_above_60d_low": float(np.nanmedian(risen60) * 100) if risen60 else None,
                      "median_remaining_max40": float(np.nanmedian(remaining) * 100) if remaining else None,
                      "median_ret40": float(np.nanmedian(ret40) * 100) if ret40 else None}
        out.setdefault("anticipation", {})[per_name] = res

    # ── clasificación según §6 ──
    tp = out["test"][str(PRIMARY)]["EF7"]; dp = out["dev"][str(PRIMARY)]["EF7"]
    c1 = tp["mean_excess"] > 0 and (tp["t_nw_excess"] or 0) >= 2
    c2 = all(tp["paired_vs"][b]["mean_diff"] > 0 and (tp["paired_vs"][b]["t_nw"] or 0) >= BONF_T for b in BENCH)
    c3 = (np.sign(dp["mean_excess"]) == np.sign(tp["mean_excess"]) and
          all(np.sign(dp["paired_vs"][b]["mean_diff"]) == np.sign(tp["paired_vs"][b]["mean_diff"]) for b in BENCH))
    c4 = tp["hit_rate"] > 0.5 and tp["median_mae"] >= out["test"][str(PRIMARY)]["M20"]["median_mae"] - 1
    other_h = [h for h in HORIZONS if h != PRIMARY and out["test"][str(h)]["EF7"]["mean_excess"] > 0
               and (out["test"][str(h)]["EF7"]["t_nw_excess"] or 0) >= 2]
    n_test = tp["n"]
    if n_test < 100:
        verdict = "INCONCLUSO"
    elif c1 and c2 and c3 and c4:
        verdict = "CAPACIDAD DEMOSTRADA"
    elif (c1 and np.sign(dp["mean_excess"]) == np.sign(tp["mean_excess"])) or other_h:
        verdict = "INDICIO EXPLORATORIO"
    else:
        verdict = "NO SOPORTADO"
    out["verdict"] = {"verdict": verdict, "c1_excess_test": bool(c1), "c2_beats_all_benchmarks": bool(c2),
                      "c3_same_sign_dev": bool(c3), "c4_hit_and_mae": bool(c4), "other_horizons_c1": other_h}
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=1)
    pd.DataFrame(per_event, columns=["date", "ticker", "excess_20"]).to_csv(os.path.join(HERE, "_events_ef7.csv"), index=False)
    print(json.dumps(out["verdict"], indent=1))


if __name__ == "__main__":
    main()
