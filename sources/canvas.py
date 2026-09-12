"""Canvas (bCourses etc.) — REST API with a personal access token."""

from __future__ import annotations

import logging
import os

import requests

from .base import Assignment, normalize_course, parse_iso

log = logging.getLogger("sync")


class CanvasSource:
    name = "canvas"

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

    def _get(self, path: str, **params) -> list[dict]:
        url = f"{self.base_url}/api/v1{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        params.setdefault("per_page", 100)
        results: list[dict] = []
        while url:
            r = requests.get(url, headers=headers, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            results.extend(data if isinstance(data, list) else [data])
            url = r.links.get("next", {}).get("url")
            params = {}
        return results

    def fetch(self, aliases: dict[str, str]) -> list[Assignment]:
        if not self.enabled():
            log.info("CANVAS_TOKEN not set; skipping bCourses")
            return []

        courses = self._get("/courses", enrollment_state="active", enrollment_type="student")
        out: list[Assignment] = []
        for c in courses:
            label = normalize_course(c.get("course_code") or c.get("name") or str(c["id"]), aliases)
            try:
                items = self._get(f"/courses/{c['id']}/assignments",
                                   **{"include[]": "submission", "order_by": "due_at"})
            except requests.HTTPError as e:
                log.warning("bCourses: could not read %s: %s", label, e)
                continue
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
        log.info("bCourses: %d assignments across %d courses", len(out), len(courses))
        return out
