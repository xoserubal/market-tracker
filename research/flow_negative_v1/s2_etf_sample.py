"""D2 (viabilidad) — extracción de una muestra de documentos y comprobación de que salen completos.

Por fondo: un documento HTML de 2017, otro de 2018 y un NPORT-P de finales de 2019 / 2020.
Salida: FLOWNEG_DATA_DIR/etf_holdings/sample/<fondo>_<fecha>.json y data/d2_sample_extraction.json (agregados).
"""
import json
import sys

import s2_etf_lib as L

FUNDS = ["IJR", "SLY", "VIOO", "IJH", "SPMD", "IVOO"]
OUT = L.ETF / "sample"
OUT.mkdir(exist_ok=True)


def pick(idx, tk):
    rows = idx[tk]
    sel = []
    for y in ("2017", "2018"):
        c = [r for r in rows if r["filed"].startswith(y) and r["type"] in ("N-Q", "N-CSR", "N-CSRS")]
        if c:
            sel.append(c[0])
    c = [r for r in rows if r["type"] == "NPORT-P" and "2019-11" <= r["filed"] <= "2020-06"]
    if c:
        sel.append(c[0])
    return sel


def run_one(tk, f):
    per, docs = L.filing_docs(f["href"])
    if f["type"] == "NPORT-P":
        xml = [d for d in docs if d[0].endswith(".xml") and "/xsl" not in d[0]]
        if not xml:
            return {"error": "sin XML"}
        t = L.cached(xml[0][0], f"{tk}_{f['acc']}.xml")
        rep, inv = L.parse_nport(t)
        eq = [r for r in inv if r["asset_cat"] == "EC"]
        res = {"type": "NPORT-P", "period": rep, "n_all": len(inv), "n_equity": len(eq),
               "with_cusip": sum(1 for r in eq if r["cusip"] and r["cusip"] != "000000000"),
               "with_isin": sum(1 for r in eq if r["isin"]), "with_ticker": sum(1 for r in eq if r["ticker"]),
               "value_equity": sum(r["value"] for r in eq)}
        json.dump(inv, open(OUT / f"{tk}_{rep}.json", "w"), indent=0)
        return res
    main = sorted([d for d in docs if d[1].startswith(("N-Q", "N-CSR"))], key=lambda d: -d[2])
    if not main:
        return {"error": "sin documento principal"}
    t = L.cached(main[0][0], f"{tk}_{f['acc']}.htm")
    p = L.parse_html_holdings(t, tk)
    if p is None:
        return {"type": f["type"], "period": per, "error": "no se encuentra el fondo en el documento"}
    rows = p["rows"]
    json.dump(rows, open(OUT / f"{tk}_{per}.json", "w"), indent=0)
    return {"type": f["type"], "period": per, "n": len(rows), "parsed_total": round(p["parsed_total"]),
            "reported_total": p["reported_total"],
            "match_total": (p["reported_total"] is not None and abs(p["parsed_total"] - p["reported_total"]) < 2)}


def main():
    idx = L.load_index()
    out = {}
    for tk in (sys.argv[1:] or FUNDS):
        for f in pick(idx, tk):
            r = run_one(tk, f)
            r["filed"] = f["filed"]
            out[f"{tk} {f['filed']}"] = r
            print(tk, f["filed"], r, flush=True)
    json.dump(out, open(C.PUB / "d2_sample_extraction.json", "w"), indent=1)


if __name__ == "__main__":
    import fn_config as C
    main()
