#!/usr/bin/env bash
# Enmienda 1 — tanda 1 corregida por familias acumuladas (mismas reglas de selección; sin tocar los originales).
# Uso: FLOWNEG_DATA_DIR=... bash s6_variantes.sh
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
W="$FLOWNEG_DATA_DIR/work"
run() {  # sufijo panel familias
  echo "== $1 (panel $2; $3)"
  FN_OUT="$1" FN_PANEL="$2" FN_CORR="$3" py -3 s4_etapa1.py --tanda 1 > "$W/etapa1_tanda1$1.log" 2>&1
  grep -E "elegibles|congelado" "$W/etapa1_tanda1$1.log"
}
run c1s      v4c1s   splits
run c1si     v4c1si  splits,identity
run c1sic    v4c1sic splits,identity,cik
run c1sicp   v4c1sic splits,identity,cik,spinoffs
run c1sicpj  v4c1sic splits,identity,cik,spinoffs,jumps
run c1sicpjt v4c1sic splits,identity,cik,spinoffs,jumps,terminals
run c1       v4c1sic splits,identity,cik,spinoffs,jumps,terminals,missing
