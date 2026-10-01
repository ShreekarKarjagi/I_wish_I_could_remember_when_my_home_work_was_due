"""Canvas (bCourses etc.) — REST API with a personal access token."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter

from .base import Assignment, normalize_course, parse_iso

log = logging.getLogger("sync")

# Courses are fetched concurrently -- a student's own course list is small
# enough that this is a courtesy limit, not a real throttle.
MAX_WORKERS = 6


class CanvasSource:
    name = "canvas"

    def __init__(self) -> None:
        self._session: requests.Session | None = None

    # Read fresh from the environment on every access (not cached in __init__)
    # -- see the comment in sources/gradescope.py for why.
    @property
    def base_url(self) -> str:
        return os.getenv("CANVAS_BASE_URL", "https://bcourses.berkeley.edu").rstrip("/")

    @property
    def token(self) -> str:
        return os.getenv("CANVAS_TOKEN", "")

    def enabled(self) -> bool:
        return bool(self.token)

    def _get_session(self) -> requests.Session:
        # One persistent connection pool for every request this source makes,
        # instead of a fresh TCP+TLS handshake per call -- matters a lot once
        # fetch() is firing several of these concurrently (see MAX_WORKERS).
        if self._session is None:
            session = requests.Session()
            session.headers["Authorization"] = f"Bearer {self.token}"
            session.mount("https://", HTTPAdapter(pool_maxsize=MAX_WORKERS))
            self._session = session
        return self._session

    def _get(self, path: str, **params) -> list[dict]:
        url = f"{self.base_url}/api/v1{path}"
        params.setdefault("per_page", 100)
        session = self._get_session()
        results: list[dict] = []
        while url:
            r = session.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            results.extend(data if isinstance(data, list) else [data])
            url = r.links.get("next", {}).get("url")
            params = {}
        return results

    def _fetch_course(self, course: dict, aliases: dict[str, str]) -> list[Assignment]:
        label = normalize_course(course.get("course_code") or course.get("name") or str(course["id"]), aliases)
        try:
            items = self._get(f"/courses/{course['id']}/assignments",
                               **{"include[]": "submission", "order_by": "due_at"})
        except requests.HTTPError as e:
            log.warning("bCourses: could not read %s: %s", label, e)
            return []
        out: list[Assignment] = []
        for it in items:
            if not it.get("published", True):
                continue
            state = (it.get("submission") or {}).get("workflow_state", "unsubmitted")
            out.append(Assignment(
                source=self.name,
                source_id=str(it["id"]),
                course=label,
                title=(it.get("name") or "").strip(),
                due=parse_iso(it.get("due_at")),
                url=it.get("html_url", ""),
                submitted=state in ("submitted", "graded", "pending_review"),
            ))
        return out

    def fetch(self, aliases: dict[str, str]) -> list[Assignment]:
        if not self.enabled():
            log.info("CANVAS_TOKEN not set; skipping bCourses")
            return []

        courses = self._get("/courses", enrollment_state="active", enrollment_type="student")

        out: list[Assignment] = []
        if courses:
            # One course's assignment list doesn't depend on another's, so
            # fetch them concurrently instead of waiting on each in turn.
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(courses))) as pool:
                for result in pool.map(lambda c: self._fetch_course(c, aliases), courses):
                    out.extend(result)
        log.info("bCourses: %d assignments across %d courses", len(out), len(courses))
        return out
