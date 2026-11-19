"""D2 (viabilidad) — nombres de la SEC para enlazar las posiciones de los ETF (que solo traen nombre) con un CIK.

1. Nombre actual y anteriores (con fechas) de cada CIK de nuestro universo: submissions JSON de EDGAR.
2. Listado completo de nombres de EDGAR (cik-lookup-data.txt): para identificar empresas que no están en el universo.
Todo fuera del repo (FLOWNEG_DATA_DIR/sec). Salida: sec/names_universe.csv (cik, nombre, desde, hasta).
"""
import json

import pandas as pd

import fn_config as C
import s2_etf_lib as L

SUB = C.SEC / "submissions"
SUB.mkdir(exist_ok=True)


def main():
    cm = pd.read_csv(C.SEC / "cik_map.csv", dtype=str, keep_default_na=False)
    ciks = sorted({c for c in cm.cik if c})
    rows = []
    for i, c in enumerate(ciks):
        f = SUB / f"{c}.json"
        if not f.exists():
            t = L.sec_get(f"https://data.sec.gov/submissions/CIK{int(c):010d}.json")
            if t is None:
                continue
            f.write_text(t, encoding="utf-8")
        d = json.load(open(f, encoding="utf-8"))
        rows.append({"cik": c, "name": d.get("name", ""), "from": "", "to": "", "kind": "current",
                     "tickers": "|".join(d.get("tickers") or [])})
        for fn in d.get("formerNames") or []:
            rows.append({"cik": c, "name": fn.get("name", ""), "from": (fn.get("from") or "")[:10],
                         "to": (fn.get("to") or "")[:10], "kind": "former", "tickers": ""})
        if i % 200 == 0:
            print(i, len(ciks), flush=True)
    pd.DataFrame(rows).to_csv(C.SEC / "names_universe.csv", index=False)
    print("CIK", len(ciks), "nombres", len(rows))
    lk = C.SEC / "cik-lookup-data.txt"
    if not lk.exists():
        b = L.sec_get("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt", binary=True)
        if b:
            lk.write_bytes(b)
    print("cik-lookup", lk.exists() and lk.stat().st_size)


if __name__ == "__main__":
    main()
