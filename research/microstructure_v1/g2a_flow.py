"""G2A — reconstrucción del Flow Score y el Early Flow por entidad y día (filtro 5 de la población C,
G2A_PROTOCOLO §3) con las barras diarias SIP de referencia ajustadas por splits hacia atrás (enmienda 4.4).

Mismo procedimiento que research/macd_combo_filters_v1 (Koncorde D/3D/W de scripts/koncorde_calculator.py, RSI de
Wilder, redondeos de JS) más macdBull (histograma MACD 12/26/9 >= 0, como shared/quote-lib.js). Las entradas se
pasan a shared/flow-score.js con g2a_flow.js. Solo días <= 2021-10-29 (desarrollo). Limitación heredada
(early_flow7_validation_v1): la reconstrucción coincide con lo capturado en vivo en el 61 % de los valores exactos y
en el 97 % del lado del umbral 7 de Early Flow.
Salida: MICRO_DATA_DIR/features/flow_dev.parquet (entity, date, flow, ef).
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from micro import distributions as D, outcomes, storage  # noqa: E402

spec = importlib.util.spec_from_file_location("bf", HERE.parent / "macd_combo_filters_v1" / "build_features.py")
bf = importlib.util.module_from_spec(spec)
import os  # noqa: E402
_cwd = os.getcwd()
os.chdir(spec.origin and Path(spec.origin).parent)     # build_features crea _work/ en el directorio actual
try:
    spec.loader.exec_module(bf)
finally:
    os.chdir(_cwd)


def ema_sma_seed(x, n):
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    k = 2 / (n + 1)
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = x[i] * k + out[i - 1] * (1 - k)
    return out


def macd_bull(c):
    line = ema_sma_seed(c, 12) - ema_sma_seed(c, 26)
    ok = ~np.isnan(line)
    sig = np.full(len(c), np.nan)
    sig[ok] = ema_sma_seed(line[ok], 9)
    return np.where(np.isnan(sig), np.nan, (line - sig >= 0).astype(float))


def adjusted(g, splits):
    g = g.sort_values("date").copy()
    f = np.ones(len(g))
    for r in splits.itertuples():
        f[g["date"].to_numpy() < r.ex_date] *= r.factor
    a = {k: g[c].to_numpy(float) for k, c in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"))}
    return pd.DataFrame({"open": a["open"] / f, "high": a["high"] / f, "low": a["low"] / f, "close": a["close"] / f,
                         "volume": a["volume"] * f}, index=pd.DatetimeIndex(pd.to_datetime(g["date"].to_numpy())))


def main():
    root = storage.root()
    ref = root / "reference"
    daily = pd.read_parquet(ref / "daily_ohlc_v2.parquet")
    daily = daily[(~daily["filler"]) & (daily["date"] <= outcomes.DEV_LAST_DECISION)]
    daily["entity"] = daily["entity"].astype(str)
    act = outcomes.parse_actions(pd.read_parquet(ref / "corporate_actions.parquet"))
    import g2a_coverage
    syms = g2a_coverage.entity_symbols(daily, pd.read_parquet(ref / "corporate_actions.parquet"))
    applied = D.applied_splits_by_entity()
    lines = ["entity,date,kd,pkd,k3,pk3,kw,atr,patr,fh,rsi,w1,m1,mb"]
    skipped = []

    def s(x):
        return "" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x)

    for k, (e, g) in enumerate(daily.groupby("entity")):
        if len(g) < 120:
            continue
        adj = adjusted(g, applied.get(e, pd.DataFrame(columns=["symbol", "ex_date", "factor"])))  # solo splits coherentes (enmienda 7)
        try:
            sd, s3, sw = bf.konc_daily_3d_weekly(adj)
        except IndexError as ex:      # Koncorde sin barras suficientes en algún marco: sin Flow (se cuenta)
            skipped.append({"entity": e, "rows": len(adj), "first": str(adj.index.min().date()),
                            "last": str(adj.index.max().date()), "error": str(ex)})
            continue
        c = adj["close"].to_numpy(float)
        h, l = adj["high"].to_numpy(float), adj["low"].to_numpy(float)
        atr = bf.bt.wilder_atr(c, h, l)
        atr_pct = np.round(atr / c * 100, 1)
        rsi = bf.js_round(bf.wilder_rsi(c))
        hi365 = adj["close"].rolling("365D").max().to_numpy()
        fh = bf.js_round((c - hi365) / hi365 * 100)
        w1 = np.full(len(c), np.nan); w1[5:] = bf.js_round((c[5:] / c[:-5] - 1) * 100)
        m1 = np.full(len(c), np.nan); m1[21:] = bf.js_round((c[21:] / c[:-21] - 1) * 100)
        mb = macd_bull(c)
        dates = adj.index.strftime("%Y-%m-%d")
        for i in range(1, len(c)):
            lines.append(",".join([e, dates[i], s(sd[i]), s(sd[i - 1]), s(s3[i]), s(s3[i - 1]), s(sw[i]),
                                   s(atr_pct[i]), s(atr_pct[i - 1]), s(None if np.isnan(fh[i]) else int(fh[i])),
                                   s(None if np.isnan(rsi[i]) else int(rsi[i])),
                                   s(None if np.isnan(w1[i]) else int(w1[i])),
                                   s(None if np.isnan(m1[i]) else int(m1[i])),
                                   s(None if np.isnan(mb[i]) else int(mb[i]))]))
        if k % 100 == 0:
            print(k, e, flush=True)
    work = root / "features"
    (work / "flow_in.csv").write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(["node", str(HERE / "g2a_flow.js"), str(work)], check=True)
    out = pd.read_csv(work / "flow_out.csv", dtype={"entity": str})
    storage.write_parquet_atomic(out, work / "flow_dev.parquet")
    print(out.describe().to_string())
    print("sin Flow por falta de barras:", skipped)


if __name__ == "__main__":
    main()
