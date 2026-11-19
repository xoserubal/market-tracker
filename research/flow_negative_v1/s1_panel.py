"""Etapa 0 (v3) — panel por EMPRESA y día. NO usa ningún rendimiento posterior a una señal.

Cambio de enfoque (encargo 2026-11-18): la unidad es la empresa, no la pertenencia a un índice. Los índices solo
sirven para identificar empresas y fechar su entrada en el marco muestral.

1. Series: todas las de work/series_summary.csv con datos, sustituyendo las cortadas a los 75 días de la baja del
   índice por su versión prolongada (s1_extend.py).
2. Duplicados: dos series con los MISMOS precios y volúmenes en las fechas que comparten (>= 20 días, >= 95 % de
   coincidencia exacta) son la misma empresa (p. ej. HCN con asof y WELL sin asof). Candidatas: mismo CIK o algún
   símbolo en común. Las épocas de una misma petición (ticker reutilizado, empresa que reaparece tras quiebra) nunca
   se fusionan. Series del mismo CIK que se suceden sin solaparse (<= 10 días de hueco) se enlazan como la misma
   empresa (cambio de ticker). Cada día de una empresa sale de una sola serie: la que tiene el Flow completo y, a
   igualdad, la que empieza antes.
3. Marco muestral en cada fecha (sin información futura): la empresa entra el primer día en que perteneció a
   cualquiera de los tres índices (dentro de su época) y sigue en el marco después de salir de él, hasta que deja de
   cotizar. La historia anterior a esa entrada NO entra: elegir una empresa porque más tarde entró en un índice
   sería seleccionar por su éxito posterior.
4. Capitalización a fecha t, solo con presentaciones de la SEC publicadas <= t (mcap_pit; filtro de errores que en
   cada presentación solo mira las anteriores). La versión con el filtro centrado de la etapa 0 queda como
   corrección retrospectiva (mcap_retro), solo para sensibilidad.
5. Liquidez (mediana de precio x volumen de 20 sesiones, incluida t), rotación (liquidez / capitalización), spread
   estimado de Abdi-Ranaldo con las 21 sesiones anteriores (solo para comprobar los costes supuestos).
6. Eventos: se excluye la señal solo si un evento en [t-259, t] impide calcular bien el Flow en t. Los eventos
   posteriores (t, t+40] NO excluyen: se marcan para tratarlos en el resultado.

Salidas: work/panel_v3.parquet, work/companies_v3.csv (fuera del repo); data/v3_*.json (agregados, en el repo).
"""
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

import fn_config as C
from s0_coverage import calendar

SER = C.WORK / "series"
TAG = os.environ.get("FN_TAG", "v3")
V4 = TAG >= "v4"
# v4 (opción 2, aprobada 2026-11-19):
#  - S&P 600: solo cuenta para entrar en el marco desde el primer cambio oficial registrado (antes, la composición
#    era la de dic-2019 copiada hacia atrás: supervivientes);
#  - S&P 400 2015-2020: pertenencia observada en las carteras de IJH/IVOO (data/membership_etf_sp400.csv, por CIK);
#    la reconstrucción de Wikipedia solo desde 2021 (fiable);
#  - capitalización: la prueba de rotación plausible se aplica a todas las presentaciones, no solo a la primera.
SP600_FROM = "2019-12-17"
SP400_WIKI_FROM = "2021-01-01"
SIG_START = "2018-01-02"
LOOKBACK, HORIZON = 259, 40
SIZE_TIERS = [(0, 300e6, "micro"), (300e6, 2e9, "small"), (2e9, 10e9, "mid"), (10e9, 1e15, "large")]
LIQ_TIERS = [(0, 1e6, "<1M"), (1e6, 5e6, "1-5M"), (5e6, 25e6, "5-25M"), (25e6, 100e6, "25-100M"),
             (100e6, 1e15, ">=100M")]
TURN_MIN, TURN_MAX = 1e-5, 0.5      # rotación diaria plausible para validar una primera presentación sin historia
FLOW_EVENTS = ("E1_dividendo_grande", "E2_split_incoherente", "E1_escision_alpaca", "E1_escision_curada",
               "E3_hueco_serie")


def tier(x, tiers):
    if x != x:
        return "unknown"
    for lo, hi, n in tiers:
        if lo <= x < hi:
            return n
    return "unknown"


# ---------------------------------------------------------------------------------------------- series y CIK
def load_series_table():
    a = pd.read_csv(C.WORK / "series_summary.csv", dtype=str, keep_default_na=False)
    b = pd.read_csv(C.WORK / "series_summary_ext.csv", dtype=str, keep_default_na=False)
    a, b = a[a.status == "ok"], b[b.status == "ok"]
    replaced = {k[:-1] for k in b.req_key}
    a = a[~a.req_key.isin(replaced)]
    s = pd.concat([a.assign(ext=False), b.assign(ext=True)], ignore_index=True)
    s["orig_req"] = np.where(s.ext, s.req_key.str[:-1], s.req_key)
    cm = pd.read_csv(C.SEC / "cik_map.csv", dtype=str, keep_default_na=False)
    cik = dict(zip(cm.key, cm.cik))
    s["cik"] = s.orig_req.map(lambda k: cik.get(k, "") or "")
    return s.set_index("key")


class UF:
    def __init__(self, keys):
        self.p = {k: k for k in keys}

    def f(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def u(self, a, b):
        a, b = self.f(a), self.f(b)
        if a != b:
            self.p[max(a, b)] = min(a, b)


def companies(s, close_of):
    """Agrupa series en empresas. Devuelve dict serie→empresa y un registro de enlaces."""
    uf = UF(s.index)
    by = defaultdict(set)
    for k, r in s.iterrows():
        if r.cik:
            by[("cik", r.cik)].add(k)
        for sym in r.symbols.split("|"):
            by[("sym", sym)].add(k)
    pairs = set()
    for ks in by.values():
        ks = sorted(ks)
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                pairs.add((ks[i], ks[j]))
    log = []
    for a, b in sorted(pairs):
        ra, rb = s.loc[a], s.loc[b]
        if ra.req_key == rb.req_key:
            continue                              # épocas distintas de la misma petición: identidades distintas
        ca, cb = close_of(a), close_of(b)
        ov = ca.index.intersection(cb.index)
        if len(ov) >= 20:
            same = (np.abs(np.log(ca[ov].to_numpy() / cb[ov].to_numpy())) < 1e-6).mean()
            if same >= 0.95:
                uf.u(a, b)
                log.append((a, b, "duplicado", len(ov), round(float(same), 4)))
            elif ra.cik and ra.cik == rb.cik:
                # mismo CIK, mismas fechas, precios distintos: o dos clases de acciones de la misma empresa (se
                # mueven juntas durante toda su vida común) o un CIK mal asignado / dos entidades de una fusión
                ra_ = np.diff(np.log(ca[ov].to_numpy()))
                rb_ = np.diff(np.log(cb[ov].to_numpy()))
                corr = float(np.corrcoef(ra_, rb_)[0, 1]) if len(ra_) > 20 else 0.0
                cover = len(ov) / min(len(ca), len(cb))
                if corr >= 0.9 and cover >= 0.9:
                    uf.u(a, b)
                    log.append((a, b, "clases_mismo_cik", len(ov), round(corr, 3)))
                else:
                    log.append((a, b, "conflicto_cik", len(ov), round(corr, 3)))
            else:
                log.append((a, b, "solapan_sin_coincidir", len(ov), round(float(same), 4)))
            continue
        if ra.cik and ra.cik == rb.cik:
            first, second = (ra, rb) if ra.end <= rb.end else (rb, ra)
            gap = (pd.Timestamp(second.start) - pd.Timestamp(first.end)).days
            if 0 < gap <= 10:
                uf.u(a, b)
                log.append((a, b, "sucesion_cik", gap, None))
    return {k: uf.f(k) for k in s.index}, log


# ------------------------------------------------------------------------------------------- marco muestral
def clip_membership(mem):
    """v4: recorta los tramos de Wikipedia que no son fiables (ver cabecera)."""
    mem = mem.copy()
    cut = {"sp600": SP600_FROM, "sp400": SP400_WIKI_FROM}
    for ix, d in cut.items():
        sel = mem["index"] == ix
        mem.loc[sel, "start"] = mem.loc[sel, "start"].where(mem.loc[sel, "start"] >= d, d)
        drop = sel & (mem.end != "") & (mem.end < d)
        mem = mem[~drop]
    return mem


def frame_entry(s, mem, etf=None):
    """Primer día de pertenencia a algún índice dentro de la época de cada serie (None si nunca fue miembro).
    etf: tramos de pertenencia por CIK (S&P 400 2015-2020 observados en las carteras de los ETF)."""
    etf_by, etf_tk = defaultdict(list), defaultdict(list)
    if etf is not None:
        for r in etf.itertuples():
            if r.cik:
                etf_by[r.cik].append((r.start, r.end))
            elif getattr(r, "ticker", ""):
                etf_tk[r.ticker].append((r.start, r.end))
    mem = mem.copy()
    mem["end2"] = mem.end.replace("", C.PRICE_END)
    by_t = {t: g for t, g in mem.groupby("ticker")}
    entry, idx_iv = {}, {}
    for k, r in s.iterrows():
        ivs = []
        for sym in set(r.symbols.split("|")) | {r.ticker}:
            g = by_t.get(sym)
            if g is None:
                continue
            for m in g.itertuples():
                if m.start <= r.end and m.end2 >= r.start:
                    ivs.append((max(m.start, r.start), min(m.end2, r.end), m.index, m.sector_wiki))
        etf_ivs = []
        if r.cik and not r.get("cik_conflict", False):
            etf_ivs += etf_by.get(r.cik, [])
        for sym in set(r.symbols.split("|")) | {r.ticker}:
            etf_ivs += etf_tk.get(sym, [])
        for a, b in etf_ivs:
            if a <= r.end and b >= r.start:
                ivs.append((max(a, r.start), min(b, r.end), "sp400", ""))
        entry[k] = min((a for a, *_ in ivs), default=None)
        idx_iv[k] = ivs
    return entry, idx_iv


# -------------------------------------------------------------------------------------------- capitalización
def filings(cik):
    f = C.SEC / "shares" / f"{cik}.json"
    if not f.exists():
        return None
    s = pd.DataFrame(json.load(open(f)))
    if s.empty or "filed" not in s:
        return None
    if "form" in s:
        s = s[s.form.astype(str).str.match(r"^(10-K|10-Q|10-KT|10-QT|20-F|40-F)")]
    g = s.groupby(["end", "filed"]).agg(val=("val", "sum"), n=("val", "size")).reset_index()
    g = g[g.val > 0].sort_values(["filed", "end"]).reset_index(drop=True)
    return g if len(g) else None


def split_factor(splits, d_from, d_to):
    """Factor que lleva acciones con fecha de cierre d_from a la base de d_to (splits entre ambas)."""
    f = 1.0
    for bd, fac in splits:
        if d_from < bd <= d_to:
            f *= fac
    return f


def clean_pit(g, splits, turnover_at):
    """Filtro sin información futura: cada presentación se valida solo con las anteriores.
    - Con historia aceptada: se acepta si está a menos de x2 de la mediana de las 4 últimas aceptadas (llevadas a su
      base con los splits ocurridos hasta su fecha de cierre).
    - Si no, se acepta igualmente si coincide (x2) con la presentación inmediatamente anterior rechazada: dos
      presentaciones seguidas que coinciden confirman un cambio real (fusión, emisión, split no registrado).
    - Primera presentación: se valida con la rotación implícita en su fecha de publicación (si hay precio)."""
    ok = np.zeros(len(g), bool)
    acc = []
    prev_rej = None
    for i, r in enumerate(g.itertuples()):
        v = float(r.val)
        plaus = True
        if V4:
            t = turnover_at(r.filed, v * split_factor(splits, r.end, r.filed))
            plaus = t is None or TURN_MIN <= t <= TURN_MAX
        if acc:
            ref = np.median([a_v * split_factor(splits, a_e, r.end) for a_e, a_v in acc[-4:]])
            good = abs(np.log(v / ref)) <= np.log(2)
            if not good and prev_rej is not None:
                pe, pv = prev_rej
                good = abs(np.log(v / (pv * split_factor(splits, pe, r.end)))) <= np.log(2)
            good = good and plaus
        else:
            t = turnover_at(r.filed, v * split_factor(splits, r.end, r.filed))
            # v4: una primera presentación que no se puede comprobar (empresa que aún no cotiza: escisiones, nuevas
            # entidades de una fusión) no sirve de ancla; se espera a la primera comprobable
            good = (t is not None and TURN_MIN <= t <= TURN_MAX) if V4 else (t is None or TURN_MIN <= t <= TURN_MAX)
        ok[i] = good
        if good:
            acc.append((r.end, v))
            prev_rej = None
        elif acc or not V4:
            prev_rej = (r.end, v)
    return ok


def clean_retro(g, splits):
    base = g.val.to_numpy(float).copy()
    for bd, fac in splits:
        base *= np.where(g.end.to_numpy() < bd, fac, 1.0)
    med = pd.Series(base).rolling(5, center=True, min_periods=1).median().to_numpy()
    return np.abs(np.log(base / med)) <= np.log(2)


def mcap_series(g, ok, splits, dates, close):
    sh = g[ok].reset_index(drop=True)
    if sh.empty:
        return np.full(len(dates), np.nan), np.zeros(len(dates), bool)
    j = np.searchsorted(sh.filed.to_numpy(), dates, side="right") - 1
    valid = j >= 0
    jj = np.where(valid, j, 0)
    filed, endd = sh.filed.to_numpy()[jj], sh.end.to_numpy()[jj]
    age = (pd.to_datetime(dates) - pd.to_datetime(filed)).days.to_numpy()
    f = np.ones(len(dates))
    for bd, fac in splits:
        f *= np.where((endd < bd) & (dates >= bd), fac, 1.0)
    mc = sh.val.to_numpy(float)[jj] * f * close
    good = valid & (age <= 400)
    return np.where(good, mc, np.nan), np.where(good, sh.n.to_numpy()[jj] > 1, False)


# --------------------------------------------------------------------------------------------------- panel
def main():
    cal = calendar()
    cpos = {d: i for i, d in enumerate(cal)}
    s = load_series_table()
    mem = pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False)
    etf = None
    mem_full = None
    if V4:
        mem_full = mem.copy()
        mem = clip_membership(mem)
        etf = pd.read_csv(C.PUB / "membership_etf_sp400.csv", dtype=str, keep_default_na=False)

    cache = {}

    def load(k):
        if k not in cache:
            d = pd.read_parquet(SER / f"{k}.parquet")
            d["adv20"] = d.dollar_vol.rolling(20, min_periods=20).median()
            lh, ll, lc = np.log(d.high), np.log(d.low), np.log(d.close)
            eta = (lh + ll) / 2
            x = (lc.shift(1) - eta.shift(1)) * (lc.shift(1) - eta)
            d["spread_ar21"] = np.sqrt(np.clip(4 * x.rolling(21, min_periods=15).mean(), 0, None))
            cache[k] = d.set_index("date")
            if len(cache) > 300:
                cache.pop(next(iter(cache)))
        return cache[k]

    def close_of(k):
        return load(k).raw_close

    comp, links = companies(s, close_of)
    s["company"] = pd.Series(comp)
    # CIK en conflicto (dos empresas distintas con el mismo CIK): la capitalización de ambas no es fiable
    conflict = {k for a, b, t, *_ in links if t == "conflicto_cik" for k in (a, b)}
    s["cik_conflict"] = s.index.isin(conflict)
    sicf = C.PUB / "sic_sector_by_cik.csv"
    sic_sector = {}
    if sicf.exists():
        t = pd.read_csv(sicf, dtype=str, keep_default_na=False)
        sic_sector = dict(zip(t.cik, t.sector_sic))
    entry, idx_iv = frame_entry(s, mem, etf)
    s["frame_entry"] = pd.Series(entry)
    print("series", len(s), "empresas", s.company.nunique(),
          "series sin pertenencia en su época", int(s.frame_entry.isna().sum()), flush=True)

    rows = []
    shares_stats = defaultdict(int)
    for cid, g in s.groupby("company"):
        ent = g.frame_entry.dropna()
        if ent.empty:
            continue
        cstart = max(ent.min(), SIG_START)
        # sector: último sector de Wikipedia de la empresa
        ivs = [iv for k in g.index for iv in idx_iv[k]]
        sectors = [iv[3] for iv in sorted(ivs, key=lambda z: z[1]) if iv[3]]
        sector = sectors[-1] if sectors else ""
        if not sector and mem_full is not None:
            # el sector es un dato fijo de la empresa: se busca también en la pertenencia sin recortar (v4)
            syms = {x for k in g.index for x in s.loc[k].symbols.split("|")} | set(g.ticker)
            g0, g1 = g.start.min(), g.end.max()     # solo tramos que coinciden en el tiempo (tickers reutilizados)
            ws = mem_full[mem_full.ticker.isin(syms) & (mem_full.sector_wiki != "") & (mem_full.start <= g1)
                          & ((mem_full.end == "") | (mem_full.end >= g0))].sort_values("start")
            if len(ws):
                sector = ws.sector_wiki.iat[-1]
        sector_src = "wikipedia" if sector else ""
        if not sector:
            for c in g.cik:
                if c and sic_sector.get(c):
                    sector, sector_src = sic_sector[c], "sic"
                    break
        parts = []
        for k, r in g.iterrows():
            d = load(k)
            d = d[d.index >= cstart]
            if d.empty:
                continue
            # clase de acciones: se queda la de mayor liquidez en su primer día dentro del marco (sin mirar después)
            liq0 = d.adv20.dropna()
            x = pd.DataFrame({"date": d.index, "key": k, "fc": d.flow_complete.fillna(False).astype(bool).to_numpy(),
                              "start": r.start, "liq0": -(liq0.iat[0] if len(liq0) else 0.0)})
            parts.append(x)
        if not parts:
            continue
        pick = pd.concat(parts).sort_values(["date", "fc", "start", "liq0", "key"],
                                            ascending=[True, False, True, True, True]).drop_duplicates("date")
        for k, dd in pick.groupby("key"):
            r = s.loc[k]
            d = load(k).loc[dd.date.to_numpy()]
            dates = d.index.to_numpy()
            pos = np.array([cpos.get(x, -1) for x in dates])
            # eventos
            evs = json.loads(r.events) if r.events else []
            ep = np.array(sorted(cpos[e] for e, t in evs if t in FLOW_EVENTS and e in cpos))
            past = np.zeros(len(d), bool)
            fut = np.array([""] * len(d), dtype=object)
            if len(ep):
                lo = np.searchsorted(ep, pos - LOOKBACK, side="left")
                hi = np.searchsorted(ep, pos, side="right")
                past = hi > lo
                hi2 = np.searchsorted(ep, pos + HORIZON, side="right")
                fut = np.where(hi2 > hi, "evento", "")
            # índice vigente en t (prioridad 500 > 400 > 600), o ex-miembro
            idx_now = np.array(["ex"] * len(d), dtype=object)
            for pri in ("sp600", "sp400", "sp500"):
                for a, b, ix, _ in ivs:
                    if ix == pri:
                        idx_now[(dates >= a) & (dates <= b)] = pri
            # capitalización
            splits = json.loads(r.splits_list) if r.splits_list else []
            mc_pit = mc_retro = np.full(len(d), np.nan)
            multi = np.zeros(len(d), bool)
            if r.cik and not r.cik_conflict:
                fl = filings(r.cik)
                if fl is not None:
                    full = load(k)

                    def turnover_at(filed, shares):
                        w = full[full.index <= filed].tail(1)
                        if w.empty or not (w.adv20.iat[0] > 0):
                            return None
                        return float(w.adv20.iat[0] / (shares * w.raw_close.iat[0]))
                    okp = clean_pit(fl, splits, turnover_at)
                    okr = clean_retro(fl, splits)
                    shares_stats["filings"] += len(fl)
                    shares_stats["rejected_pit"] += int((~okp).sum())
                    shares_stats["rejected_retro"] += int((~okr).sum())
                    shares_stats["disagree"] += int((okp != okr).sum())
                    mc_pit, multi = mcap_series(fl, okp, splits, dates, d.raw_close.to_numpy())
                    mc_retro, _ = mcap_series(fl, okr, splits, dates, d.raw_close.to_numpy())
            rows.append(pd.DataFrame({
                "company": cid, "key": k, "date": dates, "cik": r.cik, "sector": sector,
                "sector_src": sector_src, "cik_conflict": bool(r.cik_conflict),
                "flow": d.flow.to_numpy(), "R": d.R.to_numpy(), "mom": d.mom.to_numpy(),
                "w1": d.w1.to_numpy(), "m1": d.m1.to_numpy(),
                "flow_complete": d.flow_complete.fillna(False).astype(bool).to_numpy(),
                "raw_close": d.raw_close.to_numpy(), "adv20": d.adv20.to_numpy(),
                "spread_ar21": d.spread_ar21.to_numpy(),
                "mcap_pit": mc_pit, "mcap_retro": mc_retro, "multiclass": multi,
                "idx_now": idx_now, "past_event": past, "future_event_40": fut,
                "series_end": r.end, "terminated": r.terminated == "True"}))
    p = pd.concat(rows, ignore_index=True)
    p["turnover"] = p.adv20 / p.mcap_pit
    p["size"] = [tier(x, SIZE_TIERS) for x in p.mcap_pit.to_numpy()]
    p["size_retro"] = [tier(x, SIZE_TIERS) for x in p.mcap_retro.to_numpy()]
    p["liq"] = [tier(x, LIQ_TIERS) for x in p.adv20.to_numpy()]
    p["year"] = p.date.str[:4]
    p["usable"] = p.flow_complete & ~p.past_event
    p["operable"] = p.usable & (p.raw_close >= 3) & (p.adv20 >= 1e6)
    # terminal dentro de 40 sesiones (no excluye; se trata en el resultado)
    p.to_parquet(C.WORK / f"panel_{TAG}.parquet")
    s.reset_index().to_csv(C.WORK / f"companies_{TAG}.csv", index=False)
    pd.DataFrame(links, columns=["a", "b", "tipo", "n", "coincidencia"]).to_csv(C.WORK / f"company_links_{TAG}.csv",
                                                                               index=False)
    json.dump(dict(shares_stats), open(C.PUB / f"{TAG}_shares_cleaning.json", "w"), indent=1)
    print("filas", len(p), "empresas", p.company.nunique(), dict(shares_stats), flush=True)


if __name__ == "__main__":
    main()
