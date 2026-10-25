import json, sys
sys.path.insert(0, "scripts")
import paper_trading as pt, ranking_score_calculator as rs
fz = sys.argv[1]
cur = json.load(open(f"X" if False else sys.argv[2], encoding="utf-8"))
new = json.load(open(sys.argv[3], encoding="utf-8"))
picks = json.load(open(f"{fz}/ai_picks.json", encoding="utf-8"))
TH = [("HC entrada 82",82),("CFL 75",75),("ER 68",68),("MTB 62 / suelo",62)]
print("== Cambios de PCS por ticker ==")
rows=[]
for tk in sorted(set(cur)|set(new)):
    a, b = cur.get(tk), new.get(tk)
    if not a: rows.append((tk,"(nuevo)")); continue
    if not b: rows.append((tk, f"ELIMINADO  pcs={a['pcs']} elig={a['eligible']} theme={a['theme']}")); continue
    d = round(b["pcs"]-a["pcs"],1)
    if d or a["eligible"]!=b["eligible"] or a["theme"]!=b["theme"] or a["subtheme"]!=b["subtheme"]:
        cross=[n for n,t in TH if (a["pcs"]>=t)!=(b["pcs"]>=t)]
        rows.append((tk, f"PCS {a['pcs']}->{b['pcs']} (Δ{d:+}) B {a['component_B']}->{b['component_B']} F {a['component_F']}->{b['component_F']} elig {a['eligible']}->{b['eligible']} | {a['theme']}/{a['subtheme'] or '-'} -> {b['theme']}/{b['subtheme'] or '-'}" + (f"  CRUZA: {cross}" if cross else "")))
for r in rows: print(f"  {r[0]:9} {r[1]}")
nz=[r for r in rows if "Δ" in r[1] and "Δ+0" not in r[1] and "Δ0" not in r[1]]
def summ(x):
    el=[c for c in x.values() if c["eligible"]]
    return {"total":len(x),"elegibles":len(el),**{n:sum(1 for c in el if c["pcs"]>=t) for n,t in TH}}
print("\n== Resumen ==\n  actual:", summ(cur), "\n  nuevo: ", summ(new))
# theme averages (fallback B) -- recompute like pcs
print("\n== Concentración temática (posiciones abiertas congeladas) ==")
c1,e1 = pt.compute_theme_concentration(list(cur.values()), picks); c2,e2 = pt.compute_theme_concentration(list(new.values()), picks)
openpos = sorted({p["ticker"] for ptf in picks["portfolios"].values() for p in ptf.get("positions",[])})
for tk in sorted(set(c1)|set(c2)):
    if c1.get(tk)!=c2.get(tk): print(f"  {tk:9} {c1.get(tk)} -> {c2.get(tk)}")
print("  exposición por tema actual:", {k:(v['open_positions'],v['risk']) for k,v in e1.items()})
print("  exposición por tema nueva: ", {k:(v['open_positions'],v['risk']) for k,v in e2.items()})
print("\n== theme_breadth (Ranking Score): (elegibles, total) por tema ==")
b1=rs.build_theme_breadth_index(list(cur.values())); b2=rs.build_theme_breadth_index(list(new.values()))
for th in sorted(set(b1)|set(b2)):
    if b1.get(th)!=b2.get(th): print(f"  {th:22} {b1.get(th)} -> {b2.get(th)}")
print("\n== Posiciones abiertas afectadas ==")
for name, ptf in picks["portfolios"].items():
    for p in ptf.get("positions",[]):
        tk=p["ticker"]; a,b=cur.get(tk),new.get(tk)
        if a and (not b or a["pcs"]!=b["pcs"] or a["theme"]!=b["theme"] or a["subtheme"]!=b["subtheme"]):
            print(f"  {name:28} {tk:9} pcs {a['pcs']} -> {b['pcs'] if b else 'ELIMINADO'} | theme {a['theme']} -> {b['theme'] if b else '-'}")
