"""Reconstrucción del manifiesto de descargas a partir de los ficheros de raw/ (incidente del disco, 22-nov-2026).

El 22-nov-2026 manifest/manifest.sqlite quedó en 0 bytes. Sin manifiesto, cualquier pasada (g2_downloads, e3_daily)
volvería a descargar todo, también lo que sigue intacto en disco. Este script lo rehace desde el disco:

- Recorre raw/<proveedor>/<tipo>/symbol=*/asof=*/<periodo>[__<hash>].parquet.
- Hash de configuración: el del nombre del fichero. Los ficheros anteriores al 15-nov 10:10 UTC no lo llevan; su
  configuración se deduce: quotes -> sesión regular (la de la etapa quotes y la de g1_live_checks); barras de mes ->
  mes natural sin tope; barras de día -> sesión completa; trades -> sesión completa si la unidad está en un plan B1/B1q
  (v1 o v2) o si tiene operaciones fuera de 09:30-16:00 NY, regular en otro caso.
- Cada fichero se lee entero (decodificación de todas las columnas): uno que no se lee no entra en el manifiesto.
  Se guardan sha256, tamaño y filas. La calidad original no se puede recuperar: quality_json lo indica.
- Lo que no deja fichero (unidades 'empty', 'failed') se pierde: la siguiente pasada vuelve a pedirlas (una petición).
- Ficheros vacíos (0 bytes), entradas asof=* que no son carpeta y la lista --suspect se apartan a
  _incident_2026-11-22/quarantine/ (con --quarantine), nunca se borran.

Uso (desde research/microstructure_v1, con MICRO_DATA_DIR apuntando al disco):
  py -3 manifest_rebuild.py scan [--quarantine] [--suspect lista.txt]   # escribe manifest/manifest_rebuilt.sqlite
  py -3 manifest_rebuild.py quarantine-from-report                     # aparta lo listado sin releer
  py -3 manifest_rebuild.py swap                                          # lo pone como manifest.sqlite
  py -3 manifest_rebuild.py recover-configs [--cap 2026-11-17T22:20:48Z]   # config_json de hashes no estándar
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, download as D, manifest as M, sampling, storage  # noqa: E402,F401

ROOT = storage.root()
RAW = ROOT / "raw"
NEW_DB = ROOT / "manifest" / "manifest_rebuilt.sqlite"
DB = ROOT / "manifest" / "manifest.sqlite"
INC = ROOT / "_incident_2026-11-22"
NAME = re.compile(r"^(\d{4}-\d{2}(?:-\d{2})?)(?:__([0-9a-f]{10}))?\.parquet$")
CODE = "manifest_rebuild_2026-11-22"

CANDS = {
    "bars_month": D.config_for("bars"),
    "bars_day": D.config_for("bars", bars_window="day"),
    "trades_regular": D.config_for("trades"),
    "trades_full": D.config_for("trades", session="full"),
    "quotes_regular": D.config_for("quotes"),
    "quotes_full": D.config_for("quotes", session="full"),
}
try:
    import g2_downloads as G
    CANDS["bars_month_capA"] = D.config_for("bars", cap=G.cap_utc())
except Exception:  # noqa: BLE001
    G = None
BY_HASH = {D.config_hash(c): c for c in CANDS.values()}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def b1_trade_units() -> set:
    """(símbolo, asof, día) de los planes B1/B1q, v1 y v2 (trades de sesión completa)."""
    out = set()
    if G is None:
        return out
    for ver in ("v1", "v2"):
        G.PLAN_VERSION = ver
        for st in ("B1", "B1q"):
            try:
                for kind, sym, day, asof, cfg in G.units_for(st):
                    out.add((sym, D.clean_asof(asof) or "-", day))
            except FileNotFoundError:
                pass
    return out


def scan_tree():
    files, odd = [], []
    for prov in sorted(p for p in RAW.iterdir() if p.is_dir()):
        for kind in sorted(p for p in prov.iterdir() if p.is_dir()):
            for sdir in sorted(kind.iterdir()):
                if not sdir.is_dir() or not sdir.name.startswith("symbol="):
                    odd.append((sdir, "symbol_entry_not_dir")); continue
                for adir in sorted(sdir.iterdir()):
                    if not adir.is_dir() or not adir.name.startswith("asof="):
                        odd.append((adir, "asof_entry_not_dir")); continue
                    for f in sorted(adir.iterdir()):
                        m = NAME.match(f.name)
                        if not f.is_file() or not m:
                            odd.append((f, "unexpected_name")); continue
                        files.append({"path": f, "provider": prov.name, "kind": kind.name, "symbol": sdir.name[7:],
                                      "asof": adir.name[5:], "period": m.group(1), "hash": m.group(2)})
    return files, odd


def check_file(rec: dict) -> dict:
    p = rec["path"]
    try:
        size = p.stat().st_size
        if size == 0:
            return {**rec, "ok": False, "error": "zero_bytes"}
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for ch in iter(lambda: f.read(1 << 20), b""):
                h.update(ch)
        t = pq.read_table(p)                      # decodifica todo: un fichero dañado falla aquí
        info = {"rows": t.num_rows}
        if "t" in t.column_names and t.num_rows:
            ts = pd.to_datetime(t.column("t").to_pandas(), utc=True)
            info["t_min"], info["t_max"] = ts.min().isoformat(), ts.max().isoformat()
            if rec["kind"] == "trades" and not rec["hash"]:
                ny = ts.dt.tz_convert("America/New_York")
                m = ny.dt.hour * 60 + ny.dt.minute
                info["outside_regular"] = int(((m < 570) | (m >= 960)).sum())
        return {**rec, "ok": True, "sha256": h.hexdigest(), "file_bytes": size, **info}
    except Exception as e:  # noqa: BLE001
        return {**rec, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}


def period_ok(r: dict) -> bool:
    """Las marcas de tiempo caen en el periodo del nombre (día: sesión completa de ese día; mes: ese mes)."""
    if not r.get("rows"):
        return True
    a, b = pd.Timestamp(r["t_min"]), pd.Timestamp(r["t_max"])
    if len(r["period"]) == 7:
        s = pd.Timestamp(r["period"] + "-01", tz="UTC")
        return a >= s - pd.Timedelta(hours=6) and b < s + pd.offsets.MonthBegin(1) + pd.Timedelta(hours=6)
    s, e = calendar.session_bounds(r["period"], "full")
    return a >= s - pd.Timedelta(minutes=1) and b <= e + pd.Timedelta(minutes=1)


def resolve_cfg(r: dict, b1: set):
    if r["hash"]:
        return r["hash"], BY_HASH.get(r["hash"]), "file_name"
    k, daily = r["kind"], len(r["period"]) == 10
    if k == "quotes":
        c = CANDS["quotes_regular"]
        how = "nohash:quotes_regular"
    elif k == "bars":
        c = CANDS["bars_day"] if daily else CANDS["bars_month"]
        how = "nohash:bars_day" if daily else "nohash:bars_month"
    else:
        in_plan = (r["symbol"], r["asof"], r["period"]) in b1
        full = in_plan or (r.get("outside_regular") or 0) > 0
        c = CANDS["trades_full" if full else "trades_regular"]
        how = f"nohash:trades_{'full' if full else 'regular'}({'plan_b1' if in_plan else 'contenido'})"
    return D.config_hash(c), c, how


def quarantine(path: Path, reason: str, log: list):
    rel = path.relative_to(ROOT)
    dst = INC / "quarantine" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dst))
    log.append({"path": str(rel), "reason": reason, "moved_to": str(dst.relative_to(ROOT))})


def scan(do_quarantine: bool, suspect_file: str, workers: int):
    INC.mkdir(exist_ok=True)
    suspects = set()
    if suspect_file:
        suspects = {l.strip().replace("\\", "/") for l in open(suspect_file, encoding="utf-8") if l.strip()}
    files, odd = scan_tree()
    print(f"ficheros: {len(files)}; entradas raras: {len(odd)}", flush=True)
    b1 = b1_trade_units()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = []
        for i, r in enumerate(ex.map(check_file, files), 1):
            res.append(r)
            if i % 5000 == 0:
                print(f"  {i}/{len(files)}", flush=True)
    qlog, bad, units = [], [], {}
    for p, why in odd:
        if do_quarantine and p.is_file() and p.stat().st_size == 0:
            quarantine(p, why + "_zero_bytes", qlog)
        else:
            bad.append({"path": str(p.relative_to(ROOT)), "reason": why})
    for r in res:
        rel = str(r["path"].relative_to(ROOT)).replace("\\", "/")
        if not r["ok"]:
            if do_quarantine:
                quarantine(r["path"], r["error"], qlog)
            else:
                bad.append({"path": rel, "reason": r["error"]})
            continue
        if rel in suspects:
            if not period_ok(r):
                why = "suspect_and_out_of_period"
            else:
                why = "suspect_written_after_divergence"
            if do_quarantine:
                quarantine(r["path"], why, qlog)
            else:
                bad.append({"path": rel, "reason": why})
            continue
        if not period_ok(r):
            bad.append({"path": rel, "reason": "out_of_period", "t_min": r.get("t_min"), "t_max": r.get("t_max")})
            continue
        h, cfg, how = resolve_cfg(r, b1)
        key = f"{r['provider']}|{r['kind']}|{r['symbol']}|{r['asof']}|{r['period']}|{h}"
        if key in units:
            # misma unidad con y sin hash en el nombre: vale la del nombre con hash (la más reciente)
            prev = units[key]
            keep = r if r["hash"] else prev
            bad.append({"path": str((prev if keep is r else r)["path"].relative_to(ROOT)), "reason": "duplicate_unit",
                        "kept": str(keep["path"].relative_to(ROOT))})
            r = keep
        units[key] = {**r, "cfg_hash": h, "cfg": cfg, "how": how}
    if NEW_DB.exists():
        NEW_DB.unlink()
    m = M.Manifest(NEW_DB)
    ts = now()
    with sqlite3.connect(NEW_DB) as c:
        for key, u in units.items():
            q = {"rebuilt_from_disk": True, "config_inferred": u["how"], "rows_on_disk": u.get("rows"),
                 "note": "calidad original perdida en el incidente del 22-nov-2026"}
            c.execute("""INSERT INTO units (unit_key, provider, kind, symbol, asof, period, config_hash, config_json,
                         status, rows, path, sha256, file_bytes, quality_grade, quality_json, code_version, started_utc,
                         finished_utc, attempts) VALUES (?,?,?,?,?,?,?,?, 'ok', ?,?,?,?, NULL, ?, ?, ?, ?, 0)""",
                      (key, u["provider"], u["kind"], u["symbol"], u["asof"], u["period"], u["cfg_hash"],
                       json.dumps(u["cfg"], sort_keys=True) if u["cfg"] else None, u.get("rows"),
                       str(u["path"]), u["sha256"], u["file_bytes"], json.dumps(q), CODE, ts, ts))
            c.execute("INSERT INTO events VALUES (?,?,?,?)", (ts, key, "rebuilt_from_disk", u["how"]))
    del m
    summ = {"built_utc": ts, "root": str(ROOT), "files_seen": len(files), "units": len(units),
            "by_kind_cfg": pd.Series([f"{u['kind']}|{u['cfg_hash']}|{u['how']}" for u in units.values()])
            .value_counts().to_dict(),
            "quarantined": qlog, "not_registered": bad, "unknown_config_hashes": sorted(
                {u["cfg_hash"] for u in units.values() if u["cfg"] is None})}
    # control: unidades de los planes de descarga presentes en el manifiesto reconstruido
    if G is not None:
        G.PLAN_VERSION = "v2"
        cov = {}
        for st in ("A", "quotes", "B1q"):
            keys = [D.unit_key("alpaca", k, s, a, p, c) for k, s, p, a, c in G.units_for(st)]
            cov[st] = {"planned": len(keys), "present": sum(k in units for k in keys)}
        summ["plan_coverage"] = cov
    out = INC / "manifest_rebuild_report.json"
    out.write_text(json.dumps(summ, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summ.items() if k not in ("quarantined", "not_registered")}, indent=1,
                     ensure_ascii=False, default=str))
    print("apartados:", len(qlog), "no registrados:", len(bad), "->", out)


def recover_configs(db: Path = DB, days_back: int = 60, extra_caps: list = ()):
    """Rellena config_json de las unidades cuyo hash no es una configuración conocida (fuerza bruta acotada).

    event_scan._unit_end y otros consumidores leen config_json (tope `cap`, ventana horaria `range`); sin él fallan
    (visto el 23-nov-2026). Candidatos: topes al minuto de los últimos `days_back` días (ventana de día y de mes) y
    ventanas horarias HH:MM-HH:MM de trades/quotes en sesión regular y completa (~4 M hashes, ~30 s). Un tope con
    segundos no sale por esta vía: se puede pasar en `extra_caps` (p. ej. el 2026-11-17T22:20:48Z de PLTR)."""
    from datetime import timedelta

    def h(cfg):
        return D.config_hash(cfg)

    c = sqlite3.connect(db)
    try:
        unk = {r[0]: r[1] for r in c.execute("SELECT DISTINCT config_hash, kind FROM units WHERE config_json IS NULL")}
        found = {}
        for cap in extra_caps:
            for cfg in (D.config_for("bars", bars_window="day", cap=cap), D.config_for("bars", cap=cap)):
                if h(cfg) in unk:
                    found[h(cfg)] = cfg
        t = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(days=days_back)
        end = datetime.now(timezone.utc)
        while "bars" in unk.values() and t < end and len(found) < len(unk):
            cap = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            for cfg in (D.config_for("bars", bars_window="day", cap=cap), D.config_for("bars", cap=cap)):
                if h(cfg) in unk:
                    found.setdefault(h(cfg), cfg)
            t += timedelta(minutes=1)
        mins = [f"{m // 60:02d}:{m % 60:02d}" for m in range(24 * 60)]
        for kind in sorted({k for k in unk.values() if k in ("trades", "quotes")}):
            for sess in ("regular", "full"):
                for i, a in enumerate(mins):
                    for b in mins[i + 1:]:
                        cfg = D.config_for(kind, session=sess, time_range=f"{a}-{b}")
                        if h(cfg) in unk:
                            found.setdefault(h(cfg), cfg)
        ts = now()
        for x, cfg in found.items():
            c.execute("UPDATE units SET config_json=? WHERE config_hash=? AND config_json IS NULL",
                      (json.dumps(cfg, sort_keys=True), x))
            c.execute("INSERT INTO events SELECT ?, unit_key, 'config_recovered', 'fuerza bruta' FROM units "
                      "WHERE config_hash=?", (ts, x))
        c.commit()
        left = sorted(set(unk) - set(found))
    finally:
        c.close()
    print(f"configuraciones recuperadas: {len(found)} de {len(unk)}; sin recuperar: {left}")
    return found, left


QUARANTINE_REASONS = ("zero_bytes", "asof_entry_not_dir", "symbol_entry_not_dir", "suspect_written_after_divergence",
                      "suspect_and_out_of_period")


def quarantine_from_report():
    """Aparta lo que `scan` (sin --quarantine) dejó fuera del manifiesto, sin volver a leer el disco.

    Solo ficheros vacíos, entradas que no son carpeta y la lista de sospechosos; los ilegibles y los fuera de periodo
    se dejan donde están para revisarlos a mano. Los duplicados sin hash no se tocan (no estorban)."""
    rep_p = INC / "manifest_rebuild_report.json"
    rep = json.loads(rep_p.read_text(encoding="utf-8"))
    log = []
    for b in rep["not_registered"]:
        why = b["reason"]
        if not (why in QUARANTINE_REASONS or why.startswith("zero_bytes")):
            continue
        p = ROOT / b["path"]
        if not p.exists():
            continue
        if p.is_file() and why in ("asof_entry_not_dir", "symbol_entry_not_dir") and p.stat().st_size != 0:
            continue                                      # una entrada rara con contenido no se mueve a ciegas
        quarantine(p, why, log)
    rep.setdefault("quarantined", []).extend(log)
    rep_p.write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"apartados {len(log)} -> {INC / 'quarantine'}")
    for x in log:
        print("  ", x["path"], x["reason"])


def swap():
    if not NEW_DB.exists():
        raise SystemExit("falta manifest_rebuilt.sqlite: ejecutar antes `scan`")
    c = sqlite3.connect(f"file:{NEW_DB.as_posix()}?mode=ro", uri=True)
    try:                                    # `with` no cierra la conexión en sqlite3: sin close(), Windows no deja moverlo
        qc = c.execute("PRAGMA integrity_check").fetchone()[0]
        n = c.execute("SELECT count(*) FROM units").fetchone()[0]
    finally:
        c.close()
    if qc != "ok" or n == 0:
        raise SystemExit(f"el manifiesto reconstruido no es válido: {qc}, {n} unidades")
    if DB.exists():
        keep = INC / f"manifest.sqlite.antes_de_reconstruir_{DB.stat().st_size}B"
        shutil.move(str(DB), str(keep))
        for ext in ("-wal", "-shm", "-journal"):
            side = DB.with_name(DB.name + ext)
            if side.exists():
                shutil.move(str(side), str(INC / (side.name + ".antes_de_reconstruir")))
    shutil.move(str(NEW_DB), str(DB))
    print(f"manifest.sqlite reconstruido en su sitio: {n} unidades")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "quarantine-from-report", "swap", "recover-configs"])
    ap.add_argument("--quarantine", action="store_true")
    ap.add_argument("--suspect")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cap", action="append", help="tope con segundos a probar en recover-configs (repetible)")
    a = ap.parse_args()
    if a.cmd == "scan":
        scan(a.quarantine, a.suspect, a.workers)
    elif a.cmd == "quarantine-from-report":
        quarantine_from_report()
    elif a.cmd == "recover-configs":
        recover_configs(extra_caps=a.cap or [])
    else:
        swap()
