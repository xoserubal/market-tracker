# Pendiente para la próxima sesión en LAWNMOWER

Dejado el 2026-11-19 desde DESPACHOB. Al empezar una sesión en LAWNMOWER (`hostname`), Claude debe recordar al
usuario todo lo de abajo antes de hacer otra cosa. Cuando esté resuelto, borrar este archivo y la línea de aviso al
principio de `CLAUDE.md`.

## 1. Estudio Flow negativo — firmar el preregistro v3

Borrador sin firmar: `wiki/PREREGISTRO_FLOW_NEGATIVO_V3.md`. Las etapas 1-2 siguen sin autorizar: no calcular ningún
rendimiento posterior hasta que se firme.

Decidido el 2026-11-19: el desarrollo de las pequeñas va de 2018 a 2022 y la prueba empieza en 2023. Grandes,
medianas y «sin capitalización»: desarrollo 2018-2020, prueba desde 2021.

**El usuario tiene que confirmar los 4 puntos de §12.2:**
1. Las micro siguen el mismo periodo que las pequeñas (desarrollo 2018-2022).
2. H1 da veredicto solo para grandes, medianas y pequeñas. Micro y «sin capitalización» quedan como descriptivas.
3. Coste supuesto de las micro: 1,5 % ida y vuelta.
4. La etapa 1 va en dos tandas. Primero 2018-2020, congelando grandes, medianas y «sin capitalización». Después, los
   días de 2021-2022 de pequeñas y micro.

**Pasos en LAWNMOWER, una vez confirmados los cuatro puntos:**
1. Adaptar `research/flow_negative_v1/fn_config.py`: `DEV_END` hoy define los periodos por índice
   (`{"sp500": "2020-12-31", "sp400": "2020-12-31", "sp600": "2022-12-31"}`) y debe pasar a definirlos por talla de
   capitalización, como dice §2.2 del preregistro.
2. Calcular los SHA-256 de la lista de §13: código, `data/*` y, en `D:\backup market tracker\flow_negative_v1`,
   `panel_v4.parquet`, `companies_v4.csv` y `company_links_v4.csv`. Escribirlos en el preregistro y firmarlo.
3. Antes de lanzar la etapa 1, pedir autorización explícita.

El panel v4 solo está en el disco D: de LAWNMOWER. DESPACHOB solo tiene hasta la v3.

## 2. Otros cabos sueltos

- `llm1.docx` en la raíz del repo, sin seguimiento. Decidir si se deja, se borra o se añade a `.gitignore`.
- `portfolio.json` y `docs/data/baseline_comparison.json` estaban modificados en DESPACHOB sin commitear. No son de
  este trabajo: no tocarlos sin preguntar.
