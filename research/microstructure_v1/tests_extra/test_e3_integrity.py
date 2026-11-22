"""Pruebas de e3_integrity.py (2026-11-22).

Están FUERA de tests/ a propósito: tests/ es la batería que el piloto E3 ejecuta antes de cada jornada y su contenido
forma parte del manifiesto autorizado; añadir aquí pruebas nuevas durante el piloto lo bloquearía. Al terminar el
piloto pueden pasarse a tests/ (y volver a congelar el manifiesto si hubiera otro piloto).

Todo corre sobre una copia del estudio en un directorio temporal: nunca toca la tarea programada, el disco de datos
ni Telegram.
  py -3 -m pytest tests_extra -q -p no:cacheprovider
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY))
import e3_integrity as G  # noqa: E402

DAYS = ["2027-01-04", "2027-01-05"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Copia del estudio con sus archivos autorizados + disco de datos de juguete + modo prueba del piloto."""
    real = G.build_manifest(STUDY)
    repo = tmp_path / "repo"
    study = repo / "research" / "microstructure_v1"
    for rel in real["files"]:
        dst = (study / rel).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2((STUDY / rel).resolve(), dst)
    shutil.copy2(G.SELF, study / "e3_integrity.py")
    data = tmp_path / "data"
    for rel in G.ESSENTIAL_DATA:
        (data / rel).mkdir(parents=True, exist_ok=True)
    (data / "manifest" / "manifest.sqlite").rmdir()
    con = sqlite3.connect(data / "manifest" / "manifest.sqlite")
    con.execute("create table units(x)")
    con.execute("insert into units values (1)")
    con.commit()
    con.close()
    pilot = data / "results" / "e3" / "pilot_test"
    pilot.mkdir(parents=True)
    (pilot / "pilot.json").write_text(json.dumps({"days": DAYS, "status": "active"}), encoding="utf-8")
    monkeypatch.setenv("MICRO_DATA_DIR", str(data))
    monkeypatch.setenv("MICRO_E3_PILOT_DIR", str(pilot))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    G.install(study, no_task=True)
    return {"study": study, "data": data, "pilot": pilot, "gdir": pilot / "guard", "real": real}


def kinds(res):
    return sorted({p["kind"] for p in res["problems"]})


def test_closure_covers_what_the_pilot_runs_and_nothing_else():
    m = G.build_manifest(STUDY)
    f = set(m["files"])
    for must in ("e3_pilot.py", "e3_daily.py", "e3_integrity.py", "micro/episode.py", "micro/catalog_v1.py",
                 "micro/providers/alpaca.py", "lab/server.py", "tests/conftest.py", "tests/test_micro.py",
                 "catalog/cat_v1_params.json", "retention_config.json", "u1_universe_registry.py"):
        assert must in f, must
    for never in ("vp_build.py", "vp_study.py", "cv1_build.py", "tests_extra/test_e3_integrity.py"):
        assert never not in f, never
    assert m["digest"] == G.digest_of(m["files"])


def test_digest_is_the_same_on_a_faithful_copy(env):
    copy = G.build_manifest(env["study"])
    assert copy["digest"] == env["real"]["digest"]


def test_clean_install_verifies(env):
    res = G.verify(env["study"], env["gdir"])
    assert res["ok"], res["problems"]


@pytest.mark.parametrize("damage,expected", [
    (lambda s: (s / "micro" / "episode.py").write_text("# cambiado\n", encoding="utf-8"), "changed"),
    (lambda s: (s / "micro" / "event_scan.py").unlink(), "missing"),
    (lambda s: (s / "catalog" / "cat_v1_params.json").write_bytes(
        (s / "catalog" / "cat_v1_params.json").read_bytes()[:100]), "changed"),           # copia incompleta
    (lambda s: (s / "tests" / "test_nuevo.py").write_text("def test_x(): pass\n", encoding="utf-8"), "extra"),
    (lambda s: (s / "tests" / "test_micro (Copia en conflicto de LAWNMOWER).py").write_text(
        "", encoding="utf-8"), "extra"),
    (lambda s: (s / "conftest.py").write_text("", encoding="utf-8"), "pytest_config_added"),
    (lambda s: shutil.rmtree(s / "micro"), "missing"),
])
def test_code_damage_is_detected(env, damage, expected):
    damage(env["study"])
    res = G.verify(env["study"], env["gdir"])
    assert not res["ok"] and expected in kinds(res)


@pytest.mark.parametrize("damage,expected", [
    (lambda d, p: (d / "manifest" / "manifest.sqlite").write_bytes(b"esto no es sqlite" * 400), "sqlite_bad"),
    (lambda d, p: shutil.rmtree(d / "events" / "cat-v1"), "data_missing"),
    (lambda d, p: (p / "pilot.json").write_text("{roto", encoding="utf-8"), "pilot_json_bad"),
    (lambda d, p: (p / "pilot.json").write_text(json.dumps({"days": ["2027-02-01"]}), encoding="utf-8"),
     "pilot_days_changed"),
])
def test_data_damage_is_detected(env, damage, expected):
    damage(env["data"], env["pilot"])
    res = G.verify(env["study"], env["gdir"])
    assert not res["ok"] and expected in kinds(res)


def test_altered_guard_manifest_is_detected(env):
    m = json.loads((env["gdir"] / "manifest.json").read_text(encoding="utf-8"))
    m["files"]["micro/episode.py"]["sha256"] = "0" * 64
    (env["gdir"] / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert "guard_manifest_altered" in kinds(G.verify(env["study"], env["gdir"]))


def test_environment_change_only_warns(env):
    m = json.loads((env["gdir"] / "manifest.json").read_text(encoding="utf-8"))
    m["environment"]["packages"]["pandas"] = "0.0.1"
    (env["gdir"] / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    res = G.verify(env["study"], env["gdir"])
    assert res["ok"] and any(w["kind"] == "environment_changed" for w in res["warnings"])


def test_guard_tick_blocks_logs_alerts_once_and_recovers(env, monkeypatch):
    sent, launched = [], []
    monkeypatch.setattr(G, "notify", lambda study, text, test_mode, log: sent.append(text) or True)
    monkeypatch.setattr(G.subprocess, "run",
                        lambda cmd, **kw: launched.append(cmd) or G.subprocess.CompletedProcess(cmd, 0))
    ep = env["study"] / "micro" / "episode.py"
    good = ep.read_bytes()
    ep.write_bytes(good + b"\n# cambio no autorizado\n")
    assert G.guard_tick(env["gdir"]) == 2
    assert G.guard_tick(env["gdir"]) == 2                        # mismo problema, mismo día: no repite el aviso
    assert launched == [] and len(sent) == 1 and "NO arranca" in sent[0] and "micro/episode.py" in sent[0]
    blocks = (env["pilot"] / "integrity_blocks.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(blocks) == 2 and json.loads(blocks[0])["action"] == "pilot_not_started"
    ep.write_bytes(good)
    assert G.guard_tick(env["gdir"]) == 0
    assert len(launched) == 1 and launched[0][-2:] == [str(env["study"] / "e3_pilot.py"), "tick"]
    assert len(sent) == 2 and "restablecida" in sent[1]
    assert G.guard_tick(env["gdir"]) == 0 and len(sent) == 2     # ya sano: sin avisos


def test_guard_tick_passes_test_pilot_dir_to_the_pilot(env, monkeypatch):
    seen = {}
    monkeypatch.setattr(G.subprocess, "run",
                        lambda cmd, **kw: seen.update(kw) or G.subprocess.CompletedProcess(cmd, 0))
    assert G.guard_tick(env["gdir"]) == 0
    assert seen["env"]["MICRO_E3_PILOT_DIR"] == str(env["pilot"]) and seen["cwd"] == env["study"]


def test_install_refuses_a_different_digest(env):
    with pytest.raises(SystemExit, match="NO coincide"):
        G.install(env["study"], expect="f" * 64, no_task=True)


def test_install_refuses_when_essential_data_is_missing(env):
    shutil.rmtree(env["data"] / "raw")
    with pytest.raises(SystemExit, match="faltan rutas esenciales"):
        G.install(env["study"], no_task=True)


def test_guarded_task_xml_changes_only_the_action(tmp_path):
    import ast                      # sin importar e3_pilot: al importarlo crea las capas en el disco de datos
    tree = ast.parse((STUDY / "e3_pilot.py").read_text(encoding="utf-8"))
    tpl = next(n.value.value for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "TASK_XML")
    xml = tpl.format(user="DOM\\u", pyw=r"C:\Windows\pyw.exe", script=STUDY / "e3_pilot.py", cwd=STUDY)
    gdir = tmp_path / "backup market tracker" / "guard"
    new = G.guarded_task_xml(xml, gdir)
    assert f'-3 &quot;{gdir / "e3_integrity.py"}&quot; guard-tick' in new
    assert f"<WorkingDirectory>{gdir}</WorkingDirectory>" in new and "e3_pilot.py" not in new
    strip = lambda x: G.re.sub(r"<Exec>.*?</Exec>", "", x, flags=G.re.S)       # noqa: E731
    assert strip(new) == strip(xml)                                          # disparadores y ajustes intactos
    assert r"<Command>C:\Windows\pyw.exe</Command>" in new
