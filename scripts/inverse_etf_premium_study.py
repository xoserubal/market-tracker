"""
Estudio de primas de opciones de ETFs inversos (UVXY/SQQQ/GLL/BOIL).

Lee los snapshots diarios de inverse_etf_options_snapshot.py y responde, con la
estructura acordada (put/put spread a ~90 DTE + call spread vendido a ~30 DTE):

 1. Nivel de la prima: ATM IV, RV20, IV/RV20 y su percentil dentro del propio
    historial acumulado (solo fiable con >= 20 días de snapshots).
 2. Estructura de plazos: ratio IV 3m/1m y % de días con curva invertida
    (invertida = la put a 3 meses sale más barata por unidad de vol).
 3. ¿El decay ya está en el precio? Carry implícito por put-call parity en el
    ATM de ~90 DTE (F = K + C - P) frente a la deriva histórica mediana del ETF
    a ese plazo. Si lo que implica la cadena ya iguala a lo que históricamente
    cae el ETF, comprar la put no tiene ventaja; si la cadena implica menos caída
    que la histórica, hay hueco (con la cautela de que el pasado no garantiza).
 4. Estructura candidata con precios reales de la cadena más reciente
    (compra al ask, venta al bid) y su valor esperado sobre la distribución
    empírica de retornos del ETF (incondicional y, para UVXY, condicionada a la
    señal VIX>=25 + UVXY girando). Es una comparación prima-vs-historia, NO un
    backtest de opciones: sin IV histórica no se puede reproducir el P&L diario.

Solo observación. No toca carteras ni señales.

Uso:
  py -3 scripts/inverse_etf_premium_study.py                 # informe en consola
  py -3 scripts/inverse_etf_premium_study.py --save          # + docs/analysis/inverse_etf_premium_study.md
  py -3 scripts/inverse_etf_premium_study.py --no-fetch      # sin yfinance (omite las secciones 3b y 4)
  py -3 scripts/inverse_etf_premium_study.py --summary X --chains Y   # ficheros alternativos (tests)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
OUT_MD = ROOT / "docs" / "analysis" / "inverse_etf_premium_study.md"
TICKERS = ["UVXY", "SQQQ", "GLL", "BOIL"]
RF = 0.045                    # tipo libre de riesgo aproximado para el carry implícito
MIN_DAYS_PCTL = 20            # mínimo de días para hablar de percentil propio

# Estructura acordada (moneyness respecto al spot). Parámetros de primera pasada.
PUT_LONG_M, PUT_SHORT_M = 0.85, 0.60     # put spread a ~90 DTE: compra 85%, vende 60%
CALL_SHORT_M, CALL_LONG_M = 1.30, 2.00   # call spread a ~30 DTE: vende 130%, compra 200%
PUT_DTE, CALL_DTE = 90, 30


def read_jsonl(path: Path) -> list[dict]:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def pctile(series: list[float], v: float) -> float | None:
    s = [x for x in series if x is not None]
    if len(s) < MIN_DAYS_PCTL or v is None:
        return None
    return round(100 * sum(1 for x in s if x <= v) / len(s))


def pick_expiry(expiries: list[dict], target: int, tol: int, need_iv=True):
    c = [e for e in expiries if abs(e["dte"] - target) <= tol and (not need_iv or e.get("atm_iv") is not None)]
    return min(c, key=lambda e: abs(e["dte"] - target)) if c else None


def mid(c: dict):
    b, a = c.get("bid") or 0, c.get("ask") or 0
    return (a + b) / 2 if a > 0 and b > 0 else None


def nearest_strike(contracts: list[dict], cp: str, target: float, need_quote="mid"):
    pool = [c for c in contracts if c["cp"] == cp and (mid(c) is not None if need_quote == "mid" else True)]
    return min(pool, key=lambda c: abs(c["strike"] - target)) if pool else None


# ── 1-2: nivel y estructura de plazos (desde el resumen) ───────────────────────
def level_and_term(rows: list[dict]) -> dict:
    hist = []
    for r in rows:
        e30 = pick_expiry(r["expiries"], 30, 20)
        e90 = pick_expiry(r["expiries"], 90, 35)
        iv30 = e30["atm_iv"] if e30 else None
        iv90 = e90["atm_iv"] if e90 else None
        hist.append({
            "date": r["date"], "spot": r["spot"], "rv20": r.get("rv20"), "iv30": iv30, "iv90": iv90,
            "ivrv": (iv30 / r["rv20"]) if (iv30 and r.get("rv20")) else None,
            "ratio": (iv90 / iv30) if (iv30 and iv90) else None,
            "skew30": e30.get("call_put_skew") if e30 else None,
            "spread30": e30.get("rel_spread_near_atm") if e30 else None,
        })
    last = hist[-1]
    ratios = [h["ratio"] for h in hist if h["ratio"] is not None]
    return {
        "n_days": len(hist), "last": last,
        "pctl_iv30": pctile([h["iv30"] for h in hist], last["iv30"]),
        "pctl_ivrv": pctile([h["ivrv"] for h in hist], last["ivrv"]),
        "pct_inverted": round(100 * sum(1 for x in ratios if x < 1) / len(ratios)) if ratios else None,
        "hist": hist,
    }


# ── 3a: carry implícito (put-call parity) ─────────────────────────────────────
def implied_carry(chain_row: dict, target_dte=PUT_DTE, tol=35):
    spot = chain_row["spot"]
    ex = [e for e in chain_row["expiries"] if abs(e["dte"] - target_dte) <= tol]
    if not ex:
        return None
    e = min(ex, key=lambda x: abs(x["dte"] - target_dte))
    k = min({c["strike"] for c in e["contracts"]}, key=lambda s: abs(s - spot))
    call = next((c for c in e["contracts"] if c["cp"] == "C" and c["strike"] == k and mid(c) is not None), None)
    put = next((c for c in e["contracts"] if c["cp"] == "P" and c["strike"] == k and mid(c) is not None), None)
    if not call or not put:
        return None
    fwd = k + mid(call) - mid(put)
    t = e["dte"] / 365
    drift = fwd / spot - 1                       # deriva implícita hasta el vencimiento
    carry = drift - RF * t                       # lo que excede al tipo libre = coste de préstamo/contango
    return {"expiry": e["expiry"], "dte": e["dte"], "strike": k, "forward": round(fwd, 3),
            "implied_drift_pct": round(drift * 100, 1), "excess_over_rf_pct": round(carry * 100, 1),
            "annualized_excess_pct": round(carry / t * 100, 0)}


# ── 3b/4: histórico del ETF para comparar prima vs distribución ───────────────
def price_history(tk: str):
    import yfinance as yf
    h = yf.Ticker(tk).history(period="6y", auto_adjust=False)
    return [float(x) for x in h["Close"].dropna()], h.index


def forward_returns(closes: list[float], horizon: int, mask=None) -> list[float]:
    out = []
    for i in range(len(closes) - horizon):
        if mask is not None and not mask[i]:
            continue
        out.append(closes[i + horizon] / closes[i] - 1)
    return out


def uvxy_signal_mask(closes_len_hint: int):
    """Máscara de días con señal VIX>=25 + UVXY girando, reutilizando el backtest."""
    sys.path.insert(0, str(ROOT / "research" / "uvxy_spike_fade_v1"))
    import backtest as bt
    df = bt.features(bt.load())
    m = ((df["vix"] >= 25) & (df["d1"] < 0) & (df["dhist"] < 0)).fillna(False)
    return df, m


def put_spread_payoff(ret: float, k_long: float, k_short: float, s0: float) -> float:
    st = s0 * (1 + ret)
    return max(k_long - st, 0) - max(k_short - st, 0)


def call_spread_loss(ret: float, k_short: float, k_long: float, s0: float) -> float:
    st = s0 * (1 + ret)
    return max(st - k_short, 0) - max(st - k_long, 0)     # lo que pagas como vendedor


def structure(chain_row: dict):
    s0 = chain_row["spot"]
    ep = pick_expiry(chain_row["expiries"], PUT_DTE, 35, need_iv=False)
    ec = pick_expiry(chain_row["expiries"], CALL_DTE, 20, need_iv=False)
    out = {"spot": s0, "put": None, "call": None}
    if ep:
        lo = nearest_strike(ep["contracts"], "P", s0 * PUT_LONG_M, need_quote="any")
        sh = nearest_strike(ep["contracts"], "P", s0 * PUT_SHORT_M, need_quote="any")
        if lo and sh and lo["strike"] > sh["strike"] and (lo.get("ask") or 0) > 0:
            debit = lo["ask"] - (sh.get("bid") or 0)
            out["put"] = {"expiry": ep["expiry"], "dte": ep["dte"], "long": lo["strike"], "short": sh["strike"],
                          "debit": round(debit, 3), "max_gain": round(lo["strike"] - sh["strike"] - debit, 3),
                          "long_ask": lo["ask"], "short_bid": sh.get("bid") or 0,
                          "rel_spread_long": round((lo["ask"] - (lo.get("bid") or 0)) / lo["ask"], 2)}
    if ec:
        sh = nearest_strike(ec["contracts"], "C", s0 * CALL_SHORT_M, need_quote="any")
        lo = nearest_strike(ec["contracts"], "C", s0 * CALL_LONG_M, need_quote="any")
        if sh and lo and lo["strike"] > sh["strike"] and (sh.get("bid") or 0) > 0:
            credit = sh["bid"] - (lo.get("ask") or 0)
            out["call"] = {"expiry": ec["expiry"], "dte": ec["dte"], "short": sh["strike"], "long": lo["strike"],
                           "credit": round(credit, 3), "max_loss": round(lo["strike"] - sh["strike"] - credit, 3),
                           "short_bid": sh["bid"], "long_ask": lo.get("ask") or 0}
    return out


def ev_vs_history(st: dict, closes: list[float], sig_mask=None, sig_closes=None):
    """Valor esperado de cada pata sobre retornos empíricos (por unidad de prima)."""
    res = {}
    s0 = st["spot"]
    if st["put"]:
        p = st["put"]
        h = round(p["dte"] / 365 * 252)
        for label, rets in (("incondicional", forward_returns(closes, h)),
                            ("señal VIX>=25+giro", forward_returns(sig_closes, h, sig_mask) if sig_mask is not None else [])):
            if len(rets) >= 8:
                pay = [put_spread_payoff(r, p["long"], p["short"], s0) for r in rets]
                res[f"put_{label}"] = {"n": len(rets), "ev_payoff": round(sum(pay) / len(pay), 3),
                                       "ev_net": round(sum(pay) / len(pay) - p["debit"], 3),
                                       "ratio": round(sum(pay) / len(pay) / p["debit"], 2) if p["debit"] > 0 else None,
                                       "p_profit": round(100 * sum(1 for x in pay if x > p["debit"]) / len(pay))}
    if st["call"]:
        c = st["call"]
        h = round(c["dte"] / 365 * 252)
        for label, rets in (("incondicional", forward_returns(closes, h)),
                            ("señal VIX>=25+giro", forward_returns(sig_closes, h, sig_mask) if sig_mask is not None else [])):
            if len(rets) >= 8:
                loss = [call_spread_loss(r, c["short"], c["long"], s0) for r in rets]
                pnl = [c["credit"] - x for x in loss]
                res[f"call_{label}"] = {"n": len(rets), "ev_pnl": round(sum(pnl) / len(pnl), 3),
                                        "p_max_loss": round(100 * sum(1 for x in loss if x >= c["long"] - c["short"] - 1e-9) / len(loss)),
                                        "worst": round(min(pnl), 3)}
    return res


def fmt(v, d=2, suf=""):
    return "—" if v is None else f"{v:.{d}f}{suf}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default=str(DATA / "inverse_etf_options_summary.jsonl"))
    ap.add_argument("--chains", default=str(DATA / "inverse_etf_options_chains.jsonl"))
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()

    summary = read_jsonl(Path(args.summary))
    chains = read_jsonl(Path(args.chains))
    lines = ["# Estudio de primas — ETFs inversos", ""]
    if not summary:
        msg = ("Sin snapshots todavía (inverse_etf_options_summary.jsonl vacío o inexistente). "
               "El snapshot solo escribe en horario de mercado (>= 15:30 ET); vuelve a ejecutar cuando haya datos.")
        print(msg)
        return 0

    days = sorted({r["date"] for r in summary})
    lines.append(f"Snapshots: {len(days)} día(s) ({days[0]} → {days[-1]}). "
                 f"{'⚠️ Muy pocos días: los percentiles propios no son fiables hasta ' + str(MIN_DAYS_PCTL) + '.' if len(days) < MIN_DAYS_PCTL else ''}")
    lines.append("")

    for tk in TICKERS:
        rows = sorted([r for r in summary if r["ticker"] == tk], key=lambda r: r["date"])
        if not rows:
            lines += [f"## {tk}", "Sin snapshots.", ""]
            continue
        lt = level_and_term(rows)
        L = lt["last"]
        lines += [f"## {tk} — último snapshot {L['date']} (spot {L['spot']})", "",
                  f"- IV ATM ~30d: **{fmt(L['iv30'] and L['iv30'] * 100, 0, '%')}** · RV20: {fmt(L['rv20'] and L['rv20'] * 100, 0, '%')} · "
                  f"IV/RV20: **{fmt(L['ivrv'])}** (percentil propio: {lt['pctl_ivrv'] if lt['pctl_ivrv'] is not None else 'n/d, pocos días'})",
                  f"- Plazos: IV ~90d {fmt(L['iv90'] and L['iv90'] * 100, 0, '%')} · ratio 3m/1m **{fmt(L['ratio'])}** "
                  f"({'invertida' if (L['ratio'] or 9) < 1 else 'normal'}); días con curva invertida: "
                  f"{fmt(lt['pct_inverted'], 0, '%')} de {lt['n_days']}",
                  f"- Skew call−put ~30d: {fmt(L['skew30'] and L['skew30'] * 100, 0, 'pp')} · spread bid-ask cerca del ATM: {fmt(L['spread30'] and L['spread30'] * 100, 0, '%')}", ""]

        crow = next((c for c in reversed(chains) if c["ticker"] == tk), None)
        if not crow:
            lines += ["_Sin cadena guardada para este ticker._", ""]
            continue

        carry = implied_carry(crow)
        closes = idx = None
        if not args.no_fetch:
            try:
                closes, idx = price_history(tk)
            except Exception as e:
                lines.append(f"_(sin histórico de precio: {type(e).__name__})_")
        if carry:
            line = (f"- **Carry implícito** (parity, {carry['expiry']}, {carry['dte']} DTE, strike {carry['strike']}): "
                    f"forward {carry['forward']} → deriva implícita **{carry['implied_drift_pct']}%** hasta el vencimiento "
                    f"(exceso sobre tipo libre {carry['excess_over_rf_pct']}% ≈ {carry['annualized_excess_pct']}% anualizado)")
            if closes:
                h = round(carry["dte"] / 365 * 252)
                rets = forward_returns(closes, h)
                if rets:
                    med = sorted(rets)[len(rets) // 2] * 100
                    line += (f"\n  - Deriva histórica mediana a {h} sesiones: **{med:.1f}%** (n={len(rets)}). "
                             f"{'La cadena ya descuenta buena parte del decay: poca ventaja en comprar la put.' if carry['implied_drift_pct'] <= med * 0.7 else 'La cadena implica menos caída que la histórica: hay hueco, con la cautela de que el pasado no garantiza.'}")
            lines.append(line)
        else:
            lines.append("- Carry implícito: no calculable (faltan cotizaciones call/put en el ATM de ~90 DTE).")

        st = structure(crow)
        lines.append("")
        lines.append("**Estructura candidata (precios de la cadena, compra al ask / venta al bid):**")
        if st["put"]:
            p = st["put"]
            lines.append(f"- Put spread {p['expiry']} ({p['dte']} DTE): compra {p['long']} / vende {p['short']} → débito **{p['debit']}** "
                         f"(máx. ganancia {p['max_gain']}; spread bid-ask de la pata comprada {int(p['rel_spread_long'] * 100)}%)")
        else:
            lines.append("- Put spread: sin cotizaciones utilizables a ~90 DTE.")
        if st["call"]:
            c = st["call"]
            lines.append(f"- Call spread vendido {c['expiry']} ({c['dte']} DTE): vende {c['short']} / compra {c['long']} → crédito **{c['credit']}** "
                         f"(pérdida máx. {c['max_loss']})")
        else:
            lines.append("- Call spread vendido: sin cotizaciones utilizables a ~30 DTE.")

        if closes and (st["put"] or st["call"]):
            sig_closes = sig_mask = None
            if tk == "UVXY":
                try:
                    df, m = uvxy_signal_mask(len(closes))
                    sig_closes, sig_mask = [float(x) for x in df["c"]], [bool(x) for x in m]
                except Exception as e:
                    lines.append(f"_(sin condicionar a la señal: {type(e).__name__})_")
            ev = ev_vs_history(st, closes, sig_mask, sig_closes)
            lines.append("")
            lines.append("**Prima vs distribución histórica de retornos** (al vencimiento, sin gestión intermedia; NO es un backtest de opciones):")
            for k, v in ev.items():
                if k.startswith("put_"):
                    lines.append(f"- Put spread, {k[4:]} (n={v['n']}): pago esperado {v['ev_payoff']} vs débito → EV neto **{v['ev_net']}** "
                                 f"(pago/débito {v['ratio']}), gana en el {v['p_profit']}% de los casos")
                else:
                    lines.append(f"- Call spread vendido, {k[5:]} (n={v['n']}): P&L esperado **{v['ev_pnl']}**, "
                                 f"pérdida máxima en el {v['p_max_loss']}% de los casos, peor caso {v['worst']}")
        lines.append("")

    lines += ["---", "Notas: umbrales y strikes (85%/60% put, 130%/200% call) de primera pasada, sin calibrar. "
              "Con pocos días de snapshots los percentiles y el % de curva invertida no son concluyentes. "
              "El valor esperado usa retornos reales del ETF, pero ignora la gestión intermedia, el early exercise y los costes de comisión. "
              "Las muestras son días solapados (ventanas de 21-63 sesiones): el n efectivo es mucho menor que el n nominal, y los eventos con señal se agrupan en pocos episodios."]
    text = "\n".join(lines)
    print(text)
    if args.save:
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text(text + "\n", encoding="utf-8")
        print(f"\nGuardado en {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
