"""Restauración de los artefactos de trabajo perdidos en el incidente del disco externo (22-nov-2026).

El estudio está CERRADO (INFORME_CIERRE.md). Esto no calcula ningún resultado nuevo: rehace ficheros intermedios que
existían y que se perdieron, y SOLO los da por buenos si coinciden byte a byte con los hashes registrados antes del
incidente. Si un fichero no coincide, se deja con otro nombre y se informa; nunca sustituye a nada.

Pasos (en orden; cada uno es independiente y repetible):
  panel     FN_TAG=v4c2 ... s1_panel.py  -> panel_v4c2.parquet, companies_v4c2.csv, company_links_v4c2.csv
            comprobados contra data/version_c2_freeze.json
  tanda1    s4_etapa1.py --tanda 1 con FN_OUT=c2r (la repetición del 21-nov; no toca ninguna congelación)
            filas comparadas con etapa1_tanda1c2_rows.parquet de data/etapa2_preparacion_freeze.json
            -> si coinciden, se copian también como etapa1_tanda1c2_rows.parquet
  tanda2    igual para la tanda 2
  c1j       la variante c1j (enmienda 2, efecto aislado de §7): no tiene hash registrado; se rehace y se informa
  devcheck  s9_etapa2.py --rebuild-dev-check (filas de desarrollo reconstruidas = congeladas)
  test      filas de PRUEBA: mismo constructor que --open-test (s9_etapa2.build_rows("test")), escritas aparte y
            aceptadas solo si su sha256 es el registrado en data/etapa2_acceso.jsonl (rows_built). Abre datos del
            periodo de prueba: se registra el acceso antes de leer. No ejecuta run() ni escribe resultados.

Uso:  py -3 s10_restaurar_incidente_disco.py panel tanda1 tanda2 c1j devcheck test
Informe: data/restauracion_incidente_disco.json (se va completando paso a paso).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fn_config as C  # noqa: E402

REPORT = C.PUB / "restauracion_incidente_disco.json"
CORR_FULL = "splits,identity,cik,spinoffs,jumps,terminals,missing_j"
PY = sys.executable


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {"steps": {}}


def save_step(name: str, rec: dict):
    rep = load_report()
    rep["steps"][name] = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **rec}
    REPORT.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(name, json.dumps(rec, ensure_ascii=False), flush=True)


def run(cmd: list, env_extra: dict, log_name: str) -> int:
    env = {**os.environ, **env_extra, "PYTHONIOENCODING": "utf-8"}
    for k in ("FN_FREEZE",):
        env.pop(k, None)
    log = C.WORK / log_name
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run([PY, "-u", *cmd], cwd=HERE, env=env, stdout=f, stderr=subprocess.STDOUT)
    print(f"  {' '.join(cmd)} -> código {r.returncode} en {time.time() - t0:.0f} s (log {log.name})", flush=True)
    return r.returncode


def step_panel():
    want = json.loads((C.PUB / "version_c2_freeze.json").read_text(encoding="utf-8"))["external"]
    rc = run(["s1_panel.py"], {"FN_TAG": "v4c2", "FN_CORR": "splits,identity,cik,multiclass"}, "panel_v4c2_stdout.log")
    got = {k: (sha(C.DATA / k) if (C.DATA / k).exists() else None) for k in want}
    save_step("panel", {"returncode": rc, "match": {k: got[k] == v for k, v in want.items()}, "sha256": got})


def step_tanda(n: int):
    freeze = json.loads((C.PUB / "etapa2_preparacion_freeze.json").read_text(encoding="utf-8"))["external"]
    want = freeze[f"work/etapa1_tanda{n}c2_rows.parquet"]
    rc = run(["s4_etapa1.py", "--tanda", str(n)], {"FN_OUT": "c2r", "FN_PANEL": "v4c2", "FN_CORR": CORR_FULL},
             f"etapa1_tanda{n}c2r_stdout.log")
    rows = C.WORK / f"etapa1_tanda{n}c2r_rows.parquet"
    got = sha(rows) if rows.exists() else None
    rec = {"returncode": rc, "rows_sha256": got, "expected": want, "match": got == want}
    cand = C.PUB / f"etapa1_tanda{n}c2r_candidate.json"
    if cand.exists():                         # subproducto de ejecutar sin FN_FREEZE: no existía antes
        cand.unlink()
    if got == want:
        dst = C.WORK / f"etapa1_tanda{n}c2_rows.parquet"
        shutil.copyfile(rows, dst)
        rec["copied_as"] = dst.name
        rec["copy_match"] = sha(dst) == want
    save_step(f"tanda{n}", rec)


def step_c1j():
    rc = run(["s4_etapa1.py", "--tanda", "1"], {"FN_OUT": "c1j", "FN_PANEL": "v4c1sic", "FN_CORR": CORR_FULL},
             "etapa1_tanda1c1j_stdout.log")
    rows = C.WORK / "etapa1_tanda1c1j_rows.parquet"
    save_step("c1j", {"returncode": rc, "rows_bytes": rows.stat().st_size if rows.exists() else None,
                      "rows_sha256": sha(rows) if rows.exists() else None,
                      "note": "sin hash registrado: comparar data/etapa1_tanda1c1j_*.json con git diff"})


def step_devcheck():
    rc = run(["s9_etapa2.py", "--rebuild-dev-check"], {}, "etapa2_rebuild_dev_stdout.log")
    chk = json.loads((C.PUB / "etapa2_rebuild_dev_check.json").read_text(encoding="utf-8"))
    save_step("devcheck", {"returncode": rc, "identical": chk.get("identical"), "rows_new": chk.get("rows_new")})


def step_test():
    import pandas as pd
    import s9_etapa2 as S9
    built = [json.loads(l) for l in S9.ACCESS.read_text(encoding="utf-8").splitlines() if '"rows_built"' in l]
    want = built[-1]["rows_sha"]
    if S9.TEST_ROWS.exists() and sha(S9.TEST_ROWS) == want:
        save_step("test", {"already_ok": True, "rows_sha256": want})
        return
    with S9.ACCESS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": pd.Timestamp.now("UTC").isoformat(), "event": "rows_rebuild_disk_incident",
                            "expected_rows_sha": want,
                            "note": "reconstrucción de las filas de prueba perdidas en el incidente del disco "
                                    "(22-nov-2026); sin run() ni resultados"}) + "\n")
    tmp = C.WORK / "etapa2_test_rows.rebuild.parquet"
    t0 = time.time()
    S9.build_rows("test").to_parquet(tmp)
    got = sha(tmp)
    rec = {"rows_sha256": got, "expected": want, "match": got == want, "seconds": round(time.time() - t0)}
    if got == want:
        os.replace(tmp, S9.TEST_ROWS)
        rec["placed_as"] = S9.TEST_ROWS.name
    with S9.ACCESS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": pd.Timestamp.now("UTC").isoformat(), "event": "rows_rebuild_disk_incident_done",
                            "rows_sha": got, "match": got == want}) + "\n")
    save_step("test", rec)


STEPS = {"panel": step_panel, "tanda1": lambda: step_tanda(1), "tanda2": lambda: step_tanda(2), "c1j": step_c1j,
         "devcheck": step_devcheck, "test": step_test}

if __name__ == "__main__":
    for s in sys.argv[1:]:
        STEPS[s]()
