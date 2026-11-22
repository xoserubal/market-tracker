"""Pruebas de regresión de episode.load_trades tras la corrección del 2026-11-22 (sin red, datos sintéticos).

Fuera de tests/ por la misma razón que test_e3_integrity.py: no se puede cambiar la batería del piloto E3 mientras dure.
Fijan las dos conductas (corregida y anterior, `legacy_overlap_dedupe=True`) sobre un mismo caso pensado para separar
cada regla, y comprueban que los consumidores de G1.5 y de E1 usan la carga corregida.

Caso: dos unidades de trades que se solapan entre 10:00 y 10:30 NY.
  U1 09:30-10:30:  a, b  mismo contenido (t, mercado, precio, tamaño, condiciones, cinta), identificador distinto
                   c, d  mismo identificador y contenido, d 2 ms después (repetición difundida, como NVDA 2020-11-27)
                   e     mismo identificador que c pero en otro mercado (los identificadores son por mercado: legítima)
                   g     en el tramo solapado; vuelve a venir en U2 con el mismo identificador
                   f     en el tramo solapado, solo en U1
  U2 10:00-11:00:  g     (repetición entre unidades: se cuenta una vez)
                   h     mismo contenido que g e identificador distinto
                   k     solo en U2
"""
import ast
import sys
from pathlib import Path

import pandas as pd
import pytest

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY))
sys.path.insert(0, str(STUDY / "tests"))
from micro import episode  # noqa: E402
from micro.download import config_for, download_unit  # noqa: E402
from micro.manifest import Manifest  # noqa: E402
from test_micro import Resp, data_dir, provider  # noqa: E402,F401

DAY = "2026-11-13"
T0 = pd.Timestamp("2026-11-13T14:30:00Z")          # 09:30 NY


def tr(sec, p, s, i, x="Q", c=(" ",)):
    return {"t": (T0 + pd.Timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "p": p, "s": s, "x": x,
            "c": list(c), "z": "C", "i": i}


A, B = tr(5, 100.0, 100, 1), tr(5, 100.0, 100, 2)
C, D = tr(10, 100.1, 50, 3), tr(10.002, 100.1, 50, 3)
E = tr(12, 100.1, 50, 3, x="K")
G, H = tr(2000, 100.2, 300, 5), tr(2000, 100.2, 300, 6)
F = tr(3500, 100.3, 200, 4)
K = tr(4000, 100.4, 400, 7)


def unit(trades, rng):
    pr = provider([Resp(200, {"trades": trades, "next_page_token": None})])
    download_unit(pr, "trades", "TST", DAY, cfg=config_for("trades", session="full", time_range=rng), manifest=Manifest())


@pytest.fixture
def two_units(data_dir):
    unit([A, B, C, D, E, G, F], "09:30-10:30")
    unit([G, H, K], "10:00-11:00")
    return data_dir


def keys(df):
    """Identidad de cada fila cargada: (segundos desde 09:30, mercado, tamaño)."""
    return sorted((round((t - T0).total_seconds(), 3), x, int(s)) for t, x, s in zip(df["t"], df["exchange"], df["size"]))


def k(t):
    return (round(pd.Timestamp(t["t"]).tz_convert("UTC").timestamp() - T0.timestamp(), 3), t["x"], t["s"])


@pytest.mark.parametrize("kw,expected,removed", [
    # corregida: solo se quitan repeticiones entre unidades solapadas, con el identificador en la clave
    ({}, [A, B, C, D, E, G, H, F, K], 0),
    # corregida + identificadores (E1): además se quita d (mismo mercado, identificador, precio, tamaño y condiciones)
    ({"dedupe_ids": True}, [A, B, C, E, G, H, F, K], 1),
    # anterior: se quitaban siempre las filas iguales en (t, mercado, precio, tamaño, condiciones, cinta)
    ({"legacy_overlap_dedupe": True}, [A, C, D, E, G, F, K], 0),
    ({"legacy_overlap_dedupe": True, "dedupe_ids": True}, [A, C, E, G, F, K], 1),
])
def test_rules_on_the_reference_case(two_units, kw, expected, removed):
    df, cov = episode.load_trades("TST", DAY, **kw)
    assert keys(df) == sorted(k(t) for t in expected)
    assert df.attrs["duplicate_ids_removed"] == removed
    assert len(cov) == 1                                            # ventanas fusionadas: 09:30-11:00
    assert df["t"].is_monotonic_increasing


def test_volume_difference_is_exactly_the_identical_trades(two_units):
    new, _ = episode.load_trades("TST", DAY)
    old, _ = episode.load_trades("TST", DAY, legacy_overlap_dedupe=True)
    assert new["size"].sum() - old["size"].sum() == B["s"] + H["s"]


def test_single_unit_never_deduplicates_by_default(data_dir):
    """Con una sola unidad no hay solape posible: ni siquiera una fila idéntica con el mismo identificador se quita
    (solo dedupe_ids la quita). Fija la conducta; el proveedor no devuelve filas así dentro de una misma descarga."""
    unit([A, A, B], "09:30-10:30")
    assert len(episode.load_trades("TST", DAY)[0]) == 3
    assert len(episode.load_trades("TST", DAY, dedupe_ids=True)[0]) == 2
    assert len(episode.load_trades("TST", DAY, legacy_overlap_dedupe=True)[0]) == 1


@pytest.mark.parametrize("hhmm,expected", [
    (("10:20", "10:40"), [F, K]),                   # toca las dos unidades; se recorta a la ventana
    (("10:35", "10:50"), [K]),                      # solo U2: una unidad, sin deduplicación entre unidades
    (("09:30", "09:31"), [A, B, C, D, E]),
])
def test_window_reads_only_overlapping_units_and_clips(two_units, hhmm, expected):
    from micro import calendar
    w = calendar.ny_range(DAY, *hhmm)
    df, _ = episode.load_trades("TST", DAY, window=w)
    assert keys(df) == sorted(k(t) for t in expected)


def test_output_schema_is_unchanged(two_units):
    df, _ = episode.load_trades("TST", DAY)
    assert list(df.columns) == ["t", "price", "size", "exchange", "tape", "upd_oc", "upd_hl", "upd_vol", "auction",
                                "nonstandard", "cond_odd_lot", "conditions", "canceled", "odd_lot", "trf", "session"]
    assert "i" not in df.columns


# ── consumidores ───────────────────────────────────────────────────────────────────────────────────────────────
CONSUMERS = {                                       # archivo: dedupe_ids esperado en cada llamada
    "g15_case_study.py": [False], "g15_classifier_comparison.py": [False], "ev_case_sheet.py": [False],
    "micro/drilldown.py": [True, True], "micro/window_access.py": [True], "lab/server.py": [False, True],
    "vp1_pilot.py": [True],
}
# micro/vp_observed.py no usa load_trades: lee por lotes y evita el doble conteo entre unidades por tiempo (cada tramo
# cubierto por una unidad anterior se descarta), sin deduplicar identificadores repetidos (ver ESTRUCTURAS_METODO.md).


def calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", None)) == "load_trades":
            out.append({kw.arg: (kw.value.value if isinstance(kw.value, ast.Constant) else "expr") for kw in n.keywords})
    return out


@pytest.mark.parametrize("rel", sorted(CONSUMERS))
def test_consumers_use_the_corrected_loader(rel):
    cs = calls(STUDY / rel)
    assert cs, f"{rel} ya no llama a load_trades: revisar la lista de consumidores"
    assert all(c.get("legacy_overlap_dedupe") in (None, False) for c in cs), f"{rel} fija la carga anterior"
    if CONSUMERS[rel] is not None:
        assert [bool(c.get("dedupe_ids")) for c in cs] == CONSUMERS[rel]


def test_no_other_consumer_pins_the_legacy_loader():
    """Fuera de las pruebas, nadie debe usar legacy_overlap_dedupe=True sin que esta prueba lo sepa."""
    hits = []
    for p in STUDY.rglob("*.py"):
        skip_dir = any(s in p.parts for s in ("tests", "tests_extra", "__pycache__"))
        if skip_dir or p.name in ("episode.py", "loader_correction_diff.py"):   # la comparación usa las dos cargas
            continue
        if any(c.get("legacy_overlap_dedupe") not in (None, False) for c in calls(p)):
            hits.append(str(p.relative_to(STUDY)))
    assert hits == [], hits


def test_loader_correction_diff_smoke(two_units):
    import loader_correction_diff as L
    rows = L.compare("TST", DAY, "E1 ficha prueba", (False, True))
    assert [r["dedupe_ids"] for r in rows] == [False, True]
    assert rows[0]["trades_legacy"] == 7 and rows[0]["trades_corrected"] == 9
    assert rows[0]["volume_diff"] == B["s"] + H["s"] and not rows[0]["has_quotes"]
    assert rows[1]["duplicate_ids_removed_corrected"] == 1
    s = L.summarize(pd.DataFrame(rows))
    assert s["compared"] == 2 and s["E1 ficha | dedupe_ids=False"]["with_any_change"] == 1
    assert L.compare("TST", "2023-05-10", "x", (False,))[0]["skipped"] == "periodo reservado de G2A"
