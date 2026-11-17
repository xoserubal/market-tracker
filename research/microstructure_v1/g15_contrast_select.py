"""G1.5 — selección del caso de contraste (regla fijada ANTES de mirar los candidatos; resultado conocido por diseño).

Se busca un episodio con rasgos observables comparables al de NVDA (2026-11-12: apertura con hueco a la baja muy
fuerte y volumen extraordinario) pero que NO terminara en recuperación sostenida.

Regla (determinista):
  ventana: 2026-09-15 → 2026-11-13 (fuera del periodo de prueba; misma época de datos que NVDA, misma
           proporción de odd lots y timestamps en ns). Si no hay candidatos, se amplía a desarrollo 2017-2021.
  universo: miembros del S&P 500 en esa fecha (salvo NVDA).
  hueco:    apertura <= -7 % frente al cierre anterior.
  volumen:  trades del día >= 2 × mediana de las 20 sesiones previas.
  sin recuperación: cierre del día <= apertura del día Y cierre 5 sesiones después < cierre del día.
  elección: el de mayor volumen en dólares (lo más parecido en liquidez a NVDA).
Salida: results/g15_contrast_selection.json (todos los candidatos y el elegido).
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, runtime, storage  # noqa: E402
from micro.providers.base import FetchStats  # noqa: E402
from micro.providers.alpaca import DATA_BASE  # noqa: E402

WINDOWS = [("2026-09-15", "2026-11-13"), ("2017-01-03", "2021-10-28")]
GAP, VOL_X = -0.07, 2.0


def daily_ohlc(p, symbols, start, end):
    out = []
    stats = FetchStats()
    for i in range(0, len(symbols), 100):
        token = None
        while True:
            q = {"symbols": ",".join(symbols[i:i + 100]), "timeframe": "1Day", "start": start, "end": end,
                 "adjustment": "raw", "feed": "sip", "limit": 10000}
            if token:
                q["page_token"] = token
            j = p._get(f"{DATA_BASE}/v2/stocks/bars", q, stats)
            for s, bars in (j.get("bars") or {}).items():
                for b in bars:
                    out.append({"symbol": s, "date": b["t"][:10], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                                "v": b["v"], "n": b["n"]})
            token = j.get("next_page_token")
            if not token:
                break
    return pd.DataFrame(out), stats.requests


def candidates(p, iv, a, b):
    days = calendar.trading_days("2015-12-01", "2026-11-13")
    pos = {d: i for i, d in enumerate(days)}
    pre = days[max(0, pos[a] - 25)]
    post = days[min(len(days) - 1, pos[b] + 6)] if b in pos else b
    sp = iv[(iv["source"] == "sp500") & (iv["start"] <= b) & (iv["end"] >= a) & (iv["symbol"] != "NVDA")]
    syms = sorted(set(sp["symbol"]))
    d, req = daily_ohlc(p, syms, pre, post)
    d = d.sort_values(["symbol", "date"])
    g = d.groupby("symbol")
    d["prev_c"] = g["c"].shift(1)
    d["med_n20"] = g["n"].transform(lambda s: s.shift(1).rolling(20, min_periods=15).median())
    d["c_plus5"] = g["c"].shift(-5)
    d["gap"] = d["o"] / d["prev_c"] - 1
    d["dollar_vol"] = d["v"] * (d["o"] + d["c"]) / 2
    win = d[(d["date"] >= a) & (d["date"] <= b)].copy()
    # pertenencia a fecha
    mem = sp.groupby("symbol").apply(lambda x: list(zip(x["start"], x["end"])), include_groups=False).to_dict()
    win = win[[any(s <= dt <= e for s, e in mem.get(sym, [])) for sym, dt in zip(win["symbol"], win["date"])]]
    c = win[(win["gap"] <= GAP) & (win["n"] >= VOL_X * win["med_n20"])].copy()
    c["no_intraday_recovery"] = c["c"] <= c["o"]
    c["no_5d_recovery"] = c["c_plus5"] < c["c"]
    return c, req


if __name__ == "__main__":
    iv = pd.read_parquet(storage.root() / "reference" / "universe_intervals.parquet")
    p = runtime.alpaca()
    out = {"rule": __doc__, "windows": []}
    chosen = None
    for a, b in WINDOWS:
        c, req = candidates(p, iv, a, b)
        ok = c[c["no_intraday_recovery"] & c["no_5d_recovery"]].sort_values("dollar_vol", ascending=False)
        out["windows"].append({"window": [a, b], "requests": req, "gap_volume_candidates": c.round(4).to_dict("records"),
                               "qualifying": ok.round(4).to_dict("records")})
        if len(ok) and chosen is None:
            chosen = ok.iloc[0].to_dict()
            break
    out["chosen"] = chosen
    f = storage.root() / "results" / "g15_contrast_selection.json"
    f.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    for w in out["windows"]:
        print(w["window"], "candidatos hueco+volumen:", len(w["gap_volume_candidates"]), "cumplen:", len(w["qualifying"]))
        for r in w["gap_volume_candidates"]:
            print(" ", r["symbol"], r["date"], "gap", r["gap"], "c<=o", r["no_intraday_recovery"], "5d", r["no_5d_recovery"],
                  "$vol", round(r["dollar_vol"] / 1e9, 2), "B")
    print("ELEGIDO:", chosen)
