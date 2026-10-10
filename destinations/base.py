"""Shared interface for where reminders get written (Google Tasks, Notion, ...)."""

from __future__ import annotations

from typing import Protocol

from sources.base import Assignment  # re-exported for destinations' convenience

__all__ = ["Assignment", "Destination"]


class Destination(Protocol):
    """A place reminders get written to."""

    name: str

    def enabled(self) -> bool:
        """True if this destination is configured (its env vars are set).
        Not checked in --dry-run mode, so dry runs work with nothing set up."""
        ...

    def list_id(self, course: str) -> str:
        """A grouping id for `course` -- e.g. a Google Tasks list id, or just
        the configured Notion database id if this destination groups a
        different way (a "Course" property instead of separate lists)."""
        ...

    def task_body(self, a: Assignment) -> dict:
        """This destination's request body for creating/updating a reminder for `a`."""
        ...

    def completed_body(self) -> dict:
        """The patch body that marks an existing reminder complete."""
        ...

    def insert(self, list_id: str, body: dict) -> str:
        """Create a reminder; return an id that can be used to patch it later."""
        ...

    def patch(self, list_id: str, task_id: str, body: dict) -> bool:
        """Update an existing reminder. Never raises for an ordinary failure.

        Returns True if the reminder is now up to date -- including when it
        no longer exists (the user deleted it by hand; don't recreate it, and
        don't retry forever). Returns False for a transient failure (network
        blip, server error), so the caller leaves its record unchanged and the
        update is simply retried on the next run."""
        ...
