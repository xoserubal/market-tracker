# VP2 — Perfiles de volumen históricos y su evolución entre sesiones

Fecha: 2026-11-22. Autorización: aprobación del usuario del 2026-11-22 (cálculo histórico con barras de 1 minuto y
reparto triangular).

**Descriptivo.** Estudia cómo se distribuye la negociación por precio y cómo cambia de una sesión a otra. No genera
alertas, no predice nada y no atribuye ninguna concentración a acumulación o distribución.

**Código y datos:**
- Código: `micro/vp_store.py`, `micro/vp_windows.py`, `micro/vp_observed.py`, `micro/heavy_lock.py`, `vp_build.py`,
  `vp_study.py` y `lab/profiles.html` + `profiles.js`.
- Pruebas: `test_vp_store.py` (5), `test_vp_windows.py` (3) y `test_vp_observed.py` (2).
- Datos: `MICRO_DATA_DIR/features/vp_profiles/` (estimados), `features/vp_profiles_observed/` (observados) y
  `results/vp2/`.

## 1. Tabla histórica de perfiles

**Definición** (`vp_store.PARAMS`, versión `vp2-1`; el hash `9486fe37c1d746ce` va en cada fila):
- **Fuente** `estimated_bars_1m_ex_auction`: barras de 1 minuto de la sesión regular [apertura, cierre).
  - Excluye la subasta de cierre, que se imprime a las 16:00.
  - La de apertura no puede separarse con barras y va dentro de la barra de las 09:30.
  - Los minutos con solo lotes impares no tienen barra en Alpaca y su volumen falta (§5).
- **Reparto:** triangular centrado en el VWAP de cada barra, dentro de [mínimo, máximo].
- **Perfil base:** en precio sin ajustar y en una rejilla fina (máx(tick, 0,025 % del precio de referencia del día)).
  - De él se derivan la rejilla canónica del día y la rejilla común de cada comparación, repartiendo por solape de
    intervalos.
  - Por eso un cambio de rejilla no crea desplazamientos (prueba `test_rebin_no_artificial_shift`).
- **Rejilla canónica:** 0,10 % del precio de referencia del día, nunca menor que el tick efectivo (0,01 $; 0,0001 $
  por debajo de 1 $).
- **Barras originales:** no se tocan.

**Cobertura** (nada del periodo reservado de G2A):

| Periodo | Días | Valores | Valor-días | Identidad |
|---|---|---:|---:|---|
| Histórico | 2016-01-04 → 2021-10-28 | 655 símbolos de 629 entidades | 759 822 | plan de E2: S&P 500 con pertenencia verificada, símbolo de cada día del nivel A, splits validados |
| Reciente | 2026-09-15 → 2026-11-20 | 616 símbolos de 613 emisores | 30 172 | universo actual de E3; emisor = CIK del registro U1 (113 sin CIK, como `T:SÍMBOLO`) |

**Controles de integridad** (`py -3 vp_build.py verify`, `results/vp2/verify.json`):
- **Volumen:** en el 100 % de las 789 994 filas el volumen del perfil es igual al de las barras de la sesión regular.
- **Periodo reservado:** 0 fechas.
- **Estadísticas:** todas calculadas.
- **Versiones:** un solo conjunto de parámetros y una sola versión.
- **Recálculo independiente:** 8 entidades elegidas al azar salen idénticas byte a byte (niveles, volúmenes, POC y
  área de valor).
- **Barras recortadas:** 5, todas con un rango absurdo (> 2 000 niveles); su volumen va al nivel del VWAP.
- **Marcas conservadas, no corregidas:**
  - 6 113 días con menos del 50 % de minutos con barra;
  - 249 días con un evento corporativo no reconstruido;
  - 59 días de split;
  - 1 014 días de caída de datos.

**Rendimiento y almacenamiento:**
- **Histórico:** 57 minutos con 4 procesos, a unos 6 s por entidad; 477 MB.
- **Reciente:** 33 minutos con un proceso (lee una unidad diaria por día); 40 MB.
- **Ventanas:** una de 60 sesiones con la matriz para el laboratorio tarda ~0,4 s.

**Estadísticas de cada día** (rejilla canónica):
- POC y área de valor del 70 %;
- zona del 90 %, en segmentos contiguos (nunca como banda continua si no lo es);
- planitud: cuota del nivel máximo y de los 3 mayores, entropía normalizada y fracción de niveles para el 50 %;
- prominencia del POC;
- confianza del POC: alta, media o baja;
- picos separados: máximos ≥ 50 % del máximo con un valle ≤ 70 % del pico menor.

Reparto en el histórico (el reciente, entre paréntesis):
- confianza alta 68 % (63 %), media 17 % (20 %), baja 15 % (17 %);
- zona del 90 % partida en ≥ 2 segmentos: 15 % (17 %);
- ≥ 2 picos separados: 49 % (55 %);
- cuota mediana del nivel máximo: 17 % (14 %).

**Aviso sobre la confianza.** En NVDA (2026-11-12), el perfil estimado da confianza alta y el observado con trades,
baja (perfil plano). El POC estimado está a un nivel del verdadero, con el 96 % de su volumen. **En valores muy
líquidos, la confianza calculada con barras puede sobrestimarse.**

## 2. Laboratorio

`py -3 lab/server.py` → http://127.0.0.1:8765/profiles.html (enlazado desde la portada y desde el acceso libre).
- **Cualquier valor del índice y cualquier fecha final:** ventana de 5, 10, 20, 40 o 60 sesiones; no necesita alertas.
- **Mapa de calor tiempo × precio:**
  - volumen por nivel, normalizado por día o absoluto (escala logarítmica);
  - POC de cada día, hueco si la confianza es baja;
  - área de valor, cierre y rango;
  - perfil compuesto a la derecha;
  - persistencia nivel a nivel (fracción de días dentro del área de valor de su día).
- **Fuente, versión, escala de precios y marcas de calidad:** siempre visibles. Se señalan las sesiones sin perfil y
  si existe un perfil observado con trades.
- **Profundizar:** pulsar una columna, o el enlace de cada día, abre esa sesión en el acceso libre, que descarga trades
  y quotes bajo demanda con coste y confirmación. `POST /api/vp/observed` calcula el perfil observado de ese día.
- **Comprobado** en Edge sin interfaz con HSIC 2019, NVDA 2026, CMG 2018, TECH 2026 y AVGO 2020: el gráfico, el
  resumen y la tabla diaria se muestran correctamente, sin errores propios.

## 3. Comparaciones entre sesiones (`micro/vp_windows.py`, `vp_study.py`)

**Escala común en cada ventana:**
- precios en la escala del último día, con los splits validados; el volumen en acciones, dividido por el mismo factor;
- una sola rejilla del 0,10 % del precio del último día;
- los eventos que no se pueden reconstruir se señalan y no se corrigen.

**Desplazamiento material del POC:** al menos 2 niveles (≈ 0,2 %), fuera de la zona del 90 % del día anterior y
viceversa, y ninguno de los dos días con confianza baja. Lo demás son casi empates o movimientos de un nivel y no se
suman como migración.

**Muestra (fijada antes):**
- 200 entidades al azar del histórico, con una fecha final cada 60 sesiones;
- todos los valores recientes, con fecha final el 20-nov;
- en total, 21 518 ventanas; 20 587 sin marcas.

**Resultados** (medianas, ventanas sin marcas; recientes entre paréntesis):

| Ventana | Jaccard del área de valor entre días | Diferencia de perfiles entre días (variación total) | Desplazamientos materiales por sesión | Neto del POC, \|pb\| (p10-p90) | Persistencia máxima en el área de valor diaria | Compuesto con ≥ 2 segmentos |
|---|---:|---:|---:|---|---:|---:|
| 5 | 0,18 (0,12) | 0,72 (0,77) | 0,75 (0,50) | 171 (30-515) | 60 % (40 %) | 28 % (31 %) |
| 10 | 0,18 (0,15) | 0,71 (0,74) | 0,67 (0,67) | 288 (50-865) | 40 % (40 %) | 32 % (39 %) |
| 20 | 0,18 (0,14) | 0,71 (0,77) | 0,63 (0,63) | 434 (80-1 210) | 30 % (25 %) | 38 % (48 %) |
| 40 | 0,18 (0,15) | 0,72 (0,75) | 0,64 (0,64) | 641 (119-1 783) | 20 % (18 %) | 45 % (49 %) |
| 60 | 0,18 | 0,72 | 0,64 | 779 (151-2 110) | 17 % | 48 % |

Lectura descriptiva:
1. **El perfil diario se desplaza con el precio.** De un día a otro el área de valor casi no se solapa (Jaccard
   ~0,18) y el POC se mueve de forma material en unas dos de cada tres sesiones. La negociación diaria se concentra en
   una banda estrecha (unos 50-100 pb), y el precio se mueve más que eso.
2. **Apenas hay niveles persistentes.** El nivel que más se repite dentro del área de valor diaria lo hace en el 30 %
   de las sesiones de una ventana de 20, y en el 17 % de una de 60.
   - Con la zona del 90 %, la mediana de concentraciones persistentes (≥ 50 % de los días) es 0 en todas las ventanas.
   - La persistencia por área de valor se añadió **después de ver** ese resultado; la original se conserva. No he
     seguido bajando umbrales hasta que apareciera algo.
3. **El perfil compuesto se vuelve multimodal al alargar la ventana:** su zona del 90 % está partida en el 28 % de las
   ventanas de 5 sesiones y en el 48 % de las de 60. Por eso un único «POC de 60 sesiones» suele ser poco informativo
   (confianza baja en el 49 % de ellas).
4. **El periodo reciente** muestra áreas de valor más anchas al final que al principio (×1,9-2,3 frente a ×1,0 en el
   histórico) y netos mayores: es un periodo de más movimiento (NVDA −45 % y MU −33 % en 20-40 sesiones).
5. **La coherencia de dirección ponderada por tamaño engaña** cuando hay un hueco grande (ver CMG en §4). Se añadieron
   el mayor desplazamiento individual y la fracción de desplazamientos en el mismo sentido, contada por número.

## 4. Casos representativos (`results/vp2/cases.json`)

Las reglas se fijaron en `vp_study.py` antes de ver resultados. Dos categorías se añadieron después, declaradas como
tales, porque las originales quedaron vacías o eligieron un caso equivocado. Se abren con
`profiles.html?symbol=…&end=…&n=20`.

| Categoría | Caso | Lo que se ve |
|---|---|---|
| POC estable (regla original, 40 sesiones) | — | **Ninguno**: exige una concentración persistente en la zona del 90 %, que casi no existe (§3.2) |
| POC más estable de la muestra (posterior) | **TECH, 20 sesiones hasta 2026-11-20** | Neto 10 pb, 0 desplazamientos materiales, área de valor de 19 pb, compuesto de confianza alta con el 41 % del volumen en un nivel (72,70 $). **No es un patrón de negociación:** Bio-Techne tiene una fusión pendiente (DEFM14A en agosto, votación de accionistas el 23-sep), y el precio está anclado al de la oferta |
| ídem | AEE, 20 sesiones hasta 2019-07-31 | Neto −95 pb; nivel dentro del área de valor diaria el 70 % de las sesiones |
| Migración (regla original) | CMG, 20 sesiones hasta 2018-05-21 (desde el 24-abr) | **Ejemplo de lo que la regla confunde:** un único salto de +19 % el día de resultados (26-abr) y después un rango lateral. La coherencia ponderada (0,88) la domina ese hueco |
| ídem, a la baja | MU, 20 sesiones hasta 2026-11-20 | −33 % con 7 desplazamientos materiales; el mayor, 2 096 pb |
| Migración repartida al alza (posterior) | **AVGO, 20 sesiones hasta 2020-04-17 (desde el 20-mar)** | +32 %, el POC sube por escalones; 4 desplazamientos materiales, todos al alza, el mayor un 40 % del neto. Varios días de salto grande tienen confianza baja y no cuentan |
| Migración repartida a la baja (posterior) | APH, 20 sesiones hasta 2026-11-20 | −6 %; 10 desplazamientos materiales, el 70 % a la baja |
| Expansión del área de valor | UVXY, 20 sesiones hasta 2026-11-20 | Anchura de 107 a 1 365 pb con +70 % de precio |
| Contracción del área de valor | COO, 20 sesiones hasta 2018-05-21 | Anchura de 549 a 51 pb con un rango del 7 % |

## 5. Cobertura, calidad y limitaciones

**La discrepancia de 2016-2017 era un fallo nuestro, ya corregido.** `episode.load_trades` quitaba como duplicadas
operaciones legítimas con distinto identificador: en KSS 2017-05-10, 7 580 de 47 382.
- Con la corrección, los trades suman exactamente lo mismo que las barras (KSS: 6 547 164 = 6 547 164).
- G2A no usaba ese cargador. Las fichas de E1 y los casos de G1.5 (días recientes) no cambian.
- VP1 repetido: mismas conclusiones (POC igual 82 %).

**Lotes impares sin barra:** en valores poco líquidos, los minutos con solo lotes impares no tienen barra y su volumen
falta del perfil estimado. En GL (2026-11-20) es un 5 %; donde hay barra, el volumen coincide exactamente.

**Perfiles observados, separados:**
- `micro/vp_observed.py` lee los trades por lotes de 500 000 filas y acumula por nivel. NVDA (9,6 M de trades) se
  procesa en 102 s con un pico de 458 MB.
- Se guardan aparte (`observed_trades_ex_close_auction`), con la subasta de cierre en columnas propias y marcando si
  cubren toda la sesión. No sustituyen ni modifican el perfil estimado.

**Emisores con varias clases:**
- En el histórico, G1 asigna una sola clase por emisor (GOOG y no GOOGL; FOX, NWSA).
- En el reciente están todas, porque el fichero se nombra por emisor + símbolo. Un primer cálculo sobrescribía una
  clase con otra; se detectó y se corrigió.

**Identidad estable pendiente:** las 113 entidades recientes sin CIK (`T:SÍMBOLO`); ver `U1_INFORME.md` §6.

**Ventanas largas en el periodo reciente:** tiene 49 sesiones, así que no hay ventanas de 60. No se cruza el periodo
reservado: una ventana nunca une el histórico y el reciente.

**Umbrales sin calibrar:** confianza, picos, persistencia, desplazamiento material de 2 niveles. Son definiciones
descriptivas fijadas a priori. Las dos categorías de casos añadidas después lo indican.

**Subasta de apertura y cierres anticipados:** la de apertura no se puede separar con barras. Los días de cierre
anticipado tienen sesión regular más corta; no se marcan aparte en el perfil.

## 6. E3 durante este trabajo

- **Cerrojo de procesos intensivos** (`micro/heavy_lock.py`): el piloto no arranca una jornada mientras corre un cálculo
  pesado (lo reintenta en el siguiente disparo), y los cálculos de VP2 no arrancan si hay una pasada E3 en marcha.
  Ningún cálculo de VP2 ha coincidido con el piloto: la primera jornada se procesa el 24-nov a las 3:40.
- **Sesión reducida del 27-nov:**
  - El calendario es correcto: cierre a las 13:00 y after hours hasta las 17:00.
  - La comprobación de cobertura daba falsos avisos de «cobertura baja» en casi todos los valores. Ahora escala lo
    esperado por la duración de la sesión del día.
  - Probado con el 27-nov-2020: 0 valores con cobertura baja y ningún aviso de caída general.
