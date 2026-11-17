"""G1.5 — estudio de los episodios NVDA (2026-11-12) y GOOGL (2026-10-29, contraste). Exploratorio: no es validación.

Para cada episodio:
- subasta de apertura (precio, volumen) y primera hora;
- footprint de la vela 09:30-10:30 con los cuatro métodos, y sensibilidad (sin TRF, sin odd lots, quote simultánea);
- secuencia de 5 minutos en 09:30-12:00: precio, compra, venta, delta, delta acumulado, nivel con más venta/compra;
- niveles con mayor venta y mayor compra agresiva de la primera hora;
- recorrido posterior (cierre del día, máximo y mínimo).
Salida: results/g15_case_study.json (privado; el informe solo cita agregados).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import aggressor, calendar, episode, footprint, storage  # noqa: E402

CASES = [("NVDA", "2026-11-12", 0.25), ("GOOGL", "2026-10-29", 0.25)]


def ny(day, hhmm):
    return calendar.ny_range(day, hhmm, "23:59")[0]


def top_levels(fp, bar_t, key, k=5):
    ls = [l for l in fp["levels"] if l["t"] == bar_t]
    return [{"p": l["p"], key: l[key], "buy": l["buy"], "sell": l["sell"], "vol": l["vol"]}
            for l in sorted(ls, key=lambda x: -x[key])[:k]]


def study(sym, day, step):
    tr, tcov = episode.load_trades(sym, day)
    q, qcov = episode.load_quotes(sym, day)
    out = {"symbol": sym, "day": day, "trades": int(len(tr)), "quotes": int(len(q)), "step": step,
           "trade_coverage": [[str(a), str(b)] for a, b in tcov], "quote_coverage": [[str(a), str(b)] for a, b in qcov],
           "sizes": episode.sizes(sym, day)}
    o930 = ny(day, "09:30")
    reg = tr[(tr["session"] == "regular") & ~tr["canceled"]]
    au = reg[reg["auction"] & reg["upd_vol"]]
    first_au = au[au["t"] < o930 + pd.Timedelta(minutes=5)]
    out["opening_auction"] = {"volume": int(first_au["size"].sum()), "prints": int(len(first_au)),
                              "prices": sorted(set(np.round(first_au["price"], 3).tolist()))[:10],
                              "conditions": first_au["conditions"].astype(str).value_counts().head(5).to_dict()}
    prev = tr[(tr["session"] == "pre") & ~tr["canceled"]]
    out["premarket"] = {"volume": int(prev["size"].sum()), "low": float(prev["price"].min()) if len(prev) else None,
                        "last": float(prev["price"].iloc[-1]) if len(prev) else None}
    # Reglas oficiales de barras: máximo/mínimo solo con trades que actualizan high/low, apertura/cierre con los que
    # actualizan open/close. Usar todos los trades metía comunicaciones tardías (GOOGL 2026-10-29: "máximo" 323,94
    # con la barra diaria en 288,33; corregido 2026-11-15).
    hl = reg[reg["upd_hl"]]
    oc = reg[reg["upd_oc"] != "N"]
    out["day_path"] = {"open_first_trade": float(oc["price"].iloc[0]), "low": float(hl["price"].min()),
                       "low_time": str(hl.loc[hl["price"].idxmin(), "t"]), "high": float(hl["price"].max()),
                       "high_time": str(hl.loc[hl["price"].idxmax(), "t"]),
                       "close_last_trade": float(oc["price"].iloc[-1]),
                       "rule": "upd_hl / upd_oc (reglas oficiales de barras)"}
    variants = {
        "base": {}, "simultaneous_quote": {"strict_before": False}, "quote_lag_1s": {"quote_lag_ms": 1000},
        "ref_without_trf": {"ref_exclude_trf": True},
    }
    first_h = (o930, o930 + pd.Timedelta(hours=1))
    out["first_hour"] = {}
    base_c = None
    for vname, opts in variants.items():
        c = aggressor.classify(tr, q if len(q) else None, qcov, **opts)
        if vname == "base":
            base_c = c
        for method in aggressor.METHODS:
            for filt in ([{}, {"exclude_trf": True}, {"exclude_odd": True}] if vname == "base" else [{}]):
                fp = footprint.build(c, day, method=method, tf_minutes=60, step=step, start=first_h[0], end=first_h[1],
                                     sessions=("regular",), **filt)
                b = fp["bars"][0]
                key = f"{vname}|{method}|{'+'.join(k for k, v in filt.items() if v) or 'all'}"
                out["first_hour"][key] = {"buy": b["buy"], "sell": b["sell"], "delta": b["delta"], "vol": b["vol"],
                                          "auction": b["auction"], "unclassified": b["unclassified"], "poc": b["poc"],
                                          "top_sell_levels": top_levels(fp, b["t"], "sell"),
                                          "top_buy_levels": top_levels(fp, b["t"], "buy"),
                                          "quality": fp["quality"]}
    # secuencia de 5 minutos 09:30-12:00 (Lee-Ready, base)
    fp5 = footprint.build(base_c, day, method="lr", tf_minutes=5, step=step, start=o930,
                          end=o930 + pd.Timedelta(minutes=150), sessions=("regular",))
    seq = []
    for b in fp5["bars"]:
        ls = [l for l in fp5["levels"] if l["t"] == b["t"]]
        ms = max(ls, key=lambda l: l["sell"]) if ls else None
        mb = max(ls, key=lambda l: l["buy"]) if ls else None
        seq.append({"t_ny": pd.Timestamp(b["t"], unit="ms", tz="UTC").tz_convert("America/New_York").strftime("%H:%M"),
                    "o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"], "vol": b["vol"], "buy": b["buy"],
                    "sell": b["sell"], "delta": b["delta"], "cum_delta": b["cum_delta"],
                    "max_sell_level": ms["p"] if ms else None, "max_buy_level": mb["p"] if mb else None,
                    "classified_share": round((b["buy"] + b["sell"]) / b["vol"], 3) if b["vol"] else None,
                    "trf_share": round(b["trf"] / b["vol"], 3) if b["vol"] else None})
    out["sequence_5m_lr"] = seq
    out["methods_summary_first_2h"] = aggressor.summary(base_c[(base_c["t"] >= o930) & (base_c["t"] < o930 + pd.Timedelta(hours=2))])
    out["quality_reconciliation"] = reconcile(sym, day, tr)
    return out


def reconcile(sym, day, tr):
    """Trades descargados frente a las barras de 1 min del proveedor (sesión regular)."""
    from micro import normalize, quality, runtime
    from micro.providers.base import FetchStats
    o, c = calendar.session_bounds(day, "regular")
    bars = []
    for pg in runtime.alpaca().fetch_pages("bars", sym, calendar.iso(o), calendar.iso(c), timeframe="1Min", stats=FetchStats()):
        bars.extend(pg)
    br = normalize.bars(normalize.records_to_frame("bars", bars))
    t = tr[tr["session"] == "regular"].assign(minute=lambda x: x["t"].dt.floor("min"), unknown_cond="")
    return quality.reconcile_trades_bars(t, br)


if __name__ == "__main__":
    res = {}
    for sym, day, step in CASES:
        print("…", sym, day, flush=True)
        res[f"{sym}|{day}"] = study(sym, day, step)
    f = storage.root() / "results" / "g15_case_study.json"
    f.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    for k, r in res.items():
        print(k, json.dumps({x: r[x] for x in ("opening_auction", "premarket", "day_path", "quality_reconciliation")}, default=str)[:900])
        for s in r["sequence_5m_lr"][:16]:
            print("  ", s)
