"""G2A — eventos de reparto, splits incoherentes y rupturas de identidad por entidad (enmienda 7), sin resultados.

Salida (MICRO_DATA_DIR/results):
- g2a_split_status.parquet: cada registro de split de Alpaca por entidad, con 'applied' / 'incoherent' / 'outside';
- g2a_events.parquet: eventos E1-E3 por entidad (fecha, tipo, detalle);
- g2a_genuine_jumps.parquet: saltos >x2 o <x0,5 sin acción corporativa cerca (se conservan; sensibilidad).
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, distributions as D, outcomes, storage  # noqa: E402
import g2a_coverage  # noqa: E402


def load():
    ref = storage.root() / "reference"
    daily = pd.read_parquet(ref / "daily_ohlc_v2.parquet")
    daily["entity"] = daily["entity"].astype(str)
    ca = pd.read_parquet(ref / "corporate_actions.parquet")
    syms = g2a_coverage.entity_symbols(daily, ca)
    act = outcomes.parse_actions(ca)
    spin = pd.DataFrame([json.loads(j) for t, j in zip(ca["type"], ca["json"]) if t == "spin_offs"])
    return daily, syms, act, spin


def main():
    root = storage.root()
    daily, syms, act, spin = load()
    cur = D.curated_events()
    days = calendar.trading_days("2016-01-04", "2026-11-13")
    pos = {d: i for i, d in enumerate(days)}
    d = daily[~daily["filler"]].sort_values(["entity", "date"])
    st_all, ev_all, gj = [], [], []
    for e, g in d.groupby("entity"):
        g = g.reset_index(drop=True)
        s = syms.get(e, set())
        ss = act["splits"][act["splits"]["symbol"].isin(s)]
        if len(ss):
            st = D.split_status(g, ss)
            st.insert(0, "entity", e)
            st_all.append(st)
        applied, ev = D.entity_events(e, g, s, act, spin, cur)
        ev_all.append(ev)
        for dt, r in D.unexplained_jumps(g, applied, ev, pos):
            gj.append({"entity": e, "date": dt, "ratio": round(r, 4)})
    st = pd.concat(st_all, ignore_index=True)
    ev = pd.concat(ev_all, ignore_index=True)
    gj = pd.DataFrame(gj)
    st.to_parquet(root / "results" / "g2a_split_status.parquet")
    ev.to_parquet(root / "results" / "g2a_events.parquet")
    gj.to_parquet(root / "results" / "g2a_genuine_jumps.parquet")
    print("splits:", st["status"].value_counts().to_dict())
    print("eventos:", ev["kind"].value_counts().to_dict())
    print("eventos <= 2021-12-31:", ev[ev["date"] <= "2021-12-31"]["kind"].value_counts().to_dict())
    print("saltos reales conservados:", len(gj))
    return st, ev, gj


if __name__ == "__main__":
    main()
