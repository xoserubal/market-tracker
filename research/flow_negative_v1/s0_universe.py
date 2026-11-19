"""Etapa 0 — composición histórica del S&P 500, 400 y 600 (sin precios ni resultados).

Método (el mismo de research/sector_breadth_v1): instantáneas anuales de Wikipedia (revisión vigente a 15-ene) +
tabla de cambios de la página actual. La composición de un día d sale de la última instantánea con fecha <= d más
los cambios posteriores hasta d (anclada a cada instantánea para que los errores no se acumulen).
Coherencia: aplicar los cambios de un año a su instantánea y comparar con la instantánea siguiente.

Salidas (en el repo, información pública):
  data/membership.csv      índice, ticker, nombre, inicio, fin (vacío = sigue), fuente del alta/baja
  data/changes.csv         tabla de cambios usada, con motivo
  data/universe_quality.json   tamaños, coherencia por año, tickers renombrados sin cambio registrado
"""
import io
import json
import re
from collections import defaultdict

import pandas as pd

import fn_config as C

SB = C.REPO / "research" / "sector_breadth_v1" / "data"


def norm_t(t):
    t = str(t).strip().upper()
    t = re.sub(r"\[.*?\]", "", t).strip()
    return t.replace("-", ".")          # formato Alpaca/Wikipedia: BRK.B


def is_ticker(t):
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.]{0,6}", t or ""))


def html(idx, tag):
    if idx == "sp500":
        p = C.WIKI / f"sp500_{tag}.html" if tag in ("current", "historical") else SB / f"wiki_{tag}.html"
    else:
        p = C.WIKI / f"{idx}_{tag}.html"
    return open(p, encoding="utf-8").read()


def snapshot(idx, tag):
    """Tabla de componentes: la mayor con columna de ticker y >= 300 filas."""
    tabs = pd.read_html(io.StringIO(html(idx, tag)))
    best = None
    for t in tabs:
        if len(t) < 300:
            continue
        cols = [str(c) for c in t.columns]
        if any("Added" in c or "Removed" in c for c in cols):   # la tabla de cambios también tiene «Ticker»
            continue
        tc = next((c for c in t.columns if re.search(r"ymbol|icker", str(c))), None)
        if tc is None:
            continue
        if best is None or len(t) > len(best[0]):
            best = (t, tc, cols)
    if best is None:
        return None
    t, tc, cols = best
    nc = next((c for c in t.columns if re.search(r"Security|Company", str(c))), None)
    sc = next((c for c in t.columns if "Sector" in str(c)), None)
    out = pd.DataFrame({"ticker": t[tc].map(norm_t),
                        "name": t[nc].astype(str) if nc is not None else "",
                        "sector": t[sc].astype(str) if sc is not None else ""})
    out = out[out.ticker.map(is_ticker)].drop_duplicates("ticker")
    return out


def changes(idx):
    """Tabla de cambios de la página actual: (fecha, alta, nombre, baja, nombre, motivo)."""
    tabs = pd.read_html(io.StringIO(html(idx, "historical" if idx == "sp500" else "current")))
    t = next(x for x in tabs if any("Added" in str(c) for c in x.columns) and len(x.columns) >= 5)
    t = t.iloc[:, :6].copy()
    t.columns = ["date", "add_t", "add_n", "rem_t", "rem_n", "reason"][: len(t.columns)]
    t["date"] = pd.to_datetime(t["date"].astype(str).str.replace(r"\[.*?\]", "", regex=True), errors="coerce")
    for c in ("add_t", "rem_t"):
        t[c] = t[c].map(lambda x: norm_t(x) if isinstance(x, str) and is_ticker(norm_t(x)) else None)
    t = t.dropna(subset=["date"])
    t["index"] = idx
    return t.sort_values("date", kind="stable").reset_index(drop=True)


def revisions(idx):
    if idx == "sp500":
        r = json.load(open(SB / "wiki_revisions.json"))
        return {str(y): pd.Timestamp(v["timestamp"]).tz_localize(None) for y, v in r.items() if y.isdigit()}
    r = json.load(open(C.WIKI / "revisions.json"))[idx]
    out = {str(y): pd.Timestamp(v["timestamp"]).tz_localize(None) for y, v in r.items()}
    mp = C.WIKI / f"{idx}_monthly_revisions.json"
    if idx in MONTHLY and mp.exists():   # anclas mensuales: limitan la deriva de una tabla de cambios incompleta
        for k, v in json.load(open(mp)).items():
            out["m" + k] = pd.Timestamp(v["timestamp"]).tz_localize(None)
    return out


MONTHLY = set()   # anclas mensuales probadas en sp400 y descartadas: las instantáneas se contradicen mes a mes (universe_quality_monthly_sp400_test.json)
SIZE = {"sp500": (495, 510), "sp400": (395, 405), "sp600": (590, 610)}


def _norm_name(n):
    n = re.sub(r"\[.*?\]|\(.*?\)", "", str(n)).lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    stop = {"inc", "corp", "corporation", "co", "company", "the", "holdings", "group", "ltd", "plc", "class", "a",
            "b", "llc", "lp", "trust", "international", "technologies", "technology"}
    return [w for w in n.split() if w not in stop]


def rename_pairs(missing, extra):
    """Empareja (ticker nuevo, ticker viejo) que son la misma empresa renombrada: primera palabra significativa del
    nombre igual, o un ticker contenido en el otro (CSW/CSWI, JBT/JBTM). Revisable a mano en universe_quality.json."""
    out, used = [], set()
    for tm, nm in missing:
        wm = _norm_name(nm)
        for te, ne in extra:
            if te in used:
                continue
            we = _norm_name(ne)
            same_word = bool(wm and we and wm[0] == we[0] and len(wm[0]) >= 3)
            sub = (tm.startswith(te) or te.startswith(tm)) and min(len(tm), len(te)) >= 2
            if same_word or sub:
                out.append([tm, te, nm, ne])
                used.add(te)
                break
    return out


def _apply(s, rows, forward=True):
    for r in rows:
        if forward:
            if r.rem_t:
                s.discard(r.rem_t)
            if r.add_t:
                s.add(r.add_t)
        else:
            if r.add_t:
                s.discard(r.add_t)
            if r.rem_t:
                s.add(r.rem_t)


def build(idx):
    """Composición diaria (días laborables) y su conversión a intervalos.
    Anclas: solo instantáneas de tamaño plausible. Antes de la primera ancla se reconstruye hacia atrás deshaciendo
    los cambios (S&P 600: las instantáneas 2019-2021 de Wikipedia listan 1 000-1 063 valores)."""
    revs = revisions(idx)
    start = pd.Timestamp(C.PRICE_START)
    snaps, bad = {}, {}
    for y in sorted(revs, key=revs.get):
        s = snapshot(idx, y)
        if s is None:
            continue
        lo, hi = SIZE[idx]
        (snaps if lo <= len(s) <= hi else bad)[y] = s
    years = sorted(snaps, key=revs.get)
    ch = changes(idx)
    names = {}
    for d in list(bad.values()) + [snaps[y] for y in years]:
        names.update(dict(zip(d.ticker, d.name)))
    sectors = {}
    for y in years:
        sectors.update(dict(zip(snaps[y].ticker, snaps[y].sector)))
    for r in ch.itertuples():
        if r.add_t:
            names.setdefault(r.add_t, str(r.add_n))
        if r.rem_t:
            names.setdefault(r.rem_t, str(r.rem_n))

    days = pd.bdate_range(start, C.PRICE_END)
    member = {}
    # hacia delante desde cada ancla
    for k, y in enumerate(years):
        a = revs[y]
        b = revs[years[k + 1]] if k + 1 < len(years) else days[-1] + pd.Timedelta(days=1)
        s = set(snaps[y].ticker)
        seg = ch[(ch.date > a) & (ch.date <= b)]
        rows = list(seg.itertuples())
        j = 0
        for d in days[(days > a) & (days < b)]:
            while j < len(rows) and rows[j].date <= d:
                _apply(s, [rows[j]])
                j += 1
            member[d] = frozenset(s)
    # hacia atrás antes de la primera ancla
    a0 = revs[years[0]]
    s = set(snaps[years[0]].ticker)
    prior = list(ch[ch.date <= a0].sort_values("date", ascending=False).itertuples())
    j = 0
    for d in reversed(days[days <= a0]):
        member[d] = frozenset(s)   # composición vigente el día d
        while j < len(prior) and prior[j].date >= d:
            _apply(s, [prior[j]], forward=False)
            j += 1
    # coherencia con instantáneas: anclas consecutivas (hacia delante) y listas no plausibles (contención)
    coh = {}
    for k, y in enumerate(years[:-1]):
        d = days[days < revs[years[k + 1]]][-1]
        got, nxt = set(member[d]), set(snaps[years[k + 1]].ticker)
        miss, extra = sorted(nxt - got), sorted(got - nxt)
        nn = dict(zip(snaps[years[k + 1]].ticker, snaps[years[k + 1]].name))
        pairs = rename_pairs([(t, nn.get(t, "")) for t in miss], [(t, names.get(t, "")) for t in extra])
        coh[str(y)] = {"to": str(revs[years[k + 1]].date()), "reconstructed": len(got), "snapshot_next": len(nxt),
                       "missing_vs_next": miss, "extra_vs_next": extra, "rename_pairs": pairs,
                       "jaccard": round(len(got & nxt) / len(got | nxt), 4),
                       "jaccard_company": round((len(got & nxt) + len(pairs)) / (len(got | nxt) - len(pairs)), 4)}
    contain = {}
    for y, sbad in bad.items():
        dd = days[days <= revs[y]]
        if not len(dd):
            continue
        got, lst = set(member[dd[-1]]), set(sbad.ticker)
        contain[str(y)] = {"list_size": len(lst), "reconstructed": len(got),
                           "reconstructed_in_list_pct": round(100 * len(got & lst) / max(1, len(got)), 1),
                           "not_in_list": sorted(got - lst)}
    # intervalos
    rows = []
    allt = set().union(*member.values())
    for t in sorted(allt):
        inside = [d for d in days if t in member[d]]
        if not inside:
            continue
        s0 = prev = inside[0]
        for d in inside[1:]:
            if (d - prev).days > 5:
                rows.append((t, s0, prev))
                s0 = d
            prev = d
        rows.append((t, s0, prev))
    m = pd.DataFrame([{"index": idx, "ticker": t, "name": names.get(t, ""), "sector_wiki": sectors.get(t, ""),
                       "start": a.date().isoformat(),
                       "end": None if b == days[-1] else b.date().isoformat()} for t, a, b in rows])
    q = {"anchor_snapshots": {str(y): len(snaps[y]) for y in years},
         "rejected_snapshots_size": {str(y): len(v) for y, v in bad.items()},
         "changes_rows": int(len(ch)), "changes_first": str(ch.date.min().date()), "coherence": coh,
         "containment_rejected": contain,
         "mean_jaccard": round(sum(v["jaccard"] for v in coh.values()) / max(1, len(coh)), 4),
         "min_jaccard": min((v["jaccard"] for v in coh.values()), default=None),
         "mean_jaccard_company": round(sum(v["jaccard_company"] for v in coh.values()) / max(1, len(coh)), 4),
         "min_jaccard_company": min((v["jaccard_company"] for v in coh.values()), default=None),
         "daily_size_min_max": [min(len(v) for v in member.values()), max(len(v) for v in member.values())]}
    return m, ch, q


def main():
    allm, allc, qual = [], [], {}
    for idx in ("sp500", "sp400", "sp600"):
        m, ch, q = build(idx)
        allm.append(m)
        allc.append(ch)
        qual[idx] = q
        print(idx, "intervalos", len(m), "tickers", m.ticker.nunique(), "jaccard medio", q["mean_jaccard"],
              "mínimo", q["min_jaccard"], "anclas", list(q["anchor_snapshots"]))
    pd.concat(allm).to_csv(C.PUB / "membership.csv", index=False)
    pd.concat(allc).to_csv(C.PUB / "changes.csv", index=False)
    json.dump(qual, open(C.PUB / "universe_quality.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
