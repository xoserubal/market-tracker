"""Desglose de un episodio (o de cualquier valor, fecha y ventana) con trades y, si aportan, quotes (E1).

Qué hace:
1. Descarga (si falta) los trades de la ventana del episodio ±30 min. Si el episodio está a menos de 30 min del cierre,
   añade la subasta de cierre y la primera hora de after hours.
2. Separa los tramos exactos (sessions.segment_summary) y los compara con lo que estimaban las barras.
3. Rehace con trades la medida de cada alerta (reglas oficiales de barras) para detectar artefactos de agregación.
4. Perfil de volumen de la ventana (POC, área de valor), concentración por nivel (N1), operaciones grandes (N3) y
   comunicaciones tardías (C4).
5. Con quotes: diferencial y los cuatro clasificadores de agresor, con el volumen indeterminado de cada uno.

Las quotes solo se piden cuando aportan algo (catálogo: quotes_useful) o si se piden expresamente.
Nada aquí interpreta intención. Topes configurables de peticiones, tiempo y almacenamiento.
"""
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import aggressor, calendar, catalog_v1 as V1, config, download, episode, event_catalog as cat, event_store, footprint, \
    intraday_features as F, sessions, test_guard
from .manifest import Manifest

DEFAULT_BUDGET = {"max_requests": 400, "max_seconds": 900, "max_mb": 300}
PAD_MIN = 30


def _ny(ts):
    return pd.Timestamp(ts).tz_convert(sessions.NY).strftime("%H:%M")


def _ranges_needed(day: str, start: pd.Timestamp, end: pd.Timestamp, covered: list) -> list:
    """Tramos 'HH:MM-HH:MM' (NY) de [start, end) sin cubrir por las unidades de trades ya descargadas."""
    mins = pd.date_range(start, end, freq="1min", inclusive="left")
    need = [m for m in mins if not any(a <= m and m + pd.Timedelta(minutes=1) <= z for a, z in covered)]
    out, cur = [], None
    for m in need:
        if cur and m == cur[1]:
            cur[1] = m + pd.Timedelta(minutes=1)
        else:
            cur = [m, m + pd.Timedelta(minutes=1)]
            out.append(cur)
    return [f"{_ny(a)}-{_ny(b)}" for a, b in out]


def plan_window(day: str, t_start, t_end) -> tuple:
    b = sessions.bounds(day)
    a = max(pd.Timestamp(t_start) - pd.Timedelta(minutes=PAD_MIN), b["full_open"])
    z = min(pd.Timestamp(t_end) + pd.Timedelta(minutes=PAD_MIN), b["full_close"])
    if abs((pd.Timestamp(t_end) - b["close"]).total_seconds()) <= PAD_MIN * 60 or \
       abs((pd.Timestamp(t_start) - b["close"]).total_seconds()) <= PAD_MIN * 60:
        a = min(a, b["close"] - pd.Timedelta(minutes=10))
        z = max(z, min(b["close"] + pd.Timedelta(minutes=60), b["full_close"]))
    latest = pd.Timestamp(datetime.now(timezone.utc)) - pd.Timedelta(minutes=16)
    return a, min(z, latest.floor("min"))


def fetch(provider, symbol: str, day: str, window: tuple, *, quotes_window: tuple = None, budget: dict = None,
          manifest: Manifest = None) -> dict:
    budget = {**DEFAULT_BUDGET, **(budget or {})}
    m = manifest or Manifest()
    t0, reqs, mb, res = time.time(), 0, 0.0, []
    for kind, win in (("trades", window), ("quotes", quotes_window)):
        if win is None:
            continue
        cov = episode.coverage_windows(episode.units_for(symbol, day, kind, m), day) if episode.units_for(
            symbol, day, kind, m) else []
        for rng in _ranges_needed(day, win[0], win[1], cov):
            if reqs >= budget["max_requests"] or time.time() - t0 > budget["max_seconds"] or mb > budget["max_mb"]:
                res.append({"kind": kind, "range": rng, "status": "skipped_budget"})
                continue
            cfg = download.config_for(kind, session="regular", time_range=rng)
            r = download.download_unit(provider, kind, symbol, day, asof=None, cfg=cfg, manifest=m)
            reqs += int(r.get("requests") or 0)
            mb += (r.get("file_bytes") or 0) / 1e6
            res.append({"kind": kind, "range": rng, **{k: r.get(k) for k in ("status", "rows", "requests")}})
    return {"units": res, "requests": reqs, "mb": round(mb, 2), "seconds": round(time.time() - t0, 1)}


def _bar_price(tr: pd.DataFrame, at: pd.Timestamp):
    """Último precio con reglas de barras (upd_oc) estrictamente antes de `at`, solo continua/after hours estándar."""
    x = tr[(tr["t"] < at) & (tr["upd_oc"] != "N") & tr["_seg"].isin(["continuous", "post", "pre"])]
    return float(x["price"].iloc[-1]) if len(x) else None


def recheck_alert(tr: pd.DataFrame, a: dict) -> dict:
    """Rehace el desplazamiento de la alerta con trades. Una alerta de precio cuyo movimiento con trades es menos de la
    mitad que con barras se marca como artefacto de agregación."""
    if a["family"] not in ("D", "C", "PM", "I", "P") or "vol" in a["measure"] or a["measure"].startswith("V3"):
        return {"checked": False}
    p0, p1 = _bar_price(tr, pd.Timestamp(a["t_start_utc"])), _bar_price(tr, pd.Timestamp(a["t_end_utc"]))
    if not (p0 and p1):
        return {"checked": False, "reason": "sin trades en los extremos de la ventana"}
    r = float(np.log(p1 / p0))
    out = {"checked": True, "trade_return_pct": round(r * 100, 3), "price_start": p0, "price_end": p1}
    if a["measure"].startswith(("D1", "C1", "C3_30", "C3_60", "PRE_ret", "C5_first5")):
        sign = a["direction"] or 1
        out["same_direction"] = bool(np.sign(r) == sign) if r else False
    return out


def profile(tr: pd.DataFrame, step: float = None) -> dict:
    d = tr[tr["_seg"].isin(["continuous", "post", "pre"]) & tr["upd_vol"]]
    if d.empty:
        return {}
    step = step or footprint.auto_step(float(d["price"].quantile(0.001)), float(d["price"].quantile(0.999)), 40)
    lv = footprint.level_of(d["price"].to_numpy(), step)
    prof = pd.DataFrame({"level": lv, "vol": d["size"].to_numpy()}).groupby("level").sum().reset_index()
    va = footprint._value_area(prof, 0.70)
    top = prof.sort_values("vol", ascending=False)
    poc_i = prof["vol"].idxmax()
    near = prof[(prof["level"] >= prof.loc[poc_i, "level"] - step) & (prof["level"] <= prof.loc[poc_i, "level"] + step)]
    return {"step": step, "value_area": va, "levels": int(len(prof)),
            "top_level_share": round(float(top["vol"].iloc[0] / prof["vol"].sum()), 4),
            "poc_pm1_share": round(float(near["vol"].sum() / prof["vol"].sum()), 4),
            "profile": prof.to_dict("records")}


def run(symbol: str, day: str, window: tuple, *, alerts: list = None, provider=None, quotes: str = "auto",
        budget: dict = None, manifest: Manifest = None, key: str = None, allow_test_period: bool = False,
        catalog: str = "cat-v0") -> dict:
    test_guard.check([day], symbol=symbol, purpose="desglose de eventos", script="drilldown",
                     allow=allow_test_period)
    alerts = alerts or []
    t0 = time.time()
    useful = any(cat.BY_CODE.get(a["code"], cat.Entry("", "", "", (), "")).quotes_useful for a in alerts)
    want_q = quotes == "yes" or (quotes == "auto" and useful)
    qwin = None
    if want_q:
        # solo las alertas que caen en la ventana del desglose (un episodio de día entero no debe pedir quotes de todo el día)
        inside = [a for a in alerts if pd.Timestamp(a["t_end_utc"]) > window[0] and pd.Timestamp(a["t_start_utc"]) < window[1]]
        st = max(min((pd.Timestamp(a["t_start_utc"]) for a in inside), default=window[0]), window[0])
        en = min(max((pd.Timestamp(a["t_end_utc"]) for a in inside), default=window[1]), window[1])
        b = sessions.bounds(day)
        qwin = (max(st - pd.Timedelta(minutes=10), b["open"]), min(en + pd.Timedelta(minutes=10), window[1]))
        if qwin[0] >= qwin[1]:
            qwin = None
    fetched = fetch(provider, symbol, day, window, quotes_window=qwin, budget=budget, manifest=manifest) \
        if provider else {"units": [], "requests": 0}
    tr, tcov = episode.load_trades(symbol, day, manifest, window=window, dedupe_ids=True)
    if tr.empty:
        return {"symbol": symbol, "day": day, "error": "sin trades en la ventana", "fetch": fetched}
    tr["_seg"] = sessions.classify_trades(tr, day).astype(str).to_numpy()
    seg = sessions.segment_summary(tr, day)
    seg.pop("segment_of", None)
    bars = F.load_bars(symbol, [day], manifest)
    bw = bars[(bars["t"] >= window[0]) & (bars["t"] < window[1])] if len(bars) else bars
    est = sessions.bar_estimates(bw, day) if len(bw) else {}
    clipped_cov = [(max(a, window[0]), min(z, window[1])) for a, z in tcov if z > window[0] and a < window[1]]
    mstat = sessions.minute_status(bw, day, tr, clipped_cov, window=window) if len(bw) else {}
    q, qcov = (episode.load_quotes(symbol, day, manifest, window=qwin) if qwin else (pd.DataFrame(), []))
    agg = None
    if len(q):
        c = aggressor.classify(tr.drop(columns=["_seg"]), q, qcov)
        c["_seg"] = tr["_seg"].to_numpy()
        win_alerts = []
        for a in alerts:
            sel = c[(c["t"] >= pd.Timestamp(a["t_start_utc"])) & (c["t"] < pd.Timestamp(a["t_end_utc"]))
                    & (c["_seg"] == "continuous")]
            if len(sel):
                win_alerts.append({"event_id": a["event_id"], "measure": a["measure"], **_methods(sel, q)})
        allq = c[(c["t"] >= qwin[0]) & (c["t"] < qwin[1]) & (c["_seg"] == "continuous")]
        agg = {"quote_window": [str(qwin[0]), str(qwin[1])], "window": _methods(allq, q) if len(allq) else None,
               "by_alert": win_alerts,
               "caveat": "estimación del lado agresor; sin lado verdadero con el que comparar; con métodos que no "
                         "coinciden en el signo, el delta no es evidencia de nada"}
    rechecks, statuses = [], {}
    for a in alerts:
        if not (pd.Timestamp(a["t_end_utc"]) > window[0] and pd.Timestamp(a["t_start_utc"]) < window[1]):
            continue                    # fuera de la ventana del desglose: su estado no cambia
        rc = recheck_alert(tr, a)
        st = "enriched_quotes" if len(q) else "characterized_trades"
        why = ""
        if rc.get("checked") and a["measure"].startswith(("D1", "C1", "C3_30", "C3_60")):
            bar_r = None
            if a.get("t_start_utc") and a.get("t_end_utc"):
                bar_r = _bar_window_ret(bars, a)
            if bar_r and abs(rc["trade_return_pct"]) < 0.5 * abs(bar_r):
                st, why = "artifact", f"con trades el movimiento es {rc['trade_return_pct']} % frente a {bar_r} % con barras"
        if a["status"] in (KEEP_STATUS if catalog != "cat-v0" else ("indeterminate",)):   # cat-v0: como antes
            # el escaneo ya la marcó (dato dudoso, artefacto de split, referencia insuficiente): el desglose lo anota,
            # no lo borra
            st, why = a["status"], "; ".join(x for x in (a.get("status_note", ""), why) if x)
        if seg["segments"]["halt_reopen"]["prints"] > 0:
            why = (why + "; " if why else "") + "hay una reapertura tras suspensión en la ventana"
        rechecks.append({"event_id": a["event_id"], "measure": a["measure"], **rc, "new_status": st, "why": why})
        statuses[a["event_id"]] = (st, why)
    late = tr[tr["_seg"] == "late_report"]
    big = tr[tr["upd_vol"] & ~tr["canceled"]].nlargest(8, "size")
    big = big.assign(segment=big["_seg"]).drop(columns=["_seg"])      # itertuples renombra las columnas con «_»
    out = {
        "symbol": symbol, "day": day, "key": key, "window_utc": [str(window[0]), str(window[1])],
        "window_ny": f"{_ny(window[0])}-{_ny(window[1])}", "fetch": fetched,
        "segments": seg, "bar_estimates": est, "minute_status": mstat, "profile": profile(tr),
        "late_reports": {"shares": int(late.loc[late["upd_vol"], "size"].sum()), "prints": int(len(late)),
                         "largest": int(late["size"].max()) if len(late) else 0,
                         "top_prices": late.groupby("price")["size"].sum().nlargest(5).round(0).to_dict()},
        "largest_prints": [{"t": str(r.t), "ny": pd.Timestamp(r.t).tz_convert(sessions.NY).strftime("%H:%M:%S"),
                            "price": float(r.price), "size": int(r.size), "exchange": str(r.exchange),
                            "conditions": str(r.conditions), "segment": r.segment} for r in big.itertuples()],
        "aggressor": agg, "rechecks": rechecks,
        "trades_loaded": int(len(tr)), "quotes_loaded": int(len(q)),
        "duplicate_ids_removed": tr.attrs.get("duplicate_ids_removed", 0),
        "code_version": config.code_version(),
        "catalog_version": catalog if catalog != "cat-v0" else cat.CATALOG_VERSION,
        "detector_version": V1.DETECTOR_VERSION if catalog == "cat-v1" else cat.DETECTOR_VERSION,
        "data_units": [{"unit_key": r["unit_key"], "sha256": r["sha256"]}
                       for k in ("trades", "quotes") for r in episode.units_for(symbol, day, k, manifest)],
        "seconds": round(time.time() - t0, 1),
    }
    out["profile"].pop("profile", None) if isinstance(out["profile"], dict) else None
    out["statuses"] = statuses
    out["day_shares"] = day_shares(symbol, day, manifest) if seg["segments"]["close_auction"]["prints"] else None
    if seg["segments"]["close_auction"]["prints"] and len(bars):
        b = sessions.bounds(day)
        sl = sessions.slots_of(bars["t"], b)
        cont_bar_vol = float(bars["v"].to_numpy()[(sl > b["open_slot"]) & (sl < b["close_slot"])].sum())
        out["close_auction_vs_bar_continuous"] = {
            "auction_shares_exact": seg["segments"]["close_auction"]["shares"], "continuous_volume_bars": cont_bar_vol,
            "share": round(seg["segments"]["close_auction"]["shares"] / cont_bar_vol, 4) if cont_bar_vol else None,
            "note": "numerador exacto (trades); denominador aproximado: volumen de las barras de negociación continua "
                    "sin las dos barras mixtas (incluye comunicaciones tardías en horario regular)"}
    return out


MAX_DAY_ROWS = 3_000_000
KEEP_STATUS = ("indeterminate", "suspected_data_issue", "artifact")


def day_shares(symbol: str, day: str, manifest: Manifest = None) -> dict:
    """Cuotas exactas de las subastas sobre la sesión entera, SOLO si ya están descargados los trades de toda la
    sesión regular (no descarga nada) y el día no es demasiado grande para la memoria."""
    b = sessions.bounds(day)
    rows = episode.units_for(symbol, day, "trades", manifest)
    cov = episode.coverage_windows(rows, day) if rows else []
    if not any(a <= b["open"] - pd.Timedelta(minutes=1) and z >= b["close"] + pd.Timedelta(minutes=1) for a, z in cov):
        return {"computed": False, "reason": "no están descargados los trades de toda la sesión regular"}
    est = sum(int(r["rows"] or 0) for r in rows)
    if est > MAX_DAY_ROWS:
        return {"computed": False, "reason": f"día demasiado grande para cargarlo entero ({est:,} operaciones)"}
    win = (b["open"] - pd.Timedelta(minutes=1), b["close"] + pd.Timedelta(minutes=1))
    tr, _ = episode.load_trades(symbol, day, manifest, window=win, dedupe_ids=True)
    ss = sessions.segment_summary(tr, day)
    return {"computed": True, "window": "sesión regular completa (09:29-16:01 o equivalente)",
            "denominators": ss["denominators"], "close_auction": ss["shares_of"]["close_auction"],
            "open_auction": ss["shares_of"]["open_auction"], "late_report": ss["shares_of"]["late_report"]}


def _bar_window_ret(bars, a):
    if not len(bars):
        return None
    s0, s1 = pd.Timestamp(a["t_start_utc"]), pd.Timestamp(a["t_end_utc"])
    x0 = bars[bars["t"] < s0]
    x1 = bars[bars["t"] < s1]
    if not len(x0) or not len(x1):
        return None
    return round(float(np.log(x1["c"].iloc[-1] / x0["c"].iloc[-1])) * 100, 3)


def _methods(sel: pd.DataFrame, q: pd.DataFrame) -> dict:
    tot = float(sel["size"].sum())
    out = {"shares": int(tot)}
    for m in aggressor.METHODS:
        col = f"side_{m}"
        buy, sell = float(sel.loc[sel[col] == 1, "size"].sum()), float(sel.loc[sel[col] == -1, "size"].sum())
        out[m] = {"delta_pct_of_volume": round((buy - sell) / tot * 100, 1) if tot else None,
                  "undetermined_pct": round((tot - buy - sell) / tot * 100, 1) if tot else None}
    signs = {np.sign(out[m]["delta_pct_of_volume"]) for m in aggressor.METHODS
             if out[m]["delta_pct_of_volume"] is not None and abs(out[m]["delta_pct_of_volume"]) >= 5}
    out["sign_agreement"] = "coinciden" if len(signs) <= 1 else "signo distinto según el método"
    wq = q[(q["t"] >= sel["t"].min()) & (q["t"] <= sel["t"].max()) & (q["ask"] > q["bid"]) & (q["bid"] > 0)]
    sp = (wq["ask"] - wq["bid"]) / ((wq["ask"] + wq["bid"]) / 2) * 1e4
    out["spread_bps_median"] = round(float(sp.median()), 2) if len(sp) else None
    return out


def apply_statuses(day: str, statuses: dict, version: str = "cat-v0"):
    """Actualiza el estado de las alertas desglosadas en el registro de esa versión del catálogo (y el del episodio)."""
    p = event_store.root(version) / "alerts" / f"{day}.parquet"
    if not p.exists() or not statuses:
        return 0
    df = pd.read_parquet(p)
    for eid, (st, why) in statuses.items():
        m = df["event_id"] == eid
        df.loc[m, "status"] = st
        if why:
            df.loc[m, "status_note"] = why
    from . import storage
    storage.write_parquet_atomic(df, p)
    ep_p = event_store.root(version) / "episodes" / f"{day}.parquet"
    if ep_p.exists():
        eps = pd.read_parquet(ep_p)
        for eid in eps["episode_id"]:
            sts = set(df.loc[df["episode_id"] == eid, "status"])
            if sts:
                eps.loc[eps["episode_id"] == eid, "status"] = (
                    "artifact" if sts == {"artifact"} else "indeterminate" if sts == {"indeterminate"} else
                    "suspected_data_issue" if sts == {"suspected_data_issue"} else
                    "enriched_quotes" if "enriched_quotes" in sts else
                    "characterized_trades" if "characterized_trades" in sts else "candidate_bars")
        storage.write_parquet_atomic(eps, ep_p)
    return len(statuses)
