"""HTTP sessions that survive brief network trouble."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def make_session(headers: dict | None = None, pool_maxsize: int = 10) -> requests.Session:
    """A Session with a shared connection pool and automatic retries.

    Retries connection errors, 429 and 5xx with exponential backoff (and
    honors Retry-After). POST is only retried when the connection never
    opened, never after the server may have processed it, because repeating
    a POST the server already handled would create a duplicate reminder.
    """
    retry = Retry(
        total=3, connect=3, read=2, status=3, backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "PATCH"}),
        respect_retry_after_header=True,
        raise_on_status=False,  # let raise_for_status() report the final failure
    )
    session = requests.Session()
    if headers:
        session.headers.update(headers)
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=pool_maxsize)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
