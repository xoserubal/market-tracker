"""Etapa 0 — desenlace de las empresas cuya serie termina antes del final de los datos (sin rendimientos posteriores).

Procedimiento determinista, por orden:
1. Acciones corporativas de Alpaca (registradas desde ~2020) de cualquier símbolo de la empresa, con fecha en
   [fin − 10, fin + 40] días naturales:
     cash_mergers → adquisición en efectivo; valor de salida = precio por acción pagado (conocido).
     stock_mergers → adquisición en acciones; valor = ratio × cierre del comprador en la fecha efectiva.
     stock_and_cash_mergers → mixta; valor = efectivo + ratio × cierre del comprador.
     worthless_removals → quiebra/liquidación con valor 0 (conocido).
     name_changes (el símbolo pasa a otro) → cambio de ticker: no es un desenlace económico (fallo de enlace).
2. Si Alpaca no registra nada: motivo de la baja en la tabla de cambios de Wikipedia (mismo ticker, ±45 días), por
   palabras clave: quiebra/liquidación, adquisición (tipo desconocido), fusión, escisión, exclusión/OTC, cambio de
   ticker. Valor de salida: DESCONOCIDO.
3. Si no hay nada: «fin de serie por causa desconocida». Valor: DESCONOCIDO.

Valores desconocidos: no se imputan. Se dan dos referencias que el preregistro usará como cotas en la sensibilidad:
el último cierre disponible (cota superior razonable en quiebras; estimación en adquisiciones, cuya precisión se mide
con los casos de 2020+ en los que Alpaca da los términos) y 0 (cota inferior absoluta).

Salidas: work/terminal_events_full.csv (con último cierre y valor de salida; fuera del repo por la licencia de
Alpaca), data/terminal_events.csv (sin precios: fecha, categoría, fuente, estado del valor) y data/terminal_summary.json
"""
import json
import re

import numpy as np
import pandas as pd

import fn_config as C
from s0_series import load_ca, symbols_for

SER = C.WORK / "series"
TERMS_TOL = 0.25   # |ln(último cierre / términos)| por encima del cual los términos de Alpaca no se aceptan
KW = [("quiebra_liquidacion", r"bankrupt|chapter 11|chapter 7|liquidat|insolv|receivership"),
      ("escision", r"spun off|spin-off|spinoff|spin off"),
      ("exclusion_otc", r"delist|otc|pink sheet"),
      ("cambio_ticker", r"renam|changed (its )?name|name change|ticker change|changed ticker"),
      ("fusion", r"merg"),
      ("adquisicion_tipo_desconocido", r"acqui|bought|purchas|taken private|buyout|buy-out|privat")]


def acquirer_close(sym, date, cache={}):
    """Cierre en bruto del comprador en la fecha efectiva (o la última sesión anterior), de nuestras series."""
    if sym not in cache:
        plan = pd.read_csv(C.WORK / "requests.csv", dtype=str, keep_default_na=False)
        keys = plan.loc[plan.ticker == sym, "key"].tolist()
        best = None
        for k in keys:
            for p in SER.glob(f"{k}__e*.parquet"):
                d = pd.read_parquet(p, columns=["date", "raw_close"])
                if best is None or d.date.max() > best.date.max():
                    best = d
        cache[sym] = best
    d = cache[sym]
    if d is None:
        return None
    d = d[d.date <= date]
    return float(d.raw_close.iat[-1]) if len(d) else None


def successor(r, cik_of, by_cik, summ):
    """Misma empresa (mismo CIK) con otra serie que sigue después del fin: cambio de ticker, no desenlace."""
    cik = cik_of.get(r["req_key"])
    if not cik:
        return None
    reqs = set(by_cik.get(cik, ()))
    for k, o in summ[summ.req_key.isin(reqs)].iterrows():
        if k == r["key"] or o["status"] != "ok":
            continue
        if o["start"] <= (pd.Timestamp(r["end"]) + pd.Timedelta(days=10)).date().isoformat() and o["end"] > r["end"]:
            return o["ticker"]
    return None


def classify(r, ca, ch, cik_of=None, by_cik=None, summ=None):
    syms = set(r["symbols"].split("|"))
    end = pd.Timestamp(r["end"])
    lo, hi = (end - pd.Timedelta(days=10)).date().isoformat(), (end + pd.Timedelta(days=40)).date().isoformat()

    def near(a, dk):
        d = a.get(dk) or a.get("effective_date") or a.get("process_date") or a.get("ex_date")
        return d and lo <= d <= hi
    raw = ca["raw"]
    for a in raw.get("cash_mergers", []):
        if a.get("acquiree_symbol") in syms and near(a, "effective_date"):
            return "adquisicion_efectivo", float(a["rate"]), "alpaca", f"{a.get('rate')} USD"
    for a in raw.get("stock_and_cash_mergers", []):
        if a.get("acquiree_symbol") in syms and near(a, "effective_date"):
            px = acquirer_close(a.get("acquirer_symbol"), a.get("effective_date"))
            ratio = float(a.get("acquirer_rate") or 0) / float(a.get("acquiree_rate") or 1)
            cash = float(a.get("cash_rate") or a.get("rate") or 0)
            v = cash + ratio * px if px is not None else None
            return "adquisicion_mixta", v, "alpaca", f"{cash} USD + {ratio:.4g} x {a.get('acquirer_symbol')}"
    for a in raw.get("stock_mergers", []):
        if a.get("acquiree_symbol") in syms and near(a, "effective_date"):
            px = acquirer_close(a.get("acquirer_symbol"), a.get("effective_date"))
            ratio = float(a.get("acquirer_rate") or 0) / float(a.get("acquiree_rate") or 1)
            return ("adquisicion_acciones", ratio * px if px is not None else None, "alpaca",
                    f"{ratio:.4g} x {a.get('acquirer_symbol')}")
    for a in raw.get("worthless_removals", []):
        if a.get("symbol") in syms and near(a, "process_date"):
            return "quiebra_liquidacion", 0.0, "alpaca", "worthless_removal"
    for a in raw.get("name_changes", []):
        if a.get("old_symbol") in syms and near(a, "process_date"):
            return "cambio_ticker", None, "alpaca", f"{a.get('old_symbol')} -> {a.get('new_symbol')}"
    if cik_of is not None:
        nxt = successor(r, cik_of, by_cik, summ)
        if nxt:
            return "cambio_ticker", None, "sec_cik", f"misma empresa continúa como {nxt}"
    rows = ch[(ch.rem_t.isin(syms)) & (ch.date >= (end - pd.Timedelta(days=45))) &
              (ch.date <= (end + pd.Timedelta(days=45)))]
    for reason in rows.reason.astype(str):
        low = reason.lower()
        for cat, pat in KW:
            if re.search(pat, low):
                return cat, None, "wikipedia", reason[:160]
    if len(rows):
        return "desconocido_con_baja", None, "wikipedia", str(rows.reason.iat[0])[:160]
    return "desconocido", None, "", ""


def main():
    s = pd.read_csv(C.WORK / "series_summary.csv", dtype=str, keep_default_na=False)
    s = s[(s.status == "ok") & (s.terminated == "True")]
    ca = load_ca()
    allsum = pd.read_csv(C.WORK / "series_summary.csv", dtype=str, keep_default_na=False).set_index("key")
    cm = pd.read_csv(C.SEC / "cik_map.csv", dtype=str, keep_default_na=False)
    cik_of = {k: c for k, c in zip(cm.key, cm.cik) if c}
    by_cik = {}
    for k, c in cik_of.items():
        by_cik.setdefault(c, []).append(k)
    ch = pd.read_csv(C.PUB / "changes.csv", dtype=str)
    ch["date"] = pd.to_datetime(ch.date)
    out = []
    for r in s.to_dict("records"):
        cat, val, src, det = classify(r, ca, ch, cik_of, by_cik, allsum)
        lc = float(r["last_close_raw"])
        status = "conocido" if val is not None else ("no_aplica" if cat == "cambio_ticker" else "desconocido")
        if val is not None and val > 0 and lc > 0 and abs(np.log(lc / val)) > TERMS_TOL:
            status = "terminos_incoherentes"
        out.append({"key": r["key"], "ticker": r["ticker"], "names": r["names"], "indices": r["indices"],
                    "end": r["end"], "year": r["end"][:4], "category": cat, "source": src, "detail": det,
                    "last_close": lc, "terminal_value": val, "value_status": status,
                    "ln_last_vs_terminal": (np.log(lc / val) if val and val > 0 and lc > 0 else None)})
    t = pd.DataFrame(out)
    t.to_csv(C.WORK / "terminal_events_full.csv", index=False)          # con precios: fuera del repo (licencia)
    t.drop(columns=["last_close", "terminal_value", "ln_last_vs_terminal"]).to_csv(C.PUB / "terminal_events.csv",
                                                                                   index=False)
    known = t[(t.value_status == "conocido") & t.ln_last_vs_terminal.notna()]
    summ = {"terminated": int(len(t)), "by_category": t.category.value_counts().to_dict(),
            "by_source": t.source.value_counts().to_dict(),
            "by_year_category": t.groupby(["year", "category"]).size().unstack(fill_value=0).to_dict("index"),
            "value_status": t.value_status.value_counts().to_dict(),
            "value_status_by_category": t.groupby(["category", "value_status"]).size().unstack(fill_value=0).to_dict("index"),
            "last_close_vs_terms": {c: {"n": int(len(g)), "median_abs_ln": float(g.ln_last_vs_terminal.abs().median()),
                                         "p90_abs_ln": float(g.ln_last_vs_terminal.abs().quantile(.9)),
                                         "max_abs_ln": float(g.ln_last_vs_terminal.abs().max())}
                                    for c, g in known.groupby("category")}}
    json.dump(summ, open(C.PUB / "terminal_summary.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in summ.items() if k != "by_year_category"}, indent=1, default=str))


if __name__ == "__main__":
    main()
