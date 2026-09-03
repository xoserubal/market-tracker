"""
ranking_score_readiness_monitor.py -- avisa por Telegram cuando toca escribir
el informe de Fase 3 del Ranking Score (wiki/PREREGISTRO_RANKING_SCORE_V0.md
§4/§6), o si se cumple el criterio de descarte anticipado. No decide nada por
si solo -- solo cuenta picks/tiempo acumulados de RANKING_SHADOW_EXPERIMENTAL
y avisa; la decision de escribir el informe (o de descartar el experimento)
sigue siendo manual, revisando §4 antes de actuar.

Umbrales -- literales de §4, sin inventar ninguno nuevo:
  Piloto     -- >=30 picks con ret_1m Y >=3 meses desde el primer --apply
                real (2026-09-04, primera vez que RANKING_SHADOW_EXPERIMENTAL
                abrio posiciones). Umbral MINIMO para empezar a evaluar, no
                para promocionar -- ver criterios completos en §4.
  Productivo -- >=75 picks con ret_1m Y >=75 con ret_3m Y >=6 meses.
  Descarte   -- desde que han pasado >=6 semanas: retorno acumulado (proxy,
                ver docstring de compute_descarte()) < -10% Y Spearman
                (candidate_ranking_score_shadow, ret_1m) negativo sobre todos
                los picks maduros -- ambas condiciones a la vez, literal
                del texto.

Cada alerta se dispara UNA sola vez (dedup via state file), igual que
p1_readiness_monitor.py/duration_monitor.py/check_koncorde_alerts.py.

Uso:
    py -3 scripts/ranking_score_readiness_monitor.py              # evalua y avisa si toca
    py -3 scripts/ranking_score_readiness_monitor.py --dry-run     # imprime, no envia ni persiste
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from notify_telegram import send_telegram  # reusa el sender ya existente, no reimplementa
from compare_vs_baselines import dedup_same_day_reruns  # reusa, no reimplementa (P0 ya resuelto)

# Mismo incidente ya documentado y arreglado en duration_monitor.py /
# check_koncorde_alerts.py / p1_readiness_monitor.py: emoji + consola
# Windows (cp1252) revienta print() si no se fuerza UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

SHADOW_PICKS = DATA / "shadow_picks.jsonl"
STATE_PATH   = DATA / "ranking_score_readiness_state.json"

PORTFOLIO = "RANKING_SHADOW_EXPERIMENTAL"

# Fecha del primer --apply real de la cartera experimental (2026-09-04, ver
# CLAUDE.md seccion "Ranking Score -- Fase 2"). Todo "meses desde el arranque"
# de §4/§6 se cuenta desde aqui, no desde el preregistro (2026-08-06) ni
# desde Fase 1 (2026-09-04, mismo dia pero antes de la primera posicion).
FASE2_START_DATE = "2026-09-04"

PILOTO_MIN_PICKS = 30
PILOTO_MIN_DAYS = 90       # ~3 meses
PRODUCTIVO_MIN_PICKS = 75
PRODUCTIVO_MIN_DAYS = 180  # ~6 meses
DESCARTE_MIN_DAYS = 42     # 6 semanas
DESCARTE_RET_THRESHOLD = -10.0


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def days_since_start(today: str) -> int:
    return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(FASE2_START_DATE, "%Y-%m-%d")).days


def load_portfolio_picks() -> list[dict]:
    picks = dedup_same_day_reruns(_load_jsonl(SHADOW_PICKS))
    return [p for p in picks if p.get("portfolio") == PORTFOLIO]


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rho sin scipy -- este monitor es deliberadamente ligero (no
    importa pandas/scipy, mismo criterio que duration_monitor.py/
    check_koncorde_alerts.py, para que un fallo de dependencias no le quite
    utilidad a un script que solo cuenta y avisa)."""
    n = len(xs)
    if n < 5:
        return None

    def rank(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        return ranks

    rx, ry = rank(xs), rank(ys)
    mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
    num = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    den_x = sum((a - mean_rx) ** 2 for a in rx) ** 0.5
    den_y = sum((b - mean_ry) ** 2 for b in ry) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def compute_descarte(picks: list[dict], today: str) -> dict:
    """Retorno acumulado = suma simple de ret_1m de los picks con entrada en
    las ultimas 6 semanas y ret_1m ya maduro -- proxy declarado, no una NAV
    real de cartera (todas las posiciones son 5% fijo, asi que la suma es
    aproximadamente proporcional al drag real sobre el libro). Correlacion:
    Spearman(candidate_ranking_score_shadow, ret_1m) sobre TODOS los picks
    maduros hasta hoy, no solo los de las ultimas 6 semanas -- una ventana de
    6 semanas natural de esta cartera (5 picks/semana) da demasiado pocos
    puntos para una correlacion con algo de fiabilidad."""
    today_d = datetime.strptime(today, "%Y-%m-%d")
    recent_rets = []
    for p in picks:
        d = p.get("date")
        r1m = p.get("ret_1m")
        if not d or r1m is None:
            continue
        try:
            days_ago = (today_d - datetime.strptime(d, "%Y-%m-%d")).days
        except ValueError:
            continue
        if 0 <= days_ago <= DESCARTE_MIN_DAYS:
            recent_rets.append(r1m)
    cum_ret = sum(recent_rets) if recent_rets else None

    xs, ys = [], []
    for p in picks:
        s, r1m = p.get("candidate_ranking_score_shadow"), p.get("ret_1m")
        if s is not None and r1m is not None:
            xs.append(s)
            ys.append(r1m)
    rho = spearman(xs, ys)

    triggered = (
        cum_ret is not None and cum_ret < DESCARTE_RET_THRESHOLD
        and rho is not None and rho < 0
    )
    return {"cum_ret_6w_proxy": cum_ret, "spearman_rho": rho, "n_recent": len(recent_rets),
            "n_corr": len(xs), "triggered": triggered}


def evaluate(picks: list[dict], today: str, state: dict) -> list[str]:
    messages = []
    fired = state.setdefault("fired", {})
    d_since = days_since_start(today)

    n_ret1m = sum(1 for p in picks if p.get("ret_1m") is not None)
    n_ret3m = sum(1 for p in picks if p.get("ret_3m") is not None)

    piloto_ready = n_ret1m >= PILOTO_MIN_PICKS and d_since >= PILOTO_MIN_DAYS
    productivo_ready = (
        n_ret1m >= PRODUCTIVO_MIN_PICKS and n_ret3m >= PRODUCTIVO_MIN_PICKS and d_since >= PRODUCTIVO_MIN_DAYS
    )

    if piloto_ready and "fase3_piloto_ready" not in fired:
        messages.append(
            f"🟢 <b>Ranking Score -- listo para Fase 3 (nivel Piloto)</b>\n"
            f"{n_ret1m} picks con ret_1m y {d_since} días desde el primer --apply "
            f"({FASE2_START_DATE}) -- umbral ≥{PILOTO_MIN_PICKS} picks / ≥{PILOTO_MIN_DAYS} días "
            f"cumplido. Revisa los criterios completos de §4 (Spearman&gt;0, outperformance vs "
            f"baseline PCS y rot_score, MFE/MAE no peor) antes de escribir el informe."
        )
        fired["fase3_piloto_ready"] = today

    if productivo_ready and "fase3_productivo_ready" not in fired:
        messages.append(
            f"🟢 <b>Ranking Score -- listo para Fase 3 (nivel Productivo)</b>\n"
            f"{n_ret1m} picks con ret_1m, {n_ret3m} con ret_3m, {d_since} días desde "
            f"{FASE2_START_DATE} -- umbral ≥{PRODUCTIVO_MIN_PICKS}/≥{PRODUCTIVO_MIN_PICKS}/"
            f"≥{PRODUCTIVO_MIN_DAYS} días cumplido. Revisa §4 completo: Spearman&gt;0.15 en "
            f"ret_1m Y ret_3m, outperformance vs las 7 baselines, sin depender de 1-2 winners, "
            f"consistencia en ≥2/3 sub-períodos."
        )
        fired["fase3_productivo_ready"] = today

    if d_since >= DESCARTE_MIN_DAYS:
        desc = compute_descarte(picks, today)
        if desc["triggered"] and "descarte_anticipado_triggered" not in fired:
            messages.append(
                f"🔴 <b>Ranking Score -- posible descarte anticipado (§4)</b>\n"
                f"Retorno acumulado proxy de picks abiertos en las últimas "
                f"{DESCARTE_MIN_DAYS//7} semanas: {desc['cum_ret_6w_proxy']:+.1f}% "
                f"(n={desc['n_recent']}), y Spearman(ranking_score, ret_1m)="
                f"{desc['spearman_rho']:+.3f} (n={desc['n_corr']}) -- ambas condiciones del "
                f"criterio de descarte anticipado se cumplen a la vez. Revisa §4 antes de "
                f"decidir nada; esto es un aviso, no un cierre automático de la cartera."
            )
            fired["descarte_anticipado_triggered"] = today
        state["last_descarte_check"] = desc

    state["last_check"] = {
        "date": today, "days_since_start": d_since,
        "n_picks_ret1m": n_ret1m, "n_picks_ret3m": n_ret3m,
    }
    return messages


def main():
    dry_run = "--dry-run" in sys.argv
    today = str(date.today())
    picks = load_portfolio_picks()

    state = _load_state()
    messages = evaluate(picks, today, state)

    last = state["last_check"]
    print(f"días desde el primer --apply ({FASE2_START_DATE}): {last['days_since_start']}")
    print(f"picks con ret_1m: {last['n_picks_ret1m']} (umbral piloto {PILOTO_MIN_PICKS}, "
          f"productivo {PRODUCTIVO_MIN_PICKS})")
    print(f"picks con ret_3m: {last['n_picks_ret3m']} (umbral productivo {PRODUCTIVO_MIN_PICKS})")
    if "last_descarte_check" in state:
        d = state["last_descarte_check"]
        print(f"descarte anticipado: cum_ret_6w_proxy={d['cum_ret_6w_proxy']} "
              f"spearman={d['spearman_rho']} triggered={d['triggered']}")

    if not messages:
        print("Sin umbrales nuevos cumplidos -- nada que avisar.")
    else:
        token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        for msg in messages:
            if dry_run:
                print(f"[DRY RUN] Telegram:\n{msg}\n")
            elif not token or not chat_id:
                print(f"TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID no configurados, no se envía:\n{msg}",
                      file=sys.stderr)
                sys.exit(1)
            else:
                ok = send_telegram(token, chat_id, msg)
                print(f"Telegram {'enviado' if ok else 'FALLÓ'}: {msg[:60]}...")

    if not dry_run:
        _save_state(state)
    else:
        print("[DRY RUN] state no persistido.")


if __name__ == "__main__":
    main()
