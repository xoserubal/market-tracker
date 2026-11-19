# Flow negativo — empresas desaparecidas y resultados terminales (etapa 0)

Fecha: 2026-11-18. Sin rendimientos posteriores a ninguna señal. Datos: `data/terminal_events.csv` (una fila por
serie que termina: fecha, categoría, fuente, términos y estado del valor de salida; sin precios),
`data/terminal_summary.json` y `data/terminal_impact.json`. La versión con el último cierre y el valor de salida está
fuera del repo (`work/terminal_events_full.csv`), por la licencia de Alpaca. Scripts: `s0_terminal.py`, `s0_terminal_impact.py`.

## 1. Principio

Que Alpaca conserve la cotización de una empresa desaparecida no dice cuánto recibió el accionista. El último cierre
no se usa como rentabilidad final por defecto: cada fin de serie se clasifica y, si el valor de salida no se conoce,
queda marcado como desconocido. Nunca se rellena con una cifra presentada como real.

## 2. Procedimiento determinista (por orden)

1. **Acciones corporativas de Alpaca**, de cualquier símbolo de la empresa, entre 10 días antes y 40 después del fin:

   | Registro | Categoría | Valor de salida |
   |---|---|---|
   | Fusión en efectivo | Adquisición en efectivo | Precio pagado (conocido) |
   | Fusión en acciones | Adquisición en acciones | Ratio × cierre del comprador en la fecha efectiva |
   | Fusión mixta | Adquisición mixta | Efectivo + ratio × cierre del comprador |
   | Baja sin valor | Quiebra/liquidación | 0 |
   | Cambio de nombre | Cambio de ticker | No es un desenlace: se sigue con la serie sucesora |

2. **Misma empresa con otro ticker** (mismo CIK de la SEC y serie que continúa): cambio de ticker. Cubre los anteriores
   a 2020, que Alpaca no registra (CBS→VIAC, HCN→WELL, CBG→CBRE, COH→TPR, APY→ChampionX…).
3. **Motivo de la baja en la tabla de cambios de Wikipedia** (mismo ticker, ±45 días), por palabras clave: quiebra
   (incluye «receivership»), escisión, exclusión/OTC, cambio de ticker, fusión, adquisición de tipo desconocido.
   Valor: desconocido.
4. Si no hay nada: fin de serie por causa desconocida. Valor: desconocido.
5. **Control de coherencia:** si los términos de Alpaca se alejan más de un 25 % del último cierre, no se aceptan
   (valor desconocido). Casos:
   - Meredith: 16,99 $ registrados frente a 59 $ de cierre; era una escisión con pago parcial.
   - iStar.
   - Paramount.
   - Uno más.

## 3. Resultado (solo series con días de pertenencia a algún índice: 540)

| Categoría | Casos | Valor conocido | Desconocido | No aplica |
|---|---|---|---|---|
| Adquisición en efectivo | 157 | 154 | 3 (términos incoherentes) | — |
| Adquisición de tipo desconocido (Wikipedia) | 123 | 0 | 123 | — |
| Cambio de ticker | 114 | — | — | 114 |
| Adquisición en acciones | 64 | 58 | 6 (1 con términos incoherentes) | — |
| Adquisición mixta | 36 | 22 | 14 | — |
| Fin con baja del índice sin motivo clasificable | 18 | 0 | 18 | — |
| Desconocido | 16 | 0 | 16 | — |
| Quiebra/liquidación | 7 | 0 | 7 | — |
| Fusión | 3 | 0 | 3 | — |
| Escisión | 1 | 0 | 1 | — |
| Exclusión/OTC | 1 | 0 | 1 | — |
| **Total** | **540** | **234** | **192** | **114** |

- **Por año, valor conocido / desconocido:**

  | Años | Conocido | Desconocido |
  |---|---|---|
  | 2016 | 0 | 41 |
  | 2017 | 0 | 40 |
  | 2018 | 0 | 36 |
  | 2019 | 0 | 23 |
  | 2020 | 15 | 20 |
  | 2021-2026 | 219 | 32 |

  **Antes de 2020 ningún desenlace tiene valor conocido:** Alpaca no registra términos de fusión anteriores a esa
  fecha. Esto afecta de lleno al periodo de desarrollo de grandes y medianas (2018-2020).
- **Por índice (conocido / desconocido / cambio de ticker):**

  | Índice | Conocido | Desconocido | Cambio de ticker |
  |---|---|---|---|
  | S&P 500 | 48 | 73 | 46 |
  | S&P 400 | 94 | 113 | 55 |
  | S&P 600 | 145 | 36 | 36 |

- Las 19 adquisiciones en acciones o mixtas sin valor tienen un comprador que no está en ningún índice estudiado. **Se
  pueden resolver** descargando la serie del comprador (pendiente; no cambia ninguna conclusión de esta etapa).

### 3.1 ¿Cuánto se aleja el último cierre del valor real? (casos de 2020+ con términos conocidos)

| Tipo | Casos | Diferencia mediana | Percentil 90 | Máximo |
|---|---|---|---|---|
| Efectivo | 154 | 0,05 % | 0,35 % | 9,4 % (TEGNA) |
| Acciones | 58 | 1,3 % | 4,8 % | 8,1 % (GDEN) |
| Mixta | 22 | 0,8 % | 5,3 % | 6,3 % |

(diferencias en |ln(último cierre / valor de salida)|, sin los 4 casos de términos incoherentes)

En adquisiciones, el último cierre es una estimación muy buena del valor de salida: casi exacta en efectivo y con un
error típico del 1-5 % en acciones. **Esto no vale para quiebras ni para exclusiones**: ahí el accionista puede seguir
en el mercado OTC con un precio muy inferior, o recibir cero.

## 4. Impacto sobre las señales (días con Flow < 0, completo y sin evento, desde el inicio de señales)

Se cuenta una señal como afectada si el fin de la serie cae dentro de sus 40 sesiones siguientes.

| | S&P 500 | S&P 400 | S&P 600 |
|---|---|---|---|
| Días con Flow < 0 | 400 117 | 346 203 | 440 099 |
| Afectados, valor desconocido | 298 (0,07 %) | 284 (0,08 %) | 360 (0,08 %) |
| Afectados, valor conocido | 333 | 413 | 908 |
| Afectados por cambio de ticker (se sigue con la sucesora) | 536 | 591 | 567 |
| % de días con valor desconocido en la franja < −30 | 0,35 % | 0,01 % | 0,41 % |

**Episodios afectados por un desenlace de valor desconocido:**

| Umbral | S&P 500 | S&P 400 | S&P 600 |
|---|---|---|---|
| < −10 | 10 de 17 587 (0,06 %) | 10 de 15 402 (0,06 %) | 8 de 19 096 (0,04 %) |
| < −20 | 9 de 8 126 (0,11 %) | 7 de 8 466 (0,08 %) | 6 de 12 269 (0,05 %) |
| < −30 | 3 de 3 173 (0,09 %) | 1 de 3 853 (0,03 %) | 6 de 6 369 (0,09 %) |

- Por año, los días afectados de valor desconocido se concentran en 2018-2020 (grandes y medianas) y 2020 (pequeñas).
- En las franjas extremas lo que pesa son **quiebras** (S&P 500: 66 días; S&P 600: 97) y finales sin motivo
  clasificable. Es justo el caso en que el último cierre puede sobrestimar el resultado.

**Lectura:** el efecto potencial sobre medias de miles de episodios es muy pequeño. Puede importar en una celda
pequeña y extrema. Por eso el preregistro v2 exige que cada conclusión se mantenga entre las dos cotas (§5) y marca
toda celda con más del 1 % de episodios con valor desconocido.

## 5. Tratamiento propuesto para las etapas 1 y 2 (fijado antes de ver resultados)

| Situación | Valor que se usa | Sensibilidad / cota |
|---|---|---|
| Valor conocido | Ese valor en la fecha efectiva; después, 0 % hasta el plazo | — |
| Cambio de ticker | Serie sucesora (mismo CIK o cambio de nombre de Alpaca) | — |
| Adquisición sin valor conocido (tipo desconocido, acciones o mixta sin comprador) | Último cierre | Cota baja: último cierre × e^−0,05; cota alta: × e^+0,05 (percentil 90 del error medido en §3.1) |
| Quiebra, exclusión/OTC, escisión, términos incoherentes, fin desconocido | Último cierre (marcado) | **Cota baja: 0** (pérdida total desde la entrada); cota alta: último cierre |

- Una conclusión (reversión, peligro o descriptiva) solo vale si se mantiene con las dos cotas.
- Se publica siempre el % de episodios de cada celda con valor desconocido y una versión que los excluye.
- Nada se excluye en silencio: las tres versiones (estimación, cota baja, cota alta) se publican juntas.

## 6. Lo que no se puede resolver con las fuentes actuales

- **Continuidad OTC tras una exclusión o una quiebra:** Alpaca solo tiene mercado regulado. Sin fuente gratuita.
- **Términos de fusiones de 2016-2019:** posibles con la SEC (8-K y DEFM14A), pero no de forma determinista y barata.
  Con las cotas de §5 no hace falta para que el estudio sea válido.
- **Escisiones del S&P 400 y 600 anteriores a 2020:** no se registran; las mayores (> ~5 % del precio) dejan un salto
  visible (92 saltos sin explicar en 79 series, que se informan).
- **Épocas de SPAC antes de su fusión:** aparecen como fines de serie, pero son anteriores a la entrada en el índice y
  no generan señales. Quedan fuera de la tabla de §3 por no tener días de pertenencia.
