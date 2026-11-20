"""Auditoría de identidad de las series del panel v4 (enmienda 1, 2026-11-20). Solo lectura: no modifica nada.

Origen: en la tanda 1 aparecieron retornos imposibles (contrasplits sin aplicar) y series en las que el ticker pasa de
una empresa a otra en una escisión (AAN, ARNC, DLPH). Esta auditoría busca esos problemas en todas las series con días
utilizables, con reglas generales:

  A. datos_previos_al_cik: la serie tiene días en el panel anteriores a la primera presentación de su CIK en la SEC
     (más de 30 días antes): ese tramo es de otra entidad (normalmente la matriz de una escisión).
  B. varios_nombres: el campo de nombres lista entidades distintas («Arconic Corp. | Arconic Inc.»). Informativo.
  C. quiebra_atravesada: el CIK presentó un 8-K con el ítem 1.03 (quiebra) y la serie sigue cotizando más de 60
     días después sin terminar: posible mezcla de acciones antiguas (canceladas) y nuevas con el mismo ticker.
  D. cik_conflicto / cik_ausente.

Salida: data/identity_audit_v1.csv (una fila por clave y bandera) y resumen por consola.
"""
import json

import numpy as np
import pandas as pd

import fn_config as C

SUB = C.SEC / "submissions"


def sec_info(cik):
    f = SUB / f"{int(cik)}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    if "filings" not in d:
        return None
    r = d["filings"]["recent"]
    first = min([x["filingFrom"] for x in d["filings"].get("files", [])] + r["filingDate"]) if r["filingDate"] else None
    b13 = [fd for fd, fm, it in zip(r["filingDate"], r["form"], r.get("items", [""] * len(r["form"])))
           if fm.startswith("8-K") and "1.03" in (it or "")]
    return {"name": d.get("name"), "former": [x["name"] for x in d.get("formerNames", [])], "first_filing": first,
            "item103": sorted(b13), "recent_from": min(r["filingDate"]) if r["filingDate"] else None}


def main():
    comp = pd.read_csv(C.WORK / "companies_v4.csv", dtype={"cik": str})
    p = pd.read_parquet(C.WORK / "panel_v4.parquet", columns=["company", "key", "date", "usable"])
    span = p.groupby("key").agg(company=("company", "first"), d0=("date", "min"), d1=("date", "max"),
                                use0=("date", lambda s: None), n_use=("usable", "sum"))
    span["use0"] = p[p.usable].groupby("key").date.min()
    span["use1"] = p[p.usable].groupby("key").date.max()
    comp = comp.set_index("key")
    out = []
    for k, s in span.iterrows():
        if s.n_use == 0:
            continue
        r = comp.loc[k]
        cik = r.cik
        base = {"key": k, "company": s.company, "names": r.names, "cik": cik, "panel_from": s.d0, "panel_to": s.d1,
                "usable_from": s.use0, "usable_to": s.use1, "terminated": r.terminated}
        if isinstance(r.names, str) and "|" in r.names:
            parts = [x.strip() for x in r.names.split("|")]
            norm = {x.lower().replace(",", "").replace(".", "").replace(" inc", "").replace(" corporation", "")
                    .replace(" corp", "").replace(" co", "").strip() for x in parts}
            if len(norm) > 1:
                out.append({**base, "flag": "B_varios_nombres", "detail": r.names})
        if bool(r.cik_conflict):
            out.append({**base, "flag": "D_cik_conflicto", "detail": ""})
        if not isinstance(cik, str) or cik in ("", "nan"):
            out.append({**base, "flag": "D_cik_ausente", "detail": ""})
            continue
        info = sec_info(float(cik))
        if info is None:
            out.append({**base, "flag": "D_sin_submissions", "detail": ""})
            continue
        ff = info["first_filing"]
        if ff and s.d0 < (pd.Timestamp(ff) - pd.Timedelta(days=30)).strftime("%Y-%m-%d"):
            out.append({**base, "flag": "A_datos_previos_al_cik",
                        "detail": f"primera presentación {ff} ({info['name']}); panel desde {s.d0}"})
        for d in info["item103"]:
            if s.d0 <= d <= s.d1:
                cont = (pd.Timestamp(s.d1) - pd.Timestamp(d)).days
                if cont > 60:
                    out.append({**base, "flag": "C_quiebra_atravesada",
                                "detail": f"8-K 1.03 {d}; la serie sigue {cont} días; nombre SEC {info['name']}"})
                else:
                    out.append({**base, "flag": "C_quiebra_al_final",
                                "detail": f"8-K 1.03 {d}; serie termina {s.d1}"})
    a = pd.DataFrame(out)
    a.to_csv(C.PUB / "identity_audit_v1.csv", index=False)
    print(a.flag.value_counts())
    return a


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 300)
    pd.set_option("display.max_colwidth", 90)
    a = main()
    print(a[a.flag != "B_varios_nombres"][["key", "flag", "usable_from", "usable_to", "detail"]].to_string())
