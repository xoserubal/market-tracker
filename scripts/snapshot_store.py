"""Lectura y reparto de los snapshots diarios grandes (implementado 2026-11-11).

`portfolio_daily_snapshot.jsonl` (~0,44 MB/día) y `market_equities_daily_snapshot.jsonl` crecen sin límite y
llegarían a los límites de GitHub (avisa a 50 MB, rechaza a 100 MB). El fichero vivo conserva solo los últimos
LIVE_DAYS días; lo anterior pasa a `docs/data/archive/<nombre>/AAAA-MM.jsonl` (un fichero por mes de la fecha de
captura). Las páginas del navegador leen solo el fichero vivo; los scripts que necesitan toda la historia usan
`read_rows()` / `iter_lines()`, que concatenan archivo + vivo en orden.

Las filas de una misma clave (fecha, ticker) siempre caen en el mismo fichero y mantienen su orden relativo, así que
la semántica "la última gana" de los lectores no cambia. Si el reparto se interrumpe entre escribir el archivo y
reescribir el vivo, una línea puede quedar en los dos sitios: la lectura descarta las líneas idénticas repetidas.

Espejo en Node: shared/snapshot-store.js (mantener sincronizados).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
LIVE_DAYS = 75
ROTATED = ("portfolio_daily_snapshot.jsonl", "market_equities_daily_snapshot.jsonl")


def archive_dir(path: Path) -> Path:
    path = Path(path)
    return path.parent / "archive" / path.stem


def archive_files(path: Path) -> list[Path]:
    d = archive_dir(path)
    return sorted(d.glob("*.jsonl")) if d.is_dir() else []


def iter_lines(path: Path) -> Iterator[str]:
    """Líneas no vacías del archivo mensual (meses en orden) y después del fichero vivo. Sin archivo, solo el vivo."""
    path = Path(path)
    seen: set[bytes] = set()
    for f in archive_files(path):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.strip():
                    seen.add(hashlib.md5(line.encode()).digest())
                    yield line
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.strip() and (not seen or hashlib.md5(line.encode()).digest() not in seen):
                    yield line


def read_rows(path: Path) -> list[dict]:
    """Filas JSON de toda la historia (archivo + vivo); ignora líneas ilegibles."""
    out = []
    for line in iter_lines(path):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _row_date(line: str) -> str | None:
    try:
        d = json.loads(line).get("date")
    except (json.JSONDecodeError, AttributeError):
        return None
    return d if isinstance(d, str) and len(d) >= 10 else None


def rotate(path: Path, today: date, live_days: int = LIVE_DAYS, dry_run: bool = False) -> dict:
    """Mueve al archivo mensual las filas con fecha de captura anterior a today - live_days."""
    path = Path(path)
    if not path.exists():
        return {"file": path.name, "moved": 0, "kept": 0}
    cutoff = (today - timedelta(days=live_days)).isoformat()
    keep, move = [], {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            d = _row_date(line)
            if d is not None and d[:10] < cutoff:
                move.setdefault(d[:7], []).append(line)
            else:
                keep.append(line)
    n_moved = sum(len(v) for v in move.values())
    if dry_run or not n_moved:
        return {"file": path.name, "moved": n_moved, "kept": len(keep), "months": sorted(move), "cutoff": cutoff}
    adir = archive_dir(path)
    adir.mkdir(parents=True, exist_ok=True)
    for month, lines in sorted(move.items()):
        af = adir / f"{month}.jsonl"
        existing = set()
        if af.exists():
            existing = {l.rstrip("\n") for l in af.open(encoding="utf-8") if l.strip()}
        new = [l for l in lines if l not in existing]
        if new:
            with af.open("a", encoding="utf-8", newline="\n") as fh:  # LF, como los escritores de Node
                fh.write("\n".join(new) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(keep) + ("\n" if keep else ""))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return {"file": path.name, "moved": n_moved, "kept": len(keep), "months": sorted(move), "cutoff": cutoff}


def live_cutoff(today: date, live_days: int = LIVE_DAYS) -> str:
    return (today - timedelta(days=live_days)).isoformat()
