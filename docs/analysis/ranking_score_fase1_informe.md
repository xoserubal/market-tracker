# Ranking Score -- Fase 1: informe de analisis exploratorio

_Generado 2026-09-04 por `scripts/ranking_score_fase1_analysis.py`, disparado por el recordatorio `ranking_score_fase1_analisis` (`docs/data/reminders.json`, 2026-09-03)._

**Naturaleza de este informe (preregistro Sec.1, `wiki/PREREGISTRO_RANKING_SCORE_V0.md`):** descriptivo, no calibratorio. No elimina ni anade componentes preregistrados, no ajusta pesos. Longitud acotada a 3-5 paginas por el preregistro (el plan original de Fase 1 pedia 10-15; el preregistro lo recorto explicitamente, seccion 6).

## 0. Dataset limpio de P0

- `shadow_picks.jsonl` en bruto: **303** filas.
- Tras `dedup_same_day_reruns()` (P0, ya resuelto antes del preregistro): **271** filas.
- Tras filtrar `valid_for_performance_tracking != False` (excluye runs con violaciones de HARD_RULES o `forced_run=True` -- nunca se convirtieron en decision real de portfolio): **150** filas -- este es el "dataset limpio de P0" que usa este informe.
- De esas, **98** tienen `ret_1m` ya calculado y **33** tienen `ret_3m` (los mas recientes aun no maduran).
- Calidad de datos media por pick (fraccion de 13 campos rastreados presentes): **0.798**. Picks `ranking_score_eligible=true` (calidad >=0.80 y ningun bucket critico totalmente ausente): **60/150**.
- Dataset consolidado completo: `docs/data/ranking_score_fase1_dataset.jsonl` (formato .jsonl en vez de .csv/.parquet -- consistente con el resto de `docs/data/`, mismo contenido tabular, una fila por linea).

## 1. Metodologia de clasificacion (definida en esta ejecucion, no en el preregistro)

El preregistro deja la clasificacion en terminos cualitativos ("correlacion consistente y en direccion esperada" / "senal debil o inconsistente"). Para que el resultado sea reproducible, esta ejecucion fija una regla mecanica, aplicada igual a todos los componentes:

1. **not_usable_missing_data** si n < 15 o cobertura < 30% del universo con el outcome disponible.
2. **suspicious_redundant** si `|Spearman rho|` >= 0.7 contra cualquier otro componente preregistrado (se cita cual).
3. **plausible** si `|rho pooled|` >= 0.15, p <= 0.1, el signo no se invierte en ningun segmento (por cartera o por regimen macro) con n >= 10, y -- solo para los componentes de Entry Quality, donde el plan fija una direccion a priori -- el signo coincide con esa direccion esperada.
4. **inconclusive** en cualquier otro caso (incluye signo consistente pero en la direccion contraria a la esperada).

IC95% via transformacion Fisher-z sobre Spearman rho (misma convencion ya usada en `scripts/analyze_relative_flow_signal.py` para el backtest de Relative Flow Lab) -- aproximacion estandar, no exacta para rho, declarada como tal.

**Dos notas de lectura, para no confundir numeros de distintas secciones:**
- El `coverage_pct` de cada componente (Secciones 2-5) se mide sobre el universo con el outcome disponible (`ret_1m`/`ret_3m`), no sobre el dataset limpio completo -- es distinto del gate de cobertura de la Seccion 7, que se mide sobre las 150 filas limpias enteras.
- `MAE (1m)` es `max_drawdown_1m`, guardado con signo (negativo = peor). Un rho **positivo** entre un componente "mas alcista" (ordinal ascendente) y MAE significa drawdowns **menos** profundos (mejor), no peores -- leer el signo con cuidado en las tablas de abajo.

## 2. Entry Quality (30%)

### extension_risk (ordinal bajo=0..extremo=3)

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=-0.049, p=0.6334, n=98, IC95%=[-0.2448, 0.1511]

- vs ret_3m: rho=-0.269, p=0.1301, n=33, IC95%=[-0.5605, 0.0819]

- vs MAE (1m): rho=-0.157, p=0.0582, n=146, IC95%=[-0.3116, 0.0055]

- vs ratio MFE/|MAE| (1m): rho=-0.069, p=0.4064, n=146, IC95%=[-0.2291, 0.0943]


### dist_sma20_atr

- Clasificacion: **PLAUSIBLE**

- vs ret_1m: rho=-0.268, p=0.0077, n=98, IC95%=[-0.4427, -0.0733]

- vs ret_3m: rho=-0.188, p=0.2945, n=33, IC95%=[-0.4992, 0.1659]

- vs MAE (1m): rho=-0.071, p=0.3934, n=146, IC95%=[-0.2309, 0.0924]

- vs ratio MFE/|MAE| (1m): rho=-0.117, p=0.1594, n=146, IC95%=[-0.2743, 0.0463]


### spike_flag (0/1)

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=+0.172, p=0.0898, n=98, IC95%=[-0.0271, 0.3585]

- vs ret_3m: rho=-0.224, p=0.2103, n=33, IC95%=[-0.5268, 0.1293]

- vs MAE (1m): rho=+0.014, p=0.8655, n=146, IC95%=[-0.1487, 0.1762]

- vs ratio MFE/|MAE| (1m): rho=+0.066, p=0.4257, n=146, IC95%=[-0.0971, 0.2264]


### RSI en zona 45-65 (0/1)

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=+0.028, p=0.7811, n=98, IC95%=[-0.171, 0.2256]

- vs ret_3m: rho=-0.034, p=0.8519, n=33, IC95%=[-0.3728, 0.3132]

- vs MAE (1m): rho=-0.079, p=0.3442, n=146, IC95%=[-0.2382, 0.0847]

- vs ratio MFE/|MAE| (1m): rho=-0.014, p=0.8698, n=146, IC95%=[-0.1757, 0.1491]


### momentum_decay (0/1)

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=+0.171, p=0.0933, n=98, IC95%=[-0.0289, 0.3568]

- vs ret_3m: rho=+0.279, p=0.1162, n=33, IC95%=[-0.0714, 0.5678]

- vs MAE (1m): rho=-0.064, p=0.4425, n=146, IC95%=[-0.2242, 0.0994]

- vs ratio MFE/|MAE| (1m): rho=+0.074, p=0.3754, n=146, IC95%=[-0.0896, 0.2335]


## 3. Flow Institucional (25%) -- subseccion Koncorde, tratada aparte

**Nota de cobertura (preregistro Sec.0/Sec.1):** Koncorde no existia como feature antes de 2026-06-30 y no se registro en `shadow_picks.jsonl` de forma sistematica hasta 2026-07-02 -- no es un hueco de logging, es ausencia real de la senal en ese periodo. Su clasificacion aqui tiene **caracter provisional**, con su propio n e IC95% por debajo, nunca mezclada en la misma tabla que componentes con historial completo desde 2026-05-08.

### Koncorde 3D state (ordinal)

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=-0.142, p=0.4312, n=33, IC95%=[-0.4626, 0.2118]

- vs ret_3m: n=0 (insuficiente)

- vs MAE (1m): rho=+0.139, p=0.2681, n=65, IC95%=[-0.1082, 0.3707]

- vs ratio MFE/|MAE| (1m): rho=-0.078, p=0.5373, n=65, IC95%=[-0.3158, 0.1692]


### Koncorde W state (ordinal)

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=-0.092, p=0.6161, n=32, IC95%=[-0.4271, 0.2651]

- vs ret_3m: n=0 (insuficiente)

- vs MAE (1m): rho=+0.000, p=1.0000, n=61, IC95%=[-0.2518, 0.2518]

- vs ratio MFE/|MAE| (1m): rho=-0.071, p=0.5851, n=61, IC95%=[-0.3174, 0.1838]


### Coherencia D/3D/W (konc_alignment, ordinal)

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=-0.172, p=0.3384, n=33, IC95%=[-0.4866, 0.182]

- vs ret_3m: n=0 (insuficiente)

- vs MAE (1m): rho=+0.293, p=0.0178, n=65, IC95%=[0.0531, 0.5012]

- vs ratio MFE/|MAE| (1m): rho=-0.005, p=0.9699, n=65, IC95%=[-0.2484, 0.2394]


## 4. Cambio de Senal (20%)

### rot_score_delta 4w

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=+0.042, p=0.7691, n=51, IC95%=[-0.2362, 0.3141]

- vs ret_3m: n=1 (insuficiente)

- vs MAE (1m): rho=-0.219, p=0.0303, n=98, IC95%=[-0.4, -0.0214]

- vs ratio MFE/|MAE| (1m): rho=-0.057, p=0.5756, n=98, IC95%=[-0.2528, 0.1428]


### streak_weeks_delta

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=+0.138, p=0.3337, n=51, IC95%=[-0.1429, 0.3986]

- vs ret_3m: n=1 (insuficiente)

- vs MAE (1m): rho=-0.002, p=0.9876, n=98, IC95%=[-0.1999, 0.1969]

- vs ratio MFE/|MAE| (1m): rho=+0.025, p=0.8075, n=98, IC95%=[-0.1744, 0.2222]


### theme_flow_delta (delta component_B)

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=-0.084, p=0.5428, n=55, IC95%=[-0.3415, 0.1856]

- vs ret_3m: n=1 (insuficiente)

- vs MAE (1m): rho=-0.094, p=0.3492, n=102, IC95%=[-0.283, 0.1027]

- vs ratio MFE/|MAE| (1m): rho=+0.019, p=0.8465, n=102, IC95%=[-0.1757, 0.2131]


## 5. Contexto Sectorial (15%)

`vehicle_vs_theme_strength` no existe como campo calculado en ningun punto del codebase (confirmado por busqueda en el repo antes de este analisis) -- se reporta directamente como `not_usable_missing_data`, cobertura 0%, sin inventar un proxy.

### theme_breadth

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=+0.135, p=0.1867, n=98, IC95%=[-0.0657, 0.3243]

- vs ret_3m: rho=+0.280, p=0.1143, n=33, IC95%=[-0.0698, 0.5688]

- vs MAE (1m): rho=+0.258, p=0.0016, n=146, IC95%=[0.1001, 0.4038]

- vs ratio MFE/|MAE| (1m): rho=+0.050, p=0.5521, n=146, IC95%=[-0.1138, 0.2104]


### vehicle_vs_theme_strength

- Clasificacion: **NOT USABLE (missing data)**

- vs ret_1m: n=0 (insuficiente)

- vs ret_3m: n=0 (insuficiente)

- vs MAE (1m): n=0 (insuficiente)

- vs ratio MFE/|MAE| (1m): n=0 (insuficiente)


### dias desde ultimo pick del mismo ticker

- Clasificacion: **INCONCLUSIVE**

- vs ret_1m: rho=+0.161, p=0.2500, n=53, IC95%=[-0.1145, 0.4132]

- vs ret_3m: n=11 (insuficiente)

- vs MAE (1m): rho=+0.103, p=0.3428, n=86, IC95%=[-0.1108, 0.3086]

- vs ratio MFE/|MAE| (1m): rho=+0.087, p=0.4244, n=86, IC95%=[-0.127, 0.2937]


## 6. Analisis segmentado (informativo, seccion 1.4 del plan)

Los cortes por cartera y por regimen macro ya se usan arriba solo como chequeo de consistencia de signo para la clasificacion (paso 3 de la regla mecanica) -- no se listan aqui coeficiente por coeficiente por segmento para mantener el informe en 3-5 paginas; el detalle completo por segmento queda en `docs/data/ranking_score_fase1_results.json`.

## 7. Verificacion de cobertura minima (preregistro 1.7)

El plan original marca esta seccion como **bloqueante para Fase 2** si algun componente critico tiene cobertura <80%. **El preregistro ya resolvio esto en su Seccion 0**, verificado contra datos reales: *"la cobertura en candidatos en vivo (hoy): 100% en todos los campos anteriores -- el gate de 80% de la Fase 1.7 del plan original no bloquea Fase 2, solo condiciona que puede analizarse retrospectivamente en Fase 1."* Se reportan los numeros reales de todos modos, por transparencia, no como gate:


| Componente critico | Cobertura sobre dataset limpio de P0 | >=80%? |
|---|---|---|

| entry_quality inputs (extension_risk) | 100.0% | si |

| Koncorde 3D/W (ambos) | 41.3% | **no** |

| rot_score_delta_4w | 68.0% | **no** |

| theme_breadth | 100.0% | si |


Por debajo de 80%: Koncorde 3D/W (ambos) (41.3%), rot_score_delta_4w (68.0%). Koncorde 3D/W es el mas bajo, coherente con el techo de cobertura historica (~15%) ya documentado en el preregistro -- no existia como feature antes de 2026-06-30. No bloquea el arranque de Fase 2 (resolucion ya firmada en preregistro Sec.0); solo limita cuanto se puede decir de esos componentes en este informe.

## 8. Lectura de conjunto (comentario, no decision)

De los 14 componentes preregistrados evaluados, **1** clasifica como `plausible` frente a `ret_1m` bajo la regla mecanica de la Seccion 1: `dist_sma20_atr`. El resto queda `inconclusive` (senal debil, inconsistente entre segmentos, o en direccion contraria a la esperada) por ahora -- con n=98 para ret_1m y muestras menores por componente segun cobertura, es exactamente el resultado que cabe esperar de una muestra todavia pequena, no evidencia de que el diseno este mal.

Algunos patrones descriptivos, sin implicar decision alguna (Seccion 1.1): componentes con asociacion mas marcada con MAE (`max_drawdown_1m`, drawdowns menos profundos) que con `ret_1m` -- `theme_breadth` (rho=+0.258, p=0.002, n=146) y, dentro de la subseccion Koncorde, la coherencia D/3D/W (rho=+0.293, p=0.018, n=65) -- sugieren que, si hay senal, podria estar mas del lado de "evita el peor escenario" que de "predice el retorno medio". Notas de este tipo van a la lista de "siguiente iteracion" de abajo, no cambian nada hoy.

## 9. Notas para siguiente iteracion (no se aplican al Ranking Score actual)

- `extension_risk_ord` y `dist_sma20_atr` correlacionan entre si con rho=+0.552 (n=150) -- por debajo del umbral de redundancia (0.7) pero cerca; vigilar cuando crezca la muestra, no actuar todavia.
- `dist_sma20_atr` y `rsi_zone_45_65` correlacionan entre si con rho=-0.598 (n=150) -- por debajo del umbral de redundancia (0.7) pero cerca; vigilar cuando crezca la muestra, no actuar todavia.
- `spike_flag_num` y `extension_risk_ord` correlacionan entre si con rho=+0.531 (n=150) -- por debajo del umbral de redundancia (0.7) pero cerca; vigilar cuando crezca la muestra, no actuar todavia.
- `konc_3d_state_ord` y `konc_alignment_ord` correlacionan entre si con rho=+0.663 (n=66) -- por debajo del umbral de redundancia (0.7) pero cerca; vigilar cuando crezca la muestra, no actuar todavia.

**Recordatorio explicito (preregistro Sec.5):** ninguna de estas notas se traduce en un cambio de pesos, componentes o umbrales del Ranking Score preregistrado. Cualquier cambio exige marcar "post-preregistro" con justificacion conceptual escrita, nunca numerica.
