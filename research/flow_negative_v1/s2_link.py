"""D2 (viabilidad) — enlace de las posiciones de un ETF (solo nombre) con un CIK de la SEC.

Referencia: nombres actual y anteriores de cada CIK del universo (sec/names_universe.csv), con su vigencia.
Regla, por orden:
  1. exacto: el nombre normalizado coincide con un nombre de un solo CIK (si coincide con varios, gana el que tenía ese
     nombre vigente en la fecha de la cartera; si siguen siendo varios, «ambiguo»).
  2. difuso: similitud ≥ 0,90 con margen ≥ 0,05 sobre el segundo CIK, o prefijo común largo con margen.
  3. ambiguo: similitud 0,80-0,90 o sin margen. No se cuenta como enlazado.
  4. sin_enlace.
El miembro de un índice (ticker en una fecha) pasa a CIK con cik_map.csv, eligiendo la identidad vigente en esa fecha
(tickers reutilizados: la clave con asof más próximo posterior a la fecha).
"""
from difflib import SequenceMatcher

import pandas as pd

import fn_config as C
from s2_etf_validate import norm


class Linker:
    def __init__(self):
        n = pd.read_csv(C.SEC / "names_universe.csv", dtype=str, keep_default_na=False)
        # vigencia: los nombres anteriores traen desde/hasta; el actual, desde el último «hasta» de los anteriores
        last_to = n[n.kind == "former"].groupby("cik").to.max().to_dict()
        n["from"] = [r["from"] if r.kind == "former" else last_to.get(r.cik, "") for _, r in n.iterrows()]
        n["to"] = [r.to if r.kind == "former" else "9999" for r in n.itertuples()]
        n["norm"] = n.name.map(norm)
        self.names = n[n.norm != ""]
        self.by_norm = {}
        for r in self.names.itertuples():
            self.by_norm.setdefault(r.norm, []).append((r.cik, r._3, r.to))
        self.norm_list = sorted({(r.norm, r.cik) for r in self.names.itertuples()})
        cm = pd.read_csv(C.SEC / "cik_map.csv", dtype=str, keep_default_na=False)
        cm["asof"] = cm.key.str.split("__").str[1].replace("none", "9999")
        self.tk = {t: g.sort_values("asof")[["asof", "cik"]].values.tolist() for t, g in cm[cm.cik != ""].groupby("ticker")}
        self.cik_name = dict(zip(n[n.kind == "current"].cik, n[n.kind == "current"].name))

    def ticker_cik(self, t, d, tol_days=0):
        """CIK de la identidad del ticker vigente en d. tol_days: admite identidades que terminaron hasta tol_days antes
        de d (bajas de índice con fecha efectiva posterior a la exclusión de cotización: compra ya cerrada)."""
        if tol_days:
            d = (pd.Timestamp(d) - pd.Timedelta(days=tol_days)).strftime("%Y-%m-%d")
        for asof, cik in self.tk.get(t, []):
            if asof >= d:
                return cik
        return None

    def link(self, name, d):
        x = norm(name)
        if not x:
            return None, "sin_enlace", 0.0
        c = self.by_norm.get(x)
        if c:
            ciks = sorted({k for k, _, _ in c})
            if len(ciks) == 1:
                return ciks[0], "exacto", 1.0
            valid = sorted({k for k, a, b in c if (a or "0000") <= d <= (b or "9999")})
            if len(valid) == 1:
                return valid[0], "exacto", 1.0
            return None, "ambiguo", 1.0
        best = {}
        for v, k in self.norm_list:
            sm = SequenceMatcher(None, x, v)
            if sm.real_quick_ratio() < 0.6 or sm.quick_ratio() < 0.6:
                continue
            s = sm.ratio()
            pre = (x.startswith(v) or v.startswith(x)) and min(len(x), len(v)) >= 6
            s_eff = max(s, 0.95) if pre else s
            if s_eff > best.get(k, (0, 0))[0]:
                best[k] = (s_eff, s)
        if not best:
            return None, "sin_enlace", 0.0
        sc = sorted(((v[0], k) for k, v in best.items()), reverse=True)
        s1, k1 = sc[0]
        s2 = sc[1][0] if len(sc) > 1 else 0.0
        if s1 >= 0.90 and s1 - s2 >= 0.05:
            return k1, "difuso", round(s1, 3)
        if s1 >= 0.80:
            return None, "ambiguo", round(s1, 3)
        return None, "sin_enlace", round(s1, 3)
