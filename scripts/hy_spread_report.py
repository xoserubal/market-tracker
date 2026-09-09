"""
HY Spread Daily Report — informe informativo tras cada run del pipeline
(hasta nuevo aviso, sin fecha de retirada fijada)

Origen: el usuario quiere vigilar de cerca la tesis "mientras el HY spread se
mueva ~265-270 el sistema financiero dice rotacion, no crisis; si empieza a
subir 270 -> 285 -> 300 -> 325 mientras petroleo y yields se mantienen
altos, la pelicula cambia". A diferencia de duration_monitor.py (que solo
avisa en una transicion de fase o un cruce de nivel nuevo), esto es
deliberadamente un informe INCONDICIONAL: se envia un mensaje por Telegram
en cada ejecucion del pipeline (2x/dia), no solo cuando algo cambia, para
que el usuario pueda ver el nivel actual y la evolucion de la ultima semana
de un vistazo, sin tener que abrir duration.html.

Reutiliza los helpers de fetch ya existentes en duration_monitor.py
(_fred_latest, _yfinance_price, LEVELS["core_break_10y"]) en vez de
duplicarlos -- mismo criterio de reuso que el resto del proyecto
(ai_shared.py, ratio_signal.py).

Escalera de vigilancia (literal de la tesis del usuario, no calibrada
contra rendimiento -- es un marco narrativo, no una senal cuantitativa):
    <270      -> rotacion, no crisis
    270-285   -> primer escalon, empieza a vigilarse
    285-300   -> segundo escalon, alerta
    300-325   -> tercer escalon, estres significativo
    >=325     -> cuarto escalon, la pelicula cambia

Uso:
  py -3 scripts/hy_spread_report.py              # envia el informe por Telegram
  py -3 scripts/hy_spread_report.py --dry-run    # imprime en vez de enviar
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# Los mensajes llevan emoji; en consola Windows (cp1252) print() revienta sin
# esto. GitHub Actions ya es UTF-8, pero no debe romper tampoco en local.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).parent))
from notify_telegram import send_telegram  # noqa: E402
from duration_monitor import _fred_latest, _yfinance_price, LEVELS  # noqa: E402

FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"

LADDER = [
    (270.0, "🟢 &lt;270 bps — rotación, no crisis"),
    (285.0, "🟡 270–285 bps — primer escalón, empieza a vigilarse"),
    (300.0, "🟠 285–300 bps — segundo escalón, alerta"),
    (325.0, "🔴 300–325 bps — tercer escalón, estrés significativo"),
    (float("inf"), "🚨 ≥325 bps — cuarto escalón, la película cambia"),
]


def classify_zone(hy_bps: float) -> str:
    for threshold, label in LADDER:
        if hy_bps < threshold:
            return label
    return LADDER[-1][1]


def fetch_hy_history(limit: int = 12) -> list[tuple[str, float]]:
    """Últimas `limit` observaciones de BAMLH0A0HYM2, en bps, orden ascendente por fecha."""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise EnvironmentError("FRED_API_KEY no configurada (.env local o GitHub Secrets)")
    params = {
        "series_id": "BAMLH0A0HYM2", "api_key": key, "file_type": "json",
        "sort_order": "desc", "limit": limit,
    }
    r = requests.get(FRED_API_BASE, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "observations" not in data:
        raise ValueError(f"Respuesta inesperada de FRED: {data.get('error_message', data)}")
    obs = [(o["date"], float(o["value"]) * 100) for o in data["observations"] if o["value"] != "."]
    obs.sort(key=lambda x: x[0])
    return obs


def find_closest_at_or_before(history: list[tuple[str, float]], target_date: date) -> tuple[str, float] | None:
    """Misma semántica 'closest at or before N days ago' ya usada en rotacion.html/relative.html."""
    candidates = [h for h in history if datetime.strptime(h[0], "%Y-%m-%d").date() <= target_date]
    if not candidates:
        return None
    return max(candidates, key=lambda h: h[0])


def format_date_es(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{d.day:02d}-{months[d.month - 1]}"


def build_report(history: list[tuple[str, float]], wti: float | None, y10: float | None) -> str:
    current_date, current_bps = history[-1]
    week_ago = find_closest_at_or_before(history[:-1], datetime.strptime(current_date, "%Y-%m-%d").date() - timedelta(days=7))

    lines = ["📊 <b>HY Spread — informe diario</b>"]
    lines.append(f"Ahora: <b>{current_bps:.0f} bps</b> ({current_date})")

    if week_ago is not None:
        week_ago_date, week_ago_bps = week_ago
        delta = current_bps - week_ago_bps
        sign = "+" if delta >= 0 else ""
        lines.append(f"Hace 1 semana: {week_ago_bps:.0f} bps ({week_ago_date}) → Δ {sign}{delta:.0f} bps")
    else:
        lines.append("Hace 1 semana: sin dato suficiente todavía")

    lines.append("")
    lines.append("Últimos días hábiles:")
    for d, bps in history[-6:]:
        lines.append(f"  {format_date_es(d)}: {bps:.0f}")

    lines.append("")
    lines.append(f"Zona actual: {classify_zone(current_bps)}")
    lines.append("Escalera de vigilancia: 270 → 285 → 300 → 325")

    context_bits = []
    if wti is not None:
        context_bits.append(f"WTI ${wti:.2f}")
    if y10 is not None:
        flag = " (por encima del umbral de estrés 4.60%)" if y10 > LEVELS["core_break_10y"] else ""
        context_bits.append(f"10Y {y10:.2f}%{flag}")
    if context_bits:
        lines.append("")
        lines.append("Contexto: " + " | ".join(context_bits))

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Imprime el informe en vez de enviarlo por Telegram")
    args = parser.parse_args()

    print("Fetching BAMLH0A0HYM2 history (FRED) + WTI (yfinance) + DGS10 (FRED)...")
    history = fetch_hy_history()
    if not history:
        print("Sin observaciones de HY spread disponibles hoy — nada que informar.", file=sys.stderr)
        sys.exit(1)

    wti = _yfinance_price("CL=F")
    y10, _y10_date = _fred_latest("DGS10")

    message = build_report(history, wti, y10)
    print(message.replace("&lt;", "<"))

    if args.dry_run:
        print("[DRY RUN] No enviado a Telegram.")
        return

    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID no configurados, no se puede enviar el informe.", file=sys.stderr)
        sys.exit(1)

    ok = send_telegram(token, chat_id, message)
    print(f"Telegram {'enviado' if ok else 'FALLÓ'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
