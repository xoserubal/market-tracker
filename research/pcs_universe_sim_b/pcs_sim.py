"""Simulación hermética del PCS con inputs congelados (commit e728e75d).
Uso: py -3.12 pcs_sim.py FROZEN_DIR UNIVERSE_JSON OUT_JSON
Reutiliza compute_pcs() de scripts/pcs_calculator.py sin tocarlo; no llama a la red
(daily=None: DEMS/extension_risk no afectan al PCS)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts").resolve()))
import pcs_calculator as pc
fz = Path(sys.argv[1]); uni = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
L = lambda n: json.loads((fz/n).read_text(encoding="utf-8"))
macro_j, rot_j, cand_j = L("macro_history.json"), L("rotation_signals.json"), L("stock_candidates.json")
macro_latest = macro_j.get("latest", {}); hist = macro_j.get("history", []); last_hist = hist[-1] if hist else {}
rot_idx = {s["ticker"]: s for s in rot_j.get("latest_signals", [])}
u_meta = {t["ticker"]: t for t in uni.get("tickers", [])}
cand_idx = {}
for c in cand_j.get("candidates", []):
    e = dict(c)
    if c["ticker"] in u_meta: e["theme"] = u_meta[c["ticker"]].get("theme", "")
    cand_idx[c["ticker"]] = e
cbt = {}
for c in cand_idx.values():
    if c.get("theme") and c.get("ret_13w_vs_spy") is not None: cbt.setdefault(c["theme"], []).append(c["ret_13w_vs_spy"])
out = {tk: pc.compute_pcs(tk, m, macro_latest, last_hist, rot_idx, cand_idx, cbt, daily=None) for tk, m in u_meta.items()}
Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
