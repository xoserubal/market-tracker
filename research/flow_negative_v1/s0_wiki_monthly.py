"""Descarga instantáneas mensuales (revisión vigente el día 15) de las páginas de Wikipedia de un índice.
Uso: py -3 s0_wiki_monthly.py sp400 2015-06 2022-12"""
import json, sys, time
import pandas as pd, requests
import fn_config as C
H = {"User-Agent": "FlowNegResearch/1.0 (personal research; python-requests)"}
TITLE = {"sp400": "List_of_S%26P_400_companies", "sp600": "List_of_S%26P_600_companies"}


def get(url):
    for i in range(8):
        try:
            r = requests.get(url, headers=H, timeout=60)
            if r.ok and r.text.strip():
                return r
        except Exception:
            pass
        time.sleep(4 * (i + 1))
    raise RuntimeError(url)


def main(idx, a, b):
    path = C.WIKI / f"{idx}_monthly_revisions.json"
    revs = json.load(open(path)) if path.exists() else {}
    for m in pd.period_range(a, b, freq="M"):
        key = str(m)
        if key in revs and (C.WIKI / f"{idx}_m{key}.html").exists():
            continue
        q = get(f"https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles={TITLE[idx]}&rvlimit=1"
                f"&rvdir=older&rvstart={key}-15T00:00:00Z&rvprop=timestamp%7Cids&format=json").json()
        rv = next(iter(q["query"]["pages"].values())).get("revisions")
        if not rv:
            continue
        revs[key] = rv[0]
        f = C.WIKI / f"{idx}_m{key}.html"
        if not f.exists():
            f.write_text(get(f"https://en.wikipedia.org/w/index.php?oldid={rv[0]['revid']}").text, encoding="utf-8")
        json.dump(revs, open(path, "w"), indent=1)
        time.sleep(1)
    print(idx, len(revs), "revisiones mensuales")


if __name__ == "__main__":
    main(*sys.argv[1:4])
