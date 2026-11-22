"""Aislamiento de las pruebas respecto del estado del equipo (2026-11-21).

El laboratorio rechaza cargar datos si quedan menos de RESERVE_MB (2,5 GB) de memoria libre: es su protección, a
propósito. Con el equipo cargado (un recálculo grande, otras aplicaciones) eso hacía fallar pruebas del laboratorio que
no prueban la protección. Aquí la memoria libre se fija en un valor amplio; la prueba de la propia protección
(test_g2_controls::test_lab_memory_guard_refuses_instead_of_loading) la vuelve a sustituir dentro de la prueba.
"""
import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1] / "lab"


@pytest.fixture(autouse=True)
def _lab_memory_independent_of_machine(monkeypatch):
    if str(LAB) not in sys.path:
        sys.path.insert(0, str(LAB))
    import server
    monkeypatch.setattr(server, "_avail_mb", lambda: 1e9)
