"""Comprobación posterior a la apertura (2026-11-21): H1 pequeñas con el embargo de la enmienda 1 §9.

La enmienda 1 §9 (aprobada 2026-11-20) fija la prueba propia de pequeñas y micro desde el 2023-03-02 (40 sesiones tras
el último cierre usado en desarrollo). La preparación de la etapa 2 lo omitió por error y decidió con el periodo
completo (2023-01-03 → 2026-09-17). Para grandes y medianas la versión con embargo (desde el 2021-03-03) ya está en los
resultados, como sensibilidad «excl_overlap_own_dev». Este script calcula la que falta, H1 pequeñas, con el mismo
código congelado (s9_etapa2.h1) y los mismos parámetros. No cambia ningún criterio: aplica el ya aprobado.

Salida: data/etapa2_embargo_check.json. Generador aleatorio propio (semilla 20261123): los intervalos no son los de la
ejecución principal, porque allí el generador ya había avanzado.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s9_etapa2 as E  # noqa: E402  (fija FN_PANEL/FN_OUT/FN_CORR al importarse)

E.RNG = np.random.default_rng(20261123)
EMBARGO_FROM = {"large": "2021-03-03", "mid": "2021-03-03", "small": "2023-03-02"}


def main():
    acc = [json.loads(l) for l in E.ACCESS.read_text(encoding="utf-8").splitlines()]
    rows_sha = [a["rows_sha"] for a in acc if a.get("event") in ("rows_built", "rows_reused")][-1]
    assert E.sha(E.TEST_ROWS) == rows_sha, "las filas de prueba no coinciden con las registradas"
    models, cells, cuts, dev = E.frozen()
    rows = E.load_rows([E.TEST_ROWS])
    out = {"rule": "enmienda 1 §9: embargo de 40 sesiones tras el último cierre de desarrollo",
           "rows_sha": rows_sha, "seed": 20261123, "H1": {}}
    for sz, d0 in EMBARGO_FROM.items():
        out["H1"][sz] = {"from": d0, **E.h1(rows[rows.date >= d0], sz, models, cuts)}
    p = E.C.PUB / "etapa2_embargo_check.json"
    p.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    print("→", p)


if __name__ == "__main__":
    main()
