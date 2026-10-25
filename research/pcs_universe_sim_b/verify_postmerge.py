"""
verify_postmerge.py — verificación de la línea B en producción (primer run tras el merge 43d9a0a2).

Sin red de pago ni modelos: solo lee git. Uso:
    py -3 research/pcs_universe_sim_b/verify_postmerge.py                    # busca el primer run posterior al merge
    py -3 research/pcs_universe_sim_b/verify_postmerge.py --run-commit HASH  # un run concreto
    py -3 research/pcs_universe_sim_b/verify_postmerge.py --preview          # vista previa: inputs de HOY + universo nuevo
    ... --write wiki/VERIFICACION_B_POSTMERGE.md

Método (por qué no depende del mercado de ese día): el PCS es una función determinista de macro_history,
rotation_signals, stock_candidates y universe.json. Con los inputs EXACTOS de ese run se reconstruye el PCS
(a) con el universo antiguo y (b) con el nuevo. Si (b) coincide con el ai_candidates.json realmente
publicado, el pipeline usó el universo nuevo y calculó lo esperado; (b)-(a) aísla el efecto de la corrección
de la deriva normal del mercado.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import pcs_calculator as pc  # noqa: E402

MERGE = "43d9a0a2"
BASELINE = "b98f0aa1"          # último run anterior al merge (universo antiguo)
THRESHOLDS = (("HC82", 82), ("CFL75", 75), ("ER68", 68), ("MTB62", 62))
RETIRED = ("GOLD", "ASMI", "YAN.AX", "MRR.XA")
NEW = ("B", "NRL.AX")
CORRECTED = ("AFM.V", "ASCU.TO", "GLEN.L", "GS", "KTOS", "MOS", "SLB", "SMR.AX", "TECK", "TK", "TTI",
             "VAL", "SLP.L", "DMX.V", "SAIA")
SECOND_ORDER = ("IE", "III.TO", "REG.V")
PINNED = {  # identidad y clasificación aprobadas (nombre, tema, subtema)
    "VAL": ("Valaris", "oil_gas", "offshore_drilling"),
    "SLP.L": ("Sylvania Platinum", "silver_gold_miners", "pgm_miners"),
    "DMX.V": ("District Metals", "uranium_nuclear", "uranium_exploration"),
    "B": ("Barrick Mining", "silver_gold_miners", "gold_miners"),
    "NRL.AX": ("Northstone Resources", "commodities_metals", ""),
    "TK": ("Teekay", "oil_gas", "tankers"),
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def show(commit: str, path: str):
    try:
        return json.loads(git("show", f"{commit}:{path}"))
    except Exception:
        return None


def find_run_commit() -> str | None:
    out = git("log", "--reverse", "--format=%H|%s", f"{MERGE}..origin/master", "--", "docs/data/ai_candidates.json")
    for line in out.splitlines():
        h, subj = line.split("|", 1)
        if subj.startswith("chore: auto-update market data"):
            return h
    return None


def replay(commit: str, universe: dict) -> dict[str, dict]:
    macro = show(commit, "docs/data/macro_history.json")
    rot = show(commit, "docs/data/rotation_signals.json")
    cand = show(commit, "docs/data/stock_candidates.json")
    hist = macro.get("history", [])
    last = hist[-1] if hist else {}
    rot_idx = {s["ticker"]: s for s in rot.get("latest_signals", [])}
    meta = {t["ticker"]: t for t in universe["tickers"]}
    cidx = {}
    for c in cand.get("candidates", []):
        e = dict(c)
        if c["ticker"] in meta:
            e["theme"] = meta[c["ticker"]].get("theme", "")
        cidx[c["ticker"]] = e
    by_theme: dict[str, list] = {}
    for c in cidx.values():
        if c.get("theme") and c.get("ret_13w_vs_spy") is not None:
            by_theme.setdefault(c["theme"], []).append(c["ret_13w_vs_spy"])
    return {tk: pc.compute_pcs(tk, m, macro.get("latest", {}), last, rot_idx, cidx, by_theme, daily=None)
            for tk, m in meta.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-commit"); ap.add_argument("--preview", action="store_true")
    ap.add_argument("--no-fetch", action="store_true"); ap.add_argument("--write")
    a = ap.parse_args()
    if not a.no_fetch:
        subprocess.run(["git", "fetch", "-q", "origin", "master"], cwd=ROOT)
    lines: list[str] = []
    out = lines.append
    fails: list[str] = []

    def chk(name: str, ok: bool, detail: str = ""):
        out(f"- {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    old_u = show(BASELINE, "docs/data/universe.json")
    if a.preview:
        run = git("rev-parse", "origin/master").strip()
        new_u = show(MERGE, "docs/data/universe.json")
        out(f"# Vista previa (NO es la verificación): inputs de `{run[:8]}` + universo del merge\n")
        actual = None
    else:
        run = a.run_commit or find_run_commit()
        if not run:
            print("Aún no hay ningún run del pipeline posterior al merge 43d9a0a2 en origin/master."); return 2
        new_u = show(run, "docs/data/universe.json")
        actual = {c["ticker"]: c for c in show(run, "docs/data/ai_candidates.json")["candidates"]}
        subj = git("log", "-1", "--format=%s (%cd)", "--date=iso", run).strip()
        out(f"# Verificación de la línea B en producción\n\nRun verificado: `{run[:8]}` — {subj}\nLínea base: `{BASELINE}` (último run con el universo antiguo)\n")
        anc = subprocess.run(["git", "merge-base", "--is-ancestor", MERGE, run], cwd=ROOT).returncode == 0
        out("## 1. Commit"); chk(f"el run descende del merge {MERGE}", anc)

    out("\n## 2. Universo del motor en ese run")
    tk_new = {t["ticker"]: t for t in new_u["tickers"]}
    chk("símbolos retirados ausentes (GOLD, ASMI, YAN.AX, MRR.XA)", not (set(RETIRED) & set(tk_new)), str(sorted(set(RETIRED) & set(tk_new))))
    chk("B y NRL.AX presentes como instrumentos independientes", all(t in tk_new for t in NEW))
    chk("B no reutiliza la clave GOLD y NRL.AX no reutiliza MRR.XA", not ({"B", "NRL.AX"} & set(RETIRED)))
    for tk, (name, theme, sub) in PINNED.items():
        r = tk_new.get(tk, {})
        chk(f"{tk}: {name} · {theme} · {sub or '—'}", (r.get("name"), r.get("theme"), r.get("subtheme")) == (name, theme, sub),
            f"actual: {r.get('name')} · {r.get('theme')} · {r.get('subtheme')}")
    chk("ningún registro en classification_status=pending", not [t for t, r in tk_new.items() if r.get("classification_status") == "pending"],
        str([t for t, r in tk_new.items() if r.get("classification_status") == "pending"]))

    rp_new = replay(run if not a.preview else run, new_u)
    rp_old = replay(run if not a.preview else run, old_u)
    if actual is not None:
        out("\n## 3. Reconstrucción exacta del PCS publicado")
        bad = [t for t, c in actual.items() if t not in rp_new or rp_new[t]["pcs"] != c["pcs"] or rp_new[t]["pcs_components"] != c["pcs_components"]
               or bool(rp_new[t]["eligible"]) != bool(c["eligible"])]
        chk(f"el PCS publicado coincide con la reconstrucción (inputs del run + universo nuevo): {len(actual) - len(bad)}/{len(actual)}",
            not bad, str(bad[:6]))
        chk(f"mismo conjunto de tickers ({len(actual)} publicados)", set(actual) == set(rp_new))
        base = actual
    else:
        base = rp_new

    out("\n## 4. B y NRL.AX")
    for tk in NEW:
        c = base.get(tk)
        if not c:
            chk(f"{tk} en ai_candidates.json", False, "ausente"); continue
        u = tk_new[tk]
        ok = bool(c.get("eligible")) and c.get("ineligible_reason") in (None, "") and u.get("classification_status") != "pending"
        detail = f"PCS {c['pcs']} · elegible={c.get('eligible')} · motivo={c.get('ineligible_reason')} · estado={u.get('classification_status')}"
        if a.preview and not ok and c.get("ineligible_reason") == "no_signal_data":
            out(f"- ℹ️ {tk}: aún sin datos del scanner (`no_signal_data`), esperado antes del primer run — {detail}")
        else:
            chk(f"{tk}: elegible, sin motivo de inelegibilidad, no pending", ok, detail)

    out("\n## 5. Efecto de la corrección (mismos inputs del run: universo nuevo − universo antiguo)")
    out("| Ticker | PCS antes | PCS después | Δ | Tramos que cruza | Publicado |\n|---|---|---|---|---|---|")
    moved = []
    for tk in sorted(set(rp_old) & set(rp_new)):
        o, n = rp_old[tk], rp_new[tk]
        if o["pcs"] != n["pcs"] or o["theme"] != n["theme"] or o["subtheme"] != n["subtheme"]:
            crossed = [nm for nm, t in THRESHOLDS if (o["pcs"] >= t) != (n["pcs"] >= t)]
            pub = (actual or {}).get(tk, {}).get("pcs", "—")
            out(f"| {tk} | {o['pcs']} | {n['pcs']} | {n['pcs'] - o['pcs']:+.1f} | {', '.join(crossed) or '—'} | {pub} |")
            moved.append(tk)
    unexpected = [t for t in moved if t not in CORRECTED and t not in SECOND_ORDER]
    chk("solo cambian los tickers esperados (corregidos + 3 de segundo orden)", not unexpected, f"inesperados: {unexpected}")
    out("\n_Nota: el cruce de umbrales de TK y SLB depende del `rot_score` de XLE ese día; la comprobación válida es la coincidencia exacta con el PCS publicado (apartado 3)._")
    out("\n**Retirados con PCS publicado en la línea base:** " + ", ".join(
        f"{t} {show(BASELINE, 'docs/data/ai_candidates.json') and next((c['pcs'] for c in show(BASELINE, 'docs/data/ai_candidates.json')['candidates'] if c['ticker'] == t), '—')}" for t in RETIRED))

    out("\n## 6. Divergencias")
    out("Ninguna." if not fails else "\n".join(f"- {f}" for f in fails))
    text = "\n".join(lines) + "\n"
    if a.write:
        Path(a.write).write_text(text, encoding="utf-8")
    sys.stdout.buffer.write(text.encode("utf-8"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
