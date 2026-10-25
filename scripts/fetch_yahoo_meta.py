"""
fetch_yahoo_meta.py — hechos de Yahoo Finance por ticker del Portfolio (capa 3 del diseño de etiquetas).

Qué es y qué NO es:
  · Referencia informativa y regenerable: quoteType, sector, industria, país de domicilio, nombre legal, bolsa y divisa.
  · NO es fuente de verdad ni prueba de identidad (su ISIN no es fiable y el sector/industria no describe la exposición
    económica: MSTR sale como software). Ninguna etiqueta se crea ni se valida solo con esto.
  · Ningún motor de inversión lo lee (lo comprueba scripts/test_tags_invariance.py).

Uso manual (requiere yfinance; en esta máquina `py -3.12`):
    py -3.12 scripts/fetch_yahoo_meta.py              # todos los tickers de portfolio.json
    py -3.12 scripts/fetch_yahoo_meta.py --tickers NVDA,GGAL
Escribe docs/data/ticker_yahoo_meta.json (conserva los tickers no solicitados).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "ticker_yahoo_meta.json"
FIELDS = ("quoteType", "sector", "industry", "country", "longName", "exchange", "currency")


def portfolio_tickers() -> list[str]:
    pf = json.loads((ROOT / "portfolio.json").read_text(encoding="utf-8"))
    seen: list[str] = []
    for sec in pf.get("sections", []):
        for it in sec.get("items", []):
            t = it.get("ticker")
            if t and t not in seen:
                seen.append(t)
    return seen


def fetch_one(yf, ticker: str) -> dict:
    last = None
    for attempt in range(3):
        try:
            info = yf.Ticker(ticker).info or {}
            if not info or (info.get("quoteType") is None and not info.get("longName")):
                raise ValueError("sin datos")
            return {k: info.get(k) for k in FIELDS}
        except Exception as exc:                      # red, 404 de símbolo, límite de peticiones…
            last = str(exc)[:120]
            time.sleep(1.5 * (attempt + 1))
    return {"error": last or "desconocido"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", help="lista separada por comas (por defecto, todos los de portfolio.json)")
    args = ap.parse_args()
    try:
        import yfinance as yf
    except ImportError:
        print("Falta yfinance (prueba con `py -3.12`).", file=sys.stderr)
        return 2
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else portfolio_tickers()
    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8")).get("tickers", {})
        except ValueError:
            prev = {}
    out = dict(prev)
    errors = []
    for i, t in enumerate(tickers, 1):
        out[t] = fetch_one(yf, t)
        if "error" in out[t]:
            errors.append(t)
        time.sleep(0.15)
    doc = {"source": "yfinance (Yahoo Finance quoteSummary)", "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "warning": "Referencia informativa. No es prueba de identidad ni describe la exposición económica.",
           "tickers": dict(sorted(out.items()))}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(tickers) - len(errors)}/{len(tickers)} tickers con datos -> {OUT.relative_to(ROOT)}")
    if errors:
        print("sin datos:", ", ".join(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
