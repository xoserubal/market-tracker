"""Enmienda 1 §8 — registro de CIK verificado (corr1_cik.csv).

Cada fila asigna a una serie (clave) el CIK válido en un tramo de fechas [desde, hasta]:
  - correccion:  el CIK de companies_v4 era de otra entidad o faltaba;
  - predecesor:  el CIK actual es de un holding/entidad creada después; antes se usa el de la entidad anterior,
                 solo con continuidad legal y económica documentada (canje fijo, normalmente 1:1);
  - sin_cik:     se quita el CIK (la serie, en ese tramo, no es de la entidad del CIK) para resolver un conflicto.
`share_factor`: acciones de la entidad posterior por acción de la anterior (1 = canje 1:1). Con factor 1 las acciones
del predecesor se usan tal cual.

Verificación automática (columnas `sec_name`, `shares_filings`, `evidence`):
  - nombre registrado en la SEC para ese CIK;
  - número de presentaciones de acciones (dei:EntityCommonStockSharesOutstanding) dentro del tramo (se descargan si
    faltan);
  - para predecesores: frase de la SEC sobre la sucesión (búsqueda de texto completo), si se encuentra.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

import fn_config as C
from s0_sec import fetch_shares

UA = {"User-Agent": "research-script contact@example.com"}
END = "2026-11-13"

# key, desde, hasta, cik, tipo, factor, nota
ROWS = [
    # --- correcciones (CIK ausente o de otra entidad)
    ("CB__none__e0", "2015-01-01", END, 896159, "correccion", 1, "Chubb Ltd (antes ACE Ltd); CIK ausente"),
    ("FLG__none__e0", "2015-01-01", END, 910073, "correccion", 1, "New York Community Bancorp → Flagstar Financial"),
    ("MYL__2021-01-08__e0", "2015-01-01", END, 1623613, "correccion", 1, "Mylan N.V."),
    ("DD__none__e0", "2015-01-01", END, 1666700, "correccion", 1, "DowDuPont → DuPont de Nemours"),
    ("BBT__2020-01-10__e0", "2015-01-01", END, 92230, "correccion", 1, "BB&T Corp (luego Truist)"),
    ("GCI__2023-06-16x__e0", "2019-11-20", END, 1579684, "correccion", 1,
     "Gannett Co., Inc. (antes New Media); tramo anterior cortado por identidad"),
    ("NWN__none__e0", "2018-10-01", END, 1733998, "correccion", 1, "Northwest Natural Holding Co"),
    ("NWN__none__e0", "2015-01-01", "2018-09-30", 73020, "predecesor", 1, "Northwest Natural Gas Co (holding 1:1, 2018)"),
    ("STOR__2023-02-03__e0", "2015-01-01", END, 1538990, "correccion", 1, "STORE Capital Corp"),
    ("OA__2018-06-08__e0", "2015-01-01", END, 866121, "correccion", 1, "Orbital ATK (antes Alliant Techsystems)"),
    ("LNCE__2018-03-23__e0", "2015-01-01", END, 57528, "correccion", 1, "Snyder's-Lance"),
    ("ALSK__2024-01-12__e0", "2015-01-01", END, 1089511, "correccion", 1,
     "Alaska Communications (tenía el CIK de Alaska Air: conflicto con ALK)"),
    ("DOC__2024-02-29__e0", "2015-01-01", END, 1574540, "correccion", 1,
     "Physicians Realty Trust (tenía el CIK de Healthpeak)"),
    ("WTW__2019-12-27__e0", "2015-01-01", END, 105319, "correccion", 1,
     "Weight Watchers (tenía el CIK de Willis Towers Watson)"),
    ("AA__none__e0", "2016-11-01", END, 1675149, "correccion", 1, "Alcoa Corp (tenía el CIK de Alcoa Inc./Howmet)"),
    ("FI__2026-01-14__e0", "2015-01-01", END, 1575828, "correccion", 1,
     "Frank's International N.V. (el ticker FI hasta 2021; tenía el CIK de Fiserv)"),
    ("FG__none__e0", "2015-01-01", END, 1668428, "correccion", 1, "FGL Holdings (tenía el CIK de F&G Annuities, 2022)"),
    ("IIVI__2023-01-05x__e1", "2015-01-01", END, 0, "sin_cik", 1, "tramo 2023 que no es II-VI: conflicto con COHR"),
    ("ROCC__2023-06-22__e0", "2015-01-01", "2021-10-05", 0, "sin_cik", 1,
     "ROCC antes de oct-2021 no es Penn Virginia: conflicto con PVAC"),
    ("TYC__2016-09-05__e0", "2015-01-01", END, 0, "sin_cik", 1,
     "Tyco antes de 2016 (precios distintos de JCI): conflicto con JCI"),
    # --- Safehold / iStar (fusión 2023: iStar sobrevive y se renombra Safehold; SAFE antiguos 1:1)
    ("SAFE__none__e0", "2015-01-01", "2023-03-31", 1688852, "predecesor", 1, "Safehold antigua (canje 1:1 en 2023)"),
    ("SAFE__none__e0", "2023-04-01", END, 1095651, "correccion", 1, "Safehold (antes iStar)"),
    # --- predecesores por reorganización de holding (canje 1:1)
    ("APA__none__e0", "2015-01-01", "2021-02-28", 6769, "predecesor", 1, "Apache Corp → APA Corp (holding 1:1, mar-2021)"),
    ("BLK__none__e0", "2015-01-01", "2024-09-30", 1364742, "predecesor", 1, "BlackRock Inc. → nuevo holding (1:1, oct-2024)"),
    ("CLB__2026-06-30x__e0", "2015-01-01", "2023-05-01", 1000229, "predecesor", 1,
     "Core Laboratories N.V. → Core Laboratories Inc. (1:1, 2023)"),
    ("DINO__none__e0", "2015-01-01", "2022-03-13", 48039, "predecesor", 1, "HollyFrontier → HF Sinclair (1:1, mar-2022)"),
    ("XOM__none__e0", "2015-01-01", "2026-06-30", 34088, "predecesor", 1, "Exxon Mobil Corp → ExxonMobil Holdings (1:1, 2026)"),
    ("XRX__2025-09-19x__e0", "2015-01-01", "2019-07-31", 108772, "predecesor", 1, "Xerox Corp → Xerox Holdings (1:1, 2019)"),
    ("STE__none__e0", "2015-01-01", "2019-03-27", 1624899, "predecesor", 1, "STERIS plc (UK) → STERIS plc (Irlanda) (1:1, 2019)"),
    ("DIS__none__e0", "2015-01-01", "2019-03-19", 1001039, "predecesor", 1, "Walt Disney Co → TWDC Holdco (1:1, mar-2019)"),
    ("CI__none__e0", "2015-01-01", "2018-12-19", 701221, "predecesor", 1, "Cigna Corp → nuevo holding (1:1, dic-2018)"),
    ("QDEL__none__e0", "2015-01-01", "2022-05-26", 353569, "predecesor", 1, "Quidel → QuidelOrtho (1:1, may-2022)"),
    ("AVGO__none__e0", "2015-01-01", "2018-04-03", 1649338, "predecesor", 1, "Broadcom Ltd → Broadcom Inc. (1:1, abr-2018)"),
    ("SW__none__e0", "2015-01-01", "2018-11-01", 1636023, "predecesor", 1, "WestRock (2015) → WestRock (2018, 1:1)"),
    ("SW__none__e0", "2018-11-02", "2024-07-05", 1732845, "predecesor", 1,
     "WestRock (2018); en jul-2024 1 SW + 5 $ por acción (efectivo: evento, fuera del desarrollo)"),
    ("UNIT__none__e0", "2015-01-01", "2025-07-31", 1620280, "predecesor", 1,
     "Uniti Group antigua; en ago-2025 0,6029 nuevas por acción (canje: evento, fuera del desarrollo)"),
    ("TKO__none__e0", "2015-01-01", "2023-09-11", 1091907, "predecesor", 1, "WWE → TKO (1 TKO clase A por acción WWE, sep-2023)"),
    # --- identidad (§5): la parte anterior al corte se asigna en el registro de identidad; aquí los CIK de cada tramo
    ("ARNC__2023-08-18__e0", "2020-04-01", END, 1790982, "correccion", 1, "Arconic Corp. (escindida)"),
    ("AAN__2023-09-15x__e0", "2020-12-01", END, 1821393, "correccion", 1, "The Aaron's Company (escindida)"),
    ("PRG__none__e0", "2015-01-01", "2020-10-15", 706688, "predecesor", 1, "Aaron's Inc. → Aaron's Holdings/PROG (1:1, 2020)"),
    ("DLPH__2020-10-06__e0", "2017-12-05", END, 1707092, "correccion", 1, "Delphi Technologies PLC (escindida)"),
    ("CR__none__e0", "2023-04-04", END, 1944013, "correccion", 1, "Crane Company (escindida, 2023)"),
    ("FOXA__none__e0", "2019-03-19", END, 1754301, "correccion", 1, "Fox Corporation"),
]


def get(url):
    time.sleep(0.15)
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()


def sec_name(cik):
    f = C.SEC / "submissions" / f"{cik}.json"
    if not f.exists():
        try:
            f.write_bytes(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
        except Exception:
            return None
    d = json.loads(f.read_text(encoding="utf-8"))
    return d.get("name")


def shares_in(cik, a, b):
    f = C.SEC / "shares" / f"{cik}.json"
    if not f.exists():
        fetch_shares([str(cik)])
    s = pd.DataFrame(json.loads(f.read_text()))
    if s.empty or "filed" not in s:
        return 0
    return int(((s.filed >= a) & (s.filed <= b)).sum())


def successor_evidence(cik_new_key, d):
    """Frase de sucesión en presentaciones de la entidad posterior cerca de la fecha del cambio."""
    t0 = (pd.Timestamp(d) - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    t1 = (pd.Timestamp(d) + pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    for q in ['"successor issuer"', '"one share of" "common stock" "holding company"']:
        u = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(
            {"q": q, "ciks": f"{cik_new_key:010d}", "dateRange": "custom", "startdt": t0, "enddt": t1})
        try:
            hits = json.loads(get(u)).get("hits", {}).get("hits", [])
        except Exception:
            continue
        if hits:
            h = hits[0]["_source"]
            return f"{q} — {h.get('form')} {h.get('file_date')} ({hits[0]['_id']})"
    return ""


def main():
    comp = pd.read_csv(C.WORK / "companies_v4.csv", dtype={"cik": str}).drop_duplicates("key").set_index("key")
    out = []
    for key, a, b, cik, typ, fac, note in ROWS:
        row = {"key": key, "from": a, "to": b, "cik": cik, "type": typ, "share_factor": fac, "note": note,
               "old_cik": comp.cik.get(key, "") if key in comp.index else "NO_KEY"}
        if cik:
            row["sec_name"] = sec_name(cik)
            row["shares_filings"] = shares_in(cik, a, b)
        if typ == "predecesor":
            # cik actual de la serie (entidad posterior) para buscar la frase de sucesión
            cur = comp.cik.get(key, "")
            nxt = [r for r in ROWS if r[0] == key and r[1] > a and r[3]]
            new = nxt[0][3] if nxt else (int(float(cur)) if isinstance(cur, str) and cur not in ("", "nan") else 0)
            row["evidence"] = successor_evidence(new, b) if new else ""
        out.append(row)
        print(key, cik, row.get("sec_name"), row.get("shares_filings"), row.get("evidence", "")[:120], flush=True)
    pd.DataFrame(out).to_csv(C.PUB / "corr1_cik.csv", index=False)


if __name__ == "__main__":
    main()
