"""manifest.localize: las rutas guardadas en otro equipo (otra letra de unidad) se traducen a la raíz actual."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_localize(tmp_path, monkeypatch):
    monkeypatch.setenv("MICRO_DATA_DIR", str(tmp_path / "microstructure"))
    from micro import manifest, storage
    root = storage.root()
    tail = ["raw", "alpaca", "bars", "symbol=SPY", "asof=-", "2026-01__3f27f91fdd.parquet"]
    want = str(root.joinpath(*tail))
    # misma raíz: sin cambios
    assert manifest.localize(want) == want
    # otra letra de unidad y separadores de Windows
    other = "D:\\backup market tracker\\microstructure\\" + "\\".join(tail)
    assert manifest.localize(other) == want
    # separadores mezclados
    assert manifest.localize("E:/x/y/" + "/".join(tail)) == want
    # un símbolo llamado RAW no confunde la capa
    t2 = ["raw", "alpaca", "bars", "symbol=RAW", "asof=-", "2026-01.parquet"]
    assert manifest.localize("Z:\\a\\" + "\\".join(t2)) == str(root.joinpath(*t2))
    # sin capa raw o vacía: se deja como está
    assert manifest.localize("Z:\\otra\\cosa.parquet") == "Z:\\otra\\cosa.parquet"
    assert manifest.localize(None) is None


def test_rows_and_is_done_use_localized_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MICRO_DATA_DIR", str(tmp_path / "microstructure"))
    from micro import manifest, storage
    root = storage.root()
    p = root / "raw" / "alpaca" / "bars" / "symbol=SPY" / "asof=-" / "2026-01__3f27f91fdd.parquet"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    m = manifest.Manifest()
    meta = {"provider": "alpaca", "kind": "bars", "symbol": "SPY", "asof": "-", "period": "2026-01",
            "config_hash": "3f27f91fdd", "config": {}, "code_version": "t"}
    m.start("k", meta)
    m.finish("k", "ok", path="D:\\otro\\microstructure\\raw\\alpaca\\bars\\symbol=SPY\\asof=-\\2026-01__3f27f91fdd.parquet",
             sha256=storage.sha256_file(p), file_bytes=1)
    assert m.get("k")["path"] == str(p)
    assert m.rows("unit_key='k'")[0]["path"] == str(p)
    assert m.is_done("k", verify_checksum=True)
