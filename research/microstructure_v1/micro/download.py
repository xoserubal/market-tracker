"""Descarga idempotente y reanudable por unidades.

Unidad = (proveedor, tipo, símbolo, asof, periodo, configuración):
  trades / quotes -> un día de sesión (periodo 'YYYY-MM-DD', ventana de la sesión pedida);
  bars 1 min      -> un mes (periodo 'YYYY-MM', ventana del mes completo: incluye horario extendido, sin pérdida).

Flujo: ¿hecha y con checksum correcto? -> saltar. Si no: parada segura de disco -> descargar todas las páginas
en memoria -> validar -> escribir Parquet atómico -> manifiesto 'ok' (o 'empty'/'failed').
Un fallo a mitad no deja fichero parcial; reintentar la unidad la descarga completa de nuevo.
Los JSON del API nunca se escriben a disco (solo el Parquet sin pérdida).
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

NY_TZ = "America/New_York"

from . import calendar, config, normalize, quality, storage
from .manifest import Manifest
from .providers.base import FetchStats, ProviderError, clean_asof

EST_BYTES_PER_ROW = {"trades": 11, "quotes": 9, "bars": 40}


def config_for(kind: str, *, feed="sip", session="regular", timeframe="1Min", bars_window="month",
               time_range: str = None, cap: str = None) -> dict:
    """bars_window: 'month' (histórico: mes natural completo) o 'day' (captura diaria: sesión 04:00-20:00 NY).

    time_range (trades/quotes): 'HH:MM-HH:MM' en hora de Nueva York, recorta la ventana del día (episodios).
    cap (barras por mes): instante UTC ISO que limita el final del mes (mes en curso: solo sesiones cerradas).
    Ambos entran en el hash de configuración: una ventana distinta es una unidad distinta.
    """
    c = {"kind": kind, "feed": feed, "adjustment": "raw"}
    if kind == "bars":
        c.update({"timeframe": timeframe, "window": "calendar_month" if bars_window == "month" else "session_full"})
        if cap:
            c["cap"] = cap
    else:
        c.update({"session": session})
        if time_range:
            c["range"] = time_range
    return c


def config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:10]


def unit_key(provider: str, kind: str, symbol: str, asof, period: str, cfg: dict) -> str:
    return f"{provider}|{kind}|{symbol}|{asof or '-'}|{period}|{config_hash(cfg)}"


def _window(kind: str, period: str, cfg: dict):
    if kind == "bars" and cfg.get("window") == "session_full":
        s, e = calendar.session_bounds(period, "full")
        if cfg.get("cap"):
            e = min(e, pd.Timestamp(cfg["cap"]))
        latest = pd.Timestamp(datetime.now(timezone.utc) - timedelta(minutes=16))
        if e > latest:
            # una unidad sin tope que aún no ha terminado quedaría registrada como completa: se exige el tope
            raise ValueError(f"sesión {period} sin cerrar (fin {e}); pasa un 'cap' explícito")
        return s, e
    if kind == "bars":
        start = pd.Timestamp(period + "-01", tz="UTC")
        end = start + pd.offsets.MonthBegin(1)
        latest = pd.Timestamp(datetime.now(timezone.utc) - timedelta(minutes=16))   # plan Basic: nada de los últimos 15 min
        if cfg.get("cap"):
            latest = min(latest, pd.Timestamp(cfg["cap"]))
        elif end > latest:
            # mismo fallo latente que la sesión sin tope (E2 §7): un mes sin terminar se recortaría en silencio y quedaría
            # registrado como completo; con su clave (sin tope) no se volvería a descargar nunca
            raise ValueError(f"mes {period} sin terminar (fin {end}); pasa un 'cap' explícito")
        return start, min(end, latest)
    if cfg.get("range"):
        a, b = cfg["range"].split("-")
        return calendar.ny_range(period, a, b)
    return calendar.session_bounds(period, cfg["session"])


def download_unit(provider, kind: str, symbol: str, period: str, *, asof=None, cfg=None, manifest: Manifest = None,
                  force=False, expected_rows: int = None, verify_checksum=True) -> dict:
    cfg = cfg or config_for(kind)
    asof = clean_asof(asof)
    manifest = manifest or Manifest()
    key = unit_key(provider.name, kind, symbol, asof, period, cfg)
    if not force and manifest.is_done(key, verify_checksum=verify_checksum):
        return {"unit_key": key, "status": "skipped"}
    daily_unit = kind != "bars" or cfg.get("window") == "session_full"
    if daily_unit and not calendar.is_trading_day(period):
        return {"unit_key": key, "status": "not_trading_day"}
    storage.disk_guard((expected_rows or 0) * EST_BYTES_PER_ROW[kind] * 2)
    meta = {"provider": provider.name, "kind": kind, "symbol": symbol, "asof": asof or "-", "period": period,
            "config_hash": config_hash(cfg), "config": cfg, "code_version": config.code_version()}
    start, end = _window(kind, period, cfg)        # antes de abrir la unidad: un error aquí no deja nada "en curso"
    manifest.start(key, meta)
    stats = FetchStats()
    try:
        frames = []
        for page in provider.fetch_pages(kind, symbol, calendar.iso(start), calendar.iso(end), asof=asof,
                                         timeframe=cfg.get("timeframe", "1Min"), stats=stats):
            if page:
                frames.append(normalize.records_to_frame(kind, page))
        raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        common = dict(rows=int(len(raw)), pages=stats.pages, requests=stats.requests, bytes_api=stats.bytes,
                      seconds=round(stats.seconds, 2), retries=stats.retries)
        if raw.empty:
            q = {"grade": "F" if kind != "bars" else "C", "issues": [{"check": "empty", "severity": "fatal"}]}
            manifest.finish(key, "empty", quality_grade=q["grade"], quality_json=q, **common)
            return {"unit_key": key, "status": "empty", **common}
        q = assess(kind, raw, period, (start, end))
        path = storage.raw_path(provider.name, kind, symbol, asof, period, config_hash(cfg))
        digest, size = storage.write_parquet_atomic(raw, path)
        manifest.finish(key, "ok", path=str(path), sha256=digest, file_bytes=size, quality_grade=q["grade"],
                        quality_json=q, **common)
        return {"unit_key": key, "status": "ok", "path": str(path), "file_bytes": size, "grade": q["grade"], **common}
    except (ProviderError, storage.DiskGuardError, Exception) as e:   # noqa: B014 - se registra cualquier fallo
        manifest.finish(key, "failed", error=f"{type(e).__name__}: {e}", pages=stats.pages, requests=stats.requests,
                        bytes_api=stats.bytes, seconds=round(stats.seconds, 2), retries=stats.retries)
        raise


def download_bars_multi_day(provider, symbols: list, day: str, *, manifest: Manifest = None, batch: int = 100,
                            batch_retries: int = 1, log=None) -> dict:
    """Barras de 1 minuto de UN día de sesión completa (04:00-20:00 NY) para muchos valores con la petición múltiple
    (/v2/stocks/bars?symbols=...). Registro diario E3.

    Cada valor queda como una unidad diaria propia, con la MISMA clave que download_unit(..., bars_window='day'): el
    escaneo, el laboratorio y la cobertura la leen igual que si se hubiera bajado sola.
    - Idempotente: las unidades ya hechas (con checksum correcto) se saltan.
    - Un lote que falla tras los reintentos de página se reintenta entero `batch_retries` veces; si sigue fallando se
      parte en dos, hasta llegar a peticiones individuales (download_unit). Nada se da por bueno a medias.
    - Un valor sin barras ese día queda 'empty' (no se reintenta en cada pasada).
    - Interrupción: una unidad a medias queda 'running' en el manifiesto y sin fichero; la siguiente pasada la rehace.
    Devuelve estadísticas reales: peticiones, páginas, bytes, segundos, lotes, reintentos y divisiones."""
    m = manifest or Manifest()
    cfg = config_for("bars", bars_window="day")
    if not calendar.is_trading_day(day):
        return {"day": day, "status": "not_trading_day"}
    start, end = _window("bars", day, cfg)
    keys = {s: unit_key(provider.name, "bars", s, None, day, cfg) for s in symbols}
    todo = [s for s in symbols if not m.is_done(keys[s], verify_checksum=False)]
    res = {"day": day, "symbols": len(symbols), "already_done": len(symbols) - len(todo), "ok": 0, "empty": 0,
           "failed": [], "requests": 0, "pages": 0, "bytes_api": 0, "seconds_api": 0.0, "retries": 0, "batches": 0,
           "batch_retries": 0, "splits": 0, "fallback_single": 0}

    def write(sym, rows, batch_id, pending):
        """Escribe el fichero de la unidad (atómico) y deja su registro pendiente para la transacción del lote."""
        key = keys[sym]
        meta = {"provider": provider.name, "kind": "bars", "symbol": sym, "asof": "-", "period": day,
                "config_hash": config_hash(cfg), "config": cfg, "code_version": config.code_version()}
        if not rows:
            q = {"grade": "C", "issues": [{"check": "empty", "severity": "fatal"}], "source": f"multi:{batch_id}"}
            pending.append((key, meta, "empty", dict(quality_grade="C", quality_json=q, rows=0, pages=0, requests=0,
                                                     bytes_api=0)))
            return
        raw = normalize.records_to_frame("bars", rows)
        q = assess("bars", raw, day, (start, end))
        q["source"] = f"multi:{batch_id}"
        path = storage.raw_path(provider.name, "bars", sym, None, day, config_hash(cfg))
        digest, size = storage.write_parquet_atomic(raw, path)
        # las peticiones del lote se contabilizan en el lote (res), no en cada unidad
        pending.append((key, meta, "ok", dict(path=str(path), sha256=digest, file_bytes=size, quality_grade=q["grade"],
                                               quality_json=q, rows=int(len(raw)), pages=0, requests=0, bytes_api=0)))

    def run(group, depth=0):
        bid = f"{day}|{group[0]}|{len(group)}|{depth}"
        for attempt in range(batch_retries + 1):
            st = FetchStats()
            try:
                out = provider.fetch_bars_multi(group, calendar.iso(start), calendar.iso(end), stats=st)
                res["batches"] += 1
                for k_ in ("requests", "pages", "retries"):
                    res[k_] += getattr(st, k_)
                res["bytes_api"] += st.bytes
                res["seconds_api"] += st.seconds
                # escritura en paralelo (cada fichero es atómico con fsync; en este disco es lo que más tarda)
                from concurrent.futures import ThreadPoolExecutor
                parts = [[] for _ in group]
                with ThreadPoolExecutor(max_workers=8) as ex:
                    list(ex.map(lambda i: write(group[i], out.get(group[i]) or [], bid, parts[i]), range(len(group))))
                pending = [x for part in parts for x in part]
                m.record_done_many(pending)
                for _, _, stt, _ in pending:
                    res[stt] += 1
                if log:
                    log(f"  lote {bid}: {sum(len(out.get(s) or []) for s in group)} barras, {st.requests} peticiones")
                return
            except ProviderError as e:
                res["requests"] += st.requests
                res["batch_retries"] += 1
                if log:
                    log(f"  lote {bid}: fallo ({e}); intento {attempt + 1}")
        if len(group) == 1:
            res["fallback_single"] += 1
            try:
                r = download_unit(provider, "bars", group[0], day, cfg=cfg, manifest=m)
                res["requests"] += int(r.get("requests") or 0)
                res["ok" if r["status"] == "ok" else "empty"] += 1
            except Exception as e:  # noqa: BLE001
                res["failed"].append({"symbol": group[0], "error": f"{type(e).__name__}: {e}"})
            return
        res["splits"] += 1
        h = len(group) // 2
        run(group[:h], depth + 1)
        run(group[h:], depth + 1)

    for i in range(0, len(todo), batch):
        run(todo[i:i + batch])
    res["seconds_api"] = round(res["seconds_api"], 1)
    return res


def assess(kind: str, raw: pd.DataFrame, period: str, window: tuple) -> dict:
    """Calidad intrínseca de la unidad (sin comparar con otras fuentes)."""
    if kind == "trades":
        return quality.check_trades(normalize.trades(raw, period), period, window)
    if kind == "quotes":
        return quality.check_quotes(normalize.quotes(raw, period))
    br = normalize.bars(raw)
    days = [period] if len(period) == 10 else calendar.trading_days(period + "-01", period + "-31")
    last_day = window[1].tz_convert(NY_TZ).strftime("%Y-%m-%d")
    days = [d for d in days if d < last_day or (d == last_day and window[1] >= calendar.session_bounds(d, "regular")[1])]
    with_reg = set(br.loc[br["session"] == "regular", "day"])
    zero_v = int((br["volume"] == 0).sum())
    issues = []
    if zero_v:
        issues.append({"check": "zero_volume_bars", "severity": "major", "detail": zero_v})
    missing = [d for d in days if d not in with_reg]
    if missing:
        issues.append({"check": "trading_days_without_regular_bars", "severity": "minor", "detail": missing[:30]})
    return {"grade": quality.grade(issues), "issues": issues, "rows": int(len(br)),
            "sessions": br["session"].value_counts().to_dict(), "trading_days": len(days),
            "days_with_regular_bars": len(with_reg)}
