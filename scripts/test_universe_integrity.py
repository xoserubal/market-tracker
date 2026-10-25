"""
test_universe_integrity.py — regresión de la corrección de integridad del universo (línea B).

Sin pytest, sin red, mismo estilo que test_cava_mapping.py:
    py -3 scripts/test_universe_integrity.py            # ejecuta los tests
    py -3 scripts/test_universe_integrity.py --regen-golden   # regenera golden_b1.json (revisar a mano antes de commitear)

Qué protege
  T1  El código actual de PCS, con el universo ANTERIOR a la corrección, reproduce el
      ai_candidates.json publicado el 2026-10-24 (149/149). Si falla, alguien tocó una
      fórmula o un peso: eso no es una corrección de universo.
  T2  El universo corregido produce EXACTAMENTE el conjunto de cambios esperado
      (golden_b1.json): ningún otro ticker cambia de PCS, elegibilidad, tema ni subtema.
  T3  El universo real (docs/data/universe.json) cumple las invariantes de integridad y
      los campos corregidos siguen como se aprobaron.
  T4  sync_universe: fail-closed para tickers nuevos, sin tocar los existentes; idempotente.
  T5  PCS: un registro "pending" no es elegible (con motivo propio) aunque tenga datos;
      no se confunde con tradable=False.
  T6  La sincronización con el YAML real es una operación nula.
  T7  B y NRL.AX no quedan excluidos de forma permanente: sin datos del scanner son 'no_signal_data'
      (no 'unclassified'); con las filas reales del scanner pasan a elegibles. Fixture: salida real
      de scan_stocks() del 2026-10-25, validada contra tres controles publicados (USAU, VGZ, MRR.XA).

Fixtures: tests/fixtures/universe_integrity/ (datos congelados del commit e728e75d,
recortados a lo que lee el PCS). Nada de aquí accede a información privada.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "tests" / "fixtures" / "universe_integrity"
sys.path.insert(0, str(ROOT / "scripts"))

import pcs_calculator as pc          # noqa: E402
import paper_trading as pt           # noqa: E402
import sync_universe as su           # noqa: E402

THRESHOLDS = (("HC82", 82), ("CFL75", 75), ("ER68", 68), ("MTB62", 62))


def _load(name: str):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def simulate(universe: dict) -> dict[str, dict]:
    """compute_pcs() real, sin red y con daily=None (DEMS/extension_risk no entran en el PCS)."""
    macro, rot_j, cand_j = _load("macro_min.json"), _load("rotation_signals.json"), _load("stock_candidates.json")
    macro_latest = macro.get("latest", {})
    hist = macro.get("history", [])
    last_hist = hist[-1] if hist else {}
    rot_idx = {s["ticker"]: s for s in rot_j.get("latest_signals", [])}
    u_meta = {t["ticker"]: t for t in universe.get("tickers", [])}
    cand_idx = {}
    for c in cand_j.get("candidates", []):
        e = dict(c)
        if c["ticker"] in u_meta:
            e["theme"] = u_meta[c["ticker"]].get("theme", "")
        cand_idx[c["ticker"]] = e
    by_theme: dict[str, list] = {}
    for c in cand_idx.values():
        if c.get("theme") and c.get("ret_13w_vs_spy") is not None:
            by_theme.setdefault(c["theme"], []).append(c["ret_13w_vs_spy"])
    return {tk: pc.compute_pcs(tk, m, macro_latest, last_hist, rot_idx, cand_idx, by_theme, daily=None)
            for tk, m in u_meta.items()}


def _row(c: dict) -> dict:
    return {"pcs": c["pcs"], "eligible": bool(c["eligible"]), "theme": c["theme"], "subtheme": c["subtheme"],
            "component_B": c["component_B"]}


def build_golden_b1() -> dict:
    """Delta entre el estado publicado (B0) y el universo corregido, calculado con el código actual."""
    b0 = {tk: _row(c) for tk, c in simulate(_load("universe_before.json")).items()}
    new = simulate(_load("universe_after_b1.json"))
    b1 = {tk: _row(c) for tk, c in new.items()}
    changed = {tk: {"before": b0[tk], "after": b1[tk]} for tk in sorted(set(b0) & set(b1)) if b0[tk] != b1[tk]}
    picks = _load("open_positions.json")
    conc0, _ = pt.compute_theme_concentration(list(simulate(_load("universe_before.json")).values()), picks)
    conc1, exp1 = pt.compute_theme_concentration(list(new.values()), picks)
    conc_changed = {tk: {"before": conc0.get(tk), "after": conc1.get(tk)}
                    for tk in sorted(set(conc0) | set(conc1)) if conc0.get(tk) != conc1.get(tk)}

    def summ(rows):
        el = [r for r in rows.values() if r["eligible"]]
        return {"total": len(rows), "eligible": len(el), **{n: sum(1 for r in el if r["pcs"] >= t) for n, t in THRESHOLDS}}

    return {
        "source_commit": "e728e75d",
        "removed": sorted(set(b0) - set(b1)),
        "added": sorted(set(b1) - set(b0)),
        "changed": changed,
        "summary_before": summ(b0),
        "summary_after": summ(b1),
        "concentration_changed": conc_changed,
        "theme_exposure_after": {k: [v["open_positions"], v["risk"]] for k, v in sorted(exp1.items())},
    }


# ── mini-runner ──────────────────────────────────────────────────────────────
_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    _results.append((name, bool(ok), detail))


def t1_baseline():
    golden = _load("golden_b0.json")
    got = simulate(_load("universe_before.json"))
    bad = [tk for tk, g in golden.items()
           if tk not in got or got[tk]["pcs"] != g["pcs"] or got[tk]["pcs_components"] != g["components"]
           or bool(got[tk]["eligible"]) != g["eligible"] or got[tk]["theme"] != g["theme"]]
    check("T1 B0 reproduce el ai_candidates publicado", not bad and len(got) == len(golden),
          f"{len(golden) - len(bad)}/{len(golden)} idénticos; difieren: {bad[:5]}")


def t2_golden():
    expected = _load("golden_b1.json")
    actual = build_golden_b1()
    for key in ("removed", "added", "changed", "summary_before", "summary_after", "concentration_changed", "theme_exposure_after"):
        check(f"T2 golden B1: {key}", actual[key] == expected[key],
              "" if actual[key] == expected[key] else f"esperado {json.dumps(expected[key], ensure_ascii=False)[:300]} | actual {json.dumps(actual[key], ensure_ascii=False)[:300]}")


# Campos corregidos que NO deben revertirse (aprobados en la línea B).
PINNED = {
    "VAL": {"name": "Valaris", "subtheme": "offshore_drilling"},
    "SLP.L": {"name": "Sylvania Platinum", "subtheme": "pgm_miners", "theme_proxy": ""},
    "DMX.V": {"name": "District Metals", "theme": "uranium_nuclear", "subtheme": "uranium_exploration"},
    "SSV.V": {"name": "Southern Silver Exploration"},
    "PNPN.V": {"name": "Power Metallic Mines"},
    "DPM.TO": {"name": "DPM Metals"},
    "GLEN.L": {"theme": "commodities_metals", "subtheme": "diversified_miners", "theme_proxy": "", "region": "UK"},
    "SMR.AX": {"theme": "commodities_metals", "subtheme": "met_coal", "region": "Australia"},
    "AFM.V": {"theme": "commodities_metals", "theme_proxy": "", "region": "Canada"},
    "SLB": {"theme": "oil_gas", "subtheme": "oilfield_services", "theme_proxy": "XLE"},
    "TTI": {"theme": "oil_gas", "subtheme": "oilfield_services", "theme_proxy": ""},
    "TK": {"theme": "oil_gas", "subtheme": "tankers", "theme_proxy": ""},          # sin proxy: XLE no representa fletes
    "MOS": {"theme": "us_cyclical", "subtheme": "fertilizers", "theme_proxy": "XLB"},
    "TECK": {"theme": "commodities_copper", "theme_proxy": "COPX"},
    "KTOS": {"asset_type": "stock", "theme": "defense_space"},
    "SAIA": {"asset_type": "stock", "theme": "us_cyclical"},
    "GS": {"theme_proxy": "XLF"},
    "III.TO": {"region": "Canada"},
    "B": {"name": "Barrick Mining", "theme": "silver_gold_miners", "subtheme": "gold_miners"},
    "NRL.AX": {"name": "Northstone Resources", "region": "Australia"},
}
RETIRED = {"GOLD", "ASMI", "YAN.AX", "MRR.XA"}


def t3_real_universe():
    import yaml
    u = json.loads((ROOT / "docs" / "data" / "universe.json").read_text(encoding="utf-8"))
    recs = {}
    dups = []
    for r in u["tickers"]:
        (dups.append(r["ticker"]) if r["ticker"] in recs else None)
        recs[r["ticker"]] = r
    check("T3 universe sin tickers duplicados", not dups, str(dups))
    check("T3 símbolos retirados ausentes (GOLD/ASMI/YAN.AX/MRR.XA)", not (RETIRED & set(recs)), str(RETIRED & set(recs)))
    ycfg = yaml.safe_load((ROOT / "backtest" / "config" / "individual_stocks.yaml").read_text(encoding="utf-8"))
    ytk = [s["ticker"] for st in (ycfg.get("clusters") or {}).values() for s in (st or [])]
    check("T3 YAML sin duplicados", len(ytk) == len(set(ytk)), str([t for t in set(ytk) if ytk.count(t) > 1]))
    check("T3 universe ≡ YAML (1:1)", set(ytk) == set(recs), f"solo YAML: {set(ytk) - set(recs)}; solo universe: {set(recs) - set(ytk)}")
    for tk, fields in PINNED.items():
        r = recs.get(tk)
        wrong = {k: (r.get(k) if r else "<ausente>", v) for k, v in fields.items() if not r or r.get(k) != v}
        check(f"T3 {tk} conserva lo aprobado", not wrong, str(wrong))
    # Barrick y Northstone son instrumentos nuevos: no heredan nada de GOLD/MRR.XA
    check("T3 B no es GOLD", "B" in recs and "GOLD" not in recs)
    # ningún registro "pending" colado sin revisar en el universo versionado
    pend = [tk for tk, r in recs.items() if r.get("classification_status") == "pending"]
    check("T3 sin registros pending (informativo: lista de revisión pendiente)", True, f"pendientes: {pend}")


def _tmp_sync(universe: dict, yaml_text: str):
    tmp = Path(tempfile.mkdtemp())
    (tmp / "u.json").write_text(json.dumps(universe, ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp / "s.yaml").write_text(yaml_text, encoding="utf-8")
    old = (su.UNIV_PATH, su.YAML_PATH)
    su.UNIV_PATH, su.YAML_PATH = tmp / "u.json", tmp / "s.yaml"
    try:
        su.sync(verbose=False)
        return json.loads((tmp / "u.json").read_text(encoding="utf-8"))
    finally:
        su.UNIV_PATH, su.YAML_PATH = old
        shutil.rmtree(tmp, ignore_errors=True)


def t4_sync_fail_closed():
    existing = {"version": "1.0", "updated": "x", "themes": ["oil_gas"], "tickers": [
        {"ticker": "OLD", "name": "Old Co", "asset_type": "stock", "tradable": True, "theme": "oil_gas", "subtheme": "us_oil",
         "region": "US", "macro_proxy": "BZ=F", "theme_proxy": "XLE", "benchmark": "SPY", "priority": "high", "notes": "n"}]}
    yaml_text = ('clusters:\n  Value/Cyclical:\n    - ticker: OLD\n      note: "n"\n  Commodities:\n    - ticker: NEWCO\n      note: "nota"\n'
                 '  Portfolio:\n    - ticker: NEWPF\n      note: "desde Portfolio Tracker"\n')
    out = _tmp_sync(existing, yaml_text)
    by = {t["ticker"]: t for t in out["tickers"]}
    check("T4 registro existente intacto", by["OLD"] == existing["tickers"][0], str(by["OLD"]))
    for tk in ("NEWCO", "NEWPF"):
        r = by[tk]
        ok = (r["classification_status"] == "pending" and r["theme"] == "" and r["subtheme"] == "" and r["theme_proxy"] == ""
              and r["macro_proxy"] == "" and r["region"] == "" and r["tradable"] is True)
        check(f"T4 {tk}: nuevo → sin clasificar y sin tema/proxy heredado", ok, str(r))
    check("T4 NEWCO guarda la pista del cluster sin aplicarla", by["NEWCO"]["suggested_from_cluster"]["cluster"] == "Commodities")
    check("T4 los themes del fichero no incluyen temas inventados", out["themes"] == ["oil_gas"], str(out["themes"]))
    again = _tmp_sync(out, yaml_text)
    strip = lambda d: {k: v for k, v in d.items() if k != "updated"}
    check("T4 segunda sincronización idempotente", strip(again) == strip(out))


def t5_pcs_gate():
    macro, rot_j, cand_j = _load("macro_min.json"), _load("rotation_signals.json"), _load("stock_candidates.json")
    rot_idx = {s["ticker"]: s for s in rot_j["latest_signals"]}
    cand_idx = {c["ticker"]: c for c in cand_j["candidates"]}
    tk = "NVDA"
    assert tk in cand_idx

    def run(meta):
        return pc.compute_pcs(tk, meta, macro["latest"], macro["history"][-1], rot_idx, cand_idx, {}, daily=None)

    base = {"theme": "us_tech_ai", "theme_proxy": "XLK", "priority": "high", "tradable": True}
    r_ok = run(base)
    r_pend = run({**base, "classification_status": "pending", "theme": "", "theme_proxy": ""})
    r_rev = run({**base, "classification_status": "reviewed"})
    r_nt = run({**base, "tradable": False})
    check("T5 con datos y clasificado → elegible, sin motivo", r_ok["eligible"] is True and r_ok["ineligible_reason"] is None)
    check("T5 pending → no elegible, motivo 'unclassified'", r_pend["eligible"] is False and r_pend["ineligible_reason"] == "unclassified",
          str((r_pend["eligible"], r_pend["ineligible_reason"])))
    check("T5 'reviewed' vuelve a ser elegible", r_rev["eligible"] is True)
    check("T5 tradable=False → motivo 'not_tradable' (distinto de 'unclassified')", r_nt["ineligible_reason"] == "not_tradable")
    check("T5 el PCS numérico de pending no cambia por el estado (solo la elegibilidad)",
          run({**base, "classification_status": "pending"})["pcs"] == r_ok["pcs"])


def t6_real_sync_noop():
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "docs" / "data" / "universe.json", tmp / "u.json")
    old = su.UNIV_PATH
    su.UNIV_PATH = tmp / "u.json"
    try:
        su.sync(verbose=False)
        a = json.loads((ROOT / "docs" / "data" / "universe.json").read_text(encoding="utf-8"))
        b = json.loads((tmp / "u.json").read_text(encoding="utf-8"))
        a.pop("updated", None); b.pop("updated", None)
        check("T6 sync con el YAML real no cambia el universo versionado", a == b)
    finally:
        su.UNIV_PATH = old
        shutil.rmtree(tmp, ignore_errors=True)


def t7_new_tickers_not_locked_out():
    """B y NRL.AX: fail-closed no debe dejarlos fuera para siempre."""
    uni = _load("universe_after_b1.json")
    meta = {t["ticker"]: t for t in uni["tickers"]}
    rows = _load("scanner_rows_new_tickers.json")
    for tk in ("B", "NRL.AX"):
        check(f"T7 {tk}: registro clasificado (sin 'pending'), tradable y con tema",
              meta[tk].get("classification_status") != "pending" and meta[tk]["tradable"] is True and bool(meta[tk]["theme"]),
              str({k: meta[tk].get(k) for k in ("classification_status", "tradable", "theme")}))
    sin_datos = simulate(uni)
    for tk in ("B", "NRL.AX"):
        check(f"T7 {tk} sin datos del scanner: 'no_signal_data' (no 'unclassified')",
              sin_datos[tk]["eligible"] is False and sin_datos[tk]["ineligible_reason"] == "no_signal_data",
              str((sin_datos[tk]["eligible"], sin_datos[tk]["ineligible_reason"])))
    orig = globals()["_load"]

    def with_rows(name):
        d = orig(name)
        if name == "stock_candidates.json":
            d = json.loads(json.dumps(d)); d["candidates"].extend(rows)
        return d

    globals()["_load"] = with_rows
    try:
        con_datos = simulate(uni)
    finally:
        globals()["_load"] = orig
    for tk in ("B", "NRL.AX"):
        r = con_datos[tk]
        check(f"T7 {tk} con datos del scanner: elegible y sin motivo de inelegibilidad",
              r["eligible"] is True and r["ineligible_reason"] is None, str((r["pcs"], r["eligible"], r["ineligible_reason"])))
    # entrada de B y NRL.AX no mueve a ningún compañero
    movidos = [tk for tk in sin_datos if tk not in ("B", "NRL.AX") and sin_datos[tk]["pcs"] != con_datos[tk]["pcs"]]
    check("T7 la entrada de B y NRL.AX no cambia el PCS de ningún compañero", not movidos, str(movidos))
    # y los símbolos retirados no comparten clave con los nuevos (series distintas por construcción)
    check("T7 B y NRL.AX son claves distintas de GOLD y MRR.XA", not ({"B", "NRL.AX"} & {"GOLD", "MRR.XA"}))


def main() -> int:
    if "--regen-golden" in sys.argv:
        g = build_golden_b1()
        (FX / "golden_b1.json").write_text(json.dumps(g, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")
        print(f"golden_b1.json regenerado: {len(g['changed'])} cambiados, +{g['added']} -{g['removed']}")
        return 0
    for fn in (t1_baseline, t2_golden, t3_real_universe, t4_sync_fail_closed, t5_pcs_gate, t6_real_sync_noop, t7_new_tickers_not_locked_out):
        try:
            fn()
        except Exception as e:   # un fallo de infraestructura cuenta como fallo del test
            check(f"{fn.__name__} (excepción)", False, repr(e))
    bad = [r for r in _results if not r[1]]
    for name, ok, detail in _results:
        print(("  ok   " if ok else "  FAIL ") + name + (f"\n         {detail}" if (detail and not ok) or name.startswith("T3 sin registros pending") else ""))
    print(f"\n{len(_results) - len(bad)}/{len(_results)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
