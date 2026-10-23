"""
Estructuras de opciones candidatas para ETFs inversos (UVXY/SQQQ/GLL/BOIL).

Lee la última cadena guardada por inverse_etf_options_snapshot.py y, para cada
ETF, evalúa un MENÚ FIJO de estructuras (no optimizado: elegir "la mejor" sobre
la misma distribución con la que se mide su valor esperado sesgaría el
resultado a favor):

  Lado put  (~90 DTE, compra de bajista):  put spread 90/65, 85/60 (acordada),
                                           100/70 y put simple 85
  Lado call (~30 DTE, venta de prima):     call spread vendido 120/180,
                                           130/200 (acordado) y 150/250

(moneyness respecto al spot; los strikes se ajustan al más cercano cotizado).

Para cada estructura calcula prima (estimada / media / peor caso), riesgo y
ganancia máximos, breakeven, rentabilidad máxima y TAE simple, valor esperado
contra la distribución empírica de retornos del ETF a ese plazo (incondicional
y, solo para UVXY, condicionada a la señal VIX>=25 + UVXY girando), probabilidad
de ganar / de pérdida máxima y una tabla de escenarios al vencimiento.

NO es un backtest de opciones (no hay IV histórica): compara la prima de hoy con
lo que el ETF ha hecho históricamente. Muestras de días solapados -> el n
efectivo es mucho menor que el nominal (se informa de nº de episodios). Umbrales
de calificación de primera pasada, sin calibrar. Solo observación: no toca
carteras ni señales.

Salida: docs/data/inverse_etf_recommendations.json (lo lee inversos.html).

Uso:
  py -3 scripts/inverse_etf_recommendations.py            # escribe el JSON
  py -3 scripts/inverse_etf_recommendations.py --dry-run  # imprime, no escribe
  py -3 scripts/inverse_etf_recommendations.py --no-fetch # sin yfinance (sin EV)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
import inverse_etf_premium_study as ps  # noqa: E402  (reutiliza helpers, sin duplicarlos)

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
OUT = DATA / "inverse_etf_recommendations.json"
TICKERS = ["UVXY", "SQQQ", "GLL", "BOIL"]

PUT_DTE, PUT_TOL = 90, 35
CALL_DTE, CALL_TOL = 30, 20
# (id, etiqueta, moneyness largo, moneyness corto, es la estructura acordada)
PUT_SPREADS = [
    ("ps_cons", "Put spread conservador 90/65", 0.90, 0.65, False),
    ("ps_agreed", "Put spread acordado 85/60", 0.85, 0.60, True),
    ("ps_atm", "Put spread ATM 100/70", 1.00, 0.70, False),
]
PUT_SINGLE = ("p_85", "Put simple 85", 0.85)
CALL_SPREADS = [
    ("cs_near", "Call spread vendido 120/180", 1.20, 1.80, False),
    ("cs_agreed", "Call spread vendido 130/200", 1.30, 2.00, True),
    ("cs_far", "Call spread vendido 150/250", 1.50, 2.50, False),
]
SCENARIO_MOVES = [-70, -50, -30, -10, 0, 10, 30, 60, 100, 150]
SPREAD_HAIRCUT = 0.25     # precio estimado = media ± 25% del spread bid-ask
EPISODE_GAP = 10          # sesiones sin señal que separan dos episodios
SNAP_TOL = 0.12           # un strike cotizado solo vale si está a <=12% del strike objetivo (si no, el perfil no existe en esa cadena)


# ── Precios y liquidez de una pata ────────────────────────────────────────────
def leg_price(c: dict, side: str) -> dict | None:
    """Prima por acción de una pata. side: 'buy' (pagas) o 'sell' (cobras)."""
    bid, ask = c.get("bid") or 0.0, c.get("ask") or 0.0
    flags = []
    if side == "buy":
        if ask <= 0:
            return None
        worst = ask
        if bid > 0:
            mid = (bid + ask) / 2
            est = mid + SPREAD_HAIRCUT * (ask - bid)
        else:
            mid = est = ask
            flags.append("sin bid")
    else:
        if bid <= 0:
            return {"est": 0.0, "mid": 0.0, "worst": 0.0, "rel_spread": None,
                    "flags": ["sin bid: no se puede vender"], "ok": False}
        worst = bid
        if ask > 0:
            mid = (bid + ask) / 2
            est = mid - SPREAD_HAIRCUT * (ask - bid)
        else:
            mid = est = bid
    rel = ((ask - bid) / mid) if (bid > 0 and ask > 0 and mid > 0) else None
    return {"est": est, "mid": mid, "worst": worst, "rel_spread": rel, "flags": flags, "ok": True}


def snap(contracts: list[dict], cp: str, target: float, side: str, exclude: float | None = None):
    pool = [c for c in contracts if c["cp"] == cp and c["strike"] != exclude and leg_price(c, side) is not None
            and abs(c["strike"] / target - 1) <= SNAP_TOL]
    return min(pool, key=lambda c: abs(c["strike"] - target)) if pool else None


def leg_view(c: dict, side: str, px: dict) -> dict:
    return {"side": side, "cp": c["cp"], "strike": c["strike"], "bid": c.get("bid"), "ask": c.get("ask"),
            "oi": c.get("oi"), "vol": c.get("vol"), "iv": c.get("iv"),
            "rel_spread": None if px["rel_spread"] is None else round(px["rel_spread"], 2), "flags": px["flags"]}


# ── Payoffs y estadísticos ────────────────────────────────────────────────────
def pnl_put_spread(s_t, kl, ks, debit):
    return max(kl - s_t, 0) - max(ks - s_t, 0) - debit


def pnl_put(s_t, k, debit):
    return max(k - s_t, 0) - debit


def pnl_call_spread(s_t, ks, kl, credit):
    return credit - (max(s_t - ks, 0) - max(s_t - kl, 0))


def stats(pnls: list[float], capital: float, dte: int, max_loss_pnl: float) -> dict | None:
    if len(pnls) < 8 or capital <= 0:
        return None
    s = sorted(pnls)
    ev = sum(pnls) / len(pnls)
    return {
        "n": len(pnls), "ev_pnl": round(ev, 3), "ev_ret_pct": round(ev / capital * 100, 1),
        "tae_ev_pct": round(ev / capital * 365 / dte * 100, 0),
        "p_profit": round(100 * sum(1 for x in pnls if x > 0) / len(pnls)),
        "p_max_loss": round(100 * sum(1 for x in pnls if x <= max_loss_pnl + 1e-9) / len(pnls)),
        "p10": round(s[int(0.10 * (len(s) - 1))], 3), "worst": round(s[0], 3),
    }


def count_episodes(mask: list[bool], horizon: int) -> int:
    idx = [i for i, m in enumerate(mask[: max(len(mask) - horizon, 0)]) if m]
    if not idx:
        return 0
    return 1 + sum(1 for a, b in zip(idx, idx[1:]) if b - a > EPISODE_GAP)


# ── Calificación (primera pasada, sin calibrar) ───────────────────────────────
def grade(kind: str, ev: dict | None, legs: list[dict], max_loss_pnl: float) -> tuple[str, str]:
    rels = [l["rel_spread"] if l["rel_spread"] is not None else 1.0 for l in legs]
    worst_rel = max(rels)
    min_oi = min((l["oi"] or 0) for l in legs)
    reasons = []
    if ev is None:
        return "avoid", "sin distribución histórica para valorarla"
    if worst_rel > 0.75:
        reasons.append(f"spread bid-ask de {int(worst_rel * 100)}% en alguna pata")
    elif worst_rel > 0.35:
        reasons.append(f"spread bid-ask de {int(worst_rel * 100)}% (el precio real puede diferir mucho)")
    if min_oi < 10:
        reasons.append(f"open interest muy bajo ({min_oi})")
    elif min_oi < 50:
        reasons.append(f"open interest bajo ({min_oi})")
    if kind == "call_spread":
        good = ev["ev_pnl"] > 0 and ev["p_max_loss"] <= 5
        bad = ev["ev_pnl"] <= 0
        if ev["ev_pnl"] <= 0:
            reasons.append("valor esperado ≤ 0 (la prima no paga el riesgo histórico)")
        if ev["p_max_loss"] > 5:
            reasons.append(f"pérdida máxima en el {ev['p_max_loss']}% de los casos históricos")
    else:
        good = ev["ev_ret_pct"] >= 5
        bad = ev["ev_ret_pct"] < -10
        if ev["ev_ret_pct"] < 5:
            reasons.append(f"valor esperado {ev['ev_ret_pct']:+.0f}% sobre el capital (prima ya cara respecto al historial)")
    if worst_rel > 0.75 or min_oi < 10:
        bad = True
    if worst_rel > 0.35 or min_oi < 50:
        good = False
    g = "ok" if good else ("avoid" if bad else "marginal")
    return g, "; ".join(reasons) if reasons else "valor esperado positivo y cadena razonablemente líquida"


# ── Construcción de estructuras ───────────────────────────────────────────────
def build_structures(chain_row: dict, dists: dict) -> dict:
    s0 = chain_row["spot"]
    out = {"put": [], "call": []}
    ep = ps.pick_expiry(chain_row["expiries"], PUT_DTE, PUT_TOL, need_iv=False)
    ec = ps.pick_expiry(chain_row["expiries"], CALL_DTE, CALL_TOL, need_iv=False)

    def finish(base: dict, capital: float, max_loss_pnl: float, pnl_fn, dte: int):
        base["capital_at_risk"] = round(capital, 3)
        evs = {}
        for basis, rets in dists.items():
            h = round(dte / 365 * 252)
            r = rets.get(h)
            evs[basis] = stats([pnl_fn(s0 * (1 + x)) for x in r], capital, dte, max_loss_pnl) if r else None
        base["ev_by_basis"] = evs
        base["payoff"] = [{"move_pct": m, "pnl": round(pnl_fn(s0 * (1 + m / 100)), 3)} for m in SCENARIO_MOVES]
        return base

    if ep:
        cons = ep["contracts"]
        dte = ep["dte"]
        for pid, label, mlong, mshort, agreed in PUT_SPREADS:
            lo = snap(cons, "P", s0 * mlong, "buy")
            sh = snap(cons, "P", s0 * mshort, "sell", exclude=lo["strike"] if lo else None)
            if not lo or not sh or lo["strike"] <= sh["strike"]:
                continue
            pl, psh = leg_price(lo, "buy"), leg_price(sh, "sell")
            debit = pl["est"] - psh["est"]
            width = lo["strike"] - sh["strike"]
            if debit <= 0 or debit >= width * 0.98:
                continue
            legs = [leg_view(lo, "buy", pl), leg_view(sh, "sell", psh)]
            kl, ks = lo["strike"], sh["strike"]
            base = {
                "id": pid, "kind": "put_spread", "label": label, "agreed": agreed,
                "expiry": ep["expiry"], "dte": dte, "strikes": {"long": kl, "short": ks}, "legs": legs,
                "premium": {"type": "debit", "est": round(debit, 3), "mid": round(pl["mid"] - psh["mid"], 3),
                            "worst": round(pl["worst"] - psh["worst"], 3)},
                "max_gain": round(width - debit, 3), "max_loss": round(debit, 3),
                "breakeven": round(kl - debit, 3), "breakeven_pct": round((kl - debit) / s0 * 100 - 100, 1),
                "ret_max_pct": round((width - debit) / debit * 100, 0),
                "tae_max_pct": round((width - debit) / debit * 365 / dte * 100, 0),
            }
            finish(base, debit, -debit, lambda st, kl=kl, ks=ks, d=debit: pnl_put_spread(st, kl, ks, d), dte)
            out["put"].append(base)
        pid, label, m = PUT_SINGLE
        lo = snap(cons, "P", s0 * m, "buy")
        if lo:
            pl = leg_price(lo, "buy")
            debit, k = pl["est"], lo["strike"]
            if debit > 0:
                base = {
                    "id": pid, "kind": "put", "label": label, "agreed": False,
                    "expiry": ep["expiry"], "dte": dte, "strikes": {"long": k, "short": None},
                    "legs": [leg_view(lo, "buy", pl)],
                    "premium": {"type": "debit", "est": round(debit, 3), "mid": round(pl["mid"], 3), "worst": round(pl["worst"], 3)},
                    "max_gain": round(k - debit, 3), "max_loss": round(debit, 3),
                    "breakeven": round(k - debit, 3), "breakeven_pct": round((k - debit) / s0 * 100 - 100, 1),
                    "ret_max_pct": round((k - debit) / debit * 100, 0),
                    "tae_max_pct": round((k - debit) / debit * 365 / dte * 100, 0),
                }
                finish(base, debit, -debit, lambda st, k=k, d=debit: pnl_put(st, k, d), dte)
                out["put"].append(base)

    if ec:
        cons = ec["contracts"]
        dte = ec["dte"]
        for cid, label, mshort, mlong, agreed in CALL_SPREADS:
            sh = snap(cons, "C", s0 * mshort, "sell")
            lo = snap(cons, "C", s0 * mlong, "buy", exclude=sh["strike"] if sh else None)
            if not sh or not lo or lo["strike"] <= sh["strike"]:
                continue
            psh, pl = leg_price(sh, "sell"), leg_price(lo, "buy")
            credit = psh["est"] - pl["est"]
            width = lo["strike"] - sh["strike"]
            if credit <= 0:
                continue
            legs = [leg_view(sh, "sell", psh), leg_view(lo, "buy", pl)]
            ks, kl = sh["strike"], lo["strike"]
            max_loss = width - credit
            base = {
                "id": cid, "kind": "call_spread", "label": label, "agreed": agreed,
                "expiry": ec["expiry"], "dte": dte, "strikes": {"long": kl, "short": ks}, "legs": legs,
                "premium": {"type": "credit", "est": round(credit, 3), "mid": round(psh["mid"] - pl["mid"], 3),
                            "worst": round(psh["worst"] - pl["worst"], 3)},
                "max_gain": round(credit, 3), "max_loss": round(max_loss, 3),
                "breakeven": round(ks + credit, 3), "breakeven_pct": round((ks + credit) / s0 * 100 - 100, 1),
                "ret_max_pct": round(credit / max_loss * 100, 1),
                "tae_max_pct": round(credit / max_loss * 365 / dte * 100, 0),
            }
            finish(base, max_loss, -max_loss, lambda st, ks=ks, kl=kl, c=credit: pnl_call_spread(st, ks, kl, c), dte)
            out["call"].append(base)

    # Calificación sobre la base primaria (se fija fuera, en `primary`)
    return out


def distributions(tk: str, no_fetch: bool) -> tuple[dict, dict, str]:
    """Retornos empíricos por horizonte en sesiones: {basis: {h: [ret,...]}}."""
    info = {"uncond": None, "signal": None, "error": None}
    if no_fetch:
        return {}, info, "uncond"
    try:
        closes, _ = ps.price_history(tk)
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
        return {}, info, "uncond"
    horizons = {round(d / 365 * 252) for d in (PUT_DTE - PUT_TOL, PUT_DTE - 5, PUT_DTE, PUT_DTE + 10, CALL_DTE - 10, CALL_DTE, CALL_DTE + 10)}
    horizons |= set(range(30, 80))      # cubre cualquier vencimiento elegido
    horizons |= set(range(10, 30))
    dists = {"uncond": {h: ps.forward_returns(closes, h) for h in horizons}}
    info["uncond"] = {"n_at_60d": len(dists["uncond"].get(59, []))}
    primary = "uncond"
    if tk == "UVXY":
        try:
            df, m = ps.uvxy_signal_mask(len(closes))
            sc, mask = [float(x) for x in df["c"]], [bool(x) for x in m]
            dists["signal"] = {h: ps.forward_returns(sc, h, mask) for h in horizons}
            info["signal"] = {"n_at_60d": len(dists["signal"].get(59, [])),
                              "episodes_at_60d": count_episodes(mask, 59), "rule": "VIX>=25 y UVXY girando a la baja"}
            primary = "signal"
        except Exception as e:
            info["error"] = f"señal: {type(e).__name__}: {e}"
    return dists, info, primary


def recommend(tk: str, chain_row: dict, summary_row: dict | None, no_fetch: bool) -> dict:
    dists, dinfo, primary = distributions(tk, no_fetch)
    st = build_structures(chain_row, dists)
    for side in ("put", "call"):
        for s in st[side]:
            ev = s["ev_by_basis"].get(primary) or s["ev_by_basis"].get("uncond")
            s["primary_basis"] = primary if s["ev_by_basis"].get(primary) else ("uncond" if ev else None)
            s["grade"], s["grade_reason"] = grade(s["kind"], ev, s["legs"], -s["max_loss"])
            rels = [l["rel_spread"] if l["rel_spread"] is not None else 1.0 for l in s["legs"]]
            # Con spreads >75% o OI <10 la prima estimada es ruido: el EV/TAE no se presenta como cifra.
            s["ev_reliable"] = max(rels) <= 0.75 and min((l["oi"] or 0) for l in s["legs"]) >= 10
    agreed_put = next((s for s in st["put"] if s["id"] == "ps_agreed"), None)
    agreed_call = next((s for s in st["call"] if s["id"] == "cs_agreed"), None)
    notes = []
    if not st["put"]:
        notes.append("Sin estructura de puts utilizable a ~90 DTE (faltan cotizaciones).")
    if not st["call"]:
        notes.append("Sin call spread vendido utilizable a ~30 DTE (cadena sin cotizaciones o crédito ≤ 0).")
    if primary != "signal":
        notes.append("Valor esperado medido contra el historial completo del ETF; la regla de señal de este ETF no está calibrada.")
    live = chain_row.get("source") == "ibkr_tws"
    dtype = chain_row.get("data_type")
    try:
        t = datetime.fromisoformat(chain_row["collected_at"])
        after_hours = t.weekday() >= 5 or t.hour * 60 + t.minute > 16 * 60 + 15 or t.hour * 60 + t.minute < 9 * 60 + 30
        if live and dtype == "delayed":
            notes.append("Cadena de IBKR con datos RETRASADOS (~15 min): no hay suscripción de opciones en tiempo real. "
                         "Los precios pueden haberse movido; confirma en la ventana de órdenes antes de operar.")
        elif live and dtype == "frozen":
            notes.append("Cadena de IBKR con datos CONGELADOS (último cierre): el mercado de opciones no está operando ahora.")
        elif live and after_hours:
            notes.append(f"Cadena de IBKR pedida a las {t:%H:%M} ET, con el mercado de opciones cerrado: cotizaciones de cierre, no ejecutables.")
        elif not live and t.hour * 60 + t.minute > 16 * 60 + 15:
            notes.append(f"Cadena tomada a las {t:%H:%M} ET, fuera de horario de opciones: bid/ask residuales con spreads exagerados; "
                         "las primas son orientativas hasta contrastarlas con la cadena en vivo del broker.")
    except Exception:
        pass
    carry = ps.implied_carry(chain_row)
    if carry and dists:
        h = round(carry["dte"] / 365 * 252)
        for basis, key in (("uncond", "hist_median_pct"), ("signal", "signal_median_pct")):
            r = dists.get(basis, {}).get(h)
            if r:
                carry[key] = round(sorted(r)[len(r) // 2] * 100, 1)
    return {
        "chain_date": chain_row["date"], "collected_at": chain_row.get("collected_at"), "spot": chain_row["spot"],
        "live": live, "source": chain_row.get("source", "yfinance_snapshot"), "data_type": dtype,
        "primary_basis": primary, "distributions": dinfo, "implied_carry": carry,
        "put": st["put"], "call": st["call"],
        "agreed": {"put": agreed_put["id"] if agreed_put else None, "call": agreed_call["id"] if agreed_call else None,
                   "put_grade": agreed_put["grade"] if agreed_put else None,
                   "call_grade": agreed_call["grade"] if agreed_call else None},
        "notes": notes,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--chains", default=str(DATA / "inverse_etf_options_chains.jsonl"))
    ap.add_argument("--summary", default=str(DATA / "inverse_etf_options_summary.jsonl"))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--live-chain", help="JSON con UNA fila de cadena (esquema del jsonl) pedida en vivo a IBKR; "
                                         "sustituye al jsonl guardado y exige --only")
    ap.add_argument("--only", help="solo este ticker")
    args = ap.parse_args()

    if args.live_chain:
        if not args.only:
            print("--live-chain exige --only TICKER", file=sys.stderr)
            return 2
        chains = [json.loads(Path(args.live_chain).read_text(encoding="utf-8"))]
        summary = []
    else:
        chains = ps.read_jsonl(Path(args.chains))
        summary = ps.read_jsonl(Path(args.summary))
    if not chains:
        print("Sin cadenas guardadas todavía: nada que recomendar.")
        return 0
    result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tickers": {},
              "method": {"price_est": f"media ± {int(SPREAD_HAIRCUT * 100)}% del spread bid-ask",
                         "ev": "valor esperado al vencimiento contra retornos históricos del ETF (sin gestión intermedia; NO es backtest de opciones)",
                         "tae": "TAE simple = rentabilidad × 365 / DTE (ilustrativa, no compuesta)",
                         "grades": "ok / marginal / avoid: umbrales de primera pasada, sin calibrar"}}
    for tk in ([args.only] if args.only else TICKERS):
        crow = next((c for c in reversed(chains) if c["ticker"] == tk), None)
        if not crow:
            continue
        srow = next((s for s in reversed(summary) if s["ticker"] == tk and s["date"] == crow["date"]), None)
        try:
            result["tickers"][tk] = recommend(tk, crow, srow, args.no_fetch)
        except Exception as e:
            result["tickers"][tk] = {"error": f"{type(e).__name__}: {e}"}
            print(f"[{tk}] error: {e}", file=sys.stderr)
        r = result["tickers"][tk]
        if "error" not in r:
            print(f"[{tk}] cadena {r['chain_date']} · puts {len(r['put'])} · calls {len(r['call'])} · base {r['primary_basis']} · "
                  f"acordadas: put={r['agreed']['put_grade']} call={r['agreed']['call_grade']}")
    if args.dry_run:
        print(json.dumps(result, indent=1, ensure_ascii=False)[:6000])
        return 0
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Guardado {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
