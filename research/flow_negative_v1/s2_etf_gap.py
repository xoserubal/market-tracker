"""D2 (viabilidad) — ¿cuántas empresas de las carteras de 2015-2019 faltan en nuestro universo?

Son las que habría que identificar desde cero (nombre → CIK → ticker de la época → precios de Alpaca). Es el coste
principal de D2. Enlace por nombre con la misma función que la validación.
Salida: data/d2_gap.json y FLOWNEG_DATA_DIR/etf_holdings/gap_detail.json.
"""
import json

import pandas as pd

import fn_config as C
import s2_etf_lib as L
from s2_etf_validate import match

DATES = {"IJR": ["2015-03-31", "2016-03-31", "2017-03-31", "2018-03-31", "2019-03-31", "2019-09-30"],
         "IJH": ["2015-06-30", "2016-06-30", "2017-06-30", "2018-06-30", "2019-06-30", "2020-06-30"]}


def main():
    mem = pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False)
    cm = pd.read_csv(C.SEC / "cik_map.csv", dtype=str, keep_default_na=False)
    ref = {}
    for r in mem.itertuples():
        ref[f"m:{r.ticker}:{r.name}"] = r.name
    for r in cm.itertuples():
        if r.sec_name:
            ref[f"s:{r.ticker}:{r.sec_name}"] = r.sec_name
    inv = L.inventory()
    out, detail, all_missing = {}, {}, {}
    for f, ds in DATES.items():
        for d in ds:
            h = L.holdings(f, d, inv)
            if h is None:
                print("sin cartera", f, d)
                continue
            names = [r["name"] for r in h["rows"]]
            # aquí varios nombres de referencia pueden ser la misma empresa: no se exige unicidad del destino
            mt = match(names, ref)
            miss = [n for n, (k, t, s) in mt.items() if t == "sin_enlace"]
            amb = [n for n, (k, t, s) in mt.items() if t == "ambiguo"]
            out[f"{f} {d}"] = {"n": len(names), "linked": len(names) - len(miss) - len(amb), "ambiguous": len(amb),
                               "not_in_universe": len(miss)}
            detail[f"{f} {d}"] = {"not_in_universe": miss, "ambiguous": [(n, mt[n][0], mt[n][2]) for n in amb]}
            for n in miss:
                all_missing.setdefault(f, set()).add(n)
            print(f, d, out[f"{f} {d}"], flush=True)
    out["distinct_not_in_universe"] = {f: len(v) for f, v in all_missing.items()}
    json.dump(out, open(C.PUB / "d2_gap.json", "w"), indent=1)
    json.dump(detail | {"all_missing": {f: sorted(v) for f, v in all_missing.items()}},
              open(L.ETF / "gap_detail.json", "w"), indent=1)
    print(out["distinct_not_in_universe"])


if __name__ == "__main__":
    main()
