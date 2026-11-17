"""Exposición del periodo de prueba y exclusiones proporcionadas (política de G2, pendiente del preregistro).

Principio: se excluye del contraste confirmatorio lo que pudo influir en una decisión, y nada más. No se eliminan
fechas completas de todas las acciones salvo que lo visto en esa fecha sea de mercado entero.

Niveles de exposición (de menos a más):
- E0 «técnica»: descarga, calidad, conciliación, identidad, cobertura, liquidez previa para muestrear. No se
  calcula ninguna variable candidata ni ningún resultado. -> no se excluye nada.
- E1 «estadística sin resultados»: estadísticas descriptivas de la microestructura (p. ej. concordancia de
  clasificadores, cuota de TRF) sin rentabilidades posteriores. -> no se excluye la observación; esas cifras no se
  pueden usar para elegir métodos ni parámetros (las elecciones se justifican solo con desarrollo), y el contraste
  se repite sin esas ventanas como sensibilidad.
- E2 «variable candidata vista»: se miró un episodio con las variables candidatas (footprint, delta, anomalía) sin
  ver lo que pasó después. -> se excluyen de ese valor las observaciones con fecha de decisión t en
  [día - H, día + L] (H = horizonte más largo, L = ventana más larga de las variables): son las que tienen ese día
  dentro de su resultado (t < día ≤ t + H) o de sus variables (t - L ≤ día ≤ t). Solo ese valor.
- E3 «resultado visto»: se vio el precio posterior (anotación retrospectiva, selección por resultado). -> igual
  que E2. Si la selección se hizo cribando muchos valores por su resultado, se excluyen las ventanas de todos los
  valores cribados, no las fechas enteras del mercado.
- M «de mercado»: se miró un dato o resultado agregado de todo el mercado en una fecha (índice, amplitud) para
  decidir algo. -> se excluyen las observaciones de todos los valores con t en [día - H, día + L].
Además, cualquier método o parámetro elegido con información del periodo de prueba degrada a exploratoria la
hipótesis que lo usa: eso no se arregla excluyendo observaciones.
"""
from dataclasses import dataclass

LEVELS = ("E0", "E1", "E2", "E3", "M")
EXCLUDING = {"E2", "E3", "M"}


@dataclass(frozen=True)
class Exposure:
    level: str
    symbol: str          # "*" para exposición de mercado
    first: str           # primera fecha expuesta (YYYY-MM-DD)
    last: str            # última fecha expuesta
    what: str
    source: str

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"nivel desconocido {self.level}")
        if self.level == "M" and self.symbol != "*":
            raise ValueError("la exposición de mercado se registra con symbol='*'")


def exclusion_windows(exposures, trading_days: list, lookback: int, horizon: int) -> list:
    """Ventanas de fechas de decisión (symbol, desde, hasta) a excluir del contraste confirmatorio.

    Una observación con fecha t usa variables de [t - lookback, t] y resultado de (t, t + horizon]; un día expuesto d
    la afecta si t está en [d - horizon, d + lookback]. E0/E1 no excluyen nada.
    """
    pos = {d: i for i, d in enumerate(trading_days)}

    def idx(d, side):
        if d in pos:
            return pos[d]
        cands = [i for x, i in pos.items() if (x >= d if side == "first" else x <= d)]
        return (min(cands) if side == "first" else max(cands)) if cands else None

    out = []
    for e in exposures:
        if e.level not in EXCLUDING:
            continue
        a, b = idx(e.first, "first"), idx(e.last, "last")
        if a is None or b is None:
            continue
        out.append({"symbol": e.symbol, "from": trading_days[max(0, a - horizon)],
                    "to": trading_days[min(len(trading_days) - 1, b + lookback)], "level": e.level, "why": e.what})
    return out


def is_excluded(symbol: str, day: str, windows: list) -> bool:
    return any((w["symbol"] in ("*", symbol)) and w["from"] <= day <= w["to"] for w in windows)
