"""Biblioteca de patrones: episodios, anotaciones (humanas / IA / regla) y registro de accesos del visor.

Vive en MICRO_DATA_DIR/library/ (privado: guarda precios y volúmenes derivados de datos con licencia personal).

Principios:
- Una etiqueta describe lo observado en los datos ejecutados, no la intención de los participantes.
- Procedencia: cada episodio guarda las unidades de datos (unit_key + sha256), la versión del código y los parámetros
  de cálculo; cada anotación guarda quién la hizo (humano, modelo con versión, o regla con versión).
- Información disponible: cada anotación guarda el cursor (hasta dónde se veía) y si el anotador ya había visto datos
  posteriores. Esto último NO lo declara el anotador: se deduce del registro de accesos del visor
  (`revealed_future`). Una anotación con revealed_future=True es retrospectiva: sirve para generar hipótesis,
  nunca como evidencia confirmatoria.
- Periodo de prueba: todo acceso del visor a fechas del periodo de prueba queda en el registro; esas fechas (y sus
  ventanas informativas) se excluyen del conjunto confirmatorio (`contaminated_test_dates`).
- Pensada para aprendizaje supervisado: ejemplos positivos, negativos (no_pattern), ambiguos (indeterminate) y
  contraejemplos enlazados (`counterexample_of`); taxonomía versionada.
"""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config, storage

TAXONOMY_VERSION = "v1"
LABELS = {
    "capitulation_sell": "Posible capitulación vendedora",
    "absorption_buy": "Posible absorción compradora",
    "accumulation": "Posible acumulación",
    "distribution": "Posible distribución",
    "buy_pressure_rising": "Presión compradora creciente",
    "sell_pressure_falling": "Presión vendedora decreciente",
    "failed_breakout": "Ruptura fallida",
    "no_pattern": "Ausencia de patrón",
    "indeterminate": "Indeterminado",
}
ANNOTATOR_TYPES = ("human", "ai", "rule")
# Partición propuesta (G2): fechas de decisión del periodo de prueba + embargo de 40 sesiones antes de él.
TEST_START, TEST_END = "2022-01-03", "2026-09-14"
EMBARGO_START = "2021-10-29"

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY, symbol TEXT, entity TEXT, company TEXT, day TEXT, start_utc TEXT, end_utc TEXT,
  tf_minutes INTEGER, method TEXT, step REAL, price_lo REAL, price_hi REAL, proposed_label TEXT,
  data_units TEXT, code_version TEXT, params_json TEXT, metrics_json TEXT, quality_json TEXT,
  selection_note TEXT, outcome_known_at_selection INTEGER, in_test_period INTEGER, created_utc TEXT, created_by TEXT,
  taxonomy_version TEXT);
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY, kind TEXT, symbol TEXT, start_day TEXT, end_day TEXT, start_utc TEXT, end_utc TEXT,
  catalog TEXT, catalog_episode_id TEXT, alert_ids TEXT, data_units TEXT, params_json TEXT, metrics_json TEXT,
  note TEXT, outcome_known_at_selection INTEGER, in_test_period INTEGER, code_version TEXT, created_utc TEXT,
  created_by TEXT);
CREATE TABLE IF NOT EXISTS annotations (
  annotation_id TEXT PRIMARY KEY, episode_id TEXT, annotator_type TEXT, annotator_id TEXT, label TEXT,
  confidence REAL, justification TEXT, cursor_utc TEXT, revealed_future INTEGER, max_seen_utc TEXT,
  price_levels TEXT, interval_json TEXT, counterexample_of TEXT, ambiguous INTEGER, created_utc TEXT,
  taxonomy_version TEXT, code_version TEXT);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ts_iso(ts) -> str:
    """Formato fijo (UTC, microsegundos, sufijo Z) para que las comparaciones de texto sean cronológicas."""
    import pandas as pd
    if ts is None:
        return None
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def lib_dir() -> Path:
    d = storage.root() / "library"
    d.mkdir(exist_ok=True)
    return d


def in_test_period(day: str) -> bool:
    return EMBARGO_START <= day <= TEST_END


class Library:
    def __init__(self, path: Path = None):
        self.path = str(path or (lib_dir() / "library.sqlite"))
        with self._c() as c:
            c.executescript(SCHEMA)

    def _c(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    # ── accesos del visor ──
    @staticmethod
    def log_access(rec: dict, path: Path = None):
        p = path or (lib_dir() / "access_log.jsonl")
        rec = {"ts": _now(), **rec, "in_test_period": in_test_period(rec.get("day", ""))}
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    @staticmethod
    def accesses(symbol: str = None, day: str = None, path: Path = None) -> list:
        p = path or (lib_dir() / "access_log.jsonl")
        if not Path(p).exists():
            return []
        out = []
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            if (symbol is None or r.get("symbol") == symbol) and (day is None or r.get("day") == day):
                out.append(r)
        return out

    def max_seen(self, symbol: str, day: str, before_ts: str = None, path: Path = None):
        """Último instante de mercado mostrado por el visor para ese valor y día (antes de `before_ts`)."""
        seen = [r.get("max_t_returned") for r in self.accesses(symbol, day, path)
                if r.get("max_t_returned") and (before_ts is None or r["ts"] <= before_ts)]
        return max(seen) if seen else None

    def contaminated_test_dates(self, path: Path = None) -> list:
        """(símbolo, día) del periodo de prueba (o su embargo) vistos en el visor: excluir del conjunto confirmatorio."""
        s = {(r["symbol"], r["day"]) for r in self.accesses(path=path) if r.get("in_test_period")}
        return sorted(s)

    # ── episodios ──
    def add_episode(self, ep: dict) -> str:
        base = f"{ep['symbol']}|{ep['day']}|{ep.get('start_utc')}|{ep.get('end_utc')}|{_now()}"
        eid = ep.get("episode_id") or f"ep_{ep['day'].replace('-', '')}_{ep['symbol']}_{hashlib.sha1(base.encode()).hexdigest()[:6]}"
        row = {"episode_id": eid, "symbol": ep["symbol"], "entity": ep.get("entity"), "company": ep.get("company"),
               "day": ep["day"], "start_utc": ep.get("start_utc"), "end_utc": ep.get("end_utc"),
               "tf_minutes": ep.get("tf_minutes"), "method": ep.get("method"), "step": ep.get("step"),
               "price_lo": ep.get("price_lo"), "price_hi": ep.get("price_hi"),
               "proposed_label": ep.get("proposed_label"),
               "data_units": json.dumps(ep.get("data_units", []), default=str),
               "code_version": config.code_version(), "params_json": json.dumps(ep.get("params", {}), default=str),
               "metrics_json": json.dumps(ep.get("metrics", {}), default=str),
               "quality_json": json.dumps(ep.get("quality", {}), default=str),
               "selection_note": ep.get("selection_note", ""),
               "outcome_known_at_selection": int(bool(ep.get("outcome_known_at_selection"))),
               "in_test_period": int(in_test_period(ep["day"])), "created_utc": _now(),
               "created_by": ep.get("created_by", "human"), "taxonomy_version": TAXONOMY_VERSION}
        if row["proposed_label"] and row["proposed_label"] not in LABELS:
            raise ValueError(f"etiqueta desconocida: {row['proposed_label']}")
        with self._c() as c:
            c.execute(f"INSERT INTO episodes ({','.join(row)}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))
        return eid

    # ── casos de investigación (acceso libre, 2026-11-21) ──
    CASE_KINDS = ("manual_window", "catalog_episode", "multi_session")

    def add_case(self, c: dict) -> str:
        """Ventana consultada guardada como caso trazable: qué se miró, con qué datos (unidades y sha256), con qué
        parámetros y versión de código, y si el resultado posterior ya se conocía al elegirla. No lleva etiqueta."""
        if c.get("kind") not in self.CASE_KINDS:
            raise ValueError(f"tipo de caso desconocido: {c.get('kind')}")
        base = f"{c['symbol']}|{c.get('start_utc')}|{c.get('end_utc')}|{_now()}|{uuid.uuid4().hex}"
        cid = f"case_{c['start_day'].replace('-', '')}_{c['symbol']}_{hashlib.sha1(base.encode()).hexdigest()[:6]}"
        row = {"case_id": cid, "kind": c["kind"], "symbol": c["symbol"], "start_day": c["start_day"],
               "end_day": c.get("end_day") or c["start_day"], "start_utc": c.get("start_utc"), "end_utc": c.get("end_utc"),
               "catalog": c.get("catalog"), "catalog_episode_id": c.get("catalog_episode_id"),
               "alert_ids": json.dumps(c.get("alert_ids", [])), "data_units": json.dumps(c.get("data_units", []), default=str),
               "params_json": json.dumps(c.get("params", {}), default=str),
               "metrics_json": json.dumps(c.get("metrics", {}), default=str), "note": c.get("note", ""),
               "outcome_known_at_selection": int(bool(c.get("outcome_known_at_selection"))),
               "in_test_period": int(in_test_period(c["start_day"]) or in_test_period(c.get("end_day") or c["start_day"])),
               "code_version": config.code_version(), "created_utc": _now(), "created_by": c.get("created_by", "human")}
        with self._c() as cx:
            cx.execute(f"INSERT INTO cases ({','.join(row)}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))
        return cid

    def cases(self, symbol: str = None) -> list:
        q, p = "SELECT * FROM cases", []
        if symbol:
            q, p = q + " WHERE symbol=?", [symbol]
        with self._c() as cx:
            return [dict(r) for r in cx.execute(q + " ORDER BY created_utc DESC", p).fetchall()]

    def episodes(self, symbol: str = None, day: str = None) -> list:
        q, p = "SELECT * FROM episodes WHERE 1=1", []
        if symbol:
            q, p = q + " AND symbol=?", p + [symbol]
        if day:
            q, p = q + " AND day=?", p + [day]
        with self._c() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY created_utc", p).fetchall()]

    # ── anotaciones ──
    def annotate(self, a: dict, access_path: Path = None) -> str:
        if a["label"] not in LABELS:
            raise ValueError(f"etiqueta desconocida: {a['label']}")
        if a.get("annotator_type", "human") not in ANNOTATOR_TYPES:
            raise ValueError("annotator_type debe ser human, ai o rule")
        if a.get("annotator_type") in ("ai", "rule") and not a.get("annotator_id"):
            raise ValueError("una anotación de IA o regla debe identificar el modelo/regla y su versión")
        with self._c() as c:
            ep = c.execute("SELECT symbol, day FROM episodes WHERE episode_id=?", (a["episode_id"],)).fetchone()
        if not ep:
            raise ValueError("episodio inexistente")
        now = _now()
        max_seen = self.max_seen(ep["symbol"], ep["day"], before_ts=now, path=access_path)
        cursor = ts_iso(a.get("cursor_utc")) if a.get("cursor_utc") else None
        revealed = bool(max_seen and (cursor is None or max_seen > cursor))
        aid = "an_" + uuid.uuid4().hex[:12]
        row = {"annotation_id": aid, "episode_id": a["episode_id"], "annotator_type": a.get("annotator_type", "human"),
               "annotator_id": a.get("annotator_id", "usuario"), "label": a["label"],
               "confidence": a.get("confidence"), "justification": a.get("justification", ""),
               "cursor_utc": cursor, "revealed_future": int(revealed), "max_seen_utc": max_seen,
               "price_levels": json.dumps(a.get("price_levels", [])), "interval_json": json.dumps(a.get("interval", {})),
               "counterexample_of": a.get("counterexample_of"), "ambiguous": int(bool(a.get("ambiguous"))),
               "created_utc": now, "taxonomy_version": TAXONOMY_VERSION, "code_version": config.code_version()}
        with self._c() as c:
            c.execute(f"INSERT INTO annotations ({','.join(row)}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))
        return aid

    def annotations(self, episode_id: str = None) -> list:
        q, p = "SELECT * FROM annotations", []
        if episode_id:
            q, p = q + " WHERE episode_id=?", [episode_id]
        with self._c() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY created_utc", p).fetchall()]

    def export_for_learning(self) -> list:
        """Tabla plana episodio × anotación, separando prospectivas de retrospectivas (para modelos futuros)."""
        eps = {e["episode_id"]: e for e in self.episodes()}
        out = []
        for a in self.annotations():
            e = eps.get(a["episode_id"], {})
            out.append({**{k: e.get(k) for k in ("symbol", "day", "start_utc", "end_utc", "in_test_period",
                                                  "outcome_known_at_selection", "metrics_json")},
                        **{k: a[k] for k in ("annotation_id", "episode_id", "annotator_type", "annotator_id", "label",
                                             "confidence", "revealed_future", "ambiguous", "counterexample_of",
                                             "taxonomy_version")},
                        "usable_as_confirmatory": (not a["revealed_future"] and not e.get("in_test_period")
                                                   and not e.get("outcome_known_at_selection"))})
        return out
