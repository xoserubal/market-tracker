# Capitulation Precursors v1 — SIN PRECURSOR FIABLE (NOT SUPPORTED)

**Estado: sin precursor identificado, 2026-08-12.** Ver `CLAUDE.md`, sección
"PCS-floor whipsaw monitor" / búsqueda de precursores de capitulación, y
`wiki/HALLAZGOS_CAPITULACION_PRECURSORES_V1.md` para el informe completo.

## Qué es esto

Prueba preregistrada (`wiki/PREREGISTRO_CAPITULACION_PRECURSORES_V1.md`)
que intenta responder: ¿algo en el RSI, el volumen, la forma de la vela o la
velocidad de una capitulación anticipa, con días de antelación, si va a venir
un rebote? Surgió de una exploración puntual sin grupo de control (21 tickers
del portfolio que sí rebotaron) que no encontró ningún aviso previo — esta
prueba añade el grupo de control que faltaba: **todas** las capitulaciones del
universo, rebotaran o no.

## Resultado

**Ninguna de las 9 features candidatas ni las 7 reglas de la rejilla congelada
supera la barra preregistrada.** Solo `rsi14_T0` sobrevive Bonferroni en DEV
(p=0.0033, efecto pequeño) pero no replica en TEST (p=0.27). Volumen, forma de
vela, divergencia de RSI, racha de días bajistas y velocidad de la caída no
discriminan en absoluto (p>0.15 en todos los casos). Ver informe completo para
la tabla de las 9 comparaciones.

## Cómo reproducir

```bash
cd research/capitulation_precursors_v1
py -3 build_dataset.py --save-cache      # descarga 5y de 112 tickers, ~590 eventos
py -3 analyze.py                         # solo DEV: comparación de features + rejilla de 7 reglas
py -3 analyze.py --confirm-test          # confirmación única en TEST de lo que sobrevivió DEV
```

Definiciones de evento/resultado/features congeladas en
`../../wiki/PREREGISTRO_CAPITULACION_PRECURSORES_V1.md` — no modificar los
umbrales aquí sin abrir una v2 y documentar por qué.

## Por qué queda aquí y no se borra

Mismo motivo que `research/relative_flow_family_test_v1/`: evita repetir la
misma exploración sin control en el futuro y sirve como referencia de que el
patrón visible a ojo en pocos casos no sobrevivió con n grande y un test
adecuado. No se usa para trading real. No toca `paper_trading.py`,
`koncorde_calculator.py`, `pcs_calculator.py` ni ninguna cartera.
