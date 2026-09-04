#!/usr/bin/env python3
"""
assignment-sync: pull upcoming assignments from Gradescope + bCourses (Canvas)
and create reminders for them in Google Tasks, one task list per course.

Run:  python sync.py            (normal sync)
      python sync.py --dry-run  (print what would happen, touch nothing)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests
from dotenv import load_dotenv

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

GRADESCOPE_EMAIL = os.getenv("GRADESCOPE_EMAIL", "")
GRADESCOPE_PASSWORD = os.getenv("GRADESCOPE_PASSWORD", "")
CANVAS_BASE_URL = os.getenv("CANVAS_BASE_URL", "https://bcourses.berkeley.edu").rstrip("/")
CANVAS_TOKEN = os.getenv("CANVAS_TOKEN", "")

# Only create reminders for assignments due within this many days.
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "21"))
# Put the reminder this many days BEFORE the due date (0 = on the due date).
REMIND_DAYS_BEFORE = int(os.getenv("REMIND_DAYS_BEFORE", "0"))

GOOGLE_CREDENTIALS = HERE / "credentials.json"
GOOGLE_TOKEN = HERE / "token.json"
STATE_FILE = HERE / "synced.json"
ALIASES_FILE = HERE / "course_aliases.json"

SCOPES = ["https://www.googleapis.com/auth/tasks"]

log = logging.getLogger("sync")


# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------

@dataclass
class Assignment:
    source: str            # "gradescope" | "canvas"
    source_id: str
    course: str            # normalized course label, e.g. "CS 61A"
    title: str
    due: datetime | None   # timezone-aware
    url: str = ""
    submitted: bool = False

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


# ----------------------------------------------------------------------------
# Course-name normalization
# ----------------------------------------------------------------------------

DEPT_ALIASES = {
    "COMPSCI": "CS", "ELENG": "EE", "MATH": "Math", "PHYSICS": "Physics",
    "DATA": "Data", "STAT": "Stat", "ENGIN": "Engin",
}
_COURSE_RE = re.compile(r"\b([A-Z]{2,8})\s*[- ]?\s*([A-Z]?\d{1,3}[A-Z]{0,2})\b", re.IGNORECASE)


def load_aliases() -> dict[str, str]:
    if ALIASES_FILE.exists():
        try:
            return json.loads(ALIASES_FILE.read_text())
        except json.JSONDecodeError:
            log.warning("course_aliases.json is not valid JSON; ignoring it")
    return {}


def normalize_course(raw: str, aliases: dict[str, str]) -> str:
    """Turn 'Fall 2026 COMPSCI 61A 001' or 'CS 61A' into 'CS 61A'."""
    if raw in aliases:
        return aliases[raw]
    m = _COURSE_RE.search(raw)
    if not m:
        return raw.strip()
    dept, num = m.group(1).upper(), m.group(2).upper()
    label = f"{DEPT_ALIASES.get(dept, dept)} {num}"
    return aliases.get(label, label)


# ----------------------------------------------------------------------------
# Gradescope
# ----------------------------------------------------------------------------

def fetch_gradescope(aliases: dict[str, str]) -> list[Assignment]:
    if not (GRADESCOPE_EMAIL and GRADESCOPE_PASSWORD):
        log.info("Gradescope credentials not set; skipping Gradescope")
        return []

    from gradescopeapi.classes.connection import GSConnection

    conn = GSConnection()
    conn.login(GRADESCOPE_EMAIL, GRADESCOPE_PASSWORD)
    courses = conn.account.get_courses().get("student", {})
    out: list[Assignment] = []

    for course_id, course in courses.items():
        label = normalize_course(course.name or course.full_name, aliases)
        try:
            items = conn.account.get_assignments(course_id)
        except Exception as e:  # noqa: BLE001
            log.warning("Gradescope: could not read course %s (%s): %s", label, course_id, e)
            continue
        for it in items:
            status = (it.submissions_status or "").lower()
            out.append(Assignment(
                source="gradescope",
                source_id=str(it.assignment_id),
                course=label,
                title=it.name.strip(),
                due=_aware(it.due_date),
                url=f"https://www.gradescope.com/courses/{course_id}/assignments/{it.assignment_id}",
                submitted="submitted" in status and "no submission" not in status,
            ))
    log.info("Gradescope: %d assignments across %d courses", len(out), len(courses))
    return out


# ----------------------------------------------------------------------------
# bCourses (Canvas)
# ----------------------------------------------------------------------------

def _canvas_get(path: str, **params) -> list[dict]:
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    headers = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
    params.setdefault("per_page", 100)
    results: list[dict] = []
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        results.extend(data if isinstance(data, list) else [data])
        url = r.links.get("next", {}).get("url")
        params = {}
    return results


def fetch_canvas(aliases: dict[str, str]) -> list[Assignment]:
    if not CANVAS_TOKEN:
        log.info("CANVAS_TOKEN not set; skipping bCourses")
        return []

    courses = _canvas_get("/courses", enrollment_state="active", enrollment_type="student")
    out: list[Assignment] = []
    for c in courses:
        label = normalize_course(c.get("course_code") or c.get("name") or str(c["id"]), aliases)
        try:
            items = _canvas_get(f"/courses/{c['id']}/assignments",
                                **{"include[]": "submission", "order_by": "due_at"})
        except requests.HTTPError as e:
            log.warning("bCourses: could not read %s: %s", label, e)
            continue
        for it in items:
            if not it.get("published", True):
                continue
            state = (it.get("submission") or {}).get("workflow_state", "unsubmitted")
            out.append(Assignment(
                source="canvas",
                source_id=str(it["id"]),
                course=label,
                title=(it.get("name") or "").strip(),
                due=_parse_iso(it.get("due_at")),
                url=it.get("html_url", ""),
                submitted=state in ("submitted", "graded", "pending_review"),
            ))
    log.info("bCourses: %d assignments across %d courses", len(out), len(courses))
    return out


# ----------------------------------------------------------------------------
# Google Tasks
# ----------------------------------------------------------------------------

class GoogleTasks:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.service = None if dry_run else self._build()
        self._lists: dict[str, str] | None = None

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


def reminder_date(due: datetime) -> str:
    """Google Tasks keeps only the date part of 'due'; send local date as midnight UTC."""
    d = (due - timedelta(days=REMIND_DAYS_BEFORE)).astimezone().date()
    return f"{d.isoformat()}T00:00:00.000Z"


def task_body(a: Assignment) -> dict:
    notes = ["Due: " + a.due.astimezone().strftime("%a %b %d, %I:%M %p")]
    if a.url:
        notes.append(a.url)
    return {"title": a.title, "notes": "\n".join(notes), "due": reminder_date(a.due)}


# ----------------------------------------------------------------------------
# Sync
# ----------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            log.warning("synced.json corrupt; starting fresh")
    return {}


def sync(assignments: Iterable[Assignment], dry_run: bool) -> None:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=LOOKAHEAD_DAYS)
    state = load_state()
    gt = GoogleTasks(dry_run=dry_run)
    added = updated = completed = skipped = 0

    for a in assignments:
        rec = state.get(a.key)

        if rec:  # already tracked: keep the reminder in sync
            if a.submitted and not rec.get("completed"):
                gt.patch(rec["list_id"], rec["task_id"], {"status": "completed"})
                rec["completed"] = True
                completed += 1
                log.info("Completed: %s / %s", a.course, a.title)
            elif a.due and rec.get("due") != a.due.isoformat():
                gt.patch(rec["list_id"], rec["task_id"], task_body(a))
                rec["due"] = a.due.isoformat()
                updated += 1
                log.info("Due date changed: %s / %s", a.course, a.title)
            continue

        if a.submitted or not a.due or a.due < now or a.due > horizon:
            skipped += 1
            continue

        list_id = gt.list_id(a.course)
        task_id = gt.insert(list_id, task_body(a))
        state[a.key] = {"list_id": list_id, "task_id": task_id, "due": a.due.isoformat(),
                        "title": a.title, "course": a.course, "completed": False}
        added += 1
        log.info("Added %s / %s (due %s)", a.course, a.title, a.due.astimezone().strftime("%b %d"))

    if not dry_run:
        STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))
    log.info("Done: %d added, %d updated, %d marked complete, %d skipped",
             added, updated, completed, skipped)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    aliases = load_aliases()
    assignments: list[Assignment] = []
    for fetch in (fetch_gradescope, fetch_canvas):
        try:
            assignments.extend(fetch(aliases))
        except Exception as e:  # noqa: BLE001
            log.error("%s failed: %s", fetch.__name__, e)
    if not assignments:
        log.warning("No assignments fetched from any source; check your .env")
        return
    sync(assignments, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
