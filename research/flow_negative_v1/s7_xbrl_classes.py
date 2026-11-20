"""Enmienda 2 (piloto de acciones por clase): extrae del XBRL ORIGINAL de cada 10-K/10-Q las acciones en circulación
de portada (dei:EntityCommonStockSharesOutstanding) por clase de acción, con su fecha, y el símbolo de cada clase
cuando la portada lo etiqueta (dei:TradingSymbol, obligatorio desde 2019).

La API companyconcept de la SEC solo publica hechos sin dimensión; las empresas que informan por clase (eje
us-gaap:StatementClassOfStockAxis) aparecen allí vacías. Aquí se leen los documentos de cada presentación.

Salida (fuera del repo): sec/xbrl_classes/<cik>.json — lista de presentaciones con sus hechos por clase.
Uso: py -3 s7_xbrl_classes.py CIK [CIK ...]
"""
import json
import re
import sys
import xml.etree.ElementTree as ET

import fn_config as C
from s0_sec import sec_get

OUT = C.SEC / "xbrl_classes"
OUT.mkdir(parents=True, exist_ok=True)
FORMS = re.compile(r"^(10-K|10-Q|10-KT|10-QT)(/A)?$")
FROM = "2016-06-01"          # una presentación ≤ 400 días antes del primer día de desarrollo
SKIP = re.compile(r"(FilingSummary|_cal|_def|_lab|_pre|_ref)\.xml$|\.xsd$", re.I)


def filings_list(cik, frm=FROM, to="9999-12-31"):
    sub = C.SEC / "submissions" / f"{int(cik)}.json"
    js = json.loads(sub.read_text()) if sub.exists() else None
    if js is None:
        r = sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
        js = r.json() if r is not None else {}
    blocks = [js.get("filings", {}).get("recent", {})]
    for f in js.get("filings", {}).get("files", []):
        r = sec_get(f"https://data.sec.gov/submissions/{f['name']}")
        if r is not None:
            blocks.append(r.json())
    out = []
    for b in blocks:
        for acc, form, filed, rep in zip(b.get("accessionNumber", []), b.get("form", []), b.get("filingDate", []),
                                         b.get("reportDate", [])):
            if FORMS.match(form) and frm <= filed <= to:
                out.append({"acc": acc, "form": form, "filed": filed, "report": rep})
    return sorted({o["acc"]: o for o in out}.values(), key=lambda o: o["filed"])


def instance_url(cik, acc):
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
    r = sec_get(base + "/index.json")
    if r is None:
        return None
    items = [i["name"] for i in r.json().get("directory", {}).get("item", [])]
    xs = [n for n in items if n.lower().endswith(".xml") and not SKIP.search(n)]
    pref = [n for n in xs if n.lower().endswith("_htm.xml")] or xs
    return f"{base}/{pref[0]}" if pref else None


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_instance(xml_bytes):
    root = ET.fromstring(xml_bytes)
    ctx = {}
    for c in root.iter():
        if local(c.tag) != "context":
            continue
        dims, inst = {}, None
        for e in c.iter():
            t = local(e.tag)
            if t == "explicitMember":
                dims[e.get("dimension")] = (e.text or "").strip()
            elif t == "instant":
                inst = (e.text or "").strip()
            elif t == "endDate":
                inst = inst or (e.text or "").strip()
        ctx[c.get("id")] = (dims, inst)
    shares, symbols, titles = [], {}, {}
    for e in root.iter():
        t = local(e.tag)
        if t not in ("EntityCommonStockSharesOutstanding", "TradingSymbol", "Security12bTitle"):
            continue
        dims, inst = ctx.get(e.get("contextRef"), ({}, None))
        cls = dims.get("us-gaap:StatementClassOfStockAxis") or ("" if not dims else "|".join(f"{k}={v}" for k, v in dims.items()))
        txt = (e.text or "").strip()
        if t == "EntityCommonStockSharesOutstanding":
            try:
                v = float(txt)
            except ValueError:
                continue
            shares.append({"class": cls, "date": inst, "val": v, "other_dims": sorted(k for k in dims if k != "us-gaap:StatementClassOfStockAxis")})
        elif t == "TradingSymbol":
            symbols.setdefault(cls, set()).add(txt.upper())
        else:
            titles[cls] = txt
    return shares, {k: sorted(v) for k, v in symbols.items()}, titles


def run(cik, frm=FROM, to="9999-12-31"):
    cik = str(int(cik))
    f = OUT / f"{cik}.json"
    done = {r["acc"]: r for r in json.loads(f.read_text())} if f.exists() else {}
    for fl in filings_list(cik, max(frm, FROM), to):
        if fl["acc"] in done:
            continue
        url = instance_url(cik, fl["acc"])
        rec = dict(fl, instance=url)
        if url:
            r = sec_get(url)
            if r is not None:
                try:
                    rec["shares"], rec["symbols"], rec["titles"] = parse_instance(r.content)
                except ET.ParseError as e:
                    rec["error"] = f"parse: {e}"
            else:
                rec["error"] = "instance not fetched"
        else:
            rec["error"] = "no instance"
        done[fl["acc"]] = rec
        f.write_text(json.dumps(sorted(done.values(), key=lambda r: r["filed"]), indent=0))
    return sorted(done.values(), key=lambda r: r["filed"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["--list"]:
        # extracción general: work/enmienda2_multiclass_ciks.csv (cik, frm, d1) — ventana de días sin capitalización
        import pandas as pd
        L = pd.read_csv(C.WORK / "enmienda2_multiclass_ciks.csv", dtype=str)
        for i, r in enumerate(L.itertuples()):
            recs = run(r.cik, r.frm, r.d1)
            print(i + 1, len(L), r.cik, "presentaciones", len(recs), "con acciones",
                  sum(1 for x in recs if x.get("shares")), flush=True)
        sys.exit(0)
    for c in sys.argv[1:]:
        recs = run(c)
        ok = sum(1 for r in recs if r.get("shares"))
        print(c, "presentaciones", len(recs), "con acciones", ok, flush=True)
