"""Etapa 2 — validación confirmatoria de UNA SOLA VEZ (preregistro v3 §6-§9, enmiendas 1 y 2, selección c2).

Contrastes (Bonferroni, preregistro §9: nivel por contraste = 0,05 / 5 = 0,01; intervalos al 99 %):
  H1-grandes, H1-medianas, H1-pequeñas (§6.3)
  C1: grandes / episodio Flow < −30 / 20 sesiones / todos los regímenes   (hipótesis principal de celda)
  C2: grandes / episodio Flow < −30 / 20 sesiones / lateral               (secundaria, ANIDADA en C1)

Modos
- `--rehearsal`: ensayo con las filas de DESARROLLO ya congeladas (etapa1_tanda{1,2}c2_rows.parquet). Solo prueba el
  código; los resultados están dentro de muestra y no significan nada. No abre ningún dato de prueba.
- `--rebuild-dev-check`: reconstruye con este código las filas de desarrollo de la tanda 1 y comprueba que son
  idénticas a las congeladas (el constructor de filas de la prueba es el mismo, con otro periodo).
- `--open-test --confirm "ABRO LA PRUEBA"`: la ejecución confirmatoria. Antes de leer nada:
  1. comprueba los hashes de data/etapa2_preparacion_freeze.json (incluido este fichero);
  2. se niega si ya existe una ejecución (una sola oportunidad);
  3. registra el acceso en data/etapa2_acceso.jsonl.
Las cifras, tablas y veredictos salen en data/etapa2_resultados.json (agregados; nada por empresa).
"""
import argparse
import gc
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ["FN_PANEL"] = "v4c2"
os.environ["FN_OUT"] = "c2"
os.environ["FN_CORR"] = "splits,identity,cik,spinoffs,jumps,terminals,missing_j"
os.environ.pop("FN_FREEZE", None)
for _s in (sys.stdout, sys.stderr):     # la consola de Windows (cp1252) no escribe «→»
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fn_config as C  # noqa: E402
import s4_etapa1 as S  # noqa: E402

ALPHA = 0.05 / 5
REPS = 2000
MIN_REL = 0.005                         # 0,5 pp (§6.3 y §7, este último × (H/20)^0,5)
H1_SIZES = ("large", "mid", "small")
DESCRIPTIVE_SIZES = ("micro", "unknown")
FREEZE = C.PUB / "etapa2_preparacion_freeze.json"
RESULTS = C.PUB / "etapa2_resultados.json"
ACCESS = C.PUB / "etapa2_acceso.jsonl"
TEST_ROWS = C.WORK / "etapa2_test_rows.parquet"      # fuera del repo, en el disco de datos
OUTCOME_CHUNKS = 10
CONFIRM = "ABRO LA PRUEBA"
RNG = np.random.default_rng(20261121)
# Complementos (2026-11-21, antes de abrir la prueba; no deciden nada): generador propio para que los intervalos
# confirmatorios sean idénticos con o sin ellos, y se calculan después de todo lo confirmatorio.
RNG_COMP = np.random.default_rng(20261122)
STRICT_MIN_REF = 10                     # comparadores mínimos por (mes, celda w1×m1) en la atribución estricta
STRICT_MIN_SHARE = 0.5                  # si se emparejan menos episodios, la atribución estricta es «no evaluable»
STRICT_MIN_DAYS = 10
RELATIVE_NOTE = ("Un exceso relativo positivo (frente a la media de su talla) no demuestra por sí solo una reversión "
                 "alcista rentable: puede ser positivo con rentabilidad absoluta negativa, o desaparecer tras costes.")


def frozen():
    t1 = json.loads((C.PUB / "etapa1_tanda1c2_frozen.json").read_text(encoding="utf-8"))
    t2 = json.loads((C.PUB / "etapa1_tanda2c2_frozen.json").read_text(encoding="utf-8"))
    cuts = json.loads((C.PUB / "v4_h1_frozen_cuts.json").read_text(encoding="utf-8"))
    models = {**t1["models"], **t2["models"]}
    cells = t2["chosen_cells"]
    sel1 = json.loads((C.PUB / "etapa1_tanda1c2_selection.json").read_text(encoding="utf-8"))
    dev = {(c["size"], c["X"], c["H"], c["regime"]): c for c in sel1["candidates"]}
    return models, cells, cuts, dev


# ── filas ──
def build_rows(period: str, tanda1_only=False) -> pd.DataFrame:
    """Mismo constructor que s4_etapa1.main (outcomes → label → excess), para las filas utilizables del periodo."""
    cols = ["company", "key", "date", "sector", "sector_src", "flow", "R", "w1", "m1", "raw_close", "adv20",
            "mcap_pit", "idx_now", "future_event_40", "size", "size_retro", "turnover", "usable", "operable"]
    p = pd.read_parquet(C.WORK / "panel_v4c2.parquet", columns=cols)
    p = p[p.usable].reset_index(drop=True)
    per = np.array([C.period_for(s, d) for s, d in zip(p["size"].astype(str), p["date"].astype(str))], dtype=object)
    p = p[per == period].reset_index(drop=True)
    if tanda1_only:
        p = p[p.date <= C.TANDA1_END].reset_index(drop=True)
    km = pd.read_parquet(C.WORK / "panel_v4c2.parquet", columns=["company", "key", "date"])
    km = km[km.company.isin(set(p.company))]
    last_key = km.sort_values("date").groupby("company").key.last().to_dict()
    paths = S.company_paths(km)
    term = S.terminal_by_company(set(p.company), last_key)
    p = p[p.company.isin(paths)].reset_index(drop=True)
    del km
    spins, jumps = S.corr_inputs(paths)
    # outcomes calcula cada fila con la ruta de su propia empresa: por tandas de empresas el resultado es el mismo y
    # la memoria (listas de Python por columna) cae a una fracción. Comprobado con --rebuild-dev-check.
    parts = []
    for ch in np.array_split(p.company.unique(), OUTCOME_CHUNKS):
        parts.append(S.outcomes(p[p.company.isin(set(ch))], paths, term, spins, jumps))
        gc.collect()
    p = pd.concat(parts).sort_index()
    del parts, paths
    gc.collect()
    spy = S.spy_frame()
    p = S.label(p, spy)
    p = S.excess(p, S.spy_returns(spy, p.date.unique()))
    return p


def analysis_columns(path):
    """Columnas que lee el análisis (run). Las demás (texto, auxiliares) no intervienen; leer solo estas cabe en memoria
    con el resto del equipo abierto. Si falta alguna, error: nunca un cálculo distinto en silencio."""
    cols = ["company", "date", "size", "size_retro", "flow", "R", "w1", "m1", "operable", "regime"]
    cols += [f"ep{X}" for X in S.XS]
    for H in S.HS:
        cols += [f"{b}{H}{s}" for b in ("r", "x") for s in ("", "_lo", "_hi")]
        cols += [f"{b}{H}" for b in ("rc", "mfe", "mae", "nl", "unkany", "xs", "xa", "xspy")]
    import pyarrow.parquet as pq
    have = set(pq.read_schema(path).names)
    miss = [c for c in cols if c not in have]
    if miss:
        raise SystemExit(f"faltan columnas en {path}: {miss}")
    return cols


def load_rows(paths):
    return pd.concat([pd.read_parquet(p, columns=analysis_columns(p)) for p in paths], ignore_index=True)


# ── estadística ──
def boot(y, block, alpha=ALPHA, rng=None):
    rng = RNG if rng is None else rng
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    n = len(y)
    if n < 10:
        return [np.nan, np.nan]
    b = min(block, n)
    nb = int(np.ceil(n / b))
    st = rng.integers(0, n, size=(REPS, nb))
    idx = (st[:, :, None] + np.arange(b)[None, None, :]) % n
    means = y[idx.reshape(REPS, -1)[:, :n]].mean(axis=1)
    return [float(v) for v in np.quantile(means, [alpha / 2, 1 - alpha / 2])]


def excl0(ci):
    return bool(ci[0] == ci[0] and (ci[0] > 0 or ci[1] < 0))


def cell_codes(d, cuts):
    return (np.searchsorted(cuts["w1_breaks"], d.w1, side="right").astype(str)
            + np.searchsorted(cuts["m1_breaks"], d.m1, side="right").astype(str))


def terciles(d, cuts):
    Rc = cuts["R_tercile_cuts_by_cell"]
    c1, c2 = d.cell.map(lambda c: Rc[c]["c1"]), d.cell.map(lambda c: Rc[c]["c2"])
    eq = c1 == c2
    low = np.where(eq, d.R < c1, d.R <= c1)
    high = np.where(eq, d.R > c1, d.R >= c2)
    return np.where(low, "low", np.where(high, "high", "mid"))


def h1(rows, size, models, cuts, H=20, pop="A", daily_cells=False, size_col="size", min_days_obs=30, xsrc=None):
    d = rows[(rows[size_col] == size) & (rows.flow < 0)]
    if xsrc is not None:        # cotas: mismo resultado que rows.assign(x20=rows[xsrc]) sin copiar la tabla entera
        d = d.copy()
        d[f"x{H}"] = d[xsrc]
    if pop == "B":
        d = d[d.operable]
    d = d.dropna(subset=["w1", "m1", "R", f"x{H}"]).copy()
    if not len(d):
        return {"n": 0}
    d["cell"] = cell_codes(d, cuts)
    d["terc"] = terciles(d, cuts)
    d["unit"] = d.date if daily_cells else d.date.str[:7]
    mins = 10
    g = d.groupby(["unit", "cell"])
    st = g.apply(lambda x: pd.Series({"n": len(x), "nl": int((x.terc == "low").sum()), "nh": int((x.terc == "high").sum()),
                                      "dc": x.loc[x.terc == "high", f"x{H}"].mean() - x.loc[x.terc == "low", f"x{H}"].mean()}),
                 include_groups=False).reset_index()
    st = st[(st.nl >= mins) & (st.nh >= mins)]
    Dm = st.groupby("unit").apply(lambda x: np.average(x.dc, weights=x.n), include_groups=False) if len(st) else pd.Series(dtype=float)
    out = {"n": int(len(d)), "units_valid": int(len(Dm)), "D": float(Dm.mean()) if len(Dm) else np.nan}
    blocks = (60, 20, 120) if daily_cells else (3, 1, 6)
    out["D_ci"] = boot(Dm.to_numpy(), blocks[0])
    out["D_ci_sens"] = {str(b): boot(Dm.to_numpy(), b) for b in blocks[1:]}
    if size not in models:          # micro y «sin capitalización»: solo descriptivas, sin M0/M1 congelados
        out["verdict"] = "descriptiva (sin veredicto)"
        return out
    m = models[size]
    p0 = d.cell.map(m["M0"]).astype(float)
    p1 = p0 + d.terc.map(m["M1_tercile_effect"]).astype(float)
    d["p0"], d["p1"] = p0, p1
    ics = []
    for day, x in d.groupby("date"):
        if len(x) < min_days_obs:
            continue
        i0 = spearmanr(x.p0, x[f"x{H}"]).statistic if x.p0.nunique() > 1 else np.nan
        i1 = spearmanr(x.p1, x[f"x{H}"]).statistic if x.p1.nunique() > 1 else np.nan
        ics.append((day, i0, i1))
    ic = pd.DataFrame(ics, columns=["date", "ic0", "ic1"]).dropna()
    dic = (ic.ic1 - ic.ic0).to_numpy()
    out.update({"ic_days": int(len(ic)), "IC0": float(ic.ic0.mean()) if len(ic) else np.nan,
                "IC1": float(ic.ic1.mean()) if len(ic) else np.nan, "dIC": float(dic.mean()) if len(dic) else np.nan,
                "dIC_ci": boot(dic, 60), "dIC_ci_sens": {"20": boot(dic, 20), "120": boot(dic, 120)},
                "dIC_t_nw": float(S.nw_t(dic, H)[1]) if len(dic) > 2 else np.nan})
    dok = abs(out["D"]) >= MIN_REL and excl0(out["D_ci"])
    iok = out["dIC"] > 0 and excl0(out["dIC_ci"])
    out["verdict"] = "confirmado" if dok and iok else ("evidencia parcial" if dok or iok else "no confirmado")
    out["fragile"] = any(not excl0(v) for v in list(out["D_ci_sens"].values()) + list(out["dIC_ci_sens"].values())) \
        if dok and iok else None
    return out


def cell_test(rows, c, dev, cuts, H=None, pop="A", col="x", restrict=None):
    H = H or c["H"]
    sz, X, reg = c["size"], c["X"], c["regime"]
    base = rows[rows["size"] == sz]
    if restrict is not None:
        base = base[restrict(base)]
    if pop == "B":
        base = base[base.operable]
    g = base[base[f"ep{X}"]]
    if reg != "all":
        g = g[g.regime == reg]
    g = g.dropna(subset=[f"{col}{H}"])
    if not len(g):
        return {"n": 0}
    ser = S.daily(g, f"{col}{H}")
    m, t = S.nw_t(ser.to_numpy(), H)
    out = {"n": int(len(g)), "companies": int(g.company.nunique()), "days": int(len(ser)),
           "weeks": int(pd.to_datetime(g.date).dt.to_period("W").nunique()), "x_daily_mean": float(m), "t_nw": float(t),
           "ci": boot(ser.to_numpy(), 60), "ci_sens": {"20": boot(ser.to_numpy(), 20), "120": boot(ser.to_numpy(), 120)}}
    if col == "x":
        out["x_lo"], out["x_hi"] = float(S.daily(g, f"x{H}_lo").mean()), float(S.daily(g, f"x{H}_hi").mean())
        out["unknown_share"] = float(g[f"unkany{H}"].mean())
        out["sens_jumps_as_is"] = float(S.daily(g, f"xs{H}").mean()) if f"xs{H}" in g else None
        out["sens_jumps_annulled"] = float(S.daily(g, f"xa{H}").mean()) if f"xa{H}" in g else None
    return out


def attribution(rows, c, cuts):
    """Señal frente a días SIN esa señal de la misma (talla, mes, quintil w1, quintil m1) (§7)."""
    H, sz, X, reg = c["H"], c["size"], c["X"], c["regime"]
    d = rows[(rows["size"] == sz)].dropna(subset=["w1", "m1", f"x{H}"]).copy()
    d["cell"] = cell_codes(d, cuts)
    d["mo"] = d.date.str[:7]
    sig = d[f"ep{X}"] & ((d.regime == reg) if reg != "all" else True)
    ref = d[~d[f"ep{X}"]].groupby(["mo", "cell"])[f"x{H}"].mean()
    s = d[sig].copy()
    s["ref"] = [ref.get((a, b), np.nan) for a, b in zip(s.mo, s.cell)]
    s["diff"] = s[f"x{H}"] - s["ref"]
    ser = S.daily(s.dropna(subset=["diff"]), "diff")
    m, t = S.nw_t(ser.to_numpy(), H)
    nl_sig = float(s[f"nl{H}"].astype(float).mean())
    nl_ref = float(d[~d[f"ep{X}"]][f"nl{H}"].astype(float).mean())
    return {"n_matched": int(s["diff"].notna().sum()), "diff_daily_mean": float(m), "t_nw": float(t),
            "ci": boot(ser.to_numpy(), 60), "new_low_signal": nl_sig, "new_low_reference": nl_ref,
            "p10_signal": float(s[f"r{H}"].quantile(.10)), "p10_reference": float(d[~d[f"ep{X}"]][f"r{H}"].quantile(.10))}


def classify(res, c, dev_sign):
    H = c["H"]
    thr = MIN_REL * (H / 20) ** 0.5
    m = res["main"]
    same = np.sign(m["x_daily_mean"]) == dev_sign
    conf = bool(same and abs(m["x_daily_mean"]) >= thr and excl0(m["ci"]))
    bounds_ok = bool(np.sign(m["x_lo"]) == np.sign(m["x_hi"]) == np.sign(m["x_daily_mean"]))
    a = res["attribution"]
    attr = bool(np.sign(a["diff_daily_mean"]) == np.sign(m["x_daily_mean"]) and excl0(a["ci"]))
    net = res["pop_B_net"]
    fragile = conf and any(not excl0(v) for v in m["ci_sens"].values())
    if conf and m["x_daily_mean"] > 0 and attr and net > 0 and bounds_ok:
        reading = "reversión (posible oportunidad)"
    elif conf and m["x_daily_mean"] < 0 and bounds_ok:
        reading = "continuación bajista (peligro)"
    else:
        reading = "descripción de la caída"
    return {"confirmed": conf, "threshold": thr, "same_sign_as_dev": bool(same), "bounds_same_sign": bounds_ok,
            "attribution": attr, "pop_B_net_positive": bool(net > 0), "fragile": bool(fragile), "reading": reading}


# ── complementos (no deciden nada; se publican junto a lo confirmatorio) ──
def attribution_strict(rows, c, cuts, min_ref=STRICT_MIN_REF):
    """Atribución estricta: señal frente a días SIN la señal de la misma talla, mes, quintil w1, quintil m1 Y del mismo
    régimen que la celda. Cada grupo de referencia necesita ≥ min_ref observaciones; los episodios sin grupo suficiente
    quedan fuera y se cuentan. Si se emparejan < 50 % de los episodios o < 10 días, «no evaluable»."""
    H, sz, X, reg = c["H"], c["size"], c["X"], c["regime"]
    d = rows[(rows["size"] == sz)].dropna(subset=["w1", "m1", f"x{H}"]).copy()
    if reg != "all":
        d = d[d.regime == reg]
    d["cell"] = cell_codes(d, cuts)
    d["mo"] = d.date.str[:7]
    g = d[~d[f"ep{X}"]].groupby(["mo", "cell"])[f"x{H}"]
    ref, cnt = g.mean(), g.count()
    s = d[d[f"ep{X}"]].copy()
    keys = list(zip(s.mo, s.cell))
    s["nref"] = [int(cnt.get(k, 0)) for k in keys]
    s["ref"] = [ref.get(k, np.nan) if cnt.get(k, 0) >= min_ref else np.nan for k in keys]
    s["diff"] = s[f"x{H}"] - s["ref"]
    ok = s.dropna(subset=["diff"])
    ser = S.daily(ok, "diff")
    share = float(len(ok) / len(s)) if len(s) else np.nan
    out = {"definition": f"referencia = talla {sz}, sin ep{X}, régimen {reg}, mismo mes y celda w1×m1; "
                         f"≥ {min_ref} comparadores por grupo",
           "n_signal": int(len(s)), "n_matched": int(len(ok)), "share_matched": share, "days": int(len(ser)),
           "median_comparators": float(s.nref.median()) if len(s) else np.nan}
    if not len(s) or share < STRICT_MIN_SHARE or len(ser) < STRICT_MIN_DAYS:
        out["status"] = "no evaluable (comparadores insuficientes)"
        return out
    m, t = S.nw_t(ser.to_numpy(), H)
    ci = boot(ser.to_numpy(), 60, rng=RNG_COMP)
    out.update({"status": "evaluable", "diff_daily_mean": float(m), "t_nw": float(t), "ci99": ci,
                "excludes_0": excl0(ci)})
    return out


def absolute_block(rows, c, pop="A", restrict=None):
    """Rentabilidad absoluta y relativa, bruta y neta de costes, por episodio y por media diaria; aciertos; MAE/MFE."""
    H, sz, X, reg = c["H"], c["size"], c["X"], c["regime"]
    cost = C.COST_ROUND_TRIP[sz]
    base = rows[rows["size"] == sz]
    if restrict is not None:
        base = base[restrict(base)]
    if pop == "B":
        base = base[base.operable]
    g = base[base[f"ep{X}"]]
    if reg != "all":
        g = g[g.regime == reg]
    g = g.dropna(subset=[f"r{H}", f"x{H}"])
    if not len(g):
        return {"n": 0}
    r, x, mae, mfe = g[f"r{H}"], g[f"x{H}"], g[f"mae{H}"], g[f"mfe{H}"]
    rd, xd = S.daily(g, f"r{H}").to_numpy(), S.daily(g, f"x{H}").to_numpy()
    return {"n": int(len(g)), "cost_round_trip": cost,
            "abs_gross": {"mean": float(r.mean()), "median": float(r.median()), "daily_mean": float(rd.mean()),
                          "daily_ci99": boot(rd, 60, rng=RNG_COMP), "lo_bound_mean": float(g[f"r{H}_lo"].mean()),
                          "hi_bound_mean": float(g[f"r{H}_hi"].mean()), "share_pos": float((r > 0).mean())},
            "abs_net": {"mean": float(r.mean() - cost), "median": float(r.median() - cost),
                        "daily_mean": float(rd.mean() - cost), "share_pos": float((r - cost > 0).mean())},
            "rel_gross": {"mean": float(x.mean()), "median": float(x.median()), "daily_mean": float(xd.mean()),
                          "share_pos": float((x > 0).mean())},
            "rel_net": {"mean": float(x.mean() - cost), "median": float(x.median() - cost),
                        "daily_mean": float(xd.mean() - cost), "share_pos": float((x - cost > 0).mean())},
            "vs_spy_gross_mean": float(g[f"xspy{H}"].mean()),
            "mae": {"mean": float(mae.mean()), "median": float(mae.median()), "p10": float(mae.quantile(.10)),
                    "share_le_m10": float((mae <= -0.10).mean()), "share_le_m20": float((mae <= -0.20).mean())},
            "mfe": {"mean": float(mfe.mean()), "median": float(mfe.median())}}


def complements(rows, cells, cuts, W):
    clean = W["_common_clean_from"]
    out = {"note": RELATIVE_NOTE, "decides_nothing": True, "cells": {}}
    for c in cells:
        key = f"{c['size']}|{c['X']}|{c['H']}|{c['regime']}"
        r = {"absolute_pop_A": absolute_block(rows, c), "absolute_pop_B": absolute_block(rows, c, pop="B"),
             "absolute_from_common_clean": absolute_block(rows, c, restrict=lambda b: b.date >= clean)}
        if c["regime"] != "all":
            r["attribution_strict"] = attribution_strict(rows, c, cuts)
            r["attribution_strict_sens_min1"] = attribution_strict(rows, c, cuts, min_ref=1)
        out["cells"][key] = r
    return out


# ── fechas de prueba, solapes y periodo común ──
def windows():
    spy = S.spy_frame()
    days = list(spy.date)
    pos = {d: i for i, d in enumerate(days)}

    def plus(d, k):
        i = max(j for j, x in enumerate(days) if x <= d)
        return days[min(i + k, len(days) - 1)]
    out = {}
    for sz in C.SIZES:
        dev_end = C.DEV_END_BY_SIZE[sz]
        out[sz] = {"dev": [C.DEV_START, dev_end], "test": [C.TEST_START_BY_SIZE[sz], C.LAST_SIGNAL],
                   "last_price_seen_by_dev": plus(dev_end, 40)}
    common = max(v["last_price_seen_by_dev"] for v in out.values())
    out["_common_clean_from"] = days[pos[common] + 1]
    return out


def run(rows, mode):
    models, cells, cuts, dev = frozen()
    W = windows()
    res = {"mode": mode, "alpha_per_contrast": ALPHA, "contrasts": 5, "windows": W, "H1": {}, "cells": {},
           "descriptive": {}, "sensitivities": {}}
    clean = W["_common_clean_from"]
    for sz in H1_SIZES:
        res["H1"][sz] = h1(rows, sz, models, cuts)
        sens = {"pop_B": h1(rows, sz, models, cuts, pop="B"),
                "daily_cells_min10": h1(rows, sz, models, cuts, daily_cells=True),
                "size_retro": h1(rows, sz, models, cuts, size_col="size_retro"),
                "bound_lo": h1(rows, sz, models, cuts, xsrc="x20_lo"),
                "bound_hi": h1(rows, sz, models, cuts, xsrc="x20_hi")}
        for H in (5, 10, 40):
            sens[f"H{H}"] = h1(rows, sz, models, cuts, H=H)
        if sz in ("large", "mid"):
            own = W[sz]["last_price_seen_by_dev"]
            sens["excl_overlap_own_dev"] = h1(rows[rows.date > own], sz, models, cuts)
            sens["before_common_clean"] = h1(rows[rows.date < clean], sz, models, cuts)
            sens["from_common_clean"] = h1(rows[rows.date >= clean], sz, models, cuts)
        res["sensitivities"][f"H1_{sz}"] = sens
    for sz in DESCRIPTIVE_SIZES:
        res["descriptive"][f"H1_{sz}"] = h1(rows, sz, models, cuts)
    for H in sorted({c["H"] for c in cells}):       # entrada al cierre de t+1: misma columna que antes, sin copiar
        rows[f"xc{H}"] = rows[f"rc{H}"] - rows.groupby(["date", "size"])[f"rc{H}"].transform("mean")
    for c in cells:
        key = f"{c['size']}|{c['X']}|{c['H']}|{c['regime']}"
        dv = dev[(c["size"], c["X"], c["H"], c["regime"])]
        main = cell_test(rows, c, dev, cuts)
        B = cell_test(rows, c, dev, cuts, pop="B")
        net = B.get("x_daily_mean", np.nan) - C.COST_ROUND_TRIP[c["size"]]
        r = {"main": main, "attribution": attribution(rows, c, cuts), "pop_B": B, "pop_B_net": float(net),
             "dev": {k: dv[k] for k in ("n", "weeks", "x_daily_mean", "t_nw")}}
        r["classification"] = classify(r, c, np.sign(dv["x_daily_mean"]))
        own = W[c["size"]]["last_price_seen_by_dev"]
        r["sensitivities"] = {
            **{f"H{H}": cell_test(rows, c, dev, cuts, H=H) for H in (5, 10, 40) if H != c["H"]},
            "entry_close_t1": cell_test(rows, c, dev, cuts, col="xc"),
            "costs_x2_net": float(B.get("x_daily_mean", np.nan) - 2 * C.COST_ROUND_TRIP[c["size"]]),
            "costs_x3_net": float(B.get("x_daily_mean", np.nan) - 3 * C.COST_ROUND_TRIP[c["size"]]),
            "excl_overlap_own_dev": cell_test(rows, c, dev, cuts, restrict=lambda b: b.date > own),
            "before_common_clean": cell_test(rows, c, dev, cuts, restrict=lambda b: b.date < clean),
            "from_common_clean": cell_test(rows, c, dev, cuts, restrict=lambda b: b.date >= clean)}
        res["cells"][key] = r
    res["dependence_note"] = ("La celda lateral está anidada en la de todos los regímenes: sus episodios son un "
                              "subconjunto. Si ambas pasan, es un único hallazgo, no dos; la lateral no prueba una "
                              "ventaja propia del mercado lateral.")
    # después de todo lo confirmatorio y con su propio generador: no altera ninguna cifra anterior
    res["complementary"] = complements(rows, cells, cuts, W)
    return res


# ── preparación: hashes ──
def sha(p: Path, text=False):
    b = p.read_bytes()
    return hashlib.sha256(b.replace(b"\r\n", b"\n") if text else b).hexdigest()


def manifest_files():
    repo = ["s9_etapa2.py", "s4_etapa1.py", "fn_config.py", "data/etapa1_tanda1c2_frozen.json",
            "data/etapa1_tanda2c2_frozen.json", "data/etapa1_tanda1c2_selection.json",
            "data/etapa1_tanda2c2_selection.json", "data/v4_h1_frozen_cuts.json", "data/version_c2_freeze.json",
            "data/enmienda1_freeze.json", "data/enmienda2_freeze.json", "data/preregistro_v3_freeze.json",
            "data/terminal_events_v4.csv", "data/corr1_splits.csv", "data/corr1_identity.csv", "data/corr1_cik.csv",
            "data/corr1_cik_ranges.csv", "data/corr1_spinoffs.csv", "data/corr1_jumps.csv",
            "data/etapa2_preparacion_freeze_v1.json", "data/etapa2_preparacion_freeze_v2.json",
            "data/etapa2_preparacion_freeze_v3.json", "data/etapa2_preparacion_freeze_v4.json",
            "ETAPA2_PREPARACION.md"]
    ext = ["work/panel_v4c2.parquet", "work/etapa1_tanda1c2_rows.parquet", "work/etapa1_tanda2c2_rows.parquet"]
    return repo, ext


def write_freeze():
    if FREEZE.exists():
        raise SystemExit(f"{FREEZE} ya existe: no se sobrescribe")
    repo, ext = manifest_files()
    m = {"frozen_at": pd.Timestamp.now("UTC").isoformat(),
         "repo": {f: sha(C.HERE / f, text=True) for f in repo},
         "external": {f: sha(C.DATA / f) for f in ext}}
    FREEZE.write_text(json.dumps(m, indent=1), encoding="utf-8")
    print("congelado", FREEZE)


def verify_freeze():
    m = json.loads(FREEZE.read_text(encoding="utf-8"))
    bad = [f for f, h in m["repo"].items() if sha(C.HERE / f, text=True) != h]
    bad += [f for f, h in m["external"].items() if sha(C.DATA / f) != h]
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehearsal", action="store_true")
    ap.add_argument("--rebuild-dev-check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--open-test", action="store_true")
    ap.add_argument("--confirm")
    a = ap.parse_args()
    if a.freeze:
        return write_freeze()
    if a.verify:
        bad = verify_freeze()
        print("OK" if not bad else f"DIFERENCIAS: {bad}")
        return
    if a.rehearsal:
        rows = load_rows([C.WORK / "etapa1_tanda1c2_rows.parquet", C.WORK / "etapa1_tanda2c2_rows.parquet"])
        assert all(C.period_for(s, d) == "dev" for s, d in rows[["size", "date"]].drop_duplicates().itertuples(index=False))
        res = run(rows, "rehearsal_dev_in_sample")
        p = C.PUB / "etapa2_ensayo_desarrollo.json"
        p.write_text(json.dumps(res, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
        print("ensayo (dentro de muestra, sin valor) →", p)
        return
    if a.rebuild_dev_check:
        tmp = C.WORK / "etapa2_rebuild_dev_rows.parquet"
        build_rows("dev", tanda1_only=True).to_parquet(tmp)       # mismo paso por parquet que las congeladas
        new = pd.read_parquet(tmp)
        old = pd.read_parquet(C.WORK / "etapa1_tanda1c2_rows.parquet")
        cols = list(old.columns)
        same_cols = sorted(cols) == sorted(new.columns)
        m = old.merge(new[cols], on=["company", "date"], how="outer", suffixes=("", "__n"), indicator=True)
        diffs = {}
        for c in cols:
            if c in ("company", "date"):
                continue
            a_, b_ = m[c], m[f"{c}__n"]
            if pd.api.types.is_numeric_dtype(a_) and pd.api.types.is_numeric_dtype(b_):
                av, bv = a_.to_numpy(float), b_.to_numpy(float)
                bad = ~(np.isclose(av, bv, rtol=1e-12, atol=0) | (np.isnan(av) & np.isnan(bv)))
            else:
                bad = ~((a_ == b_) | (a_.isna() & b_.isna()))
            if bad.any():
                diffs[c] = int(bad.sum())
        out = {"rows_old": len(old), "rows_new": len(new), "same_columns": same_cols,
               "only_old": int((m["_merge"] == "left_only").sum()), "only_new": int((m["_merge"] == "right_only").sum()),
               "cols_with_diffs": diffs, "identical": bool(same_cols and not diffs and (m["_merge"] == "both").all())}
        (C.PUB / "etapa2_rebuild_dev_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(out)
        return
    if a.open_test:
        if a.confirm != CONFIRM:
            raise SystemExit(f'Falta --confirm "{CONFIRM}"')
        if RESULTS.exists():
            raise SystemExit(f"{RESULTS} ya existe: la etapa 2 es de una sola oportunidad")
        bad = verify_freeze()
        if bad:
            raise SystemExit(f"Hashes distintos de la congelación de preparación: {bad}")
        with ACCESS.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": pd.Timestamp.now("UTC").isoformat(), "event": "open_test",
                                "freeze_sha": sha(FREEZE)}) + "\n")
        t0 = time.time()
        # Las filas de prueba se guardan y se releen en limpio (menos memoria; el paso por parquet no cambia nada,
        # ver --rebuild-dev-check). Si una ejecución anterior las construyó y murió SIN escribir resultados, se
        # reutilizan solo si su hash coincide con el registrado en el acceso.
        built = [json.loads(l) for l in ACCESS.read_text(encoding="utf-8").splitlines() if '"rows_built"' in l]
        if TEST_ROWS.exists() and built and sha(TEST_ROWS) == built[-1]["rows_sha"]:
            with ACCESS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": pd.Timestamp.now("UTC").isoformat(), "event": "rows_reused",
                                    "rows_sha": built[-1]["rows_sha"]}) + "\n")
        else:
            build_rows("test").to_parquet(TEST_ROWS)
            gc.collect()
            with ACCESS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": pd.Timestamp.now("UTC").isoformat(), "event": "rows_built",
                                    "rows_sha": sha(TEST_ROWS)}) + "\n")
        gc.collect()
        rows = load_rows([TEST_ROWS])
        res = run(rows, "test_confirmatory")
        res["rows"] = int(len(rows))
        res["seconds"] = round(time.time() - t0, 1)
        RESULTS.write_text(json.dumps(res, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
        with ACCESS.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": pd.Timestamp.now("UTC").isoformat(), "event": "done",
                                "results_sha": sha(RESULTS)}) + "\n")
        print("hecho →", RESULTS)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
