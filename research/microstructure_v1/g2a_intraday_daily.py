"""G2A — resumen intradía por entidad y día a partir de las barras de 1 minuto del nivel A (solo DESARROLLO).

Lee únicamente unidades con fecha <= 2021-10-29 (última fecha de decisión de desarrollo): ningún fichero de minutos
del embargo ni de la prueba se abre. Para cada (entidad, día), solo sesión regular (apertura-cierre oficiales del
calendario, cierres anticipados incluidos):
  n_min, v, vwap, o_first, c_last, path = Σ|c_m − c_{m−1}| con c_0 = o_first, hi, lo (de los minutos)
y el volumen por precio: cada minuto asigna su volumen a su VWAP (si falta, a su cierre) en una rejilla de
log-precio SIN AJUSTAR con celdas de 0,25 % (bin = floor(ln p / ln 1,0025)). Los splits se aplican después, al
agregar ventanas (G2A_PROTOCOLO §2-§3).

Reanudable: un fichero por mes en MICRO_DATA_DIR/features/{intraday_daily,vap_daily}/AAAA-MM.parquet.
Control de memoria: espera si quedan menos de MIN_FREE_MB libres (no compite con la descarga).
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, manifest, storage  # noqa: E402
import g1_plans  # noqa: E402

DEV_LAST_DECISION = "2021-10-29"
LOG_STEP = math.log(1.0025)
MIN_FREE_MB = int(os.environ.get("MICRO_FEAT_MIN_FREE_MB", "2500"))


def free_mb():
    try:
        import psutil
        return psutil.virtual_memory().available / 2**20
    except Exception:  # noqa: BLE001
        return 1e9


def wait_mem():
    while free_mb() < MIN_FREE_MB:
        time.sleep(30)


def day_bounds(days):
    b = {d: calendar.session_bounds(d, "regular") for d in days}
    return pd.DataFrame({"day": list(b), "a": [x[0] for x in b.values()], "b": [x[1] for x in b.values()]})


def summarize(df: pd.DataFrame, bounds: pd.DataFrame):
    """Minutos de un fichero (un símbolo-mes) -> resumen por día y volumen por precio por día."""
    df = df.copy()
    df["day"] = df["t"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    df = df.merge(bounds, on="day")
    df = df[(df["t"] >= df["a"]) & (df["t"] < df["b"])].sort_values("t")
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    g = df.groupby("day", sort=True)
    prev_c = g["c"].shift(1)
    first_o = g["o"].transform("first")
    df["step"] = (df["c"] - prev_c.fillna(first_o)).abs()
    p = df["vw"].where(df["vw"] > 0, df["c"])
    df["bin"] = np.floor(np.log(p) / LOG_STEP).astype("int64")
    df["pv"] = p * df["v"]
    s = g.agg(n_min=("t", "size"), v=("v", "sum"), pv=("pv", "sum"), o_first=("o", "first"), c_last=("c", "last"),
              path=("step", "sum"), hi=("h", "max"), lo=("l", "min"), trades=("n", "sum")).reset_index()
    s["vwap"] = s["pv"] / s["v"].where(s["v"] > 0)
    vap = df.groupby(["day", "bin"], as_index=False)["v"].sum()
    return s.drop(columns="pv"), vap


def main(limit_months=None):
    root = storage.root()
    ref = root / "reference"
    iv = pd.read_parquet(ref / "universe_intervals.parquet")
    daily = pd.read_parquet(ref / "daily_bars_levelA.parquet").drop_duplicates(["entity", "date"])
    days_all = calendar.trading_days(g1_plans.FIRST, DEV_LAST_DECISION)
    ua = g1_plans.level_a_days(iv, daily, calendar.trading_days(g1_plans.FIRST, "2026-11-13"))
    ua = ua[ua["date"] <= DEV_LAST_DECISION]
    ua["asof_k"] = [x if isinstance(x, str) and x.strip() else "" for x in ua["asof"]]
    units = pd.read_parquet(root / "samples" / "levelA_units_v1.parquet")
    units = units[units["month"] <= DEV_LAST_DECISION[:7]]
    m = manifest.Manifest()
    with m._c() as c:
        man = pd.DataFrame([dict(r) for r in c.execute(
            "SELECT symbol, asof, period, status, path FROM units WHERE kind='bars'")])
    norm = lambda x: x if isinstance(x, str) and x.strip() not in ("", "-") else None  # noqa: E731
    man_key = {(r.symbol, norm(r.asof), r.period): (r.status, manifest.localize(r.path)) for r in man.itertuples()}
    out_d, out_v = root / "features" / "intraday_daily", root / "features" / "vap_daily"
    out_d.mkdir(parents=True, exist_ok=True)
    out_v.mkdir(parents=True, exist_ok=True)
    months = sorted(units["month"].unique())[: limit_months or None]
    log = []
    t0 = time.time()
    for k, month in enumerate(months):
        fd, fv = out_d / f"{month}.parquet", out_v / f"{month}.parquet"
        if fd.exists() and fv.exists():
            continue
        wait_mem()
        bounds = day_bounds([d for d in days_all if d[:7] == month])
        uam = ua[ua["month"] == month]
        rows_d, rows_v, miss = [], [], []
        for u in units[units["month"] == month].itertuples():
            asof = u.asof if isinstance(u.asof, str) and u.asof.strip() else None
            st, path = man_key.get((u.symbol, asof, month), (None, None))
            want = uam[(uam["symbol"] == u.symbol) & (uam["asof_k"] == (asof or ""))][["entity", "date"]]
            if st != "ok" or not path or not Path(path).exists():
                miss.append({"symbol": u.symbol, "asof": asof, "month": month, "status": st, "days": len(want)})
                continue
            s, vap = summarize(pd.read_parquet(path), bounds)
            if s.empty:
                continue
            # una unidad puede servir a varias entidades el mismo día (CIK del S&P y ticker del proyecto «T:»):
            # se replica la fila para cada una (antes un dict por fecha se quedaba solo con la última)
            w = want.assign(entity=want["entity"].astype(str)).drop_duplicates().rename(columns={"date": "day"})
            s, vap = s.merge(w, on="day", how="inner"), vap.merge(w, on="day", how="inner")
            s["symbol"], vap["symbol"] = u.symbol, u.symbol
            rows_d.append(s)
            rows_v.append(vap)
        d = pd.concat(rows_d, ignore_index=True) if rows_d else pd.DataFrame()
        v = pd.concat(rows_v, ignore_index=True) if rows_v else pd.DataFrame()
        storage.write_parquet_atomic(v, fv)
        storage.write_parquet_atomic(d, fd)
        log.append({"month": month, "entity_days": int(len(d)), "vap_rows": int(len(v)), "missing_units": miss})
        print(month, len(d), len(v), "faltan", len(miss), round(time.time() - t0), "s", flush=True)
    f = root / "results" / "g2a_intraday_daily_log.jsonl"
    with f.open("a", encoding="utf-8") as h:
        for r in log:
            h.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
