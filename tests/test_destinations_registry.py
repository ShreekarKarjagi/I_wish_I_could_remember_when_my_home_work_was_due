import pytest

from destinations import get_destination
from destinations.google_tasks import GoogleTasksDestination
from destinations.notion import NotionDestination


def test_defaults_to_google_tasks_when_dry_run(monkeypatch, tmp_path):
    import destinations.google_tasks as google_tasks_module
    monkeypatch.setattr(google_tasks_module, "GOOGLE_CREDENTIALS", tmp_path / "credentials.json")
    dest = get_destination("google_tasks", dry_run=True)
    assert isinstance(dest, GoogleTasksDestination)


def test_selects_notion_by_name(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-1")
    dest = get_destination("notion", dry_run=False)
    assert isinstance(dest, NotionDestination)


def test_name_matching_is_case_and_whitespace_insensitive(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-1")
    dest = get_destination("  Notion  ", dry_run=False)
    assert isinstance(dest, NotionDestination)


def test_unknown_destination_name_exits_with_clear_message():
    with pytest.raises(SystemExit, match="Unknown REMINDER_DESTINATION"):
        get_destination("carrier-pigeon", dry_run=False)


def test_unconfigured_notion_exits_with_clear_message(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)
    with pytest.raises(SystemExit, match="isn't configured"):
        get_destination("notion", dry_run=False)


def test_unconfigured_destination_is_allowed_in_dry_run(monkeypatch):
    # dry-run shouldn't require real credentials for any destination.
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)
    dest = get_destination("notion", dry_run=True)
    assert isinstance(dest, NotionDestination)
