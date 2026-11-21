# Flow negativo — enmienda 2: resultado de la tanda 1 con c2 y de la tanda 2

Fecha: 2026-11-21 (LAWNMOWER). Enmienda: `wiki/ENMIENDA_2_FLOW_NEGATIVO_V3.md` (congelada). Todo es periodo de
desarrollo; **la prueba sigue cerrada**. Sin commits ni pushes.

## 0. Resumen

- La candidata de grandes **sigue pasando** con la versión corregida c2: grandes / episodio Flow < −30 / 20 sesiones /
  todos los regímenes, exceso +2,11 pp sobre su talla, t 2,57, 805 episodios, 101 semanas, mismo signo en las dos
  mitades y con las dos cotas.
- c2 hace elegible **una segunda celda**, que es la misma señal restringida al régimen lateral (t 2,58, 147 episodios,
  31 semanas: justo por encima de los mínimos). **Decisión tuya** (§4): contarla o no como celda de la etapa 2.
- Tanda 2 (pequeñas y micro, 2018-2022): **ninguna celda elegible**. Lo más fuerte son micro / bajista / Flow < −30,
  con exceso **negativo** (t −3,3 a 40 sesiones), que no pasa por superar el 1 % de episodios con desenlace
  desconocido (1,4-2,3 %).
- Selección para la etapa 2: 1 o 2 celdas, las dos de grandes. Nada más.

## 1. Qué se ha hecho

| Paso de la enmienda (§4) | Estado |
|---|---|
| 1. Congelar la enmienda | Hecho en DESPACHOB (`data/enmienda2_freeze.json`) |
| 2. Piloto y extracción general de acciones por clase | Piloto hecho en DESPACHOB (15 emisores, viable). Extracción general hecha aquí: 240 CIK |
| — c1j (efecto de §7 por separado) | Hecho: la candidata no cambia nada (n 767, t 2,57) |
| 3. Panel c2, tanda 1 c2 y su congelación | Hecho: `data/version_c2_freeze.json`, `data/etapa1_tanda1c2_frozen.json` |
| 4. Comparación de las 72 candidatas | Hecho: `data/etapa1_tanda1c2_conciliacion.json` |
| 5. Tanda 2 y su congelación | Hecho: `data/etapa1_tanda2c2_frozen.json` (0 elegidas) |
| 6. Alto e informe | Este documento |

## 2. Varias clases de acciones (§3 de la enmienda)

- Extracción general: 240 CIK. 198 tienen al menos una presentación 10-K/10-Q en su ventana. **42 no tienen
  ninguna**, por límites del dato, no de la descarga:
  - Bancos que presentan sus informes ante su regulador, no ante la SEC: First Republic, Signature, Bank of the
    Ozarks, Cadence.
  - Empresas cuyo 10-K está bajo otro CIK, como una matriz nueva o un sucesor: Veradigm, TechTarget, L3.
  - Empresas en liquidación o absorbidas en la ventana, como Altaba.
  Como prevé la regla, esos días quedan sin talla.
- Panel c2 (`data/v4c2_multiclass.json`):
  - Emisores sin XBRL: 142.
  - Clase no identificada: 28.
  - Clase identificada: 173.
  - Valor-días sin capitalización con cota calculable (2016-2026, todo el panel):
    - 69 975 con cota ≥ 10 000 M$: pasan a «grande»;
    - 122 276 con cota < 10 000 M$: siguen sin talla, porque una cota inferior no basta para asignar otra talla.
- Efecto en la tanda 1 (2018-2020):
  - 18 653 valor-días pasan de «sin capitalización» a «grande» (31 empresas).
  - Ningún otro cambio de talla.
  - Las mismas 833 902 filas.

## 3. La candidata, versión a versión

| Versión | Episodios | Semanas | Exceso 20 ses. | t | Mitades | IC 95 % (bloques 60) |
|---|---:|---:|---:|---:|---|---|
| Original (v4) | 739 | 96 | +2,05 pp | 2,70 | +1,37 / +2,89 | +0,90 a +3,36 |
| c1 (enmienda 1) | 767 | 100 | +2,13 pp | 2,57 | +1,39 / +3,05 | +0,92 a +3,68 |
| c1j (c1 + §7 nueva) | 767 | 100 | +2,13 pp | 2,57 | +1,39 / +3,06 | +0,91 a +3,69 |
| **c2** | **805** | **101** | **+2,11 pp** | **2,57** | **+1,31 / +3,14** | **+0,89 a +3,53** |

Las cotas de §4.2 dan +2,15 y +2,10 pp; no hay episodios de valor desconocido.

Los mayores cambios de t entre c1 y c2 están todos en celdas «sin capitalización» (por ejemplo, sin cap. / −10 / 20 /
bajista pasa de +0,49 a −2,58, con 166 → 118 episodios). Es lo esperable: c2 saca de esa población a 31 empresas
grandes. Ninguna celda «sin capitalización» puede elegirse para la etapa 2 (son solo descriptivas).

## 4. La celda nueva: grandes / Flow < −30 / 20 / lateral — DECIDE TÚ

| | Episodios | Semanas | Exceso | t | Mitades |
|---|---:|---:|---:|---:|---|
| grandes / −30 / 20 / **todos** | 805 | 101 | +2,11 pp | 2,57 | +1,31 / +3,14 |
| grandes / −30 / 20 / **lateral** | 147 | 31 | +1,97 pp | 2,58 | +1,48 / +2,88 |

- Cumple todos los criterios del preregistro (§5) al pie de la letra: |t| ≥ 2,5, ≥ 100 episodios, ≥ 30 semanas,
  mismas mitades, mismas cotas, 0 % desconocidos. El preregistro no prohíbe celdas anidadas.
- Pero son **147 de los 805 episodios de la otra celda**: aporta muy poca información nueva, y queda justo en los
  límites (t 2,58; 31 semanas).
- Por la regla, ocupaba una de las 4 plazas: para pequeñas y micro quedaban 2 en vez de 3. **No ha tenido efecto**,
  porque la tanda 2 no tiene ninguna elegible.

Opciones:
- **a) Contarla (regla literal):** la etapa 2 lleva 2 celdas de grandes.
- **b) No contarla:** la etapa 2 lleva solo la celda «todos los regímenes». La lateral queda como desglose descriptivo
  dentro de ella. Mi recomendación: así no se gasta una prueba en un subconjunto casi sin información propia.

## 5. Tanda 2 (pequeñas y micro, desarrollo 2018-2022)

48 candidatas, 0 elegibles, 2 plazas disponibles (`data/etapa1_tanda2c2_selection.json`). Las de mayor |t|:

| Celda | Episodios | Semanas | Exceso | t | Falla en |
|---|---:|---:|---:|---:|---|
| micro / −30 / 40 / bajista | 216 | 51 | −5,44 pp | −3,33 | desconocidos 2,3 % (> 1 %) |
| micro / −30 / 20 / bajista | 216 | 51 | −3,86 pp | −3,14 | desconocidos 1,4 % |
| micro / −10 / 40 / lateral | 107 | 26 | −4,97 pp | −3,12 | < 30 semanas; desconocidos 1,9 % |
| micro / −10 / 40 / bajista | 148 | 43 | −7,78 pp | −2,67 | desconocidos 1,4 % |
| pequeñas / −30 / 20 / bajista | 1 448 | 74 | +1,75 pp | 2,38 | t < 2,5 |

- Las micro en mercado bajista con Flow muy negativo **siguen cayendo** frente a su talla. Pero tienen demasiados
  desenlaces desconocidos (empresas que desaparecen sin precio de salida) para pasar el filtro. Encaja con el sesgo
  ya documentado: en micro, lo que falta suele ser lo peor.
- Las pequeñas en mercado bajista apuntan en la misma dirección que las grandes (rebote), sin llegar al umbral.

## 6. Incidencias de esta sesión

- **Disco externo dañado al traerlo de DESPACHOB.** Probablemente se desconectó sin «Quitar hardware de forma segura».
  - `chkdsk D: /scan` encontró daños solo dentro de `flow_negative_v1`: `_state`, el índice de `work` y dos JSON de la SEC. Ningún sector defectuoso.
  - `chkdsk /spotfix` lo reparó.
  - Los dos JSON (Echo Global Logistics, SharkNinja) se descargaron de nuevo.
  - Además, 96 ficheros y dos carpetas creados en DESPACHOB llegaron con permisos solo de aquel usuario; se arreglaron con `takeown` + `icacls /reset`.
  - Comprobado después: 10 165 ficheros legibles y todos los parquet/JSON se abren.
- **Fallo de código en `s4_etapa1.py`.** Con `missing_j`, la columna `nl{H}` puede quedar entera booleana, y pandas 3
  no admite NaN en una columna booleana: la variante c1j de DESPACHOB no se había interrumpido, había fallado por
  esto. Se convierte a `object` antes de anular, igual que hacía pandas 2 por su cuenta: no cambia ningún resultado.
- `.env`: `python-dotenv` no puede leer la línea 13. Es un aviso que no afecta a nada de esto.

## 7. Lo que queda

1. Tu decisión sobre la celda lateral (§4).
2. Con eso, la selección para la etapa 2 queda cerrada: 1 o 2 celdas de grandes. La etapa 2 (y abrir la prueba) necesita
   tu autorización expresa.
