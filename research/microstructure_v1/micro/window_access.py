"""Acceso libre a la negociación (2026-11-21): cualquier valor, fecha y ventana, haya o no alerta.

- estimate(): coste previsto de traer trades y quotes de una ventana, descontando lo ya descargado. Usa las barras de
  1 minuto guardadas (el nº de trades de cada minuto) y, si no las hay, una petición de barras a Alpaca.
- fetch(): trae solo lo que falta, con límites (ventana máxima, peticiones por descarga y presupuesto diario) y una
  confirmación explícita por encima de un umbral. Cada descarga queda en results/lab_access/fetch_log.jsonl.
- tape(): las operaciones y cotizaciones de la ventana, con su tramo (subasta de apertura, negociación continua,
  subasta de cierre, reapertura, pre/after hours) y las marcas que importan para leerlas: comunicación tardía, lote
  impar, TRF, operación cancelada. Para el navegador se reducen los puntos, pero los recuentos y volúmenes por tramo
  son siempre los completos.
- multi_session(): barras de varias sesiones a resoluciones de 1, 5, 15 o 60 minutos o diaria, con el tramo de cada
  barra, desde la capa 1 (sin pedir nada al proveedor).

No interpreta intención. El periodo reservado de G2A está bloqueado por defecto.
"""
import json
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import calendar, download, drilldown, episode, intraday_features as F, sessions, storage, test_guard
from .manifest import Manifest

LIMITS = {
    "max_window_min_trades": 960,        # una sesión completa 04:00-20:00
    "max_window_min_quotes": 120,        # las quotes pesan ≈ 1,3-3,5 veces los trades
    "confirm_above_requests": 150,       # por encima, hace falta confirmar
    "max_requests_per_fetch": 1500,
    "daily_requests": 6000,              # todo el laboratorio en 24 h (el límite de Alpaca es 200/min)
    "max_points_tape": 25000,
}
BYTES_PER_TRADE = 10.71                  # medido en G0
BYTES_PER_QUOTE = 9.0
QUOTES_PER_TRADE = {"median": 1.3, "high": 3.5}   # G0, 7 acciones


def log_path():
    p = storage.root() / "results" / "lab_access"
    p.mkdir(parents=True, exist_ok=True)
    return p / "fetch_log.jsonl"


def requests_last_24h() -> int:
    p = log_path()
    if not p.exists():
        return 0
    cut = pd.Timestamp(datetime.now(timezone.utc)) - pd.Timedelta(hours=24)
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if pd.Timestamp(r["ts"]) >= cut:
            n += int(r.get("requests") or 0)
    return n


def parse_window(day: str, start: str, end: str) -> tuple:
    """'HH:MM' (Nueva York) -> UTC; sin hora: la sesión completa."""
    b = sessions.bounds(day)
    a = calendar.ny_range(day, start, "23:59")[0] if start else b["full_open"]
    z = calendar.ny_range(day, "00:00", end)[1] if end else b["full_close"]
    a, z = max(a, b["full_open"]), min(z, b["full_close"])
    if z <= a:
        raise ValueError("ventana vacía")
    return a, z


def _minute_trades(symbol, day, a, z, provider=None, m=None) -> tuple:
    bars = F.load_bars(symbol, [day], m)
    src = "capa1_barras"
    if not len(bars):
        if provider is None:
            return None, "sin barras locales"
        rows = []
        fo, fc = calendar.session_bounds(day, "full")
        from .providers.base import FetchStats
        for pg in provider.fetch_pages("bars", symbol, calendar.iso(fo), calendar.iso(fc), timeframe="1Min",
                                       stats=FetchStats()):
            rows.extend(pg)
        if not rows:
            return None, "sin barras en Alpaca"
        bars = pd.DataFrame(rows)
        bars["t"] = pd.to_datetime(bars["t"], utc=True)
        src = "alpaca_barras"
    sel = bars[(bars["t"] >= a) & (bars["t"] < z)]
    return sel[["t", "n"]].copy(), src


def estimate(symbol: str, day: str, start: str = None, end: str = None, *, quotes: bool = True, provider=None,
             allow_test: bool = False) -> dict:
    a, z = parse_window(day, start, end)
    reserved = test_guard.reserved(day)
    m = Manifest()
    mt, src = _minute_trades(symbol, day, a, z, provider, m)
    out = {"symbol": symbol, "day": day, "start_utc": a.isoformat(), "end_utc": z.isoformat(),
           "minutes": int((z - a).total_seconds() // 60), "in_reserved_period": reserved, "source": src,
           "limits": LIMITS, "requests_last_24h": requests_last_24h()}
    if mt is None:
        out["error"] = src
        return out
    per = {}
    for kind in ("trades", "quotes") if quotes else ("trades",):
        units = episode.units_for(symbol, day, kind, m)
        cov = episode.coverage_windows(units, day) if units else []
        need = drilldown._ranges_needed(day, a, z, cov)
        missing = []
        for rng in need:
            ra, rz = calendar.ny_range(day, *rng.split("-"))
            missing.append((ra, rz))
        n_missing = int(sum(mt[(mt["t"] >= ra) & (mt["t"] < rz)]["n"].sum() for ra, rz in missing))
        n_all = int(mt["n"].sum())
        if kind == "trades":
            rows, rows_hi = n_missing, n_missing
            bpr = BYTES_PER_TRADE
        else:
            rows, rows_hi = int(n_missing * QUOTES_PER_TRADE["median"]), int(n_missing * QUOTES_PER_TRADE["high"])
            bpr = BYTES_PER_QUOTE
        per[kind] = {"covered_ranges": [[x.isoformat(), y.isoformat()] for x, y in cov],
                     "missing_ranges": need, "trades_in_window": n_all, "rows_est": rows, "rows_est_high": rows_hi,
                     "requests_est": (math.ceil(rows_hi / 10000) + len(need)) if need else 0,
                     "mb_est_high": round(rows_hi * bpr / 1e6, 1)}
    out["kinds"] = per
    reqs = sum(v["requests_est"] for v in per.values())
    out["requests_est"] = reqs
    out["mb_est_high"] = round(sum(v["mb_est_high"] for v in per.values()), 1)
    out["checks"] = checks(out, quotes)
    out["needs_confirmation"] = reqs > LIMITS["confirm_above_requests"]
    out["blocked"] = [c for c in out["checks"] if c["block"]]
    if reserved and not allow_test:
        out["blocked"].append({"rule": "periodo_reservado", "block": True,
                               "detail": "fecha del periodo reservado de G2A: bloqueada salvo desbloqueo explícito"})
    return out


def checks(e: dict, quotes: bool) -> list:
    res = []
    if e["minutes"] > LIMITS["max_window_min_trades"]:
        res.append({"rule": "ventana_trades", "block": True, "detail": f"{e['minutes']} min > {LIMITS['max_window_min_trades']}"})
    if quotes and e["minutes"] > LIMITS["max_window_min_quotes"]:
        res.append({"rule": "ventana_quotes", "block": True,
                    "detail": f"quotes: {e['minutes']} min > {LIMITS['max_window_min_quotes']}; acorta la ventana o pide solo trades"})
    if e["requests_est"] > LIMITS["max_requests_per_fetch"]:
        res.append({"rule": "peticiones_por_descarga", "block": True,
                    "detail": f"{e['requests_est']} > {LIMITS['max_requests_per_fetch']}"})
    if e["requests_last_24h"] + e["requests_est"] > LIMITS["daily_requests"]:
        res.append({"rule": "presupuesto_diario", "block": True,
                    "detail": f"{e['requests_last_24h']} usadas en 24 h + {e['requests_est']} > {LIMITS['daily_requests']}"})
    return res


def fetch(symbol: str, day: str, start: str = None, end: str = None, *, quotes: bool = True, confirm: bool = False,
          provider=None, allow_test: bool = False, purpose: str = "") -> dict:
    est = estimate(symbol, day, start, end, quotes=quotes, provider=provider, allow_test=allow_test)
    if est.get("error"):
        return {"status": "error", "estimate": est}
    if est["blocked"]:
        return {"status": "blocked", "estimate": est}
    if est["needs_confirmation"] and not confirm:
        return {"status": "needs_confirmation", "estimate": est}
    if est["in_reserved_period"]:
        test_guard.check([day], symbol=symbol, purpose=purpose or "laboratorio: descarga manual", script="window_access",
                         allow=True)
    a, z = pd.Timestamp(est["start_utc"]), pd.Timestamp(est["end_utc"])
    t0 = time.time()
    r = drilldown.fetch(provider, symbol, day, (a, z), quotes_window=(a, z) if quotes else None,
                        budget={"max_requests": LIMITS["max_requests_per_fetch"], "max_seconds": 1800, "max_mb": 2000})
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "symbol": symbol, "day": day,
           "start_utc": est["start_utc"], "end_utc": est["end_utc"], "quotes": quotes, "requests": r["requests"],
           "requests_est": est["requests_est"], "mb": r["mb"], "seconds": round(time.time() - t0, 1),
           "units": r["units"], "purpose": purpose, "in_reserved_period": est["in_reserved_period"]}
    with log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return {"status": "done", "estimate": est, "result": rec}


# ── tramo de cada operación ────────────────────────────────────────────────────────────────────────────────────
# Mismo criterio que el desglose (sessions.classify_trades): subastas y reaperturas por su condición, comunicaciones
# tardías o con precio de referencia aparte, impresiones oficiales informativas, el resto por la hora.
SEGMENT_ORDER = ("pre", "open_auction", "continuous", "halt_reopen", "close_auction", "post", "late_report",
                 "nonstandard", "official_print", "canceled")


def segment_trades(tr: pd.DataFrame, day: str) -> pd.DataFrame:
    if tr.empty:
        return tr.assign(segment=pd.Series(dtype=str))
    return tr.assign(segment=sessions.classify_trades(tr, day).astype(str).to_numpy())


def tape(symbol: str, day: str, start: str = None, end: str = None, *, max_points: int = None,
         allow_test: bool = False) -> dict:
    if test_guard.reserved(day) and not allow_test:
        raise test_guard.TestPeriodLocked("fecha del periodo reservado de G2A")
    a, z = parse_window(day, start, end)
    tr, tcov = episode.load_trades(symbol, day, window=(a, z), dedupe_ids=True)
    q, qcov = episode.load_quotes(symbol, day, window=(a, z))
    out = {"symbol": symbol, "day": day, "start_utc": a.isoformat(), "end_utc": z.isoformat(),
           "trade_coverage": [[x.isoformat(), y.isoformat()] for x, y in tcov],
           "quote_coverage": [[x.isoformat(), y.isoformat()] for x, y in qcov],
           "session_bounds": {k: v.isoformat() for k, v in sessions.bounds(day).items() if isinstance(v, pd.Timestamp)}}
    if tr.empty:
        out.update(trades=[], quotes=[], summary={}, note="sin trades descargados en la ventana")
        return out
    dup = tr.attrs.get("duplicate_ids_removed", 0)
    tr = segment_trades(tr, day)
    tr["notional"] = tr["price"] * tr["size"]
    summ = {}
    for s in SEGMENT_ORDER:
        x = tr[tr["segment"] == s]
        if not len(x):
            continue
        v = x[x["upd_vol"]] if s != "canceled" else x
        summ[s] = {"trades": int(len(x)), "shares": int(x["size"].sum()), "shares_counted_in_volume": int(v["size"].sum()),
                   "notional": float(x["notional"].sum()), "odd_lot_trades": int(x["odd_lot"].sum()),
                   "trf_shares": int(x.loc[x["trf"], "size"].sum()), "price_min": float(x["price"].min()),
                   "price_max": float(x["price"].max()), "vwap": float(x["notional"].sum() / max(1, x["size"].sum()))}
    live = tr[tr["segment"] != "canceled"]
    summ["_all"] = {"trades": int(len(live)), "shares_counted_in_volume": int(live.loc[live["upd_vol"], "size"].sum()),
                    "canceled": int((tr["segment"] == "canceled").sum()),
                    "duplicate_ids_removed": dup}
    out["summary"] = summ
    # puntos para el navegador: todas las subastas, tardías y grandes; el resto muestreado de forma uniforme
    mp = max_points or LIMITS["max_points_tape"]
    big = live["size"] >= live["size"].quantile(0.99) if len(live) > 100 else pd.Series(True, index=live.index)
    keep = (live["segment"].isin(["open_auction", "close_auction", "halt_reopen", "late_report"]) | big)
    rest = live[~keep]
    room = max(0, mp - int(keep.sum()))
    if len(rest) > room:
        rest = rest.iloc[np.linspace(0, len(rest) - 1, room).astype(int)] if room else rest.iloc[:0]
    pts = pd.concat([live[keep], rest]).sort_values("t")
    out["sampled"] = len(pts) < len(live)
    out["trades"] = [{"t": int(r.t.value // 1_000_000), "p": r.price, "s": int(r.size), "seg": r.segment,
                      "odd": bool(r.odd_lot), "trf": bool(r.trf), "x": str(r.exchange), "c": str(r.conditions),
                      "vol": bool(r.upd_vol)} for r in pts.itertuples()]
    if not q.empty:
        q = q[(q["bid"] > 0) & (q["ask"] > 0) & (q["ask"] >= q["bid"])]
        qs = q.set_index("t")[["bid", "ask"]].resample("1s").last().dropna().reset_index()
        if len(qs) > mp:
            qs = qs.iloc[np.linspace(0, len(qs) - 1, mp).astype(int)]
        spr = (q["ask"] - q["bid"]) / ((q["ask"] + q["bid"]) / 2)
        out["quotes"] = [{"t": int(r.t.value // 1_000_000), "b": r.bid, "a": r.ask} for r in qs.itertuples()]
        out["quote_summary"] = {"quotes": int(len(q)), "spread_rel_median": float(spr.median()),
                                "spread_rel_p95": float(spr.quantile(0.95)), "resampled_to_1s": True}
    else:
        out["quotes"] = []
    return out


# ── varias sesiones ────────────────────────────────────────────────────────────────────────────────────────────
RESOLUTIONS = {"1": "1min", "5": "5min", "15": "15min", "60": "60min", "D": None}


def multi_session(symbol: str, start_day: str, end_day: str, res: str = "15", *, allow_test: bool = False) -> dict:
    days = calendar.trading_days(start_day, end_day)
    if not days:
        raise ValueError("sin sesiones en el intervalo")
    if len(days) > 260:
        raise ValueError("máximo 260 sesiones por consulta")
    bad = [d for d in days if test_guard.reserved(d)]
    if bad and not allow_test:
        raise test_guard.TestPeriodLocked(f"{len(bad)} sesiones del periodo reservado de G2A")
    bars = F.load_bars(symbol, days)
    out = {"symbol": symbol, "start_day": days[0], "end_day": days[-1], "sessions": len(days), "res": res}
    if not len(bars):
        out.update(bars=[], missing_days=days)
        return out
    bars = bars.sort_values("t")
    have = set(bars["_day"])
    out["missing_days"] = [d for d in days if d not in have]
    seg = []
    for d, g in bars.groupby("_day"):
        b = sessions.bounds(d)
        seg.append(pd.Series(np.where(g["t"] < b["open"], "pre", np.where(g["t"] >= b["close"], "post", "regular")),
                             index=g.index))
    bars["seg"] = pd.concat(seg)
    if res == "D":
        reg = bars[bars["seg"] == "regular"]
        agg = reg.groupby("_day").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
                                      v=("v", "sum"), n=("n", "sum"))
        ext = bars[bars["seg"] != "regular"].groupby("_day")["v"].sum()
        agg["v_ext"] = ext.reindex(agg.index).fillna(0)
        out["bars"] = [{"day": d, **{k: (float(v) if k not in ("v", "n", "v_ext") else int(v)) for k, v in r.items()}}
                       for d, r in agg.iterrows()]
        return out
    rule = RESOLUTIONS[res]
    rows = []
    for (d, s), g in bars.groupby(["_day", "seg"]):
        r = g.set_index("t").resample(rule, origin="start_day").agg({"o": "first", "h": "max", "l": "min", "c": "last",
                                                                       "v": "sum", "n": "sum"}).dropna(subset=["c"])
        for t, x in r.iterrows():
            rows.append({"t": int(t.value // 1_000_000), "day": d, "seg": s, "o": x.o, "h": x.h, "l": x.l, "c": x.c,
                         "v": int(x.v), "n": int(x.n)})
    rows.sort(key=lambda x: x["t"])
    if len(rows) > 60000:
        raise ValueError(f"{len(rows)} barras: elige una resolución menor o menos sesiones")
    out["bars"] = rows
    return out
