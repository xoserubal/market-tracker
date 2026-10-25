# Incidencia: RANKING_SHADOW_EXPERIMENTAL no puede elegir candidatos en el pipeline (checkout superficial de CI)

**Estado:** causa confirmada; corrección preparada en la rama `fix/ranking-lookback-snapshots` (commit `4b325e76`), **sin fusionar**.
**Prioridad:** bug funcional. La cartera experimental llevaba inactiva en CI desde que existe.
**Fecha:** 2026-10-25.

## Qué falla exactamente

`scripts/ranking_score_calculator.py` calcula `rot_score_delta_4w`, `streak_weeks_delta` y `theme_flow_delta` comparando cada candidato con su estado de hace ~28 días (ventana ±5). Esa referencia la buscaba solo en el historial de git, con dos consultas (reutilizadas de `reconstruct_pcs_components_historical.py`):

1. `git log --follow --format=%H|%ad --date=format:%Y-%m-%d -- docs/data/ai_candidates.json` → lista de commits y fechas.
2. `git show <commit>:docs/data/ai_candidates.json` → el JSON de esa fecha.

El workflow usa `actions/checkout` con `fetch-depth: 1`, así que la consulta 1 devuelve **un único commit (el de hoy)**. No hay ninguno en `hoy−28 ±5` y `get_lookback_candidates()` devuelve `{}` sin error ni aviso. Todos los deltas quedan en `None`.

## Efecto en los candidatos (medido en un clon `--depth 1` real)

| | Antes (git, superficial) | Después (snapshots) |
|---|---|---|
| Candidatos en la referencia de 28 días | 0 | 140 |
| Campos delta rellenos | 0 / 149 | 136 / 149 |
| `ranking_score_eligible = true` | **0 / 149** | **136 / 149** |

`ranking_score_eligible` exige que los 5 campos críticos estén presentes (`rot_score_delta_4w` es uno de ellos) y calidad de datos ≥ 0,80. Sin el delta, ninguno la alcanza. `ranking_score_experimental_portfolio.py` llama a `build_universe(..., require_ranking_eligible=True)`, por lo que **el universo de selección quedaba vacío en cada run de CI**. Las 5 posiciones abiertas de esa cartera se abrieron con `--force` en local, donde sí hay historial completo.

Quedan vacíos de forma estructural, y no tienen que ver con esto, `vehicle_vs_theme_strength` (nunca implementado) y 3-5 candidatos con datos técnicos incompletos.

## Profundidad mínima necesaria

Con el camino git, hace falta historial hasta `hoy − 33 días` (28 + 5 de ventana): unos **34 días**, con `--shallow-since`, que en este repo son ~150 commits y cientos de MB por run. No se eligió esa vía.

## Corrección (pequeña y aislada)

La referencia se lee de `docs/data/universe_snapshots/YYYY-MM-DD.json`, que `pcs_calculator.py` ya escribe cada día con el mismo contenido que `ai_candidates.json`, está versionado (132 ficheros, 23 MB desde el 2026-06-18) y **viaja en un checkout superficial**. El historial de git queda como alternativa. Misma ventana (28 días, ±5) y misma regla de desempate. **No cambia ninguna regla, peso ni umbral del experimento** y no toca el workflow.

## Paridad local / CI

- 102 fechas con ambas referencias: `rot_score`, `streak_weeks` y `B_theme_flow` idénticos.
- Limitación conocida y acotada: para recalcular fechas anteriores al 2026-07-16 (cuyo objetivo cae antes del primer snapshot, 18 de junio) el snapshot elige hasta 5 días más lejos que git. No afecta a ninguna ejecución actual.
- `scripts/test_ranking_lookback_parity.py` (16 tests en repo completo; 17 en un clon superficial, donde se activa el caso que reproduce el bug).

## Lo que cambia al fusionarla (decisión tuya)

La cartera empezará a operar de verdad en el pipeline: el script abre posiciones nuevas **solo los viernes** (salidas, todos los días) y, con los datos de hoy, el top-5 sería CVE, TMO, VRTX, TLW.L y KIST.L. Es el comportamiento diseñado en el preregistro, pero hoy no se produce. Cambia su muestra: el reloj de `wiki/PREREGISTRO_RANKING_SCORE_V0.md` (umbrales de piloto a 3 meses) debería contarse desde la primera operación real en CI, no desde el primer `--force`.

## Pendiente

Fusionar la rama; confirmar en el primer viernes tras el merge que el paso 10d2 abre posiciones y que `ranking_score_eligible` supera el 80 % en `ai_candidates.json`.
