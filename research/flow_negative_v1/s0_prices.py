"""Etapa 0 — descarga de barras diarias en bruto (Alpaca SIP) y acciones corporativas.

Una petición por (ticker, asof). Los intervalos de composición del mismo ticker con el mismo nombre de empresa se
agrupan: asof = último día de pertenencia del grupo (sin asof si sigue en algún índice). Un ticker reutilizado por
otra empresa (nombre distinto) genera otra petición con su propio asof (regla de research/microstructure_v1/identity).
Rango: PRICE_START → min(fin + 75 días, PRICE_END), para cubrir 40 sesiones de resultado tras la última señal.
Ajustes: se piden barras en BRUTO; splits y dividendos se aplican después con la regla de coherencia (s0_series.py).

Salidas (fuera del repo): bars/<ticker>__<asof>.parquet, corporate_actions/ca_<lote>.json, work/requests.csv
Idempotente: no repite peticiones ya guardadas. Uso: py -3 s0_prices.py [--ca-only|--bars-only] [--threads 4]
"""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

import fn_config as C
from s0_universe import _norm_name


BENCH = ["SPY", "IJH", "IJR"]


def requests_plan():
    m = pd.read_csv(C.PUB / "membership.csv", dtype=str)
    rows = []
    for t, g in m.groupby("ticker"):
        g = g.sort_values("start")
        groups = []
        for r in g.to_dict("records"):
            w = _norm_name(r["name"])
            hit = next((x for x in groups if x["w"] and w and x["w"][0] == w[0]), None)
            if hit is None and groups and (not w or not groups[-1]["w"]):
                hit = groups[-1]
            if hit is None:
                groups.append({"w": w, "rows": [r]})
            else:
                hit["rows"].append(r)
        for x in groups:
            ends = [r["end"] for r in x["rows"]]
            asof = None if any(e is None or e != e for e in ends) else max(ends)
            end = C.PRICE_END if asof is None else min(
                (pd.Timestamp(asof) + pd.Timedelta(days=75)).date().isoformat(), C.PRICE_END)
            rows.append({"ticker": t, "asof": asof or "", "start": C.PRICE_START, "end": end,
                         "names": " | ".join(sorted({r["name"] for r in x["rows"]})),
                         "indices": ",".join(sorted({r["index"] for r in x["rows"]})),
                         "first_member": min(r["start"] for r in x["rows"]),
                         "last_member": asof or ""})
    for b in BENCH:   # referencias de mercado (régimen, exceso frente a SPY); no son miembros de ningún índice
        rows.append({"ticker": b, "asof": "", "start": C.PRICE_START, "end": C.PRICE_END, "names": b,
                     "indices": "bench", "first_member": C.PRICE_START, "last_member": ""})
    p = pd.DataFrame(rows)
    p["key"] = p.ticker.str.replace(".", "_", regex=False) + "__" + p["asof"].replace("", "none")
    return p


def fetch_bars(prov, r):
    out = C.BARS / f"{r['key']}.parquet"
    if out.exists():
        return r["key"], "cached", None
    rows = []
    try:
        for page in prov.fetch_pages("bars", r["ticker"], r["start"], r["end"], asof=r["asof"] or None,
                                     timeframe="1Day"):
            rows.extend(page)
    except Exception as e:  # noqa: BLE001
        return r["key"], "error", str(e)[:200]
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["t", "o", "h", "l", "c", "v", "n", "vw"])
    df.to_parquet(out)
    return r["key"], "ok" if len(df) else "empty", len(df)


def fetch_ca(prov, symbols):
    done = {p.stem for p in C.CA.glob("ca_*.json")}
    lots = [symbols[i:i + 50] for i in range(0, len(symbols), 50)]
    for k, lot in enumerate(lots):
        name = f"ca_{k:04d}"
        if name in done:
            continue
        d = prov.corporate_actions(lot, C.PRICE_START, C.PRICE_END)
        json.dump({"symbols": lot, "actions": d}, open(C.CA / f"{name}.json", "w"))
        print("CA lote", k + 1, "/", len(lots), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ca-only", action="store_true")
    ap.add_argument("--bars-only", action="store_true")
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    plan = requests_plan()
    plan.to_csv(C.WORK / "requests.csv", index=False)
    print("peticiones", len(plan), "tickers", plan.ticker.nunique(), flush=True)
    prov = C.alpaca()
    if not a.ca_only:
        log = []
        with ThreadPoolExecutor(a.threads) as ex:
            futs = [ex.submit(fetch_bars, prov, r) for r in plan.to_dict("records")]
            for i, f in enumerate(as_completed(futs), 1):
                log.append(f.result())
                if i % 100 == 0:
                    print("barras", i, "/", len(futs), flush=True)
        pd.DataFrame(log, columns=["key", "status", "info"]).to_csv(C.WORK / "bars_log.csv", index=False)
        print(pd.Series([x[1] for x in log]).value_counts().to_dict(), flush=True)
    if not a.bars_only:
        syms = sorted(set(plan.ticker))
        ch = pd.read_csv(C.PUB / "changes.csv", dtype=str)
        ch = ch[ch.date >= C.PRICE_START]
        extra = set(ch.add_t.dropna()) | set(ch.rem_t.dropna())
        syms = sorted(set(syms) | {s for s in extra if re.fullmatch(r"[A-Z][A-Z0-9.]{0,6}", s)})
        fetch_ca(prov, syms)


if __name__ == "__main__":
    main()
