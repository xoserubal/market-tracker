"""
Estimacion del diferencial High Yield (BAMLH0A0HYM2) antes de que FRED lo publique.

Por que: FRED publica el OAS del HY con ~1 dia habil de retraso (el viernes llega
el lunes). Este script estima el valor de los dias que faltan a partir de los ETFs
de high yield y de Tesoro, y guarda cada estimacion para compararla con el dato
real cuando se publique. Es una ESTIMACION, nunca el dato oficial.

Modelo (elegido 2026-11-23 comparando 4 variantes fuera de muestra, ventana
movil de 250 sesiones, 3 anos de FRED):
    dOAS_t (pb) = a + b1*HJ_t + b2*IEI_t + b3*HJ_{t-1} + b4*IEI_{t-1}
    HJ  = media de los retornos log (%) de HYG y JNK (precio ajustado)
    IEI = retorno log (%) del ETF de Tesoro 3-7 anos (duracion parecida a la del HY)
El retorno del dia anterior entra porque los precios de ICE recogen el movimiento
de los ETFs con algo de retraso. Error medio fuera de muestra: ~2,7 pb a 1 dia,
~3,2 pb a 2 dias (2024-11 -> 2026-11). Los coeficientes se recalculan en cada
ejecucion con las 250 sesiones anteriores, sin mirar al futuro.

Limitaciones conocidas:
  - En estres el ETF puede cotizar con descuento sobre su valor liquidativo:
    la estimacion tiende a quedarse corta en saltos grandes (2026-11-20: +20 pb
    estimado frente a +24 pb real).
  - Precio de cierre del ETF (16:00 ET) frente a la hora de valoracion de ICE.

Salidas:
  docs/data/hy_spread_estimate_latest.json  ultimo dato oficial + estimaciones
      de los dias siguientes + coeficientes y precios de referencia (para que una
      pagina pueda calcular la estimacion con precios en vivo) + error historico.
  docs/data/hy_spread_estimate_log.jsonl    una fila por dia estimado; cuando
      FRED publica ese dia se rellenan actual_bp y error_bp (seguimiento real).

Uso:
  python scripts/hy_spread_estimate.py            # calcula, guarda y concilia
  python scripts/hy_spread_estimate.py --dry-run  # solo imprime
  python scripts/hy_spread_estimate.py --report   # resumen del seguimiento
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

DATA = ROOT / "docs" / "data"
LATEST_PATH = DATA / "hy_spread_estimate_latest.json"
LOG_PATH = DATA / "hy_spread_estimate_log.jsonl"

SERIES = "BAMLH0A0HYM2"
HY_TICKERS = ("HYG", "JNK")
TSY_TICKER = "IEI"
WINDOW = 250          # sesiones para recalcular los coeficientes
MODEL_ID = "hj_iei_lag_w250_v1"
BAND_Z = 1.2816       # banda del 80 % (normal) sobre el error historico
NY = "America/New_York"


# ---------------------------------------------------------------- datos

def fetch_fred(start: str) -> pd.Series:
    """OAS en puntos basicos, indexado por fecha. API con clave si hay; si no, CSV publico."""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": SERIES, "api_key": key, "file_type": "json",
                    "observation_start": start},
            timeout=30)
        r.raise_for_status()
        obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
        s = pd.Series({pd.Timestamp(o["date"]): float(o["value"]) for o in obs})
    else:
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                         params={"id": SERIES, "cosd": start}, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ["date", "v"]
        df = df[pd.to_numeric(df["v"], errors="coerce").notna()]
        s = pd.Series(df["v"].astype(float).values, index=pd.to_datetime(df["date"]))
    return (s.sort_index() * 100.0).rename("oas_bp")


def fetch_prices() -> pd.DataFrame:
    """Cierres ajustados (dividendos incluidos) por fecha de sesion de Nueva York."""
    import yfinance as yf
    tickers = list(HY_TICKERS) + [TSY_TICKER]
    raw = yf.download(tickers, period="3y", interval="1d", auto_adjust=True,
                      progress=False, threads=False, group_by="column")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[tickers].dropna(how="any")
    idx = pd.DatetimeIndex(close.index)
    if idx.tz is not None:
        idx = idx.tz_convert(NY).tz_localize(None)
    close.index = idx.normalize()
    return close[~close.index.duplicated(keep="last")]


def session_closed_today(now_utc: datetime) -> bool:
    from zoneinfo import ZoneInfo
    ny = now_utc.astimezone(ZoneInfo(NY))
    return ny.weekday() >= 5 or (ny.hour, ny.minute) >= (16, 15)


# ---------------------------------------------------------------- modelo

def build_features(px: pd.DataFrame) -> pd.DataFrame:
    """Retornos log en % entre sesiones consecutivas de los ETFs."""
    lr = np.log(px) * 100.0
    ret = lr.diff()
    f = pd.DataFrame(index=px.index)
    f["HJ"] = ret[list(HY_TICKERS)].mean(axis=1)
    f["IEI"] = ret[TSY_TICKER]
    f["HJ_l1"] = f["HJ"].shift(1)
    f["IEI_l1"] = f["IEI"].shift(1)
    return f


COLS = ["HJ", "IEI", "HJ_l1", "IEI_l1"]


def training_frame(oas: pd.Series, px: pd.DataFrame) -> pd.DataFrame:
    """Cambios del OAS entre fechas publicadas, frente a los retornos acumulados de
    los ETFs entre esas mismas fechas (asi un dia sin dato de FRED no descuadra)."""
    common = oas.index.intersection(px.index)
    sub = px.loc[common]
    f = build_features(sub)
    out = f.copy()
    out["d"] = oas.loc[common].diff()
    return out.dropna()


def fit(train: pd.DataFrame) -> np.ndarray:
    X = np.column_stack([np.ones(len(train))] + [train[c].values for c in COLS])
    return np.linalg.lstsq(X, train["d"].values, rcond=None)[0]


def predict(beta: np.ndarray, row) -> float:
    return float(beta[0] + sum(beta[i + 1] * float(row[c]) for i, c in enumerate(COLS)))


def backtest(df: pd.DataFrame) -> dict:
    """Error fuera de muestra: cada dia se estima con coeficientes de las 250 sesiones previas."""
    errs = []
    for i in range(WINDOW, len(df)):
        beta = fit(df.iloc[i - WINDOW:i])
        errs.append(predict(beta, df.iloc[i]) - df["d"].iloc[i])
    if not errs:
        return {}
    e1 = pd.Series(errs)
    e2 = e1.rolling(2).sum().dropna()

    def stats(e):
        return {"n": int(len(e)), "mae_bp": round(float(e.abs().mean()), 2),
                "bias_bp": round(float(e.mean()), 2),
                "rmse_bp": round(float(math.sqrt((e ** 2).mean())), 2),
                "p80_abs_bp": round(float(e.abs().quantile(0.8)), 1),
                "p90_abs_bp": round(float(e.abs().quantile(0.9)), 1),
                "max_abs_bp": round(float(e.abs().max()), 1)}
    return {"from": str(df.index[WINDOW].date()), "to": str(df.index[-1].date()),
            "bridge_1d": stats(e1), "bridge_2d": stats(e2)}


# ---------------------------------------------------------------- estimacion

def estimate(oas: pd.Series, px: pd.DataFrame, now_utc: datetime) -> dict:
    df = training_frame(oas, px)
    beta = fit(df.iloc[-WINDOW:])
    resid = df["d"].iloc[-WINDOW:].values - np.column_stack(
        [np.ones(WINDOW)] + [df[c].iloc[-WINDOW:].values for c in COLS]) @ beta
    sigma = float(np.std(resid, ddof=len(beta)))

    anchor_date = oas.index[-1]
    anchor_bp = float(oas.iloc[-1])

    today_ny = pd.Timestamp(now_utc).tz_convert(NY).tz_localize(None).normalize()
    closed = session_closed_today(now_utc)
    # Sesiones posteriores al ultimo dato oficial con cierre completo de los ETFs.
    sessions = [d for d in px.index if d > anchor_date and (d < today_ny or closed)]
    f = build_features(px)

    ests, level = [], anchor_bp
    for k, d in enumerate(sessions, start=1):
        level += predict(beta, f.loc[d])
        half = BAND_Z * sigma * math.sqrt(k)
        ests.append({"date": str(d.date()), "est_bp": round(level, 1),
                     "low_bp": round(level - half, 1), "high_bp": round(level + half, 1),
                     "bridge_days": k})

    if sessions:
        last_ref = sessions[-1]
    else:  # ultima sesion de los ETFs con fecha <= dato oficial
        last_ref = px.index[px.index <= anchor_date][-1]
    ref_prev = px.index[px.index.get_loc(last_ref) - 1]
    ref = {
        # Para estimar con precios en vivo: dia siguiente a ref_date,
        # HJ = media de ln(P_vivo/close)*100 de HYG y JNK; IEI igual; los
        # retornos "_l1" son los de ref_date que se dan aqui.
        "ref_date": str(last_ref.date()),
        "ref_level_bp": round(ests[-1]["est_bp"] if ests else anchor_bp, 1),
        "ref_bridge_days": len(sessions),
        "close": {t: round(float(px.loc[last_ref, t]), 4) for t in px.columns},
        "ret_ref_day": {"HJ": round(float(f.loc[last_ref, "HJ"]), 4),
                        "IEI": round(float(f.loc[last_ref, "IEI"]), 4)},
        "prev_close_date": str(ref_prev.date()),
    }
    return {
        "generated_at_utc": now_utc.isoformat(timespec="seconds"),
        "series": SERIES,
        "label": "ESTIMACION — no es el dato oficial de FRED",
        "official": {"date": str(anchor_date.date()), "value_bp": round(anchor_bp, 1)},
        "estimates": ests,
        "model": {"id": MODEL_ID, "window": WINDOW, "fitted_through": str(df.index[-1].date()),
                  "coef": {"const": round(float(beta[0]), 4),
                           **{c: round(float(beta[i + 1]), 4) for i, c in enumerate(COLS)}},
                  "resid_sigma_bp": round(sigma, 2), "band": "80%"},
        "live_reference": ref,
        "backtest": backtest(df),
    }


# ---------------------------------------------------------------- seguimiento

def load_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    rows = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def update_log(rows: list[dict], result: dict, oas: pd.Series) -> tuple[list[dict], int, int]:
    """Anade/actualiza la estimacion de cada dia aun no publicado y concilia con FRED.
    Clave: (target_date, anchor_date). Si el mismo par se vuelve a estimar antes de
    que FRED publique, se guarda la ultima version (datos de cierre mas completos);
    una fila ya conciliada no se toca."""
    by_key = {(r["target_date"], r["anchor_date"]): r for r in rows}
    added = 0
    for e in result["estimates"]:
        key = (e["date"], result["official"]["date"])
        r = by_key.get(key)
        if r and r.get("actual_bp") is not None:
            continue
        new = {"target_date": e["date"], "anchor_date": result["official"]["date"],
               "anchor_bp": result["official"]["value_bp"], "bridge_days": e["bridge_days"],
               "est_bp": e["est_bp"], "low_bp": e["low_bp"], "high_bp": e["high_bp"],
               "model": MODEL_ID, "made_at_utc": result["generated_at_utc"],
               "actual_bp": None, "error_bp": None, "in_band": None, "reconciled_at_utc": None}
        if r is None:
            added += 1
        by_key[key] = new
    reconciled = 0
    oas_by_date = {str(d.date()): float(v) for d, v in oas.items()}
    for r in by_key.values():
        if r.get("actual_bp") is None and r["target_date"] in oas_by_date:
            a = oas_by_date[r["target_date"]]
            r["actual_bp"] = round(a, 1)
            r["error_bp"] = round(r["est_bp"] - a, 1)
            r["in_band"] = bool(r["low_bp"] <= a <= r["high_bp"])
            r["reconciled_at_utc"] = result["generated_at_utc"]
            reconciled += 1
    out = sorted(by_key.values(), key=lambda r: (r["target_date"], r["anchor_date"]))
    return out, added, reconciled


def tracking_stats(rows: list[dict]) -> dict:
    done = [r for r in rows if r.get("error_bp") is not None]
    if not done:
        return {"n": 0}
    e = np.array([r["error_bp"] for r in done])
    res = {"n": int(len(e)), "mae_bp": round(float(np.abs(e).mean()), 2),
           "bias_bp": round(float(e.mean()), 2),
           "within_5bp_pct": round(float((np.abs(e) <= 5).mean() * 100), 0),
           "in_band_pct": round(float(np.mean([r["in_band"] for r in done]) * 100), 0),
           "max_abs_bp": round(float(np.abs(e).max()), 1),
           "pending": int(sum(1 for r in rows if r.get("error_bp") is None))}
    by_bridge = {}
    for k in sorted({r["bridge_days"] for r in done}):
        ek = np.array([r["error_bp"] for r in done if r["bridge_days"] == k])
        by_bridge[str(k)] = {"n": int(len(ek)), "mae_bp": round(float(np.abs(ek).mean()), 2)}
    res["by_bridge_days"] = by_bridge
    return res


def write_log(rows: list[dict]) -> None:
    LOG_PATH.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                        encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        print(json.dumps(tracking_stats(load_log()), ensure_ascii=False, indent=2))
        return 0

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=3 * 365 + 30)).strftime("%Y-%m-%d")
    oas = fetch_fred(start)
    px = fetch_prices()
    if len(oas) < WINDOW + 20 or len(px) < WINDOW + 20:
        print(f"Datos insuficientes: FRED {len(oas)}, ETFs {len(px)}", file=sys.stderr)
        return 1

    result = estimate(oas, px, now)
    rows, added, reconciled = update_log(load_log(), result, oas)
    result["tracking"] = tracking_stats(rows)

    off = result["official"]
    print(f"Oficial FRED {off['date']}: {off['value_bp']} pb")
    for e in result["estimates"]:
        print(f"  Estimado {e['date']} (+{e['bridge_days']}d): {e['est_bp']} pb "
              f"[{e['low_bp']}-{e['high_bp']}]")
    if not result["estimates"]:
        print("  Sin sesiones pendientes de publicar.")
    bt = result["backtest"].get("bridge_1d", {})
    print(f"Error historico a 1 dia: MAE {bt.get('mae_bp')} pb, p90 {bt.get('p90_abs_bp')} pb "
          f"(n={bt.get('n')})")
    print(f"Seguimiento real: {result['tracking']}  | nuevas {added}, conciliadas {reconciled}")

    if args.dry_run:
        return 0
    DATA.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    write_log(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
