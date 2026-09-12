"""Notion -- reminders as pages in a database you choose.

Setup:
  1. Create an internal integration at https://www.notion.so/my-integrations
     and copy its secret into NOTION_TOKEN.
  2. Create (or reuse) a Notion database with these properties -- names and
     types matter, since Notion's API rejects a mismatched property type:
       - the database's title property, renamed to "Name"
       - "Course"  -- Select
       - "Due"     -- Date
       - "URL"     -- URL
       - "Done"    -- Checkbox
     (Edit the PROP_* constants below if you'd rather keep your own names.)
  3. Open the database -> "..." menu -> "Connect to" -> pick your integration.
     Notion won't let it see the database otherwise.
  4. Copy the database id into NOTION_DATABASE_ID -- it's the 32-character
     id in the database URL, right before any "?v=".
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

import requests

from .base import Assignment

log = logging.getLogger("sync")

API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Property names in your Notion database -- edit if yours differ.
PROP_TITLE = "Name"
PROP_COURSE = "Course"
PROP_DUE = "Due"
PROP_URL = "URL"
PROP_DONE = "Done"


class NotionDestination:
    name = "notion"

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    @property
    def token(self) -> str:
        return os.getenv("NOTION_TOKEN", "")

    @property
    def database_id(self) -> str:
        return os.getenv("NOTION_DATABASE_ID", "")

    @property
    def remind_days_before(self) -> int:
        return int(os.getenv("REMIND_DAYS_BEFORE", "0"))

    def enabled(self) -> bool:
        return bool(self.token and self.database_id)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def list_id(self, course: str) -> str:
        # Notion groups by the "Course" property below instead of a separate
        # database per course, so every course shares one database id.
        return self.database_id

    def task_body(self, a: Assignment) -> dict:
        due_at = (a.due - timedelta(days=self.remind_days_before)).astimezone()
        properties = {
            PROP_TITLE: {"title": [{"text": {"content": a.title}}]},
            PROP_COURSE: {"select": {"name": a.course}},
            PROP_DUE: {"date": {"start": due_at.isoformat()}},
            PROP_DONE: {"checkbox": False},
        }
        if a.url:
            properties[PROP_URL] = {"url": a.url}
        return {"properties": properties}

    def completed_body(self) -> dict:
        return {"properties": {PROP_DONE: {"checkbox": True}}}

    def insert(self, list_id: str, body: dict) -> str:
        if self.dry_run:
            return "dry-page"
        r = requests.post(
            f"{API_BASE}/pages",
            headers=self._headers(),
            json={"parent": {"database_id": list_id}, **body},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["id"]

    def patch(self, list_id: str, task_id: str, body: dict) -> None:
        if self.dry_run:
            return
        try:
            r = requests.patch(f"{API_BASE}/pages/{task_id}", headers=self._headers(),
                                json=body, timeout=30)
            r.raise_for_status()
        except requests.HTTPError as e:  # page deleted/archived by hand, etc.
            log.warning("Could not update Notion page %s: %s", task_id, e)
