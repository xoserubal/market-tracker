"""D2 (viabilidad) — validación por CIK (sustituye a la comparación por nombre de s2_etf_validate.py).

V1  ETF frente a composición conocida en años fiables (S&P 600 2022-2023, S&P 400 2021-2023).
V2  Periodo objetivo: acuerdo entre gestores (mismo índice, fechas iguales o a un mes) y ETF frente a nuestra
    reconstrucción (S&P 400 defectuosa, S&P 600 congelado).
V3  Altas y bajas entre carteras consecutivas del mismo fondo frente a la tabla de cambios oficial (S&P 600 2020-2022).
GAP Periodo objetivo: posiciones sin CIK en el universo (empresas que habría que añadir) y si EDGAR las identifica.
Sin precios ni rendimientos. Agregados en data/d2_validation_cik.json; listas en etf_holdings/validation_cik_detail.json.
"""
import json
import re

import pandas as pd

import fn_config as C
import s2_etf_lib as L
from s2_etf_validate import norm
from s2_link import Linker


def linked(h, lk):
    out, bad = {}, []
    for r in h["rows"]:
        k, t, s = lk.link(r["name"], h["period"])
        if k:
            out[k] = r["name"]
        else:
            bad.append((r["name"], t, s))
    return out, bad


def members(mem, idx, d, lk):
    m = mem[(mem["index"] == idx) & (mem.start <= d) & (mem.end2 > d)]
    out, nocik = {}, []
    for r in m.itertuples():
        k = lk.ticker_cik(r.ticker, d)
        if k:
            out[k] = f"{r.ticker} {r.name}"
        else:
            nocik.append(r.ticker)
    return out, nocik


def change_ciks(chg, idx, d, days, lk):
    w = chg[(chg["index"] == idx) & ((chg.date - pd.Timestamp(d)).abs().dt.days <= days)]
    s = set()
    for r in w.itertuples():
        for t in (r.add_t, r.rem_t):
            if isinstance(t, str) and t:
                k = lk.ticker_cik(t, r.date.strftime("%Y-%m-%d"), 120)
                if k:
                    s.add(k)
    return s


def vs_index(h, mem, idx, chg, lk):
    d = h["period"]
    e, bad = linked(h, lk)
    m, nocik = members(mem, idx, d, lk)
    near = change_ciks(chg, idx, d, 31, lk)
    extra = set(e) - set(m)
    miss = set(m) - set(e)
    return {"fund": h["fund"], "date": d, "n_etf": len(h["rows"]), "etf_linked": len(e), "etf_unlinked": len(bad),
            "n_index": len(m) + len(nocik), "index_no_cik": len(nocik), "both": len(set(e) & set(m)),
            "etf_not_index": len(extra), "index_not_etf": len(miss),
            "etf_not_index_change_31d": len(extra & near), "index_not_etf_change_31d": len(miss & near),
            "coverage_pct": round(100 * len(set(e) & set(m)) / max(1, len(m)), 2),
            "precision_pct": round(100 * len(set(e) & set(m)) / max(1, len(e)), 2),
            "_extra": [(k, e[k]) for k in sorted(extra)], "_missing": [(k, m[k]) for k in sorted(miss)],
            "_unlinked": bad}


def vs_etf(a, b, lk):
    ea, ba = linked(a, lk)
    eb, bb = linked(b, lk)
    return {"a": f"{a['fund']} {a['period']}", "b": f"{b['fund']} {b['period']}", "a_linked": len(ea),
            "b_linked": len(eb), "a_unlinked": len(ba), "b_unlinked": len(bb), "both": len(set(ea) & set(eb)),
            "a_only": len(set(ea) - set(eb)), "b_only": len(set(eb) - set(ea)),
            "_a_only": [ea[k] for k in set(ea) - set(eb)], "_b_only": [eb[k] for k in set(eb) - set(ea)]}


def transitions(fund, dates, chg, idx, lk):
    res, prev = [], None
    ch = chg[chg["index"] == idx]
    for d in dates:
        h = L.holdings(fund, d)
        if h is None:
            continue
        cur, _ = linked(h, lk)
        if prev:
            pdte, pset = prev
            w = ch[(ch.date > pd.Timestamp(pdte)) & (ch.date <= pd.Timestamp(d))]
            oa = {lk.ticker_cik(t, r.date.strftime("%Y-%m-%d"), 120) for r in w.itertuples() for t in [r.add_t]
                  if isinstance(t, str) and t} - {None}
            orm = {lk.ticker_cik(t, r.date.strftime("%Y-%m-%d"), 120) for r in w.itertuples() for t in [r.rem_t]
                   if isinstance(t, str) and t} - {None}
            adds, rems = set(cur) - set(pset), set(pset) - set(cur)
            res.append({"fund": fund, "from": pdte, "to": d, "official_adds": len(oa), "official_adds_seen": len(oa & adds),
                        "official_rems": len(orm), "official_rems_seen": len(orm & rems), "etf_adds": len(adds),
                        "etf_adds_official": len(adds & oa), "etf_rems": len(rems), "etf_rems_official": len(rems & orm)})
        prev = (d, cur)
    return res


def main():
    lk = Linker()
    mem = pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False)
    mem["end2"] = mem.end.replace("", "9999")
    chg = pd.read_csv(C.PUB / "changes.csv", dtype=str)
    chg["date"] = pd.to_datetime(chg.date)
    inv = L.inventory()
    per = {f: sorted(set(g.period)) for f, g in inv.groupby("fund")}
    out, det = {}, {}

    def strip(r):
        return {k: v for k, v in r.items() if not k.startswith("_")}

    v1 = []
    for idx, funds, years in (("sp600", ("IJR", "VIOO", "SLY"), ("2022", "2023")),
                              ("sp400", ("IJH", "IVOO"), ("2021", "2022", "2023"))):
        for f in funds:
            for y in years:
                ds = [d for d in per.get(f, []) if d.startswith(y)]
                for d in sorted(set(ds[:1] + ds[-1:])):
                    h = L.holdings(f, d, inv)
                    if h is None:
                        continue
                    r = vs_index(h, mem, idx, chg, lk)
                    det[f"V1 {f} {d}"] = {k: v for k, v in r.items() if k.startswith("_")}
                    v1.append(strip(r) | {"index": idx})
                    print("V1", idx, f, d, {k: r[k] for k in ("n_etf", "etf_unlinked", "n_index", "index_no_cik", "both",
                                                             "etf_not_index", "index_not_etf",
                                                             "etf_not_index_change_31d", "index_not_etf_change_31d")}, flush=True)
    out["V1"] = v1

    v2 = []
    for a, b in (("IJR 2016-12-31", "SLY 2016-12-30"), ("IJR 2016-12-31", "VIOO 2016-11-30"),
                 ("IJR 2018-12-31", "SLY 2018-12-31"), ("IJR 2018-12-31", "VIOO 2018-11-30"),
                 ("IJR 2015-12-31", "SLY 2015-12-31"), ("IJH 2016-12-31", "IVOO 2016-11-30"),
                 ("IJH 2018-12-31", "IVOO 2018-11-30"), ("IJH 2015-12-31", "IVOO 2015-11-30")):
        ha, hb = L.holdings(*a.split(), inv), L.holdings(*b.split(), inv)
        if ha is None or hb is None:
            print("V2 sin datos", a, b)
            continue
        r = vs_etf(ha, hb, lk)
        det[f"V2 {a} vs {b}"] = {k: v for k, v in r.items() if k.startswith("_")}
        v2.append(strip(r))
        print("V2", strip(r), flush=True)
    for f, d, idx in (("IJH", "2015-12-31", "sp400"), ("IJH", "2016-12-31", "sp400"), ("IJH", "2017-12-31", "sp400"),
                      ("IJH", "2018-12-31", "sp400"), ("IJH", "2019-12-31", "sp400"), ("IJH", "2020-12-31", "sp400"),
                      ("IJR", "2016-12-31", "sp600"), ("IJR", "2018-12-31", "sp600"), ("IJR", "2019-12-31", "sp600"),
                      ("IJR", "2020-12-31", "sp600")):
        h = L.holdings(f, d, inv)
        if h is None:
            continue
        r = vs_index(h, mem, idx, chg, lk)
        det[f"V2rec {f} {d}"] = {k: v for k, v in r.items() if k.startswith("_")}
        v2.append({"vs_reconstruction": f"{f} {d}"} | strip(r))
        print("V2rec", f, d, {k: r[k] for k in ("etf_linked", "etf_unlinked", "n_index", "both", "etf_not_index",
                                                 "index_not_etf")}, flush=True)
    out["V2"] = v2

    v3 = []
    for f in ("IJR", "VIOO", "SLY"):
        ds = [d for d in per.get(f, []) if "2019-12-01" <= d <= "2022-12-31"]
        v3 += transitions(f, ds, chg, "sp600", lk)
    tot = {k: sum(x[k] for x in v3) for k in v3[0] if k not in ("fund", "from", "to")} if v3 else {}
    out["V3"] = {"pairs": v3, "totals": tot}
    print("V3", tot, flush=True)

    # GAP: posiciones sin CIK del universo en el periodo objetivo, y si el listado completo de EDGAR las identifica
    lkp = {}
    lf = C.SEC / "cik-lookup-data.txt"
    if lf.exists():
        for line in open(lf, encoding="latin-1"):
            m = re.match(r"^(.*):(\d{10}):\s*$", line.rstrip("\n"))
            if m:
                lkp.setdefault(norm(m.group(1)), set()).add(m.group(2).lstrip("0"))
    gap, names_seen = {}, {}
    for f, rng in (("IJR", ("2015-01", "2020-01")), ("VIOO", ("2015-01", "2020-01")), ("IJH", ("2016-01", "2021-01")),
                   ("IVOO", ("2016-01", "2021-01"))):
        ds = [d for d in per.get(f, []) if rng[0] <= d < rng[1]]
        for d in ds[1::2]:      # una de cada dos fechas: muestra suficiente para estimar
            h = L.holdings(f, d, inv)
            if h is None:
                continue
            _, bad = linked(h, lk)
            for n, t, s in bad:
                names_seen.setdefault(norm(n), (n, t, f, d))
    cls = {"edgar_unique": 0, "edgar_multiple": 0, "edgar_none": 0}
    for x, (n, t, f, d) in names_seen.items():
        c = lkp.get(x, set())
        cls["edgar_unique" if len(c) == 1 else ("edgar_multiple" if c else "edgar_none")] += 1
    gap = {"distinct_unlinked_names": len(names_seen), "by_edgar_lookup": cls,
           "unlinked_type": pd.Series([v[1] for v in names_seen.values()]).value_counts().to_dict()}
    det["GAP"] = sorted(names_seen.values())
    out["GAP"] = gap
    print("GAP", gap)
    json.dump(out, open(C.PUB / "d2_validation_cik.json", "w"), indent=1, default=str)
    json.dump(det, open(L.ETF / "validation_cik_detail.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
