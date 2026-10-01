"""
Tests de regresión para flow_state_lib.py — sin pytest, mismo patrón que
test_cava_mapping.py/test_numeric_claims_validation.py. Cubre:
  1. Las funciones puras (series_metrics, theme breadth, percentil ATR)
     con datos sintéticos.
  2. Los casos reales de la auditoría externa de 2026-10-01 contra el
     historial real de portfolio_daily_snapshot.jsonl/
     market_equities_daily_snapshot.jsonl, truncado a la fecha exacta en la
     que Sol etiquetó mal cada caso — para que este test falle si una
     futura edición del motor vuelve a dejar pasar un caso ya conocido como
     falso positivo, o rompe uno de los casos que debe seguir funcionando.

Ejecutar: py -3 scripts/test_flow_state_lib.py
"""
from __future__ import annotations

import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
import flow_state_lib as fsl

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FALLO: {name}" + (f" — {detail}" if detail else ""))


def row(date, flow=None, rsi=None, konc=None, atr=None, price=None, macd_hist=None, macd_hist_d1=None, m1=None):
    return {
        "date": date, "flowScore": flow, "rsi": rsi, "konc_alignment": konc,
        "atrPct": atr, "price": price, "macdHist": macd_hist, "macdHistDelta1": macd_hist_d1, "m1": m1,
    }


# ── 1. compute_series_metrics (sintético) ───────────────────────────────

def test_series_metrics_basic():
    rows = [row(f"2026-01-{i:02d}", flow=f) for i, f in enumerate(
        [-10, -8, -6, -4, -2, 2, 4, 6, 4, -2, -4], start=1)]
    out = fsl.compute_series_metrics(rows)
    # día 6 (flow=2): cruza de -2 a 2 -> zero_cross_up
    check("zero_cross_up en el día del cruce", out[5]["zero_cross_up"] is True)
    check("sin zero-cross en días anteriores", out[4]["zero_cross_up"] is False)
    # delta5 del día 6 = flow[6] - flow[1] = 2 - (-10) = 12
    check("delta5 calculado correctamente", out[5]["delta5"] == 12, f"got {out[5]['delta5']}")
    # día 10 (flow=-2): cruza de 4 a -2 -> zero_cross_down
    check("zero_cross_down detectado", out[9]["zero_cross_down"] is True)
    # flow_above_zero_days: días 6,7,8,9 tienen flow>0 (2,4,6,4), día 9 cuenta 4 consecutivos
    check("flow_above_zero_days racha correcta", out[8]["flow_above_zero_days"] == 4, f"got {out[8]['flow_above_zero_days']}")
    check("flow_above_zero_days se resetea tras cruce a negativo", out[9]["flow_above_zero_days"] == 0)


def test_series_metrics_persist_counts():
    # delta5 creciente 3 días seguidos, luego cae
    flows = [0, 0, 0, 0, 0, 1, 3, 6, 4]
    rows = [row(f"2026-02-{i:02d}", flow=f) for i, f in enumerate(flows, start=1)]
    out = fsl.compute_series_metrics(rows)
    # delta5 en índices 5,6,7,8 = flow[i]-flow[i-5]
    d5 = [r["delta5"] for r in out[5:]]
    check("delta5 serie calculada", d5 == [1, 3, 6, 4], f"got {d5}")
    check("persistencia delta5>0 cuenta las 4 sesiones", out[8]["delta5_persist_up"] == 4, f"got {out[8]['delta5_persist_up']}")


# ── 2. theme breadth ──────────────────────────────────────────────────────

def test_theme_breadth_zero():
    membership = {"A": {"TEMA"}, "B": {"TEMA"}, "C": {"TEMA"}}
    basket_to_tickers = {"TEMA": {"A", "B", "C"}}
    flow_today = {"A": -5.0, "B": -3.0, "C": -1.0}
    konc_today = {"A": None, "B": None, "C": None}
    out = fsl.compute_theme_breadth("A", membership, basket_to_tickers, flow_today, konc_today)
    check("breadth 0 cuando nadie confirma", out["blocked"] is True)
    check("confirmed=0", out["confirmed"] == 0)


def test_theme_breadth_partial():
    membership = {"A": {"TEMA"}, "B": {"TEMA"}}
    basket_to_tickers = {"TEMA": {"A", "B"}}
    flow_today = {"A": 5.0, "B": -3.0}
    konc_today = {"A": "bullish_aligned", "B": None}
    out = fsl.compute_theme_breadth("A", membership, basket_to_tickers, flow_today, konc_today)
    check("breadth parcial no bloquea", out["blocked"] is False)
    check("breadth_pct = 0.5", out["breadth_pct"] == 0.5)


def test_theme_breadth_no_basket():
    out = fsl.compute_theme_breadth("X", {}, {}, {}, {})
    check("sin cesta -> no bloqueado, sin dato", out["blocked"] is False and out["breadth_pct"] is None)


def test_theme_breadth_konc_veto_excludes_confirmation():
    membership = {"A": {"TEMA"}, "B": {"TEMA"}}
    basket_to_tickers = {"TEMA": {"A", "B"}}
    flow_today = {"A": 5.0, "B": 8.0}
    konc_today = {"A": "bullish_aligned", "B": "distribution_warning"}
    out = fsl.compute_theme_breadth("A", membership, basket_to_tickers, flow_today, konc_today)
    # B tiene Flow>0 pero Koncorde en veto -> no confirma pese al flow positivo
    check("Koncorde en veto no cuenta como confirmación aunque Flow>0", out["confirmed"] == 1, f"got {out['confirmed']}")


# ── 3. ATR percentile ─────────────────────────────────────────────────────

def test_atr_percentile_insufficient():
    rows = [row(f"2026-01-{i:02d}", atr=1.0) for i in range(1, 10)]
    check("None con <20 filas", fsl.atr_percentile_today(rows) is None)


def test_atr_percentile_basic():
    rows = [row(f"2026-01-{i:02d}", atr=float(i)) for i in range(1, 31)]
    pctile = fsl.atr_percentile_today(rows)
    check("percentil 100 cuando hoy es el máximo", pctile == 100.0, f"got {pctile}")


# ── 4. Casos reales de la auditoría (2026-10-01) ─────────────────────────

def eval_as_of(ctx, ticker, as_of_date):
    truncated = {tk: [r for r in rows if r["date"] <= as_of_date] for tk, rows in ctx["history"].items()}
    return fsl.evaluate_ticker(ticker, {**ctx, "history": truncated})


def test_real_audit_cases():
    ctx = fsl.build_context()

    # Casos que DEBEN rechazarse (Sol los etiquetó EARLY/CONFIRMED antes de
    # tiempo y tuvo que invalidarlos días después -- ver CLAUDE.md "Alertas
    # Koncorde..." no, ver la sección de esta auditoría en market_analysis_llm.py)
    must_reject = [
        ("BSX", "2026-09-15", "inflexion"),
        ("BSX", "2026-09-24", "inflexion"),
        ("VFF", "2026-09-24", "inflexion"),   # Cannabis, extendido no temprano
        ("VFF", "2026-09-30", "inflexion"),   # Cannabis invalidado -- tema bloqueado
        ("CL=F", "2026-09-24", "inflexion"),  # WTI
        ("BZ=F", "2026-09-28", "inflexion"),  # Brent
    ]
    for ticker, date, filt in must_reject:
        r = eval_as_of(ctx, ticker, date)
        check(f"{ticker}@{date} NO pasa {filt}", r.get(filt, {}).get("pass") is False,
              f"got {r.get(filt)}")

    # Tema bloqueado explícitamente en Cannabis el día de la invalidación real
    r = eval_as_of(ctx, "VFF", "2026-09-30")
    check("Cannabis muestra breadth 0 (equivalente al 'Regime Score 0' narrado por Sol)",
          r["theme"]["blocked"] is True and r["theme"]["confirmed"] == 0)

    # Casos que DEBEN seguir funcionando en algún punto de su trayectoria real
    r = eval_as_of(ctx, "ASM.AS", "2026-09-20")
    check("ASM.AS pasa inflexion el día antes de su ruptura real (9/21)", r["inflexion"]["pass"] is True)

    r = eval_as_of(ctx, "ASM.AS", "2026-09-28")
    check("ASM.AS se etiqueta MATURE (no silencio) durante la consolidación real", r["continuacion"]["mature"] is True)

    r = eval_as_of(ctx, "OSCR", "2026-09-30")
    check("OSCR sigue vetado por Koncorde (distribution_warning) el día que Sol lo marcó EARLY sin CONFIRMED",
          r["continuacion"]["pass"] is False and "distribution_warning" in str(r["continuacion"]["reasons"]))


def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        print(f"-- {t.__name__}")
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
