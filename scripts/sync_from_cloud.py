"""
sync_from_cloud.py — Sincroniza archivos cloud-managed desde origin/master.

Los archivos listados en CLOUD_MANAGED son mantenidos exclusivamente por el
pipeline de GitHub Actions. Los runs locales deben leerlos en su versión
más reciente del remote, nunca sobreescribirlos con datos obsoletos.

Uso manual:
    py -3 scripts/sync_from_cloud.py

Se llama automáticamente desde paper_trading.py cuando no detecta GITHUB_ACTIONS.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Archivos que GitHub Actions mantiene actualizados.
# Los runs locales nunca deben generar versiones más antiguas de estos.
CLOUD_MANAGED = [
    "docs/data/prices_picks.json",          # precios actuales de posiciones abiertas
]


def sync(verbose: bool = True) -> bool:
    """
    Fetch origin/master y restaura los archivos CLOUD_MANAGED a su versión remota.
    Devuelve True si la sincronización fue exitosa.
    Solo modifica los archivos listados; no toca scripts ni ai_picks.json.
    """
    # 1. Fetch sin merge (no destructivo)
    r = subprocess.run(
        ["git", "fetch", "origin", "master", "--quiet"],
        cwd=ROOT, capture_output=True, timeout=20,
    )
    if r.returncode != 0:
        if verbose:
            print(f"  [sync-cloud] fetch failed: {r.stderr.decode().strip()}")
        return False

    # 2. Restaurar solo los archivos cloud-managed a su versión en origin/master
    updated = []
    for rel_path in CLOUD_MANAGED:
        r2 = subprocess.run(
            ["git", "checkout", "origin/master", "--", rel_path],
            cwd=ROOT, capture_output=True, timeout=10,
        )
        if r2.returncode == 0:
            updated.append(rel_path)
        else:
            if verbose:
                print(f"  [sync-cloud] no pudo restaurar {rel_path}: {r2.stderr.decode().strip()}")

    if verbose and updated:
        print(f"  [sync-cloud] {len(updated)} archivo(s) sincronizados desde origin/master: {updated}")

    return bool(updated)


if __name__ == "__main__":
    import sys
    ok = sync(verbose=True)
    sys.exit(0 if ok else 1)
