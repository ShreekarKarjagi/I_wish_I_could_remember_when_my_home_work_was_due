"""
Pluggable assignment sources.

Each source is a small class with:
  - `name`      a short identifier used in Assignment.source / synced.json keys
  - `enabled()` True if the user has configured this source (env vars present)
  - `fetch(aliases)` returns a list[Assignment]; may raise on network errors,
                      which main() catches and logs per-source

To add a new site: create sources/<site>.py following gradescope.py or
canvas.py as a template, then add an instance to ALL_SOURCES below.
"""

from __future__ import annotations

from .base import Assignment, Source, load_aliases, normalize_course
from .canvas import CanvasSource
from .gradescope import GradescopeSource

# Order here is the order assignments are fetched in.
ALL_SOURCES: list[Source] = [
    GradescopeSource(),
    CanvasSource(),
]

__all__ = ["Assignment", "Source", "load_aliases", "normalize_course", "ALL_SOURCES"]
