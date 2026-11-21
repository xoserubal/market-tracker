# Retomar la enmienda 2 (pausado 2026-11-20 19:45, en DESPACHOB)

> **Obsoleto.** La enmienda 2 se completó el 2026-11-21 y el estudio está cerrado: ver `INFORME_CIERRE.md`. Esta nota
> se conserva como registro del traspaso entre equipos.

Nota de trabajo para continuar en LAWNMOWER. Instrucciones del usuario (2026-11-20): IBKR ya commiteado (`5935469b`,
sin push); Flow negativo **sin commits ni pushes**; no abrir la prueba; parar tras la tanda 2 y entregar el informe.

## Hecho
- `wiki/ENMIENDA_2_FLOW_NEGATIVO_V3.md` redactada y congelada (`data/enmienda2_freeze.json`).
- `s4_etapa1.py`: familia `missing_j` (§7 solo para saltos indeterminados y escisiones; terminales con último cierre y
  cotas) y `FN_FREEZE=1` (congelación real `etapa1_tanda{n}{sufijo}_frozen.json`; la tanda 2 lee la tanda 1 corregida).
- `s1_panel.py`: familia `multiclass` (cota inferior = acciones de la propia clase × precio; solo asigna «grande»).
- `s7_xbrl_classes.py` (extractor XBRL por clase), `s7_pilot_report.py`, `s8_conciliacion_c2.py`, `s8_freeze_c2.py`.
- Piloto (15 emisores): viable. `data/enmienda2_pilot.json`. Todos con clase identificada; MSTR y unos días de LEN y
  EXPE quedan por debajo de 10 000 M$ (sin talla, como prevé la regla).
- Extracción general: lista en `work/enmienda2_multiclass_ciks.csv` (240 CIK). Hecha solo para 3 CIK + los 15 del
  piloto (`sec/xbrl_classes/`, 18 ficheros, todos válidos).
- La variante c1j se interrumpió: hay que repetirla (no dejó resultados).

## Pendiente (en este orden)
En LAWNMOWER el disco externo es D:; `fn_config.py` lo elige solo. Si `py -3` falla por paquetes, usar `py -3.12`.
Desde `research/flow_negative_v1/`, con `PYTHONIOENCODING=utf-8`:

1. Extracción general (reanudable, ~2 h): `py -3 -u s7_xbrl_classes.py --list > "D:/backup market tracker/flow_negative_v1/work/s7_general.log"`
2. c1j (efecto aislado de §7): `FN_OUT=c1j FN_PANEL=v4c1sic FN_CORR=splits,identity,cik,spinoffs,jumps,terminals,missing_j py -3 s4_etapa1.py --tanda 1`
3. Panel c2: `FN_TAG=v4c2 FN_CORR=splits,identity,cik,multiclass py -3 s1_panel.py` (escribe `data/v4c2_multiclass.json`).
4. Congelar c2: `py -3 s8_freeze_c2.py`.
5. Tanda 1 c2, congelada: `FN_OUT=c2 FN_PANEL=v4c2 FN_FREEZE=1 FN_CORR=splits,identity,cik,spinoffs,jumps,terminals,missing_j py -3 s4_etapa1.py --tanda 1`
6. Comparación: `py -3 s8_conciliacion_c2.py` (72 candidatas; ¿grandes / Flow < −30 / 20 sigue pasando?).
7. Si no hay cambios materiales inesperados, tanda 2 (mismas variables que el paso 5, `--tanda 2`).
8. Informe completo + selección definitiva al usuario. Alto. La prueba sigue cerrada.

## Estado 2026-11-21 (LAWNMOWER): pasos 1-7 HECHOS
Informe: `ENMIENDA2_INFORME.md`. Pendiente solo la decisión del usuario sobre la celda anidada grandes/−30/20/lateral
(§4 del informe) y, después, autorizar la etapa 2. Nota: c1j no se había interrumpido en DESPACHOB; fallaba por un
`nl{H}` booleano con pandas 3 (corregido en s4_etapa1.py).
