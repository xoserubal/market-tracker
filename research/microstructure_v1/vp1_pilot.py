"""VP1 — piloto de fidelidad del Volume Profile: perfil ESTIMADO con barras de 1 minuto frente a perfil OBSERVADO con
trades (autorización del usuario, 2026-11-21). No genera perfiles históricos masivos.

Muestra (fijada antes de mirar resultados):
- A: todas las sesiones con trades de la sesión regular completa ya descargados fuera del periodo reservado de G2A
  (B1q de G2: 2016-2021, liquidez media y baja; AAPL, GOOGL, NVDA, HIMS de noviembre de 2026).
- B: sesión regular de 2026-11-18, 19 y 20 de 12 valores del universo E3 elegidos al azar (semilla 20261121), 4 por
  tercil de liquidez (nº medio de operaciones por sesión en esos tres días, de las barras guardadas). Excluye ETFs de
  contexto y valores con split en noviembre.
Comparación en la sesión regular [apertura, cierre): barras de esos minutos frente a trades de esos minutos con la
misma regla de volumen (upd_vol). Variantes observadas: sin comunicaciones tardías, sin subastas y con la subasta de
cierre (que se imprime a las 16:00 y no entra en las barras de la sesión regular).
Rejillas: 0,05 %, 0,10 % y 0,25 % del precio de referencia (mediana de los trades continuos del día).
Reparto dentro de la barra: cierre, VWAP de la barra, uniforme [mín, máx], triangular centrada en el VWAP.

Uso:
  py -3 vp1_pilot.py select              # fija la muestra y estima el coste de la parte B
  py -3 vp1_pilot.py fetch [--confirm]    # trae los trades que faltan de la parte B (con los límites del laboratorio)
  py -3 vp1_pilot.py run                  # calcula y escribe results/vp1/
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, episode, event_universe, intraday_features as F, sessions, storage, test_guard, \
    volume_profile as VP, window_access  # noqa: E402
from micro.manifest import Manifest  # noqa: E402

OUT = storage.root() / "results" / "vp1"
SAMPLE = OUT / "sample.json"
SEED = 20261121
B_DAYS = ["2026-11-18", "2026-11-19", "2026-11-20"]
RELS = (0.0005, 0.001, 0.0025)
MAX_ROWS = 4_000_000              # un día con más trades se omite (memoria); queda anotado


def regular_covered(symbol, day, m) -> bool:
    units = episode.units_for(symbol, day, "trades", m)
    if not units:
        return False
    cov = episode.coverage_windows(units, day)
    b = sessions.bounds(day)
    t, ok = b["open"], False
    for a, z in sorted(cov):
        if a <= t:
            t = max(t, z)
    return t >= b["close"]


def select():
    m = Manifest()
    rows = m.rows("kind='trades' AND status='ok'")
    pairs = sorted({(r["symbol"], r["period"]) for r in rows if not test_guard.reserved(r["period"])})
    part_a = [{"symbol": s, "day": d, "part": "A"} for s, d in pairs if regular_covered(s, d, m)]
    u = event_universe.current_universe()
    ctx = set(event_universe.CONTEXT) | {s for s, src in u["symbols"].items() if src == ["market_tracker"]}
    cand = [s for s in u["symbols"] if s not in ctx and s not in u.get("not_covered", {})]
    liq = {}
    for s in cand:
        bars = F.load_bars(s, B_DAYS, m)
        if not len(bars) or bars["_day"].nunique() < 3:
            continue
        reg = []
        for d, g in bars.groupby("_day"):
            b = sessions.bounds(d)
            reg.append(g[(g["t"] >= b["open"]) & (g["t"] < b["close"])]["n"].sum())
        liq[s] = float(np.mean(reg))
    ser = pd.Series(liq).sort_values()
    terc = pd.qcut(ser, 3, labels=["baja", "media", "alta"])
    rng = np.random.default_rng(SEED)
    part_b = []
    for t in ("baja", "media", "alta"):
        pool = sorted(terc[terc == t].index)
        for s in rng.choice(pool, size=4, replace=False):
            for d in B_DAYS:
                part_b.append({"symbol": str(s), "day": d, "part": "B", "liquidity_tercile": t,
                               "mean_trades_regular": round(liq[s])})
    est = []
    for x in part_b:
        e = window_access.estimate(x["symbol"], x["day"], "09:30", "16:01", quotes=False)
        est.append(e["kinds"]["trades"]["requests_est"])
    out = {"seed": SEED, "b_days": B_DAYS, "rels": RELS, "methods": VP.METHODS, "part_a": part_a, "part_b": part_b,
           "part_b_requests_est": int(sum(est)), "liquidity_cut_points": [float(ser.quantile(1 / 3)), float(ser.quantile(2 / 3))],
           "fixed_utc": pd.Timestamp.now("UTC").isoformat()}
    OUT.mkdir(parents=True, exist_ok=True)
    if SAMPLE.exists():
        raise SystemExit("la muestra ya está fijada")
    SAMPLE.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in out.items()}, indent=1))


def fetch(confirm: bool):
    s = json.loads(SAMPLE.read_text(encoding="utf-8"))
    tot = 0
    for x in s["part_b"]:
        r = window_access.fetch(x["symbol"], x["day"], "09:30", "16:01", quotes=False, confirm=confirm,
                                provider=__import__("micro.runtime", fromlist=["alpaca"]).alpaca(), purpose="VP1 piloto")
        n = (r.get("result") or {}).get("requests", 0)
        tot += n
        print(x["symbol"], x["day"], r["status"], n, flush=True)
        if r["status"] in ("blocked", "needs_confirmation"):
            print(json.dumps(r["estimate"].get("blocked") or "confirmación necesaria", ensure_ascii=False))
            break
    print("peticiones", tot)


def one(symbol, day, m):
    b = sessions.bounds(day)
    units = episode.units_for(symbol, day, "trades", m)
    if sum(int(u["rows"] or 0) for u in units) > MAX_ROWS * 1.6:
        return [{"symbol": symbol, "day": day, "skipped": "demasiadas filas para la memoria"}]
    tr, _ = episode.load_trades(symbol, day, m, window=(b["open"], b["close"] + pd.Timedelta(minutes=1)), dedupe_ids=True)
    if tr.empty:
        return [{"symbol": symbol, "day": day, "skipped": "sin trades"}]
    tr["segment"] = sessions.classify_trades(tr, day).astype(str).to_numpy()
    bars = F.load_bars(symbol, [day], m)
    bars = bars[(bars["t"] >= b["open"]) & (bars["t"] < b["close"])]
    if bars.empty:
        return [{"symbol": symbol, "day": day, "skipped": "sin barras"}]
    reg = tr[tr["t"] < b["close"]]
    cont = reg[reg["segment"] == "continuous"]
    ref = float(cont["price"].median()) if len(cont) else float(reg["price"].median())
    out = []
    obs_vol = float(reg.loc[reg["upd_vol"] & ~reg["canceled"], "size"].sum())
    base = {"symbol": symbol, "day": day, "ref_price": ref, "trades_regular": int(len(reg)),
            "bars_regular": int(len(bars)), "bar_volume": float(bars["v"].sum()), "trade_volume_rule": obs_vol,
            "late_share": float(reg.loc[(reg["segment"] == "late_report") & reg["upd_vol"], "size"].sum() / obs_vol) if obs_vol else None,
            "close_auction_shares": float(tr.loc[tr["segment"] == "close_auction", "size"].sum())}
    pocs = {}
    for rel in RELS:
        step = VP.grid_step(ref, rel)
        obs = {"all": VP.observed(reg, step), "no_late": VP.observed(reg, step, exclude_late=True),
               "no_auctions": VP.observed(reg, step, exclude_auctions=True), "with_close_auction": VP.observed(tr, step)}
        pocs[rel] = VP.value_area(obs["all"])[2] * step if len(obs["all"]) else None
        for meth in VP.METHODS:
            est = VP.estimated(bars, step, meth)
            for variant, o in obs.items():
                if variant != "all" and meth not in ("vwap", "uniform"):
                    continue                    # las variantes observadas se comparan con dos repartos, no con todos
                out.append({**base, "rel": rel, "step": step, "method": meth, "observed_variant": variant,
                            "profile_estimated": "estimated_bars_1m", "profile_observed": "observed_trades",
                            **VP.compare(est, o, step, ref)})
    # sensibilidad del POC observado al tamaño del nivel (en pb del precio)
    ps = [p for p in pocs.values() if p is not None]
    for r in out:
        r["obs_poc_range_across_grids_bps"] = round((max(ps) - min(ps)) / ref * 1e4, 2) if ps else None
    return out


def run():
    s = json.loads(SAMPLE.read_text(encoding="utf-8"))
    m = Manifest()
    rows, t0 = [], time.time()
    items = s["part_a"] + s["part_b"]
    for i, x in enumerate(items):
        if not regular_covered(x["symbol"], x["day"], m):
            rows.append({**x, "skipped": "sin la sesión regular completa de trades"})
            continue
        try:
            for r in one(x["symbol"], x["day"], m):
                rows.append({**x, **r})
        except Exception as e:  # noqa: BLE001
            rows.append({**x, "skipped": f"{type(e).__name__}: {e}"})
        if (i + 1) % 20 == 0:
            print(f"{i + 1}/{len(items)} · {round(time.time() - t0)} s", flush=True)
    df = pd.DataFrame(rows)
    storage.write_parquet_atomic(df, OUT / "comparisons.parquet")
    ok = df[df.get("ok", False) == True]  # noqa: E712
    ok = ok.assign(liq=ok["liquidity_tercile"].fillna("A (2016-2021 y nov-2026)") if "liquidity_tercile" in ok else "A")
    ok = ok.assign(period=np.where(ok["day"] < "2022-01-01", "2016-2021", "2026"))
    agg = lambda g: pd.Series({"n": len(g), "poc_same": g["poc_same"].mean(), "poc_diff_bps_med": g["poc_diff_bps"].median(),  # noqa: E731
                               "poc_diff_bps_p90": g["poc_diff_bps"].quantile(0.9), "va_jaccard_med": g["va_jaccard"].median(),
                               "va_mid_shift_bps_med": g["va_mid_shift_bps"].median(), "tvd_med": g["tvd"].median(),
                               "hvn_jaccard_med": g["hvn_jaccard"].median(),
                               "poc_vol_ratio_med": g["poc_est_obs_volume_ratio"].median(),
                               "poc_vol_ratio_p10": g["poc_est_obs_volume_ratio"].quantile(0.1),
                               "poc_off_below_half": (g["poc_est_obs_volume_ratio"] < 0.5).mean(),
                               "top1_obs_med": g["top1_share_obs"].median(), "top1_est_med": g["top1_share_est"].median(),
                               "vol_ratio_med": g["volume_ratio_est_obs"].median()})
    a = ok[ok["observed_variant"] == "all"]
    summary = {
        "sessions_compared": int(ok[["symbol", "day"]].drop_duplicates().shape[0]),
        "skipped": df[df.get("skipped").notna()][["symbol", "day", "skipped"]].drop_duplicates().to_dict("records") if "skipped" in df else [],
        "by_method_grid": a.groupby(["method", "rel"]).apply(agg).round(4).reset_index().to_dict("records"),
        "by_method_liquidity_grid010": a[a["rel"] == 0.001].groupby(["method", "liq"]).apply(agg).round(4).reset_index().to_dict("records"),
        "by_method_period_grid010": a[a["rel"] == 0.001].groupby(["method", "period"]).apply(agg).round(4).reset_index().to_dict("records"),
        "observed_variants_vwap_grid010": ok[(ok["method"] == "vwap") & (ok["rel"] == 0.001)].groupby("observed_variant")
            .apply(agg).round(4).reset_index().to_dict("records"),
        "obs_poc_range_across_grids_bps": a.drop_duplicates(["symbol", "day"])["obs_poc_range_across_grids_bps"].describe().round(2).to_dict(),
        "bar_vs_trade_volume": (a.drop_duplicates(["symbol", "day"])["bar_volume"] /
                                a.drop_duplicates(["symbol", "day"])["trade_volume_rule"]).describe().round(4).to_dict(),
        "late_share": a.drop_duplicates(["symbol", "day"])["late_share"].describe().round(4).to_dict(),
        "seconds": round(time.time() - t0, 1)}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("sessions_compared", "seconds")}))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("select")
    f = sp.add_parser("fetch")
    f.add_argument("--confirm", action="store_true")
    sp.add_parser("run")
    a = ap.parse_args()
    {"select": select, "fetch": lambda: fetch(a.confirm), "run": run}[a.cmd]()


if __name__ == "__main__":
    main()
