"""Manifiesto de descargas (SQLite): una fila por unidad (proveedor, tipo, símbolo, asof, periodo, configuración).

Garantiza idempotencia: una unidad 'ok' cuyo fichero existe y conserva su checksum no se vuelve a descargar.
Guarda procedencia (versión de código, parámetros), consumo (peticiones, bytes, segundos, reintentos) y calidad.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS units (
  unit_key TEXT PRIMARY KEY, provider TEXT, kind TEXT, symbol TEXT, asof TEXT, period TEXT, config_hash TEXT,
  config_json TEXT, status TEXT, rows INTEGER, pages INTEGER, requests INTEGER, bytes_api INTEGER, seconds REAL,
  retries INTEGER, path TEXT, sha256 TEXT, file_bytes INTEGER, quality_grade TEXT, quality_json TEXT,
  code_version TEXT, started_utc TEXT, finished_utc TEXT, error TEXT, attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS events (ts TEXT, unit_key TEXT, event TEXT, detail TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Manifest:
    def __init__(self, db_path: Path = None):
        self.db_path = str(db_path or (storage.root() / "manifest" / "manifest.sqlite"))
        with self._c() as c:
            c.executescript(SCHEMA)

    def _c(self):
        c = sqlite3.connect(self.db_path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def get(self, unit_key: str):
        with self._c() as c:
            r = c.execute("SELECT * FROM units WHERE unit_key=?", (unit_key,)).fetchone()
            return dict(r) if r else None

    def is_done(self, unit_key: str, verify_checksum: bool = True) -> bool:
        r = self.get(unit_key)
        if not r or r["status"] not in ("ok", "empty"):
            return False
        if r["status"] == "empty":
            return True
        p = Path(r["path"])
        if not p.exists():
            self.event(unit_key, "missing_file", r["path"])
            return False
        if verify_checksum and storage.sha256_file(p) != r["sha256"]:
            self.event(unit_key, "checksum_mismatch", r["path"])
            return False
        return True

    def start(self, unit_key: str, meta: dict):
        with self._c() as c:
            c.execute("""INSERT INTO units (unit_key, provider, kind, symbol, asof, period, config_hash, config_json, status,
                         code_version, started_utc, attempts) VALUES (?,?,?,?,?,?,?,?, 'running', ?, ?, 1)
                         ON CONFLICT(unit_key) DO UPDATE SET status='running', started_utc=excluded.started_utc,
                         code_version=excluded.code_version, error=NULL, attempts=attempts+1""",
                      (unit_key, meta["provider"], meta["kind"], meta["symbol"], meta["asof"], meta["period"],
                       meta["config_hash"], json.dumps(meta["config"], sort_keys=True), meta["code_version"], now()))
        self.event(unit_key, "start", "")

    def finish(self, unit_key: str, status: str, **fields):
        fields = dict(fields)
        if "quality_json" in fields and not isinstance(fields["quality_json"], str):
            fields["quality_json"] = json.dumps(fields["quality_json"], default=str)
        fields["status"] = status
        fields["finished_utc"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._c() as c:
            c.execute(f"UPDATE units SET {cols} WHERE unit_key=?", (*fields.values(), unit_key))
        self.event(unit_key, status, fields.get("error") or "")

    def record_done_many(self, items: list):
        """Registra de una vez (una transacción) unidades ya escritas en disco: [(unit_key, meta, status, fields)].

        Para la descarga múltiple diaria (E3): cada operación de SQLite en este disco cuesta ~75 ms y una por unidad
        hacía la pasada diaria de horas. Los ficheros se escriben antes (atómicos); si el proceso se corta antes de esta
        transacción, las unidades no constan como hechas y la siguiente pasada las rehace."""
        ts = now()
        with self._c() as c:
            for key, meta, status, fields in items:
                f = dict(fields)
                if "quality_json" in f and not isinstance(f["quality_json"], str):
                    f["quality_json"] = json.dumps(f["quality_json"], default=str)
                c.execute("""INSERT INTO units (unit_key, provider, kind, symbol, asof, period, config_hash, config_json,
                             status, code_version, started_utc, finished_utc, attempts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)
                             ON CONFLICT(unit_key) DO UPDATE SET status=excluded.status, code_version=excluded.code_version,
                             started_utc=excluded.started_utc, finished_utc=excluded.finished_utc, error=NULL,
                             attempts=attempts+1""",
                          (key, meta["provider"], meta["kind"], meta["symbol"], meta["asof"], meta["period"],
                           meta["config_hash"], json.dumps(meta["config"], sort_keys=True), status, meta["code_version"],
                           ts, ts))
                if f:
                    c.execute(f"UPDATE units SET {', '.join(f'{k}=?' for k in f)} WHERE unit_key=?", (*f.values(), key))
                c.execute("INSERT INTO events VALUES (?,?,?,?)", (ts, key, status, str(f.get("quality_json", ""))[:200]))

    def event(self, unit_key: str, event: str, detail: str):
        with self._c() as c:
            c.execute("INSERT INTO events VALUES (?,?,?,?)", (now(), unit_key, event, detail[:2000]))

    def rows(self, where: str = "1=1", params=()):
        with self._c() as c:
            return [dict(r) for r in c.execute(f"SELECT * FROM units WHERE {where}", params).fetchall()]
