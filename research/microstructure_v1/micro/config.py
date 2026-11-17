"""Configuración: rutas, límites y versión del código.

Todo lo que ocupa disco vive en MICRO_DATA_DIR (fuera del repo y de Dropbox).
"""
import hashlib
import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

logging.getLogger("dotenv.main").setLevel(logging.ERROR)  # la línea 14 del .env no es una variable (preexistente)

PKG_DIR = Path(__file__).resolve().parent
STUDY_DIR = PKG_DIR.parent
REPO_ROOT = STUDY_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")

RATE_PER_MIN = int(os.environ.get("MICRO_RATE_PER_MIN", "180"))     # margen bajo el límite de 200/min de Alpaca
MIN_FREE_GB = float(os.environ.get("MICRO_MIN_FREE_GB", "40"))       # parada segura: nunca dejar el disco por debajo
PAGE_LIMIT = 10000


class ConfigError(RuntimeError):
    pass


def data_dir(create=True) -> Path:
    raw = os.environ.get("MICRO_DATA_DIR", "").strip()
    if not raw:
        raise ConfigError("Falta MICRO_DATA_DIR en el entorno/.env")
    p = Path(raw).resolve()
    low = str(p).lower()
    if "dropbox" in low:
        raise ConfigError(f"MICRO_DATA_DIR no puede estar dentro de Dropbox: {p}")
    try:
        p.relative_to(REPO_ROOT)
        raise ConfigError(f"MICRO_DATA_DIR no puede estar dentro del repositorio: {p}")
    except ValueError:
        pass
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def credentials():
    key = os.environ.get("ALPACA_API_KEY", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    if not key or not secret:
        raise ConfigError("Faltan ALPACA_API_KEY / ALPACA_API_SECRET en .env")
    return key, secret


@lru_cache(maxsize=1)
def code_version() -> str:
    """Hash del código del paquete: se guarda en cada unidad del manifiesto (trazabilidad de transformaciones).

    Se calcula una vez por proceso: un proceso largo registra la versión con la que arrancó aunque el código cambie."""
    h = hashlib.sha256()
    for f in sorted(PKG_DIR.rglob("*.py")):
        h.update(f.relative_to(PKG_DIR).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:12]
