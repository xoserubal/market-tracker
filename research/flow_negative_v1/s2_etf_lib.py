"""D2 (viabilidad) — carteras de ETF que replican el S&P 600 / S&P 400, sacadas de EDGAR.

Solo lectura de documentos públicos de la SEC. Nada de precios ni rendimientos. Documentos en bruto fuera del repo
(FLOWNEG_DATA_DIR/etf_holdings/raw); en el repo solo código y agregados.

Fuentes (series de EDGAR):
  S&P 600: IJR (iShares, S000004313), SLY/SPSM (SPDR, S000006989 / S000041317), VIOO (Vanguard, S000030017)
  S&P 400: IJH (iShares, S000004307), SPMD (SPDR, S000006986), IVOO (Vanguard, S000030014)
  MDY es un fideicomiso de inversión (UIT) y no presenta N-Q/N-PORT con la misma estructura: no se usa.

Formatos:
  N-Q, N-CSR, N-CSRS (hasta 2019): HTML con nombre, acciones y valor. SIN identificador (ni CUSIP ni ticker).
  NPORT-P (desde 2019): XML con nombre, CUSIP, ISIN y a veces ticker.
"""
import html
import json
import re
import time
from pathlib import Path

import requests

import fn_config as C

ETF = C.DATA / "etf_holdings"
RAW = ETF / "raw"
RAW.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "FlowNegResearch ir@xoserubal.com"}

SERIES = {"IJR": "S000004313", "IJH": "S000004307", "SLY": "S000006989", "SPSM": "S000041317",
          "SPMD": "S000006986", "VIOO": "S000030017", "IVOO": "S000030014"}
INDEX_OF = {"IJR": "sp600", "SLY": "sp600", "SPSM": "sp600", "VIOO": "sp600",
            "IJH": "sp400", "SPMD": "sp400", "IVOO": "sp400"}
# Título del fondo dentro de los documentos combinados del fideicomiso (cabecera de cada página de la cartera)
_S = r"(?:\s|<[^>]*>|&nbsp;|&#160;|&reg;|&#174;)+"


def _t(*words):
    return _S.join(words)


_SP = r"S&(?:amp;)?P"
# Título del fondo dentro de los documentos combinados del fideicomiso (cabecera de cada página de la cartera).
# Tolera etiquetas HTML y «®» entre palabras. SPDR: SPMD solo sigue el S&P 400 tras su cambio de índice de 2017 (antes
# era el SPDR S&P 1000, SMD); la fuente principal del S&P 400 es IJH + IVOO.
TITLE = {
    "IJR": _t("CORE", _SP, r"SMALL-CAP", "ETF"),
    "IJH": _t("CORE", _SP, r"MID-CAP", "ETF"),
    "SLY": _t("SPDR", _SP, "600", "Small", "Cap", "ETF") + r"(?!" + _S + r"\(?SLY[GV]|" + _S + "(?:Growth|Value))",
    "SPMD": _t("SPDR", "Portfolio", "Mid", "Cap", "ETF"),
    "VIOO": _t(_SP, r"Small-Cap", "600", "Index", "Fund"),
    "IVOO": _t(_SP, r"Mid-Cap", "400", "Index", "Fund"),
}
EXPECTED = {"sp600": (540, 720), "sp400": (360, 470)}   # posiciones plausibles de una cartera completa
END = r"(?i)TOTAL\s+COMMON\s+STOCKS|TOTAL\s+INVESTMENTS"


def sec_get(url, binary=False):
    for i in range(6):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            time.sleep(0.15)
            if r.status_code == 200:
                return r.content if binary else r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def cached(url, name):
    f = RAW / name
    if not f.exists():
        b = sec_get(url, binary=True)
        if b is None:
            return None
        f.write_bytes(b)
    return f.read_bytes().decode("latin-1")


def filing_docs(index_url):
    """Documentos de una presentación y su periodo de cartera."""
    t = sec_get(index_url) or ""
    per = re.search(r"Period of Report</div>\s*<div class=\"info\">(.*?)<", t)
    docs = re.findall(r'<td scope="row"><a href="(.*?)">.*?</a>.*?<td scope="row">(.*?)</td>\s*<td scope="row">(\d*)</td>',
                      t, re.S)
    return (per.group(1) if per else None), [(f"https://www.sec.gov{u}", ty, int(sz or 0)) for u, ty, sz in docs]


# ------------------------------------------------------------------------------------------------- N-Q (HTML)
_NUM = re.compile(r"^\(?\$?\s*[\d,]+(?:\.\d+)?\)?$")


def _cells(tr):
    out = []
    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I):
        x = html.unescape(re.sub(r"<[^>]+>", " ", c)).replace("\xa0", " ")
        x = re.sub(r"\s+", " ", x).strip()
        if x and x != "$":
            out.append(x)
    return out


def _parse_region(doc, start, endm):
    end = endm.start() if endm else len(doc)
    region = doc[start:end]
    rows, section = [], ""
    for tr in re.findall(r"<tr.*?</tr>", region, re.S | re.I):
        cs = _cells(tr)
        if not cs:
            continue
        joined = " ".join(cs)
        sec = re.match(r"^(COMMON STOCKS|RIGHTS|WARRANTS|SHORT-TERM INVESTMENTS|MONEY MARKET FUNDS|INVESTMENT COMPANIES|"
                       r"PREFERRED STOCKS|REAL ESTATE INVESTMENT TRUSTS).*?[—–-]\s*[\d.]+\s*%", joined, re.I)
        if sec:
            section = sec.group(1).upper()
        while cs and re.fullmatch(r"[*^†‡§#+,\s]+", cs[0]):   # marcas de nota en celda aparte (Vanguard «*»)
            cs = cs[1:]
        if len(cs) >= 3 and _NUM.match(cs[-1]) and _NUM.match(cs[-2]) and not _NUM.match(cs[0]):
            name = cs[0]
            if re.match(r"^(Total|TOTAL|Other securities|OTHER SECURITIES)", name):
                continue
            rows.append({"name": name, "shares": float(re.sub(r"[^\d.]", "", cs[-2])),
                         "value": float(re.sub(r"[^\d.]", "", cs[-1])), "section": section})
    reported = None
    if endm:
        i0 = max(doc.rfind("<tr", 0, endm.start()), doc.rfind("<TR", 0, endm.start()))
        ends = [m.end() for m, _ in zip(re.compile(r"</tr>", re.I).finditer(doc, endm.start()), range(3))]
        if i0 >= 0 and ends:
            for e in ends:   # el total puede ir en la misma fila o en las dos siguientes («(Cost: …)» y la cifra)
                nums = [c for c in _cells(doc[i0:e]) if _NUM.match(c) and float(re.sub(r"[^\d.]", "", c) or 0) > 0]
                if nums:
                    reported = float(re.sub(r"[^\d.]", "", nums[-1]))
                    break
    return {"rows": rows, "reported_total": reported, "parsed_total": sum(r["value"] for r in rows), "start": start}


def parse_html_holdings(doc, tk):
    """Posiciones de acciones del fondo tk en un documento HTML combinado de varios fondos.
    Una región empieza en una cabecera del fondo seguida de «COMMON STOCKS» y «Shares» y termina en el primer
    «Total common stocks / Total investments». Un documento puede tener varias regiones del mismo fondo: los informes
    anuales de iShares traen primero un «Summary Schedule of Investments» (solo las mayores posiciones) y la cartera
    completa más adelante (Item 6). Se elige la región con más posiciones."""
    hits = [m.start() for m in re.finditer(TITLE[tk], doc, re.I)]
    if not hits:
        return None
    end_re = re.compile(END)
    best, seen = None, set()
    for h in hits:
        seg = doc[h:h + 20000]
        if not (re.search(r"COMMON\s+STOCKS", seg, re.I) and re.search(r"Shares", seg, re.I)):
            continue
        endm = end_re.search(doc, h)
        key = endm.start() if endm else -1
        if key in seen:
            continue
        seen.add(key)
        p = _parse_region(doc, h, endm)
        lo, hi = EXPECTED[INDEX_OF[tk]]
        p["ok_total"] = p["reported_total"] is not None and abs(p["parsed_total"] - p["reported_total"]) < 2
        p["in_range"] = lo <= len(p["rows"]) <= hi
        rank = (p["ok_total"] and p["in_range"], p["in_range"], len(p["rows"]) if p["in_range"] else -len(p["rows"]))
        if best is None or rank > best[0]:
            best = (rank, p)
    return best[1] if best else None


def clean_name(n):
    """Quita las letras de nota de pie (a,b,c) del final."""
    return re.sub(r"(\s+[a-z](,[a-z])*)+$", "", n).strip()


# --------------------------------------------------------------------------------------------- NPORT-P (XML)
def parse_nport(xml):
    out = []
    for inv in re.findall(r"<invstOrSec>(.*?)</invstOrSec>", xml, re.S):
        def g(tag):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", inv, re.S)
            return html.unescape(m.group(1)).strip() if m else ""
        isin = re.search(r'<isin value="(.*?)"', inv)
        tick = re.search(r'<ticker value="(.*?)"', inv)
        out.append({"name": g("name"), "title": g("title"), "cusip": g("cusip"), "lei": g("lei"),
                    "isin": isin.group(1) if isin else "", "ticker": tick.group(1) if tick else "",
                    "shares": float(g("balance") or 0), "value": float(g("valUSD") or 0),
                    "asset_cat": g("assetCat"), "issuer_cat": g("issuerCat")})
    per = re.search(r"<repPdDate>(.*?)</repPdDate>", xml)
    return (per.group(1) if per else None), out


def load_index():
    return json.load(open(ETF / "filings_index.json"))


# ------------------------------------------------------------------------------------- cartera por fondo y fecha
PARSED = ETF / "parsed"
PARSED.mkdir(exist_ok=True)


def inventory():
    import pandas as pd
    inv = pd.read_csv(ETF / "inventory.csv", dtype=str, keep_default_na=False)
    return inv[~inv.type.str.endswith("/A") & (inv.period != "")]


def holdings(fund, period, inv=None):
    """Posiciones de acciones (nombre, acciones, valor; CUSIP/ISIN si es NPORT) del fondo en esa fecha de cartera.
    Si hay varias presentaciones con la misma fecha, prefiere NPORT-P (trae identificadores)."""
    f = PARSED / f"{fund}_{period}.json"
    if f.exists():
        return json.load(open(f))
    inv = inventory() if inv is None else inv
    c = inv[(inv.fund == fund) & (inv.period == period)]
    if c.empty:
        return None
    c = c.assign(p=c.type.eq("NPORT-P")).sort_values("p", ascending=False)
    r = c.iloc[0]
    if r.type == "NPORT-P":
        t = cached(r.doc_url, f"{fund}_{r.acc}.xml")
        _, inv_ = parse_nport(t)
        rows = [{"name": x["name"], "title": x["title"], "shares": x["shares"], "value": x["value"],
                 "cusip": x["cusip"], "isin": x["isin"]} for x in inv_ if x["asset_cat"] == "EC"]
        res = {"fund": fund, "period": period, "type": "NPORT-P", "rows": rows, "check": None}
    else:
        t = cached(r.doc_url, f"{fund}_{r.acc}.htm")
        p = parse_html_holdings(t, fund)
        if p is None:
            return None
        rows = [{"name": clean_name(x["name"]), "shares": x["shares"], "value": x["value"]} for x in p["rows"]]
        chk = None if p["reported_total"] is None else abs(p["parsed_total"] - p["reported_total"]) < 2
        res = {"fund": fund, "period": period, "type": r.type, "rows": rows, "check": chk}
    json.dump(res, open(f, "w"))
    return res
