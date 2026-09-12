"""Google Tasks' specific request-body formatting (due-date-as-midnight-UTC,
notes with the URL, etc). Notion's formatting is covered in
test_notion_destination.py since its shape is entirely different."""

from datetime import timedelta

from destinations.google_tasks import GoogleTasksDestination


def test_reminder_date_is_midnight_utc_on_due_date(make_assignment, monkeypatch):
    monkeypatch.setenv("REMIND_DAYS_BEFORE", "0")
    gt = GoogleTasksDestination(dry_run=True)
    a = make_assignment(days_from_now=5)
    body = gt.task_body(a)
    assert body["due"].endswith("T00:00:00.000Z")
    assert body["due"].startswith(a.due.astimezone().date().isoformat())


def test_reminder_date_respects_remind_days_before(make_assignment, monkeypatch):
    monkeypatch.setenv("REMIND_DAYS_BEFORE", "3")
    gt = GoogleTasksDestination(dry_run=True)
    a = make_assignment(days_from_now=5)
    body = gt.task_body(a)
    expected_date = (a.due - timedelta(days=3)).astimezone().date()
    assert body["due"].startswith(expected_date.isoformat())


def test_task_body_includes_title_due_and_url(make_assignment, monkeypatch):
    monkeypatch.setenv("REMIND_DAYS_BEFORE", "0")
    gt = GoogleTasksDestination(dry_run=True)
    a = make_assignment(title="Homework 3", url="https://x.test/hw3", days_from_now=2)
    body = gt.task_body(a)
    assert body["title"] == "Homework 3"
    assert "https://x.test/hw3" in body["notes"]
    assert body["notes"].startswith("Due: ")
    assert body["due"].endswith("Z")


def test_task_body_omits_url_when_blank(make_assignment, monkeypatch):
    monkeypatch.setenv("REMIND_DAYS_BEFORE", "0")
    gt = GoogleTasksDestination(dry_run=True)
    a = make_assignment(url="")
    body = gt.task_body(a)
    assert "\n" not in body["notes"]
