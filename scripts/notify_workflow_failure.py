"""
Workflow failure notifier — Market Update Pipeline

Runs as the LAST step of market-update.yml, with `if: failure()` — only
executes when an earlier required step (one WITHOUT continue-on-error) has
actually failed and put the job in a failing state. Queries the GitHub
Actions API for this specific run to find which step(s) failed, and sends a
Telegram alert naming them plus a direct link to the run log, so a hard
failure doesn't sit unnoticed until someone happens to check the Actions tab
by hand (see the incident that motivated this: Step 1 fetch data failed 3
scheduled runs in a row on 2026-08-24/25 with nobody aware until asked).

Deliberately scoped to hard job-level failures only. Steps that already have
continue-on-error: true (Cava, Koncorde alerts, Duration Monitor, Mirror
Espejo, Insider Activity, Portfolio snapshot, Telegram notify/bot commands)
never fail the job, so this never fires for them — that's intentional, those
are meant to degrade silently; alerting on every one would be noise.

Env vars (all standard GitHub Actions context, wired in the workflow):
  GITHUB_TOKEN        — Actions token (needs `actions: read` permission)
  GITHUB_REPOSITORY   — auto-provided by Actions ("owner/repo")
  GITHUB_RUN_ID       — auto-provided by Actions
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID — same secrets the rest of the pipeline uses
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

# Alert message contains emoji; Windows consoles default to cp1252 and crash
# on print() otherwise. GitHub Actions (ubuntu-latest) is already UTF-8, so
# this only matters for local testing, but it must not crash there either
# (same fix already applied in duration_monitor.py).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
from notify_telegram import send_telegram  # noqa: E402


def find_failed_steps(repo: str, run_id: str, gh_token: str | None) -> list[str]:
    """Returns ["job → step", ...] for every step with conclusion == failure."""
    headers = {"Accept": "application/vnd.github+json"}
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs",
            headers=headers,
            timeout=20,
        )
        r.raise_for_status()
    except Exception as exc:
        print(f"No se pudo consultar la API de Actions: {exc}", file=sys.stderr)
        return []

    failed = []
    for job in r.json().get("jobs", []):
        for step in job.get("steps", []):
            if step.get("conclusion") == "failure":
                failed.append(f"{job['name']} → {step['name']}")
    return failed


def main() -> None:
    repo     = os.environ.get("GITHUB_REPOSITORY")
    run_id   = os.environ.get("GITHUB_RUN_ID")
    gh_token = os.environ.get("GITHUB_TOKEN")
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id  = os.environ.get("TELEGRAM_CHAT_ID")

    if not tg_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID no configurados, no se puede notificar el fallo.", file=sys.stderr)
        sys.exit(1)

    failed_steps = find_failed_steps(repo, run_id, gh_token) if (repo and run_id) else []
    steps_txt = "\n".join(f"• {s}" for s in failed_steps) if failed_steps else "(no se pudo identificar el step exacto — revisar el log)"
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else None
    link_line = f'\n\n<a href="{run_url}">Ver log completo</a>' if run_url else ""

    msg = f"🔴 <b>Market Update Pipeline falló</b>\n\n{steps_txt}{link_line}"

    ok = send_telegram(tg_token, chat_id, msg)
    print(f"Notificación de fallo {'enviada' if ok else 'FALLÓ'}.")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
