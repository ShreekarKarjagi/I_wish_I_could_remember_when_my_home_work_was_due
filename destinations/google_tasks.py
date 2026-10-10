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
# googleapiclient retries 5xx/429/dropped connections with backoff this many times.
RETRIES = 3


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
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if GOOGLE_TOKEN.exists():
            creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN), SCOPES)
        if not creds or not creds.valid:
            refreshed = False
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    refreshed = True
                except RefreshError as e:
                    # Google rejected the saved login (expired, revoked, or the
                    # OAuth app is still in "Testing" so tokens die after 7 days).
                    log.warning("Saved Google login no longer works: %s", e)
            if not refreshed:
                # run_sync.bat / run_sync.sh set ASSIGNMENT_SYNC_UNATTENDED because
                # isatty() alone isn't reliable (Task Scheduler can attach a console).
                if os.getenv("ASSIGNMENT_SYNC_UNATTENDED") or not sys.stdin.isatty():
                    # Scheduled run: there's nobody to click "Allow", and opening
                    # a browser would just hang. Say what to do instead.
                    sys.exit("Google login expired or was revoked. Run `uv run sync.py` "
                             "once in a terminal to sign in again.")
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
                    resp = self.service.tasklists().list(maxResults=100, pageToken=page).execute(num_retries=RETRIES)
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
                self._lists[course] = self.service.tasklists().insert(body={"title": course}).execute(num_retries=RETRIES)["id"]
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
        return self.service.tasks().insert(tasklist=list_id, body=body).execute(num_retries=RETRIES)["id"]

    def patch(self, list_id: str, task_id: str, body: dict) -> bool:
        if self.dry_run:
            return True
        try:
            self.service.tasks().patch(tasklist=list_id, task=task_id,
                                       body=body).execute(num_retries=RETRIES)
            return True
        except Exception as e:  # noqa: BLE001
            status = getattr(getattr(e, "resp", None), "status", None)
            if status in (404, 410):  # deleted by hand: nothing left to update
                log.info("Task %s no longer exists in Google Tasks; leaving it alone", task_id)
                return True
            log.warning("Could not update task %s (will retry next run): %s", task_id, e)
            return False
