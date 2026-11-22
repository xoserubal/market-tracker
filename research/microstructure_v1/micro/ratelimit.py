"""Límite de peticiones compartido entre hilos y procesos.

Ventana deslizante guardada en SQLite (BEGIN IMMEDIATE = un solo escritor a la vez), así que varios procesos de
descarga no pueden superar juntos el límite. También guarda una pausa global cuando el proveedor responde 429.
"""
import sqlite3
import time
from pathlib import Path


class SharedRateLimiter:
    def __init__(self, db_path: Path, per_window: int, window_s: float = 60.0):
        self.db_path = str(db_path)
        self.per_window = per_window
        self.window_s = window_s
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS calls (ts REAL)")
            c.execute("CREATE TABLE IF NOT EXISTS pause (id INTEGER PRIMARY KEY CHECK (id=1), until REAL)")

    def _conn(self):
        c = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def acquire(self) -> float:
        """Bloquea hasta que haya hueco en la ventana, registra la llamada y devuelve la hora de la concesión.

        Garantiza las horas de CONCESIÓN, no las de envío: un hilo puede tardar en enviar tras recibir el turno si el
        equipo va cargado (lo que hacía fallar de forma intermitente test_rate_limiter_threads, que medía después de
        acquire). El margen del límite (180/min frente a los 200 de Alpaca) absorbe ese desfase."""
        while True:
            c = self._conn()
            try:
                c.execute("BEGIN IMMEDIATE")
                now = time.time()
                row = c.execute("SELECT until FROM pause WHERE id=1").fetchone()
                if row and row[0] and row[0] > now:
                    wait = row[0] - now
                    c.execute("COMMIT")
                    time.sleep(min(wait, 5.0))
                    continue
                c.execute("DELETE FROM calls WHERE ts < ?", (now - self.window_s,))
                n, oldest = c.execute("SELECT COUNT(*), MIN(ts) FROM calls").fetchone()
                if n < self.per_window:
                    c.execute("INSERT INTO calls (ts) VALUES (?)", (now,))
                    c.execute("COMMIT")
                    return now
                c.execute("COMMIT")
                wait = oldest + self.window_s - now + 0.05
            finally:
                c.close()
            time.sleep(max(0.05, min(wait, 5.0)))

    def pause_until(self, ts: float):
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO pause (id, until) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET until=MAX(until, excluded.until)",
                      (ts,))
            c.execute("COMMIT")
        finally:
            c.close()

    def calls_in_window(self) -> int:
        c = self._conn()
        try:
            return c.execute("SELECT COUNT(*) FROM calls WHERE ts >= ?", (time.time() - self.window_s,)).fetchone()[0]
        finally:
            c.close()
