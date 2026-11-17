"""Interfaz neutra de proveedor de datos (Alpaca hoy; Databento u otros mañana)."""
from dataclasses import dataclass, field
from typing import Iterator, Optional, Protocol

KINDS = ("bars", "trades", "quotes")


def clean_asof(asof):
    """asof válido = cadena no vacía; None/NaN/'' -> None (pandas convierte None en NaN dentro de columnas)."""
    return asof if isinstance(asof, str) and asof.strip() else None


class ProviderError(RuntimeError):
    def __init__(self, msg, status=None, retryable=False):
        super().__init__(msg)
        self.status = status
        self.retryable = retryable


@dataclass
class FetchStats:
    requests: int = 0
    pages: int = 0
    bytes: int = 0
    retries: int = 0
    seconds: float = 0.0
    statuses: dict = field(default_factory=dict)

    def add(self, other: "FetchStats"):
        self.requests += other.requests
        self.pages += other.pages
        self.bytes += other.bytes
        self.retries += other.retries
        self.seconds += other.seconds
        for k, v in other.statuses.items():
            self.statuses[k] = self.statuses.get(k, 0) + v


class Provider(Protocol):
    name: str

    def fetch_pages(self, kind: str, symbol: str, start: str, end: str, *, asof: Optional[str] = None,
                    timeframe: str = "1Min", stats: Optional[FetchStats] = None) -> Iterator[list]:
        """Itera páginas (listas de registros) de bars/trades/quotes para [start, end) en UTC ISO."""

    def calendar(self, start: str, end: str) -> list:
        """Sesiones del mercado: date, open, close (hora de NY)."""

    def corporate_actions(self, symbols: list, start: str, end: str, types: Optional[list] = None) -> dict:
        """Acciones corporativas agrupadas por tipo."""
