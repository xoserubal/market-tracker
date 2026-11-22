"""Catálogo de anomalías intradía, versión cat-v1 (aprobada por el usuario el 2026-11-21; E2B_INFORME.md §3).

Catálogo observacional: describe lo ocurrido y nunca atribuye intención. Las alertas son una forma de descubrir cosas
en el registro; no filtran ni borran nada de las capas 1 (datos) y 2 (medidas). cat-v0 (micro/event_catalog.py) se
conserva intacto y sigue siendo reproducible.

Reglas (parámetros congelados en catalog/cat_v1_params.json, verificados por hash al cargarlos):
1. Normalización M1: línea base = las 60 sesiones válidas anteriores (≤ 180 días naturales, ≥ 20 % de minutos
   continuos con barra); transformación por tipo de medida (cocientes en log, rachas en log1p); puntuación
   (x − mediana) / max(1,4826·MAD, suelo). Marca si la puntuación supera el umbral de su medida, fijado una vez con
   2016-2019. Sin cuota diaria. M2 (exponencial, semivida 20 sesiones) se guarda como contexto, no decide.
2. Medidas discretas o de dispersión pequeña (P1, P3, D3_gap, C3_ext35): además, superar la propia historia (máximo de
   la base en las discretas, percentil 99 en las continuas) y el percentil 99 de calibración en valor bruto.
   D3_gap exige liquidez ≥ 5 operaciones por minuto (regla de E1).
3. V3_close_est: sin alerta con barras; estado «requiere trades». La medida se guarda.
4. Ninguna medida pierde su alerta por redundancia; los grupos de `display_groups` son solo para mostrarlas.
5. Episodios por tramo, alertas a ≤ 10 minutos, con ventanas reales. Las medidas de resumen (sin serie por minuto:
   PRE_*, C1_*, C3_30/60, C3_vol_est, C5_*, V3_*) entran como puntos en su instante de detección y conservan su
   ventana original como atributo.
6. Calidad, separada en dos ejes: errores o sospechas de datos (`data_quality`) y efectos estructurales del mercado o
   del valor (`structural`). Nada se borra; algunas alertas cambian de estado.

Instantes de cada alerta (UTC):
- t_start: comienzo del fenómeno observado (primer minuto de la primera ventana que supera el umbral);
- t_detect: primer instante en que pudo detectarse (fin de la vela que completa esa ventana);
- t_peak, t_end: pico y fin del tramo por encima del umbral;
- t_available: cuándo habría estado disponible el dato con el plan gratuito de Alpaca (t_detect + 15 min);
- computed_utc: cuándo se calculó (retrospectivo o en vivo);
- threshold_knowledge: si el umbral era conocido en esa fecha (ver threshold_knowledge()).
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import event_catalog as cat0, sessions

CATALOG_VERSION = "cat-v1"
DETECTOR_VERSION = "ev-det-1.0"
PARAMS_PATH = Path(__file__).resolve().parent.parent / "catalog" / "cat_v1_params.json"
PARAMS_SHA256 = "018e62f56eb6e51db2fa5b85cec54f55ec8e681e8d64def94350c778c0774234"
FROZEN_DAY = "2026-11-21"
# Tolerancia de empate: en las medidas discretas (rachas en log1p) el umbral es un cuantil que coincide con un valor
# alcanzable; la capa 2 guarda float32 y aquí se calcula en float64. «≥ umbral» incluye el empate en ambas rutas.
TIE_REL = 1e-6


def at_or_above(score, th):
    return np.asarray(score) >= th - TIE_REL * max(1.0, abs(th))

STATUSES = {**cat0.STATUSES,
            "requires_trades": "Sin alerta con barras: requiere trades",
            "suspected_data_issue": "Sospecha de problema de datos (sin confirmar)"}
SEGMENT_ORDER = ("pre", "open_auction", "continuous", "close_auction", "post")


@lru_cache(maxsize=1)
def params() -> dict:
    body = PARAMS_PATH.read_bytes()
    h = hashlib.sha256(body).hexdigest()
    if h != PARAMS_SHA256:
        raise RuntimeError(f"cat_v1_params.json no coincide con el hash congelado ({h})")
    return json.loads(body)


INCIDENTS_PATH = PARAMS_PATH.parent / "data_incidents.json"


def data_incidents() -> dict:
    """Registro de incidencias de datos comprobadas (no es un parámetro congelado: crece con las comprobaciones)."""
    return json.loads(INCIDENTS_PATH.read_text(encoding="utf-8"))["incidents"] if INCIDENTS_PATH.exists() else {}


def valor_day_incident(symbol: str, day: str):
    """Incidencia de datos registrada para un solo valor-día (p. ej. series de precio mezcladas), o None."""
    if not INCIDENTS_PATH.exists():
        return None
    return json.loads(INCIDENTS_PATH.read_text(encoding="utf-8")).get("valor_day_incidents", {}).get(f"{symbol}|{day}")


def incident_effect(inc: dict, day: str, t_start, t_end, longest_gap=None):
    """(etiqueta, estado o None, nota) de una alerta en un día con incidencia de datos registrada.

    Toma el estado de la incidencia si el propio valor-día tiene un hueco (racha sin barras mayor que el umbral absoluto
    de D3_gap) y la ventana [t_start, t_end] de la alerta se solapa con la de la incidencia (+2 min, para el salto de la
    reapertura del dato). Si no, solo la etiqueta: el 2019-08-12 los valores de Nasdaq tenían datos completos."""
    corr = inc.get("classification") == "corroborated_data_incident"
    label = "corroborated_data_incident_day" if corr else "suspected_data_outage_day"
    w0 = pd.Timestamp(f"{day} {inc['window_start_ny']}", tz=sessions.NY)
    w1 = pd.Timestamp(f"{day} {inc['window_end_ny']}", tz=sessions.NY) + pd.Timedelta(minutes=2)
    s, e = pd.Timestamp(t_start), pd.Timestamp(t_end)
    affected = longest_gap is None or longest_gap > params()["special"]["D3_gap"]["abs_threshold_raw"]
    if affected and s <= w1 and e >= w0:
        if corr:
            return label, "artifact", f"dentro de una incidencia de difusión de datos corroborada ({inc['window_ny']} NY): " \
                                      f"{inc['external_source']}"
        return label, "suspected_data_issue", f"dentro de un hueco de datos sospechoso ({inc['window_ny']} NY), sin " \
                                              f"confirmar: {inc['provider_check']}"
    return label, None, ""


def transform_kind(name: str) -> str:
    t = params()["transforms"]
    if name.startswith(tuple(t["log"])):
        return "log"
    if name.startswith(tuple(t["log1p"])):
        return "log1p"
    return "id"


def transform(name: str, x):
    k = transform_kind(name)
    x = np.asarray(x, dtype=float)
    with np.errstate(all="ignore"):
        if k == "log":
            return np.log(np.where(x > 0, x, np.nan))
        if k == "log1p":
            return np.log1p(np.where(x >= 0, x, np.nan))
    return x


def inv_transform(name: str, y: float) -> float:
    k = transform_kind(name)
    if k == "log":
        return float(np.exp(y))
    if k == "log1p":
        return float(np.expm1(y))
    return float(y)


def family(name: str) -> str:
    return params()["families"].get(name, "?")


def threshold_knowledge(day: str) -> str:
    p = params()
    if day <= p["calibration_period"][1]:
        return "in_sample_calibration"
    if day <= FROZEN_DAY:
        return "retrospective_out_of_sample"
    return "prospective"


def m2_context(name: str, base_ordered: np.ndarray, x: float):
    """Puntuación M2 (contexto) con la historia ordenada disponible: media y desviación absoluta exponenciales."""
    p = params()["baseline"]
    s = pd.Series(np.append(transform(name, base_ordered), transform(name, [x])))
    m = s.ewm(halflife=p["m2_halflife"], ignore_na=True, min_periods=p["m2_min_periods"]).mean().shift(1)
    d = (s - m).abs().ewm(halflife=p["m2_halflife"], ignore_na=True, min_periods=p["m2_min_periods"]).mean().shift(1)
    m, d = m.ffill(), d.ffill()
    with np.errstate(all="ignore"):
        v = (s.iloc[-1] - m.iloc[-1]) / (1.2533 * d.iloc[-1])
    return float(v) if np.isfinite(v) else None


def evaluate(name: str, x: float, base: np.ndarray, *, liq: float = None, base_ordered: np.ndarray = None) -> dict:
    """Evalúa una medida de un valor-día frente a su línea base (valores brutos de la misma medida, sesiones anteriores).

    Devuelve las cifras de rareza (puntuación M1, percentil propio, M2), el umbral en la escala de la serie (para buscar
    las ventanas reales), la regla aplicada y el estado: 'flag', 'below', 'not_evaluable' o 'requires_trades'."""
    P = params()
    b = np.asarray(base, dtype=float)
    b = b[np.isfinite(b)]
    out = {"measure": name, "family": family(name), "value": float(x) if np.isfinite(x) else None, "n": int(len(b)),
           "score_m1": None, "pct_own": None, "score_m2": None, "threshold_m1": P["m1_thresholds"].get(name),
           "threshold_series": None, "state": "not_evaluable", "rule": "", "reason": ""}
    if name not in P["m1_thresholds"]:
        out["reason"] = "medida sin umbral en cat-v1"
        return out
    if not np.isfinite(x) or len(b) < P["baseline"]["min_n"]:
        out["reason"] = "valor ausente" if not np.isfinite(x) else f"línea base corta ({len(b)} < {P['baseline']['min_n']})"
        return out
    with np.errstate(all="ignore"):
        out["pct_own"] = round(float(100.0 * ((b < x).sum() + 0.5 * (b == x).sum()) / len(b)), 2)
        bt = transform(name, b)
        bt = bt[np.isfinite(bt)]
        xt = float(transform(name, [x])[0])
    if not len(bt) or not np.isfinite(xt):           # como E2: la base cuenta en bruto; la mediana, transformada
        if name in P["no_alert_measures"]:          # p. ej. V3_close_est = 0 (barra de las 16:00 vacía en NYSE)
            out.update(state="requires_trades", m1_exceeds=None, rule="sin alerta con barras: requiere trades",
                       reason=P["no_alert_measures"][name])
            return out
        out["reason"] = "valor o línea base fuera del dominio de la transformación"
        return out
    med = float(np.median(bt))
    mad = float(np.median(np.abs(bt - med)) * 1.4826)
    sc = max(mad, P["m1_mad_floors"][name])
    th = P["m1_thresholds"][name]
    out["score_m1"] = round((xt - med) / sc, 4)
    out["threshold_series"] = inv_transform(name, med + th * sc)
    out["median_base"] = inv_transform(name, med)
    if base_ordered is not None:
        out["score_m2"] = m2_context(name, np.asarray(base_ordered, float), x)
    passed = bool(at_or_above((xt - med) / sc, th))
    rule = f"M1 ≥ {th:.3g}"
    out["m1_exceeds"] = bool(passed)
    if name in P["no_alert_measures"]:
        out["state"] = "requires_trades"             # siempre: con barras no se evalúa; m1_exceeds queda informativo
        out["rule"] = rule + "; sin alerta con barras: requiere trades"
        out["reason"] = P["no_alert_measures"][name]
        return out
    if name in P["special"]:
        sp = P["special"][name]
        own = (x > np.max(b)) if sp["own_rule"] == "max" else (out["pct_own"] >= 99.0)
        absok = x > sp["abs_threshold_raw"]
        rule += f"; propia historia ({'máximo' if sp['own_rule'] == 'max' else 'p99'}); > {sp['abs_threshold_raw']:.4g} (p99 calibración)"
        if sp["evaluable"] == "min_liq":
            if liq is None or liq < P["special_rules"]["d3_min_liq"]:
                out.update(state="not_evaluable", rule=rule, reason=f"liquidez < {P['special_rules']['d3_min_liq']:g} op/min")
                return out
        passed = passed and bool(own) and bool(absok)
        out["threshold_series"] = max(out["threshold_series"], sp["abs_threshold_raw"], float(np.max(b)))
    out["state"] = "flag" if passed else "below"
    out["rule"] = rule
    return out


def is_point(m: dict) -> bool:
    """Medida de resumen (sin serie por minuto): se representa como punto en su instante de detección."""
    return m.get("series") is None


def windows(name: str, m: dict, thr: float) -> list:
    """Ventanas reales de una medida marcada, en minutos desde las 04:00 NY: (inicio, detección, pico, fin), con la
    detección y el fin como el minuto SIGUIENTE a la vela (fin de la vela). Para las de resumen, una ventana fija."""
    ser, k = m.get("series"), int(m.get("k") or 1)
    if ser is not None:
        from .intraday_features import crossings
        runs = crossings(ser, thr, k, max_runs=10_000)
        if not runs:                     # el máximo cae justo en el umbral: ventana del pico
            p = int(np.nanargmax(ser))
            runs = [{"first": p, "peak": p, "last": p, "k": k}]
        run_measure = name.startswith(("P1_", "P3_", "D3_gap"))
        out = []
        for r in runs:
            s0 = r["first"] - int(ser[r["first"]]) + 1 if run_measure else r["first"] - k + 1
            out.append((max(0, s0), r["first"] + 1, r["peak"], r["last"] + 1, float(ser[r["peak"]])))
        return out
    w0, w1 = m["window"]
    return [(int(w0), int(m["fixed_slot"]), None, int(w1), float(m["value"]))]


def alert_rows(symbol: str, day: str, name: str, m: dict, ev: dict, b: dict, *, base_extra: dict = None,
               computed_utc: str = None) -> list:
    """Filas de alerta (una por ventana real) de una medida marcada. b = sessions.bounds(day)."""
    P = params()
    ts = lambda s: sessions.slot_time(b, s)  # noqa: E731
    rows = []
    point = is_point(m)
    for s0, sdet, speak, s1, peak_val in windows(name, m, ev["threshold_series"]):
        t_start, t_det, t_end = ts(s0), ts(sdet), ts(s1)
        a = {"catalog_version": CATALOG_VERSION, "detector_version": DETECTOR_VERSION, "symbol": symbol, "day": day,
             "measure": name, "code": cat0.MEASURE_CODE.get(name, "?"), "family": ev["family"],
             "direction": m.get("sign", cat0.direction_of(name)) if "sign" in m else cat0.direction_of(name),
             "segment": m["segment"], "estimated": bool(m["estimated"]), "representation": "point" if point else "window",
             "t_start_utc": t_start, "t_detect_utc": t_det, "t_peak_utc": ts(speak) if speak is not None else t_det,
             "t_end_utc": t_end, "t_available_utc": t_det + pd.Timedelta(minutes=P["data_delay_minutes_free_plan"]),
             # ventana original de la medida (para las de resumen, todo el tramo resumido aunque se muestre como punto)
             "window_start_utc": t_start, "window_end_utc": t_end,
             "value": ev["value"], "peak_value": peak_val, "score_m1": ev["score_m1"], "pct_own": ev["pct_own"],
             "score_m2": ev["score_m2"], "threshold_m1": ev["threshold_m1"], "threshold_series": ev["threshold_series"],
             "median_base": ev.get("median_base"), "n": ev["n"], "rule": ev["rule"], "status": "candidate_bars",
             "status_note": "", "data_quality": [], "structural": [],
             "threshold_knowledge": threshold_knowledge(day), "computed_utc": computed_utc}
        if point:                         # el episodio lo usa como punto: comienzo = fin = detección
            a["episode_start_utc"] = a["episode_end_utc"] = t_det
        else:
            a["episode_start_utc"], a["episode_end_utc"] = t_start, t_end
        if base_extra:
            a.update(base_extra)
        a["event_id"] = hashlib.sha1(f"{symbol}|{day}|{name}|{t_det.isoformat()}|{DETECTOR_VERSION}".encode()).hexdigest()[:16]
        rows.append(a)
    return rows


def group_episodes(alerts: list, gap_minutes: int = None) -> list:
    """Episodios por (valor, día, tramo): alertas cuyos intervalos [episode_start, episode_end] se solapan o distan ≤ gap.

    Las alertas se conservan; cada una recibe episode_id. Las de resumen cuentan como puntos."""
    gap = pd.Timedelta(minutes=gap_minutes if gap_minutes is not None else params()["episodes"]["gap_minutes"])
    by = {}
    for a in alerts:
        by.setdefault((a["symbol"], a["day"], a["segment"]), []).append(a)
    out = []
    for (sym, day, seg), al in by.items():
        al.sort(key=lambda a: (a["episode_start_utc"], a["episode_end_utc"]))
        cur = None
        groups = []
        for a in al:
            if cur is not None and a["episode_start_utc"] <= cur["end"] + gap:
                cur["alerts"].append(a)
                cur["end"] = max(cur["end"], a["episode_end_utc"])
            else:
                cur = {"start": a["episode_start_utc"], "end": a["episode_end_utc"], "alerts": [a]}
                groups.append(cur)
        for g in groups:
            A = g["alerts"]
            eid = hashlib.sha1(f"{sym}|{day}|{seg}|{g['start'].isoformat()}|{DETECTOR_VERSION}".encode()).hexdigest()[:16]
            for a in A:
                a["episode_id"] = eid
            fams = sorted({a["family"] for a in A})
            sc = [min(abs(a["score_m1"]), 1e3) for a in A if a.get("score_m1") is not None]
            statuses = {a["status"] for a in A}
            out.append({
                "catalog_version": CATALOG_VERSION, "episode_id": eid, "symbol": sym, "day": day, "segment": seg,
                "t_start_utc": min(a["t_start_utc"] for a in A), "t_detect_utc": min(a["t_detect_utc"] for a in A),
                "t_end_utc": max(a["t_end_utc"] for a in A), "t_available_utc": min(a["t_available_utc"] for a in A),
                "episode_start_utc": g["start"], "episode_end_utc": g["end"],
                "n_alerts": len(A), "measures": sorted({a["measure"] for a in A}), "codes": sorted({a["code"] for a in A}),
                "families": fams, "max_score_m1": max(sc) if sc else None,
                "market_day": any(a.get("market_day") for a in A),
                "data_quality": sorted({q for a in A for q in a.get("data_quality", [])}),
                "structural": sorted({q for a in A for q in a.get("structural", [])}),
                "status": next(iter(statuses)) if len(statuses) == 1 else "candidate_bars",
                "threshold_knowledge": A[0]["threshold_knowledge"]})
    return out
