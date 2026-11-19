"""D2 (viabilidad) — inventario de presentaciones con cartera completa y su fecha exacta de cartera.

Lee solo la página índice de cada presentación (no descarga los documentos).
Salida: FLOWNEG_DATA_DIR/etf_holdings/inventory.csv y data/d2_inventory.json (resumen por fondo y año).
"""
import json
from collections import defaultdict

import pandas as pd

import fn_config as C
import s2_etf_lib as L

FUNDS = ["IJR", "VIOO", "SLY", "IJH", "IVOO"]
TYPES = ("N-Q", "N-CSR", "N-CSRS", "NPORT-P", "N-Q/A", "N-CSR/A", "N-CSRS/A")


def main():
    idx = L.load_index()
    out_f = L.ETF / "inventory.csv"
    done = pd.read_csv(out_f, dtype=str, keep_default_na=False) if out_f.exists() else pd.DataFrame(columns=["fund", "acc"])
    rows = done.to_dict("records")
    seen = set(zip(done.fund, done.acc))
    for tk in FUNDS:
        for f in idx[tk]:
            if f["type"] not in TYPES or not ("2014-06" <= f["filed"] <= "2024-03") or (tk, f["acc"]) in seen:
                continue
            per, docs = L.filing_docs(f["href"])
            main = sorted([d for d in docs if d[1].startswith(("N-Q", "N-CSR"))], key=lambda d: -d[2])
            xml = [d for d in docs if d[0].endswith(".xml") and "/xsl" not in d[0]]
            doc = (xml[0] if f["type"].startswith("NPORT") and xml else (main[0] if main else (None, None, 0)))
            rows.append({"fund": tk, "index": L.INDEX_OF[tk], "type": f["type"], "filed": f["filed"],
                         "period": per or "", "acc": f["acc"], "doc_url": doc[0] or "", "doc_bytes": doc[2]})
            seen.add((tk, f["acc"]))
        pd.DataFrame(rows).to_csv(out_f, index=False)
        print(tk, sum(1 for r in rows if r["fund"] == tk), flush=True)
    inv = pd.DataFrame(rows)
    inv = inv[~inv.type.str.endswith("/A")]
    summ = {}
    for (tk, y), g in inv.groupby([inv.fund, inv.period.str[:4]]):
        summ.setdefault(tk, {})[y] = sorted(g.period.tolist())
    json.dump(summ, open(C.PUB / "d2_inventory.json", "w"), indent=1)
    for tk, v in summ.items():
        print(tk, {y: len(p) for y, p in v.items()})


if __name__ == "__main__":
    main()
