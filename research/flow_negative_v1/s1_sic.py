"""Etapa 0 (v3) — sector para las empresas sin sector GICS de Wikipedia, con el código SIC de la SEC.

Solo se usa una correspondencia SIC→GICS cuando es inequívoca. Los códigos que encajan en más de un sector GICS
(edición, maquinaria diversa, mayoristas, tiendas de descuento, «servicios de internet» 7370, instrumentos de
laboratorio, investigación comercial...) quedan como «ambiguo» y la empresa sin sector: se analiza frente al mercado
y a la muestra comparable, no frente a un sector inventado.

Reglas por orden: primero el código de 4 dígitos, después el de 3, después el de 2. La tabla está en RULES.
Salidas: sec/submissions/<cik>.json (fuera del repo), data/sic_gics_rules.csv y data/sic_sector_by_cik.csv.
"""
import json

import pandas as pd

import fn_config as C
from s0_sec import sec_get

SUB = C.SEC / "submissions"
SUB.mkdir(exist_ok=True)

A = "ambiguo"
RULES = {
    # 4 dígitos
    "1531": "Consumer Discretionary", "2834": "Health Care", "2835": "Health Care", "2836": "Health Care",
    "2833": "Health Care", "5122": "Health Care", "5047": "Health Care", "5171": "Energy", "5172": "Energy",
    "5411": "Consumer Staples", "5912": "Consumer Staples", "5331": A, "6770": A, "6798": "Real Estate",
    "7370": A, "7371": "Information Technology", "7372": "Information Technology",
    "7373": "Information Technology", "7374": "Information Technology", "7377": "Information Technology",
    "8731": A, "4955": "Industrials", "4953": "Industrials",
    # 3 dígitos
    "283": "Health Care", "284": "Consumer Staples", "357": "Information Technology",
    "366": "Information Technology", "367": "Information Technology", "365": "Consumer Discretionary",
    "363": "Consumer Discretionary", "369": A, "371": "Consumer Discretionary", "372": "Industrials",
    "373": "Industrials", "374": "Industrials", "375": "Consumer Discretionary", "376": "Industrials",
    "384": "Health Care", "382": A, "381": "Industrials", "386": A, "394": "Consumer Discretionary",
    "481": "Communication Services", "482": "Communication Services", "483": "Communication Services",
    "484": "Communication Services", "489": "Communication Services", "491": "Utilities", "492": "Utilities",
    "493": "Utilities", "494": "Utilities", "495": "Industrials", "496": "Utilities", "497": "Utilities",
    "737": A, "873": A, "302": "Consumer Discretionary",
    # 2 dígitos
    "01": "Consumer Staples", "02": "Consumer Staples", "10": "Materials", "12": "Energy", "13": "Energy",
    "14": "Materials", "15": "Industrials", "16": "Industrials", "17": "Industrials",
    "20": "Consumer Staples", "21": "Consumer Staples", "22": "Consumer Discretionary",
    "23": "Consumer Discretionary", "24": "Materials", "25": "Consumer Discretionary", "26": "Materials", "27": A,
    "28": "Materials", "29": "Energy", "30": A, "31": "Consumer Discretionary", "32": "Materials",
    "33": "Materials", "34": "Industrials", "35": "Industrials", "36": "Industrials", "37": A, "38": A, "39": A,
    "40": "Industrials", "41": "Industrials", "42": "Industrials", "44": "Industrials", "45": "Industrials",
    "46": "Energy", "47": "Industrials", "48": "Communication Services", "49": A, "50": A, "51": A,
    "52": "Consumer Discretionary", "53": "Consumer Discretionary", "54": "Consumer Staples",
    "55": "Consumer Discretionary", "56": "Consumer Discretionary", "57": "Consumer Discretionary",
    "58": "Consumer Discretionary", "59": "Consumer Discretionary", "60": "Financials", "61": "Financials",
    "62": "Financials", "63": "Financials", "64": "Financials", "65": "Real Estate", "67": "Financials",
    "70": "Consumer Discretionary", "72": "Consumer Discretionary", "73": "Industrials",
    "75": "Consumer Discretionary", "78": "Communication Services", "79": "Consumer Discretionary",
    "80": "Health Care", "82": "Consumer Discretionary", "83": A, "87": "Industrials", "99": A,
}


def sic_to_gics(sic):
    sic = str(sic or "").strip()
    if not sic.isdigit():
        return "", "sin_sic"
    for n in (4, 3, 2):
        g = RULES.get(sic[:n])
        if g is not None:
            return ("", "ambiguo") if g == A else (g, f"sic{n}")
    return "", "sin_regla"


def fetch(cik):
    f = SUB / f"{cik}.json"
    if not f.exists():
        r = sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
        d = r.json() if r is not None else {}
        f.write_text(json.dumps({"sic": d.get("sic"), "sicDescription": d.get("sicDescription"),
                                 "name": d.get("name")}))
    return json.load(open(f))


def main():
    p = pd.read_parquet(C.WORK / "panel_v3.parquet", columns=["company", "cik", "sector"])
    need = sorted({c for c in p.loc[p.sector == "", "cik"] if c})
    out = []
    for cik in need:
        d = fetch(cik)
        g, how = sic_to_gics(d.get("sic"))
        out.append({"cik": cik, "sic": d.get("sic"), "sic_desc": d.get("sicDescription"), "sector_sic": g,
                    "method": how})
    o = pd.DataFrame(out)
    o.to_csv(C.PUB / "sic_sector_by_cik.csv", index=False)
    pd.DataFrame([{"sic_prefix": k, "gics_sector": v} for k, v in RULES.items()]).to_csv(
        C.PUB / "sic_gics_rules.csv", index=False)
    print(o.method.value_counts().to_dict())


if __name__ == "__main__":
    main()
