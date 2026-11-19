"""D2 (viabilidad) — ¿sirven las carteras de los ETF como composición del índice? Sin precios ni rendimientos.

V1. ETF frente a composición conocida (años con composición reconstruida fiable: S&P 600 2022+, S&P 400 2021+).
    Mide el error de tratar cada posición del ETF como miembro del índice.
V2. Periodo objetivo (2015-2019): acuerdo entre gestores distintos (iShares, Vanguard, SPDR) y del ETF frente a
    nuestra reconstrucción del S&P 400 (conocida como defectuosa en 2016-2020).
V3. Transiciones: ¿las altas y bajas entre dos carteras consecutivas recogen los cambios oficiales (tabla de cambios
    del S&P 600, completa desde dic-2019) y con qué retraso?

El enlace es por nombre, porque los N-Q no traen identificador. El error del enlace por nombre forma parte de lo que se
mide. Salida: data/d2_validation.json (agregados) y FLOWNEG_DATA_DIR/etf_holdings/validation_detail.json (listas).
"""
import json
import re
from difflib import SequenceMatcher

import pandas as pd

import fn_config as C
import s2_etf_lib as L

STOP = {"inc", "incorporated", "corp", "corporation", "co", "company", "companies", "the", "ltd", "limited", "plc",
        "llc", "lp", "nv", "sa", "class", "cl", "a", "b", "c", "com", "shs", "new", "reit", "de", "of"}


def norm(n):
    n = str(n).lower().replace("&amp;", "&").replace("&", " and ")
    n = re.sub(r"\(.*?\)|\[.*?\]", " ", n)
    n = re.sub(r"/[a-z]{2}\b", " ", n)                     # «Bancorp Inc./KY»
    n = n.replace(".com", "com")
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    w = [x for x in n.split() if x not in STOP]
    return " ".join(w)


def match(etf_names, ref):
    """etf_names: lista de nombres; ref: dict clave → nombre. Devuelve {nombre_etf: (clave|None, tipo, score)}.
    tipo: exacto | difuso (≥ 0,90 y margen ≥ 0,05 sobre el segundo) | ambiguo (0,80-0,90 o sin margen) | sin_enlace."""
    rn = {k: norm(v) for k, v in ref.items()}
    by = {}
    for k, v in rn.items():
        by.setdefault(v, []).append(k)
    out, used = {}, set()
    for n in etf_names:
        x = norm(n)
        if x in by and len(by[x]) == 1:
            out[n] = (by[x][0], "exacto", 1.0)
            used.add(by[x][0])
    for n in etf_names:
        if n in out:
            continue
        x = norm(n)
        sc = []
        for k, v in rn.items():
            if k in used:
                continue
            sm = SequenceMatcher(None, x, v)
            if sm.real_quick_ratio() < 0.6 or sm.quick_ratio() < 0.6:
                continue
            sc.append((sm.ratio(), k))
        sc.sort(reverse=True)
        if not sc:
            out[n] = (None, "sin_enlace", 0.0)
            continue
        s1, k1 = sc[0]
        s2 = sc[1][0] if len(sc) > 1 else 0.0
        # prefijo común largo: «Aerojet Rocketdyne Holdings» frente a «Aerojet Rocketdyne»
        pre = x and rn[k1] and (x.startswith(rn[k1]) or rn[k1].startswith(x)) and min(len(x), len(rn[k1])) >= 6
        if (s1 >= 0.90 and s1 - s2 >= 0.05) or (pre and s1 - s2 >= 0.05):
            out[n] = (k1, "difuso", round(s1, 3))
            used.add(k1)
        elif s1 >= 0.80:
            out[n] = (k1, "ambiguo", round(s1, 3))
        else:
            out[n] = (None, "sin_enlace", round(s1, 3))
    return out


def members(mem, idx, d):
    m = mem[(mem["index"] == idx) & (mem.start <= d) & (mem.end2 > d)]
    return dict(zip(m.ticker, m.name))


def compare_to_index(h, mem, idx, d, chg):
    ref = members(mem, idx, d)
    names = [r["name"] for r in h["rows"]]
    mt = match(names, ref)
    hit = {k for k, t, _ in mt.values() if t in ("exacto", "difuso")}
    extra = [n for n, (k, t, s) in mt.items() if t not in ("exacto", "difuso")]
    missing = sorted(set(ref) - hit)
    # ¿las diferencias se explican por un cambio oficial en ±15 días? (fecha efectiva cercana a la de la cartera)
    near = chg[(chg["index"] == idx) & ((chg.date - pd.Timestamp(d)).abs().dt.days <= 15)]
    near_t = set(near.add_t.dropna()) | set(near.rem_t.dropna())
    near_n = {norm(x) for x in list(near.add_n.dropna()) + list(near.rem_n.dropna())}
    return {"date_etf": h["period"], "fund": h["fund"], "type": h["type"], "parse_check": h.get("check"),
            "n_etf": len(names), "n_index": len(ref),
            "matched": len(hit), "exact": sum(1 for v in mt.values() if v[1] == "exacto"),
            "fuzzy": sum(1 for v in mt.values() if v[1] == "difuso"),
            "ambiguous": sum(1 for v in mt.values() if v[1] == "ambiguo"),
            "etf_not_in_index": len(extra), "index_not_in_etf": len(missing),
            "missing_explained_by_change_15d": sum(1 for t in missing if t in near_t),
            "extra_explained_by_change_15d": sum(1 for n in extra if norm(n) in near_n),
            "coverage_of_index_pct": round(100 * len(hit) / max(1, len(ref)), 2),
            "precision_pct": round(100 * len(hit) / max(1, len(names)), 2),
            "_extra": [(n, mt[n][1], mt[n][0], mt[n][2]) for n in extra],
            "_missing": [(t, ref[t]) for t in missing],
            "_fuzzy": [(n, k, ref.get(k), s) for n, (k, t, s) in mt.items() if t == "difuso"]}


def compare_etfs(a, b):
    """Acuerdo entre dos carteras del mismo índice (gestores distintos), por nombre."""
    ref = {f"b{i}": r["name"] for i, r in enumerate(b["rows"])}
    mt = match([r["name"] for r in a["rows"]], ref)
    hit = {k for k, t, _ in mt.values() if t in ("exacto", "difuso")}
    return {"a": f"{a['fund']} {a['period']}", "b": f"{b['fund']} {b['period']}", "n_a": len(a["rows"]),
            "n_b": len(b["rows"]), "matched": len(hit),
            "a_not_in_b": [n for n, (k, t, s) in mt.items() if t not in ("exacto", "difuso")],
            "b_not_in_a": [ref[k] for k in ref if k not in hit]}


def transitions(fund_dates, chg, idx, lo, hi):
    """V3: cambios oficiales frente a altas/bajas entre carteras consecutivas (todas las fuentes juntas, por fecha)."""
    seq = sorted(((d, f) for f, ds in fund_dates.items() for d in ds if lo <= d <= hi))
    ch = chg[(chg["index"] == idx) & (chg.date >= lo) & (chg.date <= hi)]
    res = []
    prev_by = {}
    for d, f in seq:
        prev = prev_by.get(f)
        h = L.holdings(f, d)
        if h is None:
            continue
        cur = {norm(r["name"]) for r in h["rows"]}
        if prev is not None:
            pd_, pf, pset = prev
            if True:       # mismo gestor: las altas/bajas no mezclan diferencias de nombre entre gestores
                w = ch[(ch.date > pd.Timestamp(pd_)) & (ch.date <= pd.Timestamp(d))]
                adds, rems = cur - pset, pset - cur
                off_add = {norm(x) for x in w.add_n.dropna()}
                off_rem = {norm(x) for x in w.rem_n.dropna()}

                def hit(xs, ys):
                    return sum(1 for x in xs if any(SequenceMatcher(None, x, y).ratio() >= 0.85 for y in ys))
                res.append({"fund": f, "from": pd_, "to": d, "official_adds": len(off_add),
                            "official_adds_seen": hit(off_add, adds), "official_rems": len(off_rem),
                            "official_rems_seen": hit(off_rem, rems), "etf_adds": len(adds),
                            "etf_adds_official": hit(adds, off_add), "etf_rems": len(rems),
                            "etf_rems_official": hit(rems, off_rem)})
        prev_by[f] = (d, f, cur)
    return res


def main():
    mem = pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False)
    mem["end2"] = mem.end.replace("", "9999")
    chg = pd.read_csv(C.PUB / "changes.csv", dtype=str)
    chg["date"] = pd.to_datetime(chg.date)
    inv = L.inventory()
    per = {f: sorted(set(g.period)) for f, g in inv.groupby("fund")}
    out, detail = {}, {}

    # V1
    v1 = []
    for idx, funds, years in (("sp600", ("IJR", "VIOO", "SLY"), ("2022", "2023")),
                              ("sp400", ("IJH", "IVOO"), ("2021", "2022", "2023"))):
        for f in funds:
            for y in years:
                ds = [d for d in per.get(f, []) if d.startswith(y)]
                for d in ds[:1] + ds[-1:] if len(ds) > 1 else ds:
                    h = L.holdings(f, d, inv)
                    if h is None:
                        continue
                    r = compare_to_index(h, mem, idx, d, chg)
                    detail[f"V1 {f} {d}"] = {k: r[k] for k in r if k.startswith("_")}
                    v1.append({k: v for k, v in r.items() if not k.startswith("_")} | {"index": idx})
                    print("V1", idx, f, d, {k: v1[-1][k] for k in ("n_etf", "n_index", "matched", "ambiguous",
                                                                    "etf_not_in_index", "index_not_in_etf",
                                                                    "missing_explained_by_change_15d")}, flush=True)
    out["V1"] = v1

    # V2
    v2 = []
    for a, b in (("IJR 2016-12-31", "SLY 2016-12-30"), ("IJR 2016-12-31", "VIOO 2016-11-30"),
                 ("IJR 2018-12-31", "SLY 2018-12-31"), ("IJR 2018-12-31", "VIOO 2018-11-30"),
                 ("IJR 2015-06-30", "SLY 2015-06-30"),
                 ("IJH 2016-12-31", "IVOO 2016-11-30"), ("IJH 2018-12-31", "IVOO 2018-11-30")):
        ha, hb = L.holdings(*a.split(), inv), L.holdings(*b.split(), inv)
        if ha is None or hb is None:
            print("V2 sin datos", a, b)
            continue
        r = compare_etfs(ha, hb)
        detail[f"V2 {a} vs {b}"] = {"a_not_in_b": r["a_not_in_b"], "b_not_in_a": r["b_not_in_a"]}
        v2.append({k: (len(v) if isinstance(v, list) else v) for k, v in r.items()})
        print("V2", v2[-1], flush=True)
    # ETF frente a nuestra reconstrucción del S&P 400 (defectuosa) y al S&P 600 congelado (ficticio)
    for f, d, idx in (("IJH", "2016-12-31", "sp400"), ("IJH", "2018-12-31", "sp400"), ("IJH", "2019-12-31", "sp400"),
                      ("IJR", "2016-12-31", "sp600"), ("IJR", "2018-12-31", "sp600"), ("IJR", "2019-12-31", "sp600")):
        h = L.holdings(f, d, inv)
        if h is None:
            continue
        r = compare_to_index(h, mem, idx, d, chg)
        detail[f"V2rec {f} {d}"] = {k: r[k] for k in r if k.startswith("_")}
        v2.append({"vs_reconstruction": f"{f} {d}"} | {k: v for k, v in r.items() if not k.startswith("_")})
        print("V2rec", f, d, {k: r[k] for k in ("n_etf", "n_index", "matched", "etf_not_in_index",
                                                 "index_not_in_etf")}, flush=True)
    out["V2"] = v2

    # V3
    fd = {f: per[f] for f in ("IJR", "VIOO", "SLY") if f in per}
    v3 = transitions(fd, chg, "sp600", "2019-12-31", "2022-12-31")
    tot = {k: sum(x[k] for x in v3) for k in v3[0] if k not in ("fund", "from", "to")} if v3 else {}
    out["V3"] = {"pairs": v3, "totals": tot}
    print("V3", tot)
    json.dump(out, open(C.PUB / "d2_validation.json", "w"), indent=1, default=str)
    json.dump(detail, open(L.ETF / "validation_detail.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
