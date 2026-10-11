"""
Pluggable reminder destinations. Pick one with REMINDER_DESTINATION in .env
(default: todoist).

To add a new destination: create destinations/<name>.py following
todoist.py or notion.py as a template (see base.py for the interface),
then add it to REGISTRY below.
"""

from __future__ import annotations

from .base import Assignment, Destination
from .notion import NotionDestination
from .todoist import TodoistDestination

REGISTRY: dict[str, type] = {
    "todoist": TodoistDestination,
    "notion": NotionDestination,
}


def get_destination(name: str, *, dry_run: bool) -> Destination:
    key = (name or "").strip().lower() or "todoist"
    if key == "google_tasks":
        raise SystemExit(
            "Google Tasks support was removed. Set REMINDER_DESTINATION to one of: "
            f"{', '.join(sorted(REGISTRY))} in .env (see README for setup)."
        )
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
