"""Diagnóstico de viabilidad del preregistro de amplitud sectorial (sin resultados predictivos).
Reconstruye la composición del S&P 500 2016-2026 con instantáneas anuales de Wikipedia + tabla de cambios, y mide:
coherencia de la reconstrucción, cobertura de precios (caché + sonda mensual de Yahoo para los que faltan),
reutilización de símbolos, cambios de sector GICS y clases de acciones. Salida: coverage_diag.json"""
import io
import json
import os
import re
from collections import Counter, defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
CACHE = os.path.join(HERE, "..", "macd_combo_filters_v1", "prices_cache.parquet")
YEARS = list(range(2016, 2027))
SECTOR_NORM = {"Telecommunications Services": "Communication Services", "Telecommunication Services": "Communication Services"}


def norm_t(t):
    return str(t).strip().replace(".", "-").upper()


def read_snapshot(name):
    tabs = pd.read_html(io.StringIO(open(os.path.join(D, f"wiki_{name}.html"), encoding="utf-8").read()))
    t = tabs[0]
    sym = next(c for c in t.columns if "ymbol" in str(c))
    sec = next(c for c in t.columns if "GICS Sector" in str(c))
    cik = next((c for c in t.columns if "CIK" in str(c)), None)
    out = pd.DataFrame({"ticker": t[sym].map(norm_t), "sector": t[sec].astype(str),
                        "cik": t[cik].astype(str) if cik is not None else "", "name": t["Security"].astype(str)})
    return out, tabs


def main():
    revs = json.load(open(os.path.join(D, "wiki_revisions.json")))
    snaps = {}
    for y in YEARS:
        snaps[y], _ = read_snapshot(y)
    cur, _ = read_snapshot("current")
    ts = {y: pd.Timestamp(revs[str(y)]["timestamp"]).tz_localize(None) for y in YEARS}

    _, tabs26 = read_snapshot(2026)
    ch = tabs26[1].copy()
    ch.columns = ["date", "add_t", "add_n", "rem_t", "rem_n", "reason"]
    ch["date"] = pd.to_datetime(ch.date, errors="coerce")
    ch = ch[ch.date >= "2015-06-01"].copy()
    for c in ("add_t", "rem_t"):
        ch[c] = ch[c].map(lambda x: norm_t(x) if isinstance(x, str) and x.strip() and x != "nan" else None)

    res = {"snapshot_sizes": {y: len(snaps[y]) for y in YEARS}, "current_size": len(cur),
           "changes_rows_2015_2025": int(len(ch))}

    # 1) coherencia: S_y + altas − bajas en (ts_y, ts_y+1] frente a S_y+1
    coh = {}
    for y in YEARS[:-1]:
        s = set(snaps[y].ticker)
        seg = ch[(ch.date > ts[y]) & (ch.date <= ts[y + 1])].sort_values("date")
        for _, r in seg.iterrows():
            if isinstance(r.rem_t, str): s.discard(r.rem_t)
            if isinstance(r.add_t, str): s.add(r.add_t)
        nxt = set(snaps[y + 1].ticker)
        coh[y] = {"reconstructed": len(s), "snapshot_next": len(nxt), "missing_vs_next": len(nxt - s),
                  "extra_vs_next": len(s - nxt), "jaccard": round(len(s & nxt) / len(s | nxt), 4)}
    res["reconstruction_consistency"] = coh

    # 2) membresía puntual a fin de mes (instantánea del año + cambios hasta la fecha)
    months = pd.date_range("2016-01-31", "2026-10-31", freq="ME")
    members = {}
    for m in months:
        y = max(yy for yy in YEARS if ts[yy] <= m) if any(ts[yy] <= m for yy in YEARS) else 2016
        s = dict(zip(snaps[y].ticker, snaps[y].sector))
        seg = ch[(ch.date > ts[y]) & (ch.date <= m)].sort_values("date")
        for _, r in seg.iterrows():
            if isinstance(r.rem_t, str): s.pop(r.rem_t, None)
            if isinstance(r.add_t, str): s[r.add_t] = None   # sector desconocido hasta la siguiente instantánea
        if y == 2026:   # cambios de 2026 no están en la tabla: inferidos de la lista actual
            for _, r in cur.iterrows():
                if r.ticker not in s:
                    s[r.ticker] = r.sector
        members[m] = s
    all_t = sorted({t for s in members.values() for t in s})
    res["unique_tickers_2016_2026"] = len(all_t)
    removed_after_2016 = sorted(set(all_t) - set(cur.ticker))
    res["tickers_no_longer_in_index"] = len(removed_after_2016)

    # 3) precios: caché diaria + sonda mensual de Yahoo para los que faltan
    px = pd.read_parquet(CACHE, columns=["date", "ticker"])
    cached = set(px.ticker.unique())
    first_cached = px.groupby("ticker").date.min()
    missing = [t for t in all_t if t not in cached]
    probe_file = os.path.join(D, "yahoo_monthly_probe.parquet")
    if not os.path.exists(probe_file):
        import yfinance as yf
        frames = []
        for i in range(0, len(missing), 80):
            chunk = missing[i:i + 80]
            df = yf.download(chunk, start="2015-12-01", end="2026-11-10", interval="1mo", group_by="ticker",
                             auto_adjust=False, progress=False, threads=True)
            for t in chunk:
                if t in df.columns.get_level_values(0):
                    s = df[t]["Close"].dropna()
                    if len(s):
                        frames.append(pd.DataFrame({"ticker": t, "date": s.index, "close": s.values}))
        pd.concat(frames).to_parquet(probe_file) if frames else pd.DataFrame(columns=["ticker", "date", "close"]).to_parquet(probe_file)
    probe = pd.read_parquet(probe_file)
    probe_months = probe.groupby("ticker").date.apply(lambda s: set(pd.to_datetime(s).dt.to_period("M")))

    def has_price_direct(t, m):
        if t in cached:
            return first_cached[t] <= m
        return t in probe_months.index and m.to_period("M") in probe_months[t]

    # cambios de símbolo: mismo CIK con otro símbolo (FB->META, ANTM->ELV...). Yahoo guarda el histórico en el nuevo.
    cik_t = defaultdict(set)
    for name in YEARS + ["current"]:
        s = snaps[name] if name != "current" else cur
        for t, c in zip(s.ticker, s.cik):
            c = re.sub(r"\D", "", str(c)).lstrip("0")
            if c:
                cik_t[c].add(t)
    t2c = {t: c for c, ts in cik_t.items() for t in ts}
    renamed_used = set()

    def has_price(t, m):
        if has_price_direct(t, m):
            return True
        for alt in cik_t.get(t2c.get(t), set()) - {t}:
            if has_price_direct(alt, m):
                renamed_used.add((t, alt))
                return True
        return False

    # 4) reutilización de símbolo: mismo símbolo con CIK distinto entre instantáneas
    cik_by_t = defaultdict(set)
    for y in YEARS:
        for t, c in zip(snaps[y].ticker, snaps[y].cik):
            if c and c != "nan":
                cik_by_t[t].add(re.sub(r"\D", "", c).lstrip("0"))
    reused = sorted(t for t, cs in cik_by_t.items() if len(cs) > 1)
    res["tickers_with_multiple_ciks_across_snapshots"] = reused

    # 5) cambios de sector entre instantáneas consecutivas
    sec_changes = Counter()
    moves = []
    for y in YEARS[:-1]:
        a = {t: SECTOR_NORM.get(s, s) for t, s in zip(snaps[y].ticker, snaps[y].sector)}
        b = {t: SECTOR_NORM.get(s, s) for t, s in zip(snaps[y + 1].ticker, snaps[y + 1].sector)}
        for t in set(a) & set(b):
            if a[t] != b[t]:
                sec_changes[f"{y}->{y + 1}"] += 1
                moves.append([y + 1, t, a[t], b[t]])
    res["sector_changes_between_snapshots"] = dict(sec_changes)
    res["sector_moves_detail"] = moves
    res["sector_names_seen"] = sorted({s for y in YEARS for s in snaps[y].sector})

    # 6) clases de acciones: varios símbolos con el mismo CIK en una instantánea
    multi = {}
    for y in YEARS:
        g = snaps[y][snaps[y].cik.str.len() > 0].groupby("cik").ticker.apply(list)
        multi[y] = [v for v in g if len(v) > 1]
    res["multi_class_by_year"] = {y: multi[y] for y in (2016, 2021, 2026)}
    res["multi_class_count_by_year"] = {y: len(multi[y]) for y in YEARS}

    # 7) cobertura por sector y año (fin de mes): miembros con precio / miembros; sector conocido
    sec_of = {}
    for y in YEARS:
        for t, s in zip(snaps[y].ticker, snaps[y].sector):
            sec_of.setdefault(t, {})[y] = SECTOR_NORM.get(s, s)
    for t, s in zip(cur.ticker, cur.sector):
        sec_of.setdefault(t, {})[2027] = s
    cov = defaultdict(lambda: {"member_months": 0, "with_price": 0, "sector_unknown": 0})
    overall = {"member_months": 0, "with_price": 0}
    for m, s in members.items():
        y = m.year
        for t, sec in s.items():
            secs = sec_of.get(t, {})
            sec_pt = SECTOR_NORM.get(sec, sec) if sec else (secs.get(y) or next((secs[k] for k in sorted(secs) if k >= y), None))
            key = f"{sec_pt or 'DESCONOCIDO'}|{y}"
            cov[key]["member_months"] += 1
            p = has_price(t, m)
            cov[key]["with_price"] += int(p)
            cov[key]["sector_unknown"] += int(sec_pt is None)
            overall["member_months"] += 1
            overall["with_price"] += int(p)
    res["overall_price_coverage"] = round(overall["with_price"] / overall["member_months"], 4)
    res["coverage_by_sector_year"] = {k: {**v, "pct": round(v["with_price"] / v["member_months"], 3)} for k, v in sorted(cov.items())}
    # miembros sin precio por año (lista)
    nopx = defaultdict(set)
    for m, s in members.items():
        for t in s:
            if not has_price(t, m):
                nopx[m.year].add(t)
    res["tickers_without_price_by_year"] = {y: sorted(v) for y, v in sorted(nopx.items())}
    res["renames_used"] = sorted(renamed_used)
    res["cache_vs_probe"] = {"in_cache": sum(t in cached for t in all_t), "probed": len(missing),
                             "probe_found": int(probe.ticker.nunique())}
    json.dump(res, open(os.path.join(HERE, "coverage_diag.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    for k in ("snapshot_sizes", "current_size", "changes_rows_2015_2025", "reconstruction_consistency",
              "unique_tickers_2016_2026", "tickers_no_longer_in_index", "cache_vs_probe", "overall_price_coverage",
              "tickers_with_multiple_ciks_across_snapshots", "sector_changes_between_snapshots", "sector_names_seen",
              "multi_class_count_by_year"):
        print(k, res[k])


if __name__ == "__main__":
    main()
