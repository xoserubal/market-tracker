"""E2 — retrospectivo del registro de eventos: medidas cat-v0 de cada valor-día, estrictamente a fecha.

Autorización: E2_AUTORIZACION.md (2026-11-21). Solo describe: no calcula ningún resultado posterior.

Universo y periodo
- Entidades del S&P 500 con pertenencia verificada en algún día de 2016-01-04 a 2021-10-28 (G1). Se calculan TODAS
  sus sesiones del nivel A hasta 2021-10-28, también las previas a la pertenencia: sirven de calentamiento de la línea
  base (el nivel A trae 252 sesiones previas). La columna `member` dice qué días cuentan para el recuento.
- Nada del periodo reservado de G2A (test_guard): ni se lee ni se calcula.

Identidad, splits y eventos
- Cada (entidad, día) se lee de la unidad del nivel A que le asigna g1_plans.level_a_days (símbolo y asof de su época).
- Barras ajustadas hacia atrás con los splits validados contra el precio en G2A (enmienda 7): precio / f, volumen · f.
  Sin esto, tras un split el volumen en acciones se duplicaría frente al perfil durante semanas (falsas anomalías).
- Días con evento corporativo no reconstruido (g2a_events: escisiones, splits incoherentes…) y caídas de datos
  (g2a_outages) quedan marcados; no se borran.

Cálculo (por sesión, una sola vez)
- Perfil propio: las 60 sesiones válidas (≥ 20 % de minutos continuos con barra) estrictamente anteriores, dentro de
  180 días naturales. Mismas reglas que E1; versión vectorizada verificada (micro/e2_fast.py, tests/test_e2.py).
- Medidas: intraday_features.day_measures SIN CAMBIOS (cat-v0), pasada completa (after hours incluido).
- Se guardan, por medida: valor (bruto, el que se normaliza), signo (medidas de instante fijo) y minuto del pico.
  La normalización frente a la historia se hace después (e2_analyze.py), con varios métodos.

Salida: MICRO_DATA_DIR/features/e2_measures/<entidad>.parquet (reanudable) y results/e2_compute_log.jsonl.
Uso: py -3 e2_compute.py [--workers 4] [--limit N] [--entities a,b]
"""
import argparse
import json
import os
import sys
import time
import traceback
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, distributions as D, e2_fast as X, intraday_features as F, manifest, storage, test_guard  # noqa: E402
import g1_plans  # noqa: E402
import g2a_outages  # noqa: E402

E2_FIRST, E2_LAST = "2016-01-04", "2021-10-28"
BASE_TARGET, BASE_MIN_STORE, MAX_AGE_DAYS, MIN_COV = 60, 20, 180, 0.2
MIN_FREE_MB = int(os.environ.get("MICRO_E2_MIN_FREE_MB", "2500"))
OUT = storage.root() / "features" / "e2_measures"
LOG = storage.root() / "results" / "e2_compute_log.jsonl"

_G = {}


def free_mb():
    try:
        import psutil
        return psutil.virtual_memory().available / 2**20
    except Exception:  # noqa: BLE001
        return 1e9


def plan():
    """Entidades de E2 y su plan (entidad, día, símbolo, asof, mes) hasta E2_LAST, más los días de pertenencia."""
    ref = storage.root() / "reference"
    iv = pd.read_parquet(ref / "universe_intervals.parquet")
    daily = pd.read_parquet(ref / "daily_bars_levelA.parquet").drop_duplicates(["entity", "date"])
    ua = g1_plans.level_a_days(iv, daily, calendar.trading_days(g1_plans.FIRST, g1_plans.LAST))
    ua = ua[(ua["date"] <= E2_LAST) & ~ua["date"].map(test_guard.reserved)]
    ua["entity"] = ua["entity"].astype(str)
    sp = iv[iv["source"] == "sp500"].copy()
    sp["entity"] = sp["entity"].astype(str)
    sp = sp[(sp["start"] <= E2_LAST) & (sp["end"] >= E2_FIRST)]
    ents = sorted(set(sp["entity"]) & set(ua["entity"]))
    member = {}
    for r in sp.itertuples():
        member.setdefault(r.entity, []).append((max(r.start, E2_FIRST), min(r.end, E2_LAST)))
    return ents, ua[ua["entity"].isin(ents)], member


def _init():
    m = manifest.Manifest()
    with m._c() as c:
        man = pd.DataFrame([dict(r) for r in c.execute(
            "SELECT symbol, asof, period, status, path FROM units WHERE kind='bars'")])
    norm = lambda x: x if isinstance(x, str) and x.strip() not in ("", "-") else None  # noqa: E731
    _G["man"] = {(r.symbol, norm(r.asof), r.period): (r.status, manifest.localize(r.path)) for r in man.itertuples()}
    _G["splits"] = D.applied_splits_by_entity()
    _G["events"] = D.events_by_entity()
    _G["outages"] = g2a_outages.outage_days()
    _G["cal"] = calendar.trading_days("2015-01-01", E2_LAST)


def load_entity_bars(g: pd.DataFrame) -> tuple:
    """Barras de 1 min de la entidad (solo los días que el plan asigna a cada unidad) y unidades usadas."""
    frames, used, miss = [], [], []
    for (sym, asof, month), gg in g.groupby(["symbol", "asof_k", "month"]):
        st, path = _G["man"].get((sym, asof or None, month), (None, None))
        if st != "ok" or not path or not Path(path).exists():
            miss.append(f"{sym}|{asof}|{month}")
            continue
        f = pd.read_parquet(path, columns=["t", "o", "h", "l", "c", "v", "n", "vw"])
        f["t"] = pd.to_datetime(f["t"], utc=True)
        f["_day"] = f["t"].dt.tz_convert(F.NY).dt.strftime("%Y-%m-%d")
        f = f[f["_day"].isin(set(gg["date"]))]
        f["_unit"] = f"{sym}|{asof or '-'}|{month}"
        frames.append(f)
        used.append(f"{sym}|{asof or '-'}|{month}")
    if not frames:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v", "n", "vw", "_day", "_unit"]), used, miss
    # un día puede venir en dos unidades contiguas (el mes UTC empieza a las 19:00/20:00 NY del día anterior)
    b = pd.concat(frames, ignore_index=True).drop_duplicates("t", keep="first").sort_values("t").reset_index(drop=True)
    return b, used, miss


def split_adjust(bars: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    if splits is None or not len(splits) or not len(bars):
        return bars
    f = np.ones(len(bars))
    for r in splits.itertuples():
        f = np.where(bars["_day"].to_numpy() < r.ex_date, f * float(r.factor), f)
    bars = bars.copy()
    for c in ("o", "h", "l", "c", "vw"):
        bars[c] = bars[c] / f
    bars["v"] = bars["v"] * f
    return bars


def compute_entity(ent: str, g: pd.DataFrame, member_iv: list) -> dict:
    t0 = time.time()
    g = g.sort_values("date")
    g = g.assign(asof_k=[x if isinstance(x, str) and x.strip() not in ("", "-") else "" for x in g["asof"]])
    days = list(g["date"])
    sym_of = dict(zip(g["date"], g["symbol"]))
    bars, used, miss = load_entity_bars(g)
    splits = _G["splits"].get(ent)
    bars = split_adjust(bars, splits)
    M = X.build_matrix_fast(bars, days)
    del bars
    cov = np.array([np.isfinite(M.C[i, m["open_slot"] + 1:m["close_slot"]]).mean() if m["close_slot"] > m["open_slot"] + 1
                    else 0.0 for i, m in enumerate(M.meta)])
    good = cov >= MIN_COV
    pos = {d: i for i, d in enumerate(days)}
    cal = _G["cal"]
    cpos = {d: i for i, d in enumerate(cal)}
    events = set(_G["events"].get(ent, []))
    split_days = set(splits["ex_date"]) if splits is not None and len(splits) else set()
    parts = {}
    rows = []
    good_idx = []
    for i, d in enumerate(days):
        dt = pd.Timestamp(d)
        old = (dt - pd.Timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
        base = [j for j in good_idx[-BASE_TARGET:] if days[j] >= old]
        row = {"entity": ent, "symbol": sym_of[d], "date": d, "cov": round(float(cov[i]), 4), "prof_n": len(base),
               "member": any(a <= d <= b for a, b in member_iv), "early_close": bool(M.meta[i]["early_close"]),
               "corp_event": d in events, "split_day": d in split_days, "outage": d in _G["outages"]}
        if np.isfinite(M.C[i]).any() and len(base) >= BASE_MIN_STORE:
            for j in base:
                if j not in parts:
                    parts[j] = X.day_parts(M, j)
            prof = X.profile_from_parts([parts[j] for j in base])
            pdx = cpos.get(d)
            pd_ = cal[pdx - 1] if pdx else None
            prev_close = F.last_continuous_close(M, pos[pd_]) if pd_ in pos else None
            ms = F.day_measures(M, i, prof, prev_close, post=True)
            q = ms.pop("_quality")
            b = M.meta[i]
            row["liq"] = float(np.nanmedian(M.N[i, b["open_slot"] + 1:b["close_slot"]])) \
                if np.isfinite(M.N[i, b["open_slot"] + 1:b["close_slot"]]).any() else 0.0
            row["longest_gap"] = q["longest_gap_minutes"]
            row["dollar_vol"] = float(np.nansum(M.V[i, b["open_slot"]:b["close_slot"]] *
                                                M.C[i, b["open_slot"]:b["close_slot"]]))
            for name, m in ms.items():
                v = m["value"]
                row[f"{name}__v"] = v
                if "sign" in m:
                    row[f"{name}__s"] = m["sign"]
                ser = m["series"]
                if ser is not None and np.any(np.isfinite(ser)):
                    row[f"{name}__p"] = int(np.nanargmax(ser))
                elif m["fixed_slot"] is not None:
                    row[f"{name}__p"] = int(m["fixed_slot"]) - 1
        rows.append(row)
        if good[i]:
            good_idx.append(i)
        # libera aportaciones que ya no pueden volver a la línea base
        if len(good_idx) > BASE_TARGET + 5:
            for j in list(parts):
                if j < good_idx[-(BASE_TARGET + 5)]:
                    del parts[j]
    df = pd.DataFrame(rows)
    for c in df.columns:
        if c.endswith("__v"):
            df[c] = df[c].astype("float32")
        elif c.endswith("__p") or c.endswith("__s"):
            df[c] = df[c].astype("Int16")
    storage.write_parquet_atomic(df, OUT / f"{ent.replace(':', '_')}.parquet")
    return {"entity": ent, "days": len(days), "member_days": int(df["member"].sum()),
            "measured_days": int(df["prof_n"].ge(BASE_MIN_STORE).sum()), "units": len(used), "missing_units": miss,
            "splits_applied": len(split_days), "seconds": round(time.time() - t0, 1)}


def _work(args):
    ent, g, miv = args
    while free_mb() < MIN_FREE_MB:
        time.sleep(20)
    try:
        return compute_entity(ent, g, miv)
    except Exception as e:  # noqa: BLE001
        return {"entity": ent, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--entities")
    a = ap.parse_args()
    test_guard.check([E2_FIRST, E2_LAST], purpose="E2 retrospectivo", script="e2_compute")
    ents, ua, member = plan()
    if a.entities:
        ents = [e for e in ents if e in set(a.entities.split(","))]
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [e for e in ents if not (OUT / f"{e.replace(':', '_')}.parquet").exists()][: a.limit or None]
    print(f"entidades {len(ents)}, pendientes {len(todo)}, días del plan {len(ua)}", flush=True)
    groups = {e: g for e, g in ua.groupby("entity")}
    jobs = [(e, groups[e], member.get(e, [])) for e in todo]
    t0 = time.time()
    with Pool(a.workers, initializer=_init) as pool, LOG.open("a", encoding="utf-8") as log:
        for k, r in enumerate(pool.imap_unordered(_work, jobs), 1):
            log.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            log.flush()
            msg = r.get("error") or f"{r['days']} días, {r['seconds']} s"
            print(f"{k}/{len(jobs)} {r['entity']}: {msg} · {round(time.time() - t0)} s", flush=True)


if __name__ == "__main__":
    main()
