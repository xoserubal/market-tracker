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
