"""
Snapshot diario de cadenas de opciones de ETFs inversos/apalancados (UVXY, SQQQ,
GLL, BOIL) para estudiar la venta de prima sobre instrumentos con decay
estructural. Solo observación: no es señal, no toca carteras.

Por qué existe: yfinance solo da la cadena ACTUAL (sin IV histórica), así que la
única forma de tener IV rank, skew y spreads propios es guardarlos cada día.
La estrategia candidata (tuit de reversión del VIX con UVXY) = put comprada /
put spread + call vendida lejos; el valor está en el skew de calls y en la IV
respecto a la volatilidad realizada, no en el precio del subyacente.

Salidas (docs/data):
  inverse_etf_options_summary.jsonl  — una fila por ticker/día: spot, RV20/60, y por
      vencimiento (7-60 DTE): ATM IV, IV put ~80% y call ~120% del spot, skew,
      spread bid-ask relativo medio cerca del ATM, OI total.
  inverse_etf_options_chains.jsonl   — cadena comprimida (strikes 50%-200% del spot
      con bid/ask/IV/OI/volumen) para reconstruir estructuras a posteriori.
Dedup por ticker+fecha ET (se conserva la primera fila válida del día).

Uso:
  py -3 scripts/inverse_etf_options_snapshot.py            # solo en ventana de mercado
  py -3 scripts/inverse_etf_options_snapshot.py --force
  py -3 scripts/inverse_etf_options_snapshot.py --dry-run --force
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
SUMMARY = DATA / "inverse_etf_options_summary.jsonl"
CHAINS = DATA / "inverse_etf_options_chains.jsonl"

ET = ZoneInfo("America/New_York")
TICKERS = ["UVXY", "SQQQ", "GLL", "BOIL"]
DTE_MIN, DTE_MAX = 7, 120   # hasta 120 DTE: la jugada de put a 2-3 meses necesita la IV de esos plazos
MONEYNESS_MIN, MONEYNESS_MAX = 0.5, 2.0   # strikes guardados en la cadena
IV_MIN = 0.02                              # yfinance devuelve ~1e-5 en contratos muertos
WINDOW_START, WINDOW_END = (15, 30), (21, 0)


def in_window(now_et: datetime) -> bool:
    if now_et.weekday() >= 5:
        return False
    return WINDOW_START <= (now_et.hour, now_et.minute) <= WINDOW_END


def _load_keys(path: Path) -> set[tuple[str, str]]:
    keys = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    keys.add((r["ticker"], r["date"]))
                except Exception:
                    pass
    return keys


def _realized_vol(closes, n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(252), 4)


def _nearest(rows: list[dict], target: float) -> dict | None:
    return min(rows, key=lambda r: abs(r["strike"] - target)) if rows else None


def _clean(df, spot: float, kind: str) -> list[dict]:
    out = []
    for r in df.itertuples():
        k = float(r.strike)
        if not (spot * MONEYNESS_MIN <= k <= spot * MONEYNESS_MAX):
            continue
        iv = float(r.impliedVolatility) if r.impliedVolatility == r.impliedVolatility else 0.0
        bid = float(r.bid) if r.bid == r.bid else 0.0
        ask = float(r.ask) if r.ask == r.ask else 0.0
        oi = int(r.openInterest) if r.openInterest == r.openInterest else 0
        vol = int(r.volume) if r.volume == r.volume else 0
        if oi == 0 and bid == 0 and ask == 0 and vol == 0:
            continue
        out.append({"strike": k, "cp": kind, "bid": round(bid, 3), "ask": round(ask, 3),
                    "iv": round(iv, 4) if iv >= IV_MIN else None, "oi": oi, "vol": vol})
    return out


def snapshot_ticker(tk: str, today: str, now_et: datetime):
    import yfinance as yf
    t = yf.Ticker(tk)
    hist = t.history(period="6mo", auto_adjust=False)
    if hist.empty:
        raise RuntimeError("sin histórico de precio")
    closes = [float(x) for x in hist["Close"].dropna()]
    spot = closes[-1]

    expiries_summary, expiries_chain = [], []
    for exp in t.options:
        dte = (date.fromisoformat(exp) - now_et.date()).days
        if dte < DTE_MIN or dte > DTE_MAX:
            continue
        ch = t.option_chain(exp)
        calls, puts = _clean(ch.calls, spot, "C"), _clean(ch.puts, spot, "P")
        if not calls and not puts:
            continue
        valid_c = [r for r in calls if r["iv"]]
        valid_p = [r for r in puts if r["iv"]]
        atm_c, atm_p = _nearest(valid_c, spot), _nearest(valid_p, spot)
        atm_iv = None
        if atm_c and atm_p:
            atm_iv = round((atm_c["iv"] + atm_p["iv"]) / 2, 4)
        c120, p80 = _nearest(valid_c, spot * 1.2), _nearest(valid_p, spot * 0.8)
        near = [r for r in calls + puts if abs(r["strike"] / spot - 1) <= 0.1 and r["ask"] > 0]
        spreads = [(r["ask"] - r["bid"]) / ((r["ask"] + r["bid"]) / 2)
                   for r in near if (r["ask"] + r["bid"]) > 0]
        expiries_summary.append({
            "expiry": exp, "dte": dte, "atm_iv": atm_iv,
            "iv_put_80": p80["iv"] if p80 else None, "strike_put_80": p80["strike"] if p80 else None,
            "iv_call_120": c120["iv"] if c120 else None, "strike_call_120": c120["strike"] if c120 else None,
            "call_put_skew": round(c120["iv"] - p80["iv"], 4) if (c120 and p80) else None,
            "rel_spread_near_atm": round(sum(spreads) / len(spreads), 4) if spreads else None,
            "oi_calls": sum(r["oi"] for r in calls), "oi_puts": sum(r["oi"] for r in puts),
        })
        expiries_chain.append({"expiry": exp, "dte": dte, "contracts": calls + puts})

    if not expiries_summary:
        raise RuntimeError("sin vencimientos en el rango DTE")
    # Sin bid/ask reales (mercado cerrado) la IV de yfinance es ruido (~0.03):
    # no se guarda, para no bloquear con el dedup la fila buena del día.
    if all(e["rel_spread_near_atm"] is None for e in expiries_summary):
        raise RuntimeError("sin cotizaciones bid/ask (mercado cerrado) — no se guarda")
    base = {"date": today, "ticker": tk, "spot": round(spot, 4), "collected_at": now_et.isoformat()}
    summary = {**base, "rv20": _realized_vol(closes, 20), "rv60": _realized_vol(closes, 60),
               "expiries": expiries_summary}
    chain = {**base, "expiries": expiries_chain}
    return summary, chain


def main() -> int:
    force, dry = "--force" in sys.argv, "--dry-run" in sys.argv
    now_et = datetime.now(ET)
    today = now_et.date().isoformat()
    if not force and not in_window(now_et):
        print(f"Fuera de ventana ({now_et:%a %H:%M} ET) — nada que hacer (usa --force).")
        return 0

    done = _load_keys(SUMMARY)
    new_s, new_c = [], []
    for tk in TICKERS:
        if (tk, today) in done:
            print(f"{tk}: ya hay fila de hoy — omitido")
            continue
        try:
            s, c = snapshot_ticker(tk, today, now_et)
        except Exception as e:  # nunca tumba el pipeline
            print(f"{tk}: error {type(e).__name__}: {e}")
            continue
        e0 = s["expiries"][0]
        print(f"{tk}: spot={s['spot']} rv20={s['rv20']} rv60={s['rv60']} "
              f"venc={len(s['expiries'])} | 1º {e0['expiry']} atm_iv={e0['atm_iv']} "
              f"skew={e0['call_put_skew']} spread={e0['rel_spread_near_atm']}")
        new_s.append(s)
        new_c.append(c)

    if dry or not new_s:
        if dry:
            print("[dry-run] nada escrito")
        return 0
    with SUMMARY.open("a", encoding="utf-8") as f:
        for r in new_s:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with CHAINS.open("a", encoding="utf-8") as f:
        for r in new_c:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Escritas {len(new_s)} filas en {SUMMARY.name} y {CHAINS.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
