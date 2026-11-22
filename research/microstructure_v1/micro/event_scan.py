"""Escaneo de un día: barras -> medidas -> alertas -> episodios -> registro (E1; se lanza a mano, sin programar).

Dos pasadas por día, preparadas para el registro diario (ninguna está programada):
- 'regular': tras el cierre regular + retraso de datos (>= 20 min). Las medidas de after hours quedan pendientes.
- 'full':    tras el fin del after hours + retraso. Todas las medidas.

Tiempos de cada alerta:
- t_start_utc: inicio de la ventana en la que empieza el fenómeno.
- t_detectable_utc: primer instante en que la medida supera la referencia USANDO SOLO datos disponibles hasta
  entonces (fin de la vela que la cruza). La referencia sale de sesiones anteriores, así que se conoce de antemano.
- t_available_free_plan_utc: t_detectable + 15 min (retraso del plan gratuito de Alpaca).
"""
import json
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import calendar, catalog_v1 as V1, config, download, event_catalog as cat, event_store, \
    event_universe, intraday_features as F, sectors, sessions, test_guard
from .manifest import Manifest

DATA_DELAY_MIN = 15
SAFETY_MIN = 20
SPLIT_TYPES = {"forward_splits", "reverse_splits", "unit_splits", "stock_dividends", "spin_offs", "stock_mergers",
               "cash_mergers", "stock_and_cash_mergers", "name_changes"}


# ── cobertura y descarga de barras ──
def _unit_end(r: dict, day_hint: str = None) -> pd.Timestamp:
    """Hasta dónde llegan de verdad los datos de una unidad de barras (ventana, tope y hora de descarga)."""
    cfg = json.loads(r["config_json"])
    fin = pd.Timestamp(r["finished_utc"]) - pd.Timedelta(minutes=16) if r.get("finished_utc") else None
    if cfg.get("window") == "session_full":
        end = calendar.session_bounds(r["period"], "full")[1]
    else:
        end = pd.Timestamp(r["period"] + "-01", tz="UTC") + pd.offsets.MonthBegin(1)
    if cfg.get("cap"):
        end = min(end, pd.Timestamp(cfg["cap"]))
    return min(end, fin) if fin is not None else end


def coverage(symbol: str, manifest: Manifest = None) -> dict:
    """{día o mes: fin de datos más tardío entre sus unidades 'ok'}."""
    out = {}
    for r in (manifest or Manifest()).rows("kind='bars' AND symbol=? AND status='ok'", (symbol,)):
        e = _unit_end(r)
        out[r["period"]] = max(out.get(r["period"], e), e)
    return out


def day_covered_until(cov: dict, day: str):
    ends = [cov[k] for k in (day, day[:7]) if k in cov]
    return max(ends) if ends else None


def required_end(day: str, pass_name: str) -> pd.Timestamp:
    b = sessions.bounds(day)
    return b["full_close"] if pass_name == "full" else b["close"] + pd.Timedelta(minutes=1)


def ensure_bars(provider, symbol: str, days: list, target_pass: dict, *, manifest: Manifest = None,
                dry_run: bool = False) -> dict:
    """Descarga solo lo que falta. Meses pasados completos -> unidad mensual con la misma clave que el plan del nivel
    A (sin asof); mes en curso o que toca el periodo reservado -> unidades diarias de los días permitidos."""
    m = manifest or Manifest()
    cov = coverage(symbol, m)
    now = pd.Timestamp(datetime.now(timezone.utc))
    latest = now - pd.Timedelta(minutes=16)
    missing = [d for d in days if (day_covered_until(cov, d) or pd.Timestamp("1970-01-01", tz="UTC"))
               < required_end(d, target_pass.get(d, "full"))]
    plan, by_month = [], {}
    for d in missing:
        by_month.setdefault(d[:7], []).append(d)
    for mo, ds in sorted(by_month.items()):
        month_days = calendar.trading_days(mo + "-01", mo + "-31")
        month_end = calendar.session_bounds(month_days[-1], "full")[1]
        touches_reserved = any(test_guard.reserved(x) for x in month_days)
        if len(ds) >= 6 and month_end < latest and not touches_reserved:
            plan.append(("month", mo, None))
        else:
            for d in ds:
                end = calendar.session_bounds(d, "full")[1]
                cap = None if end <= latest else calendar.iso(latest.floor("min"))
                plan.append(("day", d, cap))
    res = {"symbol": symbol, "missing_days": len(missing), "units": [], "requests": 0}
    if dry_run:
        res["plan"] = plan
        return res
    for kind, period, cap in plan:
        cfg = download.config_for("bars") if kind == "month" else download.config_for("bars", bars_window="day", cap=cap)
        r = download.download_unit(provider, "bars", symbol, period, asof=None, cfg=cfg, manifest=m)
        res["units"].append({k: r.get(k) for k in ("unit_key", "status", "rows", "requests")})
        res["requests"] += int(r.get("requests") or 0)
    return res


# ── eventos corporativos ──
def corporate_actions(provider, symbols: list, start: str, end: str, *, use_cache=True) -> dict:
    """{símbolo: [(tipo, fecha)]} de las acciones que rompen la continuidad de precios entre sesiones."""
    p = event_store.root() / "corporate_actions" / f"{start}_{end}_{abs(hash(tuple(sorted(symbols)))) % 10**8}.json"
    if use_cache and p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    out = {}
    try:
        raw = provider.corporate_actions(sorted(symbols), start, end) if provider else {}
        for typ, items in raw.items():
            if typ not in SPLIT_TYPES:
                continue
            for it in items:
                sym = it.get("symbol") or it.get("old_symbol") or it.get("target_symbol")
                d = it.get("ex_date") or it.get("effective_date") or it.get("process_date")
                if sym and d:
                    out.setdefault(sym, []).append([typ, d])
    except Exception as e:  # noqa: BLE001
        out = {"_error": f"{type(e).__name__}: {e}"}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out), encoding="utf-8")
    return out


# ── escaneo de un valor ──
def baseline_days(day: str, *, target: int = None, max_age: int = None) -> list:
    t = target or cat.THRESHOLDS["baseline_target"]
    age = max_age or cat.THRESHOLDS["baseline_max_age_days"]
    oldest = (pd.Timestamp(day) - pd.Timedelta(days=age)).strftime("%Y-%m-%d")
    prior = [d for d in calendar.trading_days(oldest, day) if d < day]
    return test_guard.allowed(prior)[-(t + 15):]          # margen para sesiones sin datos (antes de cotizar, etc.)


def _prev_trading_day(day: str) -> str:
    ds = calendar.trading_days((pd.Timestamp(day) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"), day)
    return ds[-2] if len(ds) >= 2 and ds[-1] == day else (ds[-1] if ds else None)


def scan_symbol(symbol: str, day: str, pass_name: str, *, corp: dict = None, manifest: Manifest = None,
                catalog: str = "cat-v0") -> dict:
    t0 = time.time()
    test_guard.check([day], symbol=symbol, purpose="escaneo de eventos", script="event_scan")
    cand = baseline_days(day)
    bars = F.load_bars(symbol, cand + [day], manifest)
    M = F.build_matrix(bars, cand + [day])
    di = M.idx(day)
    q = {}
    # sesiones de la línea base con datos de negociación continua (descarta días sin cotizar o vacíos)
    good = []
    for i, d in enumerate(M.days[:-1]):
        b = M.meta[i]
        cov = np.isfinite(M.C[i, b["open_slot"] + 1:b["close_slot"]]).mean()
        if cov >= 0.2:
            good.append(i)
    base = good[-cat.THRESHOLDS["baseline_target"]:]
    sym_corp = (corp or {}).get(symbol, [])
    bad_ref = {d for _, d in sym_corp}                     # el cierre anterior no es comparable ese día
    result = {"symbol": symbol, "day": day, "pass": pass_name, "measures": [], "alerts": [], "symbol_day": None}
    if not np.isfinite(M.C[di]).any():
        ps = event_universe.provider_status(symbol)
        uncovered = bool(ps) and ps.get("status") != "covered"
        result["symbol_day"] = {"symbol": symbol, "day": day, "pass": pass_name,
                                "status": "provider_not_covered" if uncovered else "no_data",
                                "note": (f"no cubierto por Alpaca ({ps.get('status')}; comprobado {ps.get('checked_utc')})"
                                         if uncovered else "sin barras ese día"),
                                "provider_status": ps.get("status") if ps else None,
                                "code_version": config.code_version(),
                                "catalog_version": cat.CATALOG_VERSION if catalog == "cat-v0" else V1.CATALOG_VERSION}
        return result
    prof = F.build_profile(M, base) if base else None
    req_full = required_end(day, "full")
    cov_end = day_covered_until(coverage(symbol, manifest), day)
    post_ok = pass_name == "full" and cov_end is not None and cov_end >= req_full

    def prev_close_of(i):
        # En la línea base, una sesión con evento corporativo no aporta valores de hueco (cierre anterior no comparable).
        # En el día evaluado sí se calcula, y la alerta se marca como artefacto: queda registrada, no desaparece.
        d = M.days[i]
        pd_ = _prev_trading_day(d)
        if (d in bad_ref and i != di) or pd_ is None or pd_ not in M.days:
            return None
        return F.last_continuous_close(M, M.idx(pd_))

    measures_by_row = {}
    for i in base + [di]:
        measures_by_row[i] = F.day_measures(M, i, prof, prev_close_of(i), post=(post_ok if i == di else True)) \
            if prof else {}
    today = measures_by_row.get(di, {})
    quality = today.pop("_quality", {}) if today else {}
    for i in base:
        measures_by_row[i].pop("_quality", None)
    b = M.meta[di]
    liq = float(np.nanmedian(M.N[di, b["open_slot"] + 1:b["close_slot"]])) if np.isfinite(M.N[di]).any() else 0.0
    n_base = len(base)
    short = n_base < cat.THRESHOLDS["min_baseline"]
    split_today = [t for t, d in sym_corp if d == day]
    if catalog == "cat-v1":
        _v1_symbol(result, M, di, base, measures_by_row, today, b, liq, split_today, sym_corp, pass_name)
    for name, m in (today.items() if catalog == "cat-v0" else ()):
        code = cat.MEASURE_CODE.get(name, "?")
        bv = np.array([measures_by_row[i].get(name, {}).get("value", np.nan) for i in base], dtype=float)
        nm = F.normalize(m["value"], bv, pct_hi=cat.THRESHOLDS["pct_hi"], z_hi=cat.THRESHOLDS["z_hi"])
        result["measures"].append({
            "symbol": symbol, "day": day, "pass": pass_name, "measure": name, "code": code,
            "sign": m.get("sign"), "segment": m["segment"], "estimated": m["estimated"], "value": nm["value"], "pct": nm["pct"], "z": nm["z"],
            "n": nm["n"], "median": nm["median"], "threshold": nm["threshold"], "flag": nm["flag"], "rule": nm["rule"],
            "exceeds_baseline_max": nm["exceeds_baseline_max"], "resolution_pct": nm["resolution_pct"],
            "baseline_short": short, "note": m.get("note")})
        if not nm["flag"]:
            continue
        status, note = ("indeterminate", f"línea base corta ({n_base} sesiones)") if short else ("candidate_bars", "")
        if name.startswith(("C5_gap", "PRE_ret")) and split_today:
            status, note = "artifact", f"evento corporativo ese día: {split_today}"
        if name == "D3_gap" and liq < 5:
            continue                    # en un valor poco líquido, minutos sin barras no son anómalos por sí mismos
        if m["estimated"]:
            note = (note + "; " if note else "") + "estimada con barras mixtas: confirmar con trades"
        if m["series"] is not None:
            runs = F.crossings(m["series"], nm["threshold"], m["k"], cat.THRESHOLDS["max_runs_per_measure"])
            wins = [(r["first"] - r["k"] + 1, r["first"] + 1, r["peak"], r["last"] + 1,
                     float(m["series"][r["peak"]])) for r in runs]
        else:
            w0, w1 = m["window"]
            wins = [(w0, m["fixed_slot"], None, w1, nm["value"])]
        for s0, sdet, speak, s1, peak_val in wins:
            ts = lambda s: sessions.slot_time(b, s)
            a = {"symbol": symbol, "day": day, "pass": pass_name, "measure": name, "code": code,
                 "family": cat.BY_CODE[code].family if code in cat.BY_CODE else "?",
                 "direction": m.get("sign", cat.direction_of(name)) if "sign" in m else cat.direction_of(name),
                 "segment": m["segment"], "estimated": m["estimated"],
                 "t_start_utc": ts(max(s0, 0)), "t_detectable_utc": ts(sdet),
                 "t_peak_utc": ts(speak) if speak is not None else None, "t_end_utc": ts(s1),
                 "value": nm["value"], "peak_value": peak_val, "threshold": nm["threshold"], "pct": nm["pct"],
                 "z": nm["z"], "n": n_base, "rule": nm["rule"], "status": status, "status_note": note}
            a["t_available_free_plan_utc"] = a["t_detectable_utc"] + pd.Timedelta(minutes=DATA_DELAY_MIN)
            a["event_id"] = cat.event_id(symbol, day, name, a["t_detectable_utc"])
            result["alerts"].append(a)
    sector, ssrc = sectors.sector_at(symbol, day)
    result["symbol_day"] = {
        "symbol": symbol, "day": day, "pass": pass_name, "status": "ok", "baseline_n": n_base,
        "baseline_short": short, "baseline_days": [M.days[i] for i in base],
        "baseline_rule": f"sesiones anteriores en {cat.THRESHOLDS['baseline_max_age_days']} días, sin el periodo "
                         f"reservado de G2A ({test_guard.RESERVED_START} a {test_guard.RESERVED_END})",
        "post_computed": bool(post_ok), "quality": quality, "median_trades_per_minute": liq,
        "early_close": bool(b["early_close"]), "corporate_actions": sym_corp,
        "sector": sector, "sector_source": ssrc, "sector_etf": sectors.sector_etf(sector) if sector else None,
        "sector_point_in_time": ssrc in ("snapshot", "previous_snapshot"),
        "data_units": {d: M.units.get(d, []) for d in [day]}, "baseline_units": sorted({u for d in M.days[:-1]
                                                                                       for u in M.units.get(d, [])}),
        "catalog_version": cat.CATALOG_VERSION if catalog == "cat-v0" else V1.CATALOG_VERSION,
        "detector_version": cat.DETECTOR_VERSION if catalog == "cat-v0" else V1.DETECTOR_VERSION,
        "code_version": config.code_version(), "seconds": round(time.time() - t0, 2)}
    if catalog == "cat-v1":
        result["symbol_day"].update({"params_sha256": V1.PARAMS_SHA256, "threshold_knowledge": V1.threshold_knowledge(day),
                                     "minute_coverage": float(np.isfinite(M.C[di, b["open_slot"] + 1:b["close_slot"]]).mean())})
    return result


SPLITISH = {"forward_splits", "reverse_splits", "unit_splits", "stock_dividends", "spin_offs"}
GAP_LIKE = ("C5_gap", "PRE_ret")              


def _v1_symbol(result, M, di, base, measures_by_row, today, b, liq, split_today, sym_corp, pass_name):
    """cat-v1 (catalog_v1): todas las medidas del valor-día con su estado, y las alertas con ventanas reales."""
    symbol, day = result["symbol"], result["day"]
    P = V1.params()
    computed = pd.Timestamp.now("UTC").isoformat(timespec="seconds")
    base_days = [M.days[i] for i in base]
    cov = float(np.isfinite(M.C[di, b["open_slot"] + 1:b["close_slot"]]).mean())
    splits_in_base = [(t, d) for t, d in sym_corp if t in SPLITISH and base_days and base_days[0] <= d <= day]
    recent = set(base_days[-P["structural"]["post_split_sessions_V2"]:] + [day])
    recent_split = [(t, d) for t, d in splits_in_base if d in recent]
    for name, m in today.items():
        bv = np.array([measures_by_row[i].get(name, {}).get("value", np.nan) for i in base], dtype=float)
        ev = V1.evaluate(name, m["value"], bv, liq=liq, base_ordered=bv)
        result["measures"].append({
            "symbol": symbol, "day": day, "pass": pass_name, "measure": name, "code": cat.MEASURE_CODE.get(name, "?"),
            "family": ev["family"], "sign": m.get("sign"), "segment": m["segment"], "estimated": m["estimated"],
            "representation": "point" if V1.is_point(m) else "window", "value": ev["value"], "state": ev["state"],
            "score_m1": ev["score_m1"], "pct_own": ev["pct_own"], "score_m2": ev["score_m2"],
            "threshold_m1": ev["threshold_m1"], "threshold_series": ev["threshold_series"], "n": ev["n"],
            "rule": ev["rule"], "reason": ev["reason"], "m1_exceeds": ev.get("m1_exceeds"),
            "catalog_version": V1.CATALOG_VERSION})
        if ev["state"] != "flag":
            continue
        extra = {"liq": liq, "cov": cov, "early_close": bool(b["early_close"]), "corp_event": bool(split_today),
                 "post_split": bool(recent_split)}
        for a in V1.alert_rows(symbol, day, name, m, ev, b, base_extra=extra, computed_utc=computed):
            a["pass"] = pass_name
            if split_today:
                a["data_quality"].append("corp_event_day")
                if name in GAP_LIKE:
                    a["status"], a["status_note"] = "artifact", f"evento corporativo ese día: {split_today}"
            if splits_in_base:
                a["data_quality"].append("unadjusted_split_in_baseline")      # E1 no ajusta las barras en vivo
            if recent_split and name.startswith("V2_"):
                a["structural"].append("post_split_V2_window")
            if b["early_close"]:
                a["structural"].append("early_close")
            if cov < 0.5:
                a["data_quality"].append("low_minute_coverage")
            if day in P["documented_market_halts"]:
                a["structural"].append("documented_market_halt_day")
            if m["estimated"]:
                a["status_note"] = (a["status_note"] + "; " if a["status_note"] else "") + \
                    "estimada con barras mixtas: confirmar con trades"
            result["alerts"].append(a)


# ── contexto y registro ──
def _ctx_returns(symbols: list, day: str, manifest: Manifest = None) -> dict:
    out = {}
    for s in symbols:
        bars = F.load_bars(s, [day], manifest)
        if not len(bars):
            continue
        M = F.build_matrix(bars, [day])
        out[s] = (M.meta[0], np.log(F._ffill(M.C[0])))
    return out


def _window_ret(ctx, s0: pd.Timestamp, s1: pd.Timestamp):
    b, lc = ctx
    i0 = int((s0 - b["base"]).total_seconds() // 60) - 1
    i1 = int((s1 - b["base"]).total_seconds() // 60) - 1
    if i0 < 0 or i1 >= len(lc) or not (np.isfinite(lc[i0]) and np.isfinite(lc[i1])):
        return None
    return round(float(lc[i1] - lc[i0]) * 100, 3)


def scan_day(symbols: list, day: str, pass_name: str = "full", *, provider=None, download_missing=True,
             manifest: Manifest = None, sources: dict = None, log=print, catalog: str = "cat-v0") -> dict:
    """Escanea una lista de valores (manual). Escribe medidas, contexto, alertas y episodios del día."""
    if pass_name not in ("regular", "full"):
        raise ValueError(pass_name)
    test_guard.check([day], purpose="escaneo de eventos", script="event_scan.scan_day")
    b = sessions.bounds(day)
    now = pd.Timestamp(datetime.now(timezone.utc))
    ready = (b["full_close"] if pass_name == "full" else b["close"]) + pd.Timedelta(minutes=SAFETY_MIN)
    if now < ready:
        raise RuntimeError(f"la pasada '{pass_name}' de {day} no puede correr antes de {ready} (retraso de datos)")
    m = manifest or Manifest()
    t0 = time.time()
    ctx_syms = {"SPY", "QQQ"}
    for s in symbols:
        sec, _ = sectors.sector_at(s, day)
        etf = sectors.sector_etf(sec) if sec else None
        if etf:
            ctx_syms.add(etf)
    all_syms = sorted(set(symbols) | ctx_syms)
    stats = {"download_requests": 0, "download_seconds": 0.0}
    if download_missing and provider is not None:
        t1 = time.time()
        for s in all_syms:
            days = baseline_days(day) + [day]
            r = ensure_bars(provider, s, days, {day: pass_name}, manifest=m)
            stats["download_requests"] += r["requests"]
        stats["download_seconds"] = round(time.time() - t1, 1)
    corp = corporate_actions(provider, all_syms, (pd.Timestamp(day) - pd.Timedelta(days=200)).strftime("%Y-%m-%d"),
                             day) if provider else {}
    t2 = time.time()
    measures, symdays, alerts = [], [], []
    for s in symbols:
        r = scan_symbol(s, day, pass_name, corp=corp, manifest=m, catalog=catalog)
        measures += r["measures"]
        alerts += r["alerts"]
        sd = r["symbol_day"]
        sd["sources"] = (sources or {}).get(s, [])
        symdays.append(sd)
        log(f"  {s}: {len(r['measures'])} medidas, {len(r['alerts'])} alertas, base {sd.get('baseline_n')} "
            f"({sd.get('seconds')} s)")
    stats["compute_seconds"] = round(time.time() - t2, 1)
    ctx = _ctx_returns(sorted(ctx_syms), day, m)
    sd_by = {sd["symbol"]: sd for sd in symdays}
    if catalog == "cat-v1":
        return _finish_v1(symbols, day, pass_name, measures, symdays, alerts, ctx, sd_by, stats, t0, ctx_syms)
    for a in alerts:
        etf = (sd_by.get(a["symbol"]) or {}).get("sector_etf")
        a["context"] = {k: _window_ret(ctx[k], a["t_start_utc"], a["t_end_utc"]) if k in ctx else None
                        for k in ("SPY", "QQQ")}
        a["context"]["sector_etf"] = etf
        a["context"]["sector_etf_ret_pct"] = _window_ret(ctx[etf], a["t_start_utc"], a["t_end_utc"]) \
            if etf in ctx else None
        a["simultaneous_symbols"] = sum(1 for o in alerts if o["symbol"] != a["symbol"] and o["code"] == a["code"]
                                        and abs((o["t_detectable_utc"] - a["t_detectable_utc"]).total_seconds()) <= 300)
    # P4: repetición del mismo código y dirección en las 5 sesiones anteriores ya registradas
    prev = event_store.read("alerts")
    prev_days = [d for d in calendar.trading_days((pd.Timestamp(day) - pd.Timedelta(days=12)).strftime("%Y-%m-%d"), day)
                 if d < day][-5:]
    for a in alerts:
        if len(prev):
            pp = prev[(prev["symbol"] == a["symbol"]) & (prev["code"] == a["code"]) &
                      (prev["direction"] == a["direction"]) & (prev["day"].isin(prev_days))]
            a["recurrence_5d"] = int(pp["day"].nunique())
        else:
            a["recurrence_5d"] = None
    episodes = cat.group_episodes(alerts)
    for ep in episodes:
        ep["pass"] = pass_name
        ep["lab_url"] = lab_url(ep)
    for a in alerts:
        a["lab_url"] = lab_url({"symbol": a["symbol"], "day": a["day"], "t_start_utc": a["t_start_utc"],
                                "t_end_utc": a["t_end_utc"], "episode_id": a.get("episode_id"),
                                "t_detectable_utc": a["t_detectable_utc"]})
    for tbl, rows in (("measures", measures), ("symbol_days", symdays), ("alerts", alerts), ("episodes", episodes)):
        df = pd.DataFrame(rows)
        if len(df):
            for c in df.columns:
                if c.endswith("_utc"):
                    df[c] = df[c].map(lambda v: v.isoformat() if isinstance(v, pd.Timestamp) else v)
        event_store.write_day(tbl, day, df, replace=[(s, pass_name) for s in symbols])
    stats["total_seconds"] = round(time.time() - t0, 1)
    return {"day": day, "pass": pass_name, "symbols": len(symbols), "context_symbols": sorted(ctx_syms),
            "measures": len(measures), "alerts": len(alerts), "episodes": len(episodes), "stats": stats}


def _finish_v1(symbols, day, pass_name, measures, symdays, alerts, ctx, sd_by, stats, t0, ctx_syms):
    """cat-v1: contexto, simultaneidad (sobre los valores escaneados), persistencia, calidad y episodios por tramo."""
    P = V1.params()
    ok = [s for s in symbols if (sd_by.get(s) or {}).get("status") == "ok"]
    n_ok = len(ok)
    fam_syms, d3_syms = {}, set()
    for a in alerts:
        fam_syms.setdefault(a["family"], set()).add(a["symbol"])
        if a["measure"] == "D3_gap":
            d3_syms.add(a["symbol"])
    d3_share = len(d3_syms) / n_ok if n_ok else 0.0
    suspected = n_ok >= 50 and d3_share >= P["simultaneity"]["suspected_outage_share"] and \
        day not in P["documented_market_halts"]
    prev_days = [d for d in calendar.trading_days((pd.Timestamp(day) - pd.Timedelta(days=120)).strftime("%Y-%m-%d"), day)
                 if d < day]
    # solo los días previos que hacen falta (el registro cat-v1 incluye todo el histórico retrospectivo)
    frames = [event_store.read("alerts", d, version="cat-v1") for d in prev_days]
    frames = [f[["symbol", "measure", "day"]] for f in frames if len(f)]
    prev = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    for a in alerts:
        sd = sd_by.get(a["symbol"]) or {}
        etf = sd.get("sector_etf")
        a["sector"], a["sector_src"] = sd.get("sector"), sd.get("sector_source")
        a["context"] = {k: _window_ret(ctx[k], a["t_start_utc"], a["t_end_utc"]) if k in ctx else None
                        for k in ("SPY", "QQQ")}
        a["context"]["sector_etf"] = etf
        a["context"]["sector_etf_ret_pct"] = _window_ret(ctx[etf], a["t_start_utc"], a["t_end_utc"]) if etf in ctx else None
        fs = fam_syms.get(a["family"], set())
        a["share_market_family"] = len(fs) / n_ok if n_ok else None
        same_sec = [s for s in ok if (sd_by.get(s) or {}).get("sector") == sd.get("sector")]
        a["share_sector_family"] = (len([s for s in same_sec if s in fs]) / len(same_sec)
                                    if same_sec and sd.get("sector") else None)
        a["simultaneity_denominator"] = n_ok
        a["market_day"] = bool(n_ok >= 50 and a["share_market_family"] >= P["simultaneity"]["market_wide_share"])
        if a["market_day"]:
            a["structural"].append("market_wide_family_day")
        vinc = V1.valor_day_incident(a["symbol"], day)
        if vinc:
            a["data_quality"].append(vinc["classification"])
            a["status"], a["status_note"] = "suspected_data_issue", f"incidencia de datos del valor-día: {vinc['evidence']}"
        inc = V1.data_incidents().get(day)
        if inc:
            lab, stt, nt = V1.incident_effect(inc, day, a["t_start_utc"], a["t_end_utc"],
                                              (sd.get("quality") or {}).get("longest_gap_minutes"))
            a["data_quality"].append(lab)
            if stt:
                a["status"], a["status_note"] = stt, nt
        elif suspected:
            a["data_quality"].append("suspected_data_outage_day")
            if a["measure"] == "D3_gap":
                a["status"] = "suspected_data_issue"
                a["status_note"] = "hueco simultáneo en ≥ 10 % de los valores escaneados sin parada documentada"
        # persistencia: sesiones seguidas (hasta hoy) con la misma medida marcada en el registro cat-v1
        c = 1
        if len(prev):
            have = set(prev.loc[(prev["symbol"] == a["symbol"]) & (prev["measure"] == a["measure"]), "day"])
            for d in reversed(prev_days):
                if d in have:
                    c += 1
                else:
                    break
        a["persistence"] = c
        a["lab_url"] = lab_url({"symbol": a["symbol"], "day": a["day"], "t_start_utc": a["t_start_utc"],
                                "t_end_utc": a["t_end_utc"]}) + "&catalog=cat-v1"
    episodes = V1.group_episodes(alerts)
    for ep in episodes:
        ep["pass"] = pass_name
        ep["lab_url"] = lab_url({"symbol": ep["symbol"], "day": ep["day"], "t_start_utc": ep["t_start_utc"],
                                 "t_end_utc": ep["t_end_utc"], "episode_id": ep["episode_id"]}) + "&catalog=cat-v1"
    for tbl, rows in (("measures", measures), ("symbol_days", symdays), ("alerts", alerts), ("episodes", episodes)):
        df = pd.DataFrame(rows)
        if len(df):
            for c in df.columns:
                if c.endswith("_utc"):
                    df[c] = df[c].map(lambda v: v.isoformat() if isinstance(v, pd.Timestamp) else v)
        event_store.write_day(tbl, day, df, replace=[(s, pass_name) for s in symbols], version="cat-v1")
    stats["total_seconds"] = round(time.time() - t0, 1)
    return {"day": day, "pass": pass_name, "catalog": "cat-v1", "symbols": len(symbols),
            "context_symbols": sorted(ctx_syms), "measures": len(measures), "alerts": len(alerts),
            "episodes": len(episodes), "suspected_data_outage": suspected, "d3_share": round(d3_share, 3),
            "stats": stats}


SIMUL_LABELS = ("market_wide_family_day", "suspected_data_outage_day")
SIMUL_NOTE = "hueco simultáneo en ≥ 10 % de los valores escaneados"


def finalize_day_v1(day: str, pass_name: str = "full", mixed: dict = None) -> dict:
    """cat-v1, registro diario por tandas: recalcula sobre TODOS los valores escaneados del día y la pasada lo que
    depende del conjunto (simultaneidad de mercado y de sector, día de mercado, sospecha de caída de datos) y vuelve a
    agrupar los episodios. Idempotente: parte siempre de las alertas guardadas y quita antes lo que añadió la vez
    anterior. No toca las medidas ni el resto de pasadas."""
    P = V1.params()
    sds = event_store.read("symbol_days", day, version="cat-v1")
    sds = sds[sds["pass"] == pass_name] if len(sds) else sds
    al = event_store.read("alerts", day, version="cat-v1")
    al = al[al["pass"] == pass_name].copy() if len(al) else al
    ok = sds[sds["status"] == "ok"] if len(sds) else sds
    n_ok = int(len(ok))
    # solo sectores válidos a fecha (no los de una instantánea posterior)
    pit = ok["sector_point_in_time"].fillna(True).astype(bool) if n_ok and "sector_point_in_time" in ok         else pd.Series(True, index=ok.index)
    sec_of = dict(zip(ok.loc[pit, "symbol"], ok.loc[pit, "sector"])) if n_ok else {}
    out = {"day": day, "pass": pass_name, "symbols_ok": n_ok, "alerts": int(len(al))}
    if not len(al):
        event_store.write_day("episodes", day, pd.DataFrame(), replace=[(pass_name,)], keys=("pass",), version="cat-v1")
        return {**out, "episodes": 0}
    recs = al.to_dict("records")
    for a in recs:
        for c in ("data_quality", "structural"):
            v = a.get(c)
            a[c] = [x for x in (json.loads(v) if isinstance(v, str) else (v or [])) if x not in SIMUL_LABELS]
        if a["status"] == "suspected_data_issue" and str(a.get("status_note") or "").startswith(SIMUL_NOTE):
            a["status"], a["status_note"] = "candidate_bars", ""
        for c in [c for c in a if c.endswith("_utc") and c != "computed_utc"]:
            if isinstance(a[c], str):
                a[c] = pd.Timestamp(a[c])
    fam_syms, d3 = {}, set()
    for a in recs:
        fam_syms.setdefault(a["family"], set()).add(a["symbol"])
        if a["measure"] == "D3_gap":
            d3.add(a["symbol"])
    d3_share = len(d3) / n_ok if n_ok else 0.0
    suspected = n_ok >= 50 and d3_share >= P["simultaneity"]["suspected_outage_share"] and \
        day not in P["documented_market_halts"] and day not in V1.data_incidents()
    by_sec = {}
    for s, sec in sec_of.items():
        by_sec.setdefault(sec, set()).add(s)
    for a in recs:
        mx = (mixed or {}).get(a["symbol"])
        if mx:                                   # control de series de precio mezcladas (micro/dq_checks)
            if "suspected_mixed_price_series" not in a["data_quality"]:
                a["data_quality"].append("suspected_mixed_price_series")
            if a["status"] != "artifact":
                a["status"] = "suspected_data_issue"
                a["status_note"] = f"series de precio mezcladas: niveles {mx['levels']}, {mx['switches']} cambios"
        fs = fam_syms.get(a["family"], set())
        a["share_market_family"] = len(fs) / n_ok if n_ok else None
        same = by_sec.get(sec_of.get(a["symbol"]), set()) if sec_of.get(a["symbol"]) else set()
        a["share_sector_family"] = len(same & fs) / len(same) if same else None
        a["simultaneity_denominator"] = n_ok
        a["market_day"] = bool(n_ok >= 50 and a["share_market_family"] >= P["simultaneity"]["market_wide_share"])
        if a["market_day"]:
            a["structural"].append("market_wide_family_day")
        if suspected:
            a["data_quality"].append("suspected_data_outage_day")
            if a["measure"] == "D3_gap" and a["status"] == "candidate_bars":
                a["status"] = "suspected_data_issue"
                a["status_note"] = SIMUL_NOTE + " sin parada documentada (sin confirmar)"
    episodes = V1.group_episodes(recs)
    for ep in episodes:
        ep["pass"] = pass_name
        ep["lab_url"] = lab_url({"symbol": ep["symbol"], "day": ep["day"], "t_start_utc": ep["t_start_utc"],
                                 "t_end_utc": ep["t_end_utc"], "episode_id": ep["episode_id"]}) + "&catalog=cat-v1"
    for tbl, rows in (("alerts", recs), ("episodes", episodes)):
        df = pd.DataFrame(rows)
        for c in df.columns:
            if c.endswith("_utc"):
                df[c] = df[c].map(lambda v: v.isoformat() if isinstance(v, pd.Timestamp) else v)
        event_store.write_day(tbl, day, df, replace=[(pass_name,)], keys=("pass",), version="cat-v1")
    return {**out, "episodes": len(episodes), "suspected_data_outage": suspected, "d3_share": round(d3_share, 4),
            "market_day_alerts": int(sum(a["market_day"] for a in recs))}


def lab_url(ep: dict, port: int = 8765) -> str:
    """Enlace al laboratorio: ventana del episodio ±15 min, vela de 1 min, sesión extendida, modo ciego al final."""
    st = pd.Timestamp(ep["t_start_utc"]).tz_convert(sessions.NY) - pd.Timedelta(minutes=15)
    en = pd.Timestamp(ep["t_end_utc"]).tz_convert(sessions.NY) + pd.Timedelta(minutes=15)
    q = {"symbol": ep["symbol"], "day": ep["day"], "start": st.strftime("%H:%M"), "end": en.strftime("%H:%M"),
         "tf": 1, "session": "extended"}
    if ep.get("episode_id"):
        q["episode"] = ep["episode_id"]
    return f"http://127.0.0.1:{port}/?" + "&".join(f"{k}={v}" for k, v in q.items())
