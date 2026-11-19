"""Etapa 0 (v3) — prolonga hasta el final de los datos las series de empresas que salieron del índice y siguieron
cotizando. En la etapa 0 original cada petición terminaba 75 días después de la baja del índice; para una muestra de
empresas (no de índices) hace falta lo que ocurrió después (caídas a microcap, quiebras posteriores...).

Selección (sin mirar ningún rendimiento): peticiones con asof (dieron de baja) cuyo final pedido es anterior a
PRICE_END y cuya última época NO terminó (la empresa seguía cotizando al final de lo pedido). Se vuelve a pedir el
rango completo con el mismo asof (el usado de verdad, si hubo reintento) hasta PRICE_END: es una petición por
empresa, igual que pedir solo la cola. Los ficheros originales no se tocan.

Salidas (fuera del repo): bars/<key>x.parquet, series/<key>x__e<n>.parquet, work/requests_ext.csv,
work/series_summary_ext.csv
"""
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

import pandas as pd

import fn_config as C
import s0_series as S


def plan():
    req = pd.read_csv(C.WORK / "requests.csv", dtype=str, keep_default_na=False)
    summ = pd.read_csv(C.WORK / "series_summary.csv", dtype=str, keep_default_na=False)
    retry = pd.read_csv(C.WORK / "asof_retry.csv", dtype=str, keep_default_na=False) \
        if (C.WORK / "asof_retry.csv").exists() else pd.DataFrame(columns=["key", "asof_used"])
    used = {k: a for k, a in zip(retry.key, retry.asof_used) if a}
    ok = summ[summ.status == "ok"]
    last = ok.sort_values("epoch").groupby("req_key").tail(1).set_index("req_key")
    rows = []
    for r in req.to_dict("records"):
        if not r["asof"] or r["end"] >= C.PRICE_END or r["key"] not in last.index:
            continue
        if last.loc[r["key"], "terminated"] == "True":
            continue
        x = dict(r)
        x["asof"] = used.get(r["key"], r["asof"])
        x["end"] = C.PRICE_END
        x["orig_key"] = r["key"]
        x["key"] = r["key"] + "x"
        rows.append(x)
    return pd.DataFrame(rows)


def fetch(prov, r):
    out = C.BARS / f"{r['key']}.parquet"
    if out.exists():
        return r["key"], "cached"
    rows = [x for page in prov.fetch_pages("bars", r["ticker"], r["start"], r["end"], asof=r["asof"],
                                           timeframe="1Day") for x in page]
    pd.DataFrame(rows if rows else [], columns=None if rows else ["t", "o", "h", "l", "c", "v", "n", "vw"]
                 ).to_parquet(out)
    return r["key"], "ok" if rows else "empty"


def main():
    p = plan()
    p.to_csv(C.WORK / "requests_ext.csv", index=False)
    print("peticiones a prolongar", len(p), flush=True)
    prov = C.alpaca()
    with ThreadPoolExecutor(4) as ex:
        st = list(ex.map(lambda r: fetch(prov, r), p.to_dict("records")))
    print(pd.Series([s for _, s in st]).value_counts().to_dict(), flush=True)
    ca = S.load_ca()
    ca_small = {k: ca[k] for k in ("splits", "dividends", "spinoffs", "name_changes")}
    ca_small["curated"] = S.curated()
    with ProcessPoolExecutor(6) as ex:
        res = [x for lst in ex.map(S.one, [(r, ca_small) for r in p.to_dict("records")], chunksize=8) for x in lst]
    s = pd.DataFrame(res)
    s.to_csv(C.WORK / "series_summary_ext.csv", index=False)
    print(s.status.value_counts().to_dict(), "terminadas", int((s.terminated == True).sum()))  # noqa: E712


if __name__ == "__main__":
    main()
