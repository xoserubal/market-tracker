"""Corrección de los planes congelados B1 y quotes (v1 -> v2) y revalidación de identidad y cobertura.

Autorización: respuesta del usuario al informe G1.5 (2026-11-15), punto 1: corregir PCLN->BKNG y FISV->FI con las
fechas reales de cambio de símbolo, sin sustituir empresas ni regenerar bloques; conservar v1 intacto y crear una
versión nueva con su propio hash; CTXS y MON se quedan en la muestra y sus sesiones posteriores a la salida no se
inventan ni se sustituyen.

Regla de corrección (general, no un parche para dos casos): el (símbolo, asof) de un bloque en cada fecha es el que
el nivel A asigna a esa entidad (CIK) en esa fecha. El nivel A ya recorta cada ticker a su época de identidad
(`g1_plans.level_a_days`), así que ahí los cambios de nombre están bien resueltos. Si un bloque abarcase dos
tickers, el script falla en vez de elegir uno (no ocurre en v1). Las fechas sin asignación (la empresa ya no
cotiza) se conservan en el plan con el símbolo original y quedan registradas como salida, no como hueco a rellenar.

Salidas (MICRO_DATA_DIR/samples): b1_plan_v2, quotes_plan_v2, plan_exits_v2 (.parquet + .meta.json).
Informe: MICRO_DATA_DIR/results/g2_plan_corrections.json. v1 no se toca (se comprueba su hash antes y después).

    py -3 g2_plan_corrections.py            # genera v2 y revalida
    py -3 g2_plan_corrections.py --check    # solo revalida lo ya generado (no escribe planes)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g1_plans  # noqa: E402
from micro import calendar, sampling, storage  # noqa: E402

HORIZON = 40          # horizonte máximo de resultados (sesiones tras el fin del bloque)

# Cambios de símbolo verificados (fuente: acciones corporativas de Alpaca `name_changes` y continuidad de la serie
# diaria en Alpaca; ver results/g2_plan_corrections.json -> evidence). first_session = primera sesión con el
# símbolo nuevo.
SYMBOL_CHANGES = [
    {"entity": "1075531", "company": "Booking Holdings (antes Priceline Group)", "old": "PCLN", "new": "BKNG",
     "first_session": "2018-02-27",
     "evidence": "Alpaca: PCLN asof 2019-01-11 termina el 2018-02-26 (cierre 1905,64); BKNG sin asof es continua "
                 "(2018-02-27 apertura 1884,00). Alpaca no publica este name_change en /corporate-actions."},
    {"entity": "798354", "company": "Fiserv", "old": "FISV", "new": "FI", "first_session": "2023-06-07",
     "evidence": "Alpaca /corporate-actions name_changes: FISV->FI 2023-06-07 (CUSIP 337738108); FISV asof "
                 "2024-01-11 termina el 2023-06-06 (cierre 114,23) y FI asof 2026-01-13 empieza el 2023-06-07 "
                 "(apertura 115,50). Antes de esa fecha FI era otro valor (Frank's International, FI->XPRO "
                 "2021-10-04): la época de identidad lo separa."},
    {"entity": "798354", "company": "Fiserv", "old": "FI", "new": "FISV", "first_session": "2025-11-11",
     "evidence": "Alpaca /corporate-actions name_changes: FI->FISV 2025-11-11 (mismo CUSIP). Ningún bloque B1 "
                 "cae en esta fecha; se registra para el nivel A."},
]

# Salidas definitivas de cotización que caen dentro de un bloque o de su horizonte. Fuente primaria: 8-K de cierre
# de la fusión en SEC EDGAR (Item 2.01). Comprobación cruzada: último cierre en Alpaca y /corporate-actions.
EXIT_EVENTS = {
    "877890": {"symbol": "CTXS", "company": "Citrix Systems", "last_session": "2022-09-29",
               "effective_date": "2022-09-30", "type": "cash_merger", "cash_per_share": 104.00,
               "acquirer": "Cloud Software Group (Vista Equity Partners y Evergreen Coast Capital/Elliott)",
               "source": "SEC EDGAR 8-K 0001193125-22-256805 (2022-10-03), Item 2.01: $104.00 en efectivo por acción; "
                         "Alpaca cash_mergers CTXS rate 104, effective 2022-09-30",
               "last_close": 103.90},
    "1110783": {"symbol": "MON", "company": "Monsanto", "last_session": "2018-06-06",
                "effective_date": "2018-06-07", "type": "cash_merger", "cash_per_share": 128.00,
                "acquirer": "Bayer AG",
                "source": "SEC EDGAR 8-K 0001193125-18-188226 (2018-06-08), Item 2.01: $128.00 en efectivo por "
                          "acción; Alpaca no tiene este evento en /corporate-actions",
                "last_close": 127.95},
}

TREATMENT = (
    "Resultado económico de una observación cuyo horizonte cruza una salida: "
    "fusión en efectivo -> se cobra el precio de la operación en la fecha efectiva y el resto del horizonte rinde 0 "
    "(efectivo); fusión en acciones -> se convierte a acciones del comprador con la relación de canje y se sigue su "
    "serie; mixta -> combinación; exclusión por quiebra o incumplimiento sin precio conocido -> último precio con "
    "una rentabilidad de deslistado de -30 % y sensibilidad con 0 % y -100 %. El exceso frente a la referencia usa "
    "la misma regla para la referencia. Nunca se descarta la observación (sesgo de supervivencia); como "
    "sensibilidad se informa también el resultado excluyéndolas. Las sesiones del bloque posteriores a la salida no "
    "generan observaciones (no hay mercado), no se rellenan ni se sustituyen por otro valor.")


def _norm(x):
    return x if isinstance(x, str) and x.strip() else None


def sha_plan(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_json(orient="records", date_format="iso").encode()).hexdigest()


def file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_level_a_map():
    ref = storage.root() / "reference"
    iv = pd.read_parquet(ref / "universe_intervals.parquet")
    daily = pd.read_parquet(ref / "daily_bars_levelA.parquet").drop_duplicates(["entity", "date"])
    ua = g1_plans.level_a_days(iv, daily, calendar.trading_days(g1_plans.FIRST, g1_plans.LAST))
    ua["asof"] = ua["asof"].map(_norm)
    return iv, daily, ua


def remap(plan: pd.DataFrame, ua: pd.DataFrame, days: list, start_col="start", end_col="end"):
    """Devuelve (plan corregido, cambios, días sin asignación) aplicando el (símbolo, asof) del nivel A."""
    m = ua.set_index(["entity", "date"])[["symbol", "asof"]]
    pos = {d: i for i, d in enumerate(days)}
    out, changes, unmapped = plan.copy(), [], []
    out["symbol_v1"], out["asof_v1"] = out["symbol"], out["asof"].map(_norm)
    out["asof"] = out["asof"].map(_norm)
    out["correction"] = ""
    for i, r in out.iterrows():
        ds = days[pos[r[start_col]]: pos[r[end_col]] + 1]
        got = [(m.loc[(r.entity, d), "symbol"], m.loc[(r.entity, d), "asof"]) if (r.entity, d) in m.index else None
               for d in ds]
        mapped = {g for g in got if g is not None}
        miss = [d for d, g in zip(ds, got) if g is None]
        if miss:
            unmapped.append({"block_id": r.block_id, "symbol": r.symbol, "first": miss[0], "last": miss[-1],
                             "sessions": len(miss)})
        if len(mapped) > 1:
            raise RuntimeError(f"{r.block_id}: el bloque abarca varios tickers {mapped}; no se elige uno")
        if mapped:
            sym, asof = mapped.pop()
            if (sym, asof) != (r.symbol, r["asof"]):
                ch = next((c for c in SYMBOL_CHANGES if c["entity"] == str(r.entity) and c["new"] == sym), None)
                if ch is None:
                    raise RuntimeError(f"{r.block_id}: cambio {r.symbol}->{sym} sin evidencia registrada")
                out.at[i, "symbol"], out.at[i, "asof"] = sym, asof
                out.at[i, "correction"] = (f"{r.symbol}->{sym} (asof {_norm(asof) or 'vigente'}): cambio de símbolo de "
                                           f"{ch['company']} desde {ch['first_session']}")
                changes.append({"block_id": r.block_id, "entity": str(r.entity), "from": [r.symbol, r["asof"]],
                                "to": [sym, asof], "sessions": len(ds), "reason": out.at[i, "correction"]})
    return out, changes, unmapped


def exits_table(plan: pd.DataFrame, daily: pd.DataFrame, days: list) -> pd.DataFrame:
    """Bloques cuyo valor deja de cotizar dentro del bloque o de su horizonte de 40 sesiones."""
    pos = {d: i for i, d in enumerate(days)}
    rows = []
    for r in plan.itertuples():
        ev = EXIT_EVENTS.get(str(r.entity))
        if not ev:
            continue
        hz_end = days[min(pos[r.end] + HORIZON, len(days) - 1)]
        if not (r.start <= ev["last_session"] <= hz_end):
            continue
        inb = [d for d in days[pos[r.start]: pos[r.end] + 1] if d > ev["last_session"]]
        elig = [d for d in inb if d >= r.eligible_start]
        rows.append({"block_id": r.block_id, "entity": str(r.entity), "symbol": r.symbol, "period": r.period,
                     "block_start": r.start, "block_end": r.end, "horizon_end": hz_end, **ev,
                     "block_sessions_after_exit": len(inb), "eligible_sessions_after_exit": len(elig),
                     "eligible_sessions_with_market": int(r.eligible_sessions) - len(elig),
                     "treatment": "cash_out_at_deal_price_then_cash"})
    return pd.DataFrame(rows)


def coverage_check(plan: pd.DataFrame, daily: pd.DataFrame, days: list, exits: pd.DataFrame,
                   start_col="start", end_col="end") -> dict:
    """Días del plan con datos (barras diarias con volumen) por (símbolo, asof) del plan; los que faltan se explican."""
    d = daily.copy()
    d["asof"] = d["asof"].map(_norm)
    have = set(zip(d.loc[d["v"] > 0, "symbol"], d.loc[d["v"] > 0, "asof"].fillna(""), d.loc[d["v"] > 0, "date"]))
    pos = {x: i for i, x in enumerate(days)}
    exit_after = {r.block_id: r.last_session for r in exits.itertuples()} if len(exits) else {}
    tot = miss = explained = 0
    unexplained = []
    for r in plan.itertuples():
        for dd in days[pos[getattr(r, start_col)]: pos[getattr(r, end_col)] + 1]:
            tot += 1
            if (r.symbol, _norm(r.asof) or "", dd) in have:
                continue
            miss += 1
            if r.block_id in exit_after and dd > exit_after[r.block_id]:
                explained += 1
            else:
                unexplained.append((r.block_id, r.symbol, dd))
    return {"symbol_days": tot, "with_data": tot - miss, "missing": miss, "missing_after_exit": explained,
            "missing_unexplained": len(unexplained), "unexplained": unexplained[:50]}


def horizon_check(plan: pd.DataFrame, daily: pd.DataFrame, days: list, exits: pd.DataFrame) -> dict:
    """Sesiones del horizonte de resultados (40 tras el bloque) sin barra diaria en la referencia, por motivo.

    La referencia diaria de G1 solo llega a 60 sesiones tras la salida del índice; un valor que sale del S&P 500 y
    sigue cotizando (p. ej. CZR) necesita barras diarias adicionales para medir el resultado. No es una salida.
    """
    have = set(zip(daily.loc[daily["v"] > 0, "entity"].astype(str), daily.loc[daily["v"] > 0, "date"]))
    pos = {x: i for i, x in enumerate(days)}
    exit_after = {r.block_id: r.last_session for r in exits.itertuples()} if len(exits) else {}
    need = []
    for r in plan.itertuples():
        hz = days[pos[r.end] + 1: min(pos[r.end] + 1 + HORIZON, len(days))]
        miss = [d for d in hz if (str(r.entity), d) not in have and not (r.block_id in exit_after and d > exit_after[r.block_id])]
        if miss:
            need.append({"block_id": r.block_id, "symbol": r.symbol, "asof": r.asof, "first": miss[0],
                         "last": miss[-1], "sessions": len(miss)})
    return {"blocks_needing_extra_daily_bars": need,
            "action": "descargar barras diarias de esos (símbolo, asof) en esas fechas antes de medir resultados"}


def level_a_check(ua: pd.DataFrame) -> dict:
    """El nivel A ya usa la época de cada ticker: se comprueba para las entidades con cambio de símbolo."""
    out = {}
    for ent in sorted({c["entity"] for c in SYMBOL_CHANGES}):
        u = ua[ua["entity"].astype(str) == ent]
        g = (u.groupby(["symbol", u["asof"].fillna("vigente")]).agg(first=("date", "min"), last=("date", "max"),
                                                                     days=("date", "size"),
                                                                     days_without_trades=("n", lambda s: int((s == 0).sum())))
               .reset_index().sort_values("first"))
        out[ent] = g.to_dict("records")
    zero = ua[ua["n"] == 0]
    out["universe_days_without_trades"] = {
        "entity_days": int(len(zero)), "of_total": int(len(ua)),
        "by_symbol": zero.groupby("symbol").size().sort_values(ascending=False).head(15).to_dict(),
        "note": "casi todos son valores del proyecto antes de su salida a bolsa (SPAC): días sin negociación real, "
                "no tickers mal asignados"}
    return out


def freeze_v2(df: pd.DataFrame, name: str, parent: str, extra: dict):
    smp = storage.root() / "samples"
    pmeta = json.loads((smp / f"{parent}.meta.json").read_text(encoding="utf-8"))
    meta = sampling.freeze(df, {**{k: v for k, v in pmeta.items() if k not in ("name", "rows", "sha256_plan",
                                                                              "code_version", "frozen_utc")},
                                "parent": parent, "parent_sha256_plan": pmeta["sha256_plan"], **extra}, name)
    return meta


def main(check_only=False):
    smp = storage.root() / "samples"
    v1_files = {n: file_sha(smp / f"{n}.parquet") for n in ("b1_plan_v1", "quotes_plan_v1")}
    days = calendar.trading_days("2015-01-01", g1_plans.LAST)
    iv, daily, ua = load_level_a_map()
    b1 = pd.read_parquet(smp / "b1_plan_v1.parquet")
    qp = pd.read_parquet(smp / "quotes_plan_v1.parquet")
    assert sha_plan(b1) == json.loads((smp / "b1_plan_v1.meta.json").read_text(encoding="utf-8"))["sha256_plan"]

    b2, b_changes, b_unmapped = remap(b1, ua, days)
    q2, q_changes, q_unmapped = remap(qp, ua, days, "q_start", "q_end")
    ex = exits_table(b2, daily, days)
    unexplained_exits = [u for u in b_unmapped if u["block_id"] not in set(ex["block_id"])]
    if unexplained_exits:
        raise RuntimeError(f"fechas sin asignación no explicadas por una salida registrada: {unexplained_exits}")

    if not check_only:
        just = {"authorization": "respuesta del usuario al informe G1.5, 2026-11-15, punto 1",
                "rule": "símbolo y asof de cada bloque = los que el nivel A asigna a la entidad (CIK) en esas fechas",
                "symbol_changes": SYMBOL_CHANGES}
        m_b = freeze_v2(b2, "b1_plan_v2", "b1_plan_v1", {**just, "changes": b_changes,
                                                         "unmapped_after_exit": b_unmapped})
        m_q = freeze_v2(q2, "quotes_plan_v2", "quotes_plan_v1", {**just, "changes": q_changes,
                                                                 "unmapped_after_exit": q_unmapped})
        m_e = sampling.freeze(ex, {"design": "salidas de cotización dentro de un bloque B1 o de su horizonte",
                                   "treatment_rule": TREATMENT, "horizon_sessions": HORIZON}, "plan_exits_v2")
    else:
        m_b = json.loads((smp / "b1_plan_v2.meta.json").read_text(encoding="utf-8"))
        m_q = json.loads((smp / "quotes_plan_v2.meta.json").read_text(encoding="utf-8"))
        m_e = json.loads((smp / "plan_exits_v2.meta.json").read_text(encoding="utf-8"))
        for name, df in (("b1_plan_v2", b2), ("quotes_plan_v2", q2), ("plan_exits_v2", ex)):
            stored = pd.read_parquet(smp / f"{name}.parquet")
            if sha_plan(stored) != json.loads((smp / f"{name}.meta.json").read_text(encoding="utf-8"))["sha256_plan"]:
                raise RuntimeError(f"{name}: el fichero no coincide con su hash congelado")
            if sha_plan(stored) != sha_plan(df.reset_index(drop=True)):
                raise RuntimeError(f"{name}: regenerar daría otro plan (¿han cambiado las referencias?)")

    v1_after = {n: file_sha(smp / f"{n}.parquet") for n in v1_files}
    out = {
        "v1_unchanged": v1_after == v1_files, "v1_file_sha256": v1_files,
        "b1_v2": {"sha256_plan": m_b["sha256_plan"], "parent_sha256_plan": m_b.get("parent_sha256_plan"),
                  "changes": b_changes, "unmapped_after_exit": b_unmapped,
                  "coverage_v1": coverage_check(b1.assign(asof=b1["asof"].map(_norm)), daily, days, ex),
                  "coverage_v2": coverage_check(b2, daily, days, ex),
                  "outcome_horizon": horizon_check(b2, daily, days, ex)},
        "quotes_v2": {"sha256_plan": m_q["sha256_plan"], "parent_sha256_plan": m_q.get("parent_sha256_plan"),
                      "changes": q_changes,
                      "coverage_v2": coverage_check(q2, daily, days, ex, "q_start", "q_end")},
        "exits": {"sha256_plan": m_e["sha256_plan"], "rows": ex.to_dict("records"), "treatment_rule": TREATMENT},
        "level_A": level_a_check(ua),
        "symbol_changes": SYMBOL_CHANGES,
    }
    f = storage.root() / "results" / "g2_plan_corrections.json"
    f.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("v1_unchanged",)}, ensure_ascii=False))
    print(json.dumps(out["b1_v2"], indent=1, default=str, ensure_ascii=False)[:3000])
    print(json.dumps(out["quotes_v2"], indent=1, default=str, ensure_ascii=False)[:1500])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    main(ap.parse_args().check)
