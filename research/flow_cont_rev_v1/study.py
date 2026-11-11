"""Contraste preregistrado (wiki/PREREGISTRO_FLOW_CONT_REV_V1.md, firmado y congelado 2026-11-11; hash en
PREREGISTRO.sha256). Se ejecuta UNA vez. Versión B (sesiones, ejecución operativa) decide; A (réplica literal de
producción) y A con una sesión de retraso se informan.

Entradas: _work/{U1,U2}_compact.pkl, _work/{U}_cands.parquet (A, calendario), _work/{U}_ses_cands.parquet (B, sesiones).
Salida: results.json
Uso: py -3 study.py            (contraste completo)
     py -3 study.py --selftest (solo compara el simulador A con screener_shadow_portfolio.simulate; sin métricas)
"""
import hashlib
import json
import math
import os
import pickle
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
W = os.path.join(HERE, "_work")
PREREG = os.path.join(ROOT, "wiki", "PREREGISTRO_FLOW_CONT_REV_V1.md")

COST = 0.002
HARD, TRAIL, ACT_MIN, ACT_ATR, TIME_DAYS = 1.5, 2.0, 5.0, 1.5, 14
COOLDOWN = 10
EMI = 0.5
Z95, Z975 = 1.959964, 2.241403
HORIZONS = (5, 10, 20)
SAMPLES = {"U1": {"dev": ("2017-07-01", "2020-12-31"), "test": ("2021-01-01", "2026-10-23")},
           "U2": {"test": ("2021-01-01", "2026-10-23")}}
FILTERS = {"cont": "flow_continuacion", "rev": "flow_reversion"}
SOURCES = {"U1": os.path.join(ROOT, "research", "macd_combo_filters_v1", "prices_cache.parquet"),
           "U2": os.path.join(HERE, "data", "u2_prices.parquet")}


def day(x):
    return np.asarray(x, dtype="datetime64[D]").astype(np.int64)


# ── Simuladores (devuelven (ret_neto, motivo, i_entrada, i_salida) o None) ──
def sim_a(T, s, lag=0):
    """Réplica literal de screener_shadow_portfolio.simulate(): entrada al cierre de la sesión siguiente (o la
    segunda si lag=1); ATR de la vela de entrada; condiciones y salida al mismo cierre."""
    p, atr, d = T["price"], T["atr"], T["d"]
    n = len(p)
    ei = s + 1 + lag
    if ei >= n:
        return None
    ep, ea = p[ei], atr[ei]
    if not (ea > 0):
        return None
    A = ep * ea / 100.0
    hard = ep - HARD * A
    act = ep * (1 + max(ACT_MIN, ACT_ATR * ea) / 100.0)
    M, activated = ep, False
    for i in range(ei + 1, n):
        c = p[i]
        if c > M:
            M = c
        if M >= act:
            activated = True
        if c <= hard:
            r = "hard"
        elif activated and c <= M - TRAIL * A:
            r = "trail"
        elif d[i] - d[ei] >= TIME_DAYS:
            r = "time"
        else:
            continue
        return c / ep - 1 - COST, r, ei, i
    return None


def sim_b(T, s):
    """Versión B: entrada a la apertura de la sesión siguiente (precios con dividendos), ATR de la vela de señal (el
    último conocido al decidir); condiciones sobre cierres desde el de la sesión de entrada; venta a la apertura de la
    sesión siguiente a la que dispara."""
    o, c_, atr, d = T["adj_open"], T["adj"], T["atr"], T["d"]
    n = len(c_)
    ei = s + 1
    if ei >= n:
        return None
    ep, ea = o[ei], atr[s]
    if not (ep > 0) or not (ea > 0):
        return None
    A = ep * ea / 100.0
    hard = ep - HARD * A
    act = ep * (1 + max(ACT_MIN, ACT_ATR * ea) / 100.0)
    M, activated = ep, False
    for i in range(ei, n):
        c = c_[i]
        if c > M:
            M = c
        if M >= act:
            activated = True
        if c <= hard:
            r = "hard"
        elif activated and c <= M - TRAIL * A:
            r = "trail"
        elif d[i] - d[ei] >= TIME_DAYS:
            r = "time"
        else:
            continue
        if i + 1 >= n or not (o[i + 1] > 0):
            return None
        return o[i + 1] / ep - 1 - COST, r, ei, i + 1
    return None


def fixed_a(T, s, h):
    p = T["price"]
    ei = s + 1
    if ei + h >= len(p) or not (p[ei] > 0):
        return None
    return p[ei + h] / p[ei] - 1 - COST


def fixed_b(T, s, h):
    o = T["adj_open"]
    ei = s + 1
    if ei + h >= len(o) or not (o[ei] > 0) or not (o[ei + h] > 0):
        return None
    return o[ei + h] / o[ei] - 1 - COST


VERSIONS = {"B": lambda T, s: sim_b(T, s), "A": lambda T, s: sim_a(T, s), "A_lag1": lambda T, s: sim_a(T, s, 1)}
FIXED = {"B": fixed_b, "A": fixed_a, "A_lag1": None}


# ── Estadística ──
def nw_se(x, lag):
    x = np.asarray(x, float)
    T = len(x)
    if T < 3:
        return float("nan")
    e = x - x.mean()
    v = e @ e / T
    for l in range(1, min(lag, T - 1) + 1):
        v += 2 * (1 - l / (lag + 1)) * (e[l:] @ e[:-l]) / T
    return math.sqrt(max(v, 0) / T)


def pval(t):
    return math.erfc(abs(t) / math.sqrt(2))


def summarize(ev, lag=10):
    """ev: DataFrame con columnas date (vela de señal), ex (exceso, pp). Media por fecha, luego media de fechas."""
    if ev.empty:
        return {"n_events": 0}
    by = ev.groupby("date").ex.mean().sort_index()
    m = float(by.mean())
    se = nw_se(by.values, lag)
    t = m / se if se and se > 0 else float("nan")
    return {"n_events": int(len(ev)), "n_dates": int(len(by)), "excess_mean_pp": round(m, 4),
            "se": round(se, 4), "t": round(t, 3), "p": round(pval(t), 5) if not math.isnan(t) else None,
            "ci95": [round(m - Z95 * se, 4), round(m + Z95 * se, 4)],
            "ci975_bonferroni": [round(m - Z975 * se, 4), round(m + Z975 * se, 4)]}


def main(selftest=False):
    if selftest:
        return run_selftest()
    h = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    frozen = open(os.path.join(HERE, "PREREGISTRO.sha256")).read().split()[0]
    assert h == frozen, f"el preregistro ha cambiado tras la firma: {h} != {frozen}"
    out = {"prereg_sha256": h, "universes": {}}
    for U in ("U1", "U2"):
        print("====", U, flush=True)
        out["universes"][U] = run_universe(U)
        json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    out["verdict"] = classify(out)
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    print(json.dumps(out["verdict"], indent=1, ensure_ascii=False))


def load_compact(U):
    comp = pickle.load(open(os.path.join(W, f"{U}_compact.pkl"), "rb"))
    for t, T in comp.items():
        T["d"] = day(T["bar"])
        T["idx"] = {int(x): i for i, x in enumerate(T["d"])}
    return comp


def spy_regime(U):
    s = pd.read_parquet(SOURCES[U], columns=["date", "close", "ticker"], filters=[("ticker", "==", "SPY")])
    s = s.assign(date=pd.to_datetime(s.date)).set_index("date").sort_index().close
    s = s[~s.index.duplicated()]
    sma = s.rolling(200).mean()
    return {int(day(k)): ("above" if v >= m else "below") for k, v, m in zip(s.index, s.values, sma.values)
            if not np.isnan(m)}


def events_from(cands, col):
    """Enfriamiento como load_events: evento si el candidato anterior del mismo valor está a ≥10 días de calendario;
    cada candidato reinicia el contador."""
    c = cands[cands[col]].sort_values(["ticker", "date"])
    out = []
    for t, g in c.groupby("ticker"):
        prev = None
        for dt, bar in zip(g.date.values, g.bar.values):
            dd = int(day(dt))
            if prev is None or dd - prev >= COOLDOWN:
                out.append((t, int(day(bar))))
            prev = dd
    return out


def run_universe(U):
    comp = load_compact(U)
    regime = spy_regime(U)
    lo = min(int(day(a)) for a, _ in SAMPLES[U].values())
    hi = max(int(day(b)) for _, b in SAMPLES[U].values())
    # referencia del universo: para cada versión y vela, media del retorno neto y fracción de aciertos
    print(U, "simulando universo", flush=True)
    uni = {v: defaultdict(lambda: [0.0, 0, 0]) for v in VERSIONS}
    unifix = {(v, h): defaultdict(lambda: [0.0, 0]) for v in ("A", "B") for h in HORIZONS}
    for k, (t, T) in enumerate(comp.items()):
        d = T["d"]
        for s in range(len(d)):
            ds = int(d[s])
            if ds < lo or ds > hi:
                continue
            for v, f in VERSIONS.items():
                r = f(T, s)
                if r is not None:
                    a = uni[v][ds]
                    a[0] += r[0]; a[1] += r[0] > 0; a[2] += 1
            for v in ("A", "B"):
                for hz in HORIZONS:
                    r = FIXED[v](T, s, hz)
                    if r is not None:
                        a = unifix[(v, hz)][ds]
                        a[0] += r; a[1] += 1
        if k % 100 == 0:
            print(U, "universo", k, flush=True)
    umean = {v: {ds: (a[0] / a[2], a[1] / a[2], a[2]) for ds, a in uni[v].items() if a[2]} for v in VERSIONS}
    ufix = {key: {ds: a[0] / a[1] for ds, a in dd.items() if a[1]} for key, dd in unifix.items()}

    cands = {"A": pd.read_parquet(os.path.join(W, f"{U}_cands.parquet")),
             "B": pd.read_parquet(os.path.join(W, f"{U}_ses_cands.parquet"))}
    res = {}
    for fk, fname in FILTERS.items():
        res[fname] = {}
        for v in VERSIONS:
            evs = events_from(cands["B" if v == "B" else "A"], fk)
            rows = []
            open_at_end = 0
            for t, ds in evs:
                if ds < lo or ds > hi or t not in comp:
                    continue
                T = comp[t]
                s = T["idx"].get(ds)
                if s is None:
                    continue
                r = VERSIONS[v](T, s)
                if r is None:
                    open_at_end += 1
                    continue
                if ds not in umean[v]:
                    continue
                um, uw, un = umean[v][ds]
                row = {"ticker": t, "date": ds, "ret": r[0] * 100, "ex": (r[0] - um) * 100, "win": r[0] > 0,
                       "uwin": uw, "reason": r[1], "ei": int(T["d"][r[2]]), "xi": int(T["d"][r[3]]),
                       "regime": regime.get(ds)}
                if v in ("A", "B"):
                    for hz in HORIZONS:
                        fr = FIXED[v](T, s, hz)
                        uf = ufix[(v, hz)].get(ds)
                        row[f"fx{hz}"] = None if fr is None or uf is None else (fr - uf) * 100
                rows.append(row)
            ev = pd.DataFrame(rows)
            res[fname][v] = {}
            for sname, (a, b) in SAMPLES[U].items():
                e = ev[(ev.date >= int(day(a))) & (ev.date <= int(day(b)))] if len(ev) else ev
                res[fname][v][sname] = describe(e, v)
            res[fname][v]["excluded_open_or_no_data"] = open_at_end
            print(U, fname, v, {s: res[fname][v][s].get("primary", {}).get("excess_mean_pp") for s in SAMPLES[U]},
                  flush=True)
    return res


def describe(e, v):
    if e.empty:
        return {"primary": {"n_events": 0}}
    d = {"primary": summarize(e), "nw_lag20": summarize(e, lag=20)}
    by = e.groupby("date")
    d["win_rate_filter"] = round(float(by.win.mean().mean()), 4)
    d["win_rate_universe"] = round(float(by.uwin.first().mean()), 4)
    d["net_ret_mean_pp"] = round(float(e.ret.mean()), 4)
    d["net_ret_median_pp"] = round(float(e.ret.median()), 4)
    d["net_ret_pct"] = {q: round(float(e.ret.quantile(q / 100)), 3) for q in (5, 25, 75, 95)}
    d["share_loss_gt10"] = round(float((e.ret < -10).mean()), 4)
    d["exit_reasons"] = e.reason.value_counts(normalize=True).round(4).to_dict()
    k = max(1, math.ceil(0.01 * len(e)))
    d["without_top1pct"] = summarize(e.drop(e.ret.nlargest(k).index))
    d["by_year"] = {int(y): summarize(g) for y, g in e.groupby(pd.to_datetime(e.date, unit="D").dt.year)}
    d["by_regime"] = {r: summarize(g) for r, g in e.groupby("regime")}
    if v in ("A", "B"):
        d["fixed_no_stops"] = {hz: summarize(e[["date"]].assign(ex=e[f"fx{hz}"]).dropna()) for hz in HORIZONS}
    # operaciones simultáneas: media, sobre los días con alguna abierta, del número de operaciones abiertas
    cnt = defaultdict(int)
    for a, b in zip(e.ei, e.xi):
        for x in range(a, b + 1):
            cnt[x] += 1
    d["concurrent_mean"] = round(float(np.mean(list(cnt.values()))), 2) if cnt else None
    # sin solapes: se descarta un evento si el mismo valor tiene una operación abierta de este filtro y versión
    keep, last_exit = [], {}
    for i, r in e.sort_values("ei").iterrows():
        if r.ticker in last_exit and r.ei <= last_exit[r.ticker]:
            continue
        keep.append(i)
        last_exit[r.ticker] = r.xi
    d["no_overlap"] = summarize(e.loc[keep])
    return d


def classify(out):
    v = {}
    for fname in FILTERS.values():
        b = out["universes"]["U1"][fname]["B"]
        t, dv = b["test"], b["dev"]
        p = t["primary"]
        lo, hi = p["ci975_bonferroni"]
        m = p["excess_mean_pp"]
        checks = {
            "1_magnitud_B_test_ge_0.5": m >= EMI,
            "2_significacion_B_test_ci975_low_gt_0": lo > 0,
            "3_estabilidad_B_dev_gt_0": dv["primary"]["excess_mean_pp"] > 0,
            "4_acierto_B_test_filtro_gt_universo": t["win_rate_filter"] > t["win_rate_universe"],
            "5_extremos_B_test_sin_top1pct_gt_0": t["without_top1pct"]["excess_mean_pp"] > 0,
            "6_contraste_U2_B_gt_0": out["universes"]["U2"][fname]["B"]["test"]["primary"]["excess_mean_pp"] > 0,
        }
        labels = []
        if all(checks.values()):
            labels.append("VALIDADO" + (" CON GRAN CERTEZA" if lo >= EMI else ""))
        if lo > 0 and m < EMI:
            labels.append("SIGNIFICATIVO PERO SIN INTERÉS ECONÓMICO")
        if hi < EMI:
            labels.append("NO SOPORTADO")
        if not labels:
            labels.append("INCONCLUYENTE")
        v[fname] = {"verdict": " / ".join(labels), "checks": checks, "B_test_excess_pp": m,
                    "B_test_ci975": [lo, hi], "A_test_excess_pp": out["universes"]["U1"][fname]["A"]["test"]["primary"]["excess_mean_pp"]}
    return v


def run_selftest():
    """Compara sim_a con screener_shadow_portfolio.simulate() en series reales de U2 (solo mecánica de salida)."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import screener_shadow_portfolio as ssp
    comp = load_compact("U2")
    rng = np.random.default_rng(1)
    tickers = sorted(comp)
    n = mism = 0
    for _ in range(3000):
        t = tickers[rng.integers(len(tickers))]
        T = comp[t]
        if len(T["d"]) < 50:
            continue
        s = int(rng.integers(30, len(T["d"]) - 2))
        series = [(str(np.datetime64(int(x), "D")), float(p), None if np.isnan(a) else float(a))
                  for x, p, a in zip(T["d"], T["price"], T["atr"])]
        sig = series[s][0]
        prod = ssp.simulate({"ticker": t, "date": "cap"}, {t: series}, {(t, "cap"): sig})
        mine = sim_a(T, s)
        n += 1
        if prod is None or prod.get("skipped") or prod.get("status") != "closed":
            ok = mine is None
        else:
            ok = mine is not None and abs((prod["exit_price"] / prod["entry_price"] - 1 - COST) - mine[0]) < 1e-12 \
                and prod["exit_bar"] == series[mine[3]][0]
        mism += not ok
    print("selftest sim_a vs simulate():", n, "casos, discrepancias", mism)


if __name__ == "__main__":
    main("--selftest" in sys.argv)
