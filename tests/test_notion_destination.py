from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from destinations.notion import NotionDestination


@pytest.fixture
def dest(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret_abc123")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-1")
    monkeypatch.setenv("REMIND_DAYS_BEFORE", "0")
    return NotionDestination()


def test_disabled_without_token_or_database(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)
    assert NotionDestination().enabled() is False


def test_enabled_with_both_set(dest):
    assert dest.enabled() is True


def test_disabled_with_only_token(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret_abc123")
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)
    assert NotionDestination().enabled() is False


def test_list_id_ignores_course_returns_configured_database(dest):
    # Notion groups everything into one database via the "Course" property,
    # not a separate database per course.
    assert dest.list_id("CS 61A") == "db-1"
    assert dest.list_id("EE 16A") == "db-1"


def test_task_body_shapes_notion_page_properties(dest, make_assignment):
    a = make_assignment(title="HW1", course="CS 61A", url="https://x.test/1", days_from_now=5)
    body = dest.task_body(a)
    props = body["properties"]
    assert props["Name"]["title"][0]["text"]["content"] == "HW1"
    assert props["Course"]["select"]["name"] == "CS 61A"
    assert props["Done"]["checkbox"] is False
    assert props["URL"]["url"] == "https://x.test/1"
    assert props["Due"]["date"]["start"].startswith(a.due.astimezone().date().isoformat())


def test_task_body_omits_url_property_when_blank(dest, make_assignment):
    a = make_assignment(url="")
    body = dest.task_body(a)
    assert "URL" not in body["properties"]


def test_task_body_respects_remind_days_before(monkeypatch, make_assignment):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-1")
    monkeypatch.setenv("REMIND_DAYS_BEFORE", "3")
    dest = NotionDestination()
    a = make_assignment(days_from_now=10)
    body = dest.task_body(a)
    expected_date = (a.due - timedelta(days=3)).astimezone().date()
    assert body["properties"]["Due"]["date"]["start"].startswith(expected_date.isoformat())


def test_completed_body_sets_done_checkbox(dest):
    assert dest.completed_body() == {"properties": {"Done": {"checkbox": True}}}


def test_dry_run_insert_and_patch_are_no_ops(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-1")
    dest = NotionDestination(dry_run=True)
    assert dest.insert("db-1", {"properties": {}}) == "dry-page"
    dest.patch("db-1", "dry-page", {"properties": {}})  # must not raise, no network


def test_insert_posts_to_pages_endpoint_with_parent(dest, monkeypatch):
    response = MagicMock()
    response.json.return_value = {"id": "page-123"}
    response.raise_for_status = MagicMock()
    post = MagicMock(return_value=response)
    monkeypatch.setattr("destinations.notion.requests.post", post)

    page_id = dest.insert("db-1", {"properties": {"Name": {}}})

    assert page_id == "page-123"
    _, kwargs = post.call_args
    assert kwargs["json"]["parent"] == {"database_id": "db-1"}
    assert kwargs["headers"]["Authorization"] == "Bearer secret_abc123"
    assert kwargs["headers"]["Notion-Version"]


def test_patch_sends_properties_to_page_endpoint(dest, monkeypatch):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    patch = MagicMock(return_value=response)
    monkeypatch.setattr("destinations.notion.requests.patch", patch)

    dest.patch("db-1", "page-123", {"properties": {"Done": {"checkbox": True}}})

    args, kwargs = patch.call_args
    assert args[0].endswith("/pages/page-123")
    assert kwargs["json"] == {"properties": {"Done": {"checkbox": True}}}


def test_patch_swallows_http_errors_for_deleted_pages(dest, monkeypatch):
    import requests

    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError("404 not found")
    monkeypatch.setattr("destinations.notion.requests.patch", MagicMock(return_value=response))

    dest.patch("db-1", "page-123", {"properties": {}})  # must not raise
