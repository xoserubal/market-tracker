"""Muestreo reproducible y congelado ANTES de descargar.

- Piloto B1: bloques contiguos de sesiones, independientes de cualquier señal.
  Cada bloque = (fecha de inicio aleatoria dentro del periodo, valor aleatorio entre los miembros del universo en
  esa fecha, estratificado por tercil de liquidez medida con las 60 sesiones ANTERIORES al bloque).
  Estructura de un bloque: BURN_IN sesiones de historia tick (no elegibles) + ELIGIBLE sesiones elegibles.
  Los resultados posteriores (hasta 40 sesiones) se miden con barras diarias, no con ticks: el bloque no necesita
  cubrirlos, pero el bloque + horizonte no puede cruzar la frontera desarrollo/prueba (embargo).
  No se exige que el valor siga cotizando después (evita sesgo de supervivencia); los resultados faltantes por
  deslistado se registran como tales.
- Quotes: submuestra de bloques de B1 (reutiliza sus trades), primeras N sesiones elegibles contiguas.
- Captura prospectiva: muestra diaria con semilla derivada de (semilla maestra, fecha) y probabilidad de inclusión.
"""
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config, storage


def _rng(seed, *parts):
    h = hashlib.sha256(json.dumps([seed, *parts]).encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


def freeze(plan: pd.DataFrame, meta: dict, name: str) -> dict:
    """Guarda plan + metadatos en samples/ con su hash. Se hace antes de cualquier descarga."""
    d = storage.root() / "samples"
    body = plan.to_json(orient="records", date_format="iso")
    digest = hashlib.sha256(body.encode()).hexdigest()
    meta = {**meta, "name": name, "rows": int(len(plan)), "sha256_plan": digest, "code_version": config.code_version(),
            "frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    storage.write_parquet_atomic(plan, d / f"{name}.parquet")
    (d / f"{name}.meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return meta


def b1_plan(members: pd.DataFrame, daily: pd.DataFrame, trading_days: list, periods: dict, *, seed: int,
            blocks_per_period: int = 100, block_len: int = 100, burn_in: int = 40, horizon: int = 40,
            liq_lookback: int = 60) -> pd.DataFrame:
    """members: intervalos (entity, symbol, asof, start, end). daily: (entity, date, n) con n = trades del día."""
    pos = {d: i for i, d in enumerate(trading_days)}
    n_by = daily.pivot_table(index="date", columns="entity", values="n", aggfunc="first").reindex(trading_days)
    liq = n_by.shift(1).rolling(liq_lookback, min_periods=liq_lookback // 2).median()   # solo información previa
    rows = []
    used = {}   # entity -> lista de (i0, i1) para no solapar bloques del mismo valor
    for period, (p0, p1) in periods.items():
        i_lo = pos[min(d for d in trading_days if d >= p0)]
        i_hi = pos[max(d for d in trading_days if d <= p1)] - block_len - horizon   # bloque + horizonte dentro del periodo
        rng = _rng(seed, "b1", period)
        per_tercile = {0: 0, 1: 0, 2: 0}
        target = {k: blocks_per_period // 3 + (1 if k < blocks_per_period % 3 else 0) for k in per_tercile}
        tries = 0
        while sum(per_tercile.values()) < blocks_per_period and tries < 200000:
            tries += 1
            i0 = int(rng.integers(i_lo, i_hi + 1))
            d0 = trading_days[i0]
            act = members[(members["start"] <= d0) & (members["end"] >= d0)]
            if act.empty:
                continue
            l = liq.loc[d0, liq.columns.intersection(act["entity"])].dropna()
            if len(l) < 30:
                continue
            terc = pd.qcut(l.rank(method="first"), 3, labels=[0, 1, 2])
            k = int(rng.integers(0, 3))
            if per_tercile[k] >= target[k]:
                continue
            cands = terc[terc == k].index.tolist()
            ent = cands[int(rng.integers(0, len(cands)))]
            i1 = i0 + block_len - 1
            if any(not (i1 < a or i0 > b) for a, b in used.get(ent, [])):
                continue
            used.setdefault(ent, []).append((i0, i1))
            m = act[act["entity"] == ent].iloc[0]
            per_tercile[k] += 1
            rows.append({"block_id": f"{period}-{sum(per_tercile.values()):03d}", "period": period, "entity": ent,
                         "symbol": m["symbol"], "asof": m["asof"], "liq_tercile": k,
                         "liq_median_n_prior": float(l[ent]), "start": d0, "end": trading_days[i1],
                         "eligible_start": trading_days[i0 + burn_in], "burn_in": burn_in,
                         "eligible_sessions": block_len - burn_in, "outcome_horizon_max": horizon})
    return pd.DataFrame(rows)


def block_days(plan: pd.DataFrame, trading_days: list) -> pd.DataFrame:
    pos = {d: i for i, d in enumerate(trading_days)}
    out = []
    for r in plan.itertuples():
        for i in range(pos[r.start], pos[r.end] + 1):
            d = trading_days[i]
            out.append({"block_id": r.block_id, "entity": r.entity, "symbol": r.symbol, "asof": r.asof, "date": d,
                        "eligible": d >= r.eligible_start})
    return pd.DataFrame(out)


def quotes_plan(b1: pd.DataFrame, trading_days: list, *, seed: int, n_blocks: int = 20, n_sessions: int = 20):
    rng = _rng(seed, "quotes")
    picks = []
    for k, quota in ((0, 7), (1, 7), (2, n_blocks - 14)):
        pool = b1[b1["liq_tercile"] == k]
        idx = rng.choice(len(pool), size=min(quota, len(pool)), replace=False)
        picks.append(pool.iloc[sorted(idx)])
    q = pd.concat(picks).copy()
    pos = {d: i for i, d in enumerate(trading_days)}
    q["q_start"] = q["eligible_start"]
    q["q_end"] = [trading_days[pos[s] + n_sessions - 1] for s in q["eligible_start"]]
    return q.reset_index(drop=True)


def shadow_sample(eligible: list, day: str, master_seed: int, k: int) -> dict:
    """Selección diaria reproducible: misma (semilla, fecha, universo) -> misma muestra."""
    elig = sorted(set(eligible))
    rng = _rng(master_seed, "shadow", day, hashlib.sha256("|".join(elig).encode()).hexdigest())
    idx = sorted(rng.choice(len(elig), size=min(k, len(elig)), replace=False).tolist())
    return {"date": day, "eligible_n": len(elig), "selected": [elig[i] for i in idx],
            "inclusion_probability": round(min(k, len(elig)) / len(elig), 6) if elig else 0.0,
            "eligible_sha256": hashlib.sha256("|".join(elig).encode()).hexdigest()}


def power_preview(n_eff: float, k_tests: int = 1, alpha: float = 0.05, power: float = 0.8) -> float:
    """Correlación (IC) mínima detectable aproximada: (z_{1-α/2k} + z_{power}) / sqrt(n_eff)."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - alpha / (2 * k_tests)) + NormalDist().inv_cdf(power)
    return round(z / np.sqrt(n_eff), 4) if n_eff > 0 else float("nan")
