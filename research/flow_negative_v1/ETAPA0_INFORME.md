# Flow negativo — informe de la etapa 0 (construcción y calidad de datos)

Fecha: 2026-11-18. Autorizada en el encargo del mismo día. **No se ha calculado ningún rendimiento posterior a una
señal.** Lo que hay aquí es solo disponibilidad, calidad, identidad y la distribución del propio Flow.
Producción sin tocar.

Entregables de este documento: cobertura (§2-§4), diagnóstico de H1 (§6) y resumen de puertas de calidad (§7).
Empresas desaparecidas: `EMPRESAS_DESAPARECIDAS.md`. Preregistro revisado: `wiki/PREREGISTRO_FLOW_NEGATIVO_V2.md`.

## 1. Qué se ha construido

| Pieza | Script | Resultado |
|---|---|---|
| Composición histórica S&P 500 / 400 / 600 | `s0_universe.py` | `data/membership.csv`: 798 / 1 043 / 1 123 intervalos |
| Precios Alpaca (SIP diario, en bruto) + acciones corporativas | `s0_prices.py`, `s0_prices_retry_empty.py` | 2 332 peticiones; 2 369 series por época de identidad |
| Series: identidad, splits, dividendos, eventos, Flow | `s0_series.py` | Splits coherentes 235 aplicados, 34 incoherentes (no aplicados) |
| Desenlaces de empresas desaparecidas | `s0_terminal.py`, `s0_terminal_impact.py` | Ver `EMPRESAS_DESAPARECIDAS.md` |
| Capitalización (SEC) | `s0_sec.py` | CIK para el 98 % de las empresas |
| Paridad del Flow | `s0_parity.py` | Fórmula idéntica a producción; Alpaca ≈ Yahoo |
| Panel de días-miembro | `s0_coverage.py` | 4,1 M días-miembro con Flow, liquidez, capitalización, eventos y desenlaces |
| Diseño de H1 | `s0_h1_design.py` | Tamaño de celdas y variación del resto R |

Datos con licencia de Alpaca (precios por valor y día), en `C:\Users\Usuario\market_data\flow_negative_v1`,
fuera del repo y de Dropbox. La unidad D: de `MICRO_DATA_DIR` no estaba montada en este equipo (DESPACHOB). En el
repo solo hay código, composición de índices (pública) y agregados (`data/*.json`).

## 2. Composición histórica

Coherencia: se aplican los cambios de un año a la instantánea de Wikipedia y se compara con la instantánea del año
siguiente. «Empresa» descuenta los cambios de ticker (emparejados por nombre; es orientativo: confunde, por
ejemplo, Alaska Air con Alaska Communications).

| Año → siguiente | S&P 500 ticker / empresa | S&P 400 ticker / empresa | S&P 600 ticker / empresa |
|---|---|---|---|
| 2016 | 99,2 / 99,6 % | **85,9 / 86,7 %** | — |
| 2017 | 98,4 / 98,8 % | 96,6 / 97,5 % | — |
| 2018 | 97,5 / 98,2 % | **93,0 / 94,0 %** | — |
| 2019 | 96,7 / 97,5 % | **89,4 / 89,8 %** | — |
| 2020 | 98,6 / 98,6 % | **86,7 / 87,6 %** | (reconstrucción hacia atrás) |
| 2021 | 99,2 / 99,2 % | 95,1 / 95,6 % | (reconstrucción hacia atrás) |
| 2022 | 98,0 / 98,8 % | 95,8 / 96,8 % | 98,8 / 98,8 % |
| 2023 | 98,4 / 99,2 % | 97,8 / 97,8 % | 95,6 / 97,2 % |
| 2024 | 98,4 / 98,8 % | 98,5 / 99,0 % | 97,5 / 98,5 % |
| 2025 | 98,8 / 100 % | 97,5 / 98,0 % | 96,7 / 97,7 % |

- **S&P 500:** correcto todos los años (≥ 97,5 % por empresa).
- **S&P 400, 2016-2020: no supera el 95 %.** La tabla de cambios de Wikipedia de esos años está incompleta y la lista
  de componentes también falla: la de 2016 seguía incluyendo empresas absorbidas en 2015 (Advent, AOL, Con-way,
  City National, Cytec, Omnicare, Rock-Tenn…). Se probó anclar con 91 instantáneas mensuales (2015-06 → 2022-12):
  no sirve, porque las propias instantáneas se contradicen de un mes a otro (muchos meses con ~11 diferencias; entre
  nov-2016 y ene-2017, 68 de golpe). Detalle: `data/universe_quality_monthly_sp400_test.json`. Se mantienen las
  anclas anuales.
- **S&P 600:** las listas de Wikipedia de 2019, 2020 y 2021 tienen 993-1 058 valores (no 600) y no se pueden usar como
  ancla. 2020-2021 se reconstruye hacia atrás desde la instantánea de ene-2022 deshaciendo la tabla de cambios
  (completa desde dic-2019). Contraste con esas listas: el 83,7 % de lo reconstruido para dic-2019 está en la lista
  de esa fecha y el 96,5 % para ene-2021. **2020 es el año más dudoso del S&P 600.**

## 3. Precios y Flow

### 3.1 Cobertura de precios (días-miembro con precio), por índice y año

| Año | S&P 500 | S&P 400 | S&P 600 |
|---|---|---|---|
| 2016 | 99,6 % | **94,5 %** | — |
| 2017 | 99,9 % | 98,5 % | — |
| 2018 | 100,0 % | 98,5 % | — |
| 2019 | 100,0 % | 98,7 % | — |
| 2020 | 100,0 % | 99,3 % | 99,6 % |
| 2021 | 100,0 % | 99,4 % | 99,8 % |
| 2022 | 99,8 % | 99,8 % | 99,8 % |
| 2023 | 100,0 % | 100,0 % | 99,8 % |
| 2024 | 100,0 % | 100,0 % | 99,7 % |
| 2025 | 99,9 % | 99,8 % | 100,0 % |
| 2026 | 99,7 % | 99,9 % | 98,9 % |

- Por sector, la peor cobertura es Energía del S&P 400 (93,6 %): empresas en quiebra que la lista seguía incluyendo.
  El resto de sectores ≥ 97,8 %.
- **Qué son los días sin precio** (`data/stage0_extra_checks.json`): casi todos son errores de composición, no
  huecos de Alpaca.
  - Días posteriores al último dato de la empresa (la lista la seguía incluyendo): S&P 400 3 630, 500 792, 600 1 959.
  - Días anteriores al primer dato (la empresa aún no cotizaba con ese ticker): 3 849 / 745 / 1 467.
  - Tickers sin ninguna serie (5 del S&P 400 de 2016, absorbidos en 2015): 3 915.
  - Huecos interiores reales: 347 en el S&P 400, 1 en el 500, 0 en el 600.
- Enlaces de identidad usados: por ticker, por cambio de nombre de Alpaca y por CIK de la SEC (cambios de ticker
  anteriores a 2020, que Alpaca no registra). El enlace por CIK cubre el 0-1,3 % de los días según índice y año.
- **Corrección hecha en esta etapa:** una misma petición puede traer dos empresas con el mismo ticker (Chesapeake
  antes y después de su quiebra, Dow Chemical y la nueva Dow, Gulfport, Oasis, Diebold, Valaris…). La primera
  versión solo conservaba la última y perdía justo los años de hundimiento previos a la quiebra. Ahora cada época
  de identidad es una serie propia y cada día usa la época que lo contiene.

### 3.2 Desde cuándo hay Flow completo — puerta no superada para 2016-2017

Alpaca (SIP gratuito) empieza el 4-ene-2016. El Flow necesita 120 sesiones para el Koncorde diario, **100 semanas
para el Koncorde semanal** (como producción) y 365 días para la distancia al máximo. Resultado: el Flow completo
existe desde el **29-dic-2017**. En 2016-2017, entre el 0 % y el 0,4 % de los días-miembro tiene Flow completo;
desde 2018, el 95,8-99,3 %. Antes de esa fecha falta el Koncorde semanal, que vale hasta ±1 punto.

### 3.3 Paridad del Flow (`data/parity.json`)

| Comparación | Resultado | Puerta |
|---|---|---|
| Réplica Python frente a `computeFlowScore` de `shared/flow-score.js` (producción) | 3 000 filas, diferencia máxima 0,00 | Superada |
| Flow con Alpaca frente a Flow con Yahoo (mismo código), 494 valores, 1,06 M filas, desde 2018 | Mediana 0,0; p90 0,0; p99 3,0; 4,3 % de filas con diferencia > 2 | Superada (mediana ≤ 0,5 y p90 ≤ 2) |

El peor caso es SW (Smurfit Westrock): Yahoo y Alpaca dan historias distintas antes de la fusión de 2024 (identidad,
no cálculo).

### 3.4 Ajustes

- Splits de Alpaca: 235 aplicados (explican el precio de su fecha); 34 incoherentes con el precio y no aplicados
  (pasan a ser eventos).
- Eventos que excluyen las señales con ventana [t − 259, t + 40] sesiones, como en la enmienda 7 de
  microestructura:
  - escisiones de Alpaca: 73;
  - escisiones de la lista curada (solo S&P 500 2016-2021): 47;
  - dividendos ≥ 10 %: 48;
  - splits incoherentes: 34.
- Peso de la exclusión: 0,2-2,3 % de los días-miembro según índice y año.
- Saltos ×2 o ×0,5 sin explicar: 92 en 79 series. Se conservan; la sensibilidad que los excluye queda en el
  preregistro.
- Riesgo que queda: escisiones del S&P 400 y 600 anteriores a 2020 que ninguna fuente registra. Por debajo de ~5 %
  del precio no se distinguen de un día normal.

## 4. Capitalización, liquidez y rotación

- **Enlace con la SEC:**

  | Vía | Empresas | Notas |
  |---|---|---|
  | CIK de Wikipedia | 1 992 | |
  | Tickers vigentes de la SEC | 182 | Solo si coincide el nombre |
  | Búsqueda por nombre en EDGAR | 108 | |
  | Sin enlace | 38 | |
  | CIK ambiguo | 9 | |

  Riesgo conocido: el enlace por nombre puede caer en la entidad posterior a una reestructuración (Frontier
  Communications → la entidad nueva tras su quiebra).
- **Acciones en circulación:** se usa el dato de la portada de cada 10-K/10-Q con fecha de presentación ≤ t y ≤ 400
  días de antigüedad, corregido por los splits aplicados entre el cierre del dato y t.
- **Errores de la SEC detectados y limpiados:** valores en miles en vez de unidades, escalas de ×1 000 a ×1 000 000
  y ceros.
  - Antes de limpiar: 157 saltos de acciones ×2 sin split, en 99 series.
  - Limpieza: se descarta una presentación si, llevada a la base actual, se aleja más de ×2 de la mediana de las 5
    presentaciones centradas. Se descartaron 278 presentaciones.
  - Después: 49 saltos en 45 de 2 049 series (2,2 %). Una parte son fusiones reales (Civitas, Columbia, Coterra);
    otra, errores consecutivos que el filtro no ve (Cross Country, Chesapeake Utilities).
- **Cobertura de capitalización:** 83-93 % de los días-miembro según índice y año (≥ 80 % en todos).
- Varias clases de acciones: 0-0,2 % de los días.
- **Liquidez** (mediana de 20 sesiones de precio × volumen hasta t): disponible en todos los días con precio.
  **Rotación** (liquidez / capitalización): evaluable donde hay capitalización.

## 5. Distribución del Flow (días completos, sin evento, desde el inicio de señales)

| | S&P 500 | S&P 400 | S&P 600 |
|---|---|---|---|
| Días-valor | 1 095 621 | 867 545 | 1 010 566 |
| % con Flow < 0 | 36,5 % | 39,9 % | 43,6 % |
| Percentil 1 / 2,5 / 5 / 10 | −33,6 / −24,5 / −18,3 / −12,5 | −40,1 / −29,3 / −22,1 / −15,3 | −48,4 / −34,9 / −26,4 / −18,5 |
| Mediana | +4,1 | +3,3 | +2,4 |
| Episodios bajo −10 / −20 / −30 | 17 587 / 8 126 / 3 173 | 15 402 / 8 466 / 3 853 | 19 096 / 12 269 / 6 369 |

Como se esperaba, los extremos son más frecuentes cuanto más pequeña es la empresa: el mismo −30 es percentil ~1 en
grandes y ~4 en pequeñas. De ahí que se midan también percentiles.

**Población operable** (precio ≥ 3 $ y liquidez ≥ 1 M$/día): % de días con Flow negativo que el filtro elimina.

| Franja | S&P 500 | S&P 400 | S&P 600 |
|---|---|---|---|
| [−5, 0) | 0,0 % | 0,1 % | 0,7 % |
| [−15, −10) | 0,0 % | 0,3 % | 1,2 % |
| [−30, −20) | 0,0 % | 0,6 % | 2,4 % |
| < −30 | 0,1 % | 2,0 % | **7,6 %** |

El filtro solo pesa en el extremo de las pequeñas, justo donde la población descriptiva y la operable pueden diferir.

## 6. Diagnóstico de H1 (fragmentación de celdas)

Población: días con Flow < 0, completo y sin evento, periodo de desarrollo (`data/h1_design.json`).

| | S&P 500 | S&P 400 | S&P 600 |
|---|---|---|---|
| Observaciones | 127 444 | 112 074 | 193 006 |
| Observaciones por día (mediana) | 129 | 122 | 233 |
| **10 × 10 por día**: tamaño mediano de celda | 1 | 1 | 2 |
| 10 × 10: % de observaciones en celdas < 10 | 95 % | 97 % | 91 % |
| **5 × 5 por día**: tamaño mediano | 5 | 5 | 9 |
| 5 × 5: % de observaciones en celdas < 10 | 49 % | 56 % | 27 % |
| **5 × 5 con cortes fijos de desarrollo y agrupando un mes**: % de celdas ≥ 30 obs. | 85 % | 84 % | 94 % |
| Ídem: % de observaciones en celdas ≥ 30 | 98,4 % | 98,0 % | 99,6 % |
| Valores distintos del resto R | 24 | 24 | 25 |
| Varianza de R explicada por los retornos de 5 y 21 sesiones | 22 % | 26 % | 26 % |
| Desviación típica de R tras descontar esos retornos | 1,9 | 1,9 | 1,9 |

- Tu advertencia era correcta: 10 × 10 por día deja una o dos empresas por celda y la comparación quedaría dominada
  por casos sueltos. Incluso 5 × 5 por día deja la mitad de las observaciones en celdas de menos de 10.
- **Diseño elegido:** cortes 5 × 5 de los retornos de 5 y 21 sesiones fijados una vez en desarrollo, y celdas de un
  mes natural, con un mínimo de 30 observaciones. Con eso el 98-99,6 % de las observaciones queda en celdas
  válidas. Se completa con una comparación fuera de muestra entre un modelo solo de retornos y otro con R.
  Especificación completa en el preregistro v2, §6.
- R tiene variación propia: los retornos previos solo explican una cuarta parte. Hay algo que medir. R es discreto
  (24-25 valores), por eso se usan tercios dentro de la celda, no una escala continua.
- Recordatorio de lenguaje: R son transformaciones del precio y, en parte, del volumen (RSI, MACD, ATR, Koncorde,
  distancia al máximo), no flujos de capital. Si aporta algo, la conclusión será «contiene información adicional a
  los dos retornos», no «hay acumulación institucional».

## 7. Resumen de puertas de calidad

| # | Puerta | Resultado | Qué queda |
|---|---|---|---|
| 1 | Composición ≥ 95 % por año | S&P 500 sí. **S&P 400 no en 2016, 2018, 2019 y 2020** (86,7-94,0 % por empresa). **S&P 600 2020-2021 sin ancla** (83,7 % / 96,5 % frente a las listas de Wikipedia) | Decisión 1 y 2 abajo |
| 2 | Precios ≥ 95 % de días-miembro por índice y año | Sí en todos los años con Flow completo (≥ 98,5 %). S&P 400 2016: 94,5 % (año sin Flow completo) | Los huecos son sobre todo composición desactualizada |
| 3 | Paridad Alpaca vs Yahoo (mediana ≤ 0,5; p90 ≤ 2) | Sí (0,0 / 0,0) | 4,3 % de filas con diferencia > 2 |
| 4 | Paridad con producción (≤ 0,01) | Sí (0,00 en 3 000 filas) | — |
| 5 | Capitalización ≥ 80 % por índice y año | Sí (83-93 %) | 2,2 % de series con saltos residuales; varias clases 0-0,2 % |
| 6 | Desenlaces cuantificados | Sí: afectan como máximo al 0,11 % de los episodios | Valor desconocido en todas las salidas de 2016-2019 |
| 7 | Flow completo en todo el periodo de señales | **No: solo desde el 29-dic-2017** | Decisión 3 abajo |
| 8 | Identidad (tickers reutilizados, quiebras con reaparición) | Sí, tras la corrección por épocas | Escisiones no registradas en S&P 400/600 antes de 2020 |

### Decisiones que necesito antes de congelar (no he cambiado nada por mi cuenta)

1. **Periodo de grandes y medianas.** Con Alpaca como fuente única, el Flow completo empieza el 29-dic-2017.
   - **Recomendada:** señales desde el 2-ene-2018. Desarrollo 2018-2020 (incluye el cuarto trimestre de 2018 y el
     desplome de 2020) y prueba 2021-2026.
   - Alternativa: incluir 2016-2017 con el Flow sin su parte semanal, como sensibilidad aparte. No se parece al Flow
     de producción.
   - Alternativa descartada: usar Yahoo para el calentamiento. Rompe la fuente única y solo tiene supervivientes.
2. **S&P 400 en desarrollo (2018-2020).** La composición tiene un error del 6-12 %.
   - **Recomendada:** mantenerlo con la advertencia explícita. Sus celdas solo pueden pasar a la etapa 2 si el mismo
     signo aparece en el S&P 500 o en el 600 en desarrollo. Su prueba (2021-2026) ya tiene coherencia ≥ 95,6 %.
   - Alternativa: sacarlo de la etapa 1 y evaluarlo solo en H1 en prueba.
3. **S&P 600 en 2020.** Composición reconstruida hacia atrás sin ancla, con un 84-96 % de coincidencia.
   - **Recomendada:** mantener el desarrollo 2020-2022 y añadir una sensibilidad sin 2020.
   - Alternativa: desarrollo 2021-2022 (solo dos años).
