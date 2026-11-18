"""Revisión de las lecturas macro de Market Tracker (2026-11-18) — descarga de historias largas.

Solo lectura: no toca producción. Guarda en _work/ (ignorado por git) las series diarias/semanales/mensuales que usan
las 14 lecturas de index.html, con la misma fuente que la página (FRED o Yahoo).
"""
import json
import os
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
OUT = HERE / "_work"
OUT.mkdir(exist_ok=True)
load_dotenv(HERE.parents[1] / ".env")
KEY = os.environ["FRED_API_KEY"]

FRED = ["DFII10", "T10Y3M", "T10Y2Y", "BAMLH0A0HYM2", "BAMLC0A0CM", "T5YIE", "INDPRO", "WM2NS", "WALCL",
        "RRPONTSYD", "WTREGEN", "NFCICREDIT", "CFNAI"]
YAHOO = {"^VIX": "vix", "DX-Y.NYB": "dxy", "^TNX": "tnx", "^IRX": "irx"}


def fred(s):
    j = requests.get("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": s, "api_key": KEY, "file_type": "json", "observation_start": "2000-01-01"},
                     timeout=60).json()
    return [{"date": o["date"], "value": float(o["value"])} for o in j["observations"] if o["value"] != "."]


out = {}
for s in FRED:
    out[s] = fred(s)
    print(s, len(out[s]), out[s][0]["date"], out[s][-1]["date"])
for t, name in YAHOO.items():
    d = yf.download(t, start="2000-01-01", auto_adjust=False, progress=False)
    c = d["Close"].squeeze().dropna()
    out[t] = [{"date": i.strftime("%Y-%m-%d"), "value": float(v)} for i, v in c.items()]
    print(t, len(out[t]), out[t][0]["date"], out[t][-1]["date"])
(OUT / "series.json").write_text(json.dumps(out), encoding="utf-8")
