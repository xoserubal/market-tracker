# Preregistro — Flow Continuación y Flow Reversión con las reglas de la cartera sombra (v1)

**Firmado por el usuario el 2026-11-11 (v3) y congelado** (SHA-256 en `research/flow_cont_rev_v1/PREREGISTRO.sha256`).
Escrito el 2026-11-11, antes de calcular ningún resultado histórico de estos filtros. La v2 recoge tres correcciones
del usuario: la reproducibilidad pasa a ser condición previa (§4), el criterio económico se separa de la significación
(§6) y se audita la causalidad de la simulación con una versión operativa (§2-§3). En la v3, la versión operativa (B)
pasa a decidir el veredicto y la réplica de producción (A) queda como explicativa. No se ha calculado ninguna
rentabilidad histórica antes de la firma. Es independiente del estudio de amplitud
sectorial. Código: `research/flow_cont_rev_v1/`. No se toca producción.

**Origen.** El usuario observa en AI Picks Lab que las pestañas *Flow Continuación* y *Flow Reversión* de
`SCREENER_SHADOW` cierran más operaciones con beneficio. Revisión previa, solo con datos en vivo (9-oct → 11-nov-2026):
Continuación 48 % de aciertos y +0,3 % de media en 27 operaciones cerradas, frente a 35 % y −2,6 % de entradas al azar
con las mismas reglas y fechas (t 0,9); Reversión −1,5 % (t 0,7). Todos los filtros superan al azar en ese mes, la
mejor operación de ambos es la misma (TDOC) y el historial del Screener a 30 días es negativo. **Esa observación
motiva la hipótesis y no forma parte del contraste.**

## 1. Pregunta
¿Las entradas de Flow Continuación y de Flow Reversión, gestionadas con las reglas de salida de `SCREENER_SHADOW`,
rinden más que entrar en cualquier valor del mismo universo **el mismo día y con las mismas reglas**, por encima de
un mínimo con interés económico? Fuera de muestra.

**Qué se valida exactamente.** La regla aplicada con el dato de cierre de la propia sesión. Así funciona
`SCREENER_SHADOW` desde el 2026-11-10, cuando el pipeline pasó a lanzarse después del cierre (§4). **No** se valida
la historia de la cartera sombra anterior a esa fecha, que operó con datos de uno o dos días de retraso.

## 2. Reglas comunes (código de producción, sin cambios)
- **Filtros:** `scripts/flow_state_lib.py` (`evaluate_continuacion`, `evaluate_reversion`), espejo de
  `shared/flow-state-lib.js`. La paridad entre ambos está comprobada en `parity.py`. El Flow Score es una réplica de
  `computeFlowScore` (`shared/flow-score.js`). Ninguno de los dos filtros usa la cesta de tema.
- **Entradas de cada vela** (solo con datos hasta esa vela): w1 y m1 (retornos de 5 y 21 sesiones, redondeados como
  JS), RSI14 de Wilder, ATR% (0,1), distancia al máximo de 365 días, histograma MACD, su signo y su cambio diario.
  Koncorde D/3D/W y `konc_alignment` con las funciones de `scripts/koncorde_calculator.py` (3D = bloque de 3 sesiones
  que acaba en la vela; W = última semana cerrada).
- **Fuerza relativa de Continuación:** m1 del valor − m1 de SPY (en vivo se usa ^GSPC).
- **Eventos:** como `scripts/screener_shadow_portfolio.py → load_events`. Por filtro y valor, un candidato es evento
  nuevo solo si el candidato anterior del mismo filtro y valor está a ≥ 10 días de calendario. Cada candidato
  reinicia el contador, aunque no genere evento.
- **Salida:** con el ATR de entrada congelado. *Hard stop* 1,5 × ATR. *Trailing* 2 × ATR desde el máximo de cierre,
  activo cuando un cierre supera la entrada en máx(5 %, 1,5 × ATR%). Salida por tiempo a los 14 días de calendario.
  Las condiciones se evalúan sobre cierres. Coste: 0,2 % por operación.

## 3. Dos versiones de la simulación (auditoría de causalidad)
**A — réplica literal de producción (explicativa: se informa siempre, no decide el veredicto).** Sirve para
entender los resultados históricos de `SCREENER_SHADOW`.
- **Serie:** una fila por **día de calendario**. Fines de semana y festivos repiten la última vela, como el registro
  diario. Por eso ΔFlow a 5 son 5 días de calendario, y «5 días por encima de cero» puede cumplirse un domingo con la
  vela del viernes.
- **Fecha efectiva de la señal:** la vela que usa la fila (la última vela ≤ fecha). Un evento de sábado o domingo
  tiene vela de viernes.
- **Entrada:** cierre de la primera sesión posterior a esa vela.
- **Salidas:** se ejecutan al mismo cierre que las dispara, como `simulate()`.
- **Precios:** sin dividendos, como el `price` del snapshot.

**B — sesiones y ejecución operativa (primaria: decide el veredicto).**
- **Serie:** por **sesiones bursátiles**. ΔFlow, días por encima de cero y la ventana de 15 filas se cuentan en
  sesiones; los fines de semana no generan filas.
- **Señal:** conocida tras el cierre de su vela; el pipeline corre a las 23:10 de Madrid, con todos los mercados del
  universo cerrados.
- **Entrada:** **apertura** de la sesión siguiente, como una orden enviada esa noche.
- **Salidas:** cuando un cierre cumple *hard stop*, *trailing* o tiempo, se vende en la **apertura de la sesión
  siguiente**, con el hueco incluido. Nunca al mismo cierre que la decide.
- **Precios:** ajustados por dividendos (rentabilidad total), con aperturas, máximos y mínimos ajustados por el mismo
  factor.
- **Los stops no son órdenes stop intradía.** En las dos versiones se evalúan solo con el precio de cierre. Una caída
  durante la sesión que se recupere antes del cierre no los activa, y cuando se activan la venta no se hace al nivel del
  stop. En B se vende en la apertura siguiente, así que un hueco a la baja (resultados, noticias) puede dar una pérdida
  bastante mayor que 1,5 × ATR. Ese efecto está incluido en el resultado de B, no se recorta.

**Solapes (las dos versiones).** Como en producción, cada evento es una operación independiente. Un valor puede tener
a la vez operaciones de los dos filtros, y también del mismo filtro si entre candidatos hay ≥ 10 días y la anterior
sigue abierta. Se informa del número medio de operaciones simultáneas por fecha. El error estándar se calcula sobre
la serie de fechas con Newey-West, retardo 10, unas 14 sesiones de solape. Comprobación aparte, que no decide: versión
sin solapes, que descarta un evento si el mismo valor tiene una operación abierta del mismo filtro.

**Hallazgo de la auditoría (producción, no se corrige aquí).** `SCREENER_SHADOW` entra en la primera vela posterior a
la vela de la señal, aunque esa vela ya hubiera cerrado cuando se capturó la señal (dato con retraso). De sus 255
posiciones, 17 tienen la entrada **antes** de la fecha de captura (3 de Continuación, 3 de Reversión): son precios del
pasado, inejecutables. Otras 46 entran el mismo día de la captura, que con el run de la tarde llegando tras el cierre
probablemente también eran inejecutables. Las operaciones de la cartera sombra anteriores al 2026-11-10 no son un
registro operativo fiable. Corregirlo en producción es una decisión aparte.

## 4. Condición previa: reproducibilidad (comprobada antes de mirar resultados)
Datos: registro en vivo `docs/data/screener_signal_log.jsonl` y `portfolio_daily_snapshot.jsonl`, 27-ago → 9-nov-2026,
frente a la reconstrucción de U2. Scripts: `repro.py`, `diag_repro.py`, `repro_clean.py`, `_konc_window_test.py`,
`_input_parity.py`. Resultados: `repro_results.json`, `repro_diag.json`, `repro_clean.json`.

**Requisitos. Si alguno falla, no se ejecuta el contraste.** Los umbrales R2 se fijaron después de ver las
cifras de esta comprobación; se declara.
- **R1 — lógica.** Al evaluar el código de producción sobre el propio snapshot se reproduce el registro (≥ 99 % de
  candidatos por filtro). **Cumplido:** Continuación 187 de 187 y Reversión 352 de 352, más 1 candidato de más (GTBIF,
  4-nov). Los 4 candidatos del 10-nov no se cuentan porque la descarga de U2 acaba el 9-nov.
- **R2 — entradas.** Con el mismo histórico de precios, los algoritmos de producción dan las mismas entradas que la
  reconstrucción:
  - `konc_alignment` con `compute_for_ticker` y la ventana de 820 días de producción: ≥ 98 %. **Cumplido:** 300 de
    300 en una muestra aleatoria.
  - En los días con dato en vivo limpio (vela del día, precio a ±0,3 % del cierre y mismo Koncorde, 6.161
    días-valor): Flow a ≤ 1 punto ≥ 95 % (**96,1 %**), RSI a ≤ 1 ≥ 99 % (**99,8 %**), signo del histograma MACD
    ≥ 99 % (**99,7 %**). **Cumplido.**
- **R3 — diferencias explicadas.** Las discrepancias entre eventos en vivo y reconstruidos tienen causa identificada.
  **Cumplido:** el dato en vivo llega tarde, y no hay ningún fallo de la lógica ni de las entradas.
  - Coincidencia de eventos (±3 días): Continuación 51 de 72 (71 %), Reversión 99 de 117 (85 %).
  - Antigüedad de la vela en las capturas: 35 % del mismo día, 36 % de un día antes, 22 % de dos y 6 % más antigua.
  - Desacuerdos de Continuación por día: vela distinta 93; vela capturada intradía 45; historia con velas repetidas
    37; Koncorde de otra pasada 11; otros 6.
  - En las capturas del 9 y el 10-nov, el 96 % ya trae la vela del propio día.

**Verificación prospectiva (no bloquea el contraste, sí su lectura).** Tras 20 sesiones desde el 2026-11-10 se
compara de nuevo el registro en vivo con la reconstrucción. Si coinciden menos del 85 % de los eventos (±1 sesión)
en alguno de los dos filtros, el resultado de este estudio no se puede trasladar a la cartera sombra. En ese caso se
documenta como regla distinta.

## 5. Universos y muestras
- **U1 (decide).** 514 componentes actuales del S&P 500 / Nasdaq 100, caché de `research/macd_combo_filters_v1`
  (2015 → 2026-11-09).
  - **Desarrollo:** señales del 2017-07-01 al 2020-12-31. Antes no hay Koncorde semanal: hacen falta ~2 años de
    historia.
  - **Prueba:** señales del 2021-01-01 al 2026-10-23, que deja 14 días antes del fin de los datos. Se ejecuta una sola
    vez.
- **U2 (contraste, no decide solo).** Los 130 tickers de Portfolio Tracker, con diarios de Yahoo desde el 2018-01-01.
  Señales del 2021-01-01 al 2026-10-23.
- **Sesgos declarados.**
  - U1 solo tiene supervivientes, lo que favorece comprar valores débiles que luego se recuperan; es decir, ayuda a
    Reversión.
  - U2 es una lista elegida a mano, en parte después de que los valores llamaran la atención, lo que favorece a
    cualquier filtro alcista.
- Las operaciones que sigan abiertas al final de los datos se excluyen y se informa del número.

## 6. Métricas
- **Exceso (primaria).** Para cada evento: retorno neto (coste incluido) con las reglas de salida, menos la **media
  del universo** simulada con las mismas reglas y la misma versión desde la misma vela de señal. El universo son todos
  los valores con datos esa vela; su referencia lleva el mismo coste y el mismo retardo de ejecución. Se promedian los
  eventos de cada fecha y después las fechas. El error estándar es Newey-West con retardo 10 sobre la serie de fechas
  con eventos.
- **Se informan por separado, para cada filtro, versión y muestra:**
  - **Magnitud:** exceso medio en puntos porcentuales por operación.
  - **Incertidumbre:** IC del 95 % y IC del 97,5 % (Bonferroni para 2 filtros).
  - **Significación:** t y p.
- **Secundarias:**
  - Acierto (retorno neto > 0) frente al del universo en las mismas fechas.
  - Mediana; percentiles 5/25/75/95; % de pérdidas > 10 %; motivo de salida.
  - Resultado sin el 1 % de mejores operaciones.
  - Por año y por régimen (SPY sobre o bajo su SMA200 en la vela de señal).
  - Exceso sin *stops* a 5, 10 y 20 sesiones.
  - Operaciones simultáneas.
- **Sensibilidad (se informa siempre, no decide):** retardo Newey-West 20; versión sin solapes; versión A con
  **entrada una sesión más tarde** (cierre de la segunda sesión tras la vela de señal, universo con el mismo retraso),
  que aproxima el retraso del dato en vivo anterior al 10-nov.

## 7. Clasificación (para cada filtro por separado)
Efecto mínimo de interés (EMI): **+0,5 puntos porcentuales netos por operación** sobre el universo. Una ventaja
significativa pero inferior al EMI **no** es validación económica.

El veredicto lo decide la **versión B**. Las dos hipótesis (Continuación y Reversión) se controlan con Bonferroni,
con intervalos de confianza del 97,5 % (Newey-West, retardo 10). La versión A se informa siempre con las mismas métricas,
pero no determina el veredicto por sí sola.

**VALIDADO** si se cumplen todas (versión B):
1. **Magnitud.** U1 prueba: exceso medio ≥ +0,5.
2. **Significación.** U1 prueba: límite inferior del IC 97,5 % > 0.
3. **Estabilidad.** U1 desarrollo: exceso medio > 0.
4. **Comparación con el universo.** U1 prueba: acierto del filtro > acierto del universo en las mismas fechas.
5. **Extremos.** U1 prueba, sin el 1 % de mejores operaciones: exceso medio > 0.
6. **Contraste.** U2: exceso medio > 0 (solo el signo).

**VALIDADO CON GRAN CERTEZA** (se indica aparte, no cambia la decisión): si además el límite inferior del IC 97,5 % en
U1 prueba (B) es ≥ +0,5.

**SIGNIFICATIVO PERO SIN INTERÉS ECONÓMICO:** en U1 prueba (B) el límite inferior del IC 97,5 % es > 0 y el exceso
medio es < +0,5. No se promueve.

**NO SOPORTADO:** el IC 97,5 % de U1 prueba (B) queda entero por debajo de +0,5.

**INCONCLUYENTE:** el resto. Incluye un exceso que alcanza el EMI pero con un intervalo amplio, o uno que solo aparece
en U2 o en A. No es una refutación, pero tampoco se promueve nada.

**Traslado a producción.** Aunque un filtro salga VALIDADO, no se traslada nada a producción hasta superar la
verificación prospectiva del §4: 20 sesiones desde el 2026-11-10 con al menos el 85 % de los eventos coincidentes (±1
sesión) entre el registro en vivo y la reconstrucción.

No se cambiarán umbrales de los filtros, reglas de salida, ventanas, horizontes ni versiones tras ver resultados, ni
se probarán variantes sobre estos datos. Inflexión y los demás filtros del Screener quedan fuera.

## 8. Estado
1. Condición previa (§4): cumplida el 2026-11-11.
2. Firma del usuario: 2026-11-11 (v3). Queda congelado (hash SHA-256 en
   `research/flow_cont_rev_v1/PREREGISTRO.sha256`). Contraste autorizado para ejecutarse una sola vez, sin tocar
   producción ni carteras reales.
