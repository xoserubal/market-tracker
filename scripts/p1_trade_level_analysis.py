"""
P1A / P1C — lectura por operación (trade-level) de los brazos shadow.

Preregistros: wiki/PREREGISTRO_P1A_PROFIT_PROTECTION_V1.md §5-§6 y
wiki/PREREGISTRO_P1C_INITIAL_RISK_V1.md §5-§6. Los parámetros de los brazos
NO se tocan aquí: este script solo lee lo que ya registraron
p1a_profit_protection_v1_shadow.py y p1c_initial_risk_v1_shadow.py.

Episodio = posición cerrada en el ámbito (HC/CFL/ER/MTB/CAVA) con
close_date >= FIRMA_DATE — la misma definición que el contador de
p1_readiness_monitor.py. Un mismo ticker+fecha de entrada en dos carteras son
dos episodios pero un solo evento independiente (event_id).

Para cada brazo:
  - Fecha de disparo = primera fila del log shadow con el brazo en true y
    fecha <= close_date (un brazo solo puede ADELANTAR la salida).
  - Retorno del brazo = cierre ajustado del día del disparo / cierre ajustado
    del día de entrada − 1. Si no dispara antes del cierre real, el episodio
    se queda con el retorno real.
  - Retorno real = cierre ajustado del día de cierre real / el de entrada − 1.
Todos los retornos salen de la misma serie de yfinance con ajuste por
dividendos y splits, para que el control y los brazos sean comparables; el
retorno contabilizado en ai_picks.json se informa aparte y se marcan las
discrepancias > 2 pp.

Métricas por brazo: media, mediana, p10, diferencia media frente al control
con IC 95 % por bootstrap agrupado por evento, % de episodios empeorados e
mejorados en más de 5 pp, captura de MFE. Solo P1C: falsos positivos (tras el
disparo, el precio sube > +5 % sobre el precio del disparo en las 21 sesiones
siguientes; con menos de 21 sesiones disponibles se cuenta como «sin madurar»).

Limitaciones que el informe repite:
  - La parte decisiva del criterio (libros de cartera con excess_CAGR_calendar
    y drawdown) no está construida: esto es solo la parte trade-level.
  - Los logs shadow solo ven los días que P0 capturó; hasta el 2026-11-22 P0
    no registraba el día de cierre, y las posiciones abiertas antes del
    2026-08-30 no tienen filas anteriores a esa fecha.
  - El precio del día del disparo es el cierre de ese día: una idealización de
    la ejecución (la cartera real también cierra al último cierre).

Uso:
    py -3 scripts/p1_trade_level_analysis.py            # informe por consola
    py -3 scripts/p1_trade_level_analysis.py --save     # + docs/data/p1_trade_level_report.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
PICKS_JSON = DATA / "ai_picks.json"
P1A_LOG = DATA / "p1a_profit_protection_v1_shadow.jsonl"
P1C_LOG = DATA / "p1c_initial_risk_v1_shadow.jsonl"
DECISION_STATE = DATA / "ai_picks_decision_state.jsonl"
OUT_JSON = DATA / "p1_trade_level_report.json"

sys.path.insert(0, str(Path(__file__).parent))
from p1_readiness_monitor import FIRMA_DATE, P1A_P1C_SCOPE  # noqa: E402

ARMS = {
    "P1A": [("exit_fixed", "FIXED +10/-8"), ("exit_atr", "ATR 2.5/2.0")],
    "P1C": [("brazo_B_atr_stop_exit", "B stop 2·ATR"), ("brazo_C_time_stop_exit", "C tiempo 7 ses."),
            ("brazo_D_structure_exit", "D estructura")],
}
WORSE_PP = 5.0
FP_SESSIONS = 21
FP_RECOVERY_PCT = 5.0
N_BOOT = 5000
SEED = 20261122


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_episodes() -> list[dict]:
    picks = json.loads(PICKS_JSON.read_text(encoding="utf-8"))
    eps = []
    for pf in P1A_P1C_SCOPE:
        for h in picks.get("portfolios", {}).get(pf, {}).get("history", []):
            if h.get("event") != "close" or not h.get("close_date") or h["close_date"] < FIRMA_DATE:
                continue
            eps.append({
                "portfolio": pf, "ticker": h["ticker"], "entry_date": h.get("entry_date"),
                "close_date": h["close_date"], "entry_price_booked": h.get("entry_price"),
                "close_price_booked": h.get("close_price"), "close_reason": h.get("close_reason"),
                "position_id": f"{h['ticker']}__{h.get('entry_date')}",
                "event_id": f"{h['ticker']}_{h.get('entry_date')}",
            })
    return eps


def first_fire(log_rows: list[dict], flag: str, close_date: str) -> str | None:
    for r in sorted(log_rows, key=lambda r: r["date"]):
        if r["date"] > close_date:
            break
        if r.get(flag):
            return r["date"]
    return None


def fetch_closes(tickers: list[str], start: str) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    raw = yf.download(tickers, start=start, auto_adjust=True, progress=False, group_by="ticker", threads=True)
    for tk in tickers:
        try:
            sub = raw[tk] if len(tickers) > 1 else raw
            s = sub["Close"].dropna()
            s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
            if len(s):
                out[tk] = s
        except Exception:
            continue
    return out


def close_at_or_before(s: pd.Series, day: str) -> tuple[float | None, pd.Timestamp | None]:
    sub = s.loc[:pd.Timestamp(day)]
    if sub.empty:
        return None, None
    return float(sub.iloc[-1]), sub.index[-1]


def ret(a: float | None, b: float | None) -> float | None:
    return round((b / a - 1) * 100, 3) if (a and b is not None) else None


def boot_ci(diffs: np.ndarray, groups: np.ndarray) -> tuple[float, float]:
    """IC 95 % de la media de las diferencias, remuestreando eventos (no episodios)."""
    uniq = np.unique(groups)
    if len(uniq) < 3:
        return float("nan"), float("nan")
    idx = {g: np.where(groups == g)[0] for g in uniq}
    rng = np.random.default_rng(SEED)
    means = np.empty(N_BOOT)
    for b in range(N_BOOT):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        means[b] = diffs[np.concatenate([idx[g] for g in pick])].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def build_table() -> tuple[pd.DataFrame, list[dict]]:
    eps = load_episodes()
    logs = {"P1A": _load_jsonl(P1A_LOG), "P1C": _load_jsonl(P1C_LOG)}
    by_pos = {k: {} for k in logs}
    for k, rows in logs.items():
        for r in rows:
            by_pos[k].setdefault((r["portfolio"], r["position_id"]), []).append(r)
    p0_by_pos: dict[tuple, list[dict]] = {}
    for r in _load_jsonl(DECISION_STATE):
        p0_by_pos.setdefault((r["portfolio"], r["position_id"]), []).append(r)

    start = (min(datetime.strptime(e["entry_date"], "%Y-%m-%d") for e in eps) - timedelta(days=10)).strftime("%Y-%m-%d")
    closes = fetch_closes(sorted({e["ticker"] for e in eps}), start)

    recs, notes = [], []
    for e in eps:
        s = closes.get(e["ticker"])
        key = (e["portfolio"], e["position_id"])
        p0 = sorted(p0_by_pos.get(key, []), key=lambda r: r["date"])
        rec = {**e, "p0_rows": len(p0), "p0_first": p0[0]["date"] if p0 else None,
               "p0_last": p0[-1]["date"] if p0 else None,
               "p0_has_close_day": any(r["date"] == e["close_date"] for r in p0),
               "entered_before_firma": e["entry_date"] < FIRMA_DATE,
               "group": "CAVA" if e["portfolio"] == "CAVA_MACRO" else "GROK/MIMO"}
        if s is None:
            notes.append(f"{e['ticker']}: sin precios en yfinance, episodio excluido")
            continue
        p_entry, _ = close_at_or_before(s, e["entry_date"])
        p_close, _ = close_at_or_before(s, e["close_date"])
        rec["ret_real"] = ret(p_entry, p_close)
        rec["ret_booked"] = ret(e["entry_price_booked"], e["close_price_booked"])
        if rec["ret_real"] is not None and rec["ret_booked"] is not None and abs(rec["ret_real"] - rec["ret_booked"]) > 2:
            notes.append(f"{e['portfolio']} {e['ticker']} {e['entry_date']}: retorno ajustado {rec['ret_real']:+.1f} % "
                         f"frente a contabilizado {rec['ret_booked']:+.1f} %")
        window = s.loc[pd.Timestamp(e["entry_date"]):pd.Timestamp(e["close_date"])]
        rec["mfe"] = round((window.max() / p_entry - 1) * 100, 3) if (p_entry and len(window)) else None
        for exp, arms in ARMS.items():
            rows = by_pos[exp].get(key, [])
            rec[f"{exp}_logged"] = bool(rows)
            for flag, _ in arms:
                d = first_fire(rows, flag, e["close_date"]) if rows else None
                rec[f"{flag}_date"] = d
                if d is None:
                    rec[f"{flag}_ret"] = rec["ret_real"]
                    rec[f"{flag}_fp"] = None
                    continue
                p_trig, ts = close_at_or_before(s, d)
                rec[f"{flag}_ret"] = ret(p_entry, p_trig)
                after = s.loc[s.index > ts].iloc[:FP_SESSIONS]
                if len(after) < FP_SESSIONS:
                    rec[f"{flag}_fp"] = "immature" if after.empty or after.max() < p_trig * (1 + FP_RECOVERY_PCT / 100) else True
                else:
                    rec[f"{flag}_fp"] = bool(after.max() >= p_trig * (1 + FP_RECOVERY_PCT / 100))
        recs.append(rec)
    return pd.DataFrame(recs), notes


def summarize(df: pd.DataFrame) -> dict:
    out = {"n_episodes": int(len(df)), "n_events": int(df["event_id"].nunique())}
    real = df["ret_real"].to_numpy(dtype=float)
    out["control"] = {"mean": float(np.nanmean(real)), "median": float(np.nanmedian(real)),
                      "p10": float(np.nanpercentile(real, 10))}
    pos_mfe = df["mfe"] > 0
    out["control"]["mfe_capture"] = float((df.loc[pos_mfe, "ret_real"] / df.loc[pos_mfe, "mfe"]).median()) if pos_mfe.any() else None
    for exp, arms in ARMS.items():
        for flag, label in arms:
            r = df[f"{flag}_ret"].to_numpy(dtype=float)
            d = r - real
            ok = ~np.isnan(d)
            lo, hi = boot_ci(d[ok], df.loc[ok, "event_id"].to_numpy())
            fired = df[f"{flag}_date"].notna()
            fp = df.loc[fired, f"{flag}_fp"]
            out[flag] = {
                "experiment": exp, "label": label,
                "n_fired": int(fired.sum()), "n_fired_events": int(df.loc[fired, "event_id"].nunique()),
                "mean": float(np.nanmean(r)), "median": float(np.nanmedian(r)), "p10": float(np.nanpercentile(r, 10)),
                "mean_diff_vs_control": float(np.nanmean(d)), "ci95": [lo, hi],
                "p10_diff_vs_control": float(np.nanpercentile(r, 10) - np.nanpercentile(real, 10)),
                "pct_worse_5pp": float((d < -WORSE_PP).mean() * 100),
                "pct_better_5pp": float((d > WORSE_PP).mean() * 100),
                "mfe_capture": float((df.loc[pos_mfe, f"{flag}_ret"] / df.loc[pos_mfe, "mfe"]).median()) if pos_mfe.any() else None,
                "false_pos": int((fp == True).sum()), "false_pos_immature": int((fp == "immature").sum()),  # noqa: E712
                "false_pos_pct_mature": (float((fp == True).sum() / max(1, (fp != "immature").sum()) * 100)  # noqa: E712
                                         if fired.any() else None),
            }
    return out


def print_summary(name: str, s: dict):
    c = s["control"]
    print(f"\n== {name}: {s['n_episodes']} episodios, {s['n_events']} eventos independientes ==")
    print(f"  control (regla real): media {c['mean']:+.2f} %  mediana {c['median']:+.2f} %  p10 {c['p10']:+.2f} %"
          f"  captura MFE {c['mfe_capture'] if c['mfe_capture'] is None else round(c['mfe_capture'], 2)}")
    print(f"  {'brazo':18s} {'disp.':>5s} {'media':>7s} {'Δ vs ctrl':>9s} {'IC 95 %':>17s} {'Δp10':>7s} "
          f"{'peor>5':>6s} {'mejor>5':>7s} {'FP':>9s}")
    for flag in [f for arms in ARMS.values() for f, _ in arms]:
        a = s[flag]
        lo, hi = a["ci95"]
        ci = f"[{lo:+.2f}, {hi:+.2f}]" if not np.isnan(lo) else "n/a"
        fp = f"{a['false_pos']}/{a['n_fired'] - a['false_pos_immature']}" + (f" +{a['false_pos_immature']}?" if a["false_pos_immature"] else "")
        print(f"  {a['experiment']} {a['label']:14s} {a['n_fired']:5d} {a['mean']:+7.2f} {a['mean_diff_vs_control']:+9.2f} "
              f"{ci:>17s} {a['p10_diff_vs_control']:+7.2f} {a['pct_worse_5pp']:5.0f}% {a['pct_better_5pp']:6.0f}% {fp:>9s}")


def main():
    df, notes = build_table()
    if df.empty:
        print("Sin episodios.")
        return
    print(f"Episodios post-firma ({FIRMA_DATE}) en {', '.join(P1A_P1C_SCOPE)}: {len(df)}")
    print(f"  por cartera: {df['portfolio'].value_counts().to_dict()}")
    print(f"  abiertos antes de la firma: {int(df['entered_before_firma'].sum())}")
    print(f"  con filas de P0: {int((df['p0_rows'] > 0).sum())}  ·  con la fila del día de cierre: {int(df['p0_has_close_day'].sum())}")
    print(f"  con log P1A: {int(df['P1A_logged'].sum())}  ·  con log P1C: {int(df['P1C_logged'].sum())}")
    report = {"generated": datetime.now().isoformat(timespec="seconds"), "firma_date": FIRMA_DATE,
              "groups": {}, "notes": notes}
    for name, sub in [("Todos", df), ("CAVA_MACRO", df[df["group"] == "CAVA"]), ("Grok/Mimo (HC/CFL/ER/MTB)", df[df["group"] != "CAVA"])]:
        if len(sub) == 0:
            continue
        s = summarize(sub)
        report["groups"][name] = s
        print_summary(name, s)
    print("\nCriterio trade-level P1A (§6): Δ media ≥ +1 pp y ≤ 10 % de episodios empeorados > 5 pp.")
    print("Criterio trade-level P1C (§6): p10 mejora ≥ 3 pp y ≤ 20 % de falsos positivos.")
    print("La parte decisiva (libros de cartera: excess_CAGR_calendar, drawdown) NO está construida.")
    if notes:
        print("\nNotas:")
        for n in notes:
            print("  -", n)
    if "--save" in sys.argv:
        report["episodes"] = json.loads(df.to_json(orient="records"))
        OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nGuardado en {OUT_JSON}")


if __name__ == "__main__":
    main()
