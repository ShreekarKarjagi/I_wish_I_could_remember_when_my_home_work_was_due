"""Remembers how recent runs went (status.json) and decides when a failure
is worth interrupting the user about.

Rules: tell the user right away when they must do something (e.g. a
destination token that was never set up); otherwise only after repeated
failures, so one flaky network moment doesn't ping them. Never more than
once a day.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .state import atomic_write_text

FAILURES_BEFORE_NOTIFY = 2
NOTIFY_AT_MOST_EVERY = timedelta(hours=24)


def load_status(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _parse(ts: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def record_result(path: Path, *, ok: bool, error: str | None = None,
                  needs_action: bool = False, now: datetime | None = None) -> bool:
    """Record one run's outcome. Returns True if the user should be notified."""
    now = now or datetime.now(timezone.utc)
    s = load_status(path)
    s["last_attempt"] = now.isoformat()
    notify = False
    if ok:
        s["last_success"] = now.isoformat()
        s["consecutive_failures"] = 0
        s["last_error"] = None
        s["last_notified"] = None  # so the next failure alerts promptly
    else:
        s["consecutive_failures"] = int(s.get("consecutive_failures") or 0) + 1
        s["last_error"] = error
        due = needs_action or s["consecutive_failures"] >= FAILURES_BEFORE_NOTIFY
        last = _parse(s.get("last_notified"))
        notify = due and (last is None or now - last >= NOTIFY_AT_MOST_EVERY)
        if notify:
            s["last_notified"] = now.isoformat()
    atomic_write_text(path, json.dumps(s, indent=2, sort_keys=True))
    return notify
