"""E2 — calibración y caracterización del registro de eventos (sobre e2_compute.py + e2_normalize.py).

Solo describe: frecuencias, redundancia, persistencia, simultaneidad, episodios, estabilidad. Ningún resultado
posterior a los eventos, ninguna puntuación predictiva (E2_AUTORIZACION.md §1, §5).

Elegibles (denominador): pertenencia verificada al S&P 500 ese día, perfil con ≥ 30 sesiones, sin caída de datos de
mercado, y para cada medida valor finito y ≥ 30 valores en su línea base. Calibración: 2016-01-04 a 2019-12-31.
Comprobación de estabilidad: 2020-01-02 a 2021-10-28, SIN reajustar nada.

Calibración de M1 y M2: para cada familia, un único cuantil q común a sus medidas tal que el 2 % de los valor-días
elegibles de calibración tenga al menos una marca de esa familia. Es una ORIENTACIÓN para fijar umbrales en 2016-2019,
no una cuota: los umbrales se fijan una vez (por medida, en unidades de su propia dispersión) y en días de estrés
pueden marcar muchos valores a la vez.

Salidas (MICRO_DATA_DIR/results): e2_report.json, e2_alerts_<método>.parquet, e2_lab_sample.csv.
Uso: py -3 e2_analyze.py
"""
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import event_catalog as cat, sectors, sessions, storage  # noqa: E402
import e2_normalize as N  # noqa: E402

warnings.simplefilter("ignore", RuntimeWarning)
ROOT = storage.root()
MEAS, NORM, RES = ROOT / "features" / "e2_measures", ROOT / "features" / "e2_norm", ROOT / "results"
CALIB_END, VALID_START, E2_LAST = "2019-12-31", "2020-01-02", "2021-10-28"
MIN_N, FAMILY_TARGET, MAD_FLOOR_PCT = 30, 0.02, 10
SPLIT_WINDOW_SESSIONS = 60
MARKET_WIDE = 0.10
SEED = 20261121
META = ["entity", "symbol", "date", "cov", "prof_n", "member", "early_close", "corp_event", "split_day", "outage",
        "liq", "longest_gap", "dollar_vol"]


def segment_of(m: str) -> str:
    if m.startswith("PRE_"):
        return "pre"
    if m.startswith("C3_"):
        return "post"
    if m in ("V3_open_est", "C5_gap"):
        return "open_auction"
    if m == "V3_close_est":
        return "close_auction"
    return "continuous"


def family_of(m: str) -> str:
    code = cat.MEASURE_CODE.get(m)
    return cat.BY_CODE[code].family if code in cat.BY_CODE else "?"


def k_of(m: str) -> int:
    for p in ("D1_", "V1_"):
        if m.startswith(p):
            return int(m.split("_")[1])
    if m.startswith(("I1", "I2", "I3", "V2")):
        return 15
    if m.startswith("P2_er"):
        return int(m[5:7])
    return 1


# ── carga ──
def load():
    dm = ds.dataset(str(MEAS), format="parquet")
    names = sorted({c[:-3] for c in dm.schema.names if c.endswith("__v")})
    cols = META + [f"{m}__v" for m in names] + [f"{m}__p" for m in names if f"{m}__p" in dm.schema.names] + \
        [f"{m}__s" for m in names if f"{m}__s" in dm.schema.names]
    A = dm.to_table(columns=cols).to_pandas()
    dn = ds.dataset(str(NORM), format="parquet")
    ncols = ["entity", "date"] + [f"{m}__{s}" for m in names for s in ("n", "m0f", "m0zonly", "m0z", "mad0", "m1dev", "m1mad", "m2")]
    B = dn.to_table(columns=ncols).to_pandas()
    df = A.merge(B, on=["entity", "date"], how="left", validate="one_to_one")
    df = df.sort_values(["entity", "date"]).reset_index(drop=True)
    return df, names


def base_mask(df):
    return df["member"].astype(bool) & (df["prof_n"] >= MIN_N) & ~df["outage"].astype(bool)


def split_window(df):
    """Sesiones (de la propia entidad) desde el último split aplicado; True si < SPLIT_WINDOW_SESSIONS."""
    out = np.zeros(len(df), bool)
    for _, g in df.groupby("entity", sort=False):
        sd = g["split_day"].to_numpy(bool)
        if not sd.any():
            continue
        last = -10 ** 9
        for k, (i, s) in enumerate(zip(g.index, sd)):
            if s:
                last = k
            out[i] = (k - last) < SPLIT_WINDOW_SESSIONS
    return out


# ── calibración ──
def calibrate(df, names, elig, calib, scores_by_method):
    """Para M1 y M2: umbral por medida = cuantil q de su puntuación en calibración, q común por familia."""
    fams = {}
    for m in names:
        fams.setdefault(family_of(m), []).append(m)
    out = {}
    for meth, S in scores_by_method.items():
        thr, qfam = {}, {}
        for f, ms in fams.items():
            cal_rows = calib & elig["__day"]
            vals = {m: S[m][cal_rows & elig[m]] for m in ms}

            def rate(q):
                t = {m: np.nanquantile(vals[m], q) if len(vals[m]) else np.inf for m in ms}
                any_ = np.zeros(int(cal_rows.sum()), bool)
                sub = {m: (S[m][cal_rows] >= t[m]) & elig[m][cal_rows] for m in ms}
                for m in ms:
                    any_ |= sub[m]
                return any_.mean(), t
            lo, hi = 0.90, 0.999999
            for _ in range(30):
                mid = (lo + hi) / 2
                r, t = rate(mid)
                if r > FAMILY_TARGET:
                    lo = mid
                else:
                    hi = mid
            r, t = rate(hi)
            qfam[f] = {"q": hi, "calib_family_rate": round(float(r), 5)}
            thr.update(t)
        out[meth] = {"thresholds": {m: float(v) for m, v in thr.items()}, "family_q": qfam}
    return out


def main():
    t0 = time.time()
    df, names = load()
    elig_day = base_mask(df).to_numpy()
    calib = (df["date"] <= CALIB_END).to_numpy()
    valid = ((df["date"] >= VALID_START) & (df["date"] <= E2_LAST)).to_numpy()
    year = df["date"].str[:4].to_numpy()
    sw = split_window(df)
    elig = {"__day": elig_day}
    for m in names:
        elig[m] = elig_day & np.isfinite(df[f"{m}__v"].to_numpy(float)) & (df[f"{m}__n"].to_numpy() >= MIN_N)
    # liquidez: tercil transversal del día entre elegibles
    liq_t = np.full(len(df), "", dtype=object)
    sub = df.loc[elig_day, ["date", "liq"]]
    liq_t[elig_day] = sub.groupby("date")["liq"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["baja", "media", "alta"]) if len(s) >= 3 else "media").astype(str).to_numpy()

    # puntuaciones
    floors = {}
    S1, S2, F0 = {}, {}, {}
    for m in names:
        mad = df[f"{m}__m1mad"].to_numpy(float)
        cm = calib & elig[m] & (mad > 0)
        floors[m] = float(np.nanpercentile(mad[cm], MAD_FLOOR_PCT)) if cm.any() else 1e-9
        S1[m] = df[f"{m}__m1dev"].to_numpy(float) / np.maximum(np.nan_to_num(mad, nan=0.0), floors[m])
        S2[m] = df[f"{m}__m2"].to_numpy(float)
        F0[m] = df[f"{m}__m0f"].to_numpy(bool)
    cal = calibrate(df, names, elig, calib, {"M1": S1, "M2": S2})
    flags = {"M0": {m: F0[m] & elig[m] for m in names},
             "M1": {m: (S1[m] >= cal["M1"]["thresholds"][m]) & elig[m] for m in names},
             "M2": {m: (S2[m] >= cal["M2"]["thresholds"][m]) & elig[m] for m in names}}

    rep = {"generated_utc": pd.Timestamp.now("UTC").isoformat(), "rows": int(len(df)), "entities": int(df["entity"].nunique()),
           "eligible_valor_days": {"calib": int((elig_day & calib).sum()), "valid": int((elig_day & valid).sum())},
           "params": {"min_n": MIN_N, "family_target": FAMILY_TARGET, "mad_floor_pct": MAD_FLOOR_PCT,
                      "split_window_sessions": SPLIT_WINDOW_SESSIONS, "market_wide": MARKET_WIDE},
           "mad_floors": floors, "calibration": cal, "methods": {}}
    fams = sorted({family_of(m) for m in names})
    segs = sorted({segment_of(m) for m in names})
    mad0 = {m: df[f"{m}__mad0"].to_numpy(float) for m in names}
    small_mad = {m: mad0[m] <= np.nanpercentile(mad0[m][calib & elig[m]], 10) if (calib & elig[m]).any() else
                 np.zeros(len(df), bool) for m in names}
    dates = df["date"].to_numpy()
    ent = df["entity"].to_numpy()
    for meth, Fm in flags.items():
        R = {}
        R["per_measure"] = {m: {
            "family": family_of(m), "segment": segment_of(m),
            "rate_calib": round(float(Fm[m][calib & elig[m]].mean()), 5),
            "rate_valid": round(float(Fm[m][valid & elig[m]].mean()), 5),
            "by_year": {y: round(float(Fm[m][(year == y) & elig[m]].mean()), 5) for y in sorted(set(year)) if ((year == y) & elig[m]).any()},
            "share_small_mad": round(float(small_mad[m][Fm[m]].mean()), 4) if Fm[m].any() else None,
            "share_zonly": round(float(df[f"{m}__m0zonly"].to_numpy(bool)[Fm[m]].mean()), 4) if meth == "M0" and Fm[m].any() else None,
            "n_flags": int(Fm[m].sum())} for m in names}
        anyf = {f: np.zeros(len(df), bool) for f in fams}
        anys = {s: np.zeros(len(df), bool) for s in segs}
        for m in names:
            anyf[family_of(m)] |= Fm[m]
            anys[segment_of(m)] |= Fm[m]
        any_all = np.zeros(len(df), bool)
        for f in fams:
            any_all |= anyf[f]
        ed = elig_day
        R["valor_day"] = {
            "any_flag": {"calib": round(float(any_all[ed & calib].mean()), 4), "valid": round(float(any_all[ed & valid].mean()), 4),
                         "by_year": {y: round(float(any_all[ed & (year == y)].mean()), 4) for y in sorted(set(year[ed]))}},
            "family": {f: {"calib": round(float(anyf[f][ed & calib].mean()), 4), "valid": round(float(anyf[f][ed & valid].mean()), 4),
                           "by_year": {y: round(float(anyf[f][ed & (year == y)].mean()), 4) for y in sorted(set(year[ed]))},
                           "by_liquidity": {t: round(float(anyf[f][ed & (liq_t == t)].mean()), 4) for t in ("baja", "media", "alta")}}
                       for f in fams},
            "segment": {s: {"calib": round(float(anys[s][ed & calib].mean()), 4), "valid": round(float(anys[s][ed & valid].mean()), 4)}
                        for s in segs},
            "mean_flags_per_flagged_day": round(float(sum(Fm[m].astype(int) for m in names)[any_all].mean()), 2) if any_all.any() else None}
        # simultaneidad por familia: fracción de valores elegibles del día con marca
        simul = {}
        for f in fams:
            s = pd.DataFrame({"date": dates[ed], "x": anyf[f][ed]}).groupby("date")["x"].mean()
            wide = s[s >= MARKET_WIDE]
            flagged_on_wide = anyf[f][ed & np.isin(dates, wide.index)].sum() / max(1, anyf[f][ed].sum())
            simul[f] = {"day_share_median": round(float(s.median()), 4), "day_share_p95": round(float(s.quantile(.95)), 4),
                        "day_share_max": round(float(s.max()), 4), "max_day": s.idxmax(),
                        "days_market_wide": int(len(wide)), "share_flags_on_market_wide_days": round(float(flagged_on_wide), 4),
                        "top_days": {d: round(float(v), 3) for d, v in s.sort_values(ascending=False).head(8).items()}}
        R["simultaneity"] = simul
        # persistencia: marca de la misma medida en la sesión anterior de la entidad
        pers = {}
        same_ent_prev = np.r_[False, ent[1:] == ent[:-1]]
        for m in names:
            f_ = Fm[m]
            prev = np.r_[False, f_[:-1]] & same_ent_prev
            base_r = f_[elig[m]].mean()
            cond = f_[elig[m] & prev].mean() if (elig[m] & prev).any() else np.nan
            pers[m] = {"p_flag": round(float(base_r), 5), "p_flag_given_prev": round(float(cond), 4) if cond == cond else None,
                       "lift": round(float(cond / base_r), 2) if base_r and cond == cond else None}
        R["persistence"] = pers
        # calidad del dato
        q = {}
        for nm_, mask in (("corp_event", df["corp_event"].to_numpy(bool)), ("early_close", df["early_close"].to_numpy(bool)),
                          ("post_split_window", sw), ("low_coverage", (df["cov"] < 0.8).to_numpy())):
            q[nm_] = {"share_valor_days": round(float(mask[ed].mean()), 4),
                      "rate_any_flag_inside": round(float(any_all[ed & mask].mean()), 4) if (ed & mask).any() else None,
                      "rate_any_flag_outside": round(float(any_all[ed & ~mask].mean()), 4)}
        v2 = [m for m in names if m.startswith("V2_")]
        q["V2_post_split"] = {m: {"inside": round(float(Fm[m][elig[m] & sw].mean()), 4) if (elig[m] & sw).any() else None,
                                  "outside": round(float(Fm[m][elig[m] & ~sw].mean()), 4)} for m in v2}
        R["quality"] = q
        rep["methods"][meth] = R

    # redundancia (M1, calibración, muestra)
    rng = np.random.default_rng(SEED)
    idx = np.where(elig_day & calib)[0]
    idx = rng.choice(idx, min(150_000, len(idx)), replace=False)
    sc = pd.DataFrame({m: S1[m][idx] for m in names})
    corr = sc.rank().corr()
    pairs = [(a, b, round(float(corr.loc[a, b]), 3)) for i, a in enumerate(names) for b in names[i + 1:]
             if abs(corr.loc[a, b]) >= 0.6]
    jac = []
    for i, a in enumerate(names):
        fa = flags["M1"][a]
        for b in names[i + 1:]:
            fb = flags["M1"][b]
            u = (fa | fb).sum()
            if u >= 200:
                j = (fa & fb).sum() / u
                if j >= 0.3:
                    jac.append((a, b, round(float(j), 3)))
    rep["redundancy"] = {"spearman_ge_0.6": sorted(pairs, key=lambda x: -abs(x[2])),
                         "jaccard_flags_M1_ge_0.3": sorted(jac, key=lambda x: -x[2]), "sample_rows": int(len(idx))}

    # alertas y episodios (método propuesto: el que se elija; se guardan M0 y M1 completos)
    sec = {}
    for e_, g in df.groupby("entity"):
        s_, src = sectors.sector_at(g["symbol"].iloc[-1], g["date"].iloc[-1])
        sec[e_] = s_ or ""
    for meth in ("M0", "M1", "M2"):
        rows = []
        Fm = flags[meth]
        famday = pd.DataFrame({"date": dates, "entity": ent})
        for m in names:
            ii = np.where(Fm[m])[0]
            if not len(ii):
                continue
            p = df[f"{m}__p"].to_numpy() if f"{m}__p" in df else np.full(len(df), pd.NA)
            sgn = df[f"{m}__s"].to_numpy() if f"{m}__s" in df else np.zeros(len(df))
            score = {"M0": df[f"{m}__m0z"].to_numpy() if f"{m}__m0z" in df else np.full(len(df), np.nan), "M1": S1[m], "M2": S2[m]}[meth]
            rows.append(pd.DataFrame({
                "entity": ent[ii], "symbol": df["symbol"].to_numpy()[ii], "date": dates[ii], "measure": m,
                "code": cat.MEASURE_CODE.get(m, "?"), "family": family_of(m), "segment": segment_of(m),
                "magnitude": df[f"{m}__v"].to_numpy(float)[ii], "rarity_score": np.asarray(score, dtype=float)[ii],
                "m0_flag": F0[m][ii], "peak_slot": pd.array(p[ii], dtype="Int32"), "k": k_of(m),
                "sign": pd.array(sgn[ii], dtype="Int16") if f"{m}__s" in df else cat.direction_of(m),
                "liq_tercile": liq_t[ii], "period": np.where(calib[ii], "calib", "valid"),
                "corp_event": df["corp_event"].to_numpy(bool)[ii], "post_split_window": sw[ii],
                "early_close": df["early_close"].to_numpy(bool)[ii], "coverage": df["cov"].to_numpy()[ii],
                "estimated": m.endswith("_est"), "sector": [sec.get(x, "") for x in ent[ii]]}))
        al = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        if len(al):
            # simultaneidad del propio evento: otras entidades con marca de la misma familia ese día; mismo sector
            fd = al.groupby(["date", "family"])["entity"].transform("nunique") - 1
            al["simultaneous_same_family"] = fd.astype("int32")
            al["simultaneous_same_sector"] = (al.groupby(["date", "family", "sector"])["entity"].transform("nunique") - 1).astype("int32")
            al = al.sort_values(["entity", "date", "measure"]).reset_index(drop=True)
            prevday = al.groupby(["entity", "measure"])["date"].shift(1)
            al["prev_flag_date"] = prevday
            storage.write_parquet_atomic(al, RES / f"e2_alerts_{meth}.parquet")
            rep["methods"][meth]["alerts"] = int(len(al))
            rep["methods"][meth]["episodes"] = episodes(al)
    rep["lab_sample"] = lab_sample(df, flags["M1"], names, elig_day, calib, liq_t)
    rep["costs"] = costs()
    rep["seconds"] = round(time.time() - t0, 1)
    (RES / "e2_report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print("hecho", rep["seconds"], "s")


def windows_of(al: pd.DataFrame) -> pd.DataFrame:
    """Ventana de cada alerta en minutos desde las 04:00 NY: [pico − k + 1, pico] (series) o la del instante fijo."""
    p = al["peak_slot"].astype("float").to_numpy()
    k = al["k"].to_numpy()
    st = p - k + 1
    m = al["measure"].to_numpy()
    runs = np.isin(m, ["P1_run_up", "P1_run_dn", "P3_highvol_run", "D3_gap"])
    st = np.where(runs, p - al["magnitude"].to_numpy() + 1, st)
    out = al[["entity", "date", "segment"]].copy()
    out["s0"], out["s1"] = st, p
    return out


def episodes(al: pd.DataFrame) -> dict:
    w = windows_of(al).dropna(subset=["s0", "s1"]).sort_values(["entity", "date", "s0"])
    res = {}
    for name, keys in (("cat_v0_like", ["entity", "date"]), ("per_segment", ["entity", "date", "segment"])):
        lens, sizes = [], []
        for _, g in w.groupby(keys, sort=False):
            cur0, cur1, n = None, None, 0
            for a, b in zip(g["s0"].to_numpy(), g["s1"].to_numpy()):
                if cur0 is not None and a <= cur1 + 10:
                    cur1, n = max(cur1, b), n + 1
                else:
                    if cur0 is not None:
                        lens.append(cur1 - cur0 + 1)
                        sizes.append(n)
                    cur0, cur1, n = a, b, 1
            if cur0 is not None:
                lens.append(cur1 - cur0 + 1)
                sizes.append(n)
        lens, sizes = np.array(lens), np.array(sizes)
        res[name] = {"episodes": int(len(lens)), "len_min_p50": float(np.median(lens)), "len_min_p90": float(np.quantile(lens, .9)),
                     "len_min_p99": float(np.quantile(lens, .99)), "share_over_120min": round(float((lens > 120).mean()), 4),
                     "share_over_300min": round(float((lens > 300).mean()), 4),
                     "alerts_per_episode_p50": float(np.median(sizes)), "alerts_per_episode_p90": float(np.quantile(sizes, .9))}
    return res


def lab_sample(df, F1, names, elig_day, calib, liq_t):
    """Muestra aleatoria estratificada (semilla fija): eventos M1 por familia × periodo × liquidez, y ventanas de
    control de 30 min en valor-días elegibles SIN ninguna marca M1."""
    rng = np.random.default_rng(SEED)
    rows = []
    fam_of = {m: family_of(m) for m in names}
    any1 = np.zeros(len(df), bool)
    for m in names:
        any1 |= F1[m]
    for f in sorted(set(fam_of.values())):
        ms = [m for m in names if fam_of[m] == f]
        for per, pm in (("calib", calib), ("valid", ~calib)):
            for t in ("baja", "media", "alta"):
                cands = [(i, m) for m in ms for i in np.where(F1[m] & pm & (liq_t == t))[0]]
                if not cands:
                    continue
                for j in rng.choice(len(cands), min(3, len(cands)), replace=False):
                    i, m = cands[j]
                    p = df.at[i, f"{m}__p"] if f"{m}__p" in df else None
                    rows.append(_lab_row(df, i, "evento", m, f, per, t, p, k_of(m)))
    ctrl = np.where(elig_day & ~any1)[0]
    for i in rng.choice(ctrl, min(36, len(ctrl)), replace=False):
        b = sessions.bounds(df.at[i, "date"])
        start = b["open_slot"] + 1 + int(rng.integers(0, max(1, b["close_slot"] - b["open_slot"] - 31)))
        rows.append(_lab_row(df, i, "control", None, None, "calib" if calib[i] else "valid", liq_t[i], start + 29, 30))
    out = pd.DataFrame(rows)
    storage.write_parquet_atomic(out, RES / "e2_lab_sample.parquet")
    out.to_csv(RES / "e2_lab_sample.csv", index=False, encoding="utf-8")
    return {"rows": int(len(out)), "events": int((out["kind"] == "evento").sum()), "controls": int((out["kind"] == "control").sum()),
            "seed": SEED, "file": str(RES / "e2_lab_sample.csv")}


def _lab_row(df, i, kind, m, f, per, t, peak, k):
    d = df.at[i, "date"]
    b = sessions.bounds(d)
    pk = int(peak) if peak is not None and peak == peak else b["open_slot"] + 30
    st = sessions.slot_time(b, max(0, pk - k + 1 - 15)).tz_convert(sessions.NY)
    en = sessions.slot_time(b, min(sessions.N_SLOTS - 1, pk + 16)).tz_convert(sessions.NY)
    url = (f"http://127.0.0.1:8765/?symbol={df.at[i, 'symbol']}&day={d}&start={st:%H:%M}&end={en:%H:%M}&tf=1"
           f"&session=extended&blind=1")
    return {"kind": kind, "symbol": df.at[i, "symbol"], "entity": df.at[i, "entity"], "date": d, "measure": m,
            "family": f, "period": per, "liq_tercile": t, "window_ny": f"{st:%H:%M}-{en:%H:%M}", "lab_url": url}


def costs():
    log = [json.loads(x) for x in (RES / "e2_compute_log.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    ok = [r for r in log if "seconds" in r]
    sz = sum(p.stat().st_size for p in MEAS.glob("*.parquet")) + sum(p.stat().st_size for p in NORM.glob("*.parquet"))
    days = sum(r["days"] for r in ok)
    return {"entities": len(ok), "valor_days": days, "cpu_seconds": round(sum(r["seconds"] for r in ok), 1),
            "ms_per_valor_day": round(1000 * sum(r["seconds"] for r in ok) / max(1, days), 2),
            "storage_mb_measures_and_norm": round(sz / 1e6, 1),
            "bytes_per_valor_day": round(sz / max(1, days), 1)}


if __name__ == "__main__":
    main()
