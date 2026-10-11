import pytest

from destinations import get_destination
from destinations.notion import NotionDestination
from destinations.todoist import TodoistDestination


@pytest.mark.parametrize("unset", [None, "", "   "])
def test_defaults_to_todoist_when_unset(unset, monkeypatch):
    monkeypatch.setenv("TODOIST_TOKEN", "t")
    assert isinstance(get_destination(unset, dry_run=False), TodoistDestination)


def test_google_tasks_gets_a_clear_removed_message():
    # Anyone whose .env still says google_tasks should be told why, not just "unknown".
    with pytest.raises(SystemExit, match="Google Tasks support was removed"):
        get_destination("google_tasks", dry_run=False)


def test_selects_notion_by_name(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-1")
    dest = get_destination("notion", dry_run=False)
    assert isinstance(dest, NotionDestination)


def test_selects_todoist_by_name(monkeypatch):
    monkeypatch.setenv("TODOIST_TOKEN", "t")
    dest = get_destination("todoist", dry_run=False)
    assert isinstance(dest, TodoistDestination)


def test_unconfigured_todoist_exits_with_clear_message(monkeypatch):
    monkeypatch.delenv("TODOIST_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="isn't configured"):
        get_destination("todoist", dry_run=False)


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
