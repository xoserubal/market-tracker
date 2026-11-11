# Confluencia sectorial v1: régimen + Flujos & Rotación + flow change de RFL

Preregistro firmado el 2026-11-11: `wiki/PREREGISTRO_CONFLUENCIA_SECTORIAL_V1.md`. La huella está en
`PREREGISTRO.sha256` y se guardó antes de calcular nada. Se ejecutó una sola vez.

**Resultado: NO SOPORTADO en las dos versiones.** Ni A (aceleración) ni B (retroceso) dan ventaja. Coincidir las tres
patas no mejora a ninguna de ellas por separado, ni a la fuerza relativa simple ni al azar.

## Ejecución
1. `build_signals.py` recalcula el MacroScore y Flujos & Rotación con `backtest/src`, sobre OHLCV de Yahoo descargados
   el 2026-11-11 en `backtest/data/raw`.
   - **Comprobación de §8.2:** sin desfase, el régimen guardado se reproduce en el 100 % de las 1 141 semanas (diferencia
     máxima de MacroScore = 0), y `fit` y la señal en el 100 % de 11 277 pares.
   - **Con el desfase de publicación** (NetLiq una semana; CFNAI desde el primer viernes a partir del día 25 del mes
     siguiente), el régimen cambia en el **24,9 %** de las semanas: el histórico guardado miraba al futuro.
2. `analyze.py` hace el contraste y escribe `results.json`. Los intermedios están en `_work/` (no se versionan).

## Resultado primario
Exceso a 20 sesiones frente a la media de los sectores, neto de un 0,1 % de coste. Última decisión: 2026-09-15.

| | Desarrollo 2006-2015 | Prueba 2016-2026 | IC 97,5 % (prueba) | Sectores-semana (prueba) | Clasificación |
|---|---|---|---|---|---|
| **A** (flow change > 0) | −0,30 (t −1,3) | **−0,27** (t −0,8) | −1,00 a +0,46 | 385 | NO SOPORTADO |
| **B** (flow change < 0) | −0,19 (t −0,8) | **−0,27** (t −1,1) | −0,83 a +0,29 | 380 | NO SOPORTADO |
| L y F sin flow change (referencia) | −0,25 | −0,32 (t −1,2) | | 765 | |

En los dos casos el límite superior del intervalo queda por debajo del efecto mínimo de interés (+0,5). Ninguno de los
seis criterios de validación se cumple.

**Contraste con las referencias (prueba):**
- **Lo que añade el flow change:** A −0,01 (t −0,2) y B 0,00 (t 0,0). El flow change no cambia nada.
- **Frente al top-k por fuerza relativa a 63 sesiones:** −0,17 en A y en B (t −0,5).
- **Frente al azar:** A queda en el percentil 19 y B en el 22.
- **B − A:** +0,03 en prueba (t 0,1) y −0,08 en desarrollo. Aceleración y retroceso son indistinguibles.

Por subperiodo, los dos solo son positivos en 2021-2023 (A +0,39, B +0,11). Quitando el 1 % de mejores eventos, la media
cae a −0,46 en A y −0,38 en B.

## Sensibilidades (no deciden)
- **Régimen sin desfase:** prueba A −0,46 y B −0,49 (t −1,9).
- **Horizontes** (prueba): todo negativo.
  - 5 sesiones: A −0,14, B −0,13;
  - 10 sesiones: A −0,23, B −0,08;
  - 40 sesiones: A −0,38, B −0,74.
- **Coste del 0,2 %:** A −0,37, B −0,37.
- **SPY por encima de su SMA200:** A −0,01, B −0,06.
- **SPY por debajo de su SMA200:** A −1,47, B −1,23 (t −2,4). Pocas fechas: 43-45.
- **Eventos independientes** (primera semana tras ≥ 4 sin cumplir): prueba A −0,19 (116 eventos), B −0,04 (125 eventos).

## Lectura
- **La pata media no funciona.** Coincidir con el régimen y con una señal de compra de Flujos & Rotación ya sale
  ligeramente negativo antes de mirar el flow change (prueba −0,32).
- **La pata rápida no lo arregla en ningún sentido.** La reversión que se ve en los ratios de RFL no se traslada a esta
  selección de ETFs.
- Coherente con lo ya medido: rot_score sin poder de ranking y amplitud sectorial NO SOPORTADA. La matriz de coherencia
  de RFL (Fase 5a) es una lectura descriptiva, no un detector.
- **Límites:**
  - no hay histórico de revisiones de CFNAI, así que el desfase usa valores ya revisados;
  - solo 11 sectores;
  - los datos de la prueba ya se habían visto en parte (§5 del preregistro).
