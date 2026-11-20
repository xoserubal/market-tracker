"""Enmienda 1 §3 — inventario y evidencia de los saltos de precio sin explicar. Solo lectura de las series originales.

Universo: saltos de cierre ×2/÷2 sin explicar y splits rechazados como incoherentes, en series con días utilizables,
con fecha <= 2023-03-31 (desarrollo de todas las tallas y sus ventanas; nada del periodo de prueba de pequeñas/micro).

Evidencia (independiente del rendimiento posterior a cualquier señal):
  - Yahoo: retorno de ese día con precios de Yahoo (ajustados por splits) frente al de Alpaca (en bruto);
  - SPY y mediana del sector ese día (entre las empresas del panel);
  - volumen del día / mediana de las 20 sesiones previas;
  - reversión en <= 3 sesiones (solo señal de auditoría);
  - 8-K presentados en ±3 días (ítems), del caché de la SEC.
Clasificación automática propuesta (columna `auto`), que se revisa a mano en `corr1_jumps.csv` (columna `class`):
  corporate_split / corporate_spinoff / market / data_error / indeterminate.

Salida: data/corr1_jumps_evidence.csv
"""
import json

import numpy as np
import pandas as pd

import fn_config as C
from s0_series import load_ca

LIMIT = "2023-03-31"
SPLITS = pd.read_csv(C.PUB / "corr1_splits.csv", dtype=str) if (C.PUB / "corr1_splits.csv").exists() else None


def yahoo_returns(sym, d):
    import yfinance as yf
    a = (pd.Timestamp(d) - pd.Timedelta(days=12)).strftime("%Y-%m-%d")
    b = (pd.Timestamp(d) + pd.Timedelta(days=8)).strftime("%Y-%m-%d")
    try:
        h = yf.download(sym.replace(".", "-"), start=a, end=b, auto_adjust=False, progress=False, threads=False)
    except Exception:
        return None
    if h is None or h.empty:
        return None
    c = h["Close"].squeeze().dropna()
    c.index = c.index.strftime("%Y-%m-%d")
    if d not in c.index:
        return None
    i = list(c.index).index(d)
    if i == 0:
        return None
    return float(c.iloc[i] / c.iloc[i - 1]), float(c.iloc[i - 1]), float(c.iloc[i])


def items_near(cik, d):
    if not isinstance(cik, str) or cik in ("", "nan"):
        return ""
    f = C.SEC / "submissions" / f"{int(float(cik))}.json"
    if not f.exists():
        return ""
    s = json.loads(f.read_text(encoding="utf-8"))
    if "filings" not in s:
        return ""
    r = s["filings"]["recent"]
    t0 = pd.Timestamp(d) - pd.Timedelta(days=3)
    t1 = pd.Timestamp(d) + pd.Timedelta(days=3)
    out = [f"{fd}:{it}" for fd, fm, it in zip(r["filingDate"], r["form"], r.get("items", [""] * len(r["form"])))
           if fm.startswith("8-K") and t0 <= pd.Timestamp(fd) <= t1]
    return " | ".join(out)


def main():
    comp = pd.read_csv(C.WORK / "companies_v4.csv", dtype={"cik": str}).drop_duplicates("key").set_index("key")
    p = pd.read_parquet(C.WORK / "panel_v4.parquet", columns=["key", "date", "sector", "raw_close", "usable"])
    used = set(p[p.usable].key)
    # retorno diario de cada serie del panel, para mediana de sector
    p = p.sort_values(["key", "date"])
    p["r"] = p.groupby("key").raw_close.pct_change()
    sec_med = p.groupby(["date", "sector"]).r.median()
    spy = pd.read_parquet(C.WORK / "series" / "SPY__none__e0.parquet", columns=["date", "adj"]).set_index("date").adj
    spy_r = spy / spy.shift(1) - 1
    sector_of = p.groupby("key").sector.last()
    ca = load_ca()
    spins = set(zip(ca["spinoffs"].source_symbol, ca["spinoffs"].ex_date))
    cur = pd.read_csv(C.REPO / "research" / "microstructure_v1" / "distribution_events_dev.csv")
    spins |= set(zip(cur.parent, cur.ex_date))
    rows = []
    for k in sorted(used):
        r = comp.loc[k]
        evs = [(d, "salto") for d in json.loads(r.unexplained_jumps or "[]")]
        evs += [(d, t) for d, t in json.loads(r.events or "[]") if t == "E2_split_incoherente"]
        evs = [(d, t) for d, t in evs if d <= LIMIT]
        if not evs:
            continue
        s = pd.read_parquet(C.WORK / "series" / f"{k}.parquet",
                            columns=["date", "raw_close", "raw_volume"]).reset_index(drop=True)
        dates = s.date.tolist()
        for d, t in evs:
            if d not in dates:
                continue
            i = dates.index(d)
            if i == 0:
                continue
            pc, c = s.raw_close.iat[i - 1], s.raw_close.iat[i]
            ratio = c / pc
            nxt = s.raw_close.iloc[i + 1:i + 4]
            rev = float(np.min(np.abs(np.log(nxt / pc))) / abs(np.log(ratio))) if len(nxt) and ratio != 1 else np.nan
            vol = s.raw_volume.iat[i] / s.raw_volume.iloc[max(0, i - 20):i].median()
            vol_after = s.raw_volume.iloc[i + 1:i + 21].median() / s.raw_volume.iloc[max(0, i - 20):i].median()
            y = yahoo_returns(r.ticker, d)
            syms = set(str(r.symbols).split("|")) | {r.ticker}
            is_spin = any((x, d) in spins for x in syms)
            sec = sector_of.get(k, "")
            rows.append({"key": k, "ticker": r.ticker, "names": r.names, "date": d, "type": t,
                         "alpaca_ratio": ratio, "prev_close": pc, "close": c,
                         "yahoo_ratio": y[0] if y else np.nan,
                         "spy_ret": float(spy_r.get(d, np.nan)), "sector": sec,
                         "sector_med_ret": float(sec_med.get((d, sec), np.nan)) if sec else np.nan,
                         "vol_day_x": vol, "vol_after_x": vol_after,
                         "revert_3d_share": 1 - rev if rev == rev else np.nan,
                         "spinoff_listed": is_spin, "sec_8k_pm3d": items_near(r.cik, d),
                         "usable_from": p[(p.key == k) & p.usable].date.min()})
    e = pd.DataFrame(rows)

    def auto(x):
        la, ly = np.log(x.alpaca_ratio), np.log(x.yahoo_ratio) if x.yahoo_ratio == x.yahoo_ratio else np.nan
        split_like = abs(la) > np.log(3) and x.vol_after_x == x.vol_after_x and np.sign(np.log(x.vol_after_x)) != np.sign(la) \
            and abs(np.log(x.vol_after_x)) > np.log(3)
        if x.spinoff_listed:
            return "corporate_spinoff"
        if ly == ly:
            if abs(la - ly) < 0.10:
                return "market"
            if split_like:
                return "corporate_split?"
            if abs(ly) < 0.5 * abs(la):
                return "data_error?"
            return "indeterminate"
        if split_like:
            return "corporate_split?"
        return "indeterminate"
    e["auto"] = e.apply(auto, axis=1)
    e.to_csv(C.PUB / "corr1_jumps_evidence.csv", index=False)
    print(e.auto.value_counts())
    return e


if __name__ == "__main__":
    pd.set_option("display.width", 260)
    pd.set_option("display.max_rows", 300)
    e = main()
    print(e[["key", "date", "type", "alpaca_ratio", "yahoo_ratio", "spy_ret", "sector_med_ret", "vol_day_x",
             "vol_after_x", "revert_3d_share", "spinoff_listed", "auto", "usable_from"]].round(3).to_string())
