# Estructuras de negociación A/B/C — documento de método

Fecha: 2026-11-22. Autorización: mensaje del usuario del 2026-11-22 («documento de método y pruebas de regresión
primero; después C y A con las reglas fijadas; B tras el piloto E3»).

**Qué es.** Un estudio **descriptivo** de tres estructuras de la negociación. No es un preregistro confirmatorio, pero
todas las reglas quedan escritas aquí **antes de calcular nada**. Cualquier cambio posterior se declara como tal y se
conserva la versión original.

No genera detectores ni alertas, no optimiza parámetros, no mide rentabilidades y no toca producción ni el periodo
reservado de G2A.

**Pregunta.** ¿Qué revelan estas estructuras que no esté ya en el precio (OHLC), el volumen y el VWAP? «Nada» es una
respuesta válida y se informará como tal.

## 1. Datos y versiones

| Fuente | Contenido | Uso |
|---|---|---|
| `features/vp_profiles/` | Versión `vp2-1`, hash `9486fe37c1d746ce`, fuente `estimated_bars_1m_ex_auction`. Por valor-día: o, h, l, c, vwap, bar_volume, POC, área de valor (70 %), zona del 90 % por segmentos, confianza del POC, picos y marcas (cobertura, evento corporativo, split, caída de datos). | C y A |
| `features/vp_profiles_observed/` y trades bajo demanda (acceso libre) | Perfiles observados con trades | Verificación de una submuestra de A y B |
| Trades y quotes (acceso libre, `micro/window_access.py`) | Clasificadores de agresor | Solo B |

**Periodos:**
- histórico: 2016-01-04 → 2021-10-28 (759 822 valor-días);
- reciente: 2026-09-15 → 2026-11-20 (30 172). Ninguna ventana une ambos periodos.

**Periodo reservado de G2A** (2021-10-29 → 2026-09-14): cerrado. Todo el código nuevo pasa por `micro/test_guard`.

**Código nuevo, en archivos propios:** `st_c_divergence.py`, `st_a_ranges.py` y, más adelante, `st_b_volume.py`.
- Mientras dure el piloto E3 no se modifica ningún archivo del manifiesto de `e3_integrity.py`: `micro/`, `tests/`,
  `catalog/`, `lab/`, `e3_*.py`.
- Los cálculos toman `micro/heavy_lock`, de modo que una jornada del piloto espera a que terminen. No se lanzan entre
  las 03:00 y las 06:00 (hora local del equipo del piloto).

## 2. Variables convencionales de referencia (obligatorias en las tres estructuras)

Se calculan con las mismas barras de la sesión regular que el perfil; la fila de `vp_profiles` ya las trae.

| Variable | Definición |
|---|---|
| OHLC | o, h, l, c de la sesión regular (sin subasta de cierre) |
| VWAP | `vwap` de la fila (media de los VWAP de las barras ponderada por volumen) |
| Posición del cierre | CLV = (c − l) / (h − l); sin definir si h = l |
| Rango relativo | RR = (h − l) / vwap |
| Volatilidad propia | D = mediana de RR en las 60 sesiones **anteriores** (mínimo 40) |
| Volumen relativo | RVOL = bar_volume / mediana de bar_volume en las 20 sesiones anteriores (mínimo 15) |
| Liquidez | mediana de bar_volume × vwap en las 60 sesiones anteriores |
| Distancias | en puntos básicos sobre el VWAP: d(c, POC) = (c − POC)/vwap × 10⁴; d(c, VWAP); d(POC, VWAP) |

Todas las ventanas de referencia usan solo sesiones anteriores al día estudiado y del mismo periodo.

## 3. Estratificación (común)

- **Liquidez:** terciles calculados dentro de cada periodo.
- **Volatilidad:** terciles de D dentro de cada periodo.
- **Periodo:** histórico o reciente.
- **Régimen:** SPY por encima o por debajo de su SMA de 200 sesiones al cierre anterior. Se usa en B y como
  descriptor en A y C.
- **Confianza del POC:** alta, media o baja.

Los valores-día con alguna marca de calidad (cobertura < 50 %, evento corporativo no reconstruido, split, caída de
datos) quedan fuera de los cálculos principales. Se cuentan aparte.

## 4. Estructura C — divergencias entre el precio y el perfil (un valor-día)

**C0, primer paso obligatorio: ¿es solo la diferencia entre el cierre y el VWAP?**
- En cada estrato, regresión de d(c, POC) sobre d(c, VWAP).
- Se informan R², pendiente y el residuo. El residuo es la parte de la divergencia propia del perfil.
- Si R² ≥ 0,9 en todos los estratos, se concluye que la divergencia POC–cierre es prácticamente la de VWAP–cierre.
  El resto de C se informa solo como confirmación.

**Definiciones de evento**, con POC de confianza alta o media y distancias de al menos 2 niveles de la rejilla
canónica (≈ 0,2 %). Es el margen que VP1 deja al error del POC estimado frente al observado.

| Evento | Regla |
|---|---|
| C1+ / C1− | Cierre por encima del límite superior del área de valor / por debajo del inferior |
| C2 (propia del perfil) | El POC y el VWAP quedan a lados opuestos del cierre |
| C3 | \|d(POC, VWAP)\| ≥ 2 niveles con el cierre entre ambos |

**Qué se describe, por estrato y en todos los valor-días:**
1. Frecuencia de cada evento.
2. Solape de C1 con «cierre a ≥ 2 niveles del VWAP», con CLV extremo (≥ 0,8 o ≤ 0,2) y con RVOL ≥ 2.
3. **Contenido secundario, descriptivo, sin rentabilidades:** ¿localiza el POC de hoy la negociación de la sesión
   siguiente mejor que el VWAP o el cierre de hoy?
   - Medida: distancia del POC de mañana a cada ancla de hoy y cuota del volumen de mañana dentro del área de valor
     de hoy.
   - Se compara en días con evento C2/C3 frente a días sin él.
   - Si el POC no mejora al VWAP, la estructura no añade información en este sentido.

**Incertidumbre:**
- Los días del mismo valor no son independientes: los intervalos se calculan por remuestreo de entidades (bootstrap
  por bloques de entidad, 2 000 réplicas, semilla 20261122).
- Para valores muy líquidos (tercil alto de liquidez) se informa aparte, porque VP2 vio que la confianza del POC con
  barras se sobrestima ahí.

**Casos ilustrados (unos 20):**
- Sorteo estratificado con semilla fija (20261122): entre los valor-días con C2 o C3, 5 por cada combinación periodo
  × {tercil bajo, tercil alto de liquidez}, más 2 por periodo de días sin evento, como contraste.
- La lista se guarda antes de abrir ninguno.
- Se excluyen del sorteo los valor-días ya vistos (§8).
- No se usa nada posterior al día del caso para elegirlo ni para descartarlo.

## 5. Estructura A — rangos laterales (ventanas de 10 sesiones)

**Definición** (fijada a priori; sin calibrar).
- Sea R la amplitud de la ventana = (máx h − mín l) / media del VWAP de sus 10 sesiones, y D la volatilidad propia de
  las 60 sesiones anteriores al primer día. La ventana es **rango lateral** si:
  - R ≤ 2,5 × D;
  - |c del último día − o del primero| / media del VWAP ≤ 0,5 × R;
  - las 10 sesiones están sin marcas.
- **Sensibilidad informada, sin elegir la mejor:** 2,0 × D y 3,0 × D; ventanas de 20 sesiones.

**Muestra:**
- 30 casos y 30 controles. Sorteo con semilla fija, estratificado por liquidez × volatilidad × periodo.
- Los casos no se solapan entre sí: dentro de un valor, una ventana nueva empieza después de que acabe la anterior.
- Controles: ventanas de 10 sesiones del mismo estrato que no cumplen la definición y no se solapan con ningún caso.
  Uno por caso; del mismo valor si existe, si no, de otro valor del mismo estrato.

**Operaciones corporativas:**
- Se estratifican, no se excluyen.
- Por cada caso y control se buscan en EDGAR presentaciones con **fecha de presentación ≤ último día de la ventana**:
  8-K con acuerdo de fusión, DEFM14A, PREM14A, SC TO-T, SC 14D9 y 425.
- Etiqueta: «operación pendiente pública», «sin operación conocida» o «sin CIK / no comprobable». Nunca «sin
  operación» a secas.
- No se usa información publicada después de la ventana.

**Qué se describe, frente a los controles:**
1. Concentración del perfil compuesto: cuota del nivel máximo, número de segmentos de la zona del 90 % y confianza.
2. Persistencia de niveles: fracción de sesiones con el nivel dentro de su área de valor diaria, con la definición de
   `vp_windows`.
3. ¿Coinciden los bordes del área de valor compuesta con los del rango por precio (mín l, máx h)? ¿Y el POC compuesto
   con el VWAP y el punto medio de la ventana? Si coinciden, el perfil no añade nada a la descripción por precio.

**Verificación con trades:** 6 casos y 6 controles del periodo reciente, por sorteo. Se calcula el perfil observado de
cada sesión (`micro/vp_observed`) y se compara su POC y su área de valor con los estimados.
- Coste con el estimador del acceso libre: dentro del tope de 6 000 peticiones en 24 h.
- Sin descargas en la ventana nocturna del piloto.

## 6. Estructura B — mucho volumen sin desplazamiento (después del piloto E3)

Solo se deja fijada la definición; no se calcula nada hasta que termine el piloto.
- **Unidad:** media hora de la sesión regular (13 por sesión, ancladas a la apertura).
- **Episodio:**
  - volumen ≥ 3 × la mediana del volumen de esa misma media hora en las 20 sesiones anteriores;
  - |cierre − apertura de la media hora| ≤ 0,25 × la mediana del movimiento absoluto de esa media hora en las mismas
    sesiones;
  - se excluyen la primera y la última media hora de la sesión (subastas).
- **Muestra:** unos 40 episodios por sorteo estratificado por liquidez × régimen × periodo.
- **Controles:** la misma media hora del mismo valor en otra sesión de las 20 anteriores, sin episodio. Dos por
  episodio.
- **Clasificadores** (`micro/aggressor`): tick, bid-ask y Lee-Ready. Se informan:
  - la concordancia entre métodos;
  - la cuota indeterminada;
  - la sensibilidad al desfase de la quote (0 y 1 s);
  - los resultados con y sin TRF.
- **Lo que no se hace:** no se da un delta comprador/vendedor único ni se interpreta como «absorción institucional».
  G1.5 ya mostró que el signo cambia según el método, el desfase y el tratamiento de los TRF.

## 7. Limitaciones conocidas de los datos

- **Perfil estimado:** sale de un reparto triangular de cada barra de 1 minuto, no de operaciones. El POC exacto en
  valores muy líquidos y los niveles finos requieren trades (VP1).
- **Lotes impares:** los minutos con solo lotes impares no tienen barra; en valores poco líquidos falta hasta un 5 %
  del volumen.
- **Subastas:** la de apertura queda dentro de la barra de las 09:30; la de cierre está excluida del perfil.
- **Varias clases por emisor:** en el histórico, una sola clase por emisor; en el reciente, todas. 113 emisores
  recientes no tienen CIK.
- **Periodo reciente corto:** 49 sesiones y un solo régimen de mucho movimiento. No permite ventanas de 60.
- **Umbrales sin calibrar:** todos los umbrales (2 niveles, 2,5 × D, 3 × volumen, 0,25 × movimiento) son
  definiciones a priori.
- **Corrección del cargador de trades (2026-11-22):** cualquier resultado anterior basado en trades de 2016-2017 con
  la carga antigua subestimaba el volumen (KSS 2017-05-10: 7 580 de 47 382 operaciones).
  - `loader_correction_diff.py` mide el efecto en los consumidores de G1.5 y E1, sin reescribir sus artefactos.
  - Las pruebas de regresión están en `tests_extra/test_load_trades_regression.py`.
- **Perfiles observados:** `micro/vp_observed.py` no usa `load_trades`. Evita el doble conteo entre unidades por tiempo,
  pero no quita las repeticiones con el mismo identificador. En días como NVDA 2020-11-27, la subasta de cierre puede
  contarse dos veces en `close_auction_shares`; el perfil no cambia porque la excluye. No se corrige durante el piloto.
- **Quotes:** `load_quotes` quita siempre las filas idénticas en tiempo y precios/tamaños, aunque vengan de una sola
  unidad. No cambia la quote vigente para clasificar; solo el recuento de quotes.
- **Estado del disco (2026-11-22):** el disco externo de datos muestra daños en el sistema de archivos (`chkdsk` en
  solo lectura). Nada de C, A ni B se calcula hasta comprobar que `vp_profiles` está completo: `vp_build.py verify`
  debe dar el mismo número de filas (789 994) y el hash de parámetros.

## 8. Registro de exposición previa

Lo que ya se ha mirado con detalle no es «muestra nueva». Las cifras agregadas lo incluyen. Los sorteos de casos
ilustrados lo excluyen.

| Trabajo | Qué se vio | Efecto aquí |
|---|---|---|
| G1.5 | NVDA 2026-11-12 y GOOGL 2026-10-29 con trades y quotes. Comparación de clasificadores en 20 bloques × 20 sesiones de `samples/quotes_plan_v1.parquet`, de desarrollo y prueba (uso técnico anotado en `library/test_period_usage.jsonl`). | Excluidos de los sorteos de B. Los bloques de prueba siguen cerrados. |
| E1 | Las 7 fichas de `fichas/` (NVDA 2020-11-27, NVDA 2026-11-12, GOOGL 2026-10-29, PLTR 2026-11-10 y 2026-11-17, SPY 2026-11-05, ADP 2026-11-20) | Excluidas de todos los sorteos |
| E2 / cat-v1 | Las 44 medidas de los 759 829 valor-días 2016-2021 y la calibración de cat-v1 (distribuciones, no casos) | Exposición distribucional del histórico entero: ningún resultado aquí cuenta como fuera de muestra |
| VP1 | 191 sesiones: parte A, 156 sesiones con trades ya descargados (dominada por 5 valores); parte B, 12 valores × 18-20 nov 2026 | Excluidas de los sorteos de A (verificación con trades) |
| VP2 | Estadísticas de toda la tabla. 21 518 ventanas (200 entidades al azar + todo el reciente). Casos: TECH, AEE, CMG, MU, AVGO, APH, UVXY y COO, más HSIC 2019 y NVDA 2026 en el laboratorio. | Esas ventanas (valor + fecha final) se excluyen de los sorteos de A y C. La lectura de VP2 (POC que se desplaza con el precio, poca persistencia) es conocida antes de empezar y condiciona las expectativas. |

El sorteo se registra en `results/estructuras/draws.json`, con la semilla, la lista excluida y la huella de la tabla
de perfiles, antes de abrir ningún caso.

## 9. Salida

**Informe:** `ESTRUCTURAS_INFORME.md`. Una sección por estructura con:
- lo que añade frente a las variables convencionales;
- lo que no añade;
- las limitaciones.

**Datos:** en `results/estructuras/`, nunca sobre artefactos congelados.

**Desviaciones:** cualquier desviación de este documento se lista al principio del informe.
