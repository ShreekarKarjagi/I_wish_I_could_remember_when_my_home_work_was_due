from unittest.mock import MagicMock

import pytest
import requests

from sources.canvas import CanvasSource


def _resp(json_data, next_url=None):
    r = MagicMock()
    r.json.return_value = json_data
    r.links = {"next": {"url": next_url}} if next_url else {}
    r.raise_for_status = MagicMock()
    return r


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("CANVAS_TOKEN", "tok123")
    monkeypatch.setenv("CANVAS_BASE_URL", "https://canvas.example.edu")
    return CanvasSource()


def _patch_session_get(monkeypatch, fake_get):
    """fake_get(self, url, params=None, timeout=None) -- patched on the
    Session class, since CanvasSource now issues requests through a shared
    requests.Session rather than the bare requests.get function (connection
    reuse across the concurrent per-course fetches in fetch())."""
    monkeypatch.setattr(requests.Session, "get", fake_get)


def test_disabled_without_token(monkeypatch):
    monkeypatch.delenv("CANVAS_TOKEN", raising=False)
    src = CanvasSource()
    assert src.enabled() is False
    assert src.fetch({}) == []


def test_enabled_with_token(source):
    assert source.enabled() is True


def test_fetch_maps_assignment_fields(source, monkeypatch):
    courses = [{"id": 1, "course_code": "COMPSCI 61A"}]
    assignments = [
        {
            "id": 100, "name": "HW 1", "due_at": "2026-09-20T07:59:00Z",
            "html_url": "https://canvas.example.edu/courses/1/assignments/100",
            "published": True, "submission": {"workflow_state": "unsubmitted"},
        },
        {
            "id": 101, "name": "HW 2 (graded)", "due_at": "2026-09-21T07:59:00Z",
            "html_url": "https://canvas.example.edu/courses/1/assignments/101",
            "published": True, "submission": {"workflow_state": "graded"},
        },
    ]

    def fake_get(self, url, params=None, timeout=None):
        if "/courses/1/assignments" in url:
            return _resp(assignments)
        return _resp(courses)

    _patch_session_get(monkeypatch, fake_get)

    out = source.fetch({})

    assert len(out) == 2
    hw1, hw2 = out
    assert hw1.source == "canvas"
    assert hw1.source_id == "100"
    assert hw1.course == "CS 61A"
    assert hw1.title == "HW 1"
    assert hw1.submitted is False
    assert hw2.submitted is True  # graded counts as submitted


def test_fetch_skips_unpublished_assignments(source, monkeypatch):
    courses = [{"id": 1, "course_code": "CS 61A"}]
    assignments = [{"id": 1, "name": "Draft", "due_at": None, "published": False}]

    def fake_get(self, url, params=None, timeout=None):
        if "assignments" in url:
            return _resp(assignments)
        return _resp(courses)

    _patch_session_get(monkeypatch, fake_get)
    assert source.fetch({}) == []


def test_fetch_continues_when_one_course_errors(source, monkeypatch):
    courses = [{"id": 1, "course_code": "CS 61A"}, {"id": 2, "course_code": "CS 70"}]
    good_assignments = [{"id": 5, "name": "HW", "due_at": None, "published": True}]

    def fake_get(self, url, params=None, timeout=None):
        if "/courses/1/assignments" in url:
            raise requests.HTTPError("500 server error")
        if "/courses/2/assignments" in url:
            return _resp(good_assignments)
        return _resp(courses)

    _patch_session_get(monkeypatch, fake_get)
    out = source.fetch({})
    assert len(out) == 1
    assert out[0].course == "CS 70"


def test_fetch_runs_course_requests_concurrently(source, monkeypatch):
    # Not a timing assertion (too flaky) -- just confirms every course's
    # assignment list actually gets fetched when there are more courses
    # than fit in one batch of MAX_WORKERS, i.e. the pool drains properly.
    from sources.canvas import MAX_WORKERS

    n_courses = MAX_WORKERS * 2 + 1
    courses = [{"id": i, "course_code": f"CS {i}"} for i in range(n_courses)]

    def fake_get(self, url, params=None, timeout=None):
        for c in courses:
            if f"/courses/{c['id']}/assignments" in url:
                return _resp([{"id": c["id"], "name": "HW", "due_at": None, "published": True}])
        return _resp(courses)

    _patch_session_get(monkeypatch, fake_get)
    out = source.fetch({})
    assert len(out) == n_courses
    assert {a.course for a in out} == {f"CS {i}" for i in range(n_courses)}


def test_get_follows_pagination_links(source, monkeypatch):
    page1 = _resp([{"id": 1}], next_url="https://canvas.example.edu/api/v1/courses?page=2")
    page2 = _resp([{"id": 2}])
    responses = iter([page1, page2])

    def fake_get(self, url, params=None, timeout=None):
        return next(responses)

    _patch_session_get(monkeypatch, fake_get)
    result = source._get("/courses")
    assert [r["id"] for r in result] == [1, 2]


def test_session_is_reused_across_calls(source, monkeypatch):
    seen_sessions = []

    def fake_get(self, url, params=None, timeout=None):
        seen_sessions.append(self)
        return _resp([])

    _patch_session_get(monkeypatch, fake_get)
    source._get("/courses")
    source._get("/courses")
    assert len(seen_sessions) == 2
    assert seen_sessions[0] is seen_sessions[1]


def test_session_sends_bearer_auth_header(source):
    session = source._get_session()
    assert session.headers["Authorization"] == "Bearer tok123"
