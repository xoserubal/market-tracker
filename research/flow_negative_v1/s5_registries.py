"""Enmienda 1 — registros de corrección verificados (§2, §3, §4).

Escribe:
  data/corr1_splits.csv    contrasplits documentados en la SEC (factor = acciones antiguas por cada nueva)
  data/corr1_jumps.csv     clasificación de cada salto de data/corr1_jumps_evidence.csv (s5_jumps.py)
  data/corr1_spinoffs.csv  escisiones dentro de ventanas de desarrollo, con proporción y fuente

Reglas de clasificación de saltos (enmienda §3), en este orden:
  1. Registro de operaciones corporativas verificadas (contrasplit, escisión, distribución, identidad) → corporate_*.
  2. Yahoo confirma el retorno del día (|Δ ln| < 0,10) → market (evidencia: yahoo).
  3. El sector se mueve en el mismo sentido al menos 1/3 del salto, con >= 5 pares → market (evidencia: sector).
  4. Volumen del día >= 5 veces la mediana de 20 sesiones (hubo negociación real) → market (evidencia: volumen; y
     8-K en ±3 días si los hay).
  5. Lo demás → indeterminate. La reversión en <= 3 sesiones se anota, pero no decide.
  Fuera de alcance (out_of_scope): saltos anteriores a 2016-01-01 o en series cuyos días utilizables empiezan más de
  100 semanas después (no tocan ni el Flow ni ningún resultado de desarrollo).
"""
import numpy as np
import pandas as pd

import fn_config as C

SEC = "https://www.sec.gov/Archives/edgar/data/"

SPLITS = [
    # key, primera sesión ajustada, factor, fuente
    ("CHK__2025-01-09__e0", "2020-04-15", 200, SEC + "895126/000089512620000096/ex9912020-04x13prreres.htm"),
    ("EXE__none__e0", "2020-04-15", 200, "duplicado de CHK e0 (misma serie)"),
    ("HPR__2020-06-19x__e0", "2020-10-30", 50, SEC + "1725526/000172552620000107/hpr-10302020xex991.htm"),
    ("PEI__2020-09-18x__e0", "2022-06-16", 15, SEC + "77281/000119312522178764/d364386dex31.htm"),
    ("CSR__none__e0", "2018-12-28", 10, SEC + "798359/000162828018015189/pressrelease.htm"),
    ("OVV__none__e0", "2020-01-27", 5, SEC + "1157806/000119312520014829/d869732dex9911.htm"),
    ("OPI__2023-09-15x__e0", "2019-01-02", 4, SEC + "1197909/000110465919000234/a4.xml"),
    ("OPCH__none__e0", "2020-02-03", 4, SEC + "1014739/000110465920003476/tv535800-def14c.htm"),
    ("VAL__none__e0", "2019-04-11", 4, SEC + "314808/000031480820000066/val-3312020x10q.htm"),
    ("LCI__2021-06-03x__e0", "2023-02-07", 4, SEC + "57725/000110465923011491/tm235668d1_8k.htm"),
    ("DD__none__e0", "2019-06-03", 3, SEC + "1666700/000166670019000023/dupontreversestocksplit.htm"),
    ("SITC__2025-12-19x__e0", "2018-05-21", 2, SEC + "894315/000119312518157546/d494725d8k.htm + Form 4 1299469 (2018-06-08)"),
    ("VTOL__none__e0", "2020-06-12", 3, SEC + "1525221/000114036120012860/form8k.htm"),
    ("RRD__2016-09-26x__e0", "2016-10-03", 3, SEC + "29669/000119312516709698/d261077d8k.htm (tras escindir LKSD y DFIN)"),
]

# operaciones corporativas de los saltos (clave, fecha) → (clase, detalle)
CORPORATE = {
    ("AAN__2023-09-15x__e0", "2020-12-01"): ("corporate_identity", "Aaron's Inc. → PROG; AAN pasa a la escindida"),
    ("ARNC__2023-08-18__e0", "2020-04-01"): ("corporate_identity", "Arconic Inc. → Howmet; ARNC pasa a la escindida"),
    ("DLPH__2020-10-06__e0", "2017-12-05"): ("corporate_identity", "Delphi Automotive → Aptiv; DLPH escindida"),
    ("SNX__none__e0", "2020-12-01"): ("corporate_spinoff", "escisión de Concentrix (CNXC)"),
    ("TNL__none__e0", "2018-06-01"): ("corporate_spinoff", "escisión de Wyndham Hotels (WH)"),
    ("TRN__none__e0", "2018-11-01"): ("corporate_spinoff", "escisión de Arcosa (ACA)"),
    ("KAR__2021-12-01x__e0", "2019-06-28"): ("corporate_spinoff", "escisión de IAA"),
    ("SRC__2024-01-22__e0", "2018-06-01"): ("corporate_spinoff", "escisión de SMTA"),
    ("CNX__2016-03-03x__e0", "2017-11-29"): ("corporate_spinoff", "escisión de CONSOL Coal (CEIX)"),
    ("CKH__2021-04-09__e0", "2017-06-02"): ("corporate_spinoff", "escisión de SEACOR Marine"),
    ("YHOO__2017-06-16x__e0", "2019-09-24"): ("corporate_distribution", "Altaba: distribución de liquidación en efectivo"),
    ("GRUB__2021-06-14x__e0", "2021-06-15"): ("corporate_merger", "Grubhub comprada por Just Eat Takeaway"),
    ("IAC__none__e0", "2020-07-01"): ("corporate_identity", "separación IAC / Match"),
    ("CIVI__2026-01-29__e0", "2017-05-01"): ("corporate_reorganization", "salida de quiebra de Bonanza Creek"),
    ("CRK__none__e0", "2016-08-01"): ("corporate_split_unverified", "Comstock, contrasplit 2016 (fuera de alcance)"),
}


def relevant(row):
    if row.date < "2016-01-01":
        return False
    uf = pd.Timestamp(row.usable_from)
    return pd.Timestamp(row.date) >= uf - pd.Timedelta(weeks=100)


def classify(row, split_keys):
    key = (row.key, row.date)
    if (row.key, row.date) in split_keys:
        return "corporate_split", "contrasplit verificado en la SEC (corr1_splits.csv)"
    if key in CORPORATE:
        return CORPORATE[key]
    if row.spinoff_listed:
        return "corporate_spinoff", "escisión en la lista de Alpaca o la curada"
    la = np.log(row.alpaca_ratio)
    if abs(la) < 0.05:
        return "no_price_effect", "split rechazado sin efecto en el precio"
    if row.yahoo_ratio == row.yahoo_ratio and abs(la - np.log(row.yahoo_ratio)) < 0.10:
        return "market", "Yahoo confirma el retorno del día"
    if row.sector_med_ret == row.sector_med_ret and np.sign(row.sector_med_ret) == np.sign(la) \
            and abs(np.log1p(row.sector_med_ret)) >= abs(la) / 3:
        return "market", f"sector el mismo día {row.sector_med_ret:+.1%}"
    if row.vol_day_x >= 5:
        ev = f"volumen x{row.vol_day_x:.0f}"
        if isinstance(row.sec_8k_pm3d, str) and row.sec_8k_pm3d:
            ev += f"; 8-K {row.sec_8k_pm3d}"
        return "market", ev
    if row.yahoo_ratio == row.yahoo_ratio:
        return "indeterminate", f"Yahoo no coincide (x{row.yahoo_ratio:.3f}) y no hay operación documentada"
    return "indeterminate", (f"sin segunda fuente; volumen x{row.vol_day_x:.1f}; sector {row.sector_med_ret:+.1%}; "
                             f"reversión 3 sesiones {row.revert_3d_share:.0%} (solo auditoría)")


def main():
    sp = pd.DataFrame(SPLITS, columns=["key", "bar_date", "factor", "source"])
    sp.to_csv(C.PUB / "corr1_splits.csv", index=False)
    split_keys = set(zip(sp.key, sp.bar_date))
    e = pd.read_csv(C.PUB / "corr1_jumps_evidence.csv")
    out = []
    for r in e.itertuples():
        cls, ev = classify(r, split_keys)
        out.append({"key": r.key, "date": r.date, "alpaca_ratio": round(r.alpaca_ratio, 4), "class": cls,
                    "evidence": ev, "in_scope": relevant(r)})
    j = pd.DataFrame(out)
    j.to_csv(C.PUB / "corr1_jumps.csv", index=False)
    print(pd.crosstab(j["class"], j.in_scope))
    return j


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    pd.set_option("display.max_colwidth", 120)
    j = main()
    print(j[j.in_scope & j["class"].isin(["indeterminate", "corporate_split", "corporate_spinoff",
                                          "corporate_identity", "corporate_distribution"])].to_string())
