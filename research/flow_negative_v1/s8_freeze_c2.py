"""Enmienda 2 §4.3 — congelación de la versión corregida definitiva (c2) ANTES de rehacer la tanda 1.

Guarda el SHA-256 de: documentos (preregistro v3, enmiendas 1 y 2), código, registros de la enmienda 1, piloto de
clases y, fuera del repo, el panel c2, sus tablas de empresas y el extracto XBRL por clases (hash conjunto).
Repo: saltos de línea normalizados a LF; externos: bytes.
Uso: py -3 s8_freeze_c2.py [--verify]  →  data/version_c2_freeze.json
"""
import hashlib
import json
import sys
from datetime import datetime, timezone

import fn_config as C

OUT = C.PUB / "version_c2_freeze.json"
REPO = [
    "wiki/PREREGISTRO_FLOW_NEGATIVO_V3.md", "wiki/ENMIENDA_1_FLOW_NEGATIVO_V3.md", "wiki/ENMIENDA_2_FLOW_NEGATIVO_V3.md",
    *[f"research/flow_negative_v1/{f}" for f in (
        "fn_config.py", "s0_series.py", "s1_panel.py", "s4_etapa1.py", "s5_cik.py", "s5_identity_audit.py",
        "s5_jumps.py", "s5_overlay.py", "s5_registries.py", "s5_spinoffs.py", "s7_xbrl_classes.py",
        "s7_pilot_report.py", "s8_conciliacion_c2.py", "s8_freeze_c2.py",
        "data/corr1_splits.csv", "data/corr1_jumps.csv", "data/corr1_spinoffs.csv", "data/corr1_identity.csv",
        "data/corr1_cik.csv", "data/corr1_cik_ranges.csv", "data/corr1_frame_extra.csv",
        "data/corr1_series_overlay.json", "data/enmienda1_freeze.json", "data/enmienda2_freeze.json",
        "data/enmienda2_pilot.json", "data/v4c2_multiclass.json", "data/v4_h1_frozen_cuts.json")],
]
EXT = ["work/panel_v4c2.parquet", "work/companies_v4c2.csv", "work/company_links_v4c2.csv"]


def h_repo(rel):
    return hashlib.sha256((C.REPO / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def h_ext(rel):
    h = hashlib.sha256()
    with open(C.DATA / rel, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def h_xbrl():
    h = hashlib.sha256()
    for f in sorted((C.SEC / "xbrl_classes").glob("*.json")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def compute():
    return {"repo": {r: h_repo(r) for r in REPO}, "external": {r: h_ext(r) for r in EXT},
            "external_sec_xbrl_classes": h_xbrl()}


if __name__ == "__main__":
    cur = compute()
    if "--verify" in sys.argv:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        bad = [k for sec in ("repo", "external") for k in old[sec] if old[sec][k] != cur[sec].get(k)]
        if old["external_sec_xbrl_classes"] != cur["external_sec_xbrl_classes"]:
            bad.append("sec/xbrl_classes")
        print("OK" if not bad else f"DIFERENCIAS: {bad}")
        sys.exit(1 if bad else 0)
    if OUT.exists():
        sys.exit(f"{OUT} ya existe: no se sobrescribe una congelación")
    cur["frozen_at"] = datetime.now(timezone.utc).isoformat()
    cur["note"] = ("Versión corregida definitiva c2 (enmienda 2), congelada antes de rehacer la tanda 1 y posterior "
                   "a la inspección de la tanda 1 original y c1.")
    OUT.write_text(json.dumps(cur, indent=1, ensure_ascii=False), encoding="utf-8")
    print("congelado", OUT)
