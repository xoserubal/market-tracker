"""Congelación del preregistro v3 del estudio de Flow negativo (§13).

Uso:
  py -3 s3_freeze_v3.py            # calcula los hashes e imprime la tabla markdown para §13.1
  py -3 s3_freeze_v3.py --write    # además guarda data/preregistro_v3_freeze.json (incluye el hash del documento)
  py -3 s3_freeze_v3.py --verify   # comprueba que todo sigue igual que en data/preregistro_v3_freeze.json

Ficheros del repo: SHA-256 con los saltos de línea normalizados a LF (git usa autocrlf, así el hash es el mismo en
cualquier equipo). Ficheros de fuera del repo (FLOWNEG_DATA_DIR/work): SHA-256 de los bytes tal cual.
El documento del preregistro no puede contener su propio hash: va solo en el JSON.
"""
import hashlib
import json
import sys
from pathlib import Path

import fn_config as C

DOC = C.REPO / "wiki" / "PREREGISTRO_FLOW_NEGATIVO_V3.md"
OUT = C.PUB / "preregistro_v3_freeze.json"

CODE = (["fn_config.py", "s3_freeze_v3.py"] + sorted(p.name for p in C.HERE.glob("s0_*.py"))
        + ["s1_extend.py", "s1_sic.py", "s1_panel.py", "s1_stats.py"]
        + sorted(p.name for p in C.HERE.glob("s2_*.py")) + ["s3_validate_v4.py"])
DATA_REPO = ["membership.csv", "changes.csv", "membership_etf_sp400.csv", "terminal_events_v4.csv",
             "sic_gics_rules.csv", "sic_sector_by_cik.csv", "v4_h1_frozen_cuts.json"]
DATA_EXT = ["panel_v4.parquet", "companies_v4.csv", "company_links_v4.csv"]


def sha_text(p):
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def sha_bin(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute():
    rows = [("código", f"research/flow_negative_v1/{n}", sha_text(C.HERE / n)) for n in CODE]
    rows += [("datos repo", f"research/flow_negative_v1/data/{n}", sha_text(C.PUB / n)) for n in DATA_REPO]
    rows += [("datos externos", f"work/{n}", sha_bin(C.WORK / n)) for n in DATA_EXT]
    return rows


def main():
    rows = compute()
    if "--verify" in sys.argv:
        ref = json.loads(OUT.read_text(encoding="utf-8"))
        bad = [(f, ref["files"].get(f), h) for _, f, h in rows if ref["files"].get(f) != h]
        if sha_text(DOC) != ref["document_sha256"]:
            bad.append(("documento", ref["document_sha256"], sha_text(DOC)))
        print("OK: todo coincide" if not bad else "\n".join(f"DIFIERE {f}: {a} != {b}" for f, a, b in bad))
        sys.exit(1 if bad else 0)
    print("| Tipo | Fichero | SHA-256 |\n|---|---|---|")
    for t, f, h in rows:
        print(f"| {t} | `{f}` | `{h}` |")
    if "--write" in sys.argv:
        OUT.write_text(json.dumps({"document": "wiki/PREREGISTRO_FLOW_NEGATIVO_V3.md",
                                   "document_sha256": sha_text(DOC),
                                   "normalization": "repo: CRLF->LF; externos: bytes",
                                   "external_dir": str(C.DATA),
                                   "files": {f: h for _, f, h in rows}}, indent=1, ensure_ascii=False),
                       encoding="utf-8")
        print(f"\nGuardado {OUT}")


if __name__ == "__main__":
    main()
