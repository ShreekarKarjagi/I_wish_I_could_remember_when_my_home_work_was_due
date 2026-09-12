from unittest.mock import MagicMock

import pytest

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

    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(url)
        if "/courses/1/assignments" in url:
            return _resp(assignments)
        return _resp(courses)

    monkeypatch.setattr("sources.canvas.requests.get", fake_get)

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

    def fake_get(url, headers, params, timeout):
        if "assignments" in url:
            return _resp(assignments)
        return _resp(courses)

    monkeypatch.setattr("sources.canvas.requests.get", fake_get)
    assert source.fetch({}) == []


def test_fetch_continues_when_one_course_errors(source, monkeypatch):
    import requests

    courses = [{"id": 1, "course_code": "CS 61A"}, {"id": 2, "course_code": "CS 70"}]
    good_assignments = [{"id": 5, "name": "HW", "due_at": None, "published": True}]

    def fake_get(url, headers, params, timeout):
        if "/courses/1/assignments" in url:
            raise requests.HTTPError("500 server error")
        if "/courses/2/assignments" in url:
            return _resp(good_assignments)
        return _resp(courses)

    monkeypatch.setattr("sources.canvas.requests.get", fake_get)
    out = source.fetch({})
    assert len(out) == 1
    assert out[0].course == "CS 70"


def test_get_follows_pagination_links(source, monkeypatch):
    page1 = _resp([{"id": 1}], next_url="https://canvas.example.edu/api/v1/courses?page=2")
    page2 = _resp([{"id": 2}])
    responses = iter([page1, page2])

    def fake_get(url, headers, params, timeout):
        return next(responses)

    monkeypatch.setattr("sources.canvas.requests.get", fake_get)
    result = source._get("/courses")
    assert [r["id"] for r in result] == [1, 2]
