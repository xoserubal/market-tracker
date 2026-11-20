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
# OBSOLETO (v3, periodos por índice). Solo lo usan s0_h1_cuts.py y s0_h1_design.py, que reproducen la etapa 0 v3.
# La etapa 1 usa los periodos por talla de abajo (preregistro v3, §2.2).
DEV_END = {"sp500": "2020-12-31", "sp400": "2020-12-31", "sp600": "2022-12-31"}
PRICE_END = "2026-11-13"         # último dato congelado de la etapa 0
HORIZON_MAX = 40

# ---- Periodos por talla (preregistro v3, §2.2). La talla es la de la señal: capitalización en t
# (columna `size` del panel v4: large / mid / small / micro / unknown = «sin capitalización»).
SIZES = ("large", "mid", "small", "micro", "unknown")
DEV_START = "2018-01-02"
LAST_SIGNAL = "2026-09-17"       # última señal con 40 sesiones de datos
DEV_END_BY_SIZE = {"large": "2020-12-31", "mid": "2020-12-31", "unknown": "2020-12-31",
                   "small": "2022-12-30", "micro": "2022-12-30"}
TEST_START_BY_SIZE = {"large": "2021-01-04", "mid": "2021-01-04", "unknown": "2021-01-04",
                      "small": "2023-01-03", "micro": "2023-01-03"}
H1_VERDICT_SIZES = ("large", "mid", "small")     # micro y «sin capitalización»: solo descriptivas (§12.2, punto 2)
COST_ROUND_TRIP = {"large": 0.002, "mid": 0.004, "small": 0.008, "micro": 0.015, "unknown": 0.008}  # §8; sensib. x2 y x3

# Etapa 1 en dos tandas (§1, §12.2 punto 4): la tanda 1 solo ve 2018-2020; la tanda 2 añade los días de
# 2021-2022 de pequeñas y micro, y solo puede empezar cuando exista el archivo de congelación de la tanda 1.
TANDA1_END = "2020-12-31"
TANDA1_FREEZE = PUB / "etapa1_tanda1_frozen.json"


def period_for(size, date):
    """'dev' / 'test' / 'post' para una señal de talla `size` en `date` (YYYY-MM-DD). None antes de DEV_START."""
    if date < DEV_START:
        return None
    if date <= DEV_END_BY_SIZE[size]:
        return "dev"
    if date >= TEST_START_BY_SIZE[size] and date <= LAST_SIGNAL:
        return "test"
    return "post"


def dev_mask(df, tanda):
    """Máscara booleana de las filas de desarrollo que puede ver la tanda indicada (1 o 2). Nunca incluye prueba.

    Exige columnas `size` y `date` (str YYYY-MM-DD). La tanda 2 se niega a correr sin la congelación de la tanda 1.
    """
    if tanda not in (1, 2):
        raise ValueError("tanda debe ser 1 o 2")
    if tanda == 2 and not TANDA1_FREEZE.exists():
        raise RuntimeError(f"Tanda 2 bloqueada: falta la congelación de la tanda 1 ({TANDA1_FREEZE})")
    size = df["size"].astype(str)
    date = df["date"].astype(str)
    end = size.map(DEV_END_BY_SIZE)
    if end.isna().any():
        raise ValueError(f"Tallas desconocidas: {sorted(set(size[end.isna()]))}")
    m = (date >= DEV_START) & (date <= end)
    if tanda == 1:
        m &= date <= TANDA1_END
    return m

# Alpaca: límite propio, por debajo de 200/min (otro equipo puede estar usando la misma cuenta)
RATE_PER_MIN = int(os.environ.get("FLOWNEG_RATE_PER_MIN", "150"))

sys.path.insert(0, str(REPO / "research" / "microstructure_v1"))
sys.path.insert(0, str(REPO / "scripts"))


def alpaca():
    from micro.providers.alpaca import AlpacaProvider
    from micro.ratelimit import SharedRateLimiter
    key, sec = os.environ["ALPACA_API_KEY"].strip(), os.environ["ALPACA_API_SECRET"].strip()
    return AlpacaProvider(key, sec, SharedRateLimiter(DATA / "_state" / "ratelimit.sqlite", per_window=RATE_PER_MIN))
