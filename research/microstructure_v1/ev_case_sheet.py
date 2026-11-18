"""Eventos intradía — ficha de un episodio (prototipo de E0, exploratorio).

SUSTITUIDO en E1 por micro/sessions.py + ev_drilldown.py. Se conserva para reproducir la ficha manual de PLTR; ojo:
su «volumen continuo» incluye comunicaciones tardías y condiciones no estándar, y la cuota de subasta que daba la ficha
manual (18 %) era la barra mixta de las 16:00 (ver la corrección en EVENTOS_FICHA_PLTR_2026-11-17.md).

Uso:  py -3 ev_case_sheet.py SYMBOL YYYY-MM-DD [--baseline 60]

Requiere, ya descargados con micro/download (manifiesto):
  - barras de 1 minuto (unidades mensuales) que cubran el día y las `baseline` sesiones previas;
  - trades del día (cualquier ventana) y, si se quiere el desequilibrio por agresor, quotes del tramo final.

Separa la sesión en tramos que no deben mezclarse: negociación continua, subasta de apertura, subasta de cierre,
comunicaciones tardías a precio de referencia (TRF con condición P / W) y negociación fuera de horario.
Normaliza cada medida frente a las sesiones PREVIAS del propio valor (nunca incluye el día del episodio).
Describe; no interpreta intención (nada de «compra institucional» o «acumulación»).

Salida: MICRO_DATA_DIR/results/ev_case_<SYMBOL>_<DAY>.json (privado: deriva de datos con licencia personal).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import aggressor, calendar, config, episode, storage  # noqa: E402
from micro.library import TEST_END, TEST_START, EMBARGO_START  # noqa: E402
from micro.manifest import Manifest  # noqa: E402

NY = "America/New_York"


def load_bars(symbol: str) -> pd.DataFrame:
    rows = Manifest().rows("kind='bars' AND symbol=? AND status='ok'", (symbol,))
    if not rows:
        raise SystemExit(f"sin barras de 1 minuto descargadas para {symbol}")
    b = pd.concat([pd.read_parquet(r["path"]) for r in rows], ignore_index=True)
    b["t"] = pd.to_datetime(b["t"], utc=True)
    b = b.drop_duplicates("t").sort_values("t").reset_index(drop=True)
    ny = b["t"].dt.tz_convert(NY)
    b["d"], b["hm"] = ny.dt.strftime("%Y-%m-%d"), ny.dt.strftime("%H:%M")
    return b, [r["unit_key"] for r in rows]


def session_features(g: pd.DataFrame) -> dict:
    """Medidas de un día a partir de sus barras de 1 minuto (sesión regular 09:30-16:00 + after hours)."""
    g = g.set_index("hm")
    reg = g[(g.index >= "09:30") & (g.index < "16:00")]
    if len(reg) < 380:
        return None

    def close_at(h):
        return float(g.loc[h, "c"]) if h in g.index else np.nan

    last = close_at("15:59")
    r1 = np.log(reg["c"]).diff().dropna()
    tail10 = reg[reg.index >= "15:50"]
    post = g[(g.index >= "16:01") & (g.index < "16:35")]
    return {
        "ret_last5": last / close_at("15:54") - 1, "ret_last10": last / close_at("15:49") - 1,
        "ret_last30": last / close_at("15:29") - 1,
        "rebound_from_low_last10": last / tail10["l"].min() - 1,
        "ret_last10_in_sd": (last / close_at("15:49") - 1) / (r1.std() * np.sqrt(10)),
        "vol_last10_share": tail10["v"].sum() / reg["v"].sum(),
        "vol_1559_vs_median_minute": float(g.loc["15:59", "v"]) / reg["v"].median() if "15:59" in g.index else np.nan,
        # proxy de la subasta: la barra de las 16:00 contiene la subasta y el primer minuto de after hours
        "bar1600_vol_share": float(g.loc["16:00", "v"]) / reg["v"].sum() if "16:00" in g.index else np.nan,
        "post_ret_to_1630": close_at("16:30") / last - 1 if "16:30" in g.index else np.nan,
        "post_max_ret_1601_1635": post["h"].max() / last - 1 if len(post) else np.nan,
        # ojo: el volumen de las barras incluye comunicaciones tardías a precio de referencia (condición P)
        "post_vol_1601_1635": float(post["v"].sum()),
        "day_ret_open_to_last": last / float(reg["o"].iloc[0]) - 1,
    }


def pct_rank(hist: pd.Series, v: float) -> dict:
    s = hist.dropna()
    if not len(s) or pd.isna(v):
        return {"n": int(len(s)), "value": None if pd.isna(v) else float(v)}
    mad = (s - s.median()).abs().median() * 1.4826
    return {"value": float(v), "n": int(len(s)), "pct_below": round(float((s < v).mean() * 100), 1),
            "median": float(s.median()), "p10": float(s.quantile(.1)), "p90": float(s.quantile(.9)),
            "min": float(s.min()), "max": float(s.max()),
            "robust_z": round(float((v - s.median()) / mad), 2) if mad > 0 else None}


def segments(tr: pd.DataFrame, day: str) -> dict:
    """Desglose del volumen por tramos que no deben mezclarse."""
    o, c = calendar.session_bounds(day, "regular")
    live = tr[~tr["canceled"]]
    cond = live["conditions"].astype(str)
    auction_open = live[cond.str.contains(r"(?:^|\|)O(?:\||$)")]
    auction_close = live[cond.str.contains(r"(?:^|\|)6(?:\||$)")]
    official = live[cond.str.contains(r"(?:^|\|)M(?:\||$)")]
    late_ref = live[(live["t"] >= c) & live["trf"] & cond.str.contains(r"(?:^|\|)[PW](?:\||$)")]
    cont = live[(live["session"] == "regular") & ~live["auction"] & live["upd_vol"]]
    post = live[(live["session"] == "post") & ~live["auction"] & ~live["nonstandard"]]
    last_cont = cont[cont["upd_oc"] != "N"].sort_values("t").iloc[-1] if len(cont) else None
    return {
        "continuous_regular": {"shares": int(cont["size"].sum()), "trades": int(len(cont)),
                               "trf_share": round(float(cont.loc[cont["trf"], "size"].sum() / cont["size"].sum()), 3),
                               "last_trade_price": float(last_cont["price"]) if last_cont is not None else None,
                               "last_trade_utc": str(last_cont["t"]) if last_cont is not None else None},
        "opening_auction": {"shares": int(auction_open["size"].sum()),
                            "price": float(auction_open["price"].iloc[0]) if len(auction_open) else None},
        "closing_auction": {"shares": int(auction_close["size"].sum()),
                            "price": float(auction_close["price"].iloc[0]) if len(auction_close) else None,
                            "exchange": str(auction_close["exchange"].iloc[0]) if len(auction_close) else None,
                            "utc": str(auction_close["t"].iloc[0]) if len(auction_close) else None},
        "official_close_prints_M": {"n": int(len(official)), "note": "informativos: no suman volumen"},
        "late_reported_reference_price": {
            "shares": int(late_ref["size"].sum()), "prints": int(len(late_ref)),
            "prices": sorted({round(float(p), 4) for p in late_ref["price"]})[:5],
            "largest": int(late_ref["size"].max()) if len(late_ref) else 0,
            "note": "TRF comunicados tras el cierre con condición P (precio de referencia anterior) o W (precio medio): "
                    "no son negociación de after hours a ese instante"},
        "post_market": {"shares": int(post["size"].sum()), "trades": int(len(post)),
                        "odd_lot_trade_share": round(float(post["odd_lot"].mean()), 3) if len(post) else None,
                        "median_trade_size": float(post["size"].median()) if len(post) else None},
    }


def post_path(tr: pd.DataFrame, day: str, minutes=("16:00", "16:20", "16:27", "16:31", "16:40", "17:00")) -> list:
    po = tr[(tr["session"] == "post") & ~tr["auction"] & ~tr["nonstandard"] & ~tr["canceled"]].sort_values("t")
    out = []
    for a, b in zip(minutes[:-1], minutes[1:]):
        lo, hi = calendar.ny_range(day, a, b)
        w = po[(po["t"] >= lo) & (po["t"] < hi)]
        if len(w):
            out.append({"window": f"{a}-{b}", "shares": int(w["size"].sum()), "trades": int(len(w)),
                        "first": float(w["price"].iloc[0]), "last": float(w["price"].iloc[-1]),
                        # máximo/mínimo con las reglas de barras (un odd lot comunicado no los actualiza)
                        "low": float(w.loc[w["upd_hl"], "price"].min()), "high": float(w.loc[w["upd_hl"], "price"].max()),
                        "odd_lot_trade_share": round(float(w["odd_lot"].mean()), 3),
                        "trf_share": round(float(w.loc[w["trf"], "size"].sum() / w["size"].sum()), 3)})
    return out


def aggressor_windows(tr, q, qcov, day, windows=(("15:30", "15:50"), ("15:50", "16:00"))) -> list:
    if q is None or not len(q):
        return []
    c = aggressor.classify(tr, q, qcov)
    out = []
    for a, b in windows:
        lo, hi = calendar.ny_range(day, a, b)
        w = c[(c["t"] >= lo) & (c["t"] < hi) & (c["session"] == "regular")]
        tot = float(w["size"].sum())
        rec = {"window": f"{a}-{b}", "shares": int(tot)}
        for m in ("side_tick", "side_lr", "side_emo", "side_bidask"):
            buy, sell = w.loc[w[m] == 1, "size"].sum(), w.loc[w[m] == -1, "size"].sum()
            rec[m] = {"delta_shares": int(buy - sell), "delta_pct_vol": round((buy - sell) / tot * 100, 1),
                      "unclassified_pct": round((tot - buy - sell) / tot * 100, 1)}
        wq = q[(q["t"] >= lo) & (q["t"] < hi) & (q["ask"] > q["bid"]) & (q["bid"] > 0)]
        sp = (wq["ask"] - wq["bid"]) / ((wq["ask"] + wq["bid"]) / 2) * 1e4
        rec["spread_bps_median"] = round(float(sp.median()), 2) if len(sp) else None
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("day")
    ap.add_argument("--baseline", type=int, default=60)
    ap.add_argument("--max-age-days", type=int, default=180, help="antigüedad máxima de la línea base (días naturales)")
    ap.add_argument("--allow-test-period", action="store_true",
                    help="permite fechas del periodo de prueba de G2A en la línea base (por defecto se excluyen)")
    a = ap.parse_args()
    sym, day = a.symbol.upper(), a.day

    bars, bar_units = load_bars(sym)
    prior = [d for d in calendar.trading_days("2015-12-01", day) if d < day]
    if not a.allow_test_period:     # periodo de prueba de G2A con su embargo: fuera de la línea base
        prior = [d for d in prior if not (EMBARGO_START <= d <= TEST_END)]
    oldest = (pd.Timestamp(day) - pd.Timedelta(days=a.max_age_days)).strftime("%Y-%m-%d")
    prior = [d for d in prior if d >= oldest]               # una referencia de hace años no describe al valor hoy
    wanted = set(prior[-(a.baseline + 10):]) | {day}       # solo se calcula lo que se va a usar
    feats = {d: f for d, g in bars[bars["d"].isin(wanted)].groupby("d") if (f := session_features(g)) is not None}
    h = pd.DataFrame(feats).T.sort_index()
    if day not in h.index:
        raise SystemExit(f"{day} sin barras completas de sesión regular")
    hist = h.loc[h.index < day].tail(a.baseline)   # estrictamente anteriores
    months = {d[:7] for d in list(hist.index) + [day]}
    bar_units = [u for u in bar_units if u.split("|")[4] in months]
    norm = {k: pct_rank(hist[k], h.loc[day, k]) for k in h.columns}

    tr, tcov = episode.load_trades(sym, day)
    q, qcov = episode.load_quotes(sym, day)
    reg = tr[(tr["session"] == "regular") & tr["upd_hl"] & ~tr["canceled"]]
    hi_i, lo_i = reg["price"].idxmax(), reg["price"].idxmin()

    out = {
        "symbol": sym, "day": day, "code_version": config.code_version(), "detector_version": "case-sheet-0.1",
        "baseline": {"sessions": int(len(hist)), "from": hist.index[0], "to": hist.index[-1],
                     "rule": f"sesiones estrictamente anteriores al día del episodio, de los últimos {a.max_age_days} días naturales"
                             + ("" if a.allow_test_period else f"; excluido el periodo de prueba de G2A ({EMBARGO_START} a {TEST_END})")},
        "data_units": {"bars": bar_units,
                       "trades_coverage_utc": [[str(x), str(y)] for x, y in tcov],
                       "quotes_coverage_utc": [[str(x), str(y)] for x, y in qcov]},
        "day_context": {"regular_high": float(reg.loc[hi_i, "price"]), "regular_high_utc": str(reg.loc[hi_i, "t"]),
                        "regular_low": float(reg.loc[lo_i, "price"]), "regular_low_utc": str(reg.loc[lo_i, "t"])},
        "segments": segments(tr, day),
        "post_market_path": post_path(tr, day),
        "aggressor_close_windows": aggressor_windows(tr, q, qcov, day),
        "normalized_vs_own_history": norm,
        "lab": {"url": "http://127.0.0.1:8765/", "fields": {"symbol": sym, "day": day, "start": "15:30",
                                                             "end": "16:40", "tf": 1, "session": "extended"}},
    }
    dest = storage.root() / "results" / f"ev_case_{sym}_{day}.json"
    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
