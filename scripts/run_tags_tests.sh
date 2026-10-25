#!/usr/bin/env bash
# Batería completa de Portfolio Tags. Sin red, sin modelos de pago, sin tocar datos reales.
#   bash scripts/run_tags_tests.sh
# En Windows local usar PY="py -3.12" (el `py -3` por defecto no tiene yfinance).
set -u
cd "$(dirname "$0")/.."
PY="${PY:-python}"
fail=0
run() { echo; echo "=== $* ==="; "$@" || fail=1; }
run node scripts/test_ticker_tags_lib.js
run node scripts/test_ticker_tags_store.js
run node scripts/test_ticker_tags_http.js
run $PY scripts/test_tags_invariance.py
# La prueba de navegador (test_ticker_tags_ui.js) necesita Edge/Chrome + puppeteer-core: solo local.
echo
[ "$fail" = 0 ] && echo "TAGS: TODO OK" || echo "TAGS: HAY FALLOS"
exit $fail
