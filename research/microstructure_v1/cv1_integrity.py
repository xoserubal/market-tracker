"""cat-v1 — huella de las capas que la implantación NO puede tocar, antes y después (aprobación §4).

Capas comprobadas (en MICRO_DATA_DIR):
- capa 1: raw/ (barras, trades, quotes): ruta, tamaño y fecha de modificación de cada fichero (16,8 GB: hash completo
  sería lento, y un cambio de contenido cambia tamaño o fecha); manifest/ y reference/ con sha256 completo;
- capa 2: features/e2_measures y features/e2_norm con sha256 completo;
- capa 3 de cat-v0: events/ (salvo events/cat-v1) y results/e2_alerts_M*.parquet, e2_report.json, e2b_criteria.json,
  e2c_*: sha256 completo.

Uso: py -3 cv1_integrity.py snapshot --tag before · py -3 cv1_integrity.py compare --a before --b after
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import storage  # noqa: E402

ROOT = storage.root()
FULL_HASH = ["manifest", "reference", "features/e2_measures", "features/e2_norm", "events"]
RESULT_FILES = ["e2_alerts_M0.parquet", "e2_alerts_M1.parquet", "e2_alerts_M2.parquet", "e2_report.json",
                "e2b_criteria.json", "e2c_window_audit.json", "e2c_audit_alerts.parquet", "e2c_audit_episodes.parquet"]
EXCLUDE = ("events/cat-v1",)


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def snapshot(tag: str) -> Path:
    out = {"root": str(ROOT), "stat_only": {}, "sha256": {}}
    for p in (ROOT / "raw").rglob("*"):
        if p.is_file():
            st = p.stat()
            out["stat_only"][_rel(p)] = [st.st_size, st.st_mtime_ns]
    for d in FULL_HASH:
        for p in sorted((ROOT / d).rglob("*")):
            r = _rel(p)
            if p.is_file() and not r.startswith(EXCLUDE) and not p.name.endswith(("-wal", "-shm", "-journal")):
                out["sha256"][r] = _sha(p)
    for n in RESULT_FILES:
        p = ROOT / "results" / n
        if p.exists():
            out["sha256"][_rel(p)] = _sha(p)
    dst = ROOT / "results" / f"cv1_integrity_{tag}.json"
    dst.write_text(json.dumps(out), encoding="utf-8")
    print(f"{dst}: {len(out['stat_only'])} ficheros de raw (tamaño+fecha), {len(out['sha256'])} con sha256")
    return dst


def compare(a: str, b: str) -> dict:
    A = json.loads((ROOT / "results" / f"cv1_integrity_{a}.json").read_text(encoding="utf-8"))
    B = json.loads((ROOT / "results" / f"cv1_integrity_{b}.json").read_text(encoding="utf-8"))
    res = {}
    for k in ("stat_only", "sha256"):
        x, y = A[k], B[k]
        res[k] = {"files_before": len(x), "files_after": len(y),
                  "changed": sorted(p for p in x if p in y and x[p] != y[p]),
                  "removed": sorted(set(x) - set(y)), "added": sorted(set(y) - set(x))}
    res["unchanged"] = all(not res[k]["changed"] and not res[k]["removed"] for k in res)
    print(json.dumps(res, indent=1, ensure_ascii=False)[:4000])
    return res


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("snapshot")
    s.add_argument("--tag", required=True)
    c = sp.add_parser("compare")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    a = ap.parse_args()
    snapshot(a.tag) if a.cmd == "snapshot" else compare(a.a, a.b)


if __name__ == "__main__":
    main()
