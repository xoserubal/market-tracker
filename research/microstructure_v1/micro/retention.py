"""Política de retención de datos crudos — configurable, por defecto conservarlo todo.

retention_config.json (en la carpeta del estudio):
  {"bars": {"policy": "keep_all"}, "trades": {"policy": "keep_all"}, "quotes": {"policy": "keep_all"}}
Políticas: keep_all | sample_fraction (conserva una fracción determinista por unidad, con semilla).
Decisión G1: piloto B1 = keep_all (100 % de los trades). Los JSON del API nunca se escriben a disco.
Nada se borra sin dry_run=False explícito; cada borrado queda en el manifiesto (status 'pruned').
"""
import hashlib
import json
from pathlib import Path

from . import config
from .manifest import Manifest

CONFIG_PATH = config.STUDY_DIR / "retention_config.json"
DEFAULT = {k: {"policy": "keep_all"} for k in ("bars", "trades", "quotes")}


def load() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT, indent=1), encoding="utf-8")
    return {**DEFAULT, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}


def _keep(unit_key: str, fraction: float, seed: int) -> bool:
    h = int(hashlib.sha256(f"{seed}|{unit_key}".encode()).hexdigest()[:12], 16)
    return h / 16 ** 12 < fraction


def prune(policy: dict = None, manifest: Manifest = None, dry_run: bool = True) -> dict:
    policy = policy or load()
    manifest = manifest or Manifest()
    report = {"dry_run": dry_run, "deleted_units": 0, "deleted_bytes": 0, "kept_units": 0}
    for kind, rule in policy.items():
        if rule.get("policy") == "keep_all":
            continue
        if rule.get("policy") != "sample_fraction":
            raise ValueError(f"política desconocida: {rule}")
        frac, seed = float(rule["fraction"]), int(rule["seed"])
        for r in manifest.rows("kind=? AND status='ok'", (kind,)):
            if _keep(r["unit_key"], frac, seed):
                report["kept_units"] += 1
                continue
            report["deleted_units"] += 1
            report["deleted_bytes"] += r["file_bytes"] or 0
            if not dry_run:
                Path(r["path"]).unlink(missing_ok=True)
                manifest.finish(r["unit_key"], "pruned", error=f"retención {rule}")
    return report
