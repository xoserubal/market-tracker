"""Catálogo de anomalías intradía, versión cat-v0 (EVENTOS_PROPUESTA.md §3, aprobado el 2026-11-17).

Describe lo observado; ningún nombre ni campo atribuye intención («compra institucional», «acumulación»...).

Estados de una anomalía:
- candidate_bars        anomalía candidata identificada con barras de 1 minuto
- characterized_trades  caracterizada con trades (tramos exactos, niveles, operaciones grandes)
- enriched_quotes       además, enriquecida con quotes (diferencial, clasificadores de agresor)
- indeterminate         la referencia histórica o los datos no bastan para decidir
- artifact              artefacto de datos o de agregación (barra mixta, división, reapertura, impresión aislada)

Umbrales: percentil >= 99 o z robusto >= 4 frente a las sesiones previas del valor. SOLO referencias iniciales de
exploración, no calibradas. Con 60 sesiones, el percentil 99 equivale a superar el máximo de la línea base (resolución
1,7 puntos); con ~60 medidas por valor y día, el azar produce del orden de una marca por valor y día. Calibrarlo es
tarea de E2.
"""
import hashlib
import random
from dataclasses import dataclass

CATALOG_VERSION = "cat-v0"
DETECTOR_VERSION = "ev-det-0.1"
THRESHOLDS = {"pct_hi": 99.0, "z_hi": 4.0, "min_baseline": 30, "baseline_target": 60, "baseline_max_age_days": 180,
              "episode_gap_minutes": 10, "max_runs_per_measure": 5, "status": "referencia inicial, sin calibrar"}
STATUSES = {
    "candidate_bars": "Anomalía candidata (barras)",
    "characterized_trades": "Caracterizada con trades",
    "enriched_quotes": "Enriquecida con quotes",
    "indeterminate": "Indeterminada: datos o referencia insuficientes",
    "artifact": "Artefacto de datos o de agregación",
}


@dataclass(frozen=True)
class Entry:
    code: str
    family: str
    name: str
    measures: tuple            # nombres de intraday_features (sin _up/_dn cuando es de dos lados)
    source: str                # B barras · T trades · Q quotes
    two_sided: bool = False
    quotes_useful: bool = False
    note: str = ""


FAMILIES = {"D": "Desplazamiento", "V": "Volumen", "I": "Volumen/precio", "N": "Niveles", "C": "Cierre y apertura",
            "PM": "Premercado", "P": "Persistente"}

CATALOG = (
    Entry("D1", "D", "Retorno extraordinario en 1, 5, 15 o 30 minutos", ("D1_1", "D1_5", "D1_15", "D1_30"), "B", True),
    Entry("D2", "D", "Rango extraordinario de una vela", ("D2_range",), "B"),
    Entry("D3", "D", "Salto entre velas o hueco sin barras", ("D3_jump", "D3_gap"), "B",
          note="un hueco sin barras puede ser ausencia de operaciones, dato ausente o suspensión"),
    Entry("D4", "D", "Excursión extrema respecto al VWAP del día", ("D4_vwap",), "B", True),
    Entry("V1", "V", "Volumen de la ventana frente al perfil intradía propio", ("V1_1", "V1_5", "V1_15"), "B"),
    Entry("V2", "V", "Cambio del tamaño medio por operación", ("V2_size",), "B", True),
    Entry("V3", "V", "Subasta de apertura o de cierre anómala", ("V3_open_est", "V3_close_est"), "T", quotes_useful=True,
          note="con barras solo se estima (barras mixtas); el volumen y el precio exactos salen de los trades"),
    Entry("I1", "I", "Desplazamiento alto con volumen escaso", ("I1_thin",), "B", True, quotes_useful=True),
    Entry("I2", "I", "Volumen alto sin desplazamiento", ("I2_stall",), "B", quotes_useful=True),
    Entry("I3", "I", "Cierre de la ventana lejos de su VWAP", ("I3_vwap15",), "B", True),
    Entry("N1", "N", "Concentración de volumen en un nivel de precio", (), "T"),
    Entry("N2", "N", "Toques repetidos de un nivel sin romperlo", (), "B", note="definida; sin implementar en E1"),
    Entry("N3", "N", "Operaciones grandes para el valor", (), "T"),
    Entry("C1", "C", "Cambio brusco en los últimos 5, 10 o 30 min de la sesión regular", ("C1_5", "C1_10", "C1_30"),
          "B", True),
    Entry("C2", "C", "Subasta de cierre anómala", ("V3_close_est",), "T", quotes_useful=True,
          note="comparte medida estimada con V3; exacta solo con trades"),
    Entry("C3", "C", "Deriva extraordinaria en after hours", ("C3_30", "C3_60", "C3_ext35", "C3_vol_est"), "B", True),
    Entry("C4", "C", "Comunicaciones tardías a precio de referencia", (), "T"),
    Entry("C5", "C", "Hueco de apertura y primeros minutos", ("C5_gap", "C5_first5"), "B", True),
    Entry("PM1", "PM", "Movimiento extraordinario en premercado", ("PRE_ret",), "B", True),
    Entry("PM2", "PM", "Volumen extraordinario en premercado", ("PRE_vol",), "B"),
    Entry("P1", "P", "Racha de velas en la misma dirección", ("P1_run",), "B", True),
    Entry("P2", "P", "Recorrido muy direccional (eficiencia)", ("P2_er30", "P2_er60"), "B", True),
    Entry("P3", "P", "Volumen por encima del perfil durante muchos minutos seguidos", ("P3_highvol_run",), "B"),
    Entry("P4", "P", "Repetición en varios días (mismo valor, mismo código)", (), "registro"),
)
BY_CODE = {e.code: e for e in CATALOG}

# Extensiones aprobadas para más adelante (no implementadas en E1).
PLANNED = {
    "X1": "Barrida de máximos o mínimos y recuperación",
    "X2": "Divergencia frente al sector en la misma ventana",
    "X3": "Compresión y expansión de volatilidad",
    "X4": "Migración del POC y del área de valor entre sesiones",
    "X5": "Asimetría de desplazamiento alcista/bajista",
    "X6": "Persistencia de concentraciones de volumen durante 5, 10, 20, 40 y 60 sesiones",
}


def measure_to_code() -> dict:
    """Nombre de medida (con _up/_dn si es de dos lados) -> código. V3_close_est va a V3 (C2 comparte la medida)."""
    out = {}
    for e in CATALOG:
        if e.code == "C2":
            continue
        for m in e.measures:
            out[m] = e.code                         # medidas de instante fijo: magnitud |x| con signo aparte
            if e.two_sided and m not in ("C3_vol_est",):
                out[f"{m}_up"], out[f"{m}_dn"] = e.code, e.code
    return out


MEASURE_CODE = measure_to_code()


def direction_of(measure: str) -> int:
    return 1 if measure.endswith("_up") else (-1 if measure.endswith("_dn") else 0)


def event_id(symbol, day, measure, t_first, detector=DETECTOR_VERSION) -> str:
    return hashlib.sha1(f"{symbol}|{day}|{measure}|{t_first}|{detector}".encode()).hexdigest()[:16]


def group_episodes(alerts: list, gap_minutes: int = None) -> list:
    """Agrupa las alertas de un mismo valor y día cuyos intervalos se solapan o distan <= gap_minutes.

    Las alertas se conservan; cada una recibe episode_id. Devuelve la lista de episodios."""
    gap = gap_minutes if gap_minutes is not None else THRESHOLDS["episode_gap_minutes"]
    eps = []
    by_key = {}
    for a in alerts:
        by_key.setdefault((a["symbol"], a["day"]), []).append(a)
    for (sym, day), al in by_key.items():
        al.sort(key=lambda a: a["t_start_utc"])
        cur = None
        for a in al:
            st, en = a["t_start_utc"], a["t_end_utc"]
            if cur and st <= cur["t_end"] + _td(gap):
                cur["alerts"].append(a)
                cur["t_end"] = max(cur["t_end"], en)
            else:
                cur = {"symbol": sym, "day": day, "t_start": st, "t_end": en, "alerts": [a]}
                eps.append(cur)
    out = []
    for ep in eps:
        eid = hashlib.sha1(f"{ep['symbol']}|{ep['day']}|{ep['t_start']}|{DETECTOR_VERSION}".encode()).hexdigest()[:16]
        codes = sorted({a["code"] for a in ep["alerts"]})
        fams = sorted({BY_CODE[c].family for c in codes})
        zs = [min(abs(a["z"]), 10.0) for a in ep["alerts"] if a.get("z") is not None]
        for a in ep["alerts"]:
            a["episode_id"] = eid
        statuses = {a["status"] for a in ep["alerts"]}
        main = max(ep["alerts"], key=lambda a: abs(a["z"]) if a.get("z") is not None and a["z"] == a["z"] else 0)
        out.append({"episode_id": eid, "symbol": ep["symbol"], "day": ep["day"], "t_start_utc": ep["t_start"],
                    "t_end_utc": ep["t_end"], "t_detectable_utc": min(a["t_detectable_utc"] for a in ep["alerts"]),
                    "codes": codes, "families": fams, "main_family": BY_CODE[main["code"]].family
                    if main["code"] in BY_CODE else fams[0], "n_alerts": len(ep["alerts"]),
                    "segments": sorted({a["segment"] for a in ep["alerts"]}),
                    "max_abs_z": max(zs) if zs else None,
                    "status": "indeterminate" if statuses == {"indeterminate"} else
                              ("artifact" if statuses == {"artifact"} else "candidate_bars"),
                    # prioridad para el desglose: diversidad de familias y magnitud; nada de rendimiento posterior
                    "priority": round(len(fams) + (max(zs) / 10 if zs else 0), 3)})
    return out


def _td(minutes):
    import pandas as pd
    return pd.Timedelta(minutes=minutes)


def select_for_drilldown(episodes: list, universe: list, day: str, *, max_priority: int = 5, controls: int = 2,
                         seed: int = 20261118) -> dict:
    """Selección diaria para el desglose con trades (preparada para el registro diario; no se activa en E1).

    - Hasta `max_priority` episodios, diversificados: primero un episodio por familia (rotando) y nunca dos del mismo
      valor; dentro de cada familia, por prioridad. Solo usa lo observado ese día (sin Flow Score ni rendimientos).
    - `controls` ventanas de control al azar (semilla fija por día): un valor del universo y una ventana de 30 minutos,
      tenga o no anomalías.
    """
    pool = [e for e in episodes if e["status"] != "artifact"]
    pool.sort(key=lambda e: (-e["priority"], e["symbol"], e["t_start_utc"]))
    by_fam = {}
    for e in pool:
        by_fam.setdefault(e.get("main_family") or e["families"][0], []).append(e)     # familia de la alerta principal
    chosen, used = [], set()
    fams = sorted(by_fam)
    while len(chosen) < max_priority and any(by_fam.values()):
        for f in fams:
            while by_fam.get(f):
                e = by_fam[f].pop(0)
                if e["symbol"] not in used:
                    chosen.append(e)
                    used.add(e["symbol"])
                    break
            if len(chosen) >= max_priority:
                break
    rng = random.Random(f"{seed}|{day}")
    cand = sorted(set(universe) - used)
    ctrl = []
    for sym in rng.sample(cand, min(controls, len(cand))):
        start_min = rng.randrange(0, 390 - 30)          # minutos desde la apertura (sesión regular completa)
        ctrl.append({"symbol": sym, "day": day, "kind": "control", "start_offset_min": start_min, "minutes": 30})
    return {"priority": [{"episode_id": e["episode_id"], "symbol": e["symbol"], "families": e["families"],
                          "priority": e["priority"]} for e in chosen], "controls": ctrl,
            "rule": "diversificada por familia y valor; controles al azar con semilla fija; sin Flow Score ni "
                    "rendimiento posterior", "seed": seed}
