"""Etapa 0 — capitalización histórica con datos de la SEC (sin rendimientos posteriores).

1. Enlace empresa → CIK, por orden de preferencia (y con su nivel de confianza):
   a) CIK de las instantáneas de Wikipedia del índice (S&P 500, S&P 600);
   b) company_tickers.json de la SEC (tickers vigentes), solo si el nombre coincide (si no: «ticker reutilizado»);
   c) búsqueda por nombre en EDGAR (empresas desaparecidas), aceptada solo si el nombre coincide.
2. Acciones en circulación: dei:EntityCommonStockSharesOutstanding (portada de 10-K/10-Q), con fecha de presentación.
   Varias cifras con la misma fecha de cierre y presentación = varias clases de acciones (se suman y se marca).
3. Capitalización en t = precio en bruto de t × acciones de la última presentación con fecha <= t, corregidas por los
   splits aplicados entre la fecha de cierre del dato y t. Solo se usa si la presentación tiene <= 400 días.
Controles: saltos de capitalización > x2 en un día sin movimiento de precio equivalente (enlace o clase dudosos).

Salidas: sec/cik_map.csv, sec/shares/<cik>.json (fuera del repo); data/sec_coverage.json (agregados, en el repo)
"""
import json
import re
import time
from difflib import SequenceMatcher

import pandas as pd
import requests

import fn_config as C
from s0_universe import _norm_name, SB

UA = {"User-Agent": "FlowNegResearch research@example.org"}
SH = C.SEC / "shares"
SH.mkdir(exist_ok=True)


def sec_get(url, params=None):
    for i in range(6):
        try:
            r = requests.get(url, headers=UA, params=params, timeout=30)
            time.sleep(0.15)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def name_sim(a, b):
    wa, wb = " ".join(_norm_name(a)), " ".join(_norm_name(b))
    if not wa or not wb:
        return 0.0
    return SequenceMatcher(None, wa, wb).ratio()


def wiki_ciks():
    """ticker → {cik} de las instantáneas con columna CIK."""
    import io
    out = {}
    files = list(SB.glob("wiki_*.html")) + list(C.WIKI.glob("sp600_*.html")) + list(C.WIKI.glob("sp400_*.html"))
    for f in files:
        try:
            tabs = pd.read_html(io.StringIO(f.read_text(encoding="utf-8")))
        except ValueError:
            continue
        for t in tabs:
            cols = [str(c) for c in t.columns]
            if any("Added" in c for c in cols):
                continue
            cc = next((c for c in t.columns if "CIK" in str(c)), None)
            tc = next((c for c in t.columns if re.search(r"ymbol|icker", str(c))), None)
            if cc is None or tc is None:
                continue
            for tk, ck in zip(t[tc], t[cc]):
                tk = str(tk).strip().upper().replace("-", ".")
                try:
                    out.setdefault(tk, set()).add(int(float(ck)))
                except (TypeError, ValueError):
                    pass
    return out


def build_map(plan):
    path = C.SEC / "cik_map.csv"
    done = pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame(columns=["key"])
    done_keys = set(done["key"])
    wk = wiki_ciks()
    ct = sec_get("https://www.sec.gov/files/company_tickers.json").json()
    cur = {v["ticker"].upper().replace("-", "."): (int(v["cik_str"]), v["title"]) for v in ct.values()}
    rows = []
    for r in plan.to_dict("records"):
        if r["key"] in done_keys:
            continue
        name = r["names"].split(" | ")[0]
        res = {"key": r["key"], "ticker": r["ticker"], "name": name, "cik": "", "method": "", "sec_name": "",
               "sim": ""}
        cands = wk.get(r["ticker"], set())
        if len(cands) == 1:
            res.update(cik=str(next(iter(cands))), method="wikipedia")
        elif r["ticker"] in cur and name_sim(name, cur[r["ticker"]][1]) >= 0.6:
            res.update(cik=str(cur[r["ticker"]][0]), method="sec_tickers", sec_name=cur[r["ticker"]][1],
                       sim=round(name_sim(name, cur[r["ticker"]][1]), 2))
        else:
            q = sec_get("https://efts.sec.gov/LATEST/search-index", {"keysTyped": name})
            hits = (q.json().get("hits", {}).get("hits", []) if q is not None else [])
            best = None
            for h in hits[:5]:
                s = name_sim(name, h["_source"].get("entity", ""))
                if best is None or s > best[0]:
                    best = (s, h["_id"], h["_source"].get("entity", ""))
            if best and best[0] >= 0.75:
                res.update(cik=str(int(best[1])), method="edgar_name", sec_name=best[2], sim=round(best[0], 2))
            elif len(cands) > 1:
                res.update(method="wikipedia_ambiguous")
            else:
                res.update(method="unmatched", sec_name=best[2] if best else "", sim=round(best[0], 2) if best else "")
        rows.append(res)
        if len(rows) % 100 == 0:
            pd.concat([done, pd.DataFrame(rows)]).to_csv(path, index=False)
            print("cik", len(rows), flush=True)
    m = pd.concat([done, pd.DataFrame(rows)])
    m.to_csv(path, index=False)
    return m


def fetch_shares(ciks):
    for k, cik in enumerate(sorted(set(ciks))):
        f = SH / f"{cik}.json"
        if f.exists():
            continue
        r = sec_get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{int(cik):010d}/dei/"
                    "EntityCommonStockSharesOutstanding.json")
        f.write_text(json.dumps(r.json()["units"].get("shares", []) if r is not None else []))
        if k % 200 == 0:
            print("acciones", k, flush=True)


def main():
    plan = pd.read_csv(C.WORK / "requests.csv", dtype=str, keep_default_na=False)
    m = build_map(plan)
    print(m.method.value_counts().to_dict())
    fetch_shares(m.loc[m.cik.fillna("") != "", "cik"])


if __name__ == "__main__":
    main()
