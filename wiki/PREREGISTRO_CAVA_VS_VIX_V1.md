# Preregistro — ¿Cava `risk_off` anticipa caídas mejor que el VIX solo? (v1, borrador)

**FIRMADO el 2026-11-11 por el usuario («dale»: descarga autorizada y firma). Congelado desde ese momento.** No se ha calculado ningún resultado futuro con estas definiciones. Alcance:
investigación en `research/cava_vs_vix_v1/`. No se toca la cartera CAVA_MACRO ni el pipeline.

## 0. Pregunta
La Prueba 1C mostró que con `risk_off` el mes siguiente del SPY es claramente más arriesgado:
- 34 % de meses malos, frente al 12 % en `risk_on`;
- el doble de volatilidad;
- el doble de caída.

Pero la volatilidad alta tiende a seguir a la volatilidad alta, y `risk_off` aparece cuando el VIX está alto.

**Pregunta:** ¿la postura de Cava añade información sobre el riesgo del mes siguiente a la que ya da el VIX?
- **Si no:** para modular la exposición basta una regla de VIX, más simple y sin depender del motor.
- **Si sí:** la postura de Cava tiene valor propio como capa de riesgo.

## 1. Datos
- **Motor:** `cava-decision-engine` v1.1.0 (tag `v1.1.0`, commit `e9a7140`). Es el mismo que usa CAVA_MACRO.
  - Clonado en esta sesión e instalado con `pip install -e`.
- **Estado de mercado:** `scripts/cava_state_history.py` + `scripts/cava_mapping.py`, con el mismo paso a entradas del
  motor que `scripts/cava_test_1c.py`.
- **SPY y VIX diarios:** los mismos que usa `cava_state_history.py` (yfinance).
- **Corrección de punto en el tiempo (obligatoria).** `cava_state_history` lee `macro_history.parquet`, que usa CFNAI y
  NetLiq sin desfase de publicación. Con desfase, el régimen cambia en el 24,9 % de las semanas
  (`research/sector_confluence_v1`).
  - Las entradas `macro_regime`, `macro_score_delta_4w` y `netliq_d4w/d8w` se toman del MacroScore recalculado con
    el desfase de `research/sector_confluence_v1/build_signals.py` (NetLiq una semana; CFNAI desde el primer viernes
    a partir del día 25 del mes siguiente).
  - La versión sin desfase solo se usa como sensibilidad.
- **Crédito:** solo existe desde 2023-08. Antes, Cava funciona sin la dimensión de crédito, igual que en la Prueba 1C.

## 2. Definiciones (fijadas antes de ver resultados)
- **Señal de Cava:** `C = 1` si `deterministic_risk_posture == "risk_off"` en el día t (con datos hasta el cierre de t).
- **Regla de VIX con la misma frecuencia:** `V = 1` si el VIX al cierre de t está en o por encima de su percentil q en
  las 1 260 sesiones anteriores (5 años, sin incluir t).
  - q se fija para que V esté activa el mismo porcentaje del tiempo que C en toda la muestra.
  - Es el único parámetro elegido mirando el conjunto, y solo para igualar frecuencias, no resultados.
  - Sensibilidad: un umbral fijo de VIX ≥ 25.
- **Resultados del mes siguiente** (de t+1 a t+21, sin incluir t; corrige que la 1C contaba el propio día t):
  - **MDD21 (primario):** caída máxima del cierre de SPY desde el cierre de t, en %.
  - **VOL21:** volatilidad anualizada de los retornos de t+1 a t+21.
  - **R63:** retorno a 63 sesiones. Es el coste de reducir riesgo: cuánto retorno se deja en esas fechas.

## 3. Hipótesis
- **H1 (primaria, incremental):** en los días con V = 0 (el VIX no avisa), C = 1 tiene un MDD21 medio peor que C = 0.
  - Estadístico: diferencia de medias (C = 1 − C = 0) dentro de V = 0.
- **H2 (primaria, comparación directa):** entre los días en que las dos reglas discrepan, el MDD21 es peor en
  C = 1, V = 0 que en C = 0, V = 1. Mide cuál de las dos reglas acierta cuando no coinciden.
- **Descriptivo:**
  - la misma tabla para VOL21 y R63;
  - la separación de cada regla sola (activa frente a inactiva);
  - la tabla 2 × 2 completa con número de días;
  - el porcentaje de días en que C y V coinciden.

## 4. Inferencia
- Muestra única de 2005-02 a 2026-09 (último día con 63 sesiones de futuro). No hay parámetros que ajustar, salvo q.
- Las ventanas de 21 sesiones se solapan y los estados de riesgo duran semanas. Por eso los intervalos se calculan con
  un **bootstrap por bloques circulares de 63 sesiones** (5 000 repeticiones, semilla fija), remuestreando la serie
  diaria completa y recalculando las diferencias.
- **Subperiodos:** 2005-2012, 2013-2019, 2020-2026.

## 5. Clasificación
**Efecto mínimo de interés (EMI):** 1 punto de MDD21 (la caída media mensual en `risk_on` ronda el 2 %, así que 1
punto es la mitad).

- **CAVA APORTA**, si se cumple todo:
  1. H1: diferencia ≤ −1 punto y el límite superior del IC 95 % < 0;
  2. H2: diferencia < 0;
  3. H1 negativa en al menos 2 de los 3 subperiodos;
  4. el mismo signo con la versión sin desfase y con el umbral fijo de VIX ≥ 25.
- **CAVA NO APORTA SOBRE EL VIX:** el límite inferior del IC 95 % de H1 es > −1 punto.
  - Con este resultado, para modular la exposición basta una regla de VIX. CAVA_MACRO seguiría como experimento, pero
    su capa de riesgo no se justificaría por sí misma.
- **INCONCLUYENTE:** el resto. Puede pasar con facilidad: los días con C = 1 y V = 0 pueden ser pocos.
  - Se informa el número de días y de episodios independientes de cada casilla. Si C = 1, V = 0 tiene menos de
    3 episodios separados (bloques de ≥ 21 sesiones sin señal entre ellos), el resultado es INCONCLUYENTE por datos.

**Sensibilidades (se informan todas, ninguna decide):**
- sin desfase;
- VIX ≥ 25;
- solo desde 2023-08 (con la dimensión de crédito; muestra corta);
- VOL21 como medida primaria alternativa.

No se probarán otros percentiles, ventanas ni medidas de riesgo.

## 6. Pendiente antes de firmar
1. Autorizar la descarga de SPY y VIX con yfinance (dos símbolos), si `cava_state_history` no los tiene en caché.
2. Firmar. La huella SHA-256 se guarda en `research/cava_vs_vix_v1/PREREGISTRO.sha256` antes de calcular nada.

## 7. Firma
- Firmado el 2026-11-11. La huella SHA-256 del documento, calculada sin esta sección 7, está en `research/cava_vs_vix_v1/PREREGISTRO.sha256`. Se guardó antes de calcular nada.
