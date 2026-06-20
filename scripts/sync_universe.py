"""
sync_universe.py — Sincroniza docs/data/universe.json con backtest/config/individual_stocks.yaml.

Reglas:
  - Tickers en YAML que no están en universe → se añaden con defaults del cluster.
  - Tickers en universe que ya no están en YAML → se eliminan.
  - Tickers ya presentes en universe → se conserva su metadata (theme, proxies, etc.),
    solo se actualiza el campo 'notes' con la nota del YAML si existía vacío.

Se llama automáticamente desde pcs_calculator.py al inicio de cada run.
También se puede ejecutar manualmente:
    py -3 scripts/sync_universe.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

ROOT      = Path(__file__).parent.parent
YAML_PATH = ROOT / "backtest" / "config" / "individual_stocks.yaml"
UNIV_PATH = ROOT / "docs" / "data" / "universe.json"

# Mapeo cluster YAML → campos por defecto en universe.json
# theme_proxy debe ser un ticker presente en rotation_signals (ETFs del sistema macro)
CLUSTER_DEFAULTS: dict[str, dict] = {
    "Growth": {
        "theme": "us_tech_ai",
        "theme_proxy": "XLK",
        "macro_proxy": "QQQ",
        "benchmark": "QQQ",
        "asset_type": "stock",
        "region": "US",
        "priority": "medium",
    },
    "Value/Cyclical": {
        "theme": "us_cyclical",
        "theme_proxy": "XLI",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "US",
        "priority": "medium",
    },
    "Defensive": {
        "theme": "us_defensive",
        "theme_proxy": "XLP",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "US",
        "priority": "medium",
    },
    "Commodities": {
        "theme": "silver_gold_miners",
        "theme_proxy": "GC=F",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "GLOBAL",
        "priority": "medium",
    },
    "Small/EM": {
        "theme": "smallcap_em",
        "theme_proxy": "EEM",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "etf",
        "region": "EM",
        "priority": "medium",
    },
    "Cripto": {
        "theme": "crypto",
        "theme_proxy": "BTC-USD",
        "macro_proxy": "QQQ",
        "benchmark": "BTC-USD",
        "asset_type": "stock",
        "region": "US",
        "priority": "medium",
    },
    "Cannabis": {
        "theme": "cannabis",
        "theme_proxy": "XLY",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "US",
        "priority": "medium",
    },
    "China/Asia": {
        "theme": "china_em",
        "theme_proxy": "FXI",
        "macro_proxy": "EEM",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "EM",
        "priority": "medium",
    },
    "Argentina": {
        "theme": "argentina",
        "theme_proxy": "EEM",
        "macro_proxy": "EEM",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "EM",
        "priority": "medium",
    },
    "Canada_Energy": {
        "theme": "oil_gas",
        "theme_proxy": "XLE",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "CA",
        "priority": "medium",
    },
    "REITs": {
        "theme": "reits",
        "theme_proxy": "XLRE",
        "macro_proxy": "TLT",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "US",
        "priority": "medium",
    },
    "Salud/Biotech": {
        "theme": "healthcare_special",
        "theme_proxy": "XLV",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "GLOBAL",
        "priority": "medium",
    },
    "Salud_Largecap": {
        "theme": "healthcare_largecap",
        "theme_proxy": "XLV",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "US",
        "priority": "medium",
    },
    "Volatilidad/ETFs": {
        "theme": "global_etf",
        "theme_proxy": "SPY",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "etf",
        "region": "US",
        "priority": "low",
    },
    "Mineras_Juniors": {
        "theme": "silver_gold_miners",
        "theme_proxy": "SI=F",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "GLOBAL",
        "priority": "medium",
    },
    "Europa": {
        "theme": "europa",
        "theme_proxy": "EFA",
        "macro_proxy": "SPY",
        "benchmark": "SPY",
        "asset_type": "stock",
        "region": "EU",
        "priority": "medium",
    },
}


def load_yaml_tickers() -> list[dict]:
    """Lee el YAML y devuelve lista ordenada de {ticker, cluster, note}."""
    if not YAML_PATH.exists():
        raise FileNotFoundError(f"No se encontró {YAML_PATH}")
    with open(YAML_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    result = []
    for cluster, stocks in (cfg.get("clusters") or {}).items():
        for s in (stocks or []):
            result.append({
                "ticker":  s["ticker"],
                "cluster": cluster,
                "note":    s.get("note", ""),
            })
    return result


def sync(verbose: bool = True) -> dict:
    """
    Sincroniza universe.json con individual_stocks.yaml.
    Devuelve {'added': [...], 'removed': [...], 'kept': int}.
    """
    yaml_entries = load_yaml_tickers()
    yaml_tickers = [e["ticker"] for e in yaml_entries]
    yaml_set     = set(yaml_tickers)

    # Cargar universe actual
    existing: dict = {}
    if UNIV_PATH.exists():
        data = json.loads(UNIV_PATH.read_text(encoding="utf-8"))
        existing = {t["ticker"]: t for t in data.get("tickers", [])}

    added   = []
    removed = sorted(set(existing.keys()) - yaml_set)
    kept    = 0

    new_tickers = []
    for entry in yaml_entries:
        ticker  = entry["ticker"]
        cluster = entry["cluster"]
        note    = entry["note"]

        if ticker in existing:
            rec = dict(existing[ticker])
            # Actualizar note solo si estaba vacío
            if not rec.get("notes") and note:
                rec["notes"] = note
            new_tickers.append(rec)
            kept += 1
        else:
            defaults = CLUSTER_DEFAULTS.get(cluster, CLUSTER_DEFAULTS["Growth"])
            new_tickers.append({
                "ticker":      ticker,
                "name":        "",
                "asset_type":  defaults["asset_type"],
                "tradable":    True,
                "theme":       defaults["theme"],
                "subtheme":    "",
                "region":      defaults["region"],
                "macro_proxy": defaults["macro_proxy"],
                "theme_proxy": defaults["theme_proxy"],
                "benchmark":   defaults["benchmark"],
                "priority":    defaults["priority"],
                "notes":       note,
            })
            added.append(ticker)

    # Reconstruir lista de themes desde los tickers resultantes
    themes = sorted({t["theme"] for t in new_tickers if t.get("theme")})

    out = {
        "version": data.get("version", "1.0") if UNIV_PATH.exists() else "1.0",
        "updated": str(date.today()),
        "themes":  themes,
        "tickers": new_tickers,
    }
    UNIV_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        print(f"sync_universe: {len(new_tickers)} tickers "
              f"(+{len(added)} añadidos, -{len(removed)} eliminados, {kept} conservados)")
        if added:
            print(f"  Añadidos:   {added}")
        if removed:
            print(f"  Eliminados: {removed}")

    return {"added": added, "removed": removed, "kept": kept}


if __name__ == "__main__":
    sync(verbose=True)
