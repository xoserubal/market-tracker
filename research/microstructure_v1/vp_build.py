"""VP2 — tabla histórica de perfiles de volumen ESTIMADOS (capa 2). Aprobado por el usuario el 2026-11-22.

Fuente única: `estimated_bars_1m_ex_auction` (micro/vp_store.py, PARAMS con hash en cada fila). Nunca se mezcla con
perfiles observados con trades, que irían a otra tabla.

Periodos (nada del periodo reservado de G2A, 2021-10-29 a 2026-09-14):
- hist: entidades y días del plan de E2 (S&P 500 con pertenencia verificada en 2016-01-04 → 2021-10-28; identidad y
  símbolo de cada día del nivel A; splits validados contra el precio, enmienda 7 de G2A).
- recent: desde 2026-09-15, símbolos del universo actual de E3 (registro U1; emisor = CIK cuando se conoce).

Por valor-día: perfil base en precio SIN AJUSTAR (rejilla fina), estadísticas en la rejilla canónica del día y, aparte,
el factor de split para llevar el día a la escala del último día de su periodo (lo usan las comparaciones). Las barras
originales no se tocan. Marcas: evento corporativo no reconstruido, día de split, caída de datos, cobertura de minutos.

Salida: MICRO_DATA_DIR/features/vp_profiles/<periodo>/<entidad>.parquet (reanudable) y results/vp2/build_log.jsonl.
Uso:
  py -3 vp_build.py hist [--workers 4] [--limit N] [--entities a,b]
  py -3 vp_build.py recent
  py -3 vp_build.py verify            # controles de integridad
  py -3 vp_build.py index             # índice símbolo -> entidad -> fechas
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from micro import calendar, config, heavy_lock, intraday_features as F, sessions, storage, test_guard, \
    vp_store as S  # noqa: E402

OUT = storage.root() / "features" / "vp_profiles"
LOG = storage.root() / "results" / "vp2" / "build_log.jsonl"
RECENT_FIRST = "2026-09-15"
MIN_FREE_MB = 2500
_B = {}


def bounds(day):
    if day not in _B:
        b = sessions.bounds(day)
        _B[day] = (b["open"], b["close"], int((b["close"] - b["open"]).total_seconds() // 60))
    return _B[day]


def free_mb():
    try:
        import psutil
        return psutil.virtual_memory().available / 2**20
    except Exception:  # noqa: BLE001
        return 1e9


def day_rows(bars: pd.DataFrame, meta: dict) -> list:
    """Una fila por día con barras de la sesión regular."""
    out = []
    if not len(bars):
        return out
    for d, g in bars.groupby("_day", sort=True):
        o, c, nmin = bounds(d)
        r = g[(g["t"] >= o) & (g["t"] < c)]
        if r.empty:
            continue
        vw = np.where(np.isfinite(r["vw"]) & (r["vw"] > 0), r["vw"], r["c"])
        ref = float(np.average(vw, weights=r["v"])) if r["v"].sum() > 0 else float(r["c"].median())
        fine = S.step_for(ref, S.PARAMS["fine_rel"])
        lvl0, vols, capped = S.allocate(r["l"], r["h"], r["vw"], r["c"], r["v"], fine)
        g_can = S.step_for(ref, S.PARAMS["canonical_rel"])
        c0, cv = S.rebin(lvl0, vols, fine, 1.0, g_can)
        st = S.stats(c0, cv, g_can)
        out.append({**meta(d), "date": d, "ref_price": round(ref, 6), "tick": S.tick_of(ref), "fine_step": fine,
                    "lvl0": lvl0, "vols": vols.astype(np.float32), "profile_volume": float(vols.sum()),
                    "bar_volume": float(r["v"].sum()), "n_bars": int(len(r)), "cov": round(len(r) / nmin, 4),
                    "capped_bars": capped, "o": float(r["o"].iloc[0]), "h": float(r["h"].max()),
                    "l": float(r["l"].min()), "c": float(r["c"].iloc[-1]), "vwap": round(ref, 6),
                    **{k: v for k, v in st.items() if k != "ok"}, "stats_ok": st["ok"]})
    return out


def common_cols(df):
    df["source"] = S.PARAMS["source"]
    df["version"] = S.PARAMS["version"]
    df["params_sha256"] = S.PARAMS_SHA256
    df["code_version"] = config.code_version()
    return df


# ── histórico 2016-2021 (plan de E2) ───────────────────────────────────────────────────────────────────────────
def _init_hist():
    import e2_compute as E
    E._init()
    _G = E._G
    _G["E"] = E
    globals()["_GH"] = _G


def split_factor_to_last(day: str, splits) -> float:
    """Precio del día × factor = precio en la escala del último día del periodo (splits validados posteriores)."""
    f = 1.0
    if splits is not None and len(splits):
        for r in splits.itertuples():
            if day < r.ex_date:
                f /= float(r.factor)
    return f


def hist_entity(ent: str, g: pd.DataFrame, member_iv: list) -> dict:
    t0 = time.time()
    G = globals()["_GH"]
    E = G["E"]
    g = g.sort_values("date")
    g = g.assign(asof_k=[x if isinstance(x, str) and x.strip() not in ("", "-") else "" for x in g["asof"]])
    sym_of = dict(zip(g["date"], g["symbol"]))
    bars, used, miss = E.load_entity_bars(g)
    splits = G["splits"].get(ent)
    events = set(G["events"].get(ent, []))
    split_days = set(splits["ex_date"]) if splits is not None and len(splits) else set()
    rows = day_rows(bars, lambda d: {"entity": ent, "symbol": sym_of.get(d), "period": "hist",
                                     "member": any(a <= d <= b for a, b in member_iv), "corp_event": d in events,
                                     "split_day": d in split_days, "outage": d in G["outages"],
                                     "split_factor_to_last": split_factor_to_last(d, splits)})
    if any(test_guard.reserved(r["date"]) for r in rows):
        raise RuntimeError("fecha reservada en el resultado")
    df = common_cols(pd.DataFrame(rows))
    p = OUT / "hist" / f"{ent.replace(':', '_')}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    storage.write_parquet_atomic(df, p)
    return {"entity": ent, "period": "hist", "days": len(df), "units": len(used), "missing_units": len(miss),
            "capped_bars": int(df["capped_bars"].sum()) if len(df) else 0, "seconds": round(time.time() - t0, 1)}


def _work_hist(args):
    while free_mb() < MIN_FREE_MB:
        time.sleep(20)
    try:
        return hist_entity(*args)
    except Exception as e:  # noqa: BLE001
        return {"entity": args[0], "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}


def run_hist(workers, limit, only):
    import e2_compute as E
    test_guard.check([E.E2_FIRST, E.E2_LAST], purpose="VP2 histórico", script="vp_build")
    ents, ua, member = E.plan()
    if only:
        ents = [e for e in ents if e in set(only.split(","))]
    todo = [e for e in ents if not (OUT / "hist" / f"{e.replace(':', '_')}.parquet").exists()][: limit or None]
    groups = {e: g for e, g in ua.groupby("entity")}
    jobs = [(e, groups[e], member.get(e, [])) for e in todo]
    print(f"hist: entidades {len(ents)}, pendientes {len(jobs)}", flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with heavy_lock.HeavyJob("vp_build hist"), Pool(workers, initializer=_init_hist) as pool, \
            LOG.open("a", encoding="utf-8") as log:
        for k, r in enumerate(pool.imap_unordered(_work_hist, jobs), 1):
            log.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            log.flush()
            if k % 25 == 0 or r.get("error"):
                print(f"{k}/{len(jobs)} {r['entity']}: {r.get('error') or str(r['days']) + ' días'} · "
                      f"{round(time.time() - t0)} s", flush=True)
    print(f"hist terminado en {round(time.time() - t0)} s", flush=True)


# ── reciente (desde 2026-09-15) ────────────────────────────────────────────────────────────────────────────────
def run_recent(only: str = None):
    from micro import event_universe, identity, runtime
    from micro.manifest import Manifest
    last = max(d for d in calendar.trading_days(RECENT_FIRST, pd.Timestamp.now("UTC").strftime("%Y-%m-%d"))
               if sessions.bounds(d)["full_close"] < pd.Timestamp.now("UTC"))
    days = calendar.trading_days(RECENT_FIRST, last)
    test_guard.check(days, purpose="VP2 reciente", script="vp_build")
    u = event_universe.current_universe()
    syms = sorted(s for s in u["symbols"] if s not in u.get("not_covered", {}))
    if only:
        syms = [s for s in syms if s in set(only.split(","))]
    issuer = {}
    if event_universe.registry_available():
        memb = event_universe._registry()[1]
        cur = memb[memb["end_method"] == "open"]
        issuer = {r.symbol: str(r.issuer) for r in cur.itertuples() if str(r.issuer).isdigit()}
    prov = runtime.alpaca()
    ca = prov.corporate_actions(syms, days[0], last)
    corp = {}
    for typ, items in ca.items():
        for it in items or []:
            s = it.get("symbol") or it.get("old_symbol") or it.get("target_symbol")
            d = it.get("ex_date") or it.get("effective_date") or it.get("process_date")
            if s and d and days[0] <= d <= last:
                corp.setdefault(s, []).append((typ, d))
    m = Manifest()
    t0 = time.time()
    with heavy_lock.HeavyJob("vp_build recent"), LOG.open("a", encoding="utf-8") as log:
        for k, s in enumerate(syms, 1):
            ent = issuer.get(s, f"T:{s}")
            sp = identity.split_events(ca, s)
            sp = sp[(sp["ex_date"] > days[0]) & (sp["ex_date"] <= last)] if len(sp) else sp
            bars = F.load_bars(s, days, m)
            cdays = {d for _, d in corp.get(s, [])}
            rows = day_rows(bars, lambda d: {"entity": ent, "symbol": s, "period": "recent", "member": True,
                                              "corp_event": d in cdays and d not in set(sp["ex_date"] if len(sp) else []),
                                              "split_day": d in set(sp["ex_date"] if len(sp) else []),
                                              "outage": False, "split_factor_to_last": split_factor_to_last(d, sp)})
            if not rows:
                continue
            df = common_cols(pd.DataFrame(rows))
            # emisor + símbolo: un emisor con varias clases (GOOG/GOOGL, FOX/FOXA, NWS/NWSA) comparte CIK
            p = OUT / "recent" / f"{ent.replace(':', '_')}__{s.replace('.', '-')}.parquet"
            p.parent.mkdir(parents=True, exist_ok=True)
            storage.write_parquet_atomic(df, p)
            log.write(json.dumps({"entity": ent, "symbol": s, "period": "recent", "days": len(df),
                                  "corp": corp.get(s, [])}, default=str) + "\n")
            if k % 100 == 0:
                print(f"{k}/{len(syms)} · {round(time.time() - t0)} s", flush=True)
    print(f"recent: {len(syms)} símbolos, {len(days)} sesiones ({days[0]} → {last}), {round(time.time() - t0)} s")


# ── índice e integridad ────────────────────────────────────────────────────────────────────────────────────────
def build_index():
    rows = []
    for p in sorted(OUT.glob("*/*.parquet")):
        df = pd.read_parquet(p, columns=["entity", "symbol", "date", "period"])
        for (sym, per), g in df.groupby(["symbol", "period"]):
            rows.append({"symbol": sym, "entity": g["entity"].iloc[0], "period": per, "first": g["date"].min(),
                         "last": g["date"].max(), "days": len(g), "file": p.relative_to(OUT).as_posix()})
    idx = pd.DataFrame(rows)
    storage.write_parquet_atomic(idx, OUT / "_index.parquet")
    print(len(idx), "tramos símbolo-entidad")


def verify(sample=40, seed=7):
    import e2_compute as E
    files = sorted(OUT.glob("*/*.parquet"))
    res = {"files": len(files), "rows": 0, "reserved_dates": 0, "conservation_bad": 0, "stats_not_ok": 0,
           "params": set(), "versions": set(), "bytes": 0, "low_cov_days": 0, "capped_bars": 0, "flags": {}}
    for p in files:
        df = pd.read_parquet(p, columns=["date", "profile_volume", "bar_volume", "stats_ok", "params_sha256",
                                         "version", "cov", "capped_bars", "corp_event", "split_day", "outage"])
        res["rows"] += len(df)
        res["bytes"] += p.stat().st_size
        res["reserved_dates"] += int(df["date"].map(test_guard.reserved).sum())
        res["conservation_bad"] += int((np.abs(df["profile_volume"] - df["bar_volume"]) > 1e-3 * df["bar_volume"] + 1).sum())
        res["stats_not_ok"] += int((~df["stats_ok"]).sum())
        res["low_cov_days"] += int((df["cov"] < 0.5).sum())
        res["capped_bars"] += int(df["capped_bars"].sum())
        for f in ("corp_event", "split_day", "outage"):
            res["flags"][f] = res["flags"].get(f, 0) + int(df[f].sum())
        res["params"] |= set(df["params_sha256"])
        res["versions"] |= set(df["version"])
    # recálculo independiente de una muestra: misma salida byte a byte en las columnas del perfil
    rng = np.random.default_rng(seed)
    hist = [p for p in files if p.parent.name == "hist"]
    pick = [hist[i] for i in rng.choice(len(hist), size=min(sample, len(hist)), replace=False)] if hist else []
    _init_hist()
    ents, ua, member = E.plan()
    groups = {e: g for e, g in ua.groupby("entity")}
    same = diff = 0
    for p in pick[:8]:
        ent = pd.read_parquet(p, columns=["entity"])["entity"].iloc[0]
        old = pd.read_parquet(p, columns=["date", "lvl0", "vols", "poc_price", "va_low", "va_high"])
        tmp = storage.root() / "tmp" / "vp_verify"
        g0 = OUT
        globals()["OUT"] = tmp
        try:
            hist_entity(ent, groups[ent], member.get(ent, []))
            new = pd.read_parquet(tmp / "hist" / p.name, columns=["date", "lvl0", "vols", "poc_price", "va_low", "va_high"])
        finally:
            globals()["OUT"] = g0
        eq = old["lvl0"].equals(new["lvl0"]) and all(np.array_equal(a, b) for a, b in zip(old["vols"], new["vols"])) \
            and old[["poc_price", "va_low", "va_high"]].equals(new[["poc_price", "va_low", "va_high"]])
        same += eq
        diff += not eq
    res["recompute_sample"] = {"entities": same + diff, "identical": same, "different": diff}
    res["params"], res["versions"] = sorted(res["params"]), sorted(res["versions"])
    res["mb"] = round(res.pop("bytes") / 2**20, 1)
    out = storage.root() / "results" / "vp2" / "verify.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    h = sp.add_parser("hist")
    h.add_argument("--workers", type=int, default=4)
    h.add_argument("--limit", type=int)
    h.add_argument("--entities")
    rc = sp.add_parser("recent")
    rc.add_argument("--symbols")
    for c in ("verify", "index"):
        sp.add_parser(c)
    a = ap.parse_args()
    if a.cmd == "hist":
        run_hist(a.workers, a.limit, a.entities)
    elif a.cmd == "recent":
        run_recent(a.symbols)
    elif a.cmd == "verify":
        verify()
    else:
        build_index()


if __name__ == "__main__":
    main()
