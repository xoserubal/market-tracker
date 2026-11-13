"""
Tests de las reglas de elección de vencimiento/strike y de calificación de liquidez
del estudio de primas y del recomendador de ETFs inversos (2026-11-13). Sin red.

  py -3 scripts/test_inverse_etf_pricing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import inverse_etf_premium_study as ps          # noqa: E402
import inverse_etf_recommendations as rec       # noqa: E402

FAILS = []


def check(name, cond):
    print(("OK  " if cond else "FAIL") + "  " + name)
    if not cond:
        FAILS.append(name)


# ── is_monthly / pick_expiry ──────────────────────────────────────────────────
check("tercer viernes es mensual", ps.is_monthly("2026-12-18"))
check("semanal no es mensual", not ps.is_monthly("2026-12-11"))
check("15-ene-2027 (tercer viernes) es mensual", ps.is_monthly("2027-01-15"))

ex = [{"expiry": "2026-12-04", "dte": 21}, {"expiry": "2026-12-11", "dte": 28},
      {"expiry": "2026-12-18", "dte": 35}]
check("prefer_monthly elige el mensual aunque haya un semanal más cerca",
      ps.pick_expiry(ex, 30, 20, need_iv=False, prefer_monthly=True)["expiry"] == "2026-12-18")
check("sin prefer_monthly elige el más cercano",
      ps.pick_expiry(ex, 30, 20, need_iv=False)["expiry"] == "2026-12-11")
check("sin mensual en la tolerancia, cae al más cercano",
      ps.pick_expiry([{"expiry": "2026-12-11", "dte": 28}], 30, 20, need_iv=False,
                     prefer_monthly=True)["expiry"] == "2026-12-11")
# Jueves mensual solo si el viernes no cotiza (festivo).
check("jueves con viernes listado no es el mensual",
      ps.pick_expiry([{"expiry": "2027-03-18", "dte": 30}, {"expiry": "2027-03-19", "dte": 31}],
                     30, 20, need_iv=False, prefer_monthly=True)["expiry"] == "2027-03-19")
check("jueves sin viernes listado sí cuenta como mensual",
      ps.pick_expiry([{"expiry": "2027-03-18", "dte": 30}, {"expiry": "2027-03-12", "dte": 24}],
                     26, 20, need_iv=False, prefer_monthly=True)["expiry"] == "2027-03-18")

# ── liquid_strike ─────────────────────────────────────────────────────────────
# Caso real UVXY dic-26 (CBOE 2026-11-13): la call 34 es de relleno; la 35, líquida.
calls = [
    {"cp": "C", "strike": 33.0, "bid": 0.41, "ask": 1.00, "oi": 174},
    {"cp": "C", "strike": 34.0, "bid": 0.30, "ask": 0.97, "oi": 275},
    {"cp": "C", "strike": 35.0, "bid": 0.69, "ask": 0.85, "oi": 512},
    {"cp": "C", "strike": 36.0, "bid": 0.22, "ask": 0.93, "oi": 65},
]
check("elige el strike líquido de la banda, no el más cercano",
      ps.liquid_strike(calls, "C", 34.0)["strike"] == 35.0)
check("respeta exclude",
      ps.liquid_strike(calls, "C", 34.0, exclude=35.0)["strike"] in (33.0, 34.0, 36.0))
check("fuera de banda no devuelve nada", ps.liquid_strike(calls, "C", 60.0) is None)
one_sided = [{"cp": "P", "strike": 10.0, "bid": 0.0, "ask": 0.75, "oi": 204}]
check("sin cotización a doble cara, el más cercano que acepte",
      ps.liquid_strike(one_sided, "P", 10.2)["strike"] == 10.0)

# ── leg_price con precio de relleno ───────────────────────────────────────────
stub = {"cp": "P", "strike": 11.0, "bid": 0.01, "ask": 2.07}
px = rec.leg_price(stub, "sell")
check("pata vendida de relleno se valora al bid", abs(px["est"] - 0.01) < 1e-9)
px = rec.leg_price(stub, "buy")
check("pata comprada de relleno se valora al ask", abs(px["est"] - 2.07) < 1e-9)
normal = {"cp": "P", "strike": 15.0, "bid": 1.60, "ask": 1.98}
px = rec.leg_price(normal, "buy")
check("pata normal: precio medio + 25% del spread",
      abs(px["est"] - (1.79 + rec.SPREAD_HAIRCUT * 0.38)) < 1e-9)

# ── structure_spread_cost ─────────────────────────────────────────────────────
legs = [{"bid": 1.60, "ask": 1.98, "rel_spread": 0.21}, {"bid": 0.01, "ask": 2.07, "rel_spread": 1.98}]
cost = rec.structure_spread_cost(legs, 1.78)
check("la pata de relleno no cuenta como coste", abs(cost - 0.19 / 1.78) < 1e-9)
check("sin patas con cotización real → None",
      rec.structure_spread_cost([{"bid": 0.0, "ask": 0.75, "rel_spread": None}], 0.75) is None)
check("prima nula → None", rec.structure_spread_cost(legs, 0.0) is None)

ev_ok = {"ev_ret_pct": 20, "ev_pnl": 0.3, "p_max_loss": 1}
liquid = [{"oi": 500}]
check("coste bajo + EV bueno → ok", rec.grade("put_spread", ev_ok, liquid, -1, 0.10)[0] == "ok")
check("coste medio → marginal", rec.grade("put_spread", ev_ok, liquid, -1, 0.25)[0] == "marginal")
check("coste alto → evitar", rec.grade("put_spread", ev_ok, liquid, -1, 0.50)[0] == "avoid")
check("sin coste medible → evitar", rec.grade("put_spread", ev_ok, liquid, -1, None)[0] == "avoid")

print()
print(f"{'TODO OK' if not FAILS else f'{len(FAILS)} FALLOS'}")
sys.exit(1 if FAILS else 0)
