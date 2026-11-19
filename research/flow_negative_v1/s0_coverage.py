"""Etapa 0 — panel de días-miembro y puertas de calidad. NO usa ningún rendimiento posterior a una señal.

Para cada intervalo de composición (índice, ticker, inicio, fin) y cada sesión del calendario oficial (Alpaca):
serie de la empresa (por ticker; si falta, por la cadena de cambios de nombre de Alpaca), Flow y su resto R,
precio en bruto, liquidez (mediana de 20 sesiones de precio x volumen), exclusión por evento (enmienda 7 de
microestructura: evento en [t-259, t+40] sesiones), desenlace dentro de las 40 sesiones siguientes y capitalización
(SEC, si hay dato presentado <= t con <= 400 días de antigüedad).

Salidas: work/panel.parquet (fuera del repo) y data/stage0_coverage.json (agregados)
"""
import json
from collections import defaultdict

import numpy as np
import pandas as pd

import fn_config as C
from s0_series import load_ca

SER = C.WORK / "series"
ZONES = [(-1e9, -30, "<-30"), (-30, -20, "[-30,-20)"), (-20, -15, "[-20,-15)"), (-15, -10, "[-15,-10)"),
         (-10, -5, "[-10,-5)"), (-5, 0, "[-5,0)"), (0, 4, "[0,4)"), (4, 1e9, ">=4")]
LOOKBACK, HORIZON = 259, 40


def zone(f):
    for lo, hi, n in ZONES:
        if lo <= f < hi:
            return n
    return None


def calendar():
    p = C.WORK / "calendar.json"
    if not p.exists():
        cal = C.alpaca().calendar("2015-01-01", C.PRICE_END)
        json.dump([c["date"] for c in cal], open(p, "w"))
    return json.load(open(p))


def shares_table(cik, splits=()):
    """Acciones por presentación, limpias: se descartan ceros y presentaciones que, llevadas a la base actual con
    los splits aplicados, se alejan más de x2 de la mediana de las 5 presentaciones centradas (errores de escala de
    la SEC: miles por unidades, etc.). Devuelve también cuántas se descartaron."""
    f = C.SEC / "shares" / f"{cik}.json"
    if not f.exists():
        return None, 0
    s = pd.DataFrame(json.load(open(f)))
    if s.empty or "filed" not in s:
        return None, 0
    s = s[s.form.astype(str).str.match(r"^(10-K|10-Q|10-KT|10-QT|20-F|40-F)")] if "form" in s else s
    g = s.groupby(["end", "filed"]).agg(val=("val", "sum"), n=("val", "size")).reset_index()
    g = g.sort_values("filed").reset_index(drop=True)
    g = g[g.val > 0]
    if g.empty:
        return None, 0
    base = g.val.to_numpy(float).copy()
    for bd, fac in splits:
        base *= np.where(g.end.to_numpy() < bd, fac, 1.0)
    med = pd.Series(base).rolling(5, center=True, min_periods=1).median().to_numpy()
    ok = np.abs(np.log(base / med)) <= np.log(2)
    return g[ok].reset_index(drop=True), int((~ok).sum())


def main():
    cal = calendar()
    cpos = {d: i for i, d in enumerate(cal)}
    mem = pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False)
    plan = pd.read_csv(C.WORK / "requests.csv", dtype=str, keep_default_na=False)
    summ = pd.read_csv(C.WORK / "series_summary.csv", dtype=str, keep_default_na=False).set_index("key")
    term = pd.read_csv(C.PUB / "terminal_events.csv", dtype=str, keep_default_na=False).set_index("key")
    cikm = pd.read_csv(C.SEC / "cik_map.csv", dtype=str, keep_default_na=False).set_index("key") \
        if (C.SEC / "cik_map.csv").exists() else pd.DataFrame()
    nc = load_ca()["name_changes"]
    fwd = defaultdict(set)
    for r in nc.itertuples():
        if r.old and r.new:
            fwd[r.old].add(r.new)
    by_ticker = defaultdict(list)
    for r in plan.to_dict("records"):
        by_ticker[r["ticker"]].append(r)

    cache = {}

    def series(key):
        if key not in cache:
            p = SER / f"{key}.parquet"
            if not p.exists():
                cache[key] = None
            else:
                d = pd.read_parquet(p)
                d["adv20"] = d.dollar_vol.rolling(20, min_periods=20).median()
                cache[key] = d.set_index("date")
            if len(cache) > 400:
                cache.pop(next(iter(cache)))
        return cache[key]

    epochs_of = summ.reset_index().groupby("req_key")["key"].apply(list).to_dict()
    cik_req = cikm["cik"].to_dict() if len(cikm) else {}
    req_by_cik = defaultdict(list)
    for k, c in cik_req.items():
        if c:
            req_by_cik[c].append(k)

    def candidates(t, end):
        out = []
        reqs = []
        for r in sorted(by_ticker.get(t, []), key=lambda r: (r["asof"] == "", r["asof"])):
            if r["asof"] == "" or not end or r["asof"] >= end:
                reqs.append(r["key"])
        for rk in reqs:
            out += [(k, "direct") for k in epochs_of.get(rk, [])]
        # misma empresa (CIK) con otro ticker: cambios de ticker anteriores a 2020, que Alpaca no registra
        for rk in reqs:
            for rk2 in req_by_cik.get(cik_req.get(rk, ""), []):
                if rk2 not in reqs:
                    out += [(k, "cik") for k in epochs_of.get(rk2, [])]
        seen, frontier = {t}, [t]
        while frontier:
            x = frontier.pop()
            for y in fwd.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    frontier.append(y)
                    out += [(k, "rename") for r in by_ticker.get(y, []) if r["asof"] == ""
                            for k in epochs_of.get(r["key"], [])]
        return out

    rows = []
    for m in mem.to_dict("records"):
        idx = m["index"]
        a = max(m["start"], C.SIGNAL_START[idx])
        b = m["end"] or C.PRICE_END
        days = [d for d in cal if a <= d <= b]
        if not days:
            continue
        cands = candidates(m["ticker"], m["end"])
        for d in days:
            got = None
            for k, via in cands:
                s = series(k)
                if s is not None and d in s.index:
                    got = (k, via, s)
                    break
            if got is None:
                rows.append({"index": idx, "date": d, "ticker": m["ticker"], "key": "", "via": "missing",
                             "sector": m["sector_wiki"]})
                continue
            k, via, s = got
            x = s.loc[d]
            rows.append({"index": idx, "date": d, "ticker": m["ticker"], "key": k, "via": via, "sector": m["sector_wiki"],
                         "flow": x.flow, "R": x.R, "mom": x.mom, "w1": x.w1, "m1": x.m1,
                         "flow_complete": bool(x.flow_complete), "raw_close": x.raw_close, "adv20": x.adv20,
                         "konc_d": x.konc_d, "konc_w": x.konc_w})
    p = pd.DataFrame(rows)
    print("filas panel", len(p), flush=True)

    # exclusión por eventos y desenlace dentro de 40 sesiones
    ev_pos, term_pos, term_cat = {}, {}, {}
    for k, r in summ.iterrows():
        evs = json.loads(r["events"]) if r.get("events") else []
        ev_pos[k] = np.array(sorted(cpos[e[0]] for e in evs if e[0] in cpos))
        if r.get("terminated") == "True" and r["end"] in cpos:
            term_pos[k] = cpos[r["end"]]
            term_cat[k] = term.loc[k, "category"] if k in term.index else "sin_clasificar"
    pos = p.date.map(cpos).to_numpy()
    excl = np.zeros(len(p), bool)
    # pertenencia confirmada: el ticker figura en la instantánea anual (ancla) anterior o en la siguiente
    import s0_universe as U
    p["snapshot_confirmed"] = False
    for idx in p["index"].unique():
        revs = U.revisions(idx)
        anchors = []
        for y in sorted(revs, key=revs.get):
            s = U.snapshot(idx, y)
            lo_, hi_ = U.SIZE[idx]
            if s is not None and lo_ <= len(s) <= hi_:
                anchors.append((revs[y].date().isoformat(), set(s.ticker)))
        ad = [a for a, _ in anchors]
        ii = np.where(p["index"].to_numpy() == idx)[0]
        dts, tks = p.date.to_numpy()[ii], p.ticker.to_numpy()[ii]
        j = np.searchsorted(ad, dts, side="right") - 1
        conf = np.zeros(len(ii), bool)
        for n in range(len(ii)):
            prv = anchors[j[n]][1] if j[n] >= 0 else set()
            nxt = anchors[j[n] + 1][1] if j[n] + 1 < len(anchors) else set()
            conf[n] = tks[n] in prv or tks[n] in nxt
        p.loc[p.index[ii], "snapshot_confirmed"] = conf
    tpos = np.full(len(p), -1)
    tcat = np.array([""] * len(p), dtype=object)
    for k, ix in p.groupby("key").indices.items():
        if not k:
            continue
        e = ev_pos.get(k, np.array([]))
        if len(e):
            lo = np.searchsorted(e, pos[ix] - LOOKBACK, side="left")
            hi = np.searchsorted(e, pos[ix] + HORIZON, side="right")
            excl[ix] = hi > lo
        if k in term_pos:
            tp = term_pos[k]
            w = (tp > pos[ix]) & (tp <= pos[ix] + HORIZON)
            tpos[ix] = np.where(w, tp, -1)
            tcat[ix] = np.where(w, term_cat[k], "")
    p["event_excluded"] = excl
    p["terminal_within_40"] = tcat

    # capitalización (SEC)
    p["mcap"] = np.nan
    p["multiclass"] = False
    sec_dropped = 0
    for k, ix in p.groupby("key").indices.items():
        rk = summ.loc[k, "req_key"] if k in summ.index else ""
        if not k or rk not in cikm.index or not cikm.loc[rk, "cik"]:
            continue
        splits = json.loads(summ.loc[k, "splits_list"]) if summ.loc[k, "splits_list"] else []
        sh, dropped = shares_table(cikm.loc[rk, "cik"], splits)
        sec_dropped += dropped
        if sh is None or sh.empty:
            continue
        dts = p.date.to_numpy()[ix]
        j = np.searchsorted(sh.filed.to_numpy(), dts, side="right") - 1
        ok = j >= 0
        jj = np.where(ok, j, 0)
        filed = sh.filed.to_numpy()[jj]
        endd = sh.end.to_numpy()[jj]
        age = (pd.to_datetime(dts) - pd.to_datetime(filed)).days.to_numpy()
        val = sh.val.to_numpy(float)[jj]
        f = np.ones(len(ix))
        for bd, fac in splits:
            f *= np.where((endd < bd) & (dts >= bd), fac, 1.0)
        mc = val * f * p.raw_close.to_numpy()[ix]
        good = ok & (age <= 400)
        p.loc[p.index[ix], "mcap"] = np.where(good, mc, np.nan)
        p.loc[p.index[ix], "multiclass"] = np.where(good, sh.n.to_numpy()[jj] > 1, False)
    p["year"] = p.date.str[:4]
    p["zone"] = p.flow.map(lambda f: zone(f) if f == f else None)
    p.to_parquet(C.WORK / "panel.parquet")

    res = {"note": "Etapa 0: agregados sin ningún rendimiento posterior.", "sec_filings_dropped_outliers": sec_dropped}
    sig = p[p.date >= p["index"].map(C.SIGNAL_START)]
    cov = {}
    for (i, y), g in sig.groupby(["index", "year"]):
        cov.setdefault(i, {})[y] = {"member_days": int(len(g)), "with_price_pct": round(100 * (g.via != "missing").mean(), 2),
                                    "via_rename_pct": round(100 * (g.via == "rename").mean(), 2),
                                    "via_cik_pct": round(100 * (g.via == "cik").mean(), 2),
                                    "flow_complete_pct": round(100 * g.flow_complete.fillna(False).mean(), 2),
                                    "event_excluded_pct": round(100 * g.event_excluded.mean(), 2),
                                    "mcap_pct": round(100 * g.mcap.notna().mean(), 2),
                                    "snapshot_confirmed_pct": round(100 * g.snapshot_confirmed.mean(), 2),
                                    "multiclass_pct": round(100 * g.multiclass.mean(), 2)}
    res["coverage_index_year"] = cov
    res["coverage_index_sector"] = {i: {s: round(100 * (g.via != "missing").mean(), 2)
                                        for s, g in gi.groupby("sector")} for i, gi in sig.groupby("index")}
    res["missing_tickers_top"] = {i: g[g.via == "missing"].ticker.value_counts().head(25).to_dict()
                                  for i, g in sig.groupby("index")}
    ok = sig[sig.flow_complete.fillna(False) & ~sig.event_excluded]
    res["flow_distribution"] = {i: {"days": int(len(g)), "pct_negative": round(100 * (g.flow < 0).mean(), 2),
                                    "quantiles": {str(q): round(float(g.flow.quantile(q)), 1)
                                                  for q in (.01, .025, .05, .1, .25, .5)},
                                    "zones": g.zone.value_counts().to_dict()} for i, g in ok.groupby("index")}
    # episodios: primera entrada bajo X tras >= 10 sesiones con Flow >= X (solo días completos)
    epi = defaultdict(int)
    for (i, k), g in ok.sort_values("date").groupby(["index", "key"]):
        f = g.flow.to_numpy()
        pp = g.date.map(cpos).to_numpy()
        for X in (-10, -20, -30):
            last_in = -10 ** 9
            for n in range(len(f)):
                if f[n] < X:
                    if pp[n] - last_in > 10 and (n == 0 or f[n - 1] >= X or pp[n] - pp[n - 1] > 1):
                        epi[(i, X)] += 1
                    last_in = pp[n]
    res["episodes"] = {f"{i} X={X}": n for (i, X), n in sorted(epi.items())}
    neg = ok[ok.flow < 0]
    filt = (neg.raw_close < 3) | (neg.adv20 < 1e6) | neg.adv20.isna()
    res["operable_filter_removes_pct"] = {i: {z: round(100 * filt[g.index].mean(), 2) for z, g in gi.groupby("zone")}
                                          for i, gi in neg.groupby("index")}
    res["operable_filter_detail"] = {i: {"price_lt_3_pct": round(100 * (g.raw_close < 3).mean(), 2),
                                         "adv_lt_1M_pct": round(100 * (g.adv20 < 1e6).mean(), 2)}
                                     for i, g in neg.groupby("index")}
    tw = neg[neg.terminal_within_40 != ""]
    res["terminal_affected_negative_days"] = {
        i: {"total": int(len(g)), "pct_of_negative": round(100 * len(g) / max(1, (neg["index"] == i).sum()), 3),
            "by_category": g.terminal_within_40.value_counts().to_dict(),
            "by_zone": g.zone.value_counts().to_dict(),
            "by_year": g.year.value_counts().sort_index().to_dict()} for i, g in tw.groupby("index")}
    json.dump(res, open(C.PUB / "stage0_coverage.json", "w"), indent=1, default=str)
    print(json.dumps({k: res[k] for k in ("flow_distribution", "episodes")}, indent=1, default=str))


if __name__ == "__main__":
    main()
