"""Failure-handling behavior: what happens when things go wrong mid-run."""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest
import requests

import sync
from destinations.google_tasks import GoogleTasksDestination
from destinations.notion import NotionDestination
from destinations.todoist import TodoistDestination
from reliability.lock import FileLock


# --- sync(): one failure must not corrupt state or block the rest -----------

def test_failed_update_is_not_recorded_so_it_retries_next_run(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=fake_tasks)
    submitted = make_assignment(source=a.source, source_id=a.source_id, days_from_now=5, submitted=True)

    fake_tasks.patch_ok = False  # e.g. a network blip while completing the task
    counts = sync.sync([submitted], dry_run=False, destination=fake_tasks)
    assert counts["failed"] == 1 and counts["completed"] == 0
    assert json.loads(sync.STATE_FILE.read_text())[a.key]["completed"] is False

    fake_tasks.patch_ok = True  # next run, the network is back
    counts = sync.sync([submitted], dry_run=False, destination=fake_tasks)
    assert counts["completed"] == 1 and counts["failed"] == 0
    assert json.loads(sync.STATE_FILE.read_text())[a.key]["completed"] is True


def test_failed_due_date_update_is_retried_next_run(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=fake_tasks)
    moved = make_assignment(source=a.source, source_id=a.source_id, days_from_now=9)

    fake_tasks.patch_ok = False
    assert sync.sync([moved], dry_run=False, destination=fake_tasks)["failed"] == 1
    fake_tasks.patch_ok = True
    assert sync.sync([moved], dry_run=False, destination=fake_tasks)["updated"] == 1


def test_one_failing_reminder_does_not_block_the_others(make_assignment, fake_tasks):
    good1 = make_assignment(source_id="1", title="Good 1")
    bad = make_assignment(source_id="2", title="Bad")
    good2 = make_assignment(source_id="3", title="Good 2")
    fake_tasks.fail_insert_for = {"Bad"}

    counts = sync.sync([good1, bad, good2], dry_run=False, destination=fake_tasks)

    assert counts["added"] == 2 and counts["failed"] == 1
    state = json.loads(sync.STATE_FILE.read_text())
    assert set(state) == {good1.key, good2.key}  # the failed one is retried next run


def test_state_is_saved_as_it_goes_so_a_crash_cannot_cause_duplicates(make_assignment, fake_tasks):
    """If the run dies halfway, reminders already created must be remembered,
    or the next run would create every one of them again."""
    items = [make_assignment(source_id=str(i), title=f"HW{i}") for i in range(4)]
    real_insert = fake_tasks.insert

    def insert_then_die(list_id, body):
        if body["title"] == "HW2":
            raise KeyboardInterrupt  # not an Exception: nothing in sync() may swallow it
        return real_insert(list_id, body)

    fake_tasks.insert = insert_then_die
    with pytest.raises(KeyboardInterrupt):
        sync.sync(items, dry_run=False, destination=fake_tasks)

    assert set(json.loads(sync.STATE_FILE.read_text())) == {items[0].key, items[1].key}

    fake_tasks.insert = real_insert  # rerun after the crash
    counts = sync.sync(items, dry_run=False, destination=fake_tasks)
    assert counts["added"] == 2  # only HW2 and HW3; HW0/HW1 are not duplicated
    assert len(fake_tasks.tasks) == 4


# --- destinations: patch() reports success vs. failure honestly -------------

def _http_error(status):
    response = MagicMock()
    response.status_code = status
    return requests.HTTPError(f"{status}", response=response)


@pytest.mark.parametrize("make_dest, session_method", [
    (lambda: NotionDestination(), "patch"),
    (lambda: TodoistDestination(), "post"),
])
def test_http_destinations_patch_results(make_dest, session_method, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db")
    monkeypatch.setenv("TODOIST_TOKEN", "t")
    dest = make_dest()
    session = dest._get_session()

    ok = MagicMock()
    monkeypatch.setattr(session, session_method, MagicMock(return_value=ok))
    assert dest.patch("l", "t", {"content": "x"}) is True

    for gone in (404, 410):  # deleted by hand: nothing to update, don't retry forever
        bad = MagicMock()
        bad.raise_for_status.side_effect = _http_error(gone)
        monkeypatch.setattr(session, session_method, MagicMock(return_value=bad))
        assert dest.patch("l", "t", {"content": "x"}) is True

    bad = MagicMock()
    bad.raise_for_status.side_effect = _http_error(503)
    monkeypatch.setattr(session, session_method, MagicMock(return_value=bad))
    assert dest.patch("l", "t", {"content": "x"}) is False

    monkeypatch.setattr(session, session_method, MagicMock(side_effect=requests.ConnectionError("down")))
    assert dest.patch("l", "t", {"content": "x"}) is False  # no exception escapes


def test_google_patch_results(monkeypatch):
    class FakeHttpError(Exception):
        def __init__(self, status):
            self.resp = MagicMock(status=status)

    dest = GoogleTasksDestination.__new__(GoogleTasksDestination)
    dest.dry_run = False
    service = MagicMock()
    dest.service = service
    execute = service.tasks().patch().execute

    execute.return_value = {}
    assert dest.patch("l", "t", {}) is True
    execute.side_effect = FakeHttpError(404)
    assert dest.patch("l", "t", {}) is True
    execute.side_effect = FakeHttpError(500)
    assert dest.patch("l", "t", {}) is False
    execute.side_effect = ConnectionError("down")
    assert dest.patch("l", "t", {}) is False


def test_google_calls_ask_the_client_library_to_retry(monkeypatch):
    dest = GoogleTasksDestination.__new__(GoogleTasksDestination)
    dest.dry_run = False
    service = MagicMock()
    dest.service = service
    service.tasks().insert().execute.return_value = {"id": "x"}
    dest.insert("l", {})
    _, kwargs = service.tasks().insert().execute.call_args
    assert kwargs.get("num_retries", 0) >= 1


# --- running it: outcomes, status, notification, lock, watchdog --------------

class FakeSource:
    def __init__(self, name, result=None, error=None):
        self.name, self._result, self._error = name, result or [], error

    def fetch(self, aliases):
        if self._error:
            raise self._error
        return self._result


@pytest.fixture
def run_main(monkeypatch, fake_tasks):
    def _run(sources, *, argv=("sync.py",), destination=fake_tasks):
        monkeypatch.setattr(sync, "ALL_SOURCES", sources)
        monkeypatch.setattr(sync, "get_destination", lambda name, dry_run: destination)
        monkeypatch.setattr(sys, "argv", list(argv))
        try:
            sync.main()
        except SystemExit as e:
            return e.code
        return None  # returned normally (e.g. skipped because another run holds the lock)
    return _run


def test_clean_run_exits_zero_and_records_success(run_main, make_assignment):
    code = run_main([FakeSource("canvas", [make_assignment()])])
    assert code == 0
    assert json.loads(sync.STATUS_FILE.read_text())["consecutive_failures"] == 0


def test_a_failing_source_makes_the_run_fail_but_the_other_still_syncs(run_main, make_assignment, fake_tasks):
    code = run_main([FakeSource("gradescope", error=RuntimeError("login changed")),
                     FakeSource("canvas", [make_assignment()])])
    assert code == 1  # scheduler / status now see the problem
    assert len(fake_tasks.tasks) == 1  # ...but the working source's reminders still went out
    assert "gradescope failed" in json.loads(sync.STATUS_FILE.read_text())["last_error"]


def test_every_source_failing_is_a_failure_not_a_quiet_warning(run_main):
    code = run_main([FakeSource("canvas", error=RuntimeError("down"))])
    assert code == 1


def test_no_configured_sources_is_not_an_error(run_main):
    assert run_main([FakeSource("canvas", [])]) == 0


def test_one_ordinary_failure_stays_quiet_the_second_notifies(run_main, notifications):
    failing = [FakeSource("canvas", error=RuntimeError("Canvas is down"))]
    run_main(failing)
    assert notifications == []
    run_main(failing)
    assert len(notifications) == 1
    assert "Canvas is down" in notifications[0][1]


def test_failure_needing_the_user_notifies_immediately(monkeypatch, run_main, notifications):
    def dead_login(name, dry_run):
        raise SystemExit("Google login expired or was revoked. Run `uv run sync.py` once in a terminal.")

    monkeypatch.setattr(sync, "ALL_SOURCES", [FakeSource("canvas")])
    monkeypatch.setattr(sync, "get_destination", dead_login)
    monkeypatch.setattr(sys, "argv", ["sync.py"])
    with pytest.raises(SystemExit) as exc:
        sync.main()
    assert exc.value.code == 1
    assert len(notifications) == 1 and "Google login expired" in notifications[0][1]


def test_corrupt_state_is_reported_as_needing_attention(run_main, make_assignment, notifications):
    sync.STATE_FILE.write_text("{broken")
    code = run_main([FakeSource("canvas", [make_assignment()])])
    assert code == 1
    assert len(notifications) == 1


def test_run_is_skipped_when_another_sync_holds_the_lock(run_main, make_assignment, fake_tasks):
    with FileLock(sync.LOCK_FILE):
        assert run_main([FakeSource("canvas", [make_assignment()])]) is None
    assert fake_tasks.tasks == {}
    assert not sync.STATUS_FILE.exists()  # a skipped run is not a success or a failure


def test_lock_is_released_after_the_run(run_main, make_assignment):
    run_main([FakeSource("canvas", [make_assignment()])])
    with FileLock(sync.LOCK_FILE):  # would raise LockBusy if the run had leaked it
        pass


def test_dry_run_touches_no_status_lock_or_notifications(run_main, make_assignment, notifications):
    code = run_main([FakeSource("canvas", error=RuntimeError("down"))], argv=("sync.py", "--dry-run"))
    assert code == 1
    assert not sync.STATUS_FILE.exists() and not sync.LOCK_FILE.exists()
    assert notifications == []


def test_watchdog_gives_up_and_records_a_failure(monkeypatch):
    exits = []
    monkeypatch.setattr(os, "_exit", lambda code: exits.append(code))
    timer = sync._start_watchdog(0.05)
    timer.join(2)
    assert exits == [3]
    assert "timed out" in json.loads(sync.STATUS_FILE.read_text())["last_error"]


def test_watchdog_stays_quiet_when_the_run_finishes_in_time(monkeypatch):
    exits = []
    monkeypatch.setattr(os, "_exit", lambda code: exits.append(code))
    timer = sync._start_watchdog(0.2)
    timer.cancel()
    timer.join(1)
    assert exits == []
