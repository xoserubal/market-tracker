"""
Trullás: ¿importa cómo se define la "divergencia de volumen" (tier T3)?
  Método A (producción): volumen de la vela EXACTA del pivote (vol[b] > vol[a]).
  Método B1 (ventana):   volumen máximo en [p-2, p+2] alrededor del pivote.
  Método B2 (tramo):     volumen máximo en el tramo de caída hacia el pivote, de [argmax(close) de las 20
                         barras previas, p].
Mismo universo/caché que research/trullas_divergence_backtest_v1 (118 tickers, 2019->hoy), sin look-ahead
(primera apertura accionable = b + PIVOT_WINDOW + 1), misma salida (stop pivote / TP 38.2% / time-stop 20).
T3 = RSI div + volumen div; T2 = RSI div sin volumen; T1 = solo MACD (el volumen solo cuenta con RSI).
Dos lecturas: (1) operaciones con entrada ejecutable (zona estricta 23-25% y flexible 20-25%);
(2) TODOS los pares de pivotes con divergencia MACD, retorno desde la primera apertura accionable a +21
sesiones (sin modelo de entrada: más muestra, descriptivo).
"""
import sys, json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "research" / "trullas_early_detector_v1"))
import backtest as B0
tl = B0.tl
cache = B0.load_cache()
OFF = tl.FIRST_ACTIONABLE_OFFSET

def vol_methods(vol, close, a, b):
    out = {"A": bool(vol[b] > vol[a])}
    def win(p): return vol[max(0, p - 2): p + 3].max()
    def leg(p):
        lo = max(0, p - 20)
        s = lo + int(np.argmax(close[lo:p])) if p > lo else p
        return vol[s:p + 1].max()
    out["B1"] = bool(win(b) > win(a))
    out["B2"] = bool(leg(b) > leg(a))
    return out

def tier_for(rsi_div, vol_ok):
    return 3 if (rsi_div and vol_ok) else (2 if rsi_div else 1)

def collect():
    trades, pairs = [], []
    for tk, df in cache.items():
        close = df["Close"].to_numpy(); open_ = df["Open"].to_numpy(); vol = df["Volume"].to_numpy()
        n = len(close)
        macd_arr = tl.macd_full(df["Close"])[0].to_numpy(); rsi_arr = tl.rsi(df["Close"]).to_numpy()
        piv = tl.find_pivots_low(close)
        for a, b in zip(piv, piv[1:]):
            ev = tl.evaluate_pivot_pair(close, macd_arr, rsi_arr, vol, a, b)
            if not ev.get("qualifies"): continue
            vm = vol_methods(vol, close, a, b)
            tiers = {m: tier_for(ev["rsi_div"], vm[m]) for m in vm}
            # (2) retorno descriptivo desde la primera apertura accionable
            s0 = b + OFF
            if s0 + 21 < n:
                pairs.append({"tk": tk, "tiers": tiers, "ret21": (close[s0 + 21] - open_[s0]) / open_[s0] * 100})
            # (1) operaciones con entrada ejecutable
            rng = close[a] - close[b]
            for zone, f in (("strict", tl.RETR_ENTRY_LOW), ("flex", tl.RETR_ENTRY_LOW_FLEX)):
                lo = close[b] + f * rng; hi = ev["entry_high"]; tp, stop = ev["tp"], ev["stop"]
                fill = None
                for j in range(b + OFF, min(b + 1 + tl.ENTRY_WINDOW_BARS, n)):
                    if open_[j] <= stop: break
                    if lo <= open_[j] <= hi: fill = j; break
                if fill is None: continue
                ep = open_[fill]; end = min(fill + tl.TIME_STOP_BARS, n); ex = None
                for k in range(fill, end):
                    if close[k] <= stop: ex, why = k, "stop"; break
                    if close[k] >= tp: ex, why = k, "tp"; break
                if ex is None: ex, why = end - 1, "time"
                trades.append({"tk": tk, "zone": zone, "tiers": tiers, "ret": (close[ex] - ep) / ep * 100, "why": why})
    return trades, pairs

def stats(rets):
    r = np.array(rets)
    if len(r) == 0: return "n=0"
    se = r.std(ddof=1) / np.sqrt(len(r)) if len(r) > 1 else float("nan")
    return f"n={len(r):3d} mean={r.mean():+6.2f}% (±{se:.2f}) med={np.median(r):+6.2f}% win={100*(r>0).mean():3.0f}%"

trades, pairs = collect()
print(f"pares con divergencia MACD (retorno 21s calculable): {len(pairs)} | operaciones ejecutables: {len(trades)}")
agree = {m: np.mean([p['tiers']['A'] == p['tiers'][m] for p in pairs]) * 100 for m in ('B1', 'B2')}
print(f"concordancia de tier A vs B1: {agree['B1']:.0f}% | A vs B2: {agree['B2']:.0f}%")
print("\n== (2) TODOS los pares, retorno a +21 sesiones desde la primera apertura accionable ==")
for m in ("A", "B1", "B2"):
    print(f"-- Método {m}")
    for t in (1, 2, 3):
        print(f"   T{t}: " + stats([p["ret21"] for p in pairs if p["tiers"][m] == t]))
    print(f"   T3 vs resto (diferencia de medias): "
          f"{np.mean([p['ret21'] for p in pairs if p['tiers'][m]==3]) - np.mean([p['ret21'] for p in pairs if p['tiers'][m]!=3]):+.2f}pp")
print("\n== (1) Operaciones con entrada ejecutable ==")
for zone in ("strict", "flex"):
    print(f"-- zona {zone}")
    for m in ("A", "B1", "B2"):
        row = " | ".join(f"T{t}: " + stats([x['ret'] for x in trades if x['zone']==zone and x['tiers'][m]==t]) for t in (2, 3))
        print(f"   {m}: {row}")
json.dump({"n_pairs": len(pairs), "n_trades": len(trades)}, open(Path(__file__).parent / "summary.json", "w"))
