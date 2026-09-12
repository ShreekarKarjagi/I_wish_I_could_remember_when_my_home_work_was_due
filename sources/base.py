"""Shared model + course-name normalization used by every source."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

log = logging.getLogger("sync")

HERE = Path(__file__).resolve().parent.parent
ALIASES_FILE = HERE / "course_aliases.json"


@dataclass
class Assignment:
    source: str            # "gradescope" | "canvas" | ...
    source_id: str
    course: str             # normalized course label, e.g. "CS 61A"
    title: str
    due: datetime | None    # timezone-aware
    url: str = ""
    submitted: bool = False

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


class Source(Protocol):
    """A pluggable assignment feed (Gradescope, Canvas, ...)."""

    name: str

    def enabled(self) -> bool:
        """True if this source is configured (its env vars are set)."""
        ...

    def fetch(self, aliases: dict[str, str]) -> list[Assignment]:
        """Return every assignment currently visible for this source."""
        ...


# ----------------------------------------------------------------------------
# Course-name normalization (shared across sources so lists merge correctly)
# ----------------------------------------------------------------------------

DEPT_ALIASES = {
    "COMPSCI": "CS", "ELENG": "EE", "MATH": "Math", "PHYSICS": "Physics",
    "DATA": "Data", "STAT": "Stat", "ENGIN": "Engin",
}
_COURSE_RE = re.compile(r"\b([A-Z]{2,8})\s*[- ]?\s*([A-Z]?\d{1,3}[A-Z]{0,2})\b", re.IGNORECASE)


def load_aliases() -> dict[str, str]:
    if ALIASES_FILE.exists():
        try:
            return json.loads(ALIASES_FILE.read_text())
        except json.JSONDecodeError:
            log.warning("course_aliases.json is not valid JSON; ignoring it")
    return {}


def normalize_course(raw: str, aliases: dict[str, str]) -> str:
    """Turn 'Fall 2026 COMPSCI 61A 001' or 'CS 61A' into 'CS 61A'."""
    if raw in aliases:
        return aliases[raw]
    m = _COURSE_RE.search(raw)
    if not m:
        return raw.strip()
    dept, num = m.group(1).upper(), m.group(2).upper()
    label = f"{DEPT_ALIASES.get(dept, dept)} {num}"
    return aliases.get(label, label)


# ----------------------------------------------------------------------------
# Small parsing helpers shared by sources
# ----------------------------------------------------------------------------

def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
