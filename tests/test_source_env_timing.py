"""Regression test: ALL_SOURCES is built once at import time in
sources/__init__.py, but sync.py calls load_dotenv() *after* importing
sources. Sources must read env vars lazily (at enabled()/fetch() time),
never cache them at construction time, or .env values set after import
(the normal case) are silently ignored."""

from sources.canvas import CanvasSource
from sources.gradescope import GradescopeSource


def test_canvas_source_picks_up_token_set_after_construction(monkeypatch):
    monkeypatch.delenv("CANVAS_TOKEN", raising=False)
    src = CanvasSource()  # constructed before the token exists, like ALL_SOURCES is
    assert src.enabled() is False

    monkeypatch.setenv("CANVAS_TOKEN", "tok-set-later")  # simulates load_dotenv() running later
    assert src.enabled() is True


def test_gradescope_source_picks_up_credentials_set_after_construction(monkeypatch):
    monkeypatch.delenv("GRADESCOPE_EMAIL", raising=False)
    monkeypatch.delenv("GRADESCOPE_PASSWORD", raising=False)
    src = GradescopeSource()
    assert src.enabled() is False

    monkeypatch.setenv("GRADESCOPE_EMAIL", "a@b.edu")
    monkeypatch.setenv("GRADESCOPE_PASSWORD", "pw")
    assert src.enabled() is True
