"""Impacto de los desenlaces sobre las señales de Flow negativo (sin rendimientos posteriores).
Cuenta días-estado y episodios cuyo horizonte de 40 sesiones contiene el fin de la serie, por índice, zona, año,
categoría y estado del valor de salida. Solo épocas con días de pertenencia (las demás no generan señales).
Salida: data/terminal_impact.json"""
import json
from collections import defaultdict
import pandas as pd
import fn_config as C

p = pd.read_parquet(C.WORK / "panel.parquet", columns=["index", "date", "key", "flow", "flow_complete",
                                                         "event_excluded", "terminal_within_40", "zone", "year"])
t = pd.read_csv(C.PUB / "terminal_events.csv", dtype=str, keep_default_na=False)
rel = t[t.key.isin(set(p.key))]
st = rel.set_index("key").value_status.to_dict()
cat = rel.set_index("key").category.to_dict()
p = p[(p.date >= p["index"].map(C.SIGNAL_START)) & p.flow_complete.fillna(False).astype(bool) & ~p.event_excluded]
p["tw"] = p.terminal_within_40 != ""
p["vstatus"] = p.key.map(st).where(p.tw, "")
out = {"relevant_terminations": {"total": int(len(rel)), "by_category": rel.category.value_counts().to_dict(),
                                 "by_value_status": rel.value_status.value_counts().to_dict(),
                                 "by_index_status": rel.assign(i=rel.indices.str.split(",")).explode("i")
                                 .groupby(["i", "value_status"]).size().unstack(fill_value=0).to_dict("index"),
                                 "by_year_status": rel.groupby(["year", "value_status"]).size().unstack(fill_value=0)
                                 .to_dict("index")}}
neg = p[p.flow < 0]
res = {}
for i, g in neg.groupby("index"):
    tot = g.zone.value_counts()
    aff = g[g.tw & (g.vstatus.isin(["desconocido", "terminos_incoherentes"]))]
    kn = g[g.tw & (g.vstatus == "conocido")]
    res[i] = {"negative_days": int(len(g)),
              "affected_unknown_value": int(len(aff)), "affected_known_value": int(len(kn)),
              "affected_ticker_change": int((g.tw & (g.vstatus == "no_aplica")).sum()),
              "unknown_pct_by_zone": {z: round(100 * (aff.zone == z).sum() / n, 3) for z, n in tot.items()},
              "unknown_by_year": aff.year.value_counts().sort_index().to_dict(),
              "unknown_by_category": aff.key.map(cat).value_counts().to_dict()}
# episodios bajo X afectados por desenlace de valor desconocido
cal = json.load(open(C.WORK / "calendar.json"))
cpos = {d: n for n, d in enumerate(cal)}
ep = defaultdict(lambda: [0, 0])
for (i, k), g in p.sort_values("date").groupby(["index", "key"]):
    f, pp = g.flow.to_numpy(), g.date.map(cpos).to_numpy()
    unk = (g.tw & g.vstatus.isin(["desconocido", "terminos_incoherentes"])).to_numpy()
    for X in (-10, -20, -30):
        last_in = -10 ** 9
        for n in range(len(f)):
            if f[n] < X:
                if pp[n] - last_in > 10 and (n == 0 or f[n - 1] >= X or pp[n] - pp[n - 1] > 1):
                    ep[(i, X)][0] += 1
                    ep[(i, X)][1] += int(unk[n])
                last_in = pp[n]
out["negative_days"] = res
out["episodes_unknown_terminal"] = {f"{i} X={X}": {"episodes": a, "unknown_terminal": b,
                                                   "pct": round(100 * b / max(1, a), 3)} for (i, X), (a, b) in sorted(ep.items())}
json.dump(out, open(C.PUB / "terminal_impact.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str)[:6000])
