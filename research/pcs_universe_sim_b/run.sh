#!/usr/bin/env bash
# Reproduce la simulación de la línea B (wiki/AUDITORIA_UNIVERSE_LINEA_B.md).
# Inputs congelados del commit e728e75d; sin red. Python 3 con las dependencias del pipeline (PY=... para elegir intérprete).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
D=research/pcs_universe_sim_b; T=$(mktemp -d)
for f in universe.json macro_history.json rotation_signals.json stock_candidates.json ai_candidates.json ai_picks.json; do
  git show e728e75d:docs/data/$f > "$T/$f"; done
PY=${PY:-py -3.12}
$PY $D/pcs_sim.py "$T" "$T/universe.json" "$T/sim_B0.json"
# Validación: B0 debe reproducir ai_candidates.json congelado 149/149
$PY - "$T" <<'P'
import json,sys; t=sys.argv[1]; s=json.load(open(f"{t}/sim_B0.json",encoding="utf-8")); a=json.load(open(f"{t}/ai_candidates.json",encoding="utf-8"))
bad=[c["ticker"] for c in a["candidates"] if s[c["ticker"]]["pcs"]!=c["pcs"] or s[c["ticker"]]["pcs_components"]!=c["pcs_components"]]
print("validación B0:", len(a["candidates"])-len(bad), "/", len(a["candidates"]), "idénticos"); assert not bad, bad
P
$PY $D/apply.py "$T/universe.json" $D/corrections.json objective "$T/u_B1.json"
$PY $D/apply.py "$T/universe.json" $D/corrections.json objective+interpretive "$T/u_B2.json"
$PY $D/pcs_sim.py "$T" "$T/u_B1.json" "$T/sim_B1.json"; $PY $D/pcs_sim.py "$T" "$T/u_B2.json" "$T/sim_B2.json"
PYTHONIOENCODING=utf-8 $PY $D/compare.py "$T" "$T/sim_B0.json" "$T/sim_B1.json" 2>&1 | grep -v -i warn > "$T/cmp_B1.txt"
PYTHONIOENCODING=utf-8 $PY $D/compare.py "$T" "$T/sim_B0.json" "$T/sim_B2.json" 2>&1 | grep -v -i warn > "$T/cmp_B2.txt"
diff -q "$T/cmp_B1.txt" $D/cmp_B1.txt && diff -q "$T/cmp_B2.txt" $D/cmp_B2.txt && echo "Resultados idénticos a los del informe."
