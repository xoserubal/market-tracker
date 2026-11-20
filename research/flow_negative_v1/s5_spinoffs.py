"""Enmienda 1 §4 — registro de escisiones dentro de ventanas de desarrollo (data/corr1_spinoffs.csv).

`ratio` = acciones de la escindida por cada acción de la matriz, en las unidades del precio en bruto de la matriz el
día de la fecha ex (la primera sesión sin derecho). `child_key` = serie de la escindida en el universo; vacío = no hay
precio de la escindida → resultado no reconstruible (dato ausente, §7).
`family`: «spinoffs» (operación de la matriz) o «identity» (escisión que aparece al cortar una serie, §5).
"""
import pandas as pd

import fn_config as C

SEC = "https://www.sec.gov/Archives/edgar/data/"
ROWS = [
    # parent_key, ex_date, child_key, ratio, family, fuente
    ("PNR__none__e0", "2018-05-01", "NVT__none__e0", 1.0, "spinoffs",
     SEC + "77360/000007736018000018/pentairproformafinancials-.htm"),
    ("DOV__none__e0", "2018-05-09", "APY__2021-01-08__e0", 0.5, "spinoffs",
     SEC + "29905/000002990518000024/a201804278-kexhibit991.htm"),
    ("TNL__none__e0", "2018-06-01", "WH__none__e0", 1.0, "spinoffs",
     SEC + "1361658/000110465918032536/a18-13272_2ex99d1.htm"),
    ("HON__none__e0", "2018-10-01", "GTX__2020-09-24__e0", 0.1, "spinoffs",
     SEC + "773840/000093041318002815/c91982_8k.htm"),
    ("HON__none__e0", "2018-10-29", "REZI__none__e0", 1 / 6, "spinoffs",
     SEC + "773840/000119312518290912/d528228d8k.htm"),
    ("TRN__none__e0", "2018-11-01", "ACA__none__e0", 1 / 3, "spinoffs",
     SEC + "99780/000009978018000155/exh991pressrelease.htm"),
    ("EQT__none__e0", "2018-11-13", "ETRN__2024-07-19__e0", 0.8, "spinoffs",
     SEC + "33213/000104746918006903/a2236999zex-99_1.htm"),
    ("GE__none__e0", "2019-02-25", "WAB__none__e0", 0.005371, "spinoffs", "Alpaca spin_offs (GE→WAB)"),
    ("DD__none__e0", "2019-04-02", "DOW__none__e1", 1 / 3, "spinoffs",
     SEC + "1666700/000119312519095042/d725044dex991.htm (precio en bruto anterior al contrasplit)"),
    ("DWDP__2019-05-31x__e0", "2019-04-02", "DOW__none__e1", 1 / 3, "spinoffs",
     SEC + "1666700/000119312519095042/d725044dex991.htm"),
    ("DD__none__e0", "2019-06-03", "CTVA__none__e0", 1.0, "spinoffs",
     SEC + "1666700/000119312519163322/d715311d8k.htm (1 por cada 3 antiguas = 1 por cada nueva tras el 1:3)"),
    ("TT__none__e0", "2020-03-02", "IR__none__e0", 0.8824, "spinoffs",
     SEC + "1466258/000114036120004470/nc10009348x1_ex99-1.htm"),
    ("RTX__none__e0", "2020-04-03", "CARR__none__e0", 1.0, "spinoffs",
     SEC + "101829/000114036120005675/nc10009877x1_8k.htm"),
    ("RTX__none__e0", "2020-04-03", "OTIS__none__e0", 0.5, "spinoffs",
     SEC + "101829/000114036120005675/nc10009877x1_8k.htm"),
    ("FTV__none__e0", "2020-10-09", "VNT__none__e0", 0.4, "spinoffs",
     SEC + "1659166/000119312520268470/d35176dex21.htm"),
    ("PFE__none__e0", "2020-11-17", "VTRS__none__e0", 0.1240788849, "spinoffs", "Alpaca spin_offs (PFE→VTRS)"),
    ("SNX__none__e0", "2020-12-01", "CNXC__none__e0", 1.0, "spinoffs",
     SEC + "1177394/000156459020049806/snx-ex991_148.htm"),
    ("AIV__2020-12-18x__e0", "2020-12-15", "AIRC__2024-06-27__e0", 1.0, "spinoffs", "Alpaca spin_offs (AIV→AIRC)"),
    ("FTI__none__e0", "2021-02-16", "", 0.2, "spinoffs", "Alpaca spin_offs (FTI→THNPF); sin serie de la escindida"),
    ("LGND__none__e0", "2022-11-02", "", None, "spinoffs",
     "Alpaca spin_offs (LGND→OABI 4,90007, no verificada); sin serie de la escindida"),
    # escisiones que aparecen al cortar series por identidad (§5)
    ("HWM__none__e0", "2020-04-01", "ARNC__2023-08-18__e0", 0.25, "identity",
     SEC + "4281/000000428120000038/form10k4q19.htm"),
    ("PRG__none__e0", "2020-12-01", "AAN__2023-09-15x__e0", 0.5, "identity",
     SEC + "1808834/000180883420000017/progholdingsincex991pr.htm"),
    ("APTV__none__e0", "2017-12-05", "DLPH__2020-10-06__e0", 1 / 3, "identity",
     SEC + "1521332/000119312517344144/d498099dex994.htm"),
    ("ADEA__none__e0", "2022-10-03", "", None, "identity", "Xperi Inc. — proporción sin verificar"),
    ("CXT__none__e0", "2023-04-04", "CR__none__e0", 1.0, "identity",
     SEC + "25445/000119312523064677/d297986dex991.htm"),
]

if __name__ == "__main__":
    d = pd.DataFrame(ROWS, columns=["parent_key", "ex_date", "child_key", "ratio", "family", "source"])
    d.to_csv(C.PUB / "corr1_spinoffs.csv", index=False)
    print(d.to_string())
