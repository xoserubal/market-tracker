import json, sys, copy
base = json.load(open(sys.argv[1], encoding="utf-8")); corr = json.load(open(sys.argv[2], encoding="utf-8"))
sets = sys.argv[3].split("+"); only = sys.argv[5] if len(sys.argv) > 5 else None
u = copy.deepcopy(base); seen = set(); out = []
patch = {}
for s in sets:
    for tk, p in corr[s].items():
        if only and tk != only: continue
        patch.setdefault(tk, {}).update(p)
for t in u["tickers"]:
    tk = t["ticker"]
    if tk in seen: continue          # dedupe LLY
    seen.add(tk)
    p = patch.get(tk, {})
    if p.get("_remove"): continue
    t.update({k: v for k, v in p.items() if not k.startswith("_")})
    out.append(t)
u["tickers"] = out
json.dump(u, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
