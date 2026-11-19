"""Configuración del estudio de Flow negativo (etapa 0).

Los datos de Alpaca no se pueden redistribuir: todo lo que contenga precios por valor y día vive en FLOWNEG_DATA_DIR,
fuera del repositorio y de Dropbox. En el repo solo hay código, composición de índices (pública) y agregados.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
load_dotenv(REPO / ".env")

# Por defecto: D: en el equipo que la tiene (C: casi llena allí); si no, la carpeta local de DESPACHOB.
_D_DEFAULT = Path(r"D:\backup market tracker\flow_negative_v1")
_DEFAULT = _D_DEFAULT if _D_DEFAULT.parent.exists() else Path(r"C:\Users\Usuario\market_data\flow_negative_v1")
DATA = Path(os.environ.get("FLOWNEG_DATA_DIR", str(_DEFAULT))).resolve()
if "dropbox" in str(DATA).lower():
    raise RuntimeError(f"FLOWNEG_DATA_DIR no puede estar en Dropbox: {DATA}")
try:
    DATA.relative_to(REPO)
    raise RuntimeError(f"FLOWNEG_DATA_DIR no puede estar dentro del repositorio: {DATA}")
except ValueError:
    pass
DATA.mkdir(parents=True, exist_ok=True)

WIKI = DATA / "wiki"
BARS = DATA / "bars"            # barras diarias en bruto de Alpaca, una por petición (símbolo, asof)
CA = DATA / "corporate_actions"
SEC = DATA / "sec"
WORK = DATA / "work"
for p in (WIKI, BARS, CA, SEC, WORK):
    p.mkdir(parents=True, exist_ok=True)

PUB = HERE / "data"              # en el repo: composición y agregados, nunca precios
PUB.mkdir(exist_ok=True)

# Fechas (preregistro §2)
PRICE_START = "2015-01-01"       # calentamiento: ~260 sesiones antes de la primera señal
SIGNAL_START = {"sp500": "2016-01-04", "sp400": "2016-01-04", "sp600": "2020-01-02"}
DEV_END = {"sp500": "2020-12-31", "sp400": "2020-12-31", "sp600": "2022-12-31"}
PRICE_END = "2026-11-13"         # último dato congelado de la etapa 0
HORIZON_MAX = 40

# Alpaca: límite propio, por debajo de 200/min (otro equipo puede estar usando la misma cuenta)
RATE_PER_MIN = int(os.environ.get("FLOWNEG_RATE_PER_MIN", "150"))

sys.path.insert(0, str(REPO / "research" / "microstructure_v1"))
sys.path.insert(0, str(REPO / "scripts"))


def alpaca():
    from micro.providers.alpaca import AlpacaProvider
    from micro.ratelimit import SharedRateLimiter
    key, sec = os.environ["ALPACA_API_KEY"].strip(), os.environ["ALPACA_API_SECRET"].strip()
    return AlpacaProvider(key, sec, SharedRateLimiter(DATA / "_state" / "ratelimit.sqlite", per_window=RATE_PER_MIN))
