# G2A — Resultados de la exploración en desarrollo (2017-2021)

**Resumen.** Ninguna combinación de la familia C (H-C1/H-C2) ni de la familia A (H-A1) pasa las puertas del §4 de
`G2A_PROTOCOLO.md`. Según el propio protocolo, ninguna de las tres hipótesis confirmatorias va a la prueba
(2022-2026). La prueba sigue cerrada y sin tocar. No hay preregistro definitivo que congelar con contenido
confirmatorio: se te consulta cómo seguir (§6 al final).

Protocolo aplicado: `G2A_PROTOCOLO.md` (SHA-256 `07b7af6d…`, sin cambios) más las enmiendas 1-8 de
`G2A_PROTOCOLO_ENMIENDAS.md` (SHA-256 `ab80b778…`). Todas las enmiendas se hicieron antes de calcular ningún resultado.
Los datos viven en `MICRO_DATA_DIR`; aquí solo hay agregados.

## 1. Muestra de desarrollo (§8) — se cumple

| Puerta | Resultado |
|---|---|
| 1. Nivel A completo | 40 389 de 40 389 unidades `ok` |
| 2. Cobertura intradía ≥ 98 % por año, ≥ 95 % por sector y tercil | 99,3-100 % por año; ≥ 98,4 % por sector; 100 % por tercil |
| 3. Empresas que salieron del índice ≥ 95 % | 99,2 % (24,6 % de los valor-días miembro) |
| 4. Referencia = G1, saltos y salidas | Coincide; saltos tratados por la enmienda 7; 63 salidas clasificadas (`exits_dev.csv`) |
| 5. Barras diarias de B1 y horizontes | Completas (MON y CTXS solo faltan tras su salida) |

Para llegar ahí hubo que corregir cuatro problemas de datos (detalle en las enmiendas 7 y 8):
- **Intradía perdido:** el resumen intradía perdía el intradía de 33 valores del S&P 500 que también son tickers del
  proyecto. Reparado y comprobado celda a celda.
- **Escisiones:** Alpaca no registra casi ninguna antes de 2020; se usa la lista curada de 41.
- **Splits incoherentes con el precio** (20) y **tramos de otro emisor** (Arconic, Aptiv, du Pont): son eventos, y
  los valor-días con un evento en [t−259, t+40] se excluyen. Son 9 541 (1,6 %).
- **Dos días de caída de datos de minuto** (2021-04-19 y 2021-10-25): no cuentan como sesión para las variables
  intradía.

Resultados (`g2a_outcomes.py`): coinciden exactamente con `outcomes.total_return` (diferencia máxima 2·10⁻¹⁶ en 1 600
comparaciones). A 40 sesiones, 1 700 se liquidan por salida (0,28 %) y 44 faltan (< 0,01 %).

## 2. Exploración descriptiva, sin resultados (`g2a_describe.py`)

- **Población base de C** (miembro, fuerza relativa ≤ 0, sin máximo de 252 sesiones, Flow < 4 y Early Flow < 7,
  historia y sin evento): 160 898 valor-días. El filtro que más recorta es el de Flow/Early Flow.
- **k (percentiles 20/35/50 de RANGO_L, en ATR):** 4,28 / 4,99 / 5,71 con L = 40 y 8,08 / 9,27 / 10,49 con L = 120.
- **Episodios:** cortos, con mediana de 4-6 sesiones, porque la elegibilidad entra y sale. Episodios tratados por
  año: 247-1 165, así que la puerta de muestra se cumple en las 12.
- **Correlación descriptiva:** C4 (migración del POC) correlaciona 0,51 con el momentum a 20 sesiones. Recoge en
  buena parte dónde cotizó el precio últimamente.
- **Universo de A:** 588 824 valor-días en 1 208 fechas. La sustitución sectorial por el SPY (enmienda 2) afecta al
  0,5 %.

## 3. Familia A — H-A1 (`g2a_select_a.py`)

IC de Spearman entre el residuo de A_t y Ex neto a 10 sesiones, en fechas no solapadas desde el 2017-01-03.

| Combinación | Criterio (mediana anual) | IC agrupado | ES (mes) | IC por año 2017-2021 | Estabilidad | Vecinas | p de selección |
|---|---|---|---|---|---|---|---|
| w1 diaria | +0,0028 | +0,0035 | 0,0057 | +0,003 +0,015 +0,009 −0,007 −0,003 | no | no | 0,735 |
| w1 intradía | +0,0088 | +0,0017 | 0,0054 | −0,018 +0,009 +0,011 +0,013 −0,007 | no | no | 0,125 |
| w5 diaria | −0,0031 | −0,0001 | 0,0061 | +0,004 −0,008 −0,005 +0,012 −0,003 | no | no | 0,995 |
| w5 intradía | −0,0102 | −0,0085 | 0,0053 | −0,012 −0,010 −0,009 +0,001 −0,014 | no | no | 1,000 |
| w10 diaria | −0,0056 | −0,0019 | 0,0062 | −0,013 −0,004 −0,006 +0,031 −0,022 | no | no | 1,000 |
| w10 intradía | −0,0119 | −0,0121 | 0,0058 | −0,025 −0,012 −0,009 −0,000 −0,015 | no | no | 1,000 |

- **Contraste de selección:** el percentil 95 del máximo de 200 permutaciones es 0,0105, y ninguna combinación lo
  supera.
- **Lectura:** los IC están dentro de ±0,012, muy por debajo del mínimo útil (0,031, ver §5). Las variantes con más
  sesiones tienden a ser negativas, lo contrario de lo previsto.
- **Veredicto:** ninguna pasa. **H-A1 no va a la prueba.**

## 4. Familia C — H-C1 (`g2a_select_c.py`)

Δ = exceso del tratado − media de sus controles a 40 sesiones (bruto; tratado y controles comparten coste).

| Combinación | Criterio | Δ agrupado | ES (mes) | Δ por año 2017-2021 (pp) | Estab. | Vecinas | p sel. |
|---|---|---|---|---|---|---|---|
| L40 k20 θ0,80 | −0,63 pp | −0,40 | 0,37 | −1,40 −1,21 −0,63 +0,73 +0,49 | no | no | 1,00 |
| L40 k20 θ0,90 | −0,54 pp | −0,32 | 0,41 | −1,51 −1,50 −0,54 +1,35 +0,53 | no | no | 1,00 |
| L40 k35 θ0,80 | −0,62 pp | −0,52 | 0,33 | −2,16 −0,62 −1,43 +0,86 +0,33 | no | no | 1,00 |
| L40 k35 θ0,90 | −0,40 pp | −0,36 | 0,34 | −1,26 −0,40 −1,24 +0,48 +0,32 | no | no | 1,00 |
| L40 k50 θ0,80 | −0,54 pp | −0,11 | 0,38 | −1,46 −0,54 −1,35 +2,05 +0,65 | no | no | 1,00 |
| L40 k50 θ0,90 | −0,27 pp | −0,12 | 0,30 | −0,73 −0,27 −1,31 +0,78 +0,89 | no | no | 1,00 |
| L120 k20 θ0,80 | +0,58 pp | −0,02 | 0,54 | +1,10 −1,36 +0,18 +0,58 +0,78 | no | sí | 0,11 |
| **L120 k20 θ0,90** | **+0,77 pp** | **+0,38** | 0,43 | +0,96 −0,64 +0,54 +1,54 +0,77 | **sí** | **no** | **0,005** |
| L120 k35 θ0,80 | +0,01 pp | +0,10 | 0,36 | +0,33 −0,35 +0,01 +2,27 −0,59 | no | no | 0,99 |
| L120 k35 θ0,90 | −0,10 pp | −0,12 | 0,33 | +0,14 −0,20 −0,10 +0,64 −0,70 | no | sí | 1,00 |
| L120 k50 θ0,80 | −0,23 pp | +0,09 | 0,38 | +0,03 −0,23 −1,08 +3,68 −0,45 | no | no | 1,00 |
| L120 k50 θ0,90 | −0,07 pp | −0,23 | 0,34 | −0,07 +0,03 −1,39 +2,05 −1,05 | no | sí | 1,00 |

- **Contraste de selección:** el percentil 95 del máximo de 200 permutaciones es 0,66 pp.
- **La única combinación que lo supera es L120 k20 θ0,90** (0,77 pp, p = 0,005). También tiene el signo previsto en
  4 de 5 años y en las dos mitades.
- **Falla la puerta 3 («no es un pico aislado»):** sus 4 vecinas tienen Δ agrupado negativo (L40 −0,32; k35 −0,12;
  k50 −0,23; θ0,80 −0,02). Es justo el patrón que esa puerta descarta, un resultado aislado en una esquina de la
  rejilla.
- **Las 6 de L = 40 tienen el signo contrario al previsto** en 2017-2019.
- **Controles escasos:** en el 54-69 % de los tratados no hay control del mismo sector y el 55-67 % tiene menos de 3.
  La población elegible por fecha es pequeña (~23-60 valores).
- **Veredicto:** ninguna pasa. **H-C1 no va a la prueba.** H-C2 depende de la combinación elegida en C y tampoco va.
  Como no hay combinación elegida, no se calculan la potencia del §6 ni el valor de H-C2 en desarrollo.

## 5. Potencia de A (§1, §7), para el registro

- σ₁₀ (dispersión transversal mediana de Ex neto a 10 sesiones) = 4,6 %.
- Umbral de equilibrio = 0,002 / (1,40 · 0,046) = 0,031, así que el mínimo útil es 0,031.
- Desviación del IC por fecha = 0,067. Con 118 fechas de prueba, el mínimo detectable es ≈ 0,020: habría bastado
  para detectar el mínimo útil.
- **El problema no es la potencia:** en desarrollo no hay efecto.

## 6. Qué queda y decisión pendiente

- Prueba (2022-2026): cerrada; ninguna función de resultado se ha ejecutado sobre ella.
- H-B1 (ticks) y las variables de agresor y delta: siguen siendo exploratorias, sin contraste confirmatorio.
- Captura en sombra: sigue desactivada.

**Opciones, a tu elección:**
1. **Cerrar G2 como resultado negativo de desarrollo.** Las anomalías de actividad sin desplazamiento, tal como se
   definieron, no anticipan el exceso a 10-40 sesiones en el S&P 500 de 2017-2021. Se conservan los datos y la
   infraestructura.
2. **Mantener solo la parte exploratoria** (ticks, agresor), sin pretensión confirmatoria.
3. **Rediseño.** Exige un protocolo nuevo, porque desarrollo ya está gastado para estas hipótesis. Probar en
   2022-2026 una variante elegida después de ver esto sería legítimo solo con un preregistro nuevo que reconozca que
   la variante salió de mirar desarrollo. La combinación L120 k20 θ0,90 no debe rescatarse sin más: es exactamente
   el pico aislado que la puerta 3 debía filtrar.

Ficheros (en `MICRO_DATA_DIR/results/`):
- `g2a_coverage.json`, `g2a_events.parquet`, `g2a_split_status.parquet`, `g2a_intraday_outages.json`;
- `g2a_describe.json`, `g2a_outcomes_summary.json`;
- `g2a_select_a.json`, `g2a_select_c.json`.
