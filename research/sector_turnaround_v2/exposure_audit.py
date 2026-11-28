"""Auditoría de exposición previa de los ETFs candidatos (preregistro v2, §8).

Busca cada ticker como palabra completa en ficheros de texto del repositorio y como valor real (columnas o
columna ticker/symbol) en los parquet/csv de datos. No mira precios ni resultados: solo si el ticker aparece.
Salida: exposure_audit.json. Uso: py -3 exposure_audit.py
"""
import json, re, sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
CANDIDATES = ["IYT", "XTN", "SMH", "XSD", "XSW", "PAVE", "FXR", "IYM", "XME", "SLX", "XOP", "OIH", "XES", "XPH",
              "IHE", "IHI", "XHE", "XHS", "PBJ", "IBB", "IDU", "IYZ", "KBE", "KRE", "IAT", "KIE", "XHB", "ITB",
              "XRT", "CARZ", "VNQ", "IYR", "FCG", "IYW", "IYJ"]
SKIP_DIRS = {".git", "node_modules", "_work", "__pycache__", ".pytest_cache"}
SKIP_FILES = {"PREREGISTRO_GIRO_SECTORES_REZAGADOS_V1.md", "PREREGISTRO_GIRO_SECTORES_REZAGADOS_V2.md",
              "exposure_audit.py", "exposure_audit.json"}
TEXT = {".py", ".js", ".html", ".md", ".json", ".yaml", ".yml", ".txt", ".csv", ".jsonl", ".ts"}
pat = re.compile(r"(?<![A-Za-z0-9_.=^-])(" + "|".join(CANDIDATES) + r")(?![A-Za-z0-9_])")
hits = {t: set() for t in CANDIDATES}


def rel(p):
    return str(p.relative_to(REPO)).replace("\\", "/")


for p in REPO.rglob("*"):
    if any(part in SKIP_DIRS for part in p.parts) or not p.is_file() or p.name in SKIP_FILES:
        continue
    if "Copia en conflicto" in p.name:
        continue
    suf = p.suffix.lower()
    try:
        if suf in TEXT and p.stat().st_size < 200_000_000:
            for m in pat.finditer(p.read_text(encoding="utf-8", errors="ignore")):
                hits[m.group(1)].add(rel(p))
        elif suf == ".parquet":
            import pyarrow.parquet as pq
            f = pq.ParquetFile(p)
            names = set(f.schema_arrow.names)
            for nm in names:                      # columnas tipo 'VNQ' o "('VNQ', 'Close')"
                for m in pat.finditer(str(nm)):
                    hits[m.group(1)].add(rel(p) + " [columna]")
            for c in ("ticker", "symbol", "Ticker", "asset", "etf"):
                if c in names:
                    vals = set(pd.read_parquet(p, columns=[c])[c].astype(str).unique())
                    for t in CANDIDATES:
                        if t in vals or f"{t}.US" in vals:
                            hits[t].add(rel(p) + f" [{c}]")
    except Exception as e:  # noqa: BLE001
        print("no leído:", rel(p), type(e).__name__, file=sys.stderr)

out = {t: sorted(v) for t, v in hits.items()}
Path(__file__).with_name("exposure_audit.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
for t in CANDIDATES:
    v = [x for x in out[t] if x != "CLAUDE.md"]
    print(f"{t:5s} {len(v):3d}  {'; '.join(v[:4])}")
