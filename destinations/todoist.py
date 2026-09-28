"""Todoist -- one project per course.

Setup:
  1. Get a personal API token from Todoist Settings -> Integrations -> Developer.
  2. Put it in TODOIST_TOKEN.

That's it -- projects are created automatically, one per course, the same
way Google Tasks creates one list per course.

Uses the unified Todoist API v1 (https://api.todoist.com/api/v1). The older
REST v2 endpoints (/rest/v2/...) were sunset and now return 410 Gone, so
this intentionally does not use them.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta, timezone

import requests

from .base import Assignment

log = logging.getLogger("sync")

API_BASE = "https://api.todoist.com/api/v1"


class TodoistDestination:
    name = "todoist"

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._projects: dict[str, str] | None = None

    @property
    def token(self) -> str:
        return os.getenv("TODOIST_TOKEN", "")

    @property
    def remind_days_before(self) -> int:
        return int(os.getenv("REMIND_DAYS_BEFORE", "0"))

    def enabled(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def list_id(self, course: str) -> str:
        if self._projects is None:
            self._projects = {}
            if not self.dry_run:
                cursor = ""
                while True:
                    params = {"limit": 200}
                    if cursor:
                        params["cursor"] = cursor
                    r = requests.get(f"{API_BASE}/projects", headers=self._headers(),
                                      params=params, timeout=30)
                    r.raise_for_status()
                    data = r.json()
                    for p in data.get("results", []):
                        self._projects[p["name"]] = p["id"]
                    cursor = data.get("next_cursor")
                    if not cursor:
                        break
        if course not in self._projects:
            log.info("Creating Todoist project %r", course)
            if self.dry_run:
                self._projects[course] = f"dry-{course}"
            else:
                r = requests.post(f"{API_BASE}/projects", headers=self._headers(),
                                   json={"name": course}, timeout=30)
                r.raise_for_status()
                self._projects[course] = r.json()["id"]
        return self._projects[course]

    def task_body(self, a: Assignment) -> dict:
        due_at = (a.due - timedelta(days=self.remind_days_before)).astimezone(timezone.utc)
        body = {
            "content": a.title,
            # Aware datetime -> "YYYY-MM-DDTHH:MM:SSZ", per Todoist's own format.
            "due_datetime": due_at.isoformat().replace("+00:00", "Z"),
        }
        if a.url:
            body["description"] = a.url
        return body

    def completed_body(self) -> dict:
        # Completing a Todoist task is a dedicated endpoint (POST .../close),
        # not a field you set in an update body -- patch() below special-cases
        # this sentinel rather than sending it as real task fields.
        return {"_complete": True}

    def insert(self, list_id: str, body: dict) -> str:
        if self.dry_run:
            return "dry-task"
        r = requests.post(f"{API_BASE}/tasks", headers=self._headers(),
                           json={**body, "project_id": list_id}, timeout=30)
        r.raise_for_status()
        return r.json()["id"]

    def patch(self, list_id: str, task_id: str, body: dict) -> None:
        if self.dry_run:
            return
        try:
            if body.get("_complete"):
                r = requests.post(f"{API_BASE}/tasks/{task_id}/close",
                                   headers=self._headers(), timeout=30)
            else:
                r = requests.post(f"{API_BASE}/tasks/{task_id}", headers=self._headers(),
                                   json=body, timeout=30)
            r.raise_for_status()
        except requests.HTTPError as e:  # task deleted by hand, etc.
            log.warning("Could not update Todoist task %s: %s", task_id, e)
