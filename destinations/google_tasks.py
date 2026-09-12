"""Google Tasks -- one task list per course."""

from __future__ import annotations

import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

from .base import Assignment

log = logging.getLogger("sync")

HERE = Path(__file__).resolve().parent.parent
GOOGLE_CREDENTIALS = HERE / "credentials.json"
GOOGLE_TOKEN = HERE / "token.json"
SCOPES = ["https://www.googleapis.com/auth/tasks"]


class GoogleTasksDestination:
    name = "google_tasks"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.service = None if dry_run else self._build()
        self._lists: dict[str, str] | None = None

    @property
    def remind_days_before(self) -> int:
        return int(os.getenv("REMIND_DAYS_BEFORE", "0"))

    def enabled(self) -> bool:
        # credentials.json ships with the repo, so this is normally always
        # true; the real "is this set up" gate is GOOGLE_CREDENTIALS existing,
        # which _build() already enforces with a clear error when it's missing.
        return GOOGLE_CREDENTIALS.exists()

    @staticmethod
    def _build():
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if GOOGLE_TOKEN.exists():
            creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not GOOGLE_CREDENTIALS.exists():
                    sys.exit(f"Missing {GOOGLE_CREDENTIALS.name}. See README for the Google Cloud setup.")
                flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CREDENTIALS), SCOPES)
                creds = flow.run_local_server(port=0)
            GOOGLE_TOKEN.write_text(creds.to_json())
        return build("tasks", "v1", credentials=creds, cache_discovery=False)

    def list_id(self, course: str) -> str:
        if self._lists is None:
            self._lists = {}
            if not self.dry_run:
                page = None
                while True:
                    resp = self.service.tasklists().list(maxResults=100, pageToken=page).execute()
                    for tl in resp.get("items", []):
                        self._lists[tl["title"]] = tl["id"]
                    page = resp.get("nextPageToken")
                    if not page:
                        break
        if course not in self._lists:
            log.info("Creating task list %r", course)
            if self.dry_run:
                self._lists[course] = f"dry-{course}"
            else:
                self._lists[course] = self.service.tasklists().insert(body={"title": course}).execute()["id"]
        return self._lists[course]

    def task_body(self, a: Assignment) -> dict:
        notes = ["Due: " + a.due.astimezone().strftime("%a %b %d, %I:%M %p")]
        if a.url:
            notes.append(a.url)
        return {"title": a.title, "notes": "\n".join(notes), "due": self._reminder_date(a)}

    def completed_body(self) -> dict:
        return {"status": "completed"}

    def _reminder_date(self, a: Assignment) -> str:
        """Google Tasks keeps only the date part of 'due'; send local date as midnight UTC."""
        d = (a.due - timedelta(days=self.remind_days_before)).astimezone().date()
        return f"{d.isoformat()}T00:00:00.000Z"

    def insert(self, list_id: str, body: dict) -> str:
        if self.dry_run:
            return "dry-task"
        return self.service.tasks().insert(tasklist=list_id, body=body).execute()["id"]

    def patch(self, list_id: str, task_id: str, body: dict) -> None:
        if self.dry_run:
            return
        try:
            self.service.tasks().patch(tasklist=list_id, task=task_id, body=body).execute()
        except Exception as e:  # noqa: BLE001  (task deleted by hand, etc.)
            log.warning("Could not update task %s: %s", task_id, e)
