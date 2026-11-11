"""Reparte los snapshots diarios grandes en fichero vivo (últimos 75 días) + archivo mensual. Ver snapshot_store.py.

Uso: py -3 scripts/rotate_daily_snapshots.py [--dry-run] [--days N] [--today AAAA-MM-DD]
Idempotente: si no hay filas anteriores al corte no toca nada.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot_store as ss  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=ss.LIVE_DAYS)
    ap.add_argument("--today")
    a = ap.parse_args()
    today = date.fromisoformat(a.today) if a.today else datetime.now(timezone.utc).date()
    for name in ss.ROTATED:
        r = ss.rotate(ss.DATA / name, today, a.days, a.dry_run)
        print(("[dry-run] " if a.dry_run else "") + str(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
