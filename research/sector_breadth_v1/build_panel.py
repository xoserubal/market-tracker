"""Etapa 1 del preregistro wiki/PREREGISTRO_SECTOR_BREADTH_V1.md (firmado 2026-11-11):
composición del S&P 500 a fecha, verificación de identidad, deduplicación de clases, fiabilidad por sector y variables
(amplitud, controles del ETF, objetivos). No calcula ningún estadístico de predicción.
Salidas: _work/panel.parquet, _work/etf_daily.parquet, data_quality.json"""
import io
import json
import os
import re
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
W = os.path.join(HERE, "_work")
os.makedirs(W, exist_ok=True)
CACHE = os.path.join(HERE, "..", "macd_combo_filters_v1", "prices_cache.parquet")
YEARS = list(range(2016, 2027))
SECTOR_ETF = {"Information Technology": "XLK", "Financials": "XLF", "Health Care": "XLV",
              "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Energy": "XLE", "Industrials": "XLI",
              "Materials": "XLB", "Real Estate": "XLRE", "Communication Services": "XLC", "Utilities": "XLU"}
SECTOR_NORM = {"Telecommunication Services": "Communication Services", "Telecommunications Services": "Communication Services"}
RECLASS = [pd.Timestamp("2016-09-01"), pd.Timestamp("2018-09-24"), pd.Timestamp("2023-03-20")]
XLC_FROM = pd.Timestamp("2018-10-01")
START, END = "2019-01-01", "2026-11-09"
STOP = {"inc", "corp", "corporation", "company", "co", "plc", "ltd", "limited", "the", "holdings", "holding", "group",
        "class", "a", "b", "c", "de", "sa", "nv", "n", "v", "and", "llc", "lp", "trust", "international", "intl"}


def norm_t(t):
    return str(t).strip().replace("\xa0", " ").split(":")[-1].strip().replace(".", "-").upper()


def norm_cik(c):
    return re.sub(r"\D", "", str(c)).lstrip("0")


def toks(name):
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", str(name).lower().replace("&", " ")).split() if w not in STOP}


def read_snapshot(name):
    tabs = pd.read_html(io.StringIO(open(os.path.join(D, f"wiki_{name}.html"), encoding="utf-8").read()))
    t = tabs[0]
    sym = next(c for c in t.columns if "ymbol" in str(c))
    sec = next(c for c in t.columns if "GICS Sector" in str(c))
    cik = next((c for c in t.columns if "CIK" in str(c)), None)
    added = next((c for c in t.columns if "added" in str(c).lower()), None)
    out = pd.DataFrame({"ticker": t[sym].map(norm_t), "sector": t[sec].astype(str).map(lambda s: SECTOR_NORM.get(s, s)),
                        "cik": t[cik].map(norm_cik) if cik is not None else "", "name": t["Security"].astype(str),
                        "added": pd.to_datetime(t[added], errors="coerce") if added is not None else pd.NaT})
    return out.drop_duplicates("ticker"), tabs


def main():
    revs = json.load(open(os.path.join(D, "wiki_revisions.json")))
    ts = {y: pd.Timestamp(revs[str(y)]["timestamp"]).tz_localize(None) for y in YEARS}
    snaps = {y: read_snapshot(y)[0] for y in YEARS}
    cur = read_snapshot("current")[0]
    ch = read_snapshot(2026)[1][1].copy()
    ch.columns = ["date", "add_t", "add_n", "rem_t", "rem_n", "reason"]
    ch["date"] = pd.to_datetime(ch.date, errors="coerce")
    ch = ch[ch.date >= "2015-06-01"].sort_values("date")
    for c in ("add_t", "rem_t"):
        ch[c] = [norm_t(x) if isinstance(x, str) and x.strip() else None for x in ch[c]]

    # metadatos por símbolo (CIK, nombre, sector por año)
    cik_of, name_of, sec_by_year = {}, {}, defaultdict(dict)
    for y in YEARS:
        for r in snaps[y].itertuples():
            if r.cik: cik_of[r.ticker] = r.cik
            name_of[r.ticker] = r.name
            sec_by_year[r.ticker][y] = r.sector
    for r in cur.itertuples():
        if r.cik: cik_of.setdefault(r.ticker, r.cik)
        name_of.setdefault(r.ticker, r.name)
        sec_by_year[r.ticker][2027] = r.sector
    for r in ch.itertuples():
        if r.rem_t: name_of.setdefault(r.rem_t, r.rem_n)
        if r.add_t: name_of.setdefault(r.add_t, r.add_n)

    # ── precios ──
    px = pd.concat([pd.read_parquet(CACHE), pd.read_parquet(os.path.join(D, "departed_prices.parquet"))])
    px["date"] = pd.to_datetime(px.date)
    px = px.drop_duplicates(["ticker", "date"])
    f = px.adj_close / px.close
    px = px.assign(ao=px.open * f, dv=px.close * px.volume)
    AC = px.pivot(index="date", columns="ticker", values="adj_close").sort_index()
    cal = AC["SPY"].dropna().index
    AC = AC.reindex(cal)
    AO = px.pivot(index="date", columns="ticker", values="ao").reindex(cal)
    DV = px.pivot(index="date", columns="ticker", values="dv").reindex(cal)
    hist = AC.notna().cumsum()
    dv63 = DV.rolling(63, min_periods=20).median()
    ret21 = AC / AC.shift(21) - 1
    sma50 = AC.rolling(50, min_periods=50).mean()
    pos = {d: i for i, d in enumerate(cal)}

    # ── verificación de identidad de los símbolos que ya no están en el índice ──
    yn = json.load(open(os.path.join(D, "departed_yahoo_names.json"), encoding="utf-8"))
    departed = set(pd.read_parquet(os.path.join(D, "departed_prices.parquet")).ticker.unique())
    verify = {}
    for t in sorted(departed):
        wn = toks(name_of.get(t, ""))
        yv = yn.get(t, {})
        best = 0.0
        for k in ("longName", "shortName"):
            if yv.get(k):
                a = toks(yv[k])
                if a and wn:
                    best = max(best, len(a & wn) / min(len(a), len(wn)))
        verify[t] = {"wiki": name_of.get(t), "yahoo": yv.get("longName") or yv.get("shortName"), "overlap": round(best, 2),
                     "verified": best >= 0.5}
    unverified = {t for t, v in verify.items() if not v["verified"]}

    cik_group = defaultdict(set)
    for t, c in cik_of.items():
        cik_group[c].add(t)

    def series_for(t, i):
        """Columna de precios a usar para el símbolo t en la sesión i: (columna, estado)."""
        if t in AC.columns and not np.isnan(AC[t].iat[i]):
            if t in unverified:
                return None, "unverified"
            return t, "ok"
        alts = [a for a in cik_group.get(cik_of.get(t), set()) - {t}
                if a in AC.columns and not np.isnan(AC[a].iat[i]) and a not in unverified]
        if len(alts) == 1:
            return alts[0], "renamed"
        if len(alts) > 1:   # más de un candidato con precio: ambiguo (regla del preregistro §3)
            return None, "ambiguous"
        return None, "missing"

    def sector_at(t, d, y, base_sector):
        s = base_sector
        if s is None:   # alta a mitad de año: sector de la siguiente instantánea o de la lista actual
            nxt = [sec_by_year[t][k] for k in sorted(sec_by_year[t]) if k > y]
            s = nxt[0] if nxt else None
        else:
            nx = sec_by_year[t].get(y + 1) or sec_by_year[t].get(2027)
            if nx and nx != s:
                upper = ts.get(y + 1, pd.Timestamp("2100-01-01"))
                for rd in RECLASS:
                    if ts[y] < rd <= upper and d >= rd:
                        s = nx
        return s

    def members(d):
        y = max(yy for yy in YEARS if ts[yy] <= d)
        m = {r.ticker: r.sector for r in snaps[y].itertuples()}
        for r in ch[(ch.date > ts[y]) & (ch.date <= d)].itertuples():
            if r.rem_t: m.pop(r.rem_t, None)
            if r.add_t: m[r.add_t] = None
        if y == 2026:
            curset = set(cur.ticker)
            for r in cur.itertuples():
                if r.ticker not in m and pd.notna(r.added) and r.added <= d:
                    m[r.ticker] = r.sector
            i = pos[d]
            for t in list(m):
                if t not in curset:   # salida en 2026 sin fecha: miembro mientras cotiza
                    col, _ = series_for(t, i)
                    if col is None:
                        m.pop(t)
        return {t: sector_at(t, d, y, s) for t, s in m.items()}, y

    # fechas: último día de cada semana + la sesión 20 antes de cada una
    wk = pd.Series(cal, index=cal)
    wk = wk[(wk >= pd.Timestamp(START) - pd.Timedelta(days=40)) & (wk <= END)]
    dec = wk.groupby(wk.dt.to_period("W-FRI")).max().tolist()
    need = sorted(set(dec) | {cal[pos[d] - 20] for d in dec})
    spy = AC["SPY"]
    rows = []
    dq = defaultdict(lambda: {"entities": 0, "with_price": 0, "unknown_sector": 0, "ambiguous": 0, "renamed": 0})
    for d in need:
        i = pos[d]
        mem, y = members(d)
        ents = {}
        for t, s in mem.items():
            col, st = series_for(t, i)
            key = cik_of.get(t) or t
            dvv = np.nan_to_num(dv63[col].iat[i]) if col else -1
            prev = ents.get(key)
            if prev is None or dvv > prev["dv"]:
                ents[key] = {"t": t, "sector": s, "col": col, "st": st, "dv": dvv}
        spy21 = spy.iat[i] / spy.iat[i - 21] - 1
        by_sec = defaultdict(list)
        for e in ents.values():
            by_sec[e["sector"]].append(e)
        unknown = len(by_sec.pop(None, []))
        for s, es in by_sec.items():
            if s not in SECTOR_ETF:
                continue
            ok = [e for e in es if e["col"] and hist[e["col"]].iat[i] >= 63]
            amb = sum(e["st"] in ("unverified", "ambiguous") for e in es)
            r21 = np.array([ret21[e["col"]].iat[i] for e in ok], float)
            r21 = r21[~np.isnan(r21)]
            above = np.array([AC[e["col"]].iat[i] > sma50[e["col"]].iat[i] for e in ok if not np.isnan(sma50[e["col"]].iat[i])])
            etf = SECTOR_ETF[s]
            etf21 = AC[etf].iat[i] / AC[etf].iat[i - 21] - 1 if etf in AC else np.nan
            rows.append({"date": d, "sector": s, "etf": etf, "n_members": len(es), "n_priced": len(ok),
                         "coverage": len(ok) / len(es), "ambiguous_share": amb / len(es),
                         "unknown_sector_total": unknown,
                         "P21": float(np.mean(r21 > spy21)) if len(r21) else np.nan,
                         "above50": float(np.mean(above)) if len(above) else np.nan,
                         "ew_minus_etf21": float(np.mean(r21) - etf21) if len(r21) else np.nan})
            if d in dec and d >= pd.Timestamp(START):
                q = dq[f"{s}|{d.year}"]
                q["entities"] += len(es); q["with_price"] += len(ok); q["ambiguous"] += amb
                q["renamed"] += sum(e["st"] == "renamed" for e in es)
        if d in dec and d >= pd.Timestamp(START):
            dq[f"_all|{d.year}"]["unknown_sector"] += unknown
    pan = pd.DataFrame(rows)

    # variables por fecha de decisión
    etfs = sorted(set(SECTOR_ETF.values()))
    out = []
    for d in dec:
        if d < pd.Timestamp(START):
            continue
        i = pos[d]
        d20 = cal[i - 20]
        cur_rows = pan[pan.date == d].set_index("sector")
        prev_rows = pan[pan.date == d20].set_index("sector")
        for s, r in cur_rows.iterrows():
            etf = r.etf
            if etf not in AC or np.isnan(AC[etf].iat[i]) or (s == "Communication Services" and d < XLC_FROM):
                continue
            def rs(k, j):
                return (AC[etf].iat[j] / AC[etf].iat[j - k] - 1) - (spy.iat[j] / spy.iat[j - k] - 1)
            rec = {"date": d, "sector": s, "etf": etf, "n_members": r.n_members, "n_priced": r.n_priced,
                   "coverage": r.coverage, "ambiguous_share": r.ambiguous_share, "unknown_sector_total": r.unknown_sector_total,
                   "P21": r.P21, "dP": r.P21 - prev_rows.P21.get(s, np.nan),
                   "above50": r.above50, "d_above50": r.above50 - prev_rows.above50.get(s, np.nan),
                   "ew_minus_etf21": r.ew_minus_etf21,
                   "RS21": rs(21, i), "RS63": rs(63, i), "dRS21": rs(21, i) - rs(21, i - 20),
                   "spy_above_sma200": bool(spy.iat[i] > spy.iloc[i - 199:i + 1].mean())}
            for H in (10, 20, 40, 60):
                if i + H < len(cal):
                    e = AC[etf].iat[i + H] / AO[etf].iat[i + 1] - 1
                    sp = AC["SPY"].iat[i + H] / AO["SPY"].iat[i + 1] - 1
                    rec[f"y{H}"] = e - sp
                else:
                    rec[f"y{H}"] = np.nan
            out.append(rec)
    panel = pd.DataFrame(out)
    panel.to_parquet(os.path.join(W, "panel.parquet"))
    # ETF diario (para transiciones de liderazgo)
    ed = pd.DataFrame({e: AC[e] for e in etfs if e in AC})
    ed["SPY"] = spy
    ed.to_parquet(os.path.join(W, "etf_daily.parquet"))
    pd.DataFrame({e: AO[e] for e in etfs + ["SPY"] if e in AO}).to_parquet(os.path.join(W, "etf_open_daily.parquet"))

    q = {k: dict(v) for k, v in dq.items()}
    for v in q.values():
        if v["entities"]:
            v["coverage"] = round(v["with_price"] / v["entities"], 3)
            v["ambiguous_share"] = round(v["ambiguous"] / v["entities"], 3)
    json.dump({"verification": verify, "unverified": sorted(unverified), "coverage_by_sector_year": q,
               "n_decision_dates": int(panel.date.nunique())},
              open(os.path.join(HERE, "data_quality.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    print("panel", panel.shape, "fechas", panel.date.nunique(), "no verificados", len(unverified))
    print(sorted(unverified))


if __name__ == "__main__":
    main()
