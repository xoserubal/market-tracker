"""Laboratorio visual de microestructura (G1.5) — servidor local, solo 127.0.0.1.

    py -3 lab/server.py [--port 8765]      ->  http://127.0.0.1:8765

Independiente de Market Tracker (server.js) y fuera de la web pública: lee los datos privados de MICRO_DATA_DIR
y nunca los copia al repositorio. Todo cálculo sale de micro/ (aggressor, footprint, library): el navegador solo dibuja.

Modo ciego: con blind=1 y un cursor, el servidor solo usa trades anteriores al cursor; lo posterior no sale del
servidor. Cada petición de datos queda en library/access_log.jsonl (hasta qué instante se mostró), y de ahí se
deduce si una anotación es retrospectiva.
"""
import argparse
import json
import os
import sys
import threading
import traceback
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from micro import aggressor, calendar, config, episode, footprint, runtime  # noqa: E402
from micro.library import LABELS, Library, in_test_period, ts_iso  # noqa: E402

LIMITATIONS = [
    "El lado agresor es una ESTIMACIÓN: Alpaca no publica quién inició cada operación.",
    "Concordancia entre métodos no es exactitud: no hay una verdad conocida con la que comparar.",
    "Los trades fuera de mercado (código D, FINRA TRF) llevan la hora de comunicación, no la de ejecución.",
    "Las subastas (apertura/cierre) son volumen real sin agresor: se muestran aparte.",
    "Sin libro de órdenes no se ve la absorción pasiva: solo se infiere (volumen agresor alto sin avance del precio).",
    "Una etiqueta describe lo observado en las ejecuciones, no la intención de los participantes.",
]

_cache = OrderedDict()
_cache_lock = threading.Lock()
_load_lock = threading.Lock()      # un solo día cargándose a la vez: limita el pico de memoria
_jobs = {}
LIB = None

# Control de memoria (2026-11-15: un análisis en paralelo agotó la memoria y colgó la descarga). Antes de cargar un
# día se estima el pico con lo medido (≈130 B por trade clasificado ×2 de temporales, ≈120 B por quote) y se exige
# dejar libre una reserva para el resto del equipo (descargas incluidas). Si no cabe, se vacía la caché y, si
# sigue sin caber, se rechaza con un mensaje en vez de arriesgar la descarga.
RESERVE_MB = int(os.environ.get("MICRO_LAB_RESERVE_MB", "2500"))
CACHE_MAX = int(os.environ.get("MICRO_LAB_CACHE_DAYS", "2"))


class MemoryGuardError(RuntimeError):
    pass


def _avail_mb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e6
    except Exception:  # noqa: BLE001
        return float("inf")


def estimate_peak_mb(symbol: str, day: str) -> float:
    s = episode.sizes(symbol, day)
    return (s["trades"]["rows"] * 260 + s["quotes"]["rows"] * 120) / 1e6


def ensure_memory(symbol: str, day: str):
    need = estimate_peak_mb(symbol, day)
    if _avail_mb() - need >= RESERVE_MB:
        return need
    with _cache_lock:
        _cache.clear()
    import gc
    gc.collect()
    avail = _avail_mb()
    if avail - need < RESERVE_MB:
        raise MemoryGuardError(f"memoria insuficiente para cargar {symbol} {day}: harían falta ~{need:.0f} MB y "
                               f"hay {avail:.0f} MB libres (reserva {RESERVE_MB} MB para el resto del equipo y las "
                               f"descargas). Prueba con una ventana más corta o cuando terminen las descargas.")
    return need


def classified(symbol: str, day: str, opts: dict):
    key = (symbol, day, tuple(sorted(opts.items())))
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    with _load_lock:
        with _cache_lock:
            if key in _cache:
                return _cache[key]
        ensure_memory(symbol, day)
        return _load_classified(symbol, day, opts, key)


def _load_classified(symbol, day, opts, key):
    tr, tcov = episode.load_trades(symbol, day)
    if tr.empty:
        return None
    q, qcov = episode.load_quotes(symbol, day)
    c = aggressor.classify(tr, q if len(q) else None, qcov, **opts)
    val = {"tr": c, "trade_cov": tcov, "quote_cov": qcov, "n_quotes": int(len(q))}
    with _cache_lock:
        _cache[key] = val
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return val


def parse_ny(day: str, s: str):
    """'HH:MM' o 'HH:MM:SS' en hora de Nueva York -> Timestamp UTC."""
    if not s:
        return None
    parts = s.split(":")
    base = calendar.ny_range(day, f"{parts[0]}:{parts[1]}", "23:59")[0]
    return base + pd.Timedelta(seconds=int(parts[2]) if len(parts) > 2 else 0)


def _opts(q):
    return {"quote_lag_ms": float(q.get("quote_lag_ms", 0)), "strict_before": q.get("strict", "1") == "1",
            "max_quote_age_s": float(q.get("max_quote_age_s", 10)), "ref_exclude_trf": q.get("ref_exclude_trf") == "1",
            "ref_exclude_nonbar": q.get("ref_exclude_nonbar") == "1"}


def api_footprint(q):
    sym, day = q["symbol"].upper(), q["day"]
    try:
        val = classified(sym, day, _opts(q))
    except MemoryGuardError as e:
        return {"error": str(e), "memory_guard": True}
    if val is None:
        return {"error": "sin trades descargados para ese valor y día", "need_fetch": True}
    tr = val["tr"]
    start, end = parse_ny(day, q.get("start")), parse_ny(day, q.get("end"))
    blind = q.get("blind") == "1"
    cursor = parse_ny(day, q.get("cursor")) if q.get("cursor") else None
    data_cursor = cursor if blind else None
    sess = ("pre", "regular", "post") if q.get("session") == "extended" else ("regular",)
    step = float(q["step"]) if q.get("step") not in (None, "", "auto") else None
    method = q.get("method", "lr")
    if method not in aggressor.METHODS:
        return {"error": f"método desconocido {method}"}
    kw = dict(start=start, end=end, cursor=data_cursor)
    filt = dict(exclude_trf=q.get("exclude_trf") == "1", exclude_odd=q.get("exclude_odd") == "1",
                exclude_nonbar=q.get("exclude_nonbar") == "1")
    fp = footprint.build(tr, day, method=method, tf_minutes=int(q.get("tf", 60)), step=step, sessions=sess,
                         **filt, **kw)
    fp["method_compare"] = footprint.compare_methods(tr, day, tf_minutes=int(q.get("tf", 60)), sessions=sess,
                                                     **filt, **kw)
    fp["classification_options"] = _opts(q)
    sel = tr[tr["session"].isin(list(sess))]
    for lim, op in ((start, "ge"), (end, "lt"), (data_cursor, "lt")):
        if lim is not None:
            sel = sel[sel["t"] >= lim] if op == "ge" else sel[sel["t"] < lim]
    fp["timeline"] = footprint.timeline(sel, method=method, seconds=int(q.get("timeline_s", 60)))
    fp["methods_summary"] = aggressor.summary(sel) if len(sel) else {}
    max_t = sel["t"].max() if len(sel) else None
    fp.update({"symbol": sym, "day": day, "blind": blind, "cursor": ts_iso(cursor) if cursor is not None else None,
               "max_t_returned": ts_iso(max_t) if max_t is not None else None,
               "trade_coverage": [[ts_iso(a), ts_iso(b)] for a, b in val["trade_cov"]],
               "quote_coverage": [[ts_iso(a), ts_iso(b)] for a, b in val["quote_cov"]],
               "n_quotes_loaded": val["n_quotes"], "in_test_period": in_test_period(day),
               "regular_open": ts_iso(calendar.session_bounds(day, "regular")[0]),
               "regular_close": ts_iso(calendar.session_bounds(day, "regular")[1]),
               "limitations": LIMITATIONS, "code_version": config.code_version()})
    Library.log_access({"symbol": sym, "day": day, "start": q.get("start"), "end": q.get("end"),
                        "cursor": fp["cursor"], "blind": blind, "max_t_returned": fp["max_t_returned"],
                        "endpoint": "footprint", "viewer": "lab-v1"})
    return fp


def api_available(_q):
    from micro.manifest import Manifest
    rows = Manifest().rows("kind IN ('trades','quotes') AND status='ok'")
    out = {}
    for r in rows:
        k = f"{r['symbol']}|{r['period']}"
        d = out.setdefault(k, {"symbol": r["symbol"], "day": r["period"], "trade_units": 0, "quote_units": 0,
                               "rows": 0, "in_test_period": in_test_period(r["period"])})
        d["trade_units" if r["kind"] == "trades" else "quote_units"] += 1
        d["rows"] += r["rows"] or 0
    return {"days": sorted(out.values(), key=lambda d: (d["day"], d["symbol"]))}


def _run_fetch(job_id, sym, day, ranges):
    try:
        _jobs[job_id]["status"] = "running"
        res = episode.fetch_day(runtime.alpaca(), sym, day, quote_ranges=ranges)
        _jobs[job_id].update(status="done", result=[{k: r.get(k) for k in ("status", "rows", "requests")} for r in res],
                             sizes=episode.sizes(sym, day))
        with _cache_lock:
            for k in [k for k in _cache if k[0] == sym and k[1] == day]:
                _cache.pop(k)
    except Exception as e:  # noqa: BLE001
        _jobs[job_id].update(status="failed", error=f"{type(e).__name__}: {e}")


def api_estimate(q):
    ranges = [r for r in q.get("quote_ranges", "").split(",") if r]
    return episode.estimate(runtime.alpaca(), q["symbol"].upper(), q["day"], ranges)


def api_fetch(body):
    sym, day = body["symbol"].upper(), body["day"]
    if not calendar.is_trading_day(day):
        return {"error": "no es sesión de mercado"}
    ranges = body.get("quote_ranges", [])
    est = episode.estimate(runtime.alpaca(), sym, day, ranges)
    pages = est.get("trade_pages_est", 0) + sum(w["pages_est_high"] for w in est.get("quote_windows", []))
    if pages > 4000 and not body.get("confirm_large"):
        return {"error": "descarga grande: confirma explícitamente", "estimate": est, "pages_est": pages}
    jid = uuid.uuid4().hex[:8]
    _jobs[jid] = {"symbol": sym, "day": day, "status": "queued", "estimate": est, "in_test_period": in_test_period(day)}
    threading.Thread(target=_run_fetch, args=(jid, sym, day, ranges), daemon=True).start()
    return {"job": jid, **_jobs[jid]}


def api_episode_create(body):
    sym, day = body["symbol"].upper(), body["day"]
    q = {**body.get("view", {}), "symbol": sym, "day": day}
    try:
        val = classified(sym, day, _opts(q))
    except MemoryGuardError as e:
        return {"error": str(e), "memory_guard": True}
    if val is None:
        return {"error": "sin datos"}
    a, b = parse_ny(day, body["start"]), parse_ny(day, body["end"])
    sel = val["tr"][(val["tr"]["t"] >= a) & (val["tr"]["t"] < b)]
    if sel.empty:
        return {"error": "intervalo sin trades"}
    method = q.get("method", "lr")
    fp = footprint.build(sel, day, method=method, tf_minutes=int(q.get("tf", 60)),
                         step=float(q["step"]) if q.get("step") not in (None, "", "auto") else None,
                         sessions=("pre", "regular", "post"))
    units = [{"unit_key": r["unit_key"], "sha256": r["sha256"], "kind": r["kind"]}
             for k in ("trades", "quotes") for r in episode.units_for(sym, day, k)]
    # Precios con las reglas oficiales de barras (máx/mín: upd_hl; primero/último: upd_oc), como el footprint;
    # con todos los trades entraban comunicaciones tardías fuera de rango (corregido 2026-11-15).
    hl = sel[sel["upd_hl"] & ~sel["canceled"]]
    oc = sel[(sel["upd_oc"] != "N") & ~sel["canceled"]]
    hl = hl if len(hl) else sel
    oc = oc if len(oc) else sel
    metrics = {"volume": fp["quality"]["volume"], "delta": int(sum(x["delta"] for x in fp["bars"])),
               "value_area": fp["value_area"], "price_first": float(oc["price"].iloc[0]),
               "price_last": float(oc["price"].iloc[-1]), "price_min": float(hl["price"].min()),
               "price_max": float(hl["price"].max()), "methods_summary": aggressor.summary(sel)}
    eid = LIB.add_episode({"symbol": sym, "day": day, "start_utc": ts_iso(a), "end_utc": ts_iso(b),
                           "tf_minutes": int(q.get("tf", 60)), "method": method, "step": fp["step"],
                           "price_lo": body.get("price_lo"), "price_hi": body.get("price_hi"),
                           "proposed_label": body.get("proposed_label") or None, "data_units": units,
                           "params": {**q, **_opts(q)}, "metrics": metrics, "quality": fp["quality"],
                           "selection_note": body.get("selection_note", ""),
                           "outcome_known_at_selection": body.get("outcome_known_at_selection", False),
                           "company": body.get("company"), "created_by": "human"})
    return {"episode_id": eid}


ROUTES_GET = {"/api/footprint": api_footprint, "/api/available": api_available, "/api/estimate": api_estimate,
              "/api/labels": lambda q: {"labels": LABELS},
              "/api/jobs": lambda q: {"jobs": _jobs},
              "/api/library/episodes": lambda q: {"episodes": LIB.episodes(q.get("symbol"), q.get("day"))},
              "/api/library/annotations": lambda q: {"annotations": LIB.annotations(q.get("episode_id"))},
              "/api/library/contamination": lambda q: {"test_period_accessed": LIB.contaminated_test_dates()}}
ROUTES_POST = {"/api/fetch": api_fetch, "/api/library/episode": api_episode_create,
               "/api/library/annotate": lambda b: {"annotation_id": LIB.annotate(b)}}
STATIC = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
CTYPE = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in STATIC:
            f = HERE / STATIC[u.path]
            return self._send(200, f.read_bytes(), CTYPE[f.suffix])
        fn = ROUTES_GET.get(u.path)
        if not fn:
            return self._send(404, {"error": "no existe"})
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            return self._send(200, _clean(fn(q)))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(400, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        u = urlparse(self.path)
        fn = ROUTES_POST.get(u.path)
        if not fn:
            return self._send(404, {"error": "no existe"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            return self._send(200, _clean(fn(body)))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(400, {"error": f"{type(e).__name__}: {e}"})


def _clean(o):
    """NaN/inf -> None y tipos numpy -> nativos, para JSON estricto."""
    import math

    import numpy as np
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def make_server(port: int, library: Library = None):
    global LIB
    LIB = library or Library()
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv = make_server(a.port)
    print(f"Laboratorio de microestructura: http://127.0.0.1:{a.port}", flush=True)
    srv.serve_forever()
