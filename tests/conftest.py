"""Shared fixtures: redirect every on-disk file sync.py touches into tmp_path,
so tests never read or write the real .env / synced.json / token.json."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import sync
from destinations import google_tasks as google_tasks_module
from sources import base as sources_base


@pytest.fixture(autouse=True)
def isolated_files(tmp_path, monkeypatch):
    """Point every module-level file path at a scratch directory."""
    monkeypatch.setattr(sync, "STATE_FILE", tmp_path / "synced.json")
    monkeypatch.setattr(google_tasks_module, "GOOGLE_TOKEN", tmp_path / "token.json")
    monkeypatch.setattr(google_tasks_module, "GOOGLE_CREDENTIALS", tmp_path / "credentials.json")
    monkeypatch.setattr(sources_base, "ALIASES_FILE", tmp_path / "course_aliases.json")
    yield tmp_path


@pytest.fixture
def make_assignment():
    """Factory for Assignment objects with sane defaults, due N days from now."""
    def _make(*, source="canvas", source_id="1", course="CS 61A", title="HW1",
               days_from_now=5, url="https://example.test/a/1", submitted=False):
        due = None
        if days_from_now is not None:
            due = datetime.now(timezone.utc) + timedelta(days=days_from_now)
        return sources_base.Assignment(
            source=source, source_id=source_id, course=course, title=title,
            due=due, url=url, submitted=submitted,
        )
    return _make


class FakeDestination:
    """Records calls instead of hitting the network; mirrors the Destination
    protocol (destinations/base.py) well enough to drive sync()'s state machine."""

    name = "fake"

    def __init__(self):
        self.dry_run = False
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, dict] = {}
        self._next_list_id = 0
        self._next_task_id = 0
        self.patched: list[tuple[str, str, dict]] = []

    def enabled(self) -> bool:
        return True

    def list_id(self, course: str) -> str:
        if course not in self.lists:
            self._next_list_id += 1
            self.lists[course] = f"list-{self._next_list_id}"
        return self.lists[course]

    def task_body(self, a) -> dict:
        return {"title": a.title, "due": a.due.isoformat() if a.due else None, "url": a.url}

    def completed_body(self) -> dict:
        return {"status": "completed"}

    def insert(self, list_id: str, body: dict) -> str:
        self._next_task_id += 1
        task_id = f"task-{self._next_task_id}"
        self.tasks[task_id] = {**body, "list_id": list_id, "status": "needsAction"}
        return task_id

    def patch(self, list_id: str, task_id: str, body: dict) -> None:
        self.patched.append((list_id, task_id, dict(body)))
        if task_id in self.tasks:
            self.tasks[task_id].update(body)


@pytest.fixture
def fake_tasks():
    return FakeDestination()


@pytest.fixture
def fake_destination_factory():
    """Build a FakeDestination with a chosen `.name`, for tests that need
    two distinct destinations (e.g. simulating a REMINDER_DESTINATION switch)."""
    def _make(name: str) -> FakeDestination:
        d = FakeDestination()
        d.name = name
        return d
    return _make
