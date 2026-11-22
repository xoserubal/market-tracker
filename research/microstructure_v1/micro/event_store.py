"""Registro de medidas, alertas y episodios intradía (privado, en MICRO_DATA_DIR/events/).

Tablas por día (parquet, una partición por fecha):
- measures/   TODAS las medidas de todos los valores escaneados, con o sin anomalía (el denominador). Formato largo.
- symbol_days/ contexto y calidad por valor y día: línea base, cobertura, unidades de datos, versiones.
- alerts/     anomalías individuales (una fila por medida y tramo que supera la referencia).
- episodes/   agrupación de alertas relacionadas del mismo valor y día.
- drilldowns/ resultados del desglose con trades/quotes (JSON por episodio o ventana manual).

Reescribir un día para los mismos (valor, pasada) sustituye esas filas: el escaneo es idempotente.
Los campos con estructura (listas, dicts) se guardan como JSON en texto.
"""
import json
from pathlib import Path

import pandas as pd

from . import storage

TABLES = ("measures", "symbol_days", "alerts", "episodes")


def root(version: str = None) -> Path:
    """events/ para cat-v0 (sin cambios) y events/<versión>/ para las demás (cat-v1): las versiones no se mezclan."""
    p = storage.root() / "events"
    if version and version != "cat-v0":
        p = p / version
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(table: str, day: str, version: str = None) -> Path:
    return root(version) / table / f"{day}.parquet"


def _jsonify(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if df[c].map(lambda v: isinstance(v, (dict, list, tuple))).any():
            df[c] = df[c].map(lambda v: json.dumps(v, default=str, ensure_ascii=False)
                              if isinstance(v, (dict, list, tuple)) else v)
    return df


def write_day(table: str, day: str, df: pd.DataFrame, *, replace: list = None, keys=("symbol", "pass"),
              version: str = None):
    """Sustituye las filas del día cuyas claves estén en `replace` (por defecto, las presentes en df) y conserva el
    resto. Hay que pasar `replace` con TODOS los valores escaneados: si uno se queda sin alertas, sus filas viejas
    también deben desaparecer."""
    p = _path(table, day, version)
    new = _jsonify(df)
    rep = set(map(tuple, replace)) if replace is not None else (
        set(map(tuple, new[list(keys)].drop_duplicates().itertuples(index=False))) if len(new) else set())
    if p.exists():
        old = pd.read_parquet(p)
        if rep and all(k in old.columns for k in keys):
            drop = [tuple(x) in rep for x in old[list(keys)].itertuples(index=False)]
            old = old[~pd.Series(drop, index=old.index)]
        new = pd.concat([old, new], ignore_index=True) if len(old) else new
    p.parent.mkdir(parents=True, exist_ok=True)
    storage.write_parquet_atomic(new, p)
    return p


def read(table: str, day: str = None, symbol: str = None, version: str = None) -> pd.DataFrame:
    d = root(version) / table
    files = [_path(table, day, version)] if day else sorted(d.glob("*.parquet")) if d.exists() else []
    frames = [pd.read_parquet(f) for f in files if f.exists()]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if symbol is not None and "symbol" in df.columns:
        df = df[df["symbol"] == symbol]
    return df


def days(table: str = "episodes", version: str = None) -> list:
    d = root(version) / table
    return sorted(f.stem for f in d.glob("*.parquet")) if d.exists() else []


def update_status(day: str, ids: list, status: str, note: str, *, table: str = "alerts", id_col: str = "episode_id",
                  version: str = None):
    p = _path(table, day, version)
    if not p.exists():
        return 0
    df = pd.read_parquet(p)
    m = df[id_col].isin(ids)
    df.loc[m, "status"] = status
    df.loc[m, "status_note"] = note
    storage.write_parquet_atomic(df, p)
    return int(m.sum())


def drilldown_path(key: str) -> Path:
    p = root() / "drilldowns" / f"{key}.json"      # los desgloses con trades son comunes a las versiones
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _maybe_json(v):
    if isinstance(v, str) and v and v[0] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def load_json(col):
    return col.map(_maybe_json)
