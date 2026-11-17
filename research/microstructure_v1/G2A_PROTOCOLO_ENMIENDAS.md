# Enmiendas al protocolo de G2A

`G2A_PROTOCOLO.md` no se modifica: su SHA-256 `07b7af6d…` sigue valiendo. Las correcciones van aquí, fechadas, con su
motivo. Esta lista se congela con su propio hash (`G2A_PROTOCOLO_ENMIENDAS.sha256`) y se vuelve a congelar en cada
enmienda nueva.

Todas las de esta tanda se hicieron **antes de calcular ninguna variable candidata ni ningún resultado**. Salieron al
escribir el código de las variables. Ninguna cambia una hipótesis, una rejilla, una puerta ni un criterio.

## Enmienda 1 (2026-11-16) — historia mínima de minutos: 260 sesiones, no 140

- **Error:** §2 pide 140 sesiones de barras de 1 minuto, pero las fórmulas de §3 necesitan más. El componente C3
  necesita 20 sesiones de anomalía, cada una normalizada con las 120 previas (140). Después, el propio C3 se expresa
  como percentil frente a sus 120 valores previos.
- **Total:** 140 + 120 = **260 sesiones** de minutos antes de t. Lo mismo vale para C1 con L = 120 (120 + 120 = 240,
  menos que 260).
- **Corrección:** historia mínima = 260 sesiones de minutos y 252 diarias.
- **Efecto previsto:**
  - Las primeras ~8 sesiones de 2017 no tienen índice: el nivel A empieza el 2016-01-04, y 260 sesiones llevan al
    2017-01-12.
  - Tampoco lo tienen las primeras ~8 sesiones de cada valor que entra en el índice, porque el nivel A trae 252 previas.
  - Se cuenta en el informe de cobertura.
- **Exclusiones de prueba:** la ventana hacia atrás de las variables pasa de 140 a 260 sesiones. No cambia nada,
  porque todas las exposiciones que excluyen son posteriores a la prueba; solo cuenta la ventana hacia delante, de 40.

## Enmienda 2 (2026-11-16) — fuerza relativa sectorial sin ETF

- **Hueco:** XLC no existe hasta el 2018-06-19, y el sector de comunicaciones anterior (telecomunicaciones) no tiene
  ETF SPDR en el periodo.
- **Regla:** cuando el sector del valor no tiene ETF en t, la fuerza relativa sectorial se sustituye por la fuerza
  relativa frente al SPY.
- **Motivo:** así esos valores no se pierden en la regresión de referencia de H-A1. Se cuenta cuántas observaciones
  usan la sustitución.

## Enmienda 3 (2026-11-16) — distancia de Mahalanobis de los controles

- **Hueco:** §3 no decía de dónde sale la covarianza.
- **Regla:** sale de la población elegible de desarrollo de la combinación, toda junta, y se calcula una vez antes de
  emparejar.
- No se usa ningún resultado.

## Enmienda 4 (2026-11-16) — aclaraciones de cálculo, sin cambio de fórmula

1. **Recorrido intradía:** `Σ |c_m − c_{m−1}|` toma como c_0 la apertura del primer minuto, así que ER ≤ 1.
2. **Sesión regular:** minutos con inicio en [apertura, cierre) del calendario oficial. La subasta de apertura está en
   el minuto de las 9:30.
   - La subasta de cierre (16:00:00) cae en la barra de las 16:00, junto con operaciones de después del cierre, y
     no se puede separar con barras de 1 minuto.
   - Por eso queda fuera del volumen por precio y de ER.
   - Los volúmenes diarios (RV) salen de la barra diaria oficial, que sí la incluye.
   - Es parte de la aproximación declarada del nivel A frente a los ticks.
3. **Días sin negociación:** los días con volumen 0 dentro de la época de identidad (suspensiones) se quitan de la
   serie del valor, como si no fueran sesión. Las ventanas cuentan sesiones con negociación de ese valor.
4. **Splits (equivalencia):** se usa la serie ajustada hacia atrás con todos sus splits.
   - Todas las variables son cocientes dentro de una ventana: rangos/ATR, percentiles, posiciones en el rango,
     anchuras en logaritmo, volúmenes relativos.
   - Un split posterior a t multiplica todos los días ≤ t por la misma constante y deja esos cocientes iguales.
   - Así, el resultado es idéntico a ajustar solo con los splits ≤ t, como pide §2. Una prueba lo comprueba.
   - Los saltos sin split explicativo siguen invalidando las observaciones afectadas.
5. **Percentil frente a la historia propia:** `pct_N(x_t) = (nº de previos < x_t + 0,5 · nº de previos = x_t) / N`
   sobre los N valores inmediatamente anteriores. Si alguno falta, el percentil queda vacío y la observación no se
   usa.

## Enmienda 6 (2026-11-16) — salidas sin datos de fusión en Alpaca (2016-2019)

- **Hallazgo** al descargar las acciones corporativas (`g2a_reference.py`):
  - Alpaca solo registra fusiones desde 2020. Antes no hay ninguna: faltan MON, TWX, CELG y el resto.
  - Splits y dividendos sí cubren 2016-2026, con unos 2 000 dividendos y entre 8 y 21 splits por año.
- **Alcance:** de los 62 valores que dejan de cotizar con último dato ≤ 2021, 50 no tienen fusión en Alpaca. Según la
  tabla de cambios del S&P 500 (Wikipedia), los 50 son **adquisiciones**; ninguno es una quiebra.
  - En el contraste confirmatorio (2022-2026) Alpaca sí tiene las fusiones; CTXS además está verificada con su 8-K.
- **Regla**, fijada sin mirar ningún resultado:
  - Una salida sin fusión en Alpaca que la tabla de cambios identifique como adquisición se liquida al último cierre,
    con rentabilidad 0 el resto del horizonte. Es la regla de «fusión en efectivo» con el precio de mercado como
    precio de la operación: el arbitraje de fusión ya está cerrado el último día.
  - En las adquisiciones pagadas en acciones esto ignora la evolución del comprador en las sesiones que faltan. Es un
    ruido de media cero sobre una fracción pequeña de la observación.
  - MON usa su precio verificado (128 $, 8-K).
- **Peso:** a lo sumo 40 fechas de decisión por valor (las que tienen la salida dentro de su horizonte), unas 2 000
  valor-días de ~600 000 en desarrollo (~0,3 %). Se informa el número exacto.
- **Sensibilidad:** se repite todo excluyendo esas observaciones.

## Enmienda 7 (2026-11-16) — escisiones, splits incoherentes y rupturas de identidad

Hecha **antes de calcular ninguna variable candidata ni ningún resultado**, al pasar la comprobación de cobertura del
§8. Solo usa acciones corporativas, listas de cambios de índices y precios en la fecha del evento.

- **Hallazgos:**
  - Alpaca casi no registra escisiones antes de 2020: de 2016 a 2021 solo VAR→VREX y GE→WAB. Faltan Danaher→Fortive,
    DowDuPont→Dow/Corteva, Honeywell→Garrett/Resideo, UTX→Carrier/Otis, Wyndham→WH y unas 30 más. Una escisión resta
    del precio el valor de la filial (TEGNA −37 %, Aptiv −51 %, Aimco −86 % en la apertura); sin tratarla, la ventana
    de resultado que la contiene registra una pérdida que no existió.
  - Alpaca codifica a veces el ratio de reparto de una escisión como un split de la matriz (TEGNA 1:3, EQT 0,8,
    Aptiv 1:3, Arconic 1:3 y 0,25, UTX 0,5). Aplicado como split, mete un salto falso de hasta ×4.
  - Los splits van por símbolo: el canje «IR 0,8824» (2020-03-02) se aplicaba también a Gardner Denver, que ese día
    pasó a llamarse IR y no tuvo ningún split.
  - Tramos de emisor equivocado: la referencia diaria (`g2a_reference.py`, deduplicación `keep="first"`) y el plan
    del nivel A de G1 sirven algunas fechas con la prolongación de 90 días de un tramo anterior cuando otro tramo de
    la misma entidad las cubre. Si la filial heredó el ticker, la matriz lleva precios de la filial: Arconic con la
    nueva Alcoa (nov-2016 a ene-2017) y con la nueva Arconic Corp. (abr-jun 2020), Aptiv con Delphi Technologies
    (dic-2017 a abr-2018). Afecta tanto a las barras diarias como a las de minuto.
  - La entidad 1666700 encadena E. I. du Pont y DowDuPont sin el canje de 1,282 (salto falso de 0,80 el 2017-09-01).
  - Los dividendos extraordinarios no vienen marcados: el de Dr Pepper Snapple (103,75 $, 84 % del precio) lleva
    `special=False`.
- **Regla de splits:** un registro de split se aplica solo si explica el cociente de precios en bruto de su fecha
  mejor que la hipótesis «no hubo split» y con |ln(cociente · factor)| ≤ 0,15. Con eso se conservan los ajustes de
  valor bien codificados (DWDP 1,487, Hilton, Trane, ConAgra, Aimco). Resultado: 130 aplicados, 20 incoherentes,
  20 fuera de las barras de la entidad.
- **Eventos** (`micro/distributions.py`, `g2a_events.py`):
  - **E1, reparto:** escisión de Alpaca; escisión de la lista curada `distribution_events_dev.csv` (41, con fuente y
    fecha ex comprobada por el hueco de apertura; fuentes: Wikipedia «Historical components of the S&P 500», listas
    del S&P 400 y 600, y conocimiento propio marcado como tal); dividendo en efectivo ≥ 10 % del cierre previo.
  - **E2:** registro de split incoherente (no se aplica).
  - **E3, ruptura de identidad:** cambio de tramo de petición (símbolo o asof) con |ln salto| > 0,10 que no explica
    un split aplicado, o hueco de más de 10 días naturales en la serie de la entidad.
- **Exclusión:** un valor-día (e, t) queda fuera si algún evento de e cae en [t − 259, t + 40] sesiones (ventana de
  variables de 260 sesiones y horizonte de 40). Un tramo de emisor equivocado queda siempre fuera porque sus dos
  bordes son eventos. La regla es la misma en desarrollo y en prueba; la lista de eventos de 2022-2026 se construye y
  se congela antes del contraste confirmatorio, con las mismas fuentes.
- **Aclaración de la enmienda 4.4:** «salto sin split explicativo» pasa a ser un salto (×2 o ×0,5) sin split aplicado
  y sin evento a ≤ 3 sesiones. En desarrollo, dentro del S&P 500, quedan tres, todos caídas reales del mercado:
  PG&E (2019-01-14, anuncio de quiebra), APA y OXY (2020-03-09, guerra de precios del petróleo).
  - Se conservan en el análisis principal, porque quitarlos borraría caídas reales.
  - Una sensibilidad los excluye con la misma ventana (`near_genuine_jump`).
- **Peso:** 9 541 valor-días miembro de desarrollo excluidos (1,6 %): escisiones curadas 7 548, splits incoherentes
  2 801, cambios de tramo 1 668, escisiones de Alpaca 1 157, dividendos grandes 568, huecos 260 (se solapan). Queda
  usable el 96,9 % de la muestra de desarrollo.
- **Riesgo residual:** una escisión que no recoja ninguna fuente sigue sin tratar. Por debajo de ~5 % del precio no
  se distingue de un día normal por el hueco de apertura. Se informa de que existe; no se puede medir.

### Corrección de datos asociada (no cambia el protocolo)

`g2a_intraday_daily.py` asignaba cada día de una unidad del nivel A a una sola entidad (un diccionario indexado por
fecha). Cuando la unidad servía a dos entidades el mismo día (el CIK del S&P 500 y el ticker «T:» del proyecto), solo
quedaba la última. Así se perdían casi por completo 33 valores del S&P 500, entre ellos NVDA, JNJ, UNH y CAT.
- Corregido con una unión de uno a varios.
- Los 70 meses ya calculados se repararon con `g2a_intraday_repair.py` (+45 885 días).
- El mes 2018-06, recalculado desde cero con el código corregido, coincide celda a celda con el reparado.
- Tras la corrección, la cobertura intradía pasa del 93,6 % al 99,8 % y las 6 puertas del §8 se cumplen.

## Enmienda 8 (2026-11-16) — días de caída de datos de 1 minuto

Hecha **antes de calcular ningún resultado**, al revisar la cobertura de las variables (exploración descriptiva).

- **Hallazgo:** el 2021-04-19 y el 2021-10-25 fueron sesiones normales, pero en Alpaca unos dos tercios de los
  valores del S&P 500 solo tienen la barra de la subasta de apertura. La cobertura del §8 los contaba como «con
  intradía», aunque su ER y su volumen por precio no valen.
- **Efecto sin corregir:** por la enmienda 4.5, cada uno anula el percentil intradía de las 120 sesiones siguientes;
  la variante intradía de la familia A perdía el 8 % del universo, casi todo 2021.
- **Regla** (`g2a_outages.py`): un día es caída de datos si no es media sesión del calendario oficial y más del 20 %
  de los miembros tiene menos de la mitad de su mediana de barras de minuto de las 60 sesiones previas.
  - Salen exactamente esos dos días.
  - Las medias sesiones (24 de diciembre, viernes de Acción de Gracias) superan el umbral, pero se descartan porque
    son medias sesiones del calendario.
- **Tratamiento:** para las variables intradía (ER y volumen por precio) esos días no son sesión, en la línea de la
  enmienda 4.3.
  - La mediana de ER y el percentil se calculan sobre las sesiones intradía válidas, y AWD intradía queda vacío ese día.
  - Su volumen por precio se descarta de las ventanas.
  - Las variables diarias no cambian.
  - Los huecos de un solo valor siguen la enmienda 4.5.
- **Efecto:** la variante intradía de A pasa del 91,9 % al 99,8 % del universo. Las 12 combinaciones de C apenas
  cambian (como mucho 4 episodios tratados), porque C solo usa AWD diario.
