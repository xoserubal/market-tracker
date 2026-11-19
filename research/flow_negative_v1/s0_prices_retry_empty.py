"""Reintenta las peticiones vacías con asof posterior a 2016: el asof era la fecha de baja del índice, cuando el
símbolo ya no existía. Prueba asof = baja − 1, 2, 3, 5, 7, 10, 15, 30, 60 días naturales; guarda la primera con datos
(con el asof realmente usado en work/asof_retry.csv)."""
import pandas as pd
import fn_config as C
plan = pd.read_csv(C.WORK / "requests.csv", dtype=str, keep_default_na=False).set_index("key")
summ = pd.read_csv(C.WORK / "series_summary.csv", dtype=str, keep_default_na=False)
done = set(pd.read_csv(C.WORK / "asof_retry.csv", dtype=str).key) if (C.WORK / "asof_retry.csv").exists() else set()
empty = [k for k in summ.loc[summ.status == "empty", "key"] if plan.loc[k, "asof"] >= "2016-01-01" and k not in done]
prov = C.alpaca()
out = []
for k in empty:
    r = plan.loc[k]
    got = None
    for d in (1, 2, 3, 5, 7, 10, 15, 30, 60):
        asof = (pd.Timestamp(r["asof"]) - pd.Timedelta(days=d)).date().isoformat()
        rows = [x for page in prov.fetch_pages("bars", r["ticker"], r["start"], r["end"], asof=asof, timeframe="1Day")
                for x in page]
        if rows:
            got = (asof, rows)
            break
    if got:
        pd.DataFrame(got[1]).to_parquet(C.BARS / f"{k}.parquet")
    out.append({"key": k, "ticker": r["ticker"], "asof_original": r["asof"], "asof_used": got[0] if got else "",
                "bars": len(got[1]) if got else 0})
    print(out[-1], flush=True)
prev = pd.read_csv(C.WORK / "asof_retry.csv", dtype=str) if (C.WORK / "asof_retry.csv").exists() else None
pd.concat([prev, pd.DataFrame(out)]).to_csv(C.WORK / "asof_retry.csv", index=False)
