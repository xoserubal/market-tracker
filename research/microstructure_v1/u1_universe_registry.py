"""U1 — registro del universo con cuatro capas separadas (autorización del usuario, 2026-11-21).

1. Identidad del emisor (issuers): clave = CIK de la SEC (S&P 500) o ISIN (Nasdaq 100, que no publica CIK); nombres
   y nombres anteriores con fechas, de la SEC (submissions).
2. Instrumento y ticker (instruments): tramos (emisor, ticker, desde, hasta). Un cambio de ticker del mismo emisor
   (EQR -> VMRK) es un tramo nuevo del mismo emisor, no un emisor nuevo.
3. Pertenencia a cada fecha (membership): intervalos por índice y emisor, con el ticker vigente en cada tramo y el
   método con el que se fechó cada entrada y salida.
4. Disponibilidad en Alpaca (provider_availability): estado del activo, bolsa, última barra diaria; lo que Alpaca no
   cubre queda como «no cubierto por el proveedor», nunca como un día sin negociación.

Fuentes, guardadas tal cual en reference/universe_sources/ con su revisión y hash:
- Wikipedia: todas las revisiones de «List of S&P 500 companies» desde la instantánea de 2026-01-14 que usó G1
  (revid 1332941675) y de «List of NASDAQ-100 companies» desde 2025-12-01.
- SEC: submissions de los CIK con algún cambio (User-Agent con el correo autorizado para la SEC).
- Alpaca: /v2/assets de cada símbolo y la serie diaria de 2026 de los tickers que cambian.

NO modifica reference/universe_intervals.parquet (G1, congelado: lo usan los planes de G2A). Antes de 2026-01-14 la
pertenencia sigue siendo la de G1; este registro corrige y precisa lo posterior.

Uso:
  py -3 u1_universe_registry.py fetch     # descarga y guarda las fuentes (idempotente: no repite revisiones guardadas)
  py -3 u1_universe_registry.py build     # construye las cuatro tablas y el informe de conciliación
"""
import argparse
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, event_universe, runtime, storage, universe  # noqa: E402
from micro.providers.alpaca import DATA_BASE, TRADING_BASE  # noqa: E402
from micro.providers.base import FetchStats, ProviderError  # noqa: E402

SRC = storage.root() / "reference" / "universe_sources"
REG = storage.root() / "reference" / "universe_registry"
OUT = storage.root() / "results" / "universe_registry"
WIKI_UA = {"User-Agent": "microstructure-research-universe/1.0 (personal research)"}
SEC_UA = {"User-Agent": "market-tracker research ir@xoserubal.com"}
PAGES = {"sp500": ("List of S&P 500 companies", 1332941675, "2026-01-14T19:21:08Z"),
         "ndx": ("List of NASDAQ-100 companies", None, "2025-12-01T00:00:00Z")}
FLICKER_DAYS = 3          # una ausencia o presencia de menos de 3 días entre ediciones se trata como error de edición


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ── 1. descarga ────────────────────────────────────────────────────────────────────────────────────────────────
def wiki_revisions(title: str, start_ts: str) -> list:
    revs, cont = [], {}
    while True:
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=WIKI_UA, timeout=60, params={
            "action": "query", "prop": "revisions", "titles": title, "rvprop": "ids|timestamp|comment|size",
            "rvlimit": 500, "rvstart": start_ts, "rvdir": "newer", "format": "json", "formatversion": 2, **cont}).json()
        revs += r["query"]["pages"][0].get("revisions", [])
        if "continue" not in r:
            return revs
        cont = r["continue"]


def fetch_wiki(index: str):
    title, first_revid, start_ts = PAGES[index]
    d = SRC / "wikipedia" / index
    d.mkdir(parents=True, exist_ok=True)
    revs = wiki_revisions(title, start_ts)
    if first_revid and not any(r["revid"] == first_revid for r in revs):
        raise SystemExit(f"{index}: no aparece la revisión inicial {first_revid}")
    new = 0
    for r in revs:
        p = d / f"{r['revid']}.html"
        if p.exists():
            continue
        j = None
        for attempt in range(6):
            resp = requests.get("https://en.wikipedia.org/w/api.php", headers=WIKI_UA, timeout=60, params={
                "action": "parse", "oldid": r["revid"], "prop": "text", "format": "json", "formatversion": 2})
            if resp.status_code == 200 and resp.text.lstrip().startswith("{"):
                j = resp.json()
                break
            time.sleep(5 * 2 ** attempt)
        if j is None or "parse" not in j:
            r["fetch_error"] = (j or {}).get("error", {}).get("info") if j else f"http {resp.status_code}"
            continue
        html = j["parse"]["text"].encode("utf-8")
        p.write_bytes(html)
        r["sha256"] = _sha(html)
        new += 1
        time.sleep(0.25)
    for r in revs:
        p = d / f"{r['revid']}.html"
        if p.exists():
            r["sha256"] = _sha(p.read_bytes())
    (d / "revisions.json").write_text(json.dumps({"title": title, "fetched_utc": _now(), "revisions": revs},
                                                 indent=1, ensure_ascii=False), encoding="utf-8")
    return {"index": index, "revisions": len(revs), "downloaded_now": new}


def fetch_sec(ciks: list) -> dict:
    d = SRC / "sec"
    d.mkdir(parents=True, exist_ok=True)
    out = {}
    for c in sorted({str(int(c)) for c in ciks if str(c).strip().isdigit()}):
        p = d / f"CIK{int(c):010d}.json"
        if not p.exists():
            r = requests.get(f"https://data.sec.gov/submissions/CIK{int(c):010d}.json", headers=SEC_UA, timeout=60)
            if r.status_code != 200:
                out[c] = f"http {r.status_code}"
                continue
            p.write_bytes(r.content)
            time.sleep(0.15)
        out[c] = "ok"
    return out


def fetch_alpaca_assets(symbols: list) -> dict:
    prov = runtime.alpaca()
    res = {}
    for s in sorted(set(symbols)):
        try:
            a = prov._get(f"{TRADING_BASE}/v2/assets/{s}", {}, FetchStats())
            res[s] = {k: a.get(k) for k in ("id", "status", "exchange", "class", "tradable", "name", "attributes")}
        except ProviderError as e:
            res[s] = {"error": str(e)[:200], "http": e.status}
    p = SRC / "alpaca" / f"assets_{datetime.now(timezone.utc).date()}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"fetched_utc": _now(), "assets": res}, indent=1, ensure_ascii=False), encoding="utf-8")
    return res


def fetch_alpaca_history(symbols: list, start: str, end: str) -> dict:
    """Barras diarias SIN asof (cada ticker con el historial que Alpaca le asigna hoy) y CON asof en el primer día:
    la diferencia muestra dónde termina un ticker antiguo y si Alpaca le ha reasignado el pasado a otro."""
    prov = runtime.alpaca()
    res = {}
    for s in sorted(set(symbols)):
        row = {}
        for tag, asof in (("no_asof", None), ("asof_start", start)):
            prm = {"timeframe": "1Day", "start": start, "end": end, "feed": "sip", "adjustment": "raw", "limit": 10000}
            if asof:
                prm["asof"] = asof
            try:
                bars = prov._get(f"{DATA_BASE}/v2/stocks/{s}/bars", prm, FetchStats()).get("bars") or []
                row[tag] = {"n": len(bars), "first": bars[0]["t"][:10] if bars else None,
                            "last": bars[-1]["t"][:10] if bars else None,
                            "closes": {b["t"][:10]: b["c"] for b in bars}}
            except ProviderError as e:
                row[tag] = {"error": str(e)[:200]}
        res[s] = row
    p = SRC / "alpaca" / f"daily_history_{start}_{end}.json"
    p.write_text(json.dumps({"fetched_utc": _now(), "history": res}, ensure_ascii=False), encoding="utf-8")
    return res


def fetch_alpaca_recent(symbols: list, start: str, end: str) -> dict:
    """Última barra diaria reciente de cada símbolo (petición múltiple, sin asof)."""
    prov = runtime.alpaca()
    last = {}
    syms = sorted(set(symbols))
    for i in range(0, len(syms), 100):
        part = syms[i:i + 100]
        tok = None
        while True:
            prm = {"symbols": ",".join(part), "timeframe": "1Day", "start": start, "end": end, "feed": "sip",
                   "adjustment": "raw", "limit": 10000}
            if tok:
                prm["page_token"] = tok
            j = prov._get(f"{DATA_BASE}/v2/stocks/bars", prm, FetchStats())
            for s, bars in (j.get("bars") or {}).items():
                if bars:
                    last[s] = max(last.get(s, ""), bars[-1]["t"][:10])
            tok = j.get("next_page_token")
            if not tok:
                break
    res = {s: {"last": last.get(s)} for s in syms}
    p = SRC / "alpaca" / f"recent_{end}.json"
    p.write_text(json.dumps({"fetched_utc": _now(), "start": start, "end": end, "last_bar": res}, ensure_ascii=False),
                 encoding="utf-8")
    return res


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── 2. lectura de revisiones ───────────────────────────────────────────────────────────────────────────────────
def norm_cik(c) -> str:
    c = str(c).strip()
    if re.fullmatch(r"\d+\.0+", c):          # una revisión guarda el CIK como número decimal (1000228.0)
        c = c.split(".")[0]
    s = re.sub(r"\D", "", c).lstrip("0")
    return s


def read_rev(index: str, revid: int) -> pd.DataFrame:
    html = (SRC / "wikipedia" / index / f"{revid}.html").read_text(encoding="utf-8")
    tabs = pd.read_html(io.StringIO(html))
    if index == "sp500":
        t = next(t for t in tabs if any("ymbol" in str(c) for c in t.columns) and any("CIK" in str(c) for c in t.columns))
        sym = next(c for c in t.columns if "ymbol" in str(c))
        add = next((c for c in t.columns if "added" in str(c).lower()), None)
        df = pd.DataFrame({"ticker": t[sym].astype(str).str.strip().str.replace("\xa0", " "),
                           "key": t[next(c for c in t.columns if "CIK" in str(c))].map(norm_cik),
                           "name": t["Security"].astype(str),
                           "added": pd.to_datetime(t[add], errors="coerce") if add is not None else pd.NaT})
    else:
        t = next(t for t in tabs if any("icker" in str(c) for c in t.columns))
        tk = next(c for c in t.columns if "icker" in str(c))
        isin = next((c for c in t.columns if "ISIN" in str(c)), None)
        # la columna ISIN solo aparece en la última revisión (2026-10-24): la clave es el ticker y el ISIN un dato
        df = pd.DataFrame({"ticker": t[tk].astype(str).str.strip(), "key": "",
                           "isin": t[isin].astype(str).str.strip() if isin is not None else None,
                           "name": t["Company"].astype(str) if "Company" in t else "", "added": pd.NaT})
    # clave de instrumento = emisor|ticker: un emisor con varias clases (GOOGL/GOOG, FOXA/FOX) aparece varias veces
    df["issuer"] = [k if k else f"T:{tk}" for k, tk in zip(df["key"], df["ticker"])]
    df["key"] = df["issuer"] + "|" + df["ticker"]
    return df.drop_duplicates("ticker")


COMMENT_DATE = re.compile(r"effective\s+(?:prior to (?:the )?open(?:ing)? (?:of trading )?on\s+)?"
                          r"(\d{1,2}[- ][A-Za-z]{3,9}[- ]\d{4}|[A-Za-z]{3,9}\.? \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2})", re.I)


def comment_date(c: str):
    m = COMMENT_DATE.search(c or "")
    if not m:
        return None
    d = pd.to_datetime(m.group(1).replace(".", ""), errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


# ── 3. construcción ────────────────────────────────────────────────────────────────────────────────────────────
def presence(index: str) -> tuple:
    meta = json.loads((SRC / "wikipedia" / index / "revisions.json").read_text(encoding="utf-8"))
    revs = meta["revisions"]
    snaps = []
    for r in revs:
        try:
            df = read_rev(index, r["revid"])
        except (StopIteration, ValueError, FileNotFoundError) as e:
            snaps.append((r, None, str(e)))
            continue
        snaps.append((r, df, None))
    return revs, snaps


def events_from_revisions(index: str) -> tuple:
    """Cambios de pertenencia y de ticker entre revisiones, sin parpadeos de edición."""
    revs, snaps = presence(index)
    good = [(r, df) for r, df, err in snaps if df is not None]
    bad = [{"revid": r["revid"], "ts": r["timestamp"], "error": err} for r, df, err in snaps if df is not None and False] + \
          [{"revid": r["revid"], "ts": r["timestamp"], "error": err} for r, df, err in snaps if df is None]
    ts = [pd.Timestamp(r["timestamp"]).tz_convert(None) for r, _ in good]
    keys = sorted(set().union(*[set(df.key) for _, df in good]))
    pres = {k: [k in set(df.key) for _, df in good] for k in keys}
    flick = []
    # parpadeos: rachas cortas (en tiempo) de ausencia o presencia entre dos estados iguales
    for k, v in pres.items():
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[j + 1] == v[i]:
                j += 1
            if 0 < i and j + 1 < len(v) and v[i - 1] == v[j + 1] != v[i]:
                span = (ts[j + 1] - ts[i]).total_seconds() / 86400
                if span < FLICKER_DAYS:
                    flick.append({"key": k, "state": "absent" if not v[i] else "present", "from_revid": good[i][0]["revid"],
                                  "to_revid": good[j][0]["revid"], "days": round(span, 2)})
                    for x in range(i, j + 1):
                        v[x] = v[i - 1]
            i = j + 1
    ev = []
    anyrow = {}
    for _, df in good:
        for r in df.itertuples():
            anyrow[r.key] = pd.Series(r._asdict())
    for n in range(1, len(good)):
        (r0, d0), (r1, d1) = good[n - 1], good[n]
        add = [k for k in keys if pres[k][n] and not pres[k][n - 1]]
        rem = [k for k in keys if pres[k][n - 1] and not pres[k][n]]
        a0 = d0.set_index("key")
        a1 = d1.set_index("key")
        def row_of(k):
            if k in a1.index:
                return a1.loc[k]
            if k in a0.index:
                return a0.loc[k]
            return anyrow.get(k)
        # cambio de ticker: el mismo emisor sale con un ticker y entra con otro en la misma revisión
        iss = lambda k: k.split("|")[0]  # noqa: E731
        renames = []
        for k in list(rem):
            cand = [a for a in add if iss(a) == iss(k) and not iss(k).startswith("T:")]
            if len(cand) == 1:
                renames.append((k, cand[0]))
                rem.remove(k)
                add.remove(cand[0])
        tk = lambda k: k.split("|", 1)[1]  # noqa: E731
        corrections = []
        for k in list(rem):
            cand = [a for a in add if tk(a) == tk(k)]
            if len(cand) == 1:
                corrections.append((k, cand[0]))
                rem.remove(k)
                add.remove(cand[0])
        for k_old, k_new in corrections:
            ev.append({"index": index, "type": "identity_correction", "key": k_old, "new_key": k_new, "issuer": iss(k_new),
                       "old_issuer": iss(k_old), "ticker": tk(k_new), "name": row_of(k_new)["name"],
                       "revid": r1["revid"], "rev_ts": r1["timestamp"], "prev_rev_ts": r0["timestamp"],
                       "comment": r1.get("comment")})
        adds = []
        for k in add:
            row = row_of(k)
            adds.append({"key": k, "issuer": iss(k), "ticker": None if row is None else row["ticker"],
                         "name": None if row is None else row["name"],
                         "added_col": None if row is None or pd.isna(row["added"]) else row["added"].strftime("%Y-%m-%d")})
        for a in adds:
            ev.append({"index": index, "type": "join", "revid": r1["revid"], "rev_ts": r1["timestamp"],
                       "prev_rev_ts": r0["timestamp"], "comment": r1.get("comment"), **a})
        for k in rem:
            row = row_of(k)
            ev.append({"index": index, "type": "leave", "key": k, "issuer": iss(k),
                       "ticker": None if row is None else row["ticker"],
                       "name": None if row is None else row["name"], "revid": r1["revid"], "rev_ts": r1["timestamp"],
                       "prev_rev_ts": r0["timestamp"], "comment": r1.get("comment"),
                       "paired_added": sorted({a["added_col"] for a in adds if a["added_col"]})})
        for k_old, k_new in renames:
            ev.append({"index": index, "type": "rename", "key": k_old, "new_key": k_new, "issuer": iss(k_old),
                       "old_ticker": row_of(k_old)["ticker"], "ticker": row_of(k_new)["ticker"],
                       "name": row_of(k_new)["name"], "revid": r1["revid"], "rev_ts": r1["timestamp"],
                       "prev_rev_ts": r0["timestamp"], "comment": r1.get("comment")})
    first = good[0][1].assign(index=index, known_from=good[0][0]["timestamp"], revid=good[0][0]["revid"])
    last = good[-1][1].assign(index=index, revid=good[-1][0]["revid"], rev_ts=good[-1][0]["timestamp"])
    return ev, first, last, flick, bad, revs


def trading_days(a: str, b: str) -> list:
    return calendar.trading_days(a, b)


def date_events(ev: list, hist: dict) -> list:
    """Fecha efectiva de cada cambio y método. Una entrada es efectiva el día de «Date added» (antes de la apertura);
    la salida emparejada deja de ser miembro el día anterior. Un cambio de ticker se fecha con Alpaca: primer día con
    barra del ticker nuevo que falta en la serie del antiguo."""
    cal = trading_days("2025-01-01", "2027-12-31")

    def prev_td(d):
        xs = [x for x in cal if x < d]
        return xs[-1] if xs else d

    def next_td(d):
        xs = [x for x in cal if x >= d]
        return xs[0] if xs else d
    for e in ev:
        lo = (pd.Timestamp(e["prev_rev_ts"]).tz_convert(None) - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
        hi = (pd.Timestamp(e["rev_ts"]).tz_convert(None) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        edit = pd.Timestamp(e["rev_ts"]).tz_convert("America/New_York").strftime("%Y-%m-%d")
        cd = comment_date(e.get("comment"))
        if e["type"] == "join":
            if e.get("added_col") and lo <= e["added_col"] <= hi:
                e["effective"], e["method"] = next_td(e["added_col"]), "date_added_column"
            elif cd:
                e["effective"], e["method"] = next_td(cd), "edit_comment"
            else:
                e["effective"], e["method"] = next_td(edit), "edit_timestamp_approx"
        elif e["type"] == "leave":
            hl = ((hist.get(universe.to_alpaca(e["ticker"] or "")) or {}).get("no_asof") or {})
            e["alpaca_last_bar"] = hl.get("last")
            pa = [d for d in e.get("paired_added") or [] if lo <= d <= hi]
            if pa:
                e["last_member_day"], e["method"] = prev_td(next_td(max(pa))), "paired_addition"
            elif cd:
                e["last_member_day"], e["method"] = prev_td(next_td(cd)), "edit_comment"
            else:
                e["last_member_day"], e["method"] = prev_td(next_td(edit)), "edit_timestamp_approx"
        else:
            if e["type"] == "identity_correction":
                e["effective"], e["method"] = next_td(edit), "edit_timestamp_approx"
                continue
            o = universe.to_alpaca(e["old_ticker"])
            n = universe.to_alpaca(e["ticker"])
            ho = (hist.get(o) or {}).get("no_asof") or {}
            hn = (hist.get(n) or {}).get("no_asof") or {}
            na = (hist.get(n) or {}).get("asof_start") or {}
            oa = (hist.get(o) or {}).get("asof_start") or {}
            # con asof al inicio del periodo, el ticker nuevo solo devuelve barras desde que existe con ese nombre
            if na.get("first") and na["first"] > "2026-01-02":
                e["effective"], e["method"] = na["first"], "alpaca_new_ticker_first_bar"
                same = ho.get("closes", {}).get(prev_td(na["first"])) == hn.get("closes", {}).get(prev_td(na["first"]))
                e["price_continuity"] = bool(same) if ho.get("closes") and hn.get("closes") else None
                # ¿el ticker antiguo vuelve a cotizar como otro instrumento? (Alpaca le asigna otro historial)
                if ho.get("first") and ho["first"] >= na["first"]:
                    e["old_ticker_reused_from"] = ho["first"]
                continue
            if ho.get("last") and hn.get("closes"):
                after = sorted(d for d in hn["closes"] if d > ho["last"])
                if after:
                    e["effective"], e["method"] = after[0], "alpaca_symbol_history"
                    same = ho["closes"].get(ho["last"]) == hn["closes"].get(ho["last"])
                    e["price_continuity"] = bool(same)
                    continue
            e["effective"], e["method"] = (next_td(cd), "edit_comment") if cd else (next_td(edit), "edit_timestamp_approx")
    return ev


def build_membership(index: str, ev: list, first: pd.DataFrame, last: pd.DataFrame, end_day: str) -> pd.DataFrame:
    """Intervalos por emisor (key) con el ticker vigente: [start, end]; end abierto = end_day (último día hábil)."""
    known_from = pd.Timestamp(first["known_from"].iloc[0]).tz_convert("America/New_York").strftime("%Y-%m-%d")
    state = {r.key: {"issuer": r.issuer, "ticker": r.ticker, "name": r.name, "start": known_from,
                     "start_method": "first_revision"} for r in first.itertuples()}
    rows = []
    for e in sorted(ev, key=lambda x: (x.get("effective") or x.get("last_member_day"), x["type"] != "leave")):
        k = e["key"]
        if e["type"] == "leave" and k in state:
            s = state.pop(k)
            rows.append({**s, "key": k, "end": e["last_member_day"], "end_method": e["method"], "end_revid": e["revid"]})
        elif e["type"] == "join":
            if k in state:
                continue
            state[k] = {"issuer": e["issuer"], "ticker": e["ticker"], "name": e["name"], "start": e["effective"],
                        "start_method": e["method"], "start_revid": e["revid"]}
        elif e["type"] == "identity_correction" and k in state:
            s = state.pop(k)
            state[e["new_key"]] = {**s, "issuer": e["issuer"], "identity_corrected_from": e["old_issuer"]}
        elif e["type"] == "rename" and k in state:
            s = state.pop(k)
            day = e["effective"]
            prev = [d for d in trading_days("2025-01-01", day) if d < day]
            rows.append({**s, "key": k, "end": prev[-1], "end_method": "ticker_change", "end_revid": e["revid"]})
            state[e["new_key"]] = {"issuer": e["issuer"], "ticker": e["ticker"], "name": e["name"], "start": day,
                                   "start_method": f"ticker_change:{e['method']}", "start_revid": e["revid"],
                                   "predecessor_ticker": e["old_ticker"]}
    for k, s in state.items():
        rows.append({**s, "key": k, "end": end_day, "end_method": "open", "end_revid": None})
    df = pd.DataFrame(rows)
    df["index"] = index
    df["symbol"] = df["ticker"].map(universe.to_alpaca)
    df["known_from"] = known_from
    return df.sort_values(["issuer", "start"]).reset_index(drop=True)


def sec_issuer(cik: str) -> dict:
    p = SRC / "sec" / f"CIK{int(cik):010d}.json"
    if not p.exists():
        return {}
    j = json.loads(p.read_text(encoding="utf-8"))
    return {"cik": cik, "sec_name": j.get("name"), "sec_tickers": j.get("tickers"), "sec_exchanges": j.get("exchanges"),
            "former_names": [{"name": f.get("name"), "from": (f.get("from") or "")[:10], "to": (f.get("to") or "")[:10]}
                             for f in j.get("formerNames") or []]}


def availability(symbols: list, assets: dict, hist_recent: dict, today: str) -> pd.DataFrame:
    rows = []
    for s in sorted(set(symbols)):
        a = assets.get(s) or {}
        h = (hist_recent.get(s) or {}).get("no_asof") or {}
        if "error" in a:
            status = "provider_not_found"
        elif a.get("exchange") == "OTC":
            status = "provider_otc_not_covered"
        elif a.get("status") == "active":
            status = "covered"
        else:
            status = "provider_inactive"
        rows.append({"symbol": s, "status": status, "asset_status": a.get("status"), "exchange": a.get("exchange"),
                     "asset_class": a.get("class"), "tradable": a.get("tradable"), "asset_name": a.get("name"),
                     "asset_id": a.get("id"), "last_daily_bar": h.get("last"), "checked_utc": today,
                     "http_error": a.get("error")})
    return pd.DataFrame(rows)


def build():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cal_days = trading_days("2026-01-01", today)
    end_day = [d for d in cal_days if d <= today][-1]
    hist = json.loads(sorted((SRC / "alpaca").glob("daily_history_2026-01-02_*.json"))[-1].read_text(encoding="utf-8"))["history"]
    assets = json.loads(sorted((SRC / "alpaca").glob("assets_*.json"))[-1].read_text(encoding="utf-8"))["assets"]
    recent = json.loads(sorted((SRC / "alpaca").glob("recent_*.json"))[-1].read_text(encoding="utf-8"))["last_bar"]
    report = {"built_utc": _now(), "end_day": end_day, "indexes": {}}
    memb, all_ev, lasts = [], [], {}
    for index in PAGES:
        ev, first, last, flick, bad, revs = events_from_revisions(index)
        ev = date_events(ev, hist)
        m = build_membership(index, ev, first, last, end_day)
        memb.append(m)
        all_ev += ev
        lasts[index] = last
        report["indexes"][index] = {"revisions": len(revs), "unparsed": bad, "flickers": flick,
                                    "first_revision": revs[0]["revid"], "last_revision": revs[-1]["revid"],
                                    "last_revision_ts": revs[-1]["timestamp"],
                                    "events": pd.Series([e["type"] for e in ev]).value_counts().to_dict() if ev else {},
                                    "dating_methods": pd.Series([e.get("method") for e in ev]).value_counts().to_dict() if ev else {},
                                    "current_members": int((m["end"] == end_day).sum())}
    membership = pd.concat(memb, ignore_index=True)
    events = pd.DataFrame(all_ev)
    # instrumentos: tramos (emisor, ticker) de la pertenencia + estado del proveedor
    inst = membership.groupby(["issuer", "ticker", "symbol"], as_index=False).agg(valid_from=("start", "min"),
                                                                             valid_to=("end", "max"))
    # emisores
    iss = []
    for k in sorted(membership["issuer"].unique()):
        mm = membership[membership["issuer"] == k].sort_values("start")
        rec = {"issuer_key": k, "key_type": "cik" if k.isdigit() else ("isin" if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", k) else "ticker"),
               "names_in_sources": sorted(set(mm["name"].dropna().astype(str))), "tickers": list(dict.fromkeys(mm["ticker"]))}
        if rec["key_type"] == "cik":
            rec.update(sec_issuer(k))
        iss.append(rec)
    issuers = pd.DataFrame(iss)
    # sucesiones: cambios de ticker del mismo emisor (mismo instrumento económico) y bajas con su motivo aparente
    succ = []
    for e in all_ev:
        if e["type"] == "rename":
            succ.append({"kind": "ticker_change_same_issuer", "issuer_key": e["issuer"], "from_ticker": e["old_ticker"],
                         "to_ticker": e["ticker"], "effective": e["effective"], "method": e["method"],
                         "price_continuity": e.get("price_continuity"), "index": e["index"], "evidence_revid": e["revid"],
                         "old_ticker_reused_from": e.get("old_ticker_reused_from"),
                         "comment": e.get("comment")})
    successions = pd.DataFrame(succ).drop_duplicates(["issuer_key", "from_ticker", "to_ticker"]) if succ else pd.DataFrame()
    syms = set(membership["symbol"]) | set(events_symbols(all_ev)) | set(_project_symbols())
    avail = availability(sorted(syms), assets, {s: {"no_asof": v} for s, v in recent.items()}, today)
    REG.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, df in (("membership", membership), ("events", events), ("instruments", inst), ("issuers", issuers),
                     ("successions", successions), ("provider_availability", avail)):
        p = REG / f"{name}.parquet"
        df2 = df.copy()
        for c in df2.columns:
            if df2[c].map(lambda x: isinstance(x, (list, dict))).any():
                df2[c] = df2[c].map(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else x)
        files[name] = storage.write_parquet_atomic(df2, p)[0]
    report["files_sha256"] = files
    report["sources"] = {"wikipedia": {i: json.loads((SRC / "wikipedia" / i / "revisions.json").read_text(encoding="utf-8"))
                                       ["fetched_utc"] for i in PAGES},
                         "alpaca_assets": sorted(p.name for p in (SRC / "alpaca").glob("assets_*.json"))[-1],
                         "sec_files": len(list((SRC / "sec").glob("*.json")))}
    report["reconcile"] = reconcile(membership, avail, successions, end_day)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"reconcile_{today}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str),
                                                 encoding="utf-8")
    (REG / "manifest.json").write_text(json.dumps({k: report[k] for k in ("built_utc", "end_day", "files_sha256",
                                                                           "sources")}, indent=1), encoding="utf-8")
    return report


def events_symbols(ev):
    for e in ev:
        for k in ("ticker", "old_ticker"):
            if e.get(k):
                yield universe.to_alpaca(e[k])


def _project_symbols():
    return [universe.to_alpaca(t) for t in universe.project_us_tickers()] + event_universe.market_tracker_us()


def reconcile(membership, avail, successions, end_day) -> dict:
    """Universo actual antiguo frente al registro: qué cambia y por qué."""
    old = event_universe.current_universe(use_registry=False)
    cur = membership[membership["end"] == end_day]
    av = avail.set_index("symbol")
    res = {"sp500_current_registry": int((cur["index"] == "sp500").sum()), "ndx_current_registry": int((cur["index"] == "ndx").sum())}
    reg_sp, reg_nd = set(cur[cur["index"] == "sp500"]["symbol"]), set(cur[cur["index"] == "ndx"]["symbol"])
    old_sp = {s for s, src in old["symbols"].items() if "sp500" in src}
    old_nd = {s for s, src in old["symbols"].items() if "ndx" in src}
    res["sp500_added_vs_old"] = sorted(reg_sp - old_sp)
    res["sp500_removed_vs_old"] = sorted(old_sp - reg_sp)
    res["ndx_added_vs_old"] = sorted(reg_nd - old_nd)
    res["ndx_removed_vs_old"] = sorted(old_nd - reg_nd)
    succ_from = {universe.to_alpaca(r.from_ticker): r for r in successions.itertuples()} if len(successions) else {}
    res["old_universe_symbols_not_covered"] = []
    for s in sorted(old["symbols"]):
        st = av.loc[s, "status"] if s in av.index else "not_checked"
        if st != "covered":
            r = succ_from.get(s)
            res["old_universe_symbols_not_covered"].append(
                {"symbol": s, "sources": old["symbols"][s], "provider_status": st,
                 "successor": None if r is None else {"ticker": universe.to_alpaca(r.to_ticker), "effective": r.effective,
                                                      "method": r.method, "issuer_key": r.issuer_key}})
    return res


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("fetch")
    sp.add_parser("build")
    a = ap.parse_args()
    if a.cmd == "fetch":
        out = [fetch_wiki(i) for i in PAGES]
        print(json.dumps(out))
        ev_syms, ciks = set(), set()
        for i in PAGES:
            ev, first, last, *_ = events_from_revisions(i)
            for e in ev:
                ev_syms |= {universe.to_alpaca(x) for x in (e.get("ticker"), e.get("old_ticker")) if x}
                if str(e.get("issuer", "")).isdigit():
                    ciks.add(e["issuer"])
            ev_syms |= set(first["ticker"].map(universe.to_alpaca)) | set(last["ticker"].map(universe.to_alpaca))
        print("sec", json.dumps(fetch_sec(sorted(ciks))))
        changed = set()
        for i in PAGES:
            for e in events_from_revisions(i)[0]:
                changed |= {universe.to_alpaca(x) for x in (e.get("ticker"), e.get("old_ticker")) if x}
        syms = sorted(ev_syms | set(_project_symbols()) | set(event_universe.CONTEXT))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ap = SRC / "alpaca" / f"assets_{today}.json"
        if ap.exists() and set(json.loads(ap.read_text(encoding="utf-8"))["assets"]) >= set(syms):
            assets = json.loads(ap.read_text(encoding="utf-8"))["assets"]
        else:
            assets = fetch_alpaca_assets(syms)
        print("assets", len(assets), sum("error" in v for v in assets.values()), "no encontrados")
        # el plan de datos no permite los últimos 15 min de SIP: se pide hasta el día anterior
        today = (pd.Timestamp(datetime.now(timezone.utc)) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        h = fetch_alpaca_history(sorted(changed), "2026-01-02", today)
        print("history (tickers con cambios)", len(h))
        r = fetch_alpaca_recent(syms, (pd.Timestamp(today) - pd.Timedelta(days=12)).strftime("%Y-%m-%d"), today)
        print("recent", sum(1 for v in r.values() if v["last"]), "de", len(r), "con barra reciente")
    else:
        r = build()
        for i, x in r["indexes"].items():
            print(i, {k: (len(v) if isinstance(v, list) else v) for k, v in x.items()})
        print(json.dumps(r["reconcile"], ensure_ascii=False, default=str)[:5000])


if __name__ == "__main__":
    main()
