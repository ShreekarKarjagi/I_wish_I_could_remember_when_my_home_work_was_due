from unittest.mock import MagicMock

import pytest

from destinations.todoist import TodoistDestination


@pytest.fixture
def dest(monkeypatch):
    monkeypatch.setenv("TODOIST_TOKEN", "tok123")
    monkeypatch.setenv("REMIND_DAYS_BEFORE", "0")
    return TodoistDestination()


def test_disabled_without_token(monkeypatch):
    monkeypatch.delenv("TODOIST_TOKEN", raising=False)
    assert TodoistDestination().enabled() is False


def test_enabled_with_token(dest):
    assert dest.enabled() is True


def test_task_body_uses_content_and_due_datetime(dest, make_assignment):
    a = make_assignment(title="HW1", url="https://x.test/1", days_from_now=5)
    body = dest.task_body(a)
    assert body["content"] == "HW1"
    assert body["due_datetime"].endswith("Z")
    assert body["description"] == "https://x.test/1"


def test_task_body_omits_description_when_no_url(dest, make_assignment):
    a = make_assignment(url="")
    body = dest.task_body(a)
    assert "description" not in body


def test_task_body_respects_remind_days_before(monkeypatch, make_assignment):
    from datetime import timedelta, timezone
    monkeypatch.setenv("TODOIST_TOKEN", "t")
    monkeypatch.setenv("REMIND_DAYS_BEFORE", "3")
    dest = TodoistDestination()
    a = make_assignment(days_from_now=10)
    body = dest.task_body(a)
    expected = (a.due - timedelta(days=3)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    assert body["due_datetime"] == expected


def test_completed_body_is_a_close_sentinel(dest):
    assert dest.completed_body() == {"_complete": True}


def test_dry_run_insert_and_patch_are_no_ops(monkeypatch):
    monkeypatch.setenv("TODOIST_TOKEN", "t")
    dest = TodoistDestination(dry_run=True)
    assert dest.insert("dry-CS 61A", {"content": "HW"}) == "dry-task"
    dest.patch("dry-CS 61A", "dry-task", {"_complete": True})  # must not raise


def test_dry_run_list_id_is_deterministic_placeholder():
    dest = TodoistDestination(dry_run=True)
    assert dest.list_id("CS 61A") == "dry-CS 61A"
    assert dest.list_id("CS 61A") == "dry-CS 61A"  # cached, not recomputed


def test_list_id_reuses_existing_project(dest, monkeypatch):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"results": [{"name": "CS 61A", "id": "proj-1"}], "next_cursor": None}
    session = dest._get_session()
    get = MagicMock(return_value=response)
    monkeypatch.setattr(session, "get", get)
    post = MagicMock()
    monkeypatch.setattr(session, "post", post)

    assert dest.list_id("CS 61A") == "proj-1"
    post.assert_not_called()


def test_list_id_follows_cursor_pagination(dest, monkeypatch):
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json.return_value = {"results": [{"name": "CS 61A", "id": "proj-1"}], "next_cursor": "abc"}
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json.return_value = {"results": [{"name": "EE 16A", "id": "proj-2"}], "next_cursor": None}
    session = dest._get_session()
    get = MagicMock(side_effect=[page1, page2])
    monkeypatch.setattr(session, "get", get)

    assert dest.list_id("EE 16A") == "proj-2"
    assert get.call_count == 2
    _, kwargs = get.call_args_list[1]
    assert kwargs["params"]["cursor"] == "abc"


def test_list_id_creates_project_when_missing(dest, monkeypatch):
    get_resp = MagicMock()
    get_resp.raise_for_status = MagicMock()
    get_resp.json.return_value = {"results": [], "next_cursor": None}
    session = dest._get_session()
    monkeypatch.setattr(session, "get", MagicMock(return_value=get_resp))

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json.return_value = {"id": "new-proj"}
    post = MagicMock(return_value=post_resp)
    monkeypatch.setattr(session, "post", post)

    assert dest.list_id("New Course") == "new-proj"
    _, kwargs = post.call_args
    assert kwargs["json"] == {"name": "New Course"}


def test_insert_posts_task_with_project_id(dest, monkeypatch):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"id": "task-9"}
    session = dest._get_session()
    post = MagicMock(return_value=response)
    monkeypatch.setattr(session, "post", post)

    task_id = dest.insert("proj-1", {"content": "HW"})

    assert task_id == "task-9"
    _, kwargs = post.call_args
    assert kwargs["json"] == {"content": "HW", "project_id": "proj-1"}
    # Auth header is set once on the session, not rebuilt per-call.
    assert session.headers["Authorization"] == "Bearer tok123"


def test_patch_with_normal_body_hits_task_update_endpoint(dest, monkeypatch):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    session = dest._get_session()
    post = MagicMock(return_value=response)
    monkeypatch.setattr(session, "post", post)

    dest.patch("proj-1", "task-9", {"content": "Updated"})

    args, kwargs = post.call_args
    assert args[0].endswith("/tasks/task-9")
    assert kwargs["json"] == {"content": "Updated"}


def test_patch_with_complete_sentinel_hits_close_endpoint_with_no_body(dest, monkeypatch):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    session = dest._get_session()
    post = MagicMock(return_value=response)
    monkeypatch.setattr(session, "post", post)

    dest.patch("proj-1", "task-9", {"_complete": True})

    args, kwargs = post.call_args
    assert args[0].endswith("/tasks/task-9/close")
    assert "json" not in kwargs


def test_patch_swallows_http_errors_for_deleted_tasks(dest, monkeypatch):
    import requests

    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError("404 not found")
    session = dest._get_session()
    monkeypatch.setattr(session, "post", MagicMock(return_value=response))

    dest.patch("proj-1", "task-9", {"content": "Updated"})  # must not raise


def test_session_is_reused_across_calls(dest):
    assert dest._get_session() is dest._get_session()
