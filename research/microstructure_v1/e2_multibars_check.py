"""E2 §6 — verificación de la petición múltiple de barras ANTES de usarla a escala.

Compara AlpacaProvider.fetch_bars_multi con las peticiones individuales (fetch_pages) en días ya cerrados del periodo
libre (nada del periodo reservado de G2A):
1. Equivalencia: mismas barras (t, o, h, l, c, v, n, vw) símbolo a símbolo.
2. Paginación: se repite con un límite de página pequeño para forzar muchas páginas y cortes entre símbolos.
3. Cobertura: cada símbolo pedido aparece en la respuesta (vacío si no cotizaba).
4. Símbolo ausente: un ticker inexistente devuelve lista vacía sin romper a los demás.
5. Error parcial: se simula un fallo en la 2.ª página; la llamada debe lanzar ProviderError (nada a medias).
Usa el limitador compartido. Salida: results/e2_multibars_check.json. Uso: py -3 e2_multibars_check.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import calendar, runtime, storage, test_guard  # noqa: E402
from micro.providers.base import FetchStats, ProviderError  # noqa: E402

CASES = [("2021-06-15", ["AAPL", "MSFT", "XOM", "KO", "NVR"]),          # muy líquidos + uno poco negociado
         ("2019-11-29", ["SPY", "AMZN", "JNJ"]),                          # cierre anticipado
         ("2017-03-08", ["GE", "T", "ZZZZQ"])]                            # incluye un ticker inexistente
COLS = ["t", "o", "h", "l", "c", "v", "n", "vw"]


def frame(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=COLS)
    return df[COLS].sort_values("t").reset_index(drop=True)


def main():
    prov = runtime.alpaca()
    res = {"cases": []}
    for day, syms in CASES:
        test_guard.check([day], purpose="E2 verificación multi-barras", script="e2_multibars_check")
        s, e = calendar.session_bounds(day, "full")
        start, end = calendar.iso(s), calendar.iso(e)
        single, st1 = {}, FetchStats()
        for sym in syms:
            try:
                single[sym] = frame([r for p in prov.fetch_pages("bars", sym, start, end, stats=st1) for r in p])
            except ProviderError as ex:
                single[sym] = f"error: {ex}"
        for lim in (10000, 700):
            st2 = FetchStats()
            multi = prov.fetch_bars_multi(syms, start, end, stats=st2, page_limit=lim)
            per = {}
            for sym in syms:
                a, b = single[sym], frame(multi.get(sym, []))
                if isinstance(a, str):
                    per[sym] = {"single": a, "multi_rows": len(b)}
                    continue
                eq = len(a) == len(b) and (len(a) == 0 or a.equals(b))
                per[sym] = {"rows_single": len(a), "rows_multi": len(b), "identical": bool(eq),
                            "in_response": sym in multi}
            res["cases"].append({"day": day, "symbols": syms, "page_limit": lim, "pages_multi": multi["_pages"],
                                 "requests_single": st1.requests, "requests_multi": st2.requests, "per_symbol": per,
                                 "all_identical": all(v.get("identical", v.get("multi_rows") == 0) for v in per.values())})
            print(day, lim, "páginas", multi["_pages"], "iguales", res["cases"][-1]["all_identical"], flush=True)
    # error parcial simulado: la 2.ª página falla
    orig, calls = prov._get, {"n": 0}

    def flaky(url, params, stats):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ProviderError("simulado: fallo en la 2.ª página", status=500, retryable=False)
        return orig(url, params, stats)
    prov._get = flaky
    day = CASES[0][0]
    s, e = calendar.session_bounds(day, "full")
    try:
        prov.fetch_bars_multi(CASES[0][1], calendar.iso(s), calendar.iso(e), page_limit=700)
        res["partial_error"] = {"raised": False}
    except ProviderError as ex:
        res["partial_error"] = {"raised": True, "message": str(ex)}
    finally:
        prov._get = orig
    res["ok"] = all(c["all_identical"] for c in res["cases"]) and res["partial_error"]["raised"]
    p = storage.root() / "results" / "e2_multibars_check.json"
    p.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print("OK" if res["ok"] else "FALLA", p)


if __name__ == "__main__":
    main()
