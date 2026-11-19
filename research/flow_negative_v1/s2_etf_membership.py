"""Opción 2 (aprobada 2026-11-19) — pertenencia al S&P 400 de 2015 a 2020 a partir de las carteras de IJH e IVOO.

Regla, sin información futura y sin atribuir pertenencia antes de lo observado:
- Observación: el fondo (IJH o IVOO) tiene la empresa (CIK enlazado por nombre) en su cartera en la fecha d.
- Tramo: una empresa es miembro desde la primera observación de una racha hasta la última observación de la racha.
  La racha se corta cuando la empresa falta en una cartera posterior (de cualquiera de los dos fondos).
  Entre la última observación con ella y la primera sin ella, la fecha real de baja es desconocida: se cierra en la
  última observación (no se prolonga).
- Estado del tramo:
  confirmado — aparece en ≥ 2 observaciones (del mismo fondo o de los dos);
  inferido   — una sola observación.
- Solo se usan carteras fiables: total de acciones que cuadra con el documento (o NPORT-P) y ≥ 90 % de nombres
  enlazados. Los informes semestral/anual de Vanguard (feb/ago) no pasan: mezclan filas que no son posiciones o son
  resúmenes. Se excluyen y se listan.
- Comprobación de identidad por precio: el enlace nombre → CIK solo cuenta si el precio implícito de la posición
  (valor / acciones; Vanguard N-Q en miles de $) coincide ±3 % con el último cierre en bruto de alguna serie de ese CIK
  en esa fecha. Los nombres pueden coincidir con el de otra empresa posterior (p. ej. «Coherent Inc.» de 2016 frente a
  II-VI, hoy «Coherent Corp.»). Sin serie con la que comprobar: no cuenta (sin precio no entra en el panel).
- Segundo enlace, por ticker: si una posición no se enlaza por CIK (sin CIK en nuestro mapa, CIK erróneo o precio que
  no coincide), se compara su nombre con los nombres de Wikipedia de los miembros del S&P 400 anteriores a 2021
  (exacto, o similitud ≥ 0,90 con margen ≥ 0,05) y se verifica igual por precio con la serie de ese ticker. Recupera
  miembros auténticos ya presentes en el universo (sobre todo empresas absorbidas en 2016-2018).
- Empresas sin CIK del universo: no se añaden (decisión: no se buscan empresas desaparecidas). Se cuentan.
- El tramo que llega a la última cartera de 2020 queda abierto hasta 2021-01-01 (desde ahí manda la reconstrucción
  de Wikipedia, fiable desde 2021).
Salidas: data/membership_etf_sp400.csv (cik, start, end, status, n_obs) — la pertenencia a un índice es pública — y
data/d2_membership_etf.json (resumen).
"""
import json
from collections import defaultdict

import numpy as np
import pandas as pd

import fn_config as C
import s2_etf_lib as L
from s2_link import Linker

LO, HI = "2015-01-01", "2020-12-31"
SWITCH = "2021-01-01"


def price_checker():
    comp = pd.read_csv(C.WORK / "companies_v3.csv", dtype=str, keep_default_na=False)
    ser = defaultdict(list)
    for r in comp.itertuples():
        if r.cik:
            ser[r.cik].append((r.key, r.start, r.end))
    cache = {}

    def close(key, d):
        if key not in cache:
            p = pd.read_parquet(C.WORK / "series" / f"{key}.parquet", columns=["date", "raw_close"])
            cache[key] = (p.date.to_numpy(), p.raw_close.to_numpy())
        ds, cs = cache[key]
        i = np.searchsorted(ds, d, side="right") - 1
        return float(cs[i]) if i >= 0 else None

    tser = defaultdict(list)
    for r in comp.itertuples():
        for sym in set(r.symbols.split("|")) | {r.ticker}:
            if sym:
                tser[sym].append((r.key, r.start, r.end))

    def check_tk(t, d, px):
        found = False
        for key, a, b in tser.get(t, []):
            if a <= d <= b:
                c = close(key, d)
                if c and c > 0:
                    found = True
                    if abs(np.log(px / c)) < 0.03:
                        return True
        return False if found else None

    def check(cik, d, px):
        """True si coincide, False si no coincide, None si no hay serie que cubra la fecha."""
        found = False
        for key, a, b in ser.get(cik, []):
            if a <= d <= b:
                c = close(key, d)
                if c and c > 0:
                    found = True
                    if abs(np.log(px / c)) < 0.03:
                        return True
        return False if found else None
    return check, check_tk


def main():
    lk = Linker()
    check, check_tk = price_checker()
    from difflib import SequenceMatcher
    from s2_etf_validate import norm
    mem = pd.read_csv(C.PUB / "membership.csv", dtype=str, keep_default_na=False)
    cand = mem[(mem["index"] == "sp400") & (mem.start < SWITCH)]
    tk_names = {}
    for r in cand.itertuples():
        tk_names.setdefault(norm(r.name), set()).add(r.ticker)
    tk_list = list(tk_names.items())

    def tk_link(name):
        x = norm(name)
        if x in tk_names and len(tk_names[x]) == 1:
            return next(iter(tk_names[x]))
        sc = sorted(((SequenceMatcher(None, x, v).ratio(), v) for v, _ in tk_list), reverse=True)[:2]
        if sc and sc[0][0] >= 0.90 and (len(sc) < 2 or sc[0][0] - sc[1][0] >= 0.05) and len(tk_names[sc[0][1]]) == 1:
            return next(iter(tk_names[sc[0][1]]))
        return None
    pstat = defaultdict(int)
    inv = L.inventory()
    obs = []      # (fecha, fondo, set de CIK)
    excluded = []
    unl = defaultdict(set)
    for f in ("IJH", "IVOO"):
        for d in sorted(set(inv[(inv.fund == f) & (inv.period >= LO) & (inv.period <= HI)].period)):
            h = L.holdings(f, d, inv)
            if h is None:
                print("sin cartera", f, d)
                continue
            s = set()
            scale = 1000.0 if f in ("IVOO", "VIOO") and h["type"] != "NPORT-P" else 1.0
            nlink = 0
            for r in h["rows"]:
                k, t, sc = lk.link(r["name"], d)
                px = r["value"] * scale / r["shares"] if r["shares"] > 0 else None
                pc = None
                if k:
                    nlink += 1
                    pc = check(k, d, px) if px else None
                    pstat[{True: "precio_ok", False: "precio_no_coincide", None: "sin_serie"}[pc]] += 1
                    if pc:
                        s.add(f"cik:{k}")
                        continue
                tk = tk_link(r["name"])
                if tk and px and check_tk(tk, d, px):
                    s.add(f"tk:{tk}")
                    pstat["ticker_fallback_ok"] += 1
                    if not k:
                        nlink += 1
                elif not k:
                    unl[r["name"]].add(d)
            ok = (h["type"] == "NPORT-P" or h.get("check") is True) and nlink >= 0.9 * len(h["rows"])
            print(f, d, h["type"], h.get("check"), len(h["rows"]), "enlazadas", len(s), "OK" if ok else "EXCLUIDA", flush=True)
            if ok:
                obs.append((d, f, s, len(h["rows"])))
            else:
                excluded.append(f"{f} {d} {h['type']} check={h.get('check')} n={len(h['rows'])} enlazadas={len(s)}")
    obs.sort()
    allc = set().union(*(o[2] for o in obs))
    rows = []
    for c in sorted(allc):
        run = []
        for d, f, s, _ in obs:
            if c in s:
                run.append((d, f))
            elif run:
                rows.append((c, run))
                run = []
        if run:
            rows.append((c, run))
    out = []
    last_date = obs[-1][0]
    for c, run in rows:
        start, end = run[0][0], run[-1][0]
        if end == last_date:
            end = SWITCH
        kind, ident = c.split(":", 1)
        out.append({"index": "sp400", "cik": ident if kind == "cik" else "", "ticker": ident if kind == "tk" else "",
                    "start": start, "end": end,
                    "status": "confirmado" if len(run) >= 2 else "inferido", "n_obs": len(run),
                    "funds": "|".join(sorted({f for _, f in run}))})
    m = pd.DataFrame(out)
    m.to_csv(C.PUB / "membership_etf_sp400.csv", index=False)
    per_obs = [{"date": d, "fund": f, "n": n, "linked": len(s)} for d, f, s, n in obs]
    summ = {"observations": len(obs), "first": obs[0][0], "last": obs[-1][0],
            "identities": int(len(set(zip(m.cik, m.ticker)))), "via_ticker": int((m.ticker != "").sum()),
            "intervals": len(m),
            "intervals_by_status": m.status.value_counts().to_dict(),
            "link_rate_pct_by_obs": {f"{o['fund']} {o['date']}": round(100 * o["linked"] / o["n"], 1) for o in per_obs},
            "excluded_observations": excluded,
            "price_check": dict(pstat),
            "max_gap_days": int(pd.Series(pd.to_datetime(sorted({o[0] for o in obs}))).diff().dt.days.max()),
            "distinct_unlinked_names": len(unl),
            "unlinked_names_sample": sorted(unl)[:60]}
    json.dump(summ, open(C.PUB / "d2_membership_etf.json", "w"), indent=1)
    print({k: v for k, v in summ.items() if k not in ("link_rate_pct_by_obs", "unlinked_names_sample")})


if __name__ == "__main__":
    main()
