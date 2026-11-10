"""Backtest del combo MACD (hist_cross_confirmed + line_near_zero_up) sobre S&P 500 + Nasdaq 100.
Reglas y criterio fijados antes de ejecutar: ver README.md.

Uso: py -3 backtest.py   (requiere prices_cache.parquet, ver fetch_prices.py)
Salida: results.json + tablas por consola.
"""
import json
import numpy as np
import pandas as pd

LAST_DATE = "2026-11-09"          # la vela del 2026-11-10 es parcial
HIST_CROSS_LOOKBACK = 10          # screener-lib.js
NEAR_ZERO_MAX_ATR = 1.0           # screener-lib.js
COOLDOWN_DAYS = 10                # preregistro MACD_COMBO / informe del Screener
HORIZONS = [5, 10, 21]
COST_RT = 0.2                     # % ida y vuelta
SPLIT = pd.Timestamp("2021-01-01")


def ema_sma_seed(x, p):
    """emaFull de quote-lib.js: semilla = SMA de los primeros p valores."""
    out = np.full(len(x), np.nan)
    if len(x) < p:
        return out
    k = 2 / (p + 1)
    e = x[:p].mean()
    out[p - 1] = e
    for i in range(p, len(x)):
        e = x[i] * k + e * (1 - k)
        out[i] = e
    return out


def wilder_atr(c, h, l, p=14):
    out = np.full(len(c), np.nan)
    if len(c) < p + 1:
        return out
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    a = tr[:p].mean()
    out[p] = a
    for i in range(p, len(tr)):
        a = (a * (p - 1) + tr[i]) / p
        out[i + 1] = a
    return out


def indicators(d):
    c, h, l = d.close.values, d.high.values, d.low.values
    e12, e26 = ema_sma_seed(c, 12), ema_sma_seed(c, 26)
    macd = e12 - e26                      # válido desde el índice 25
    sig = np.full(len(c), np.nan)
    if len(c) > 34:
        sig[25:] = ema_sma_seed(macd[25:], 9)
    hist = macd - sig
    atr = wilder_atr(c, h, l)
    s = pd.Series(c)
    sma50 = s.rolling(50).mean().values
    sma200 = s.rolling(200).mean().values

    n = len(c)
    # racha verde del histograma terminando en t
    streak = np.zeros(n, dtype=int)
    for i in range(n):
        if not np.isnan(hist[i]) and hist[i] >= 0:
            streak[i] = (streak[i - 1] + 1) if i > 0 else 1
    prev_ok = np.zeros(n, dtype=bool)   # la barra anterior a la racha existe y era negativa
    for i in range(n):
        j = i - streak[i]
        prev_ok[i] = streak[i] > 0 and j >= 0 and not np.isnan(hist[j]) and hist[j] < 0
    hc = (streak >= 1) & (streak <= HIST_CROSS_LOOKBACK + 1) & prev_ok

    d5 = np.full(n, np.nan)
    d5[5:] = macd[5:] - macd[:-5]
    with np.errstate(invalid="ignore", divide="ignore"):
        dist = np.round(np.abs(macd) / atr, 2)
        lz = (macd < 0) & (c > sma200) & (sma50 > sma200) & (d5 > 0) & (dist <= NEAR_ZERO_MAX_ATR)
    valid = ~np.isnan(hist) & ~np.isnan(sma200) & ~np.isnan(atr)
    return pd.DataFrame({"hist": hist, "hc": hc & valid, "lz": lz & valid, "valid": valid}, index=d.index)


def cluster_t(x, groups):
    x = np.asarray(x, float)
    if len(x) < 3:
        return None
    m = x.mean()
    g = pd.Series(x - m).groupby(np.asarray(groups)).sum().values
    se = np.sqrt((g ** 2).sum()) / len(x)
    return float(m / se) if se > 0 else None


def summarize(x, groups):
    x = np.asarray(x, float)
    if len(x) == 0:
        return {"n": 0}
    return {"n": int(len(x)), "mean": round(float(x.mean()), 2), "median": round(float(np.median(x)), 2),
            "hit": round(float((x > 0).mean() * 100), 1),
            "t_week": None if cluster_t(x, groups) is None else round(cluster_t(x, groups), 2)}


def main():
    px = pd.read_parquet("prices_cache.parquet")
    px = px[px.date <= LAST_DATE]
    spy = px[px.ticker == "SPY"].set_index("date").sort_index()
    cal = spy.index
    stocks = px[px.ticker != "SPY"]

    C, HC, LZ, HIST, VALID = {}, {}, {}, {}, {}
    for t, d in stocks.groupby("ticker"):
        d = d.set_index("date").sort_index()
        d = d[~d.index.duplicated()]
        ind = indicators(d)
        C[t] = d.close
        HC[t], LZ[t], HIST[t], VALID[t] = ind["hc"], ind["lz"], ind["hist"], ind["valid"]
    C = pd.DataFrame(C).reindex(cal)
    HC = pd.DataFrame(HC).reindex(cal).astype("boolean").fillna(False).astype(bool)
    LZ = pd.DataFrame(LZ).reindex(cal).astype("boolean").fillna(False).astype(bool)
    HIST = pd.DataFrame(HIST).reindex(cal)
    VALID = pd.DataFrame(VALID).reindex(cal).astype("boolean").fillna(False).astype(bool)
    tickers = list(C.columns)
    Cv = C.values
    T = len(cal)
    print("valores", len(tickers), "sesiones", T)

    # régimen SPY en la fecha de la señal
    sc = spy.close
    s50, s200 = sc.rolling(50).mean(), sc.rolling(200).mean()
    regime = np.where(sc < s200, "bear", np.where((sc >= s50) & (s50 >= s200), "bull", "lateral"))
    regime = pd.Series(regime, index=cal).where(s200.notna(), None)

    # exceso a plazo fijo: matriz por barra de entrada
    EX = {}
    for H in HORIZONS:
        R = np.full_like(Cv, np.nan)
        R[:-H] = (Cv[H:] / Cv[:-H] - 1) * 100
        EX[H] = R - np.nanmean(R, axis=1, keepdims=True)

    def cd_events(mask):
        """(t, j) eventos: primer día candidato tras >= COOLDOWN_DAYS naturales sin serlo."""
        out = []
        M = mask.values
        for j in range(M.shape[1]):
            last = None
            for t in np.flatnonzero(M[:, j]):
                if last is None or (cal[t] - cal[last]).days >= COOLDOWN_DAYS:
                    out.append((t, j))
                last = t
        return out

    def fixed_horizon(events, label):
        res = {}
        for H in HORIZONS:
            rows = []
            for t, j in events:
                e = t + 1
                if e >= T:
                    continue
                v = EX[H][e, j]
                if np.isnan(v):
                    continue
                rows.append((cal[t], v))
            if not rows:
                res[H] = {"n": 0}
                continue
            dates = pd.DatetimeIndex([r[0] for r in rows])
            x = np.array([r[1] for r in rows])
            wk = dates.to_period("W").astype(str)
            reg = regime.reindex(dates).values
            res[H] = {
                "all": summarize(x, wk),
                "2016-2020": summarize(x[dates < SPLIT], wk[dates < SPLIT]),
                "2021-2026": summarize(x[dates >= SPLIT], wk[dates >= SPLIT]),
                **{f"reg_{r}": summarize(x[reg == r], wk[reg == r]) for r in ("bull", "lateral", "bear")},
            }
        return res

    def rule_trades(mask, cooldown):
        M = mask.values
        Hv = HIST.values
        trades = []
        for j in range(M.shape[1]):
            cand = np.flatnonzero(M[:, j])
            if cooldown:
                ev, last = [], None
                for t in cand:
                    if last is None or (cal[t] - cal[last]).days >= COOLDOWN_DAYS:
                        ev.append(t)
                    last = t
                cand = ev
            busy_until = -1          # barra de salida de la posición anterior
            for t in cand:
                e = t + 1
                if e >= T or e <= busy_until or np.isnan(Cv[e, j]):
                    continue
                k = e + 1
                while k < T and not (Hv[k, j] <= 0):
                    k += 1
                x = k + 1
                if x >= T or np.isnan(Cv[x, j]):
                    busy_until = T     # sigue abierta al final de los datos
                    continue
                ret = (Cv[x, j] / Cv[e, j] - 1) * 100
                uni = np.nanmean((Cv[x] / Cv[e] - 1) * 100)
                trades.append({"ticker": tickers[j], "signal": str(cal[t].date()), "entry": str(cal[e].date()),
                               "exit": str(cal[x].date()), "bars": int(x - e), "ret": round(ret, 2),
                               "uni": round(float(uni), 2), "excess": round(ret - uni, 2),
                               "regime": regime.iloc[t]})
                busy_until = x
        return trades

    def rule_summary(trades):
        if not trades:
            return {"n": 0}
        df = pd.DataFrame(trades)
        d = pd.to_datetime(df.entry)
        wk = d.dt.to_period("W").astype(str).values
        net = df.excess.values - COST_RT
        early = d < SPLIT
        return {"n": len(df), "bars_median": float(df.bars.median()),
                "ret": summarize(df.ret.values, wk), "excess": summarize(df.excess.values, wk),
                "excess_net": summarize(net, wk),
                "excess_net_2016-2020": summarize(net[early], wk[early]),
                "excess_net_2021-2026": summarize(net[~early], wk[~early]),
                **{f"excess_net_reg_{r}": summarize(net[df.regime.values == r], wk[df.regime.values == r])
                   for r in ("bull", "lateral", "bear")},
                "top5_share_of_excess_sum": round(float(np.sort(df.excess.values)[-5:].sum() / df.excess.sum()), 2)
                if df.excess.sum() > 0 else None}

    combo = HC & LZ
    out = {"params": {"last_date": LAST_DATE, "n_tickers": len(tickers), "cooldown_days": COOLDOWN_DAYS,
                      "cost_rt_pct": COST_RT}}
    out["fixed_horizon"] = {}
    for name, mask in (("combo", combo), ("hist_cross_confirmed", HC), ("line_near_zero_up", LZ)):
        out["fixed_horizon"][name] = fixed_horizon(cd_events(mask), name)
    # referencia: todas las barras válidas
    out["fixed_horizon"]["all_days"] = {}
    V = VALID.values
    for H in HORIZONS:
        X = np.roll(EX[H], -1, axis=0)   # entrada en t+1
        X[-1] = np.nan
        x = X[V & ~np.isnan(X)]
        out["fixed_horizon"]["all_days"][H] = {"n": int(len(x)), "mean": round(float(x.mean()), 2),
                                               "median": round(float(np.median(x)), 2),
                                               "hit": round(float((x > 0).mean() * 100), 1)}

    # señales por año
    ev = cd_events(combo)
    yrs = pd.Series([cal[t].year for t, _ in ev]).value_counts().sort_index()
    out["combo_events_per_year"] = {int(k): int(v) for k, v in yrs.items()}
    out["combo_distinct_tickers"] = len({j for _, j in ev})
    # por año, exceso a 10 sesiones
    rows = [(cal[t].year, EX[10][t + 1, j]) for t, j in ev if t + 1 < T and not np.isnan(EX[10][t + 1, j])]
    by_year = pd.DataFrame(rows, columns=["year", "x"]).groupby("year").x.agg(["count", "mean", "median"])
    out["combo_10s_by_year"] = {int(y): {"n": int(r["count"]), "mean": round(r["mean"], 2),
                                         "median": round(r["median"], 2)} for y, r in by_year.iterrows()}

    out["rule"] = {}
    for name, cd in (("CD", True), ("SD", False)):
        tr = rule_trades(combo, cd)
        out["rule"][name] = rule_summary(tr)
        pd.DataFrame(tr).to_csv(f"trades_{name}.csv", index=False)

    # criterio preregistrado
    f10 = out["fixed_horizon"]["combo"][10]
    rc = out["rule"]["CD"]
    a = f10["all"]["mean"] > 0 and (f10["all"]["t_week"] or 0) >= 2
    b = (np.sign(f10["2016-2020"].get("mean", 0)) == np.sign(f10["2021-2026"].get("mean", 0))
         and f10["2016-2020"].get("mean", 0) > 0)
    c = rc["excess_net"]["mean"] > 0 and (rc["excess_net"]["t_week"] or 0) >= 2
    out["criterion"] = {"a_combo_10s": bool(a), "b_both_halves": bool(b), "c_rule_cd_net": bool(c),
                        "supported": bool(a and b and c)}

    json.dump(out, open("results.json", "w"), indent=1, default=str)
    print(json.dumps({k: out[k] for k in ("combo_events_per_year", "combo_distinct_tickers", "criterion")}, indent=1))
    for name in ("combo", "hist_cross_confirmed", "line_near_zero_up"):
        for H in HORIZONS:
            r = out["fixed_horizon"][name][H]
            print(name, H, "all", r["all"], "| 16-20", r["2016-2020"], "| 21-26", r["2021-2026"])
    print("all_days", out["fixed_horizon"]["all_days"])
    for H in HORIZONS:
        r = out["fixed_horizon"]["combo"][H]
        print("combo regimes", H, r["reg_bull"], r["reg_lateral"], r["reg_bear"])
    print("by year", out["combo_10s_by_year"])
    for k, v in out["rule"].items():
        print("RULE", k, json.dumps(v))


if __name__ == "__main__":
    main()
