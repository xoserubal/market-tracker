"""E2 — comprobación pendiente 2: auditoría de ventanas reales y fusión de episodios sobre una muestra.

Encargo del usuario (2026-11-21, «para despues.md» §4 y §7). Solo describe; ningún resultado posterior.

E2_INFORME §5 midió los episodios con la ventana del PICO de cada medida ([pico − k + 1, pico]), porque solo se guardó
el minuto del pico. Aquí se recalculan, para una muestra de valor-días, las series por minuto con el mismo código de
cat-v0 (intraday_features.day_measures), y cada alerta toma su ventana REAL: cada tramo contiguo en que su serie supera
el umbral (intraday_features.crossings, como el escaneo de E1). Las medidas de instante fijo usan su ventana fija.

Cada alerta guarda dos instantes:
- t_start: comienzo del fenómeno (primer minuto de la primera ventana de k minutos que supera el umbral);
- t_detect: primer minuto en que pudo detectarse (cuando termina esa ventana: no antes de tenerla completa).

Umbrales por fila, en unidades de la serie:
- M0 (cat-v0): intraday_features.normalize sobre su línea base (percentil 99 o z ≥ 4), exactamente como E1.
- M1 (E2): mediana + umbral × max(MAD, suelo) en la escala transformada, devuelta a la escala de la serie.
- cat-v1 (propuesta): M1, y en las cinco medidas problemáticas además las condiciones de e2b_criteria.py
  (superar el máximo o el percentil 99 de la base y el percentil 99 de calibración; V3_close_est solo si es evaluable).
La línea base de cada medida son sus valores guardados en e2_measures (las mismas 60 sesiones que la normalización).

Episodios: alertas a ≤ 10 minutos se agrupan (a) en todo el día, como cat-v0, y (b) dentro de cada tramo.
Comprobación de coherencia: el valor recalculado de cada medida debe coincidir con el guardado.

Salidas (MICRO_DATA_DIR/results): e2c_window_audit.json, e2c_audit_alerts.parquet, e2c_audit_episodes.parquet.
Uso: py -3 e2c_window_audit.py [--n-flagged 240] [--n-random 60]
"""
import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import e2_fast as X, intraday_features as F, sessions, storage  # noqa: E402
import e2_analyze as A  # noqa: E402
import e2_compute as EC  # noqa: E402
import e2_normalize as N  # noqa: E402
import e2b_criteria as B  # noqa: E402

warnings.simplefilter("ignore", RuntimeWarning)
RES = storage.root() / "results"
SEED = 20261122
GAP = 10
LOOKBACK_DAYS = 200


def inv_transform(name, y):
    k = N.transform_kind(name)
    if k == "log":
        return np.exp(y)
    if k == "log1p":
        return np.expm1(y)
    return y


def sample(n_flagged, n_random):
    rng = np.random.default_rng(SEED)
    al = pd.read_parquet(RES / "e2_alerts_M1.parquet", columns=["entity", "date", "period", "liq_tercile"])
    al = al.drop_duplicates(["entity", "date"])
    per = max(1, n_flagged // 6)
    parts = []
    for (p, t), g in al.groupby(["period", "liq_tercile"]):
        parts.append(g.iloc[rng.choice(len(g), min(per, len(g)), replace=False)].assign(kind="m1_flagged"))
    meta = ds.dataset(str(A.MEAS), format="parquet").to_table(columns=["entity", "date", "member", "prof_n", "outage"]).to_pandas()
    el = meta[A.base_mask(meta)]
    rnd = el.iloc[rng.choice(len(el), n_random, replace=False)][["entity", "date"]].assign(kind="random")
    rnd["period"] = np.where(rnd["date"] <= A.CALIB_END, "calib", "valid")
    s = pd.concat(parts + [rnd], ignore_index=True)[["entity", "date", "kind", "period"]]
    return s.drop_duplicates(["entity", "date"]).reset_index(drop=True)


def thresholds_for(name, x, W, rep, crit, v3_nonzero):
    """Umbrales de la fila para una medida: dict método -> (umbral en escala de la serie, marca?) o None."""
    out = {}
    b = W[np.isfinite(W)]
    if len(b) < A.MIN_N or not np.isfinite(x):
        return out
    nm = F.normalize(x, b, pct_hi=99.0, z_hi=4.0)
    out["M0"] = (nm["threshold"], bool(nm["flag"]))
    th, fl = rep["calibration"]["M1"]["thresholds"][name], rep["mad_floors"][name]
    bt = N.transform(name, b)
    bt = bt[np.isfinite(bt)]
    xt = N.transform(name, np.array([x]))[0]
    if len(bt) and np.isfinite(xt):
        med = np.median(bt)
        mad = np.median(np.abs(bt - med)) * 1.4826
        sc = max(mad, fl)
        thr1 = float(inv_transform(name, med + th * sc))
        f1 = bool((xt - med) / sc >= th)
        out["M1"] = (thr1, f1)
        if name in B.SPECIAL:
            c = crit[name]
            pct = nm["pct"]
            own = (pct >= 100 - 1e-6) if name in B.DISCRETE else (pct >= 99)
            ok = f1 and own and x > c["abs_threshold_raw"]
            if name == "V3_close_est":
                ok = ok and v3_nonzero >= B.V3_MIN_NONZERO_BASE
            out["v1"] = (max(thr1, c["abs_threshold_raw"], float(np.max(b))), bool(ok))
        else:
            out["v1"] = (thr1, f1)
    return out


def alert_windows(name, m, thr, flag, b, peak_slot):
    """Ventanas reales de una medida marcada: lista de (s_start, s_detect, s_peak, s_end) en minutos desde las 04:00."""
    if not flag:
        return []
    ser, k = m["series"], int(m["k"] or 1)
    if ser is not None:
        runs = F.crossings(ser, thr, k, max_runs=1000)
        if not runs:                    # el máximo cae justo en el umbral (empate): ventana del pico
            p = int(np.nanargmax(ser))
            return [(p - k + 1, p, p, p)]
        start_of = (lambda r: r["first"] - int(ser[r["first"]]) + 1) if name.startswith(("P1_", "P3_", "D3_gap")) else \
            (lambda r: r["first"] - k + 1)
        return [(max(0, start_of(r)), r["first"], r["peak"], r["last"]) for r in runs]
    w0, w1 = m["window"]
    return [(int(w0), int(m["fixed_slot"]) - 1, int(m["fixed_slot"]) - 1, int(w1) - 1)]


def episodes(alerts, keys):
    """Agrupa alertas a ≤ GAP minutos. Devuelve episodios con inicio, detección, fin y nº de alertas."""
    out = []
    for kk, g in alerts.sort_values("s_start").groupby(keys, sort=False):
        cur = None
        for r in g.itertuples():
            if cur is not None and r.s_start <= cur["s_end"] + GAP:
                cur["s_end"] = max(cur["s_end"], r.s_end)
                cur["s_detect"] = min(cur["s_detect"], r.s_detect)
                cur["n"] += 1
                cur["measures"].add(r.measure)
                cur["segments"].add(r.segment)
            else:
                if cur is not None:
                    out.append(cur)
                cur = {**dict(zip(keys, kk if isinstance(kk, tuple) else (kk,))), "s_start": r.s_start, "s_detect": r.s_detect,
                       "s_end": r.s_end, "n": 1, "measures": {r.measure}, "segments": {r.segment}}
        if cur is not None:
            out.append(cur)
    ep = pd.DataFrame(out)
    if len(ep):
        ep["minutes"] = ep["s_end"] - ep["s_start"] + 1
        ep["n_measures"] = ep["measures"].map(len)
        ep["measures"] = ep["measures"].map(lambda s: ",".join(sorted(s)))
        ep["segments"] = ep["segments"].map(lambda s: ",".join(sorted(s)))
    return ep


WHOLE_SEGMENT = ("PRE_ret", "PRE_vol")        # su ventana fija ES todo el premercado: no es fusión


def fusion_breakdown(al, cont_minutes):
    """Episodios largos (≥ 120 min o ≥ 80 % de la sesión continua) por causa, con ventanas reales.

    - whole_segment_measure: lo alarga una medida cuya ventana fija es todo el tramo (premercado).
    - single_long_window: una sola ventana real cubre ≥ 50 % del episodio (fenómeno persistente, p. ej. P3).
    - chained: ninguna ventana llega al 50 %: alertas cortas encadenadas a ≤ 10 min (fusión propiamente dicha)."""
    out = {}
    for meth in sorted(al["method"].unique()):
        x = al[al["method"] == meth].assign(w=lambda d: d["s_end"] - d["s_start"] + 1)
        for grp, keys in (("day", ["entity", "date"]), ("segment", ["entity", "date", "segment"])):
            for excl in (False, True):
                y = x[~x["measure"].isin(WHOLE_SEGMENT)] if excl else x
                rows = []
                for kk, g in y.sort_values("s_start").groupby(keys, sort=False):
                    cur = None
                    for r in g.itertuples():
                        if cur is not None and r.s_start <= cur["e"] + GAP:
                            cur["e"] = max(cur["e"], r.s_end)
                            cur["wmax"] = max(cur["wmax"], r.w)
                            cur["ms"].add(r.measure)
                            cur["n"] += 1
                        else:
                            if cur is not None:
                                rows.append(cur)
                            cur = {"k": kk, "s": r.s_start, "e": r.s_end, "wmax": r.w, "ms": {r.measure}, "n": 1}
                    if cur is not None:
                        rows.append(cur)
                if not rows:
                    continue
                ep = pd.DataFrame(rows)
                ep["L"] = ep["e"] - ep["s"] + 1
                ep["cm"] = [cont_minutes.get((k[0], k[1]), 390) for k in ep["k"]]
                long_ = (ep["L"] >= 120) | (ep["L"] >= 0.8 * ep["cm"])
                whole = ep["ms"].map(lambda s: bool(s & set(WHOLE_SEGMENT)))
                single = ep["wmax"] >= 0.5 * ep["L"]
                cause = np.where(whole, "whole_segment_measure", np.where(single, "single_long_window", "chained"))
                L = ep[long_]
                c = pd.Series(cause[long_.to_numpy()])
                top = pd.Series([m for s in ep.loc[long_ & (cause == "chained"), "ms"] for m in s]).value_counts().head(8).to_dict()
                tops = pd.Series([m for s in ep.loc[long_ & (cause == "single_long_window"), "ms"] for m in s]).value_counts().head(5).to_dict()
                out[f"{meth}|{grp}|{'sin_PRE' if excl else 'todo'}"] = {
                    "episodes": int(len(ep)), "long": int(long_.sum()), "long_share": round(float(long_.mean()), 4),
                    "session_wide_ge80": int((ep["L"] >= 0.8 * ep["cm"]).sum()),
                    "long_by_cause": c.value_counts().to_dict(),
                    "chained_len_p50": float(L.loc[c.values == "chained", "L"].median()) if (c == "chained").any() else None,
                    "chained_alerts_p50": float(L.loc[c.values == "chained", "n"].median()) if (c == "chained").any() else None,
                    "measures_in_chained": top, "measures_in_single_long": tops}
    return out


def summarize(ep, cont_minutes):
    if not len(ep):
        return {"episodes": 0}
    L = ep["minutes"].to_numpy()
    cm = ep.apply(lambda r: cont_minutes.get((r["entity"], r["date"]), 390), axis=1).to_numpy()
    return {"episodes": int(len(ep)), "valor_days": int(ep.groupby(["entity", "date"]).ngroups),
            "len_p50": float(np.median(L)), "len_p90": float(np.quantile(L, .9)), "len_p99": float(np.quantile(L, .99)),
            "len_max": float(L.max()), "share_over_60": round(float((L > 60).mean()), 4),
            "share_over_120": round(float((L > 120).mean()), 4), "share_over_300": round(float((L > 300).mean()), 4),
            "share_ge_80pct_of_session": round(float((L >= 0.8 * cm).mean()), 4),
            "valor_days_with_session_wide_episode": int(ep[L >= 0.8 * cm].groupby(["entity", "date"]).ngroups),
            "alerts_per_episode_p50": float(ep["n"].median()), "alerts_per_episode_p90": float(ep["n"].quantile(.9)),
            "detect_minus_start_p50": float((ep["s_detect"] - ep["s_start"]).median())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-flagged", type=int, default=240)
    ap.add_argument("--n-random", type=int, default=60)
    a = ap.parse_args()
    t0 = time.time()
    rep = json.loads((RES / "e2_report.json").read_text(encoding="utf-8"))
    crit = json.loads((RES / "e2b_criteria.json").read_text(encoding="utf-8"))["measures"]
    S = sample(a.n_flagged, a.n_random)
    print(f"muestra {len(S)} valor-días ({S['kind'].value_counts().to_dict()})", flush=True)
    ents, ua, member = EC.plan()
    EC._init()
    rows, check, cont_minutes, failed = [], [], {}, []
    for k, (ent, g) in enumerate(S.groupby("entity"), 1):
        stored = pd.read_parquet(EC.OUT / f"{ent.replace(':', '_')}.parquet")
        dates_all = pd.to_datetime(stored["date"]).to_numpy().astype("datetime64[D]")
        base_ok = (stored["cov"] >= 0.2).to_numpy()
        pos_all = {d: i for i, d in enumerate(stored["date"])}
        plan_e = ua[ua["entity"] == ent].sort_values("date")
        for r in g.itertuples():
            d = r.date
            lo = (pd.Timestamp(d) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
            gg = plan_e[(plan_e["date"] >= lo) & (plan_e["date"] <= d)].copy()
            gg["asof_k"] = [x if isinstance(x, str) and x.strip() not in ("", "-") else "" for x in gg["asof"]]
            days = list(gg["date"])
            if d not in days or d not in pos_all:
                failed.append((ent, d, "fuera del plan"))
                continue
            bars, _, _ = EC.load_entity_bars(gg)
            bars = EC.split_adjust(bars, EC._G["splits"].get(ent))
            M = X.build_matrix_fast(bars, days)
            cov = np.array([np.isfinite(M.C[i, m["open_slot"] + 1:m["close_slot"]]).mean() if m["close_slot"] > m["open_slot"] + 1
                            else 0.0 for i, m in enumerate(M.meta)])
            i = days.index(d)
            old = (pd.Timestamp(d) - pd.Timedelta(days=EC.MAX_AGE_DAYS)).strftime("%Y-%m-%d")
            base = [j for j in range(i) if cov[j] >= EC.MIN_COV and days[j] >= old][-EC.BASE_TARGET:]
            prof = X.profile_from_parts([X.day_parts(M, j) for j in base])
            cal = EC._G["cal"]
            pdx = cal.index(d)
            prev_close = F.last_continuous_close(M, days.index(cal[pdx - 1])) if cal[pdx - 1] in days else None
            ms = F.day_measures(M, i, prof, prev_close, post=True)
            ms.pop("_quality")
            b = M.meta[i]
            cont_minutes[(ent, d)] = b["close_slot"] - b["open_slot"] - 1
            si = pos_all[d]
            v3w = N.windows(stored["V3_close_est__v"].to_numpy(float), dates_all, base_ok)[si]
            v3nz = float((v3w > 0).sum() / np.isfinite(v3w).sum()) if np.isfinite(v3w).any() else np.nan
            for name, m in ms.items():
                sv = stored.at[si, f"{name}__v"] if f"{name}__v" in stored else np.nan
                check.append((name, m["value"], sv))
                W = N.windows(stored[f"{name}__v"].to_numpy(float), dates_all, base_ok)[si]
                for meth, (thr, flag) in thresholds_for(name, float(sv), W, rep, crit, v3nz).items():
                    for s0, sd, sp, s1 in alert_windows(name, m, thr, flag, b, None):
                        pk = stored.at[si, f"{name}__p"] if f"{name}__p" in stored else pd.NA
                        kk = int(m["k"] or 1)
                        if name.startswith(("P1_", "P3_", "D3_gap")) and np.isfinite(sv):   # como e2_analyze.windows_of
                            kk = int(sv)
                        rows.append({"entity": ent, "date": d, "kind": r.kind, "period": r.period, "method": meth, "measure": name,
                                     "family": A.family_of(name), "segment": A.segment_of(name), "s_start": int(s0),
                                     "s_detect": int(sd), "s_peak": int(sp), "s_end": int(s1),
                                     "peak_s0": int(pk) - kk + 1 if pd.notna(pk) else np.nan, "peak_s1": int(pk) if pd.notna(pk) else np.nan})
        if k % 25 == 0:
            print(f"{k}/{S['entity'].nunique()} entidades · {round(time.time() - t0)} s", flush=True)
    al = pd.DataFrame(rows)
    ck = pd.DataFrame(check, columns=["measure", "recomputed", "stored"])
    same = np.isclose(ck["recomputed"].astype(float), ck["stored"].astype(float), rtol=1e-4, atol=1e-6) | \
        (ck["recomputed"].isna() & ck["stored"].isna())
    res = {"generated_utc": pd.Timestamp.now("UTC").isoformat(), "seed": SEED, "sample": S["kind"].value_counts().to_dict(),
           "failed": failed, "consistency": {"values": int(len(ck)), "match": int(same.sum()),
                                             "mismatch_by_measure": ck[~same]["measure"].value_counts().to_dict()},
           "methods": {}}
    ep_all = []
    for meth in ("M0", "M1", "v1"):
        x = al[al["method"] == meth]
        R = {"alerts": int(len(x)), "valor_days_with_alert": int(x.groupby(["entity", "date"]).ngroups) if len(x) else 0,
             "windows_per_measure_p90": float(x.groupby(["entity", "date", "measure"]).size().quantile(.9)) if len(x) else None}
        for grp, keys in (("day", ["entity", "date"]), ("segment", ["entity", "date", "segment"])):
            ep = episodes(x, keys) if len(x) else pd.DataFrame()
            R[f"real_windows_{grp}"] = summarize(ep, cont_minutes)
            if len(ep):
                ep_all.append(ep.assign(method=meth, grouping=grp, window="real"))
        # comparación: mismas alertas con la ventana del pico (la medición de E2_INFORME §5), una por medida
        pk = x.dropna(subset=["peak_s0"]).drop_duplicates(["entity", "date", "measure"]).copy()
        if len(pk):
            pk["s_start"], pk["s_end"], pk["s_detect"] = pk["peak_s0"], pk["peak_s1"], pk["peak_s1"]
            for grp, keys in (("day", ["entity", "date"]), ("segment", ["entity", "date", "segment"])):
                ep = episodes(pk, keys)
                R[f"peak_windows_{grp}"] = summarize(ep, cont_minutes)
        # cuánto mide cada ventana real, por medida (las que más alargan los episodios)
        if len(x):
            x = x.assign(w=x["s_end"] - x["s_start"] + 1)
            R["window_minutes_by_measure_p90"] = x.groupby("measure")["w"].quantile(.9).sort_values(ascending=False).head(12).round(1).to_dict()
            R["windows_by_measure"] = x["measure"].value_counts().head(12).to_dict()
        res["methods"][meth] = R
    res["fusion_breakdown"] = fusion_breakdown(al, cont_minutes)
    storage.write_parquet_atomic(al, RES / "e2c_audit_alerts.parquet")
    pd.DataFrame([(e, d, v) for (e, d), v in cont_minutes.items()], columns=["entity", "date", "cont_minutes"]).pipe(
        lambda f: storage.write_parquet_atomic(f, RES / "e2c_audit_cont_minutes.parquet"))
    if ep_all:
        storage.write_parquet_atomic(pd.concat(ep_all, ignore_index=True), RES / "e2c_audit_episodes.parquet")
    res["seconds"] = round(time.time() - t0, 1)
    (RES / "e2c_window_audit.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("sample", "consistency", "seconds")}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
