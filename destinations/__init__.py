"""
Pluggable reminder destinations. Pick one with REMINDER_DESTINATION in .env
(default: google_tasks).

To add a new destination: create destinations/<name>.py following
google_tasks.py or notion.py as a template (see base.py for the interface),
then add it to REGISTRY below.
"""

from __future__ import annotations

from .base import Assignment, Destination
from .google_tasks import GoogleTasksDestination
from .notion import NotionDestination

REGISTRY: dict[str, type] = {
    "google_tasks": GoogleTasksDestination,
    "notion": NotionDestination,
}


def get_destination(name: str, *, dry_run: bool) -> Destination:
    key = (name or "google_tasks").strip().lower()
    cls = REGISTRY.get(key)
    if cls is None:
        raise SystemExit(
            f"Unknown REMINDER_DESTINATION={name!r}. Choose one of: {', '.join(sorted(REGISTRY))}"
        )
    dest = cls(dry_run=dry_run)
    if not dry_run and not dest.enabled():
        raise SystemExit(
            f"REMINDER_DESTINATION={key!r} isn't configured yet -- see README for setup."
        )
    return dest


__all__ = ["Assignment", "Destination", "REGISTRY", "get_destination"]
