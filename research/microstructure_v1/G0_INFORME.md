# Microestructura v1 — Puerta G0: viabilidad técnica y presupuesto (2026-11-15)

Encargo: «Market Tracker — Encargo V3» (investigación de microestructura, flujo de órdenes y acumulación
institucional). Esta carpeta cubre **solo G0**. No hay experimento, ni adaptador definitivo, ni captura
activa. Nada de producción se ha tocado.

- Scripts: `alpaca_g0_probe.py` (acceso y volumen de una sesión), `g0_budget.py` (presupuesto).
- Datos crudos y resultados con registros de mercado: `MICRO_DATA_DIR` = `D:/backup market tracker/microstructure/g0_probe`
  (fuera del repo y de Dropbox; la licencia de Alpaca no permite redistribuirlos). Aquí solo van agregados.
- Consumo total de G0: ~1 100 peticiones, ~1 GB descargado, ~86 MB guardados en D:.

---

## 1. Auditoría del proyecto: qué se reutiliza

| Componente | Uso en esta investigación |
|---|---|
| `research/early_flow7_validation_v1` + `research/macd_combo_filters_v1` | Benchmarks A ya construidos (momentum 5/20, RS vs mercado y sector, RS+volumen, azar emparejado) y benchmark B (Early Flow reconstruido con `shared/flow-score.js`) sobre S&P 500 + NDX 2016-2026. Ejecución a la apertura siguiente, exceso vs universo. |
| `research/sector_breadth_v1` | Composición del S&P 500 a fecha (instantáneas de Wikipedia 2016-2026, 96,5-99,4 % de coincidencia). Le faltaban precios de ~130 empresas que salieron del índice (cobertura 80 % en 2016). **Alpaca cubre el 98,6 % de esos huecos** (559/567 valor-año con ≥ 20 sesiones), ver §3. |
| `research/macd_combo_sp500_ndx_v1/constituents.json` | Lista actual S&P 500 + NDX (usada aquí solo para el presupuesto). |
| Preregistros (`wiki/PREREGISTRO_*.md` + `PREREGISTRO.sha256`) | Formato, congelación por SHA-256, desarrollo/prueba, Bonferroni, mínimo económico +0,5 pp, criterios de fiabilidad. |
| `private/` + bloqueo en `server.js` | Patrón para datos con licencia; aquí se va más allá (fuera de Dropbox). |

Resultados previos que condicionan el diseño:
- Flow Score ≈ momentum (R² 0,985). Early Flow ≥ 7: **descartado** (−0,41 pp a 20 ses., peor que los 6 benchmarks).
- RS a 3 meses positiva → **−0,4/−0,6 pp a 1-4 semanas** (reversión de corto plazo): a 5-10 sesiones el benchmark
  A no es «neutro», tiene un efecto propio que la microestructura debe superar o separar.
- Amplitud sectorial: no aporta sobre el ETF (IC −0,025). Saltos de flow change de RFL: nada a 1-5 sesiones.
- Potencia: en amplitud sectorial solo se detectaba IC ≥ ~0,13. Hay que calcularla antes, no después.

Infraestructura: el pipeline corre en GitHub Actions (efímero, no sirve para almacenar ni para descargas largas).
La captura y el estudio deben correr en el PC (y migrar al VPS). **Espacio libre: D: 136 GB (93 % ocupado),
C: 8,4 GB (97 %)**. El disco es una restricción real (ver §5).

## 2. Alpaca: matriz de disponibilidad (verificado con nuestras credenciales)

Plan **Basic (gratuito)**. Fuentes oficiales: [About Market Data API](https://docs.alpaca.markets/us/docs/about-market-data-api),
[Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq),
[redistribución](https://alpaca.markets/support/redistribute-alpaca-api),
[Terms and Conditions](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf).

| Dato | Estado | Detalle medido |
|---|---|---|
| Barras 1 min SIP | ✅ | Desde **2016-01-04**; 2015 devuelve 0. Campos `o h l c v n vw` (`n` = nº de trades de la barra; difiere del recuento de trades descargados un 0-3 %, más en los valores pequeños). |
| Trades SIP | ✅ desde 2016 | Campos `t x p s c i z`: precio, tamaño, centro de ejecución, condiciones, id, cinta. Timestamps en ns, UTC. |
| Quotes SIP | ✅ desde 2016 | Campos `t ap as ax bp bs bx c z`. Mejor bid/ask con su centro, no profundidad. |
| Últimos 15 min | ❌ 403 | `subscription does not permit querying recent SIP data`. Sin efecto: trabajamos tras el cierre. |
| IEX (alternativa gratuita en vivo) | ✅ pero inútil | 1,7 % del volumen SIP en la barra de apertura de AAPL. |
| Límite | 200 peticiones/min | Cabecera `X-RateLimit-Limit: 200`. 10 000 registros por página. |
| Rendimiento real | ~42 páginas/min en serie | Latencia ~1,4 s por página (~1 MB JSON). El límite de 200/min solo se alcanza con ~3-4 peticiones en paralelo (sin probar todavía). |
| Fuera de mercado (TRF) | ✅ | Código `x = 'D'` (FINRA ADF/TRF). **43-52 % del volumen** en los 8 valores medidos. Incluye internalización minorista, no solo ATS: no implica institucional. |
| Condiciones | ✅ | Catálogo completo (`I` odd lot, `F` ISO, `O/6` apertura/cierre, `4` derivatively priced, `T/U` extended hours…). |
| Lotes pequeños | — | **58-98 % de los trades < 100 acciones** (AAPL 91 %, URI 98 %): el recuento de trades está dominado por odd lots; hay que ponderar por volumen. |
| Deslistados | ✅ | TWTR 2021 con datos. 98,6 % de los huecos del S&P 500 histórico cubiertos. |
| Cambios de ticker | ✅ pero con cautela | FB y META devuelven los mismos datos para 2021. **Riesgo:** tickers reutilizados por otra empresa (p. ej. `ADT`, `CA`) — hay que verificar identidad en G1 (continuidad de precio y nombre). |
| Splits / acciones corporativas | ⚠️ sin verificar | Las barras aceptan `adjustment=raw/split/all`; trades y quotes llegan sin ajustar. El endpoint de corporate actions no se ha probado. |
| Calendario de sesiones / festivos | ⚠️ sin verificar | Endpoint de calendario (API de trading) no probado con estas claves. |
| Eventos (resultados) | ❌ no disponible | Alpaca no da histórico de fechas de resultados. Su endpoint de noticias no se ha probado. |
| Licencia | ⚠️ | Uso personal de investigación: permitido. **Redistribuir datos: no**, sin consentimiento escrito. Publicar agregados derivados: no aclarado → en el repo solo resultados estadísticos (IC, t, tablas resumen), nunca paneles por valor y día. |

## 3. Medición real: una sesión (2026-11-13, sesión regular, 8 valores)

| Valor | Trades | Págs. trades | Segundos | Parquet trades | Quotes (sesión) | Quotes / trade | % vol. fuera de mercado | Mediana tamaño |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NVDA | 4 423 061 | 443 | 634 | 46,3 MB | ~5,6 M (extrap.) | 1,27 | 51,7 % | 10 |
| AAPL | 679 551 | 68 | 98 | 7,7 MB | 570 276 | 0,84 | 44,2 % | 10 |
| SPY (ETF) | 520 672 | 53 | 72 | 6,3 MB | ~8,9 M (extrap.) | 17,1 | 42,5 % | 20 |
| HIMS | 85 513 | 9 | 12 | 1,2 MB | 111 510 | 1,30 | 51,0 % | 40 |
| OSCR | 44 991 | 5 | 7 | 0,7 MB | 41 000 | 0,91 | 43,4 % | 40 |
| URI | 21 845 | 3 | 4 | 0,4 MB | 76 597 | 3,51 | 50,2 % | 3 |
| CRESY | 8 244 | 1 | 1 | 0,1 MB | 11 907 | 1,44 | 43,4 % | 63 |
| VFF | 5 904 | 1 | 1 | 0,1 MB | 8 600 | 1,46 | 46,4 % | 100 |

Medido: 10,7 bytes/trade y 8,3 bytes/quote en Parquet zstd; barras ~15 KB por valor y día (fichero suelto,
cota superior). Las quotes de NVDA y SPY se cortaron a 120 páginas y se **extrapolaron** por fracción de sesión
cubierta (sobrestima: la apertura concentra más actividad). El ratio quotes/trade varía de 0,84 a 3,5 en acciones
(mediana 1,3) y es de 17 en SPY: es la cifra más incierta del presupuesto.

Mediana de trades por valor y día en el S&P 500 + NDX actual: 15 700 (2016) → 30 000 (2023) → 48 500 (2026). El
volumen de datos se ha triplicado en diez años.

## 4. Presupuesto por configuración (extrapolado de §3 con barras diarias de 588 valores)

«Horas» = descarga a ~126 páginas/min (3 en paralelo; en serie, ×3). Almacenamiento de datos crudos en Parquet.

| Configuración | Valor-días | Barras 1 min | Trades | Quotes (estimado) |
|---|---:|---|---|---|
| S&P 500 + NDX, 2016-2026 completo | 1,35 M | 52 600 pet. · **~5 h** · < 21 GB | 6,7 M pet. · **~890 h** · 650 GB | ~1 140 h · ~655 GB |
| S&P 500 + NDX, 2024-2026 | 368 k | 14 400 pet. · 1,3 h · < 6 GB | 372 h · 281 GB | ~478 h · 284 GB |
| Valores EE. UU. del proyecto (109), 2016-2026 | 268 k | 0,97 h · < 4 GB | 263 h · 196 GB | ~336 h · 198 GB |
| **Muestra B1: 100 valores × 200 días** | 19 k | 0,07 h | **~13 h · 9,8 GB** | ~17 h · 9,9 GB |
| Muestra B1: 200 valores × 250 días | 48 k | 0,2 h | ~34 h · 24,5 GB | ~43 h · 24,8 GB |
| Muestra B1: 300 valores × 500 días | 143 k | 0,5 h | ~94 h · 68 GB | ~119 h · 69 GB |

Conclusiones:
- **Nivel A (barras 1 min) es barato**: el universo completo point-in-time 2016-2026 cabe en una tarde y < 21 GB
  (bastante menos si se guarda por valor y año en vez de por día).
- **Nivel B (ticks) no admite panel completo**: ni por tiempo (~37 días de descarga continua) ni por disco
  (650 GB frente a 136 GB libres). Solo muestras.
- **Quotes cuestan tanto como los trades** y son la cifra menos fiable. Solo para una submuestra de comparación.
- El cuello de botella es el **tiempo**, no el disco, si se procesa y descarta (ver §5).

## 5. Arquitectura recomendada para G1

- **Adaptador** `micro/providers/alpaca.py` con interfaz neutra (`bars(sym, day)`, `trades(sym, day)`,
  `quotes(sym, day)`), paginación, límite de 180/min compartido entre hilos, 3 peticiones en paralelo,
  reintentos con espera, idempotencia por `(proveedor, nivel, valor, día)` y un manifiesto con estado, filas,
  bytes, peticiones, segundos y versión del adaptador.
- **Procesar y descartar por defecto**: descargar valor-día → validar → calcular variables → guardar variables →
  borrar el crudo, salvo en una muestra de retención fija (p. ej. 10 % con semilla). Así el disco deja de
  limitar el tamaño de la muestra B1; el límite pasa a ser el tiempo de descarga.
- **Capas en `MICRO_DATA_DIR`**: `raw/` (retención parcial) · `normalized/` · `features/` (por nivel, valor, año) ·
  `datasets/` · `results/` · `manifest/`. Ruta configurable para migrar al VPS.
- **Controles de calidad**: suma de volumen de trades vs barra diaria, recuento `n`, huecos de sesión, días
  medio-festivos, identidad del ticker (§2), splits.
- **Ejecución**: en el PC, por lotes nocturnos reanudables. No en GitHub Actions.

## 6. Propuesta de muestras (para decidir, no para ejecutar)

- **Nivel A:** S&P 500 point-in-time (composición de `sector_breadth_v1` + deslistados de Alpaca) + valores EE. UU.
  del proyecto, 2016-01 → 2026-11, barras 1 min completas. ~5-6 h de descarga.
- **Nivel B1 (piloto):** 100 valores × 200 días, estratificado por liquidez (terciles de trades/día) y año, elegido
  con semilla fija antes de mirar nada. ~13 h. Se presenta como **exploratorio** salvo que el cálculo de potencia
  diga otra cosa: con 200 fechas, el n efectivo se parece más a 200 que a 19 000 (dependencia transversal).
- **Quotes:** 20 valores × 20 días, solo para medir cuánto se equivoca la regla del tick frente a la clasificación
  con bid/ask (Lee-Ready).
- **B2 (enriquecida):** aplazada hasta que A o B1 den un fenómeno concreto.
- **Captura prospectiva (desactivada):** cada noche, barras 1 min de todo el universo elegible (~25 peticiones) y
  trades de una submuestra aleatoria de ~50 valores con semilla y probabilidad de inclusión registradas
  (~250 páginas, ~2-6 min, ~25 MB/día). Corre en el PC tras el cierre.

## 7. Riesgos metodológicos

1. **Benchmark A no es neutro a 5-10 sesiones** (reversión de RS). El modelo C debe compararse con A completo, no
   con «cero».
2. **Dependencia transversal**: muchos valores el mismo día no son observaciones independientes. Inferencia por
   fechas (Fama-MacBeth / errores agrupados por día) y n efectivo en el preregistro.
3. **El volumen por precio con barras de 1 minuto es una aproximación** (se reparte el volumen dentro del rango de
   la barra). Debe declararse así.
4. **Odd lots y fuera de mercado**: dominan recuentos y volumen; ni «trade grande = institucional» ni
   «`D` = institucional». Variables ponderadas por volumen y con condiciones filtradas.
5. **Tickers reutilizados y splits**: pueden fabricar anomalías falsas. Verificación de identidad y ajuste
   obligatorios en G1.
6. **Sin fechas de resultados fiables**: los días de resultados son los que más volumen anómalo generan. Sin
   fuente verificada, el análisis por eventos quedará limitado (eventos «desconocidos», no «ausentes»).
7. **Throughput**: el paralelismo de 3 no está probado; si Alpaca lo limita, las horas de B1 se triplican.
8. **Disco**: D: al 93 %, C: al 97 %. Procesar y descartar es casi obligatorio.

## 8. Estado de la puerta G0

**Superada técnicamente**: los tres niveles A y B (y quotes) son accesibles gratis desde 2016, con deslistados, y
el presupuesto permite un nivel A completo y un nivel B por muestras. **Pendiente de autorización** (ver §9).
Bloqueos menores sin resolver: splits/acciones corporativas, calendario y noticias de Alpaca sin probar.

## 9. Decisiones que requieren autorización

1. Pasar a **G1**: construir el adaptador, el manifiesto, la normalización y los controles de calidad.
2. Alcance del **nivel A** (universo point-in-time 2016-2026, ~5-6 h, < 21 GB en D:).
3. Tamaño de **B1**: piloto 100 × 200 (~13 h) o 200 × 250 (~34 h).
4. **Política de retención** del crudo (procesar y descartar con retención del 10 %).
5. **Quotes** solo en submuestra 20 × 20.
6. Que la **captura prospectiva** se construya (desactivada) dentro de G1.
