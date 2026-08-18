# GEX (dealer gamma exposure) pilot — NO INTEGRADO

**Estado: piloto completado, no promovido a producción, 2026-08-18.** Ver
`CLAUDE.md`, sección "GEX (dealer gamma exposure) — piloto, no integrado
(2026-08-18)" para el resumen, y `HALLAZGOS.md` para el detalle completo de
la verificación.

## Qué es esto

Piloto para estimar el posicionamiento de gamma de los dealers (largo vs
corto) en `^SPX`, usando cadenas de opciones gratuitas de yfinance +
Black-Scholes, a raíz de que un análisis externo señaló que ese dato faltaba
para calibrar la fuerza de un "desanclaje" de tipos en `duration.html`.

## Resultado

**No integrado.** El cálculo corre correctamente sobre datos reales, y el
nivel de "gamma flip" calculado quedó razonablemente cerca de un proveedor
externo (~0.1% de diferencia) — pero no se encontró ninguna fuente gratuita
verificablemente en vivo contra la que contrastar el signo/magnitud del Net
GEX con confianza, y la convención subyacente (qué OI es "dealer short" vs
"dealer long") es una aproximación que solo el desglose customer/firm/market-
maker de la OCC —dato de pago— resolvería de verdad. Ver `HALLAZGOS.md`.

## Cómo reproducir

```bash
cd research/gex_monitor_pilot
py -3 gex_pilot.py                    # ^SPX, horizonte 60 días, guarda JSON
py -3 gex_pilot.py --horizon-days 30 --no-save
```

## Por qué queda aquí y no se borra

Base de cálculo reutilizable si en el futuro aparece una fuente con
desglose real de posicionamiento dealer (de pago o no). No se usa en
producción. No toca `paper_trading.py`, `pcs_calculator.py`, ninguna
cartera, `duration.html` ni `positioning.html`.
