"""
Tests de las funciones críticas de relative_family_falsification_test.py,
antes de confiar en ellas sobre datos reales. Sin pytest (mismo patrón que
scripts/test_relative_flow_lib.py).

    py -3 research/relative_flow_family_test_v1/test_relative_family_falsification.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from relative_family_falsification_test import (  # noqa: E402
    build_exposure_mask, cagr, extract_trades, inverted_mask, lagged_mask,
    max_drawdown,
)

_passed = 0
_failed: list[str] = []


def check(name, got, want):
    global _passed
    ok = got == want
    if isinstance(got, float) and isinstance(want, float):
        ok = abs(got - want) < 1e-9
    if ok:
        _passed += 1
    else:
        _failed.append(f"{name}\n     esperado: {want!r}\n     obtenido: {got!r}")


def check_close(name, got, want, tol=1e-6):
    global _passed
    if abs(got - want) <= tol:
        _passed += 1
    else:
        _failed.append(f"{name}\n     esperado: {want!r} (tol {tol})\n     obtenido: {got!r}")


# ── build_exposure_mask: el día de entrada NO cuenta, el de salida SÍ ──
scores = np.array([1.0, 2.0, 3.5, 6.0, 2.0])
prices = np.array([100.0, 101.0, 102.0, 105.0, 98.0])
exposed = build_exposure_mask(scores)
check("exposure mask: entrada en idx2, no expuesto ese dia", exposed[2], False)
check("exposure mask: expuesto idx3 (dentro)", exposed[3], True)
check("exposure mask: expuesto idx4 (dia de salida)", exposed[4], True)
check("exposure mask: no expuesto antes de entrar", list(exposed[:2]), [False, False])

daily_ret = np.diff(prices) / prices[:-1]
daily_ret = np.concatenate([[0.0], daily_ret])
compounded = np.prod(1 + daily_ret[exposed]) - 1
expected = prices[4] / prices[2] - 1
check_close("composicion de dias expuestos == price[exit]/price[entry]-1", compounded, expected)

# ── extract_trades debe coincidir exactamente con build_exposure_mask ──
dates = np.array(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"], dtype="datetime64[D]")
trades = extract_trades(dates, scores, prices)
check("extract_trades: 1 operacion detectada", len(trades), 1)
check("extract_trades: entrada correcta", trades[0]["entry_date"], "2024-01-03")
check("extract_trades: salida correcta", trades[0]["exit_date"], "2024-01-05")
check("extract_trades: bars == dias expuestos", trades[0]["bars"], int(exposed.sum()))
check_close("extract_trades: ret_pct coincide con la composicion", trades[0]["ret_pct"], expected * 100)

# ── posicion abierta al final (sin señal de salida) ──
scores2 = np.array([1.0, 2.0, 3.5, 6.0, 7.0])  # nunca cruza salida
exposed2 = build_exposure_mask(scores2)
check("posicion abierta: expuesto desde idx3 en adelante", list(exposed2[3:]), [True, True])
check("posicion abierta: no expuesto en idx0-2", list(exposed2[:3]), [False, False, False])
trades2 = extract_trades(dates, scores2, prices)
check("posicion abierta: 1 trade marcado closed=False", trades2[0]["closed"], False)
check("posicion abierta: exit_date = ultimo dia disponible", trades2[0]["exit_date"], "2024-01-05")

# ── reentrada tras salida ──
scores3 = np.array([1.0, 3.5, 2.0, 4.0, 9.0])  # entra idx1, sale idx2, reentra idx3(ya>=3? necesita cruce)
# prev=2(idx1 score=3.5 -> ya en Leader/Improving), idx2: prev=3.5,cur=2 -> exit (prev>=3,cur<3) -> exposed[2]=True, sale
# idx3: prev=2(no valido para reentrada, prev<3, cur=4>=3 -> entra de nuevo) in_pos=True, just_entered, exposed[3]=False
# idx4: prev=4,cur=9 -> sigue dentro, exposed[4]=True
exposed3 = build_exposure_mask(scores3)
check("reentrada: expuesto idx2 (salida)", exposed3[2], True)
check("reentrada: no expuesto idx3 (nueva entrada)", exposed3[3], False)
check("reentrada: expuesto idx4", exposed3[4], True)
trades3 = extract_trades(dates, scores3, prices)
check("reentrada: 2 operaciones detectadas", len(trades3), 2)

# ── inverted_mask ──
check("inverted: es el complemento exacto", list(inverted_mask(exposed)), list(~exposed))

# ── lagged_mask ──
m = np.array([False, False, True, True, False])
lag1 = lagged_mask(m, 1)
check("lag+1: retrasa un dia", list(lag1), [False, False, False, True, True])
lag_m1 = lagged_mask(m, -1)
check("lag-1: adelanta un dia (control anti-lookahead)", list(lag_m1), [False, True, True, False, False])

# ── cagr ──
check_close("cagr: 10% en 1 anio natural (365 dias) ~= 10%", cagr(0.10, 365), 0.10, tol=0.001)
check_close("cagr: 21% en 730 dias con base 365.25 (no 365)", cagr(0.21, 730), (1.21 ** (365.25 / 730) - 1), tol=1e-9)
check("cagr: dias<=0 -> None", cagr(0.10, 0), None)
check("cagr: retorno total -100% -> None (evita log de 0/negativo)", cagr(-1.0, 365), None)

# ── max_drawdown ──
eq = np.array([1.0, 1.1, 1.05, 0.9, 0.95, 1.2])
check_close("max_drawdown: caida real desde el pico 1.1 a 0.9", max_drawdown(eq), 0.9 / 1.1 - 1)
eq_flat = np.array([1.0, 1.0, 1.0])
check("max_drawdown: sin caida -> 0", max_drawdown(eq_flat), 0.0)


print(f"\n{_passed} tests pasados, {len(_failed)} fallidos")
if _failed:
    print("\nFALLOS:")
    for f in _failed:
        print(f"  - {f}")
    sys.exit(1)
