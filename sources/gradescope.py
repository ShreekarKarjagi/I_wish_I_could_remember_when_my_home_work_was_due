"""Gradescope has no public API; we log in with email + password."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

from .base import Assignment, aware, normalize_course

log = logging.getLogger("sync")

# Courses are fetched concurrently -- a student's own course list is small
# enough that this is a courtesy limit, not a real throttle.
MAX_WORKERS = 6


class GradescopeSource:
    name = "gradescope"

    # Read fresh from the environment on every access (not cached in __init__)
    # so it doesn't matter whether load_dotenv() ran before or after this
    # object was constructed -- ALL_SOURCES is built once at import time in
    # sources/__init__.py, which may happen before sync.py loads .env.
    @property
    def email(self) -> str:
        return os.getenv("GRADESCOPE_EMAIL", "")

    @property
    def password(self) -> str:
        return os.getenv("GRADESCOPE_PASSWORD", "")

    def enabled(self) -> bool:
        return bool(self.email and self.password)

    @staticmethod
    def _fetch_course(conn, course_id: str, course, aliases: dict[str, str]) -> list[Assignment]:
        label = normalize_course(course.name or course.full_name, aliases)
        try:
            items = conn.account.get_assignments(course_id)
        except Exception as e:  # noqa: BLE001
            log.warning("Gradescope: could not read course %s (%s): %s", label, course_id, e)
            return []
        out: list[Assignment] = []
        for it in items:
            status = (it.submissions_status or "").lower()
            out.append(Assignment(
                source="gradescope",
                source_id=str(it.assignment_id),
                course=label,
                title=it.name.strip(),
                due=aware(it.due_date),
                url=f"https://www.gradescope.com/courses/{course_id}/assignments/{it.assignment_id}",
                submitted="submitted" in status and "no submission" not in status,
            ))
        return out

    def fetch(self, aliases: dict[str, str]) -> list[Assignment]:
        if not self.enabled():
            log.info("Gradescope credentials not set; skipping Gradescope")
            return []

        from gradescopeapi.classes.connection import GSConnection

        conn = GSConnection()
        conn.login(self.email, self.password)
        courses = conn.account.get_courses().get("student", {})

        out: list[Assignment] = []
        if courses:
            # GSConnection holds one persistent, shared requests.Session, so
            # these concurrent calls reuse connections rather than opening a
            # new one per course -- same as Canvas, just via the library.
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(courses))) as pool:
                futures = [
                    pool.submit(self._fetch_course, conn, course_id, course, aliases)
                    for course_id, course in courses.items()
                ]
                for future in futures:
                    out.extend(future.result())
        log.info("Gradescope: %d assignments across %d courses", len(out), len(courses))
        return out
