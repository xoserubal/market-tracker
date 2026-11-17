"""Adaptador de Alpaca (plan gratuito Basic, feed SIP).

- Paginación completa por next_page_token.
- Límite compartido (SharedRateLimiter) antes de cada petición, también en reintentos.
- 429: pausa global hasta X-RateLimit-Reset (o espera exponencial). 5xx / errores de red: reintento exponencial.
- 4xx distintos de 429: error no reintentable (p. ej. 403 por pedir datos de los últimos 15 minutos).
- `asof`: Alpaca enlaza tickers renombrados (activado por defecto). Ojo: con un asof posterior también mezcla
  empresas distintas que usaron el mismo símbolo (caso ADT, ver identity.py). El llamante debe pasar el asof
  de la fecha observada y cortar por épocas.
"""
import time
from typing import Iterator, Optional

import requests

from .base import FetchStats, ProviderError, clean_asof

DATA_BASE = "https://data.alpaca.markets"
TRADING_BASE = "https://paper-api.alpaca.markets"
RESPONSE_KEY = {"bars": "bars", "trades": "trades", "quotes": "quotes"}


class AlpacaProvider:
    name = "alpaca"

    def __init__(self, key: str, secret: str, limiter, session=None, max_retries: int = 6,
                 base_backoff: float = 1.5, page_limit: int = 10000, feed: str = "sip", timeout: float = 60.0):
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.limiter = limiter
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.page_limit = page_limit
        self.feed = feed
        self.timeout = timeout

    # ── HTTP con reintentos ──
    def _get(self, url: str, params: dict, stats: FetchStats):
        last = None
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            stats.requests += 1
            t0 = time.time()
            try:
                r = self.session.get(url, headers=self.headers, params=params, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                stats.seconds += time.time() - t0
                last = ProviderError(f"red: {e}", retryable=True)
                stats.retries += 1
                time.sleep(self.base_backoff * 2 ** attempt)
                continue
            stats.seconds += time.time() - t0
            stats.bytes += len(r.content)
            stats.statuses[r.status_code] = stats.statuses.get(r.status_code, 0) + 1
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                reset = r.headers.get("X-RateLimit-Reset")
                until = float(reset) if reset and reset.isdigit() else time.time() + self.base_backoff * 2 ** attempt
                self.limiter.pause_until(max(until, time.time() + 1))
                stats.retries += 1
                last = ProviderError("429 rate limit", status=429, retryable=True)
                continue
            if r.status_code >= 500:
                stats.retries += 1
                last = ProviderError(f"{r.status_code}: {r.text[:200]}", status=r.status_code, retryable=True)
                time.sleep(self.base_backoff * 2 ** attempt)
                continue
            raise ProviderError(f"{r.status_code}: {r.text[:300]}", status=r.status_code, retryable=False)
        raise last or ProviderError("reintentos agotados", retryable=True)

    # ── datos de mercado ──
    def fetch_pages(self, kind: str, symbol: str, start: str, end: str, *, asof: Optional[str] = None,
                    timeframe: str = "1Min", stats: Optional[FetchStats] = None) -> Iterator[list]:
        if kind not in RESPONSE_KEY:
            raise ValueError(kind)
        stats = stats if stats is not None else FetchStats()
        params = {"start": start, "end": end, "feed": self.feed, "limit": self.page_limit}
        if kind == "bars":
            params.update({"timeframe": timeframe, "adjustment": "raw"})
        asof = clean_asof(asof)
        if asof is not None:
            params["asof"] = asof
        url = f"{DATA_BASE}/v2/stocks/{symbol}/{kind}"
        token = None
        while True:
            p = dict(params)
            if token:
                p["page_token"] = token
            j = self._get(url, p, stats)
            stats.pages += 1
            yield j.get(RESPONSE_KEY[kind]) or []
            token = j.get("next_page_token")
            if not token:
                return

    def calendar(self, start: str, end: str) -> list:
        return self._get(f"{TRADING_BASE}/v2/calendar", {"start": start, "end": end}, FetchStats())

    def corporate_actions(self, symbols: list, start: str, end: str, types: Optional[list] = None) -> dict:
        out = {}
        stats = FetchStats()
        for i in range(0, len(symbols), 50):
            token = None
            while True:
                p = {"symbols": ",".join(symbols[i:i + 50]), "start": start, "end": end, "limit": 1000}
                if types:
                    p["types"] = ",".join(types)
                if token:
                    p["page_token"] = token
                j = self._get(f"{DATA_BASE}/v1/corporate-actions", p, stats)
                for k, v in (j.get("corporate_actions") or {}).items():
                    out.setdefault(k, []).extend(v or [])
                token = j.get("next_page_token")
                if not token:
                    break
        return out
