"""Construcción del proveedor con su limitador compartido."""
from . import config, storage
from .providers.alpaca import AlpacaProvider
from .ratelimit import SharedRateLimiter


def limiter():
    return SharedRateLimiter(storage.root() / "_state" / "ratelimit.sqlite", per_window=config.RATE_PER_MIN, window_s=60)


def alpaca():
    key, secret = config.credentials()
    return AlpacaProvider(key, secret, limiter())
