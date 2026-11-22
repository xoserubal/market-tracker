"""cat-v1 — validación final sobre casos históricos y actuales (aprobación del usuario, 2026-11-21, §5).

Casos, elegidos por regla fija (no por su resultado):
1. Día ordinario. Histórico: el día de 2019 (sin cierre anticipado ni sospecha de datos) con menor fracción de
   valor-días con alguna alerta; valor: el de mayor volumen en dólares ese día. Actual: GOOGL 2026-11-17.
2. Estrés generalizado: 2020-03-16 (cortacircuito documentado); valor: el de mayor volumen en dólares.
3. Volumen alto sin desplazamiento: histórico, la alerta I2_stall de 2020-2021 con mayor M1/umbral en un episodio sin
   alertas de desplazamiento (familia D) y fuera de día de mercado. Actual: NVDA 2026-11-10.
4. Subasta de cierre: PLTR 2026-11-17 (desglose con trades ya hecho) y un valor de NYSE en 2019 cuya barra de las
   16:00 vale 0 (el primero por orden alfabético con V3_close_est = 0 el 2019-06-03).
5. After hours: actual PLTR 2026-11-17; histórico, la alerta C3_ext35 de 2021 con mayor valor bruto en un valor de
   liquidez ≥ mediana y fuera de día de mercado.
6. Datos incompletos: PFE 2019-08-12 (incidencia corroborada) y PFE 2019-10-09 (sospecha).
Además: investigación manual de valor-días sin alerta (histórico elegible, valor fuera de la capa 2 calculado bajo
demanda, y registro en vivo).

Salida: MICRO_DATA_DIR/results/cat_v1/validation_cases.json. No escribe en las capas 1-3.
Uso: py -3 cv1_validate.py [--port 8766]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lab"))
from micro import catalog_v1 as V, event_store, sessions, storage, valorday  # noqa: E402

OUT = storage.root() / "results" / "cat_v1"
NY = "America/New_York"


def ny(t):
    return pd.Timestamp(t).tz_convert(NY).strftime("%H:%M") if t is not None and pd.notna(t) else None


def lab(port, symbol, day, start="04:00", end="20:00"):
    return (f"http://127.0.0.1:{port}/?symbol={symbol}&day={day}&start={start}&end={end}&tf=1&session=extended"
            f"&catalog=cat-v1")


def alerts_of(symbol, day):
    al = event_store.read("alerts", day, version="cat-v1")
    al = al[al["symbol"] == symbol] if len(al) else al
    if not len(al):
        return []
    al = al.sort_values("t_detect_utc")
    out = []
    for a in al.to_dict("records"):
        out.append({k: a.get(k) for k in ("measure", "family", "segment", "representation", "status", "status_note",
                                         "value", "peak_value", "score_m1", "threshold_m1", "pct_own", "score_m2",
                                         "persistence", "share_market_family", "share_sector_family", "market_day",
                                         "sector", "threshold_knowledge", "episode_id")} |
                   {"data_quality": event_store.load_json(pd.Series([a.get("data_quality")]))[0],
                    "structural": event_store.load_json(pd.Series([a.get("structural")]))[0],
                    "start_ny": ny(a["t_start_utc"]), "detect_ny": ny(a["t_detect_utc"]),
                    "available_ny": ny(a["t_available_utc"]), "end_ny": ny(a["t_end_utc"]),
                    "window_ny": f"{ny(a['window_start_utc'])}-{ny(a['window_end_utc'])}"})
    return out


def measures_summary(r, top=8):
    ms = [m for m in r.get("measures", []) if m.get("score_m1") is not None and m.get("threshold_m1")]
    ms.sort(key=lambda m: -(m["score_m1"] / m["threshold_m1"]))
    keep = ("measure", "value", "score_m1", "threshold_m1", "pct_own", "score_m2", "n", "state", "reason")
    states = pd.Series([m.get("state") for m in r.get("measures", [])]).value_counts().to_dict()
    return {"source": r.get("source"), "n_measures": len(r.get("measures", [])), "states": states,
            "top_by_ratio": [{k: m.get(k) for k in keep} | {"ratio": round(m["score_m1"] / m["threshold_m1"], 3)}
                             for m in ms[:top]],
            "requires_trades": [{k: m.get(k) for k in keep} for m in r.get("measures", [])
                                if m.get("state") == "requires_trades"]}


def lab_check(symbol, day):
    import server as S
    S.LIB = S.Library()
    b = S.api_bars({"symbol": symbol, "day": day, "catalog": "cat-v1"})
    e = S.api_events({"day": day, "symbol": symbol, "catalog": "cat-v1"})
    v = S.api_valorday({"symbol": symbol, "day": day, "compute": "1"})
    blind = S.api_valorday({"symbol": symbol, "day": day, "blind": "1", "cursor": "12:00"})
    return {"bars": len(b.get("bars", [])), "marks": len(b.get("marks", [])),
            "marks_points": sum(1 for m in b.get("marks", []) if m["representation"] == "point"),
            "events_alerts": len(e.get("alerts", [])), "events_episodes": len(e.get("episodes", [])),
            "valorday_measures": len(v.get("measures", [])), "valorday_source": v.get("source"),
            "blind_valorday_locked": bool(blind.get("blind_locked"))}


def case(name, kind, symbol, day, port, why, extra=None):
    r = valorday.valor_day(symbol, day, compute=True)
    al = alerts_of(symbol, day)
    eps = event_store.read("episodes", day, version="cat-v1")
    eps = eps[eps["symbol"] == symbol] if len(eps) else eps
    first = min((a["start_ny"] for a in al), default="09:30")
    return {"case": name, "kind": kind, "symbol": symbol, "day": day, "why": why,
            "threshold_knowledge": V.threshold_knowledge(day), "alerts": al, "n_alerts": len(al),
            "episodes": [{k: e[k] for k in ("episode_id", "segment", "n_alerts", "t_start_utc", "t_detect_utc",
                                            "t_end_utc", "market_day")} for e in eps.to_dict("records")],
            "measures": measures_summary(r), "lab": lab_check(symbol, day),
            "lab_url": lab(port, symbol, day), **(extra or {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    a = ap.parse_args()
    al = pd.read_parquet(OUT / "alerts.parquet")
    day = pd.read_parquet(OUT / "day_family.parquet")
    fams = [c[6:] for c in day.columns if c.startswith("share_") and c != "share_D3_gap"]
    import pyarrow.dataset as ds
    import pyarrow.compute as pc
    mdir = storage.root() / "features" / "e2_measures"

    def biggest(d):
        t = ds.dataset(str(mdir), format="parquet").to_table(
            columns=["symbol", "date", "member", "dollar_vol", "V3_close_est__v"], filter=pc.field("date") == d).to_pandas()
        return t[t["member"]].sort_values("dollar_vol", ascending=False)

    cases = []
    # 1. día ordinario
    vd = al.groupby(["day", "entity"]).size().groupby("day").size()
    d19 = day[(day["date"].str[:4] == "2019") & ~day["suspected_data_outage"]].copy()
    d19["share_any"] = d19["date"].map(vd).fillna(0) / d19["n_elig"]
    from micro import calendar
    d19 = d19[~d19["date"].map(calendar.is_early_close)]
    od = d19.sort_values("share_any").iloc[0]["date"]
    cases.append(case("Día ordinario (histórico)", "ordinary", biggest(od).iloc[0]["symbol"], od, a.port,
                      f"día de 2019 con menor fracción de valor-días con alerta ({d19['share_any'].min():.1%})"))
    cases.append(case("Día ordinario (actual)", "ordinary", "GOOGL", "2026-11-17", a.port, "regla fija"))
    # 2. estrés
    cases.append(case("Estrés generalizado", "stress", biggest("2020-03-16").iloc[0]["symbol"], "2020-03-16", a.port,
                      "cortacircuito documentado; mayor volumen en dólares", {
                          "market_shares": day.loc[day["date"] == "2020-03-16", [f"share_{f}" for f in fams]].round(3)
                          .to_dict("records")}))
    # 3. volumen alto sin desplazamiento
    i2 = al[(al["measure"] == "I2_stall") & (al["day"] >= "2020-01-02") & ~al["market_day"]].copy()
    epfam = al.groupby("episode_id")["family"].agg(set)
    i2 = i2[~i2["episode_id"].map(lambda e: "D" in epfam[e])]
    i2["ratio"] = i2["score_m1"] / i2["threshold_m1"]
    r = i2.sort_values("ratio", ascending=False).iloc[0]
    cases.append(case("Volumen alto sin desplazamiento (histórico)", "volume_no_move", r["symbol"], r["day"], a.port,
                      "I2_stall con mayor M1/umbral en 2020-2021, episodio sin familia D, fuera de día de mercado"))
    cases.append(case("Volumen alto sin desplazamiento (actual)", "volume_no_move", "NVDA", "2026-11-10", a.port,
                      "alerta I2_stall en el escaneo en vivo"))
    # 4. subasta de cierre
    dd = json.loads((event_store.root() / "drilldowns" / "8d280bb8e4b92d69.json").read_text(encoding="utf-8"))
    cases.append(case("Subasta de cierre (actual, con trades)", "close_auction", "PLTR", "2026-11-17", a.port,
                      "desglose con trades ya hecho", {"trades_close_auction": dd["day_shares"]["close_auction"],
                                                       "bar_vs_trades": dd.get("close_auction_vs_bar_continuous")}))
    b19 = biggest("2019-06-03")
    z = b19[b19["V3_close_est__v"] == 0].sort_values("symbol")
    cases.append(case("Subasta de cierre (histórico, barra de las 16:00 vacía)", "close_auction", z.iloc[0]["symbol"],
                      "2019-06-03", a.port, f"{len(z)} de {len(b19)} miembros con V3_close_est = 0 ese día",
                      {"zero_close_bar_share_that_day": round(len(z) / len(b19), 3)}))
    # 5. after hours
    cases.append(case("After hours (actual)", "after_hours", "PLTR", "2026-11-17", a.port, "ficha E0/E1 del 17-nov"))
    c3 = al[al["measure"].str.startswith("C3_ext35") & (al["day"].str[:4] == "2021") & ~al["market_day"]].copy()
    c3 = c3[c3["liq"] >= c3["liq"].median()]
    r = c3.sort_values("value", ascending=False).iloc[0]
    cases.append(case("After hours (histórico)", "after_hours", r["symbol"], r["day"], a.port,
                      "C3_ext35 de 2021 con mayor valor bruto, liquidez ≥ mediana, fuera de día de mercado"))
    # 6. datos incompletos
    inc = V.data_incidents()
    for d in ("2019-08-12", "2019-10-09"):
        cases.append(case(f"Datos incompletos ({inc[d]['classification']})", "incomplete_data", "PFE", d, a.port,
                          inc[d]["window_ny"], {"incident": inc[d],
                                                "d3_share": float(day.loc[day["date"] == d, "share_D3_gap"].iloc[0])}))
    # investigación manual sin alerta
    manual = []
    for sym, d in (("JNJ", od), ("PLTR", "2020-11-27"), ("GOOGL", "2026-11-12")):
        r = valorday.valor_day(sym, d, compute=True)
        manual.append({"symbol": sym, "day": d, "source": r.get("source"), "n_measures": len(r.get("measures", [])),
                       "alerts": r.get("alerts"), "error": r.get("error")})
    res = {"generated_utc": pd.Timestamp.now("UTC").isoformat(), "params_sha256": V.PARAMS_SHA256, "cases": cases,
           "manual_without_alert": manual}
    (OUT / "validation_cases.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    for c in cases:
        print(f"{c['case']}: {c['symbol']} {c['day']} · {c['n_alerts']} alertas · lab {c['lab']}", flush=True)
    print(json.dumps(manual, ensure_ascii=False))


if __name__ == "__main__":
    main()
