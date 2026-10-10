#!/usr/bin/env python3
"""
assignment-sync: pull upcoming assignments from every enabled source
(Gradescope, Canvas, ...) and create reminders for them in the destination
you choose (Google Tasks, Notion, Todoist), one list/project group per course.

Run:  python sync.py            (normal sync)
      python sync.py --dry-run  (print what would happen, touch nothing)

To add a new site, see sources/__init__.py.
To add a new reminder destination, see destinations/__init__.py.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from destinations import Destination, get_destination
from reliability.lock import FileLock, LockBusy
from reliability.notify import notify
from reliability.state import StateCorruptError, load_state as _load_state, save_state as _save_state
from reliability.status import record_result
from sources import ALL_SOURCES, Assignment, load_aliases

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

# Only create reminders for assignments due within this many days.
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "21"))
# Put the reminder this many days BEFORE the due date (0 = on the due date).
REMIND_DAYS_BEFORE = int(os.getenv("REMIND_DAYS_BEFORE", "0"))
# Where reminders go: "google_tasks" (default), "notion" or "todoist". See destinations/.
REMINDER_DESTINATION = os.getenv("REMINDER_DESTINATION", "google_tasks")
# A run still going after this long is stuck (e.g. a site never answers).
# Give up so it can't block every later scheduled run behind it.
RUN_TIMEOUT_SECONDS = int(os.getenv("SYNC_TIMEOUT_SECONDS", "600"))

STATE_FILE = HERE / "synced.json"
STATUS_FILE = HERE / "status.json"
LOCK_FILE = HERE / "sync.lock"

log = logging.getLogger("sync")


# ----------------------------------------------------------------------------
# Sync
# ----------------------------------------------------------------------------

def load_state() -> dict:
    return _load_state(STATE_FILE)


def sync(assignments: Iterable[Assignment], dry_run: bool, destination: Destination | None = None) -> dict:
    """Reconcile `assignments` against synced.json and the reminder destination.

    Returns the added/updated/completed/skipped/failed counts (mainly so tests
    don't have to scrape log output). `destination` lets callers (tests)
    inject a fake in place of a real GoogleTasksDestination/NotionDestination.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=LOOKAHEAD_DAYS)
    state = load_state()
    dest = destination if destination is not None else get_destination(REMINDER_DESTINATION, dry_run=dry_run)
    added = updated = completed = skipped = failed = 0

    def persist() -> None:
        # Saved after every change, not once at the end: if the run dies
        # halfway (network, crash, timeout), reminders already created must
        # be remembered or the next run would create them a second time.
        if not dry_run:
            _save_state(STATE_FILE, state)

    for a in assignments:
        rec = state.get(a.key)

        # A record from a *different* destination than the one active now
        # (the user switched REMINDER_DESTINATION) is stale: its list_id/
        # task_id belong to the other service and patching them would just
        # fail. Treat it as untracked so it gets recreated under the new
        # destination. Records written before this field existed are
        # implicitly "google_tasks" -- the only destination that ever existed.
        if rec and rec.get("destination", "google_tasks") != dest.name:
            rec = None

        if rec:  # already tracked: keep the reminder in sync
            if a.submitted and not rec.get("completed"):
                if dest.patch(rec["list_id"], rec["task_id"], dest.completed_body()) is False:
                    failed += 1  # leave the record alone so the next run retries
                    continue
                rec["completed"] = True
                persist()
                completed += 1
                log.info("Completed: %s / %s", a.course, a.title)
            elif a.due and rec.get("due") != a.due.isoformat():
                if dest.patch(rec["list_id"], rec["task_id"], dest.task_body(a)) is False:
                    failed += 1
                    continue
                rec["due"] = a.due.isoformat()
                persist()
                updated += 1
                log.info("Due date changed: %s / %s", a.course, a.title)
            continue

        if a.submitted or not a.due or a.due < now or a.due > horizon:
            skipped += 1
            continue

        try:
            list_id = dest.list_id(a.course)
            task_id = dest.insert(list_id, dest.task_body(a))
        except Exception as e:  # noqa: BLE001  one bad reminder must not block the rest
            log.error("Could not add %s / %s: %s", a.course, a.title, e)
            failed += 1
            continue
        state[a.key] = {"list_id": list_id, "task_id": task_id, "due": a.due.isoformat(),
                        "title": a.title, "course": a.course, "completed": False,
                        "destination": dest.name}
        persist()
        added += 1
        log.info("Added %s / %s (due %s)", a.course, a.title, a.due.astimezone().strftime("%b %d"))

    log.info("Done: %d added, %d updated, %d marked complete, %d skipped, %d failed",
             added, updated, completed, skipped, failed)
    return {"added": added, "updated": updated, "completed": completed,
            "skipped": skipped, "failed": failed}


# ----------------------------------------------------------------------------
# Running it
# ----------------------------------------------------------------------------

@dataclass
class RunOutcome:
    ok: bool
    error: str | None = None
    needs_action: bool = False  # the user has to do something (e.g. sign in again)


def run(destination: Destination, dry_run: bool) -> RunOutcome:
    aliases = load_aliases()
    assignments: list[Assignment] = []
    problems: list[str] = []
    # Sources don't depend on each other, so fetch them all at once instead
    # of waiting for Gradescope to finish before even starting Canvas.
    with ThreadPoolExecutor(max_workers=len(ALL_SOURCES)) as pool:
        futures = {pool.submit(source.fetch, aliases): source for source in ALL_SOURCES}
        for future, source in futures.items():
            try:
                assignments.extend(future.result())
            except Exception as e:  # noqa: BLE001
                log.error("%s failed: %s", source.name, e)
                problems.append(f"{source.name} failed: {e}")

    if not assignments:
        if problems:
            return RunOutcome(False, "; ".join(problems))
        log.warning("No assignments fetched from any source; check your .env")
        return RunOutcome(True)

    try:
        counts = sync(assignments, dry_run=dry_run, destination=destination)
    except StateCorruptError as e:
        log.error("%s", e)
        return RunOutcome(False, str(e), needs_action=True)
    if counts["failed"]:
        problems.append(f"{counts['failed']} reminder(s) could not be added or updated")
    return RunOutcome(not problems, "; ".join(problems) or None)


def _start_watchdog(seconds: int) -> threading.Timer:
    def give_up() -> None:
        log.error("Sync still running after %ds; giving up so it can't block later runs.", seconds)
        try:
            record_result(STATUS_FILE, ok=False, error=f"timed out after {seconds}s")
        finally:
            logging.shutdown()
            os._exit(3)  # state is saved after every change, so this loses nothing

    timer = threading.Timer(seconds, give_up)
    timer.daemon = True
    timer.start()
    return timer


def execute(dry_run: bool) -> RunOutcome:
    # Set up the destination first: if its login is dead (e.g. an expired
    # Google token) we want to know right away, not after a slow fetch.
    try:
        destination = get_destination(REMINDER_DESTINATION, dry_run=dry_run)
    except SystemExit as e:
        msg = e.code if isinstance(e.code, str) else "Reminder destination setup failed"
        log.error("%s", msg)
        return RunOutcome(False, msg, needs_action=True)
    log.info("Reminder destination: %s%s", destination.name, " (dry run)" if dry_run else "")

    # Armed only after destination setup, which may wait on a person
    # clicking "Allow" in a browser.
    watchdog = None if dry_run else _start_watchdog(RUN_TIMEOUT_SECONDS)
    try:
        return run(destination, dry_run)
    except Exception as e:  # noqa: BLE001
        log.exception("Unexpected error")
        return RunOutcome(False, f"Unexpected error: {e}")
    finally:
        if watchdog:
            watchdog.cancel()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    if args.dry_run:  # writes nothing, so no lock, status, or notification
        sys.exit(0 if execute(dry_run=True).ok else 1)

    lock = FileLock(LOCK_FILE)
    try:
        lock.acquire()
    except LockBusy:
        log.info("Another sync is already running; skipping this run.")
        return
    try:
        outcome = execute(dry_run=False)
    finally:
        lock.release()

    try:
        if record_result(STATUS_FILE, ok=outcome.ok, error=outcome.error,
                         needs_action=outcome.needs_action):
            notify("Assignment sync needs attention",
                   (outcome.error or "The last sync failed. See sync.log.")[:240])
    except Exception as e:  # noqa: BLE001  bookkeeping must never mask the real result
        log.warning("Could not record run status: %s", e)
    sys.exit(0 if outcome.ok else 1)


if __name__ == "__main__":
    main()
