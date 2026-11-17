"""Almacenamiento privado: capas, escritura atómica, checksums y parada segura por disco.

Capas en MICRO_DATA_DIR:
  raw/         registros del proveedor sin pérdida (Parquet zstd). Retención: 100 % (decisión G1).
  normalized/  vistas tipadas con flags de sesión/condiciones (materialización opcional).
  features/    variables derivadas (G2+).   datasets/  paneles experimentales.   results/  resultados.
  reference/   calendario, acciones corporativas, universo, épocas de identidad.
  manifest/    manifest.sqlite.   samples/  planes de muestreo congelados.   _state/  limitador.   tmp/
"""
import hashlib
import os
import shutil
from pathlib import Path

import pandas as pd

from . import config

LAYERS = ("raw", "normalized", "features", "datasets", "results", "reference", "manifest", "samples", "_state", "tmp")


class DiskGuardError(RuntimeError):
    pass


def root() -> Path:
    r = config.data_dir()
    for layer in LAYERS:
        (r / layer).mkdir(exist_ok=True)
    return r


def safe_sym(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_")


def raw_path(provider: str, kind: str, symbol: str, asof: str, period: str, config_hash: str = None) -> Path:
    """Ruta del fichero de una unidad. Con `config_hash` el nombre es único por configuración: dos ventanas horarias
    del mismo día (o dos configuraciones del mismo mes) nunca escriben el mismo fichero.

    Las unidades anteriores a 2026-11-15 10:10 UTC se escribieron sin hash (una sola configuración por unidad en
    la descarga masiva); el manifiesto guarda la ruta real de cada unidad y es la única referencia válida."""
    name = f"{period}.parquet" if not config_hash else f"{period}__{config_hash}.parquet"
    return root() / "raw" / provider / kind / f"symbol={safe_sym(symbol)}" / f"asof={asof or '-'}" / name


def free_bytes(path: Path = None) -> int:
    return shutil.disk_usage(path or root()).free


def disk_guard(expected_bytes: int = 0, min_free_gb: float = None):
    """Lanza DiskGuardError si escribir `expected_bytes` dejaría el disco por debajo del margen."""
    min_free = (min_free_gb if min_free_gb is not None else config.MIN_FREE_GB) * 1e9
    free = free_bytes()
    if free - expected_bytes < min_free:
        raise DiskGuardError(f"espacio insuficiente: libre {free / 1e9:.1f} GB, se necesitan {expected_bytes / 1e9:.2f} GB "
                             f"+ margen {min_free / 1e9:.0f} GB")
    return free


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_parquet_atomic(df: pd.DataFrame, path: Path) -> tuple:
    """Escribe en tmp/ del mismo disco y renombra: nunca deja un fichero a medias en su ruta final."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = root() / "tmp" / f"{path.name}.{os.getpid()}.{id(df)}.part"
    try:
        df.to_parquet(tmp, compression="zstd", index=False)
        digest = sha256_file(tmp)
        size = tmp.stat().st_size
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return digest, size


def usage_by_layer() -> dict:
    r = root()
    out = {}
    for layer in LAYERS:
        out[layer] = sum(f.stat().st_size for f in (r / layer).rglob("*") if f.is_file())
    return out
