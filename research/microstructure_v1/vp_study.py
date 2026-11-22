"""VP2 — comparaciones descriptivas en ventanas de 5, 10, 20, 40 y 60 sesiones y casos representativos.

Descriptivo: cómo se distribuye y cambia la negociación por precio. No predice nada ni busca acumulación.

Muestra (fijada antes de mirar resultados):
- hist: 200 entidades al azar (semilla 20261122) de las 629; fechas finales cada 60 sesiones desde la sesión 60 de
  cada entidad, solo días de pertenencia al S&P 500;
- recent: todos los símbolos; fecha final = última sesión (2026-11-20); ventanas de 5 a 40 (no hay 60 sesiones).
Ventanas con marcas de calidad (evento corporativo, split, caída, cobertura < 50 %) se cuentan aparte.

Casos representativos (reglas fijas; entre las que cumplen, la de mayor puntuación; entidades distintas):
- POC estable (40 sesiones): sin marcas; POC compuesto de confianza alta; ≤ 2 desplazamientos materiales;
  |neto| ≤ 50 pb; una concentración persistente con el POC compuesto dentro y persistencia ≥ 0,7.
  Puntuación: persistencia máxima.
- Migración persistente (20 sesiones): sin marcas; ≥ 4 desplazamientos materiales; coherencia de dirección ≥ 0,8;
  |neto material| ≥ 300 pb. Puntuación: |neto material|. Uno al alza y uno a la baja.
- Cambio del área de valor (20 sesiones): sin marcas; anchura último/primer día ≥ 3 (expansión) o ≤ 1/3
  (contracción). Puntuación: |log del cociente|. Una expansión y una contracción.

Uso: py -3 vp_study.py run [--workers 4]   ·   py -3 vp_study.py cases
"""
import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import heavy_lock, storage, vp_windows as VW  # noqa: E402

OUT = storage.root() / "results" / "vp2"
SEED, N_HIST, STEP = 20261122, 200, 60


def one_file(rel: str) -> list:
    df = pd.read_parquet(storage.root() / "features" / "vp_profiles" / rel).sort_values("date").reset_index(drop=True)
    per = df["period"].iloc[0]
    rows = []
    if per == "hist":
        ends = [i for i in range(STEP - 1, len(df), STEP) if bool(df.at[i, "member"])]
    else:
        ends = [len(df) - 1]
    for i in ends:
        end = df.at[i, "date"]
        for n in VW.WINDOWS:
            if i + 1 < n:
                continue
            w = VW.window(df, end, n)
            if not w.get("ok"):
                continue
            mats = [x["shift_bps"] for x in w["poc_shifts"] if x["material"]]
            net = sum(mats)
            pz = [z for z in w["persistent"] if z["low"] <= w["composite"]["poc_price"] < z["high"]]
            pv = [z for z in w["persistent_va"] if z["low"] <= w["composite"]["poc_price"] < z["high"]]
            vw0, vw1 = w["va_width_first_last_bps"]
            rows.append({"file": rel, "entity": df.at[i, "entity"], "symbol": df.at[i, "symbol"], "period": per,
                         "end": end, "n": n, "flags": ",".join(w["quality_flags"]), "missing": len(w["missing_sessions"]),
                         "poc_net_bps": w["poc_net_shift_bps"], "poc_material_shifts": w["poc_material_shifts"],
                         "poc_material_path_bps": w["poc_material_path_bps"], "poc_material_net_bps": w["poc_material_net_bps"],
                         "poc_material_consistency": w["poc_material_consistency"], "va_jaccard_mean": w["va_jaccard_mean"],
                         "tvd_mean": w["tvd_mean"], "va_width_first_bps": vw0, "va_width_last_bps": vw1,
                         "n_persistent": len(w["persistent"]),
                         "persistent_share": sum(z["composite_share"] for z in w["persistent"]),
                         "poc_in_persistent": bool(pz), "poc_persistence": max((z["max_persistence"] for z in pz), default=0.0),
                         "max_abs_material_bps": max((abs(x) for x in mats), default=0.0),
                         "material_same_sign_frac": (sum((x > 0) == (net > 0) for x in mats) / len(mats)) if mats and net else None,
                         "n_persistent_va": len(w["persistent_va"]),
                         "max_persistence_zone90": w["max_persistence_zone90"], "max_persistence_va": w["max_persistence_va"],
                         "persistent_va_share": sum(z["composite_share"] for z in w["persistent_va"]),
                         "persistent_va_width_bps": sum((z["high"] - z["low"]) for z in w["persistent_va"]) / w["days"][-1]["c"] * 1e4,
                         "poc_in_persistent_va": bool(pv),
                         "poc_persistence_va": max((z["max_persistence"] for z in pv), default=0.0),
                         "comp_conf": w["composite"]["poc_confidence"], "comp_top1": w["composite"]["top1_share"],
                         "comp_segments": w["composite"]["zone90_n_segments"], "comp_peaks": w["composite"]["n_peaks"],
                         "day_conf_low_share": float(np.mean([d["conf"] == "baja" for d in w["days"]])),
                         "price_change_pct": w["price_change_pct"], "range_pct": w["range_pct"]})
    return rows


def run(workers):
    ix = VW.index()
    files_h = sorted(set(ix[ix["period"] == "hist"]["file"]))
    rng = np.random.default_rng(SEED)
    pick = sorted(rng.choice(files_h, size=min(N_HIST, len(files_h)), replace=False).tolist())
    files = pick + sorted(set(ix[ix["period"] == "recent"]["file"]))
    t0 = time.time()
    rows = []
    with heavy_lock.HeavyJob("vp_study"), Pool(workers) as pool:
        for k, r in enumerate(pool.imap_unordered(one_file, files), 1):
            rows += r
            if k % 100 == 0:
                print(f"{k}/{len(files)} · {round(time.time() - t0)} s", flush=True)
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    storage.write_parquet_atomic(df, OUT / "windows_study.parquet")
    clean = df[(df["flags"] == "") & (df["missing"] == 0)]
    q = lambda s: {k: round(float(v), 3) for k, v in s.quantile([0.1, 0.5, 0.9]).items()}  # noqa: E731
    summ = {"windows": len(df), "clean": len(clean), "seconds": round(time.time() - t0, 1),
            "flags_share": round(float((df["flags"] != "").mean()), 4), "by_window": {}}
    for (per, n), g in clean.groupby(["period", "n"]):
        summ["by_window"][f"{per}_{n}"] = {
            "count": len(g), "entities": int(g["entity"].nunique()),
            "poc_net_bps_abs": q(g["poc_net_bps"].abs()), "material_shifts_per_session": q(g["poc_material_shifts"] / (n - 1)),
            "no_material_shift_share": round(float((g["poc_material_shifts"] == 0).mean()), 3),
            "material_consistency": q(g["poc_material_consistency"].dropna()),
            "va_jaccard_mean": q(g["va_jaccard_mean"]), "tvd_mean": q(g["tvd_mean"]),
            "va_width_ratio_last_first": q(g["va_width_last_bps"] / g["va_width_first_bps"]),
            "n_persistent": q(g["n_persistent"]), "persistent_share": q(g["persistent_share"]),
            "poc_in_persistent_share": round(float(g["poc_in_persistent"].mean()), 3),
            "n_persistent_va": q(g["n_persistent_va"]), "max_persistence_zone90": q(g["max_persistence_zone90"]),
            "max_persistence_va": q(g["max_persistence_va"]), "persistent_va_share": q(g["persistent_va_share"]),
            "persistent_va_width_bps": q(g["persistent_va_width_bps"]),
            "poc_in_persistent_va_share": round(float(g["poc_in_persistent_va"].mean()), 3),
            "comp_conf": g["comp_conf"].value_counts(normalize=True).round(3).to_dict(),
            "comp_multi_segment_share": round(float((g["comp_segments"] >= 2).mean()), 3),
            "day_conf_low_share": q(g["day_conf_low_share"])}
    (OUT / "windows_study_summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("windows", "clean", "seconds", "flags_share")}))


def cases():
    df = pd.read_parquet(OUT / "windows_study.parquet")
    c = df[(df["flags"] == "") & (df["missing"] == 0)]
    out, used = {}, set()

    def take(name, sub, score, k=1, cond=None):
        sub = sub.assign(_s=score(sub)).sort_values("_s", ascending=False)
        got = []
        for r in sub.itertuples():
            if r.entity in used or (cond and not cond(r)):
                continue
            got.append({k2: getattr(r, k2) for k2 in ("symbol", "entity", "period", "end", "n", "poc_net_bps",
                        "poc_material_shifts", "poc_material_net_bps", "poc_material_consistency", "va_jaccard_mean",
                        "va_width_first_bps", "va_width_last_bps", "poc_persistence", "max_persistence_va", "comp_conf",
                        "max_abs_material_bps", "material_same_sign_frac",
                        "price_change_pct",
                        "range_pct")})
            used.add(r.entity)
            if len(got) >= k:
                break
        out[name] = got

    s = c[(c["n"] == 40) & (c["comp_conf"] == "alta") & (c["poc_material_shifts"] <= 2) & (c["poc_net_bps"].abs() <= 50)
          & c["poc_in_persistent"] & (c["poc_persistence"] >= 0.7)]
    take("poc_estable", s, lambda x: x["poc_persistence"], k=2)
    # añadida tras ver que la regla anterior queda vacía (la persistencia en la zona del 90 % casi nunca supera 0,5):
    # las ventanas de 20 sesiones más estables de la muestra, por persistencia máxima en el área de valor diaria
    e = c[(c["n"] == 20) & (c["poc_net_bps"].abs() <= 100)]
    take("poc_mas_estable_de_la_muestra", e, lambda x: x["max_persistence_va"] - x["poc_material_shifts"] / 100, k=2)
    m = c[(c["n"] == 20) & (c["poc_material_shifts"] >= 4) & (c["poc_material_consistency"] >= 0.8)
          & (c["poc_material_net_bps"].abs() >= 300)]
    take("migracion_alcista", m[m["poc_material_net_bps"] > 0], lambda x: x["poc_material_net_bps"].abs())
    take("migracion_bajista", m[m["poc_material_net_bps"] < 0], lambda x: x["poc_material_net_bps"].abs())
    # añadida tras ver que la regla anterior elige saltos aislados (CMG 2018-04-26, resultados: un solo +19 % domina la
    # coherencia ponderada por tamaño): migración REPARTIDA, ningún desplazamiento > 40 % del neto y ≥ 70 % de los
    # desplazamientos materiales (contados) en el mismo sentido
    r = m[(m["max_abs_material_bps"] <= 0.4 * m["poc_material_net_bps"].abs()) & (m["material_same_sign_frac"] >= 0.7)]
    take("migracion_repartida_alcista", r[r["poc_material_net_bps"] > 0], lambda x: x["poc_material_net_bps"].abs())
    take("migracion_repartida_bajista", r[r["poc_material_net_bps"] < 0], lambda x: x["poc_material_net_bps"].abs())
    v = c[c["n"] == 20].assign(r=lambda x: x["va_width_last_bps"] / x["va_width_first_bps"])
    take("area_valor_expansion", v[v["r"] >= 3], lambda x: np.log(x["r"]))
    take("area_valor_contraccion", v[v["r"] <= 1 / 3], lambda x: -np.log(x["r"]))
    (OUT / "cases.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--workers", type=int, default=4)
    sp.add_parser("cases")
    a = ap.parse_args()
    run(a.workers) if a.cmd == "run" else cases()


if __name__ == "__main__":
    main()
