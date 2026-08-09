# Relative Flow Family Falsification Test v1 — HIPÓTESIS DESCARTADA

**Estado: descartada (NOT SUPPORTED), 2026-08-10.** Ver `CLAUDE.md`, sección
"Relative Flow Family Falsification Test v1 — hipótesis refugio/industrial
refutada (2026-08-10)" para el resumen, y
`outputs/relative_family_test_v1_informe.md` para el informe completo.

## Qué es esto

Prueba preregistrada (`wiki/PREREGISTRO_RELATIVE_FLOW_FAMILY_TEST_V1.md`)
diseñada para intentar refutar una hipótesis surgida de una exploración
interactiva no preregistrada sobre Relative Flow Lab: que la regla
"entrada paso-a-Improving / salida cualquiera-de-las-dos" bate a
comprar-y-mantener en activos refugio/monetarios (oro, plata, bitcoin,
ethereum, mineras de oro) y pierde en materias primas industriales (cobre,
platino, paladio, metales base).

## Resultado

**Refutada.** Al corregir la métrica (de Δ TAE, que sesgaba a favor de
estrategias con baja exposición en un mercado alcista, a
`excess_CAGR_calendar`, que sí penaliza el coste de oportunidad de estar
fuera del mercado), la separación entre familias desaparece casi por
completo: mediana refugio = -25.73, mediana industrial = -25.93,
p=1.000 tras Bonferroni. Ver informe completo para el detalle de placebos,
leave-one-out y correlación intra-familia.

## Cómo reproducir

```bash
cd research/relative_flow_family_test_v1
py -3 test_relative_family_falsification.py          # 27 tests unitarios
py -3 relative_family_falsification_test.py --save-cache   # corre el test completo
```

Universo congelado en `../../backtest/config/relative_family_test_v1.yaml`
— no modificar sin abrir una v2 nueva y documentar por qué.

## Por qué queda aquí y no se borra

Valor histórico y metodológico: documenta un caso real donde una métrica
mal elegida (Δ TAE sobre días expuestos) produjo un patrón que parecía
sólido y no lo era. Ver el "Principio: métrica primaria para estrategias
con exposición intermitente" en `CLAUDE.md` — regla derivada directamente
de este resultado, aplicable a análisis futuros.

No se usa para trading real. No toca `paper_trading.py`, `pcs_calculator.py`,
ninguna cartera ni el motor IA.
