"""Etapa 1 — caracterización del Flow negativo (preregistro v3 firmado, §4-§5, §9). Solo datos de desarrollo.

Uso:
  py -3 s4_etapa1.py --tanda 1           # señales 2018-2020, todas las tallas; elige celdas de grandes, medianas y
                                         # «sin capitalización», estima M0/M1 de grandes y medianas y CONGELA
                                         # data/etapa1_tanda1_frozen.json
  py -3 s4_etapa1.py --tanda 2           # (bloqueada hasta que exista la congelación de la tanda 1)

Las filas de desarrollo salen siempre de fn_config.dev_mask(): nunca entra un día de prueba. Los precios posteriores a
la señal (hasta 40 sesiones) sí se usan: son el resultado de las señales de desarrollo.

Decisiones de implementación no fijadas literalmente en el preregistro (documentadas en el informe):
- Ruta de precios por empresa: series de sus claves concatenadas por fecha; en el cambio de clave (cambio de ticker)
  el retorno del día es cierre nuevo / cierre anterior.
- Percentil propio: exige ≥ 120 valores de Flow completo entre las 252 sesiones; si no, sin dato.
- Liquidez (quintiles) y rotación (tercios): dentro de talla y día, entre los días utilizables.
- Elección de celdas: población A, exceso frente a la talla, episodios.
- Un evento corporativo en (t, t+40] se marca (`fut_event`) y se informa su peso; no excluye.

Salidas: data/etapa1_tanda{N}_tables.json, data/etapa1_tanda{N}_selection.json, ETAPA1_TANDA{N}_INFORME.md (repo,
solo agregados) y WORK/etapa1_tanda{N}_rows.parquet (fuera del repo).
"""
import argparse
import hashlib
import json
from collections import defaultdict

import numpy as np
import pandas as pd

import fn_config as C

import os

SER = C.WORK / "series"
SER_C1 = C.WORK / "series_c1"
# Enmienda 1 (2026-11-20). Sin variables, reproduce la tanda 1 original sobre el panel v4.
PANEL_TAG = os.environ.get("FN_PANEL", "v4")            # panel de entrada (p. ej. v4c1)
OUT_SUFFIX = os.environ.get("FN_OUT", "")               # sufijo de salida (p. ej. c1): nunca toca los originales
CORR = {x for x in os.environ.get("FN_CORR", "").split(",") if x}
#   splits/identity: series corregidas; spinoffs: valor de las escindidas; jumps: saltos indeterminados = ausentes;
#   terminals: fusiones valoradas con Alpaca; missing: §7, los resultados no observados fuera del principal
#   missing_j (enmienda 2): §7 solo para saltos indeterminados y escisiones no reconstruibles; los desenlaces
#   terminales desconocidos vuelven al preregistro §4.2 (último cierre en el principal, cotas 0 / último cierre)
# Enmienda 2: con FN_FREEZE=1 la versión corregida se congela de verdad (etapa1_tanda{n}{sufijo}_frozen.json, sin
# sobrescribir) y la tanda 2 corregida toma sus plazas de la tanda 1 corregida congelada.
FREEZE_CORR = os.environ.get("FN_FREEZE") == "1"


def tanda1_freeze_path():
    return C.PUB / f"etapa1_tanda1{OUT_SUFFIX}_frozen.json" if OUT_SUFFIX else C.TANDA1_FREEZE

HS = (5, 10, 20, 40)
XS = (-10, -20, -30)
Z_ABS = [(-5, 0, "Z0 [-5,0)"), (-10, -5, "Z1 [-10,-5)"), (-15, -10, "Z2 [-15,-10)"), (-20, -15, "Z3 [-20,-15)"),
         (-30, -20, "Z4 [-30,-20)"), (-1e9, -30, "Z5 <-30")]
PCT_BANDS = [(0, 1, "<=1"), (1, 5, "(1,5]"), (5, 10, "(5,10]"), (10, 25, "(10,25]"), (25, 50, "(25,50]")]
BOOT_REPS = 2000
RNG = np.random.default_rng(20261120)
TERM_UNKNOWN_ACQ = {"adquisicion_tipo_desconocido", "adquisicion_acciones", "adquisicion_mixta", "fusion"}


# ------------------------------------------------------------------------------------------------- datos
def company_paths(km):
    """Ruta de precios por empresa, con la misma clave por fecha que el panel v4 (`km`: company, key, date).

    Antes de la primera fecha del panel (lookbacks) se usa la primera clave del panel. Devuelve dict empresa →
    DataFrame (date, o, h, l, c, flow, fc) con índice de rendimiento total continuo.
    """
    out = {}
    cache = {}

    def ser(k):
        if k not in cache:
            cache.clear() if len(cache) > 50 else None
            cache[k] = pd.read_parquet(series_path(k),
                                       columns=["date", "open_adj", "high_adj", "low_adj", "adj", "raw_close",
                                                "flow", "flow_complete"]).set_index("date")
        return cache[k]
    for cid, g in km.groupby("company", sort=False):
        g = g.sort_values("date")
        k0 = g.key.iat[0]
        pre = ser(k0)
        pre = pre[pre.index < g.date.iat[0]].assign(k=k0)
        parts = [pre]
        for k, h in g.groupby("key", sort=False):
            parts.append(ser(k).reindex(h.date.to_numpy()).assign(k=k))
        d = pd.concat(parts).sort_index()
        d = d[~d.index.duplicated()].dropna(subset=["adj"]).reset_index().rename(columns={"index": "date"})
    # índice de rendimiento total continuo: dentro de una clave, cociente de `adj`; en el salto, cierre bruto
        r = d.adj / d.adj.shift(1)
        jump = d.k != d.k.shift(1)
        r[jump] = d.raw_close / d.raw_close.shift(1)
        r.iloc[0] = 1.0
        idx = np.cumprod(r.fillna(1.0).to_numpy())
        sc = idx / d.adj.to_numpy()                   # escala por día, misma para o/h/l de ese día
        out[cid] = pd.DataFrame({"date": d.date.to_numpy(), "o": d.open_adj.to_numpy() * sc,
                                 "h": d.high_adj.to_numpy() * sc, "l": d.low_adj.to_numpy() * sc, "c": idx,
                                 "flow": d.flow.to_numpy(),
                                 "fc": d.flow_complete.fillna(False).astype(bool).to_numpy(),
                                 "raw": d.raw_close.to_numpy(), "k": d.k.to_numpy()})
    return out


_CORR_KEYS = None


def corr_keys():
    """Claves cuya serie corregida corresponde a las familias activas (mismo criterio que s1_panel)."""
    global _CORR_KEYS
    if _CORR_KEYS is None:
        _CORR_KEYS = set()
        if CORR & {"splits", "identity"}:
            ov = json.loads((C.PUB / "corr1_series_overlay.json").read_text(encoding="utf-8"))
            for fam in ("splits", "identity"):
                if fam in CORR:
                    _CORR_KEYS |= set(ov[fam])
            if "identity" in CORR:
                _CORR_KEYS |= set(ov["new_keys"])
    return _CORR_KEYS


def series_path(k):
    return (SER_C1 if k in corr_keys() else SER) / f"{k}.parquet"


def terminal_by_company(companies, last_key):
    """Multiplicadores del valor terminal: (central, cota baja, cota alta, desconocido?) por empresa."""
    t = pd.read_csv(C.WORK / "terminal_events_v4_full.csv")
    comp = pd.read_csv(C.WORK / f"companies_{PANEL_TAG}.csv")
    merger_val = alpaca_merger_values(comp) if "terminals" in CORR else {}
    term = comp.set_index("key").terminated.astype(str).eq("True").to_dict()
    ev = t.set_index("key")
    out = {}
    for cid in companies:
        k = last_key[cid]
        if not term.get(k, False):
            continue
        if k in ev.index:
            e = ev.loc[k]
            cat, st = e.category, e.value_status
            if st == "conocido" and e.last_close > 0:
                m = float(e.terminal_value / e.last_close)
                out[cid] = (m, m, m, False, cat)
            elif k in merger_val and e.last_close > 0:
                m = float(merger_val[k] / e.last_close)
                out[cid] = (m, m, m, False, cat + "_alpaca")
            elif cat in TERM_UNKNOWN_ACQ and st != "terminos_incoherentes":
                out[cid] = (1.0, float(np.exp(-0.05)), float(np.exp(0.05)), True, cat)
            else:                                     # quiebra, OTC, escisión, incoherentes, desconocido, ticker sin sucesor
                out[cid] = (1.0, 0.0, 1.0, True, cat)
        elif k.endswith("__pre") and k.startswith("FOXA"):
            # 21st Century Fox: escisión de Fox Corp + compra mixta por Disney, valor no reconstruido (regla §4.2)
            out[cid] = (1.0, float(np.exp(-0.05)), float(np.exp(0.05)), True, "adquisicion_mixta_21cf")
        else:
            out[cid] = (1.0, 0.0, 1.0, True, "sin_evento")
    return out


def alpaca_merger_values(comp):
    """Valor por acción de las fusiones de Alpaca (2020+): efectivo + canje × cierre del comprador en la fecha
    efectiva (o el último cierre anterior). Solo si el comprador tiene serie en el universo que cubre esa fecha."""
    from s0_series import load_ca
    raw = load_ca()["raw"]
    syms = {k: set(str(r.symbols).split("|")) | {r.ticker} for k, r in comp.set_index("key").iterrows()}
    span = comp.set_index("key")[["start", "end"]]
    out = {}
    for typ in ("cash_mergers", "stock_mergers", "stock_and_cash_mergers"):
        for a in raw.get(typ, []):
            acq, eff = a.get("acquiree_symbol"), a.get("effective_date")
            cash = float(a.get("cash_rate") or a.get("rate") or 0) if typ != "stock_mergers" else 0.0
            rate = float(a.get("acquirer_rate") or 0) / float(a.get("acquiree_rate") or 1)
            buyer = a.get("acquirer_symbol") or ""
            for k, ss in syms.items():
                if acq not in ss or not (span.start[k] <= eff and abs((pd.Timestamp(span.end[k]) - pd.Timestamp(eff)).days) <= 10):
                    continue
                v = cash
                if rate:
                    if not buyer:
                        continue
                    px = None
                    for kb, sb in syms.items():
                        if buyer in sb and span.start[kb] <= eff <= span.end[kb]:
                            sb_ = pd.read_parquet(series_path(kb), columns=["date", "raw_close"])
                            sb_ = sb_[sb_.date <= eff]
                            if len(sb_):
                                px = float(sb_.raw_close.iat[-1])
                                break
                    if px is None:
                        continue
                    v += rate * px
                if v > 0:
                    out[k] = v
    return out


def spy_frame():
    s = pd.read_parquet(SER / "SPY__none__e0.parquet", columns=["date", "open_adj", "adj"])
    s = s.sort_values("date").reset_index(drop=True)
    c = s.adj
    s["sma50"], s["sma200"] = c.rolling(50).mean(), c.rolling(200).mean()
    s["regime"] = np.where(c < s.sma200, "bear",
                           np.where((c >= s.sma50) & (s.sma50 >= s.sma200), "bull", "lateral"))
    s["ret21"] = c / c.shift(21) - 1
    return s


# --------------------------------------------------------------------------------------------- resultados
def corr_inputs(paths):
    """Enmienda 1: por empresa, escisiones a reconstruir (spinoffs/identity) y saltos indeterminados (jumps)."""
    spins, jumps = defaultdict(list), defaultdict(list)
    sp = pd.read_csv(C.PUB / "corr1_spinoffs.csv", keep_default_na=False)
    sp = sp[sp.family.isin(CORR & {"spinoffs", "identity"})]
    jt = pd.read_csv(C.PUB / "corr1_jumps.csv")
    jt = jt[(jt["class"] == "indeterminate") & jt.in_scope] if "jumps" in CORR else jt.iloc[0:0]
    wanted = set(sp.parent_key) | set(jt.key)
    key_pos = {}
    for cid, P in paths.items():
        m = np.isin(P.k.to_numpy(), list(wanted))
        for i in np.where(m)[0]:
            key_pos[(P.k.iat[i], P.date.iat[i])] = (cid, int(i))
    fake = {}
    if len(sp):
        comp = pd.read_csv(C.WORK / f"companies_{PANEL_TAG}.csv").drop_duplicates("key").set_index("key")
        ov = json.loads((C.PUB / "corr1_series_overlay.json").read_text(encoding="utf-8")) if CORR & {"splits", "identity"} else {}
        for r in sp.itertuples():
            k = r.parent_key
            sl = None
            for fam in ("identity", "splits"):
                if fam in CORR and k in ov.get(fam, {}) and "splits_list" in ov[fam][k]:
                    sl = ov[fam][k]["splits_list"]
            if sl is None and k in comp.index:
                sl = json.loads(comp.splits_list[k] or "[]")
            # escisión que Alpaca aplicó como «split»: la serie ya la incorpora (reinversión aproximada)
            fake[(k, r.ex_date)] = any(abs((pd.Timestamp(d) - pd.Timestamp(r.ex_date)).days) <= 3 and f > 1
                                       for d, f in (sl or []))
    if len(sp):
        for r in sp.itertuples():
            hit = key_pos.get((r.parent_key, r.ex_date))
            if hit is None:
                continue
            cid, e = hit
            P = paths[cid]
            n = len(P)
            if not r.child_key or r.ratio in ("", None) or (isinstance(r.ratio, float) and np.isnan(r.ratio)):
                spins[cid].append((e, None, None, None, f"{r.parent_key}@{r.ex_date}"))
                continue
            ch = pd.read_parquet(series_path(r.child_key), columns=["date", "open", "high", "low", "close"])
            ch = ch.set_index("date").reindex(P.date.iloc[e:]).ffill()
            conv = P.c.iat[e] / P.raw.iat[e]          # unidades del índice por dólar de la matriz el día ex
            ratio = float(r.ratio)
            xc, xh, xl = np.zeros(n), np.zeros(n), np.zeros(n)
            xc[e:] = ratio * ch.close.to_numpy() * conv
            xh[e:] = ratio * ch.high.to_numpy() * conv
            xl[e:] = ratio * ch.low.to_numpy() * conv
            if fake.get((r.parent_key, r.ex_date)) and e > 0:
                # deshacer la reinversión implícita: factor medido en los datos (índice ajustado / bruto el día ex)
                fp = (P.c.iat[e] / P.c.iat[e - 1]) / (P.raw.iat[e] / P.raw.iat[e - 1])
                cc, hh_, ll_ = P.c.to_numpy(), P.h.to_numpy(), P.l.to_numpy()
                # valor = (índice + escindida) / fp  →  extra = valor − índice
                xc[e:] = (cc[e:] + xc[e:]) / fp - cc[e:]
                xh[e:] = (hh_[e:] + xh[e:]) / fp - hh_[e:]
                xl[e:] = (ll_[e:] + xl[e:]) / fp - ll_[e:]
            ok = not np.isnan(xc[e:]).any()
            spins[cid].append((e, np.nan_to_num(xc), np.nan_to_num(xh), np.nan_to_num(xl), None if ok else "child_nan"))
    for r in jt.itertuples():
        hit = key_pos.get((r.key, r.date))
        if hit is not None:
            jumps[hit[0]].append(hit[1])
    return spins, jumps


def outcomes(rows, paths, term, spins=None, jumps=None):
    """Retornos (entrada apertura t+1, y cierre t+1 como sensibilidad), MFE/MAE, nuevo mínimo, cotas terminales."""
    res = defaultdict(list)
    spins, jumps = spins or {}, jumps or {}
    for cid, g in rows.groupby("company", sort=False):
        P = paths[cid]
        SP, JP = spins.get(cid, []), jumps.get(cid, [])
        pos = {d: i for i, d in enumerate(P.date)}
        o, h, l, c, fl, fc = P.o.to_numpy(), P.h.to_numpy(), P.l.to_numpy(), P.c.to_numpy(), P.flow.to_numpy(), P.fc.to_numpy()
        n = len(P)
        tm = term.get(cid)
        for ri, d in zip(g.index, g.date):
            i = pos.get(d)
            res["row"].append(ri)
            if i is None or i + 1 >= n and tm is None:
                for H in HS:
                    for b in ("", "_lo", "_hi"):
                        res[f"r{H}{b}"].append(np.nan)
                    res[f"rc{H}"].append(np.nan)
                    res[f"mfe{H}"].append(np.nan)
                    res[f"mae{H}"].append(np.nan)
                    res[f"nl{H}"].append(np.nan)
                    res[f"unk{H}"].append(False)
                    res[f"unk_s{H}"].append(False)
                    res[f"unk_j{H}"].append(False)
                    res[f"rja{H}"].append(np.nan)
                res["ret21"].append(np.nan)
                res["own_pct"].append(np.nan)
                for X in XS:
                    res[f"ep{X}"].append(False)
                continue
            # retorno previo de 21 sesiones y percentil propio y episodios (con la propia ruta)
            res["ret21"].append(c[i] / c[i - 21] - 1 if i >= 21 else np.nan)
            w = fl[max(0, i - 251): i + 1][fc[max(0, i - 251): i + 1]]
            res["own_pct"].append(100.0 * (w <= fl[i]).mean() if len(w) >= 120 and fc[i] else np.nan)
            for X in XS:
                prev = fl[i - 10: i] if i >= 10 else np.array([])
                res[f"ep{X}"].append(bool(fl[i] < X and len(prev) == 10 and np.all(prev >= X)))
            low20 = l[max(0, i - 19): i + 1].min()
            if i + 1 < n:
                e_o, e_c = o[i + 1], c[i + 1]
            else:                                     # termina el mismo día: entrada al valor terminal
                e_o = e_c = c[i] * tm[0]
            flow_jump = any(e <= i <= e + 20 for e in JP)     # Flow de t posiblemente afectado por el salto
            for H in HS:
                j = i + H
                jj = min(j, n - 1)
                act = [x for x in SP if i + 1 < x[0] <= jj]      # escisiones dentro del plazo (posición comprada antes)
                unk_s = any(x[1] is None or x[4] for x in act)
                xc = sum(x[1] for x in act if x[1] is not None) if act and not unk_s else None
                xh = sum(x[2] for x in act if x[2] is not None) if xc is not None else None
                xl = sum(x[3] for x in act if x[3] is not None) if xc is not None else None
                unk_j = flow_jump or any(i < e <= j for e in JP)
                if j < n:
                    v = c[j] + (xc[j] if xc is not None else 0.0)
                    vals = (v, v, v)
                    unk = False
                    win = slice(i + 1, j + 1)
                    hh = (h[win] + (xh[win] if xh is not None else 0)).max()
                    ll = (l[win] + (xl[win] if xl is not None else 0)).min()
                elif tm is not None:
                    last = c[n - 1] + (xc[n - 1] if xc is not None else 0.0)
                    vals = (last * tm[0], last * tm[1], last * tm[2])
                    unk = tm[3]
                    win = slice(i + 1, n)
                    hw = (h[win] + (xh[win] if xh is not None else 0)) if n > i + 1 else np.array([-np.inf])
                    lw = (l[win] + (xl[win] if xl is not None else 0)) if n > i + 1 else np.array([np.inf])
                    hh = max(hw.max(), vals[0])
                    ll = min(lw.min(), vals[0])
                else:
                    vals, unk, hh, ll = (np.nan,) * 3, False, np.nan, np.nan
                res[f"r{H}"].append(vals[0] / e_o - 1)
                res[f"r{H}_lo"].append(vals[1] / e_o - 1)
                res[f"r{H}_hi"].append(vals[2] / e_o - 1)
                res[f"rc{H}"].append(vals[0] / e_c - 1)
                res[f"mfe{H}"].append(hh / e_o - 1)
                res[f"mae{H}"].append(ll / e_o - 1)
                res[f"nl{H}"].append(bool(ll < low20) if ll == ll else np.nan)
                res[f"unk{H}"].append(unk)
                res[f"unk_s{H}"].append(bool(unk_s))
                res[f"unk_j{H}"].append(bool(unk_j))
                # enmienda 2: retorno con los saltos indeterminados del plazo anulados (cota de §7 de la enmienda 1).
                # Salto del día e = c[e]/c[e-1]; si cae en la sesión de entrada, la entrada pasa al cierre de t.
                ja = [e for e in JP if i < e <= j and e < n]
                if ja and vals[0] == vals[0]:
                    fac = float(np.prod([c[e] / c[e - 1] for e in ja]))
                    base = c[i] if (i + 1) in ja else e_o
                    res[f"rja{H}"].append(vals[0] / fac / base - 1)
                else:
                    res[f"rja{H}"].append(vals[0] / e_o - 1 if vals[0] == vals[0] else np.nan)
    out = pd.DataFrame(res).set_index("row")
    return rows.join(out)


def spy_returns(spy, dates):
    pos = {d: i for i, d in enumerate(spy.date)}
    o, c = spy.open_adj.to_numpy(), spy.adj.to_numpy()
    out = {}
    for H in HS:
        out[H] = {d: (c[pos[d] + H] / o[pos[d] + 1] - 1) if pos.get(d) is not None and pos[d] + H < len(c) else np.nan
                  for d in dates}
    return out


# --------------------------------------------------------------------------------------------- etiquetas
def label(df, spy):
    sp = spy.set_index("date")
    df["regime"] = df.date.map(sp.regime)
    df["spy21"] = df.date.map(sp.ret21)
    f = df.flow
    df["z_abs"] = None
    for lo, hi, n in Z_ABS:
        df.loc[(f >= lo) & (f < hi), "z_abs"] = n
    grp = df.groupby(["date", "size"])
    df["xs_pct"] = grp.flow.rank(pct=True, method="max") * 100
    for c, n in (("xs_pct", "xs_band"), ("own_pct", "own_band")):
        df[n] = None
        for lo, hi, name in PCT_BANDS:
            df.loc[(df[c] > lo) & (df[c] <= hi), n] = name
    df["liq_q"] = (grp.adv20.rank(pct=True) * 5).clip(upper=4.999).fillna(-1).astype(int) + 1
    df.loc[df.adv20.isna(), "liq_q"] = 0
    tv = df.turnover.where(df["size"] != "unknown")
    df["rot_t"] = (tv.groupby([df.date, df["size"]]).rank(pct=True) * 3).clip(upper=2.999)
    df["rot_t"] = df.rot_t.apply(lambda x: "no_evaluable" if x != x else ("T1", "T2", "T3")[int(x)])
    # tipo de caída (jerárquica, 21 sesiones hasta t)
    sec_med = df.groupby(["date", "sector"]).ret21.transform("median")
    sec_n = df.groupby(["date", "sector"]).ret21.transform("count")
    few = (sec_n < 5) | df.sector.isna() | (df.sector == "")
    ref = np.where(few, df.spy21, sec_med)
    general = (df.spy21 <= -0.05) | (~few & (sec_med <= -0.08))
    idio = ~general & ((df.ret21 - ref) <= -0.10) & (df.spy21 > -0.03)
    df["drop"] = np.where(general, "general", np.where(idio, "idiosincratica", "mixta"))
    df["drop_spy_sub"] = few
    return df


def excess(df, spy_r):
    for H in HS:
        df[f"unkany{H}"] = df[f"unk{H}"] | df[f"unk_s{H}"] | df[f"unk_j{H}"]
        if "missing_j" in CORR:
            # enmienda 2: fuera del principal solo los saltos indeterminados y las escisiones no reconstruibles (en
            # la señal y en la media de su talla); los terminales desconocidos se quedan con el último cierre.
            # Sensibilidades: xs = saltos tal cual; xa = saltos anulados (cotas de la enmienda 1 §7).
            miss = df[f"unk_s{H}"] | df[f"unk_j{H}"]
            for nm, src in (("rs", f"r{H}"), ("ra", f"rja{H}")):
                df[f"{nm}{H}"] = df[src]
                ref = df.groupby(["date", "size"])[f"{nm}{H}"].transform("mean")
                df[f"{'xs' if nm == 'rs' else 'xa'}{H}"] = df[f"{nm}{H}"] - ref
            for col in (f"r{H}", f"r{H}_lo", f"r{H}_hi", f"rc{H}", f"mfe{H}", f"mae{H}", f"nl{H}"):
                df.loc[miss, col] = np.nan
        elif "missing" in CORR:
            # enmienda 1 §7: los resultados no observados quedan fuera del principal (también de la media de talla);
            # sensibilidad (xs*) con ellos dentro y las cotas del preregistro §4.2
            for b in ("", "_lo", "_hi"):
                df[f"rs{H}{b}"] = df[f"r{H}{b}"]
                ref = df.groupby(["date", "size"])[f"rs{H}{b}"].transform("mean")
                df[f"xs{H}{b}"] = df[f"rs{H}{b}"] - ref
            miss = df[f"unkany{H}"]
            for col in (f"r{H}", f"r{H}_lo", f"r{H}_hi", f"rc{H}", f"mfe{H}", f"mae{H}", f"nl{H}"):
                df.loc[miss, col] = np.nan
        for b in ("", "_lo", "_hi"):
            col = f"r{H}{b}"
            ref = df.groupby(["date", "size"])[col].transform("mean")
            df[f"x{H}{b}"] = df[col] - ref
        df[f"xspy{H}"] = df[f"r{H}"] - df.date.map(spy_r[H])
        med = df.groupby(["date", "sector"])[f"r{H}"].transform("median")
        cnt = df.groupby(["date", "sector"])[f"r{H}"].transform("count")
        df[f"xsec{H}"] = np.where(cnt >= 6, df[f"r{H}"] - med, np.nan)   # al menos 5 pares además de la empresa
    return df


# --------------------------------------------------------------------------------------------- inferencia
def nw_t(y, lag):
    y = np.asarray(y, float)
    n = len(y)
    if n < 3:
        return np.nan, np.nan
    m = y.mean()
    e = y - m
    v = e @ e / n
    for k in range(1, min(lag, n - 1) + 1):
        v += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    se = np.sqrt(max(v, 0) / n)
    return m, (m / se if se > 0 else np.nan)


def boot_ci(y, block, reps=BOOT_REPS, alpha=0.05):
    y = np.asarray(y, float)
    n = len(y)
    if n < 10:
        return (np.nan, np.nan)
    b = min(block, n)
    nb = int(np.ceil(n / b))
    starts = RNG.integers(0, n, size=(reps, nb))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]) % n
    means = y[idx.reshape(reps, -1)[:, :n]].mean(axis=1)
    return tuple(np.quantile(means, [alpha / 2, 1 - alpha / 2]))


def daily(g, col):
    s = g.groupby("date")[col].mean().dropna()
    return s


def summarize(g, H, boot=False):
    r = g[f"r{H}"].dropna()
    if len(r) == 0:
        return None
    x = g[f"x{H}"]
    ser = daily(g, f"x{H}")
    m, t = nw_t(ser.to_numpy(), H)
    out = {"n": int(len(r)), "companies": int(g.loc[r.index, "company"].nunique()),
           "weeks": int(pd.to_datetime(g.loc[r.index, "date"]).dt.to_period("W").nunique()),
           "ret_mean": float(r.mean()), "ret_median": float(r.median()),
           "ret_trim1": float(r.clip(r.quantile(.01), r.quantile(.99)).mean()), "ret_pos": float((r > 0).mean()),
           "x_mean": float(x.mean()), "x_median": float(x.median()), "x_pos": float((x > 0).mean()),
           "x_daily_mean": float(m), "t_nw": float(t), "days": int(len(ser)),
           "x_lo_daily": float(daily(g, f"x{H}_lo").mean()), "x_hi_daily": float(daily(g, f"x{H}_hi").mean()),
           "xspy_mean": float(g[f"xspy{H}"].mean()), "xsec_mean": float(g[f"xsec{H}"].mean()),
           "xsec_share": float(g[f"xsec{H}"].notna().mean()),
           "mfe_mean": float(g[f"mfe{H}"].mean()), "mae_mean": float(g[f"mae{H}"].mean()),
           "new_low": float(g[f"nl{H}"].astype(float).mean()),
           "p5": float(r.quantile(.05)), "p10": float(r.quantile(.10)),
           "p_le_m10": float((r <= -0.10).mean()), "p_le_m20": float((r <= -0.20).mean()),
           "unknown_share": float(g[f"unkany{H}"].mean()), "unknown_terminal": float(g[f"unk{H}"].mean()),
           "unknown_spinoff": float(g[f"unk_s{H}"].mean()), "unknown_jump": float(g[f"unk_j{H}"].mean()), "fut_event_share": float((g.future_event_40 == "evento").mean()),
           "sic_share": float((g.sector_src == "sic").mean()),
           "rc_mean": float(g[f"rc{H}"].mean())}
    if f"xs{H}_lo" in g:
        out["sens_incl_x_daily_mean"] = float(daily(g, f"xs{H}").mean())
        out["sens_incl_x_lo_daily"] = float(daily(g, f"xs{H}_lo").mean())
        out["sens_incl_x_hi_daily"] = float(daily(g, f"xs{H}_hi").mean())
    elif f"xs{H}" in g:
        out["sens_jumps_as_is_daily"] = float(daily(g, f"xs{H}").mean())
        out["sens_jumps_annulled_daily"] = float(daily(g, f"xa{H}").mean())
    out["insufficient_ep"] = None
    if boot:
        for b in (60, 20, 120):
            out[f"ci95_b{b}"] = [float(v) for v in boot_ci(ser.to_numpy(), b)]
    return out


# --------------------------------------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tanda", type=int, required=True)
    a = ap.parse_args()
    tanda = a.tanda

    cols = ["company", "key", "date", "sector", "sector_src", "flow", "R", "w1", "m1", "raw_close", "adv20",
            "mcap_pit", "idx_now", "future_event_40", "size", "size_retro", "turnover", "usable", "operable"]
    p = pd.read_parquet(C.WORK / f"panel_{PANEL_TAG}.parquet", columns=cols)
    p = p[p.usable].reset_index(drop=True)
    if tanda == 2 and not tanda1_freeze_path().exists():
        raise SystemExit(f"Tanda 2 bloqueada: falta {tanda1_freeze_path()}")
    p = p[C.dev_mask(p, tanda).to_numpy()].reset_index(drop=True)
    if tanda == 2:      # la tanda 2 solo añade los días 2021-2022 de pequeñas y micro (2018-2020 ya visto)
        p = p[(p.date > C.TANDA1_END) & p["size"].isin(["small", "micro"])].reset_index(drop=True)
    print(f"tanda {tanda}: filas {len(p)}, fechas {p.date.min()} → {p.date.max()}", flush=True)
    assert all(C.period_for(s, d) == "dev" for s, d in p[["size", "date"]].drop_duplicates().itertuples(index=False))

    km = pd.read_parquet(C.WORK / f"panel_{PANEL_TAG}.parquet", columns=["company", "key", "date"])
    km = km[km.company.isin(set(p.company))]
    last_key = km.sort_values("date").groupby("company").key.last().to_dict()
    paths = company_paths(km)
    term = terminal_by_company(set(p.company), last_key)
    print("rutas", len(paths), "terminales", len(term), flush=True)

    miss = ~p.company.isin(paths)
    print("filas sin ruta de precios (se descartan):", int(miss.sum()), flush=True)
    p = p[~miss].reset_index(drop=True)
    spins, jumps = corr_inputs(paths) if CORR else ({}, {})
    p = outcomes(p, paths, term, spins, jumps)
    spy = spy_frame()
    p = label(p, spy)
    p = excess(p, spy_returns(spy, p.date.unique()))
    rows_out = C.WORK / f"etapa1_tanda{tanda}{OUT_SUFFIX}_rows.parquet"
    p.to_parquet(rows_out)
    print("filas con resultado", int(p.r20.notna().sum()), "→", rows_out, flush=True)

    neg = p[p.flow < 0]
    sizes = sorted(p["size"].unique())

    # ---------- tablas principales: talla × nivel × plazo, estados y episodios, poblaciones A y B
    tables = {"meta": {"tanda": tanda, "dates": [p.date.min(), p.date.max()], "rows": int(len(p)),
                       "neg_rows": int(len(neg))}}
    T = {}
    for pop, base in (("A", p), ("B", p[p.operable])):
        for sz in sizes:
            g0 = base[base["size"] == sz]
            refs = {"todos": g0, "flow>=0": g0[g0.flow >= 0], "[0,4)": g0[(g0.flow >= 0) & (g0.flow < 4)]}
            levels = dict(refs)
            for _, _, n in Z_ABS:
                levels[f"abs {n}"] = g0[g0.z_abs == n]
            for _, _, n in PCT_BANDS:
                levels[f"xs {n}"] = g0[(g0.flow < 0) & (g0.xs_band == n)]
                levels[f"own {n}"] = g0[(g0.flow < 0) & (g0.own_band == n)]
            for X in XS:
                levels[f"ep {X}"] = g0[g0[f"ep{X}"]]
            for lv, g in levels.items():
                for H in HS:
                    s = summarize(g, H, boot=(H in (20, 40) and not lv.startswith("xs") and not lv.startswith("own")))
                    if s:
                        if lv.startswith("ep"):
                            s["insufficient_ep"] = s["n"] < 100 or s["weeks"] < 30
                        T[f"{pop}|{sz}|{lv}|{H}"] = s
        print("pob", pop, "hecho", flush=True)
    tables["main"] = T

    # ---------- cruces (población A, Flow < 0 por nivel absoluto agrupado, plazo 20)
    X_ = {}
    for dim in ("liq_q", "rot_t", "regime", "drop", "idx_now"):
        for (sz, v, z), g in neg.groupby(["size", dim, "z_abs"]):
            s = summarize(g, 20)
            if s:
                X_[f"{sz}|{dim}={v}|{z}|20"] = s
        for X in XS:
            for (sz, v), g in neg[neg[f"ep{X}"]].groupby(["size", dim]):
                s = summarize(g, 20)
                if s:
                    s["insufficient_ep"] = s["n"] < 100 or s["weeks"] < 30
                    X_[f"{sz}|{dim}={v}|ep {X}|20"] = s
    tables["crosses"] = X_
    print("cruces", len(X_), flush=True)

    # ---------- elección de celdas (§5): episodios, población A, exceso frente a la talla
    sel_sizes = ("large", "mid", "unknown") if tanda == 1 else ("small", "micro")
    if tanda == 2:
        full = pd.concat([pd.read_parquet(C.WORK / f"etapa1_tanda1{OUT_SUFFIX}_rows.parquet"), p])
        full = full[full["size"].isin(sel_sizes)]
    else:
        full = p
    halves = {1: [("2018-01-01", "2019-06-30"), ("2019-07-01", "2020-12-31")],
              2: [("2018-01-01", "2020-12-31"), ("2021-01-01", "2022-12-31")]}[tanda]
    cand = []
    for sz in sel_sizes:
        for X in XS:
            for H in (20, 40):
                for reg in ("all", "bull", "lateral", "bear"):
                    g = full[(full["size"] == sz) & full[f"ep{X}"]]
                    if reg != "all":
                        g = g[g.regime == reg]
                    g = g.dropna(subset=[f"x{H}"])
                    if len(g) == 0:
                        continue
                    ser = daily(g, f"x{H}")
                    m, t = nw_t(ser.to_numpy(), H)
                    halves_m = [daily(g[(g.date >= a_) & (g.date <= b_)], f"x{H}").mean() for a_, b_ in halves]
                    bl = "xs" if "missing" in CORR else "x"      # cotas: con los no observados dentro (§4.2)
                    # (con missing_j los terminales ya están en el principal con sus cotas: bl = "x")
                    lo, hi = daily(g, f"{bl}{H}_lo").mean(), daily(g, f"{bl}{H}_hi").mean()
                    weeks = pd.to_datetime(g.date).dt.to_period("W").nunique()
                    unk = float(g[f"unkany{H}"].mean())
                    ok = {"t>=2.5": bool(abs(t) >= 2.5), "n>=100": bool(len(g) >= 100), "weeks>=30": bool(weeks >= 30),
                          "halves_same_sign": bool(all(np.sign(h_) == np.sign(m) for h_ in halves_m if h_ == h_)
                                                   and all(h_ == h_ for h_ in halves_m)),
                          "bounds_same_sign": bool(np.sign(lo) == np.sign(m) == np.sign(hi)),
                          "unknown<1%": bool(unk < 0.01)}
                    cand.append({"size": sz, "X": X, "H": H, "regime": reg, "n": int(len(g)), "weeks": int(weeks),
                                 "days": int(len(ser)), "x_daily_mean": float(m), "t_nw": float(t),
                                 "halves": [float(h_) for h_ in halves_m], "x_lo": float(lo), "x_hi": float(hi),
                                 "unknown_share": unk, "criteria": ok, "eligible": all(ok.values())})
    prev_chosen = []
    if tanda == 2:
        prev_chosen = json.loads(tanda1_freeze_path().read_text(encoding="utf-8"))["chosen_cells"]
    slots = 4 - len(prev_chosen)
    elig = sorted([c for c in cand if c["eligible"]], key=lambda c: -abs(c["t_nw"]))
    chosen = elig[:slots]

    # ---------- M0 / M1 (§5, §6.2): grandes y medianas en la tanda 1; pequeñas en la tanda 2
    cuts = json.loads((C.PUB / "v4_h1_frozen_cuts.json").read_text(encoding="utf-8"))
    qw, qm, Rc = cuts["w1_breaks"], cuts["m1_breaks"], cuts["R_tercile_cuts_by_cell"]
    h1_sizes = ("large", "mid") if tanda == 1 else ("small",)
    models = {}
    for sz in h1_sizes:
        d = full[(full["size"] == sz) & (full.flow < 0)].dropna(subset=["w1", "m1", "R", "x20"]).copy()
        d["cell"] = (np.searchsorted(qw, d.w1, side="right").astype(str)
                     + np.searchsorted(qm, d.m1, side="right").astype(str))
        c1 = d.cell.map(lambda c: Rc[c]["c1"])
        c2 = d.cell.map(lambda c: Rc[c]["c2"])
        eq = c1 == c2
        low = np.where(eq, d.R < c1, d.R <= c1)
        high = np.where(eq, d.R > c1, d.R >= c2)
        d["terc"] = np.where(low, "low", np.where(high, "high", "mid"))
        M0 = d.groupby("cell").x20.mean()
        resid = d.x20 - d.cell.map(M0)
        M1 = resid.groupby(d.terc).mean()
        models[sz] = {"n": int(len(d)), "M0": {k: float(v) for k, v in M0.items()},
                      "M0_n": d.cell.value_counts().to_dict(), "M1_tercile_effect": {k: float(v) for k, v in M1.items()},
                      "tercile_n": d.terc.value_counts().to_dict()}

    sel = {"tanda": tanda, "sizes": list(sel_sizes), "slots": slots, "candidates": cand,
           "chosen_cells": prev_chosen + [{k: c[k] for k in ("size", "X", "H", "regime")} for c in chosen],
           "chosen_this_tanda": chosen, "models": models}
    tj = C.PUB / f"etapa1_tanda{tanda}{OUT_SUFFIX}_tables.json"
    sj = C.PUB / f"etapa1_tanda{tanda}{OUT_SUFFIX}_selection.json"
    tj.write_text(json.dumps(tables, indent=1, default=str), encoding="utf-8")
    sj.write_text(json.dumps(sel, indent=1, default=str), encoding="utf-8")
    print("elegibles", len(elig), "elegidas", len(chosen), flush=True)

    freeze = C.TANDA1_FREEZE if tanda == 1 else C.PUB / "etapa1_tanda2_frozen.json"
    if OUT_SUFFIX and not FREEZE_CORR:
        # versión corregida (enmienda 1): nunca sustituye a la congelación original; solo propuesta
        freeze = C.PUB / f"etapa1_tanda{tanda}{OUT_SUFFIX}_candidate.json"
    elif OUT_SUFFIX:
        freeze = C.PUB / f"etapa1_tanda{tanda}{OUT_SUFFIX}_frozen.json"
        if freeze.exists():
            raise SystemExit(f"{freeze} ya existe: no se sobrescribe una congelación")
    elif freeze.exists():
        raise SystemExit(f"{freeze} ya existe: no se sobrescribe una congelación")
    sha = {f.name: hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
           for f in (tj, sj, C.HERE / "s4_etapa1.py", C.HERE / "fn_config.py")}
    sha[rows_out.name] = hashlib.sha256(rows_out.read_bytes()).hexdigest()
    freeze.write_text(json.dumps({"tanda": tanda, "frozen_at": pd.Timestamp.utcnow().isoformat(),
                                  "chosen_cells": sel["chosen_cells"], "models": models, "sha256": sha},
                                 indent=1, default=str), encoding="utf-8")
    print("congelado", freeze, flush=True)


if __name__ == "__main__":
    main()
