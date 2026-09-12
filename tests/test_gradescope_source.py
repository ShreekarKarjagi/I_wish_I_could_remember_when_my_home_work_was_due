import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from sources.gradescope import GradescopeSource


def _fake_gradescopeapi_module(conn_instance):
    """Build a fake `gradescopeapi.classes.connection` module so
    `from gradescopeapi.classes.connection import GSConnection` works
    without the real package touching the network."""
    connection_mod = types.ModuleType("gradescopeapi.classes.connection")
    connection_mod.GSConnection = MagicMock(return_value=conn_instance)
    classes_mod = types.ModuleType("gradescopeapi.classes")
    classes_mod.connection = connection_mod
    top_mod = types.ModuleType("gradescopeapi")
    top_mod.classes = classes_mod
    return top_mod, classes_mod, connection_mod


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("GRADESCOPE_EMAIL", "student@school.edu")
    monkeypatch.setenv("GRADESCOPE_PASSWORD", "hunter2")
    return GradescopeSource()


def _assignment(assignment_id, name, due_date, status, course_id=None):
    a = MagicMock()
    a.assignment_id = assignment_id
    a.name = name
    a.due_date = due_date
    a.submissions_status = status
    return a


def test_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("GRADESCOPE_EMAIL", raising=False)
    monkeypatch.delenv("GRADESCOPE_PASSWORD", raising=False)
    src = GradescopeSource()
    assert src.enabled() is False
    assert src.fetch({}) == []


def test_fetch_maps_courses_and_submission_status(source, monkeypatch):
    course = MagicMock()
    course.name = "CS 61A"
    course.full_name = "CS 61A - Structure and Interpretation"

    conn = MagicMock()
    conn.account.get_courses.return_value = {"student": {"123": course}}
    conn.account.get_assignments.return_value = [
        _assignment("1", "HW1", datetime(2026, 9, 20, tzinfo=timezone.utc), "No Submission"),
        _assignment("2", "HW2", datetime(2026, 9, 21, tzinfo=timezone.utc), "Submitted"),
    ]

    top_mod, classes_mod, connection_mod = _fake_gradescopeapi_module(conn)
    monkeypatch.setitem(sys.modules, "gradescopeapi", top_mod)
    monkeypatch.setitem(sys.modules, "gradescopeapi.classes", classes_mod)
    monkeypatch.setitem(sys.modules, "gradescopeapi.classes.connection", connection_mod)

    out = source.fetch({})

    assert len(out) == 2
    hw1, hw2 = out
    assert hw1.source == "gradescope"
    assert hw1.source_id == "1"
    assert hw1.course == "CS 61A"
    assert hw1.submitted is False
    assert hw1.url == "https://www.gradescope.com/courses/123/assignments/1"
    assert hw2.submitted is True
    conn.login.assert_called_once_with("student@school.edu", "hunter2")


def test_fetch_continues_when_one_course_errors(source, monkeypatch):
    good_course = MagicMock(name="good_course")
    good_course.name = "CS 70"
    good_course.full_name = "CS 70"
    bad_course = MagicMock(name="bad_course")
    bad_course.name = "CS 61A"
    bad_course.full_name = "CS 61A"

    conn = MagicMock()
    conn.account.get_courses.return_value = {"student": {"1": bad_course, "2": good_course}}

    def get_assignments(course_id):
        if course_id == "1":
            raise RuntimeError("network blip")
        return [_assignment("9", "HW", None, "No Submission")]

    conn.account.get_assignments.side_effect = get_assignments

    top_mod, classes_mod, connection_mod = _fake_gradescopeapi_module(conn)
    monkeypatch.setitem(sys.modules, "gradescopeapi", top_mod)
    monkeypatch.setitem(sys.modules, "gradescopeapi.classes", classes_mod)
    monkeypatch.setitem(sys.modules, "gradescopeapi.classes.connection", connection_mod)

    out = source.fetch({})
    assert len(out) == 1
    assert out[0].course == "CS 70"


def test_fetch_treats_no_submission_substring_as_unsubmitted(source, monkeypatch):
    # "Late Submission (no submission graded)"-style strings shouldn't count as submitted.
    course = MagicMock()
    course.name = "CS 61A"
    course.full_name = "CS 61A"
    conn = MagicMock()
    conn.account.get_courses.return_value = {"student": {"1": course}}
    conn.account.get_assignments.return_value = [
        _assignment("1", "HW1", None, "Submitted (no submission received)"),
    ]

    top_mod, classes_mod, connection_mod = _fake_gradescopeapi_module(conn)
    monkeypatch.setitem(sys.modules, "gradescopeapi", top_mod)
    monkeypatch.setitem(sys.modules, "gradescopeapi.classes", classes_mod)
    monkeypatch.setitem(sys.modules, "gradescopeapi.classes.connection", connection_mod)

    out = source.fetch({})
    assert out[0].submitted is False
