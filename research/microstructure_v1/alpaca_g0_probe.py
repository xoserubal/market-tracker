"""G0 — sonda de viabilidad de Alpaca (plan gratuito Basic).

Mide, con las credenciales reales del .env, qué endpoints responden y cuánto
pesa una sesión de barras de 1 minuto, trades y quotes para una muestra
pequeña de valores de liquidez distinta.

No es parte de ningún experimento: es medición de recursos (puerta G0).
Los datos crudos se guardan en MICRO_DATA_DIR/g0_probe (fuera del repo y de
Dropbox), igual que los resultados (registros de mercado: no se redistribuyen).

Uso:
  py -3 research/microstructure_v1/alpaca_g0_probe.py access     # pruebas de acceso (pocas peticiones)
  py -3 research/microstructure_v1/alpaca_g0_probe.py volume     # medición de volumen de una sesión
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
KEY = os.environ.get("ALPACA_API_KEY", "").strip()
SECRET = os.environ.get("ALPACA_API_SECRET", "").strip()
DATA_DIR = Path(os.environ.get("MICRO_DATA_DIR", "").strip() or "")
BASE = "https://data.alpaca.markets"
OUT = DATA_DIR / "g0_probe" / "g0_probe_results.json"  # fuera del repo: contiene registros de mercado

HEAD = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET}
MAX_PER_MIN = 180  # margen bajo el límite de 200/min
_calls = []
_stats = {"requests": 0, "bytes": 0}


def _throttle():
    now = time.time()
    while _calls and now - _calls[0] > 60:
        _calls.pop(0)
    if len(_calls) >= MAX_PER_MIN:
        time.sleep(60 - (now - _calls[0]) + 0.2)
    _calls.append(time.time())


def get(path, params, retries=4):
    for attempt in range(retries):
        _throttle()
        r = requests.get(BASE + path, headers=HEAD, params=params, timeout=60)
        _stats["requests"] += 1
        _stats["bytes"] += len(r.content)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code >= 500:
            time.sleep(2 * (attempt + 1))
            continue
        return r
    return r


def paginate(path, params, key, max_pages=None):
    """Descarga todas las páginas. Devuelve (rows, pages, bytes, seconds, truncated, last_status)."""
    rows, pages, nbytes = [], 0, 0
    t0 = time.time()
    token = None
    truncated = False
    status = None
    while True:
        p = dict(params)
        if token:
            p["page_token"] = token
        b0 = _stats["bytes"]
        r = get(path, p)
        status = r.status_code
        nbytes += _stats["bytes"] - b0
        pages += 1
        if r.status_code != 200:
            return rows, pages, nbytes, time.time() - t0, truncated, f"{r.status_code}: {r.text[:200]}"
        j = r.json()
        rows.extend(j.get(key) or [])
        token = j.get("next_page_token")
        if not token:
            break
        if max_pages and pages >= max_pages:
            truncated = True
            break
    return rows, pages, nbytes, time.time() - t0, truncated, status


def access():
    res = {}

    def probe(name, path, params):
        r = get(path, params)
        info = {"status": r.status_code}
        if r.status_code == 200:
            j = r.json()
            for k in ("bars", "trades", "quotes"):
                if k in j:
                    info["n"] = len(j[k] or [])
                    info["first"] = (j[k] or [None])[0]
                    info["has_next_page"] = bool(j.get("next_page_token"))
            info["ratelimit_limit"] = r.headers.get("X-RateLimit-Limit")
        else:
            info["error"] = r.text[:300]
        res[name] = info
        print(name, info.get("status"), info.get("n"), info.get("error", ""))

    win = {"start": "2026-11-13T15:00:00Z", "end": "2026-11-13T15:01:00Z", "limit": 5}
    for feed in ("sip", "iex"):
        probe(f"bars_1min_{feed}", "/v2/stocks/AAPL/bars",
              {"timeframe": "1Min", "start": "2026-11-13T14:30:00Z", "end": "2026-11-13T14:35:00Z",
               "feed": feed, "adjustment": "raw", "limit": 5})
        probe(f"trades_{feed}", "/v2/stocks/AAPL/trades", {**win, "feed": feed})
        probe(f"quotes_{feed}", "/v2/stocks/AAPL/quotes", {**win, "feed": feed})
    # profundidad histórica
    probe("bars_2016_sip", "/v2/stocks/AAPL/bars",
          {"timeframe": "1Min", "start": "2016-01-04T14:30:00Z", "end": "2016-01-04T14:35:00Z",
           "feed": "sip", "adjustment": "raw", "limit": 5})
    probe("trades_2016_sip", "/v2/stocks/AAPL/trades",
          {"start": "2016-01-04T15:00:00Z", "end": "2016-01-04T15:00:10Z", "feed": "sip", "limit": 5})
    probe("quotes_2016_sip", "/v2/stocks/AAPL/quotes",
          {"start": "2016-01-04T15:00:00Z", "end": "2016-01-04T15:00:01Z", "feed": "sip", "limit": 5})
    probe("bars_2015_sip", "/v2/stocks/AAPL/bars",
          {"timeframe": "1Day", "start": "2015-06-01", "end": "2015-06-10", "feed": "sip", "limit": 5})
    # supervivencia / cambios de ticker
    probe("delisted_TWTR_2021", "/v2/stocks/TWTR/bars",
          {"timeframe": "1Day", "start": "2021-06-01", "end": "2021-06-05", "feed": "sip", "limit": 5})
    probe("renamed_FB_2021", "/v2/stocks/FB/bars",
          {"timeframe": "1Day", "start": "2021-06-01", "end": "2021-06-05", "feed": "sip", "limit": 5})
    probe("renamed_META_2021", "/v2/stocks/META/bars",
          {"timeframe": "1Day", "start": "2021-06-01", "end": "2021-06-05", "feed": "sip", "limit": 5})
    # datos recientes (<15 min): hoy es domingo, solo comprobamos que el parámetro end recibe error si es futuro-ish
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    probe("trades_end_now_sip", "/v2/stocks/AAPL/trades",
          {"start": "2026-11-13T20:59:00Z", "end": now, "feed": "sip", "limit": 5})
    # metadatos
    for name, path in (("meta_exchanges", "/v2/stocks/meta/exchanges"),
                       ("meta_conditions_trade_A", "/v2/stocks/meta/conditions/trade"),
                       ("meta_conditions_quote_A", "/v2/stocks/meta/conditions/quote")):
        params = {"tape": "A"} if "conditions" in name else {}
        r = get(path, params)
        res[name] = {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text[:300]}
        print(name, r.status_code)
    return res


SAMPLE = ["AAPL", "NVDA", "SPY", "URI", "HIMS", "OSCR", "CRESY", "VFF"]
SESSION = ("2026-11-13T14:30:00Z", "2026-11-13T21:00:00Z")  # sesión regular (EST)
QUOTE_PAGE_CAP = 120  # tope por valor; si se alcanza, se extrapola por fracción de sesión cubierta


def _frac_covered(rows):
    if not rows:
        return 0.0
    s = pd.Timestamp(SESSION[0])
    e = pd.Timestamp(SESSION[1])
    last = pd.Timestamp(rows[-1]["t"])
    return max(0.0, min(1.0, (last - s) / (e - s)))


def _save(rows, kind, sym):
    if not rows or not str(DATA_DIR):
        return None
    d = DATA_DIR / "g0_probe" / kind
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for col in ("c",):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: ",".join(v) if isinstance(v, list) else v)
    f = d / f"{sym}_2026-11-13.parquet"
    df.to_parquet(f, compression="zstd", index=False)
    return f.stat().st_size


def volume():
    out = {}
    for sym in SAMPLE:
        rec = {}
        base = {"start": SESSION[0], "end": SESSION[1], "feed": "sip", "limit": 10000}
        rows, pages, nb, sec, trunc, st = paginate(f"/v2/stocks/{sym}/bars",
                                                   {**base, "timeframe": "1Min", "adjustment": "raw"}, "bars")
        rec["bars"] = {"rows": len(rows), "pages": pages, "json_bytes": nb, "seconds": round(sec, 1),
                       "parquet_bytes": _save(rows, "bars", sym), "status": st,
                       "volume_sum": sum(b["v"] for b in rows), "trade_count_sum": sum(b.get("n", 0) for b in rows)}
        print(sym, "bars", rec["bars"]["rows"], rec["bars"]["pages"])
        rows, pages, nb, sec, trunc, st = paginate(f"/v2/stocks/{sym}/trades", base, "trades")
        exch = pd.Series([t.get("x") for t in rows]).value_counts().to_dict() if rows else {}
        sizes = pd.Series([t.get("s") for t in rows]) if rows else pd.Series(dtype=float)
        rec["trades"] = {"rows": len(rows), "pages": pages, "json_bytes": nb, "seconds": round(sec, 1),
                         "parquet_bytes": _save(rows, "trades", sym), "status": st, "truncated": trunc,
                         "exchanges": exch,
                         "share_D": round(sum(sizes[pd.Series([t.get('x') for t in rows]) == 'D']) / sizes.sum(), 4)
                         if rows else None,
                         "median_size": float(sizes.median()) if rows else None,
                         "odd_lot_frac": round(float((sizes < 100).mean()), 4) if rows else None,
                         "fields": sorted(rows[0].keys()) if rows else []}
        print(sym, "trades", rec["trades"]["rows"], rec["trades"]["pages"], round(sec, 1))
        rows, pages, nb, sec, trunc, st = paginate(f"/v2/stocks/{sym}/quotes", base, "quotes",
                                                   max_pages=QUOTE_PAGE_CAP)
        frac = _frac_covered(rows) if trunc else 1.0
        pq = _save(rows, "quotes", sym)
        rec["quotes"] = {"rows_downloaded": len(rows), "pages": pages, "json_bytes": nb, "seconds": round(sec, 1),
                         "parquet_bytes": pq, "status": st, "truncated": trunc,
                         "session_fraction_covered": round(frac, 4),
                         "rows_est_full_session": int(len(rows) / frac) if frac > 0 else None,
                         "pages_est_full_session": round(pages / frac, 1) if frac > 0 else None,
                         "parquet_bytes_est_full_session": int(pq / frac) if (pq and frac > 0) else None,
                         "fields": sorted(rows[0].keys()) if rows else []}
        print(sym, "quotes", len(rows), pages, "frac", round(frac, 3))
        out[sym] = rec
    return out


def main():
    if not KEY or not SECRET:
        sys.exit("Faltan ALPACA_API_KEY / ALPACA_API_SECRET en .env")
    mode = sys.argv[1] if len(sys.argv) > 1 else "access"
    results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    t0 = time.time()
    if mode == "access":
        results["access"] = access()
    elif mode == "volume":
        results["volume_2026-11-13"] = volume()
    results[f"run_{mode}"] = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "requests": _stats["requests"], "bytes": _stats["bytes"],
                              "seconds": round(time.time() - t0, 1)}
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print("requests", _stats["requests"], "bytes", _stats["bytes"])


if __name__ == "__main__":
    main()
