"""
test_tags_invariance.py — AISLAMIENTO: editar o borrar etiquetas no cambia NINGÚN motor de inversión.

Sin pytest, sin red, sin modelos de pago:    py -3 scripts/test_tags_invariance.py

Método. Se copian los datos de entrada reales a un directorio temporal (quedan congelados dentro de la
ejecución) y cada motor se ejecuta con los ficheros de etiquetas en tres estados:
    S1  ausentes
    S2  la taxonomía sembrada real
    S3  basura: JSON ilegible y metadatos de Yahoo falsos (si un motor los leyera, fallaría o cambiaría)
y se exige: (a) salida idéntica byte a byte en los tres escenarios; (b) que ninguna lectura de esos ficheros ocurra
(el detector hace fallar `open`, `Path.open/read_text` y, en Node, `fs.*` y `require`); (c) que las entradas no se
modifiquen. Además se demuestra que el detector funciona (control negativo) y se escanea el código fuente.

  I1  Flow (Python): build_context + evaluate_ticker de todos los tickers
  I2  Flow (JS): cestas de tema, Flow Score y Early Flow
  I3  Sol: build_user_message (el texto exacto que recibiría el modelo; sin llamar a la API)
  I4  PCS: pcs_calculator.run() completo (sin red) → ai_candidates.json
  I5  núcleo de decisión: compact_candidate, compute_theme_concentration, suelo de PCS
  I6  las entradas no cambian
  I7  estático: ningún fichero del pipeline referencia las etiquetas (lista blanca explícita)

Variables:  TAGS_ENGINE_ROOT (de dónde se cargan los motores, por defecto este repo; sirve para demostrar que la
batería es verde sobre un baseline SIN etiquetas)   TAGS_INPUT_ROOT (de dónde salen los datos de entrada).
"""
from __future__ import annotations

import builtins
import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENGINE = Path(os.environ.get("TAGS_ENGINE_ROOT") or REPO).resolve()
INPUT = Path(os.environ.get("TAGS_INPUT_ROOT") or REPO).resolve()
FORBIDDEN = ("ticker_tags", "ticker_yahoo_meta", "ticker-tags")

sys.path.insert(0, str(ENGINE / "scripts"))

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, bool(ok), "" if ok else str(detail)))


class TagReadDetected(Exception):
    pass


@contextlib.contextmanager
def guard():
    """Falla cualquier apertura de ficheros de etiquetas (open, io.open, Path.open/read_text/read_bytes)."""
    real_open, real_io_open, real_path_open = builtins.open, io.open, pathlib.Path.open

    def chk(p):
        s = str(p).replace("\\", "/").lower()
        if any(f in s for f in FORBIDDEN):
            raise TagReadDetected(s)

    def g_open(file, *a, **k):
        chk(file); return real_open(file, *a, **k)

    def g_path_open(self, *a, **k):
        chk(self); return real_path_open(self, *a, **k)

    builtins.open = g_open; io.open = g_open; pathlib.Path.open = g_path_open
    try:
        yield
    finally:
        builtins.open = real_open; io.open = real_io_open; pathlib.Path.open = real_path_open


def h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── raíz temporal con los datos de entrada ───────────────────────────────────
DATA_FILES = ["portfolio_daily_snapshot.jsonl", "market_equities_daily_snapshot.jsonl", "market_macro_daily_snapshot.jsonl",
              "market_analysis_llm.jsonl", "universe.json", "macro_history.json", "rotation_signals.json", "stock_candidates.json",
              "ai_candidates.json", "ai_picks.json"]


def build_root(tmp: Path) -> Path:
    (tmp / "docs" / "data").mkdir(parents=True)
    shutil.copy(INPUT / "portfolio.json", tmp / "portfolio.json")
    for f in DATA_FILES:
        src = INPUT / "docs" / "data" / f
        if src.exists():
            shutil.copy(src, tmp / "docs" / "data" / f)
    (tmp / "wiki").mkdir()
    return tmp


def set_scenario(root: Path, scenario: str):
    d = root / "docs" / "data"
    names = ["ticker_tags.json", "ticker_tags_events.jsonl", "ticker_yahoo_meta.json"]
    for n in names:
        with contextlib.suppress(FileNotFoundError):
            (d / n).unlink()
    if scenario == "S1":
        return
    if scenario == "S2":
        for n in names:
            if (INPUT / "docs" / "data" / n).exists():
                shutil.copy(INPUT / "docs" / "data" / n, d / n)
        return
    (d / "ticker_tags.json").write_text("{ esto no es json ", encoding="utf-8")
    (d / "ticker_tags_events.jsonl").write_text("BASURA\n" * 5, encoding="utf-8")
    (d / "ticker_yahoo_meta.json").write_text(json.dumps({"tickers": {"NVDA": {"sector": "Cripto", "industry": "Falso"}}}), encoding="utf-8")


def tree_hash(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(f in p.name for f in ("ticker_tags", "ticker_yahoo_meta")) and "universe_snapshots" not in p.parts and p.name != "ai_candidates.out.json":
            out[str(p.relative_to(root)).replace("\\", "/")] = sha_file(p)
    return out


# ── motores ──────────────────────────────────────────────────────────────────
def engine_flow_python(root: Path):
    import flow_state_lib as fsl
    ctx = fsl.build_context(root)
    tickers = sorted({it["ticker"] for s in json.loads((root / "portfolio.json").read_text(encoding="utf-8"))["sections"] for it in s["items"]})
    res = {tk: fsl.evaluate_ticker(tk, ctx) for tk in tickers}
    return {"n": len(res), "hash": h(res)}


def engine_sol(root: Path):
    import market_analysis_llm as mal
    d = root / "docs" / "data"
    saved = {k: getattr(mal, k) for k in ("ROOT", "DATA", "WIKI", "MARKET_EQUITIES", "MARKET_MACRO", "PORTFOLIO_SNAP", "PORTFOLIO_JSON", "OUT_PATH")}
    try:
        mal.ROOT, mal.DATA, mal.WIKI = root, d, root / "wiki"
        mal.MARKET_EQUITIES, mal.MARKET_MACRO = d / "market_equities_daily_snapshot.jsonl", d / "market_macro_daily_snapshot.jsonl"
        mal.PORTFOLIO_SNAP, mal.PORTFOLIO_JSON, mal.OUT_PATH = d / "portfolio_daily_snapshot.jsonl", root / "portfolio.json", d / "market_analysis_llm.jsonl"
        macro_dates = sorted({json.loads(l)["date"] for l in (d / "market_macro_daily_snapshot.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()})
        msg, prev = mal.build_user_message(macro_dates[-1])
        return {"chars": len(msg), "prev": prev, "hash": hashlib.sha256(msg.encode("utf-8")).hexdigest()}
    finally:
        for k, v in saved.items():
            setattr(mal, k, v)


def engine_pcs(root: Path):
    import pcs_calculator as pc
    import sync_universe as su
    work = Path(tempfile.mkdtemp(prefix="pcs-run-"))
    try:
        (work / "data").mkdir()
        for f in ("universe.json", "macro_history.json", "rotation_signals.json", "stock_candidates.json"):
            shutil.copy(root / "docs" / "data" / f, work / "data" / f)
        old = (pc.DATA, pc.fetch_daily_metrics, su.sync)
        pc.DATA = work / "data"; pc.fetch_daily_metrics = lambda tickers: {}; su.sync = lambda verbose=True: {}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                pc.run()
        finally:
            pc.DATA, pc.fetch_daily_metrics, su.sync = old
        out = json.loads((work / "data" / "ai_candidates.json").read_text(encoding="utf-8"))
        out.pop("date", None)
        return {"n": len(out["candidates"]), "hash": h(out)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def engine_core(root: Path):
    import ai_shared
    import paper_trading as pt
    d = root / "docs" / "data"
    cands = json.loads((d / "ai_candidates.json").read_text(encoding="utf-8"))["candidates"]
    picks = json.loads((d / "ai_picks.json").read_text(encoding="utf-8"))
    conc, expo = pt.compute_theme_concentration(cands, picks)
    compact = [ai_shared.compact_candidate(c, conc.get(c["ticker"])) for c in cands]
    floor = [ai_shared.compute_pcs_floor_verdict(p, r, t, b) for p in (55.0, 59.5, 61.0, 64.0, None) for r in (1, 3, 8) for t in (62.0, 68.0) for b in (True, False, None)]
    tact = [ai_shared.compute_t_active(m, s) for m in (62.0, 68.0, 82.0) for s in (0, 1, 2, None)]
    return {"hash": h({"conc": conc, "expo": expo, "compact": compact, "floor": floor, "tact": tact}), "n": len(compact)}


def run_js(root: Path, with_guard: bool = True):
    args = ["node"] + (["-r", str(REPO / "scripts" / "tags_fs_guard.js")] if with_guard else []) + [str(REPO / "scripts" / "tags_invariance_probe.js"), str(root)]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "TAGS_ENGINE_ROOT": str(ENGINE)}, cwd=str(REPO))
    if p.returncode != 0:
        return {"error": (p.stderr or p.stdout)[-400:]}
    return json.loads(p.stdout.strip().splitlines()[-1])


def main() -> int:
    if not (INPUT / "docs" / "data" / "ai_candidates.json").exists():
        print("Faltan los datos de entrada"); return 2
    tmp = Path(tempfile.mkdtemp(prefix="tags-inv-"))
    try:
        root = build_root(tmp)
        before = tree_hash(root)
        engines = {"I1 Flow (Python)": engine_flow_python, "I3 Sol (build_user_message)": engine_sol, "I4 PCS (run() completo)": engine_pcs, "I5 núcleo de decisión": engine_core}
        out: dict[str, dict[str, dict]] = {name: {} for name in list(engines) + ["I2 Flow (JS)"]}
        for sc in ("S1", "S2", "S3"):
            set_scenario(root, sc)
            for name, fn in engines.items():
                try:
                    with guard():
                        out[name][sc] = fn(root)
                except TagReadDetected as e:
                    out[name][sc] = {"LEIDO": str(e)}
                except Exception as e:                              # un fallo del motor cuenta, con su causa
                    out[name][sc] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            out["I2 Flow (JS)"][sc] = run_js(root)
        for name, per in out.items():
            vals = [per.get(sc) for sc in ("S1", "S2", "S3")]
            read = [v for v in vals if v and "LEIDO" in v]
            errs = [v for v in vals if v and "error" in v]
            same = all(v == vals[0] for v in vals) and not errs and not read
            check(f"{name}: salida idéntica sin etiquetas / sembradas / basura", same,
                  f"LECTURA DETECTADA: {read[0]['LEIDO']}" if read else (f"error: {errs[0]['error']}" if errs else json.dumps(vals)[:400]))
            check(f"{name}: ninguna lectura de ficheros de etiquetas", not read, read[0]["LEIDO"] if read else "")
            if same:
                check(f"{name}: la salida no está vacía ({ {k: v for k, v in vals[0].items() if k != 'hash'} })", True)
        # I6 entradas intactas
        set_scenario(root, "S1")
        check("I6 las entradas no se modificaron durante las 3 ejecuciones de cada motor", tree_hash(root) == before,
              str([k for k in before if tree_hash(root).get(k) != before[k]][:5]))

        # control negativo: el detector SÍ detecta (si no, las comprobaciones anteriores no valdrían)
        set_scenario(root, "S2")
        tripped = False
        try:
            with guard():
                (root / "docs" / "data" / "ticker_tags.json").read_text(encoding="utf-8")
        except TagReadDetected:
            tripped = True
        check("CONTROL el detector de Python falla ante la lectura directa de ticker_tags.json", tripped)
        tripped = False
        try:
            with guard():
                json.loads(Path(root / "docs" / "data" / "ticker_yahoo_meta.json").read_bytes())
        except TagReadDetected:
            tripped = True
        check("CONTROL …también ante Path.read_bytes() y ante los metadatos de Yahoo", tripped)
        p = subprocess.run(["node", "-r", str(REPO / "scripts" / "tags_fs_guard.js"), "-e",
                            f"try{{require('fs').readFileSync({json.dumps(str(root / 'docs' / 'data' / 'ticker_tags.json'))},'utf8');console.log('SIN-DETECTAR')}}catch(e){{console.log(e.name)}}"],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(REPO))
        check("CONTROL el detector de Node falla ante fs.readFileSync de ticker_tags.json", p.stdout.strip() == "TagReadDetected", p.stdout + p.stderr)
        p = subprocess.run(["node", "-r", str(REPO / "scripts" / "tags_fs_guard.js"), "-e", f"try{{require({json.dumps(str(root / 'docs' / 'data' / 'ticker_tags.json'))});console.log('SIN-DETECTAR')}}catch(e){{console.log(e.name)}}"],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(REPO))
        check("CONTROL …y ante require() del JSON", p.stdout.strip() == "TagReadDetected", p.stdout + p.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # I7 estático
    allow = [r"^shared/ticker-tags-(lib|store|routes)\.js$", r"^scripts/(seed_ticker_tags\.js|fetch_yahoo_meta\.py|ticker_tags_seed\.json|tags_[a-z_]+\.js|test_ticker_tags_[a-z]+\.js|test_tags_invariance\.py|run_tags_tests\.sh)$",
             r"^(server\.js|portfolio\.html|CLAUDE\.md)$", r"^\.github/workflows/tags-isolation\.yml$", r"^docs/(data|analysis)/", r"^wiki/", r"^research/", r"^tests/"]
    files = subprocess.run(["git", "ls-files"], cwd=str(REPO), capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    files += [str(p.relative_to(REPO)).replace("\\", "/") for p in (REPO / "scripts").glob("*") if p.is_file()]
    scan = sorted({f for f in files if re.search(r"\.(py|js|html|yml|yaml|sh|json|jsonl|md)$", f)})
    pat = re.compile(r"ticker[_-]?tags|ticker_yahoo_meta", re.I)
    offenders = []
    for f in scan:
        if any(re.search(a, f) for a in allow):
            continue
        try:
            if pat.search((REPO / f).read_text(encoding="utf-8", errors="ignore")):
                offenders.append(f)
        except OSError:
            pass
    check(f"I7 ningún fichero del pipeline ni de los motores referencia las etiquetas ({len(scan)} ficheros revisados)", not offenders, ", ".join(offenders))
    wf = (REPO / ".github" / "workflows" / "market-update.yml")
    check("I7 el workflow productivo market-update.yml no menciona las etiquetas", not wf.exists() or not pat.search(wf.read_text(encoding="utf-8")))

    bad = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("  ok   " if ok else "  FAIL ") + name + (f"\n         {detail}" if detail else ""))
    print(f"\n{len(results) - len(bad)}/{len(results)} passed   (motores: {ENGINE}  ·  entradas: {INPUT})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
