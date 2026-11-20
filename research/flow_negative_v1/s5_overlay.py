"""Enmienda 1 — superposición de correcciones sobre las series v4. No modifica ningún fichero original.

Familias (enmienda §2, §5, §8):
  splits    contrasplits documentados (data/corr1_splits.csv): precios × factor y volumen ÷ factor antes de la fecha.
  identity  series con el ticker transferido a otra entidad (data/corr1_identity.csv): corte en la fecha; el tramo
            anterior se une a la entidad que continúa (misma entidad legal renombrada) o queda como serie propia.
  cik       tramos de CIK por serie (data/corr1_cik.csv; las filas de las series de identidad son de esa familia).

Salidas:
  work/series_c1/<clave>.parquet        series corregidas, con el Flow recalculado (misma réplica de producción)
  data/corr1_series_overlay.json        cambios por serie y familia (inicio, fin, splits, eventos, saltos, nuevas)
  data/corr1_frame_extra.csv            tramos de pertenencia a índices que pasan de la serie cortada a la que continúa
  data/corr1_cik_ranges.csv             tramos de CIK por serie y familia (para la capitalización)
  data/corr1_overlay_checks.json        comprobaciones de cada transformación
"""
import json
import sys

import numpy as np
import pandas as pd

import fn_config as C
from s0_series import build_flow

SER = C.WORK / "series"
OUT = C.WORK / "series_c1"
OUT.mkdir(exist_ok=True)
PRICE = ["open", "high", "low", "close", "open_adj", "high_adj", "low_adj", "adj"]

# (serie cortada, fecha de corte, serie que continúa la entidad anterior o None, proporción de la escindida, fuente)
IDENTITY = [
    ("ARNC__2023-08-18__e0", "2020-04-01", "HWM__none__e0", 0.25,
     "Arconic Inc. → Howmet; 1 Arconic Corp. por cada 4 (10-K 2019 de Arconic Inc., CIK 4281)"),
    ("AAN__2023-09-15x__e0", "2020-12-01", "PRG__none__e0", 0.5,
     "Aaron's → PROG; 1 The Aaron's Company por cada 2 (8-K PROG 2020-12-04)"),
    ("DLPH__2020-10-06__e0", "2017-12-05", "APTV__none__e0", 1 / 3,
     "Delphi Automotive → Aptiv; 1 Delphi Technologies por cada 3 (APTV 2017-11-15, ex. 99.4)"),
    ("XPER__2024-06-21x__e0", "2022-10-03", "ADEA__none__e0", None,
     "Xperi Holding → Adeia; ADEA ya tiene la historia (precios idénticos); proporción de Xperi Inc. sin verificar"),
    ("CR__none__e0", "2023-04-04", "CXT__none__e0", 1.0,
     "Crane Holdings → Crane NXT; 1 Crane Company por cada 1 (8-K CXT 2023-03-08)"),
    ("FOXA__none__e0", "2019-03-19", None, None,
     "21st Century Fox (clase A) hasta 2019-03-18; desde 2019-03-19 Fox Corporation. 21CF: escisión de Fox Corp y "
     "compra por Disney (mixta, valor no reconstruido: regla §4.2)"),
    ("GCI__2023-06-16x__e0", "2019-11-20", None, None,
     "Gannett antigua hasta 2019-11-19; desde 2019-11-20 New Media renombrada Gannett (sin historia propia en el "
     "universo); el tramo anterior no entra en el marco"),
]


def load_summary():
    from s1_panel import load_series_table
    return load_series_table()


def recompute(d):
    fl = build_flow(d)
    keep = [c for c in d.columns if c not in fl.columns or c == "date"]
    out = d[keep].merge(fl, on="date", how="left")
    out["dollar_vol"] = out.raw_close * out.raw_volume
    return out


def series(k):
    f = OUT / f"{k}.parquet"
    return pd.read_parquet(f if f.exists() else SER / f"{k}.parquet")


def main():
    s = load_summary()
    overlay = {"splits": {}, "identity": {}, "new_keys": {}}
    checks = {"splits": [], "identity": []}

    # ---------------------------------------------------------------- contrasplits
    sp = pd.read_csv(C.PUB / "corr1_splits.csv")
    for r in sp.itertuples():
        k, bd, f = r.key, r.bar_date, float(r.factor)
        if k not in s.index:
            checks["splits"].append({"key": k, "error": "clave no está en el resumen"})
            continue
        row = s.loc[k]
        applied = json.loads(row.splits_list or "[]")
        if any(d == bd for d, _ in applied):
            raise SystemExit(f"doble aplicación: {k} ya tiene un split el {bd}")
        d0 = pd.read_parquet(SER / f"{k}.parquet")
        d = d0.copy()
        m = d.date < bd
        for c in PRICE:
            d.loc[m, c] = d.loc[m, c] * f
        d.loc[m, "volume"] = d.loc[m, "volume"] / f
        i = int(np.searchsorted(d.date.to_numpy(), bd))
        ratio_after = float(d.close.iat[i] / d.close.iat[i - 1])
        ratio_before = float(d0.close.iat[i] / d0.close.iat[i - 1])
        conc = d.close / d0.close
        ok_conc = bool(np.allclose(conc[m], f) and np.allclose(conc[~m], 1.0))
        if not (0.5 <= ratio_after <= 2.0):
            raise SystemExit(f"{k}: tras corregir, el cociente del {bd} es {ratio_after:.3f}")
        d = recompute(d[[c for c in d0.columns if c not in ("flow", "mom", "R", "w1", "m1", "rsi", "atrPct",
                                                             "macd_hist", "fromHigh", "konc_d", "konc_3d", "konc_w",
                                                             "konc_align", "flow_complete", "dollar_vol")]])
        d.to_parquet(OUT / f"{k}.parquet")
        events = json.loads(row.events or "[]")
        new_ev = [[e, t] for e, t in events if not (e == bd and t == "E2_split_incoherente")]
        if k == "DD__none__e0":     # la distribución de Corteva del mismo día es una operación propia (§2)
            new_ev.append(["2019-06-03", "E1_escision_registro"])
        jumps = [x for x in json.loads(row.unexplained_jumps or "[]") if x != bd]
        overlay["splits"][k] = {"splits_list": applied + [[bd, 1.0 / f]], "events": sorted(map(list, set(map(tuple, new_ev)))),
                                "unexplained_jumps": jumps,
                                "trace": {"converted_event": [bd, "E2_split_incoherente → C1_split_corregido"],
                                          "factor": f, "source": r.source}}
        checks["splits"].append({"key": k, "bar_date": bd, "factor": f, "ratio_close_before": ratio_before,
                                 "ratio_close_after": ratio_after, "conciliation_exact": ok_conc,
                                 "rows_scaled": int(m.sum())})
        print("split", k, bd, f, round(ratio_before, 3), "→", round(ratio_after, 3), "conciliación", ok_conc, flush=True)

    # ---------------------------------------------------------------- identidad
    from s1_panel import clip_membership, frame_entry
    mem = clip_membership(pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False))
    etf = pd.read_csv(C.PUB / "membership_etf_sp400.csv", dtype=str, keep_default_na=False)
    _, ivs0 = frame_entry(s, mem, etf)
    extra = []
    ident_rows = []
    for k, cut, parent, ratio, src in IDENTITY:
        row = s.loc[k]
        d0 = series(k)          # puede venir ya corregida por un split
        pre, post = d0[d0.date < cut].copy(), d0[d0.date >= cut].copy()
        base_cols = [c for c in d0.columns if c not in ("flow", "mom", "R", "w1", "m1", "rsi", "atrPct", "macd_hist",
                                                        "fromHigh", "konc_d", "konc_3d", "konc_w", "konc_align",
                                                        "flow_complete", "dollar_vol")]
        post = recompute(post[base_cols].reset_index(drop=True))
        post.to_parquet(OUT / f"{k}.parquet")
        events = json.loads(row.events or "[]")
        ov = {"start": cut,
              "events": [[e, t] for e, t in events if e > cut],
              "unexplained_jumps": [x for x in json.loads(row.unexplained_jumps or "[]") if x > cut],
              "splits_list": [x for x in json.loads(row.splits_list or "[]") if x[0] > cut]}
        overlay["identity"][k] = ov
        ivs_pre = [(a, min(b, (pd.Timestamp(cut) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")), ix)
                   for a, b, ix, _ in ivs0.get(k, []) if a < cut]
        info = {"key": k, "cut": cut, "parent": parent, "ratio": ratio, "source": src,
                "pre_rows": len(pre), "post_rows": len(post), "pre_intervals": ivs_pre}
        if parent is not None:
            p0 = series(parent)
            first = p0.date.iat[0]
            add = pre[pre.date < first][base_cols].copy()
            if parent == "ADEA__none__e0":
                add = add.iloc[0:0]          # ADEA ya tiene esos días con los mismos precios
            if len(add):
                # unión continua: el retorno del día de unión es el cociente de cierres (misma acción)
                r_join = p0.close.iat[0] / add.close.iat[-1]
                scale = (p0.adj.iat[0] / r_join) / add.adj.iat[-1]
                for c in ("open_adj", "high_adj", "low_adj", "adj"):
                    add[c] = add[c] * scale
                info["join_return"] = float(r_join - 1)
            ext = pd.concat([add, p0[base_cols]], ignore_index=True)
            ext = recompute(ext)
            ext.to_parquet(OUT / f"{parent}.parquet")
            prow = s.loc[parent]
            pev = json.loads(prow.events or "[]")
            pre_ev = [[e, t] for e, t in events if e < cut]
            new_ev = sorted(map(list, set(map(tuple, pev + pre_ev + [[cut, "E1_escision_identidad"]]))))
            psp = json.loads(prow.splits_list or "[]") + [x for x in json.loads(row.splits_list or "[]") if x[0] < cut]
            overlay["identity"][parent] = {"start": ext.date.iat[0], "events": new_ev,
                                           "unexplained_jumps": json.loads(prow.unexplained_jumps or "[]") +
                                           [x for x in json.loads(row.unexplained_jumps or "[]") if x < cut],
                                           "splits_list": psp}
            for a, b, ix in ivs_pre:
                extra.append({"key": parent, "start": a, "end": b, "index": ix, "family": "identity",
                              "from_key": k})
            info["parent_rows_added"] = len(add)
        else:
            nk = f"{k}__pre"
            pre = recompute(pre[base_cols].reset_index(drop=True))
            pre.to_parquet(OUT / f"{nk}.parquet")
            new = row.to_dict()
            new.update({"start": pre.date.iat[0], "end": pre.date.iat[-1], "terminated": "True",
                        "events": json.dumps([[e, t] for e, t in events if e < cut]),
                        "unexplained_jumps": json.dumps([x for x in json.loads(row.unexplained_jumps or "[]") if x < cut]),
                        "splits_list": json.dumps([x for x in json.loads(row.splits_list or "[]") if x[0] < cut]),
                        "req_key": f"{row.req_key}__pre", "orig_req": f"{row.orig_req}__pre", "cik": ""})
            overlay["new_keys"][nk] = {c: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
                                       for c, v in new.items()}
            for a, b, ix in ivs_pre:
                extra.append({"key": nk, "start": a, "end": b, "index": ix, "family": "identity", "from_key": k})
            info["new_key"] = nk
        checks["identity"].append(info)
        ident_rows.append({"key": k, "cut": cut, "continues_in": parent or f"{k}__pre", "spin_ratio": ratio,
                           "source": src})
        print("identidad", k, cut, "→", parent or f"{k}__pre", flush=True)

    pd.DataFrame(ident_rows).to_csv(C.PUB / "corr1_identity.csv", index=False)
    pd.DataFrame(extra).to_csv(C.PUB / "corr1_frame_extra.csv", index=False)

    # ---------------------------------------------------------------- CIK por tramos
    ck = pd.read_csv(C.PUB / "corr1_cik.csv")
    ident_keys = {x[0] for x in IDENTITY} | {x[2] for x in IDENTITY if x[2]}
    ck["family"] = np.where(ck.key.isin(ident_keys), "identity", "cik")
    # ADEA: Xperi Corp (CIK 1690666) → Xperi Holding (1803696), canje 1:1 en jun-2020
    ck = pd.concat([ck, pd.DataFrame([{"key": "ADEA__none__e0", "from": "2015-01-01", "to": "2020-05-31",
                                       "cik": 1690666, "type": "predecesor", "share_factor": 1,
                                       "note": "Xperi Corp → Xperi Holding (1:1, fusión con TiVo, jun-2020)",
                                       "family": "identity"}])], ignore_index=True)
    ck[["key", "from", "to", "cik", "type", "share_factor", "family", "note"]].to_csv(
        C.PUB / "corr1_cik_ranges.csv", index=False)

    (C.PUB / "corr1_series_overlay.json").write_text(json.dumps(overlay, indent=1, default=str), encoding="utf-8")
    (C.PUB / "corr1_overlay_checks.json").write_text(json.dumps(checks, indent=1, default=str), encoding="utf-8")
    print("hecho", flush=True)


if __name__ == "__main__":
    main()
