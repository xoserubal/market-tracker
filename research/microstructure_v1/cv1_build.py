"""cat-v1 — regenera las alertas y episodios históricos con las reglas aprobadas y las ventanas reales.

Aprobación del usuario (2026-11-21, revisión de E2B_INFORME.md, §4). Solo descripción: ningún resultado posterior.
No modifica las capas 1 (datos) ni 2 (medidas: features/e2_measures, features/e2_norm); las lee. cat-v0 (events/ y
results/e2_alerts_M0.parquet) queda intacto. La salida de cat-v1 va aparte:
- MICRO_DATA_DIR/results/cat_v1/: alerts.parquet, episodes.parquet, day_family.parquet, build_manifest.json
- MICRO_DATA_DIR/events/cat-v1/{alerts,episodes}/<día>.parquet (registro que lee el laboratorio)

Fase 1 (por entidad, en paralelo):
- marcas cat-v1 de cada valor-día elegible con las cifras guardadas en la capa 2 (misma regla vectorizada que
  e2b_criteria.py: M1 ≥ umbral, más los criterios propios de las cinco medidas; V3_close_est sin alerta);
- para cada valor-día con alguna marca, recalcula las series por minuto con el mismo código de cat-v0 (como
  e2c_window_audit.py) y extrae las VENTANAS REALES de cada alerta; comprueba que el valor recalculado coincide con el
  guardado y que la evaluación fila a fila (micro/catalog_v1.evaluate) da la misma marca que la vectorizada.
Fase 2 (agregado): sector a fecha, simultaneidad por familia (mercado y sector), días de mercado, sospecha de caída de
datos (D3_gap simultáneo sin parada documentada), paradas documentadas, persistencia, episodios por tramo.

Uso: py -3 cv1_build.py [--workers 3] [--limit N] [--entities a,b] [--phase 1|2|all]
"""
import argparse
import json
import os
import sys
import time
import traceback
import warnings
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import catalog_v1 as V, config, e2_fast as X, intraday_features as F, sectors, sessions, storage, test_guard  # noqa: E402
import e2_analyze as A  # noqa: E402
import e2_compute as EC  # noqa: E402
import e2_normalize as N  # noqa: E402

warnings.simplefilter("ignore", RuntimeWarning)
ROOT = storage.root()
OUT = ROOT / "results" / "cat_v1"
ENT = OUT / "_entities"
EVT = ROOT / "events" / "cat-v1"
MIN_FREE_MB = int(os.environ.get("MICRO_CV1_MIN_FREE_MB", "1800"))
LOW_COV = 0.5
GAP_LIKE = ("C5_gap", "PRE_ret")                     # comparan con el cierre anterior: artefacto con evento corporativo
_G = {}


def _init():
    EC._init()
    _G["P"] = V.params()
    _G["computed_utc"] = pd.Timestamp.now("UTC").isoformat(timespec="seconds")


def vector_flags(df: pd.DataFrame, norm: pd.DataFrame, names: list) -> dict:
    """Marca cat-v1 por medida (array bool por fila) con las cifras de la capa 2. Misma regla que e2b_criteria."""
    P = _G["P"]
    elig_day = A.base_mask(df).to_numpy()
    dates = pd.to_datetime(df["date"]).to_numpy().astype("datetime64[D]")
    base_ok = (df["cov"] >= 0.2).to_numpy()
    out = {}
    for m in names:
        if m in P["no_alert_measures"]:
            continue
        x = df[f"{m}__v"].to_numpy(float)
        e = elig_day & np.isfinite(x) & (norm[f"{m}__n"].to_numpy() >= P["baseline"]["min_n"])
        s1 = norm[f"{m}__m1dev"].to_numpy(float) / np.maximum(np.nan_to_num(norm[f"{m}__m1mad"].to_numpy(float)),
                                                               P["m1_mad_floors"][m])
        f = V.at_or_above(s1, P["m1_thresholds"][m]) & e
        if m in P["special"]:
            sp = P["special"][m]
            pct = norm[f"{m}__m0pct"].to_numpy(float)
            own = (pct >= 100 - 1e-6) if sp["own_rule"] == "max" else (pct >= 99)
            f &= own & (x > sp["abs_threshold_raw"])
            if sp["evaluable"] == "min_liq":
                f &= df["liq"].to_numpy(float) >= P["special_rules"]["d3_min_liq"]
        out[m] = f
    return out, elig_day


def post_split(df: pd.DataFrame) -> np.ndarray:
    sd = df["split_day"].to_numpy(bool)
    out = np.zeros(len(df), bool)
    last = -10 ** 9
    for k, s in enumerate(sd):
        if s:
            last = k
        out[k] = (k - last) < _G["P"]["structural"]["post_split_sessions_V2"]
    return out


def persistence(flag: np.ndarray, elig: np.ndarray) -> np.ndarray:
    """Sesiones seguidas (de la entidad, hasta hoy incluido) con la misma marca; una sesión no elegible corta la racha."""
    out = np.zeros(len(flag), np.int16)
    c = 0
    for k in range(len(flag)):
        c = c + 1 if (flag[k] and elig[k]) else 0
        out[k] = c
    return out


def entity_job(args) -> dict:
    ent, g, member_iv = args
    while EC.free_mb() < MIN_FREE_MB:
        time.sleep(20)
    t0 = time.time()
    try:
        fn = f"{ent.replace(':', '_')}.parquet"
        df = pd.read_parquet(EC.OUT / fn)
        norm = pd.read_parquet(N.OUT / fn)
        assert (df["date"].to_numpy() == norm["date"].to_numpy()).all()
        names = sorted(c[:-3] for c in df.columns if c.endswith("__v"))
        flags, elig_day = vector_flags(df, norm, names)
        any_flag = np.zeros(len(df), bool)
        for f in flags.values():
            any_flag |= f
        ps = post_split(df)
        pers = {m: persistence(f, elig_day) for m, f in flags.items()}
        fam_day = pd.DataFrame({"entity": ent, "symbol": df["symbol"], "date": df["date"], "elig": elig_day})
        for fam in sorted({V.family(m) for m in flags}):
            fam_day[f"f_{fam}"] = np.zeros(len(df), bool)
        for m, f in flags.items():
            fam_day[f"f_{V.family(m)}"] |= f
        fam_day["f_D3_gap"] = flags.get("D3_gap", np.zeros(len(df), bool))
        fam_day = fam_day[fam_day["elig"]]
        rows, check, disagree = [], [], []
        if any_flag.any():
            g = g.sort_values("date").assign(asof_k=lambda x: [a if isinstance(a, str) and a.strip() not in ("", "-")
                                                               else "" for a in x["asof"]])
            days = list(g["date"])
            bars, _, _ = EC.load_entity_bars(g)
            bars = EC.split_adjust(bars, EC._G["splits"].get(ent))
            M = X.build_matrix_fast(bars, days)
            del bars
            cov = np.array([np.isfinite(M.C[i, m["open_slot"] + 1:m["close_slot"]]).mean()
                            if m["close_slot"] > m["open_slot"] + 1 else 0.0 for i, m in enumerate(M.meta)])
            pos = {d: i for i, d in enumerate(days)}
            cal = EC._G["cal"]
            cpos = {d: i for i, d in enumerate(cal)}
            dates_all = pd.to_datetime(df["date"]).to_numpy().astype("datetime64[D]")
            base_ok = (df["cov"] >= 0.2).to_numpy()
            Wcache = {}
            parts = {}
            for r in np.where(any_flag)[0]:
                d = df.at[r, "date"]
                i = pos.get(d)
                if i is None:
                    disagree.append((d, "*", "día fuera del plan"))
                    continue
                old = (pd.Timestamp(d) - pd.Timedelta(days=EC.MAX_AGE_DAYS)).strftime("%Y-%m-%d")
                base = [j for j in range(i) if cov[j] >= EC.MIN_COV and days[j] >= old][-EC.BASE_TARGET:]
                for j in base:
                    if j not in parts:
                        parts[j] = X.day_parts(M, j)
                prof = X.profile_from_parts([parts[j] for j in base])
                pdx = cpos.get(d)
                pd_ = cal[pdx - 1] if pdx else None
                prev_close = F.last_continuous_close(M, pos[pd_]) if pd_ in pos else None
                ms = F.day_measures(M, i, prof, prev_close, post=True)
                ms.pop("_quality")
                b = M.meta[i]
                for m, f in flags.items():
                    if not f[r]:
                        continue
                    if m not in Wcache:
                        Wcache[m] = N.windows(df[f"{m}__v"].to_numpy(float), dates_all, base_ok)
                    x = float(df.at[r, f"{m}__v"])
                    mm = ms.get(m)
                    if mm is None:
                        disagree.append((d, m, "medida no recalculada"))
                        continue
                    check.append((m, mm["value"], x))
                    ev = V.evaluate(m, x, Wcache[m][r], liq=float(df.at[r, "liq"]))
                    if ev["state"] != "flag":
                        disagree.append((d, m, f"evaluate={ev['state']}"))
                        continue
                    ev["score_m2"] = float(norm.at[r, f"{m}__m2"]) if np.isfinite(norm.at[r, f"{m}__m2"]) else None
                    extra = {"entity": ent, "liq": float(df.at[r, "liq"]), "cov": float(df.at[r, "cov"]),
                             "longest_gap": float(df.at[r, "longest_gap"]), "dollar_vol": float(df.at[r, "dollar_vol"]),
                             "persistence": int(pers[m][r]), "corp_event": bool(df.at[r, "corp_event"]),
                             "early_close": bool(df.at[r, "early_close"]), "post_split": bool(ps[r])}
                    for a in V.alert_rows(df.at[r, "symbol"], d, m, mm, ev, b, base_extra=extra,
                                          computed_utc=_G["computed_utc"]):
                        rows.append(a)
            del M, parts
        al = pd.DataFrame(rows)
        ck = pd.DataFrame(check, columns=["measure", "recomputed", "stored"])
        same = int((np.isclose(ck["recomputed"].astype(float), ck["stored"].astype(float), rtol=1e-4, atol=1e-6)).sum()) \
            if len(ck) else 0
        ENT.mkdir(parents=True, exist_ok=True)
        if len(al):
            for c in [c for c in al.columns if c.endswith("_utc") and c != "computed_utc"]:
                al[c] = al[c].map(lambda v: v.isoformat() if isinstance(v, pd.Timestamp) else v)
            for c in ("data_quality", "structural"):
                al[c] = al[c].map(json.dumps)
        storage.write_parquet_atomic(al, ENT / f"alerts__{fn}")
        storage.write_parquet_atomic(fam_day, ENT / f"famday__{fn}")
        return {"entity": ent, "valor_days_flagged": int(any_flag.sum()), "alerts": int(len(al)),
                "values_checked": int(len(ck)), "values_match": same, "disagree": disagree[:20],
                "n_disagree": len(disagree), "seconds": round(time.time() - t0, 1)}
    except Exception as e:  # noqa: BLE001
        return {"entity": ent, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}


def phase1(workers: int, limit=None, entities=None):
    test_guard.check([A.CALIB_END, A.E2_LAST], purpose="cat-v1 retrospectivo", script="cv1_build")
    ents, ua, member = EC.plan()
    if entities:
        ents = [e for e in ents if e in set(entities.split(","))]
    ENT.mkdir(parents=True, exist_ok=True)
    have = {p.name[len("famday__"):] for p in ENT.glob("famday__*.parquet")}
    todo = [e for e in ents if f"{e.replace(':', '_')}.parquet" not in have and
            (EC.OUT / f"{e.replace(':', '_')}.parquet").exists()][: limit or None]
    groups = {e: g for e, g in ua.groupby("entity")}
    jobs = [(e, groups[e], member.get(e, [])) for e in todo]
    print(f"entidades {len(ents)}, pendientes {len(jobs)}", flush=True)
    log = OUT / "build_phase1_log.jsonl"
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with Pool(workers, initializer=_init) as pool, log.open("a", encoding="utf-8") as lf:
        for k, r in enumerate(pool.imap_unordered(entity_job, jobs), 1):
            lf.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            lf.flush()
            msg = r.get("error") or f"{r['alerts']} alertas, {r['values_match']}/{r['values_checked']} coinciden, " \
                                    f"{r['n_disagree']} discrepancias, {r['seconds']} s"
            if k % 10 == 0 or r.get("error") or r.get("n_disagree"):
                print(f"{k}/{len(jobs)} {r['entity']}: {msg} · {round(time.time() - t0)} s", flush=True)


def phase2():
    """Agregado: sector a fecha, simultaneidad, días de mercado, calidad de datos, episodios, registro del laboratorio."""
    _G["P"] = P = V.params()
    t0 = time.time()
    al = pd.concat([pd.read_parquet(p) for p in sorted(ENT.glob("alerts__*.parquet")) if p.stat().st_size],
                   ignore_index=True)
    fd = pd.concat([pd.read_parquet(p) for p in sorted(ENT.glob("famday__*.parquet"))], ignore_index=True)
    print(f"alertas {len(al)}, valor-días elegibles {len(fd)} · {round(time.time() - t0)} s", flush=True)
    # sector a fecha (por símbolo del día), cacheado por (símbolo, fecha)
    keys = fd[["symbol", "date"]].drop_duplicates()
    sec = {(s, d): sectors.sector_at(s, d) for s, d in keys.itertuples(index=False)}
    fd["sector_src"] = [sec[(s, d)][1] for s, d in zip(fd["symbol"], fd["date"])]
    # Point-in-time: un sector sacado de una instantánea POSTERIOR a la fecha ('next_snapshot', alta a mitad de año) no
    # vale para estudios a fecha. Se guarda aparte como aproximación retrospectiva y no entra en la simultaneidad por
    # sector (2026-11-21, revisión del usuario de CV1_INFORME §3).
    fd["sector_point_in_time"] = fd["sector_src"].isin(["snapshot", "previous_snapshot"])
    fd["sector_retrospective"] = [sec[(s, d)][0] or "" for s, d in zip(fd["symbol"], fd["date"])]
    fd["sector"] = np.where(fd["sector_point_in_time"], fd["sector_retrospective"], "")
    fams = sorted(c[2:] for c in fd.columns if c.startswith("f_") and c != "f_D3_gap")
    agg = {"n_elig": ("elig", "size")}
    agg.update({f"n_{f}": (f"f_{f}", "sum") for f in fams + ["D3_gap"]})
    day = fd.groupby("date").agg(**agg).reset_index()
    secday = fd[fd["sector_point_in_time"]].groupby(["date", "sector"]).agg(**agg).reset_index()
    for f in fams + ["D3_gap"]:
        day[f"share_{f}"] = day[f"n_{f}"] / day["n_elig"]
        secday[f"share_{f}"] = secday[f"n_{f}"] / secday["n_elig"]
    halts = P["documented_market_halts"]
    thr = P["simultaneity"]["suspected_outage_share"]
    day["d3_simultaneous"] = day["share_D3_gap"] >= thr
    day["documented_halt"] = day["date"].isin(set(halts))
    day["suspected_data_outage"] = day["d3_simultaneous"] & ~day["documented_halt"]
    storage.write_parquet_atomic(day, OUT / "day_family.parquet")
    storage.write_parquet_atomic(secday, OUT / "day_sector_family.parquet")
    # simultaneidad y calidad por alerta
    al = al.merge(fd[["entity", "date", "sector", "sector_src", "sector_point_in_time", "sector_retrospective"]]
                  .rename(columns={"date": "day"}), on=["entity", "day"],
                  how="left")
    dmap = day.set_index("date")
    smap = secday.set_index(["date", "sector"])
    al["share_market_family"] = [float(dmap.at[d, f"share_{f}"]) for d, f in zip(al["day"], al["family"])]
    al["share_sector_family"] = [float(smap.at[(d, s), f"share_{f}"]) if s and (d, s) in smap.index else None
                                 for d, s, f in zip(al["day"], al["sector"], al["family"])]
    al["market_day"] = al["share_market_family"] >= P["simultaneity"]["market_wide_share"]
    susp = set(day.loc[day["suspected_data_outage"], "date"])
    inc = V.data_incidents()
    from micro import dq_checks as Q
    mixed = Q.flagged_registry()
    vday_inc = json.loads(V.INCIDENTS_PATH.read_text(encoding="utf-8")).get("valor_day_incidents", {})         if V.INCIDENTS_PATH.exists() else {}
    dq_all, st_all, status, note = [], [], al["status"].to_list(), al["status_note"].to_list()
    for k, a in enumerate(al.itertuples()):
        dq, st = json.loads(a.data_quality), json.loads(a.structural)
        if a.day in inc:                            # incidencia registrada (corroborada o sospecha comprobada)
            lab, stt, nt = V.incident_effect(inc[a.day], a.day, a.t_start_utc, a.t_end_utc, a.longest_gap)
            dq.append(lab)
            if stt:
                status[k], note[k] = stt, nt
        elif a.day in susp:                         # detectada pero aún sin comprobar
            dq.append("suspected_data_outage_day")
            if a.measure == "D3_gap":
                status[k] = "suspected_data_issue"
                note[k] = "hueco simultáneo en ≥ 10 % de los valores sin parada documentada: sospecha de datos " \
                          "ausentes (sin comprobar todavía)"
        mx = mixed.get((str(a.entity), a.day))
        if mx:
            dq.append("suspected_mixed_price_series")
            if status[k] != "artifact":
                status[k], note[k] = "suspected_data_issue", f"control de series mezcladas ({Q.MIXED['version']}): "                     f"niveles {mx['levels']}, salto {mx['gap']:.1%}, {mx['switches']} cambios de nivel"
        vinc = vday_inc.get(f"{a.symbol}|{a.day}")
        if vinc:
            dq.append(vinc["classification"])
            status[k], note[k] = "suspected_data_issue", f"incidencia de datos del valor-día: {vinc['evidence']}"
        if a.day in halts:
            st.append("documented_market_halt_day")
            if a.measure == "D3_gap":
                note[k] = f"parada general documentada: {halts[a.day]}"
        if a.corp_event:
            dq.append("corp_event_unreconstructed")
            if a.measure in GAP_LIKE:
                status[k] = "artifact"
                note[k] = "evento corporativo no reconstruido: el cierre anterior no es comparable"
        if a.cov < LOW_COV:
            dq.append("low_minute_coverage")
        if a.early_close:
            st.append("early_close")
        if a.post_split and a.measure.startswith("V2_"):
            st.append("post_split_V2_window")
        if a.market_day:
            st.append("market_wide_family_day")
        dq_all.append(sorted(set(dq)))
        st_all.append(sorted(set(st)))
    al["data_quality"], al["structural"], al["status"], al["status_note"] = dq_all, st_all, status, note
    for c in [c for c in al.columns if c.endswith("_utc") and c != "computed_utc"]:
        al[c] = pd.to_datetime(al[c], utc=True)
    al = al.sort_values(["day", "symbol", "t_detect_utc", "measure"]).reset_index(drop=True)
    # agrupar con solo las columnas que usa group_episodes (memoria: 235 k filas × 50 campos en dicts no caben)
    cols = ["symbol", "day", "segment", "family", "measure", "code", "score_m1", "status", "market_day",
            "data_quality", "structural", "threshold_knowledge", "t_start_utc", "t_detect_utc", "t_end_utc",
            "t_available_utc", "episode_start_utc", "episode_end_utc"]
    recs = al[cols].assign(_i=np.arange(len(al))).to_dict("records")
    eps = pd.DataFrame(V.group_episodes(recs))
    eid = np.empty(len(al), dtype=object)
    for r in recs:
        eid[r["_i"]] = r["episode_id"]
    del recs
    al["episode_id"] = eid
    n_fd, sec_src = int(len(fd)), fd["sector_src"].value_counts().to_dict()
    del fd, keys, sec
    print(f"episodios {len(eps)} · {round(time.time() - t0)} s", flush=True)
    for df in (al, eps):
        for c in [c for c in df.columns if c.endswith("_utc") and c != "computed_utc"]:
            df[c] = df[c].map(lambda v: v.isoformat() if isinstance(v, pd.Timestamp) else v)
    storage.write_parquet_atomic(al.assign(data_quality=al["data_quality"].map(json.dumps),
                                           structural=al["structural"].map(json.dumps)), OUT / "alerts.parquet")
    storage.write_parquet_atomic(eps.assign(**{c: eps[c].map(json.dumps) for c in
                                               ("measures", "codes", "families", "data_quality", "structural")}),
                                 OUT / "episodes.parquet")
    # registro por día para el laboratorio (sustituye el día entero de cat-v1 retrospectivo)
    from micro import event_store
    for d, g in al.groupby("day"):
        event_store.write_day("alerts", d, g.assign(**{"pass": "retro"}), replace=[("retro",)], keys=("pass",),
                              version="cat-v1")
    for d, g in eps.groupby("day"):
        event_store.write_day("episodes", d, g.assign(**{"pass": "retro"}), replace=[("retro",)],
                              keys=("pass",), version="cat-v1")
    lg = [json.loads(l) for l in (OUT / "build_phase1_log.jsonl").read_text(encoding="utf-8").splitlines()]
    ok = [r for r in lg if "error" not in r]
    man = {"catalog_version": V.CATALOG_VERSION, "detector_version": V.DETECTOR_VERSION,
           "params_sha256": V.PARAMS_SHA256, "code_version": config.code_version(),
           "generated_utc": pd.Timestamp.now("UTC").isoformat(), "period": ["2016-01-04", A.E2_LAST],
           "entities": len({r["entity"] for r in ok}), "errors": [r for r in lg if "error" in r],
           "alerts": int(len(al)), "episodes": int(len(eps)), "eligible_valor_days": n_fd,
           "valor_days_with_alert": int(al.groupby(["entity", "day"]).ngroups) if len(al) else 0,
           "consistency": {"values_checked": sum(r["values_checked"] for r in ok),
                           "values_match": sum(r["values_match"] for r in ok),
                           "row_vs_vector_disagreements": sum(r["n_disagree"] for r in ok)},
           "suspected_data_outage_days": sorted(susp),
           "data_incidents_applied": {d: inc[d]["classification"] for d in sorted(susp) if d in inc}, "documented_halt_days_present": sorted(set(halts) & set(day["date"])),
           "d3_simultaneous_days": day.loc[day["d3_simultaneous"], ["date", "share_D3_gap", "n_elig"]].to_dict("records"),
           "status_counts": al["status"].value_counts().to_dict(),
           "threshold_knowledge_counts": al["threshold_knowledge"].value_counts().to_dict(),
           "sector_source_counts": sec_src}
    for p in ("alerts.parquet", "episodes.parquet", "day_family.parquet", "day_sector_family.parquet"):
        man.setdefault("output_sha256", {})[p] = _sha(OUT / p)
    (OUT / "build_manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: man[k] for k in ("entities", "alerts", "episodes", "consistency", "status_counts",
                                          "suspected_data_outage_days")}, ensure_ascii=False, default=str), flush=True)


def _sha(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 22), b""):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--entities")
    ap.add_argument("--phase", default="all", choices=["1", "2", "all"])
    a = ap.parse_args()
    if a.phase in ("1", "all"):
        phase1(a.workers, a.limit, a.entities)
    if a.phase in ("2", "all"):
        phase2()


if __name__ == "__main__":
    main()
