"""
Familia "Cruce Rojo D" — carteras 100% mecánicas, sin IA en ningún punto
(entrada ni salida). Mismo motor, dos variantes con distinto umbral de
sobreventa relativa, corridas en un solo pase (comparten la misma lectura
de koncorde_data.json, sin descargarlo/leerlo dos veces).

Origen: propuesta del usuario 2026-08-30 ("línea negra" = konc_d_trend, "línea
roja" = konc_d_trend_ma, ambas ya calculadas por koncorde_calculator.py).
Validadas primero con un backtest retroactivo sobre el universo Koncorde
completo (198 tickers, 2022-06→2026-08-30, ver research/koncorde_cross_backtest_2026-08/)
antes de implementarlas como cartera real — mismo criterio del proyecto que
para Mirror Espejo/Cava: no operar una idea nueva sin evidencia primero.

Regla de entrada (todas a la vez, sobre el cierre diario ya cerrado):
  1. konc_d_trend_cross == "up"          — el marrón cruza al alza a la roja hoy
  2. konc_d_trend_pctile252 <= pctile_max — el marrón está en su propio percentil
                                            de sobreventa relativa (el valor
                                            absoluto <0 casi nunca se da: solo
                                            ~2.3% del tiempo en todo el universo,
                                            verificado en el backtest)
  3. konc_d_rsi14 < rsi_max               — RSI clásico de sobreventa

Regla de salida — la misma que describió el usuario, sin cortacircuito de
precio añadido (decisión explícita 2026-08-30, distinto de MIRROR_ESPEJO/
CAVA_MACRO que sí llevan uno), igual en las dos variantes:
  konc_d_trend_cross == "down"           — el marrón cruza a la baja a la roja

Dos variantes, mismo backtest (research/koncorde_cross_backtest_2026-08/README.md):

  CRUCE_ROJO_D     percentil<=10  — la estricta (original, 2026-08-30). Mejor
                                     perfil del backtest (media +5.39%, peor
                                     caso -8.7%) pero rara: 38 señales/4 años
                                     sobre el universo completo.
  CRUCE_ROJO_D_25  percentil<=25  — la laxa, pedida por el usuario el mismo
                                     día para tener más frecuencia. Peor perfil
                                     en el backtest (media +3.70%, peor caso
                                     -11.9%) pero 134 señales/4 años — más
                                     turnover, más posiciones abiertas de media.

RSI<30, tamaño 5% fijo y sin límite de posiciones son iguales en ambas
(mismo patrón que MIRROR_ESPEJO). Universo: todo lo que koncorde_calculator.py
rastrea (~198-202 tickers), no solo los candidatos PCS de ai_candidates.json.

Uso:
    py -3 scripts/cruce_rojo_d_portfolio.py              # dry-run: muestra qué haría, no escribe
    py -3 scripts/cruce_rojo_d_portfolio.py --apply       # aplica entradas/salidas de verdad, ambas carteras
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

KONCORDE_JSON = DATA / "koncorde_data.json"
PICKS_JSON    = DATA / "ai_picks.json"
UNIVERSE_JSON = DATA / "universe.json"
LOG_PATH      = DATA / "cruce_rojo_d_log.jsonl"  # compartido, cada fila lleva "portfolio"

# Sin límite de posiciones (decisión del usuario 2026-08-30, mismo criterio
# que MIRROR_ESPEJO) — igual en las dos variantes.
CONFIGS = [
    {"name": "CRUCE_ROJO_D",    "pctile_max": 10.0, "rsi_max": 30.0, "size_pct": 5.0, "max_positions": 999},
    {"name": "CRUCE_ROJO_D_25", "pctile_max": 25.0, "rsi_max": 30.0, "size_pct": 5.0, "max_positions": 999},
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_universe_map() -> dict[str, dict]:
    data = _load(UNIVERSE_JSON)
    return {t["ticker"]: t for t in data.get("tickers", []) if t.get("ticker")}


def fetch_last_closes(tickers: list[str]) -> dict[str, float]:
    """Último cierre diario para una lista de tickers. Best-effort, ignora fallos individuales.
    Mismo patrón que mirror_portfolio.py — group_by="ticker" incluso para 1 solo ticker."""
    if not tickers:
        return {}
    out: dict[str, float] = {}
    try:
        raw = yf.download(tickers, period="5d", auto_adjust=True, progress=False,
                           group_by="ticker")
    except Exception as e:
        print(f"  ⚠ fetch_last_closes error: {e}")
        return out
    for tk in tickers:
        try:
            series = raw[tk]["Close"].dropna()
            if len(series):
                out[tk] = float(series.iloc[-1])
        except Exception:
            continue
    return out


def qualifies_for_entry(k: dict, config: dict) -> bool:
    cross = k.get("konc_d_trend_cross")
    pctile = k.get("konc_d_trend_pctile252")
    rsi = k.get("konc_d_rsi14")
    if cross != "up":
        return False
    if pctile is None or pctile > config["pctile_max"]:
        return False
    if rsi is None or rsi >= config["rsi_max"]:
        return False
    return True


def build_candidates(koncorde_out: dict[str, dict], already_held: set[str],
                      universe_map: dict[str, dict], config: dict) -> list[dict]:
    candidates = []
    for tk, k in koncorde_out.items():
        if not qualifies_for_entry(k, config):
            continue
        if tk in already_held:
            continue
        u = universe_map.get(tk, {})
        candidates.append({
            "ticker":    tk,
            "name":      u.get("name", ""),
            "theme":     u.get("theme", ""),
            "subtheme":  u.get("subtheme", ""),
            "konc_d_trend":          k.get("konc_d_trend"),
            "konc_d_trend_ma":       k.get("konc_d_trend_ma"),
            "konc_d_trend_pctile252": k.get("konc_d_trend_pctile252"),
            "konc_d_rsi14":          k.get("konc_d_rsi14"),
        })
    return candidates


def check_exits(picks: dict, koncorde_out: dict[str, dict], today: str, config: dict) -> list[dict]:
    """
    Salida mecánica: cierra toda posición cuyo konc_d_trend_cross de hoy sea
    "down". Sin cortacircuito de precio (decisión explícita, a diferencia de
    MIRROR_ESPEJO/CAVA_MACRO) — igual en las dos variantes, se evalúa siempre,
    antes de nuevas entradas, no depende de --apply salvo para persistir.
    """
    name = config["name"]
    ptf = picks.setdefault("portfolios", {}).setdefault(
        name, {"positions": [], "history": []}
    )
    positions = ptf.get("positions", [])
    if not positions:
        return []

    tickers = [p["ticker"] for p in positions]
    closes = fetch_last_closes(tickers)

    closed_events = []
    remaining = []
    for pos in positions:
        tk = pos["ticker"]
        k = koncorde_out.get(tk)
        if k is None:
            # el ticker salió del universo Koncorde por completo — sin dato para
            # decidir, no se toca (se reintenta el próximo run, mismo criterio
            # que "sin dato hoy" en mirror_portfolio.py)
            remaining.append(pos)
            continue
        cross = k.get("konc_d_trend_cross")
        price = closes.get(tk)
        if cross == "down":
            close_reason = (f"konc_d_trend_cross=down "
                             f"(trend={k.get('konc_d_trend')}, trend_ma={k.get('konc_d_trend_ma')})")
            ptf.setdefault("history", []).append({
                **pos,
                "event":        "close",
                "close_date":   today,
                "close_price":  price,
                "close_reason": close_reason,
            })
            closed_events.append({"ticker": tk, "close_price": price})
            print(f"  [{name}] EXIT {tk}: konc_d_trend_cross=down (trend={k.get('konc_d_trend')}, "
                  f"trend_ma={k.get('konc_d_trend_ma')})")
        else:
            remaining.append(pos)

    ptf["positions"] = remaining
    return closed_events


def run_for_config(picks: dict, koncorde_out: dict[str, dict], universe_map: dict[str, dict],
                    today: str, apply: bool, config: dict) -> dict:
    """Evalúa salidas + entradas de una sola variante. Devuelve un resumen
    para el log/print combinado — no escribe ai_picks.json (lo hace el
    caller una vez, para las dos variantes a la vez)."""
    name = config["name"]
    ptf = picks.setdefault("portfolios", {}).setdefault(
        name, {"positions": [], "history": []}
    )

    already_held = {p["ticker"] for p in ptf.get("positions", [])}
    closed = check_exits(picks, koncorde_out, today, config)
    if closed:
        print(f"  [{name}] {len(closed)} posición(es) cerrada(s) por cruce a la baja.")
    already_held -= {c["ticker"] for c in closed}

    candidates = build_candidates(koncorde_out, already_held, universe_map, config)
    print(f"[{name}] Candidatos hoy (cruce alcista + percentil<={config['pctile_max']} + "
          f"RSI<{config['rsi_max']}, no en cartera): {len(candidates)}")
    for c in candidates:
        print(f"  {c['ticker']:10s} trend={c['konc_d_trend']:.2f} trend_ma={c['konc_d_trend_ma']:.2f} "
              f"pctile252={c['konc_d_trend_pctile252']:.1f} rsi14={c['konc_d_rsi14']:.1f}")

    n_open = len(already_held)
    room = config["max_positions"] - n_open
    to_add = candidates[:room] if room > 0 else []
    if room <= 0 and candidates:
        print(f"  ⚠ [{name}] MAX_POSITIONS={config['max_positions']} alcanzado — "
              f"{len(candidates)} candidato(s) sin entrar hoy.")

    n_added = 0
    if apply:
        for c in to_add:
            tk = c["ticker"]
            entry_price = fetch_last_closes([tk]).get(tk)
            ptf["positions"].append({
                "ticker":       tk,
                "entry_date":   today,
                "entry_price":  entry_price,
                "size_pct":     config["size_pct"],
                "konc_d_trend_at_entry":          c["konc_d_trend"],
                "konc_d_trend_ma_at_entry":       c["konc_d_trend_ma"],
                "konc_d_trend_pctile252_at_entry": c["konc_d_trend_pctile252"],
                "konc_d_rsi14_at_entry":          c["konc_d_rsi14"],
            })
            n_added += 1
            print(f"  [{name}] SELECT {tk}: trend={c['konc_d_trend']:.2f} cruza al alza "
                  f"trend_ma={c['konc_d_trend_ma']:.2f} (pctile252={c['konc_d_trend_pctile252']:.1f}, "
                  f"rsi14={c['konc_d_rsi14']:.1f})")

    return {
        "portfolio": name, "date": today, "dry_run": not apply,
        "n_candidates": len(candidates), "n_added": n_added, "n_closed": len(closed),
        "added": [c["ticker"] for c in to_add], "closed": [c["ticker"] for c in closed],
    }


def run(apply: bool) -> int:
    today = str(date.today())
    koncorde = _load(KONCORDE_JSON)
    koncorde_out = koncorde.get("tickers", {})
    if not koncorde_out:
        print("koncorde_data.json vacío o no encontrado — corre koncorde_calculator.py primero.")
        return 1

    picks = _load(PICKS_JSON)
    if not isinstance(picks, dict):
        picks = {}
    universe_map = _load_universe_map()

    summaries = [run_for_config(picks, koncorde_out, universe_map, today, apply, cfg)
                 for cfg in CONFIGS]

    if not apply:
        print("\nDry-run (sin --apply): no se ha escrito ai_picks.json.")
        for s in summaries:
            _append_jsonl(LOG_PATH, s)
        return 0

    # Persistir siempre que --apply esté activo, aunque no haya cambios hoy —
    # así ambas carteras aparecen en el dashboard desde el primer run, incluso
    # vacías (mismo criterio que mirror_portfolio.py). Antes de este refactor
    # a multi-config esto se escribía justo después de las salidas; ahora se
    # hace una sola vez al final para las dos variantes a la vez.
    _write_json(PICKS_JSON, picks)
    for s in summaries:
        _append_jsonl(LOG_PATH, s)

    for s in summaries:
        print(f"\n[{s['portfolio']}] {s['n_added']} nueva(s) posición(es) añadida(s), "
              f"{s['n_closed']} cerrada(s).")
    return 0


if __name__ == "__main__":
    sys.exit(run(apply="--apply" in sys.argv))
