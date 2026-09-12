#!/usr/bin/env python3
"""
assignment-sync: pull upcoming assignments from every enabled source
(Gradescope, Canvas, ...) and create reminders for them in the destination
you choose (Google Tasks, Notion), one list/database group per course.

Run:  python sync.py            (normal sync)
      python sync.py --dry-run  (print what would happen, touch nothing)

To add a new site, see sources/__init__.py.
To add a new reminder destination, see destinations/__init__.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from destinations import Destination, get_destination
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
# Where reminders go: "google_tasks" (default) or "notion". See destinations/.
REMINDER_DESTINATION = os.getenv("REMINDER_DESTINATION", "google_tasks")

STATE_FILE = HERE / "synced.json"

log = logging.getLogger("sync")


# ----------------------------------------------------------------------------
# Sync
# ----------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            log.warning("synced.json corrupt; starting fresh")
    return {}


def sync(assignments: Iterable[Assignment], dry_run: bool, destination: Destination | None = None) -> dict:
    """Reconcile `assignments` against synced.json and the reminder destination.

    Returns the added/updated/completed/skipped counts (mainly so tests
    don't have to scrape log output). `destination` lets callers (tests)
    inject a fake in place of a real GoogleTasksDestination/NotionDestination.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=LOOKAHEAD_DAYS)
    state = load_state()
    dest = destination if destination is not None else get_destination(REMINDER_DESTINATION, dry_run=dry_run)
    added = updated = completed = skipped = 0

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
                dest.patch(rec["list_id"], rec["task_id"], dest.completed_body())
                rec["completed"] = True
                completed += 1
                log.info("Completed: %s / %s", a.course, a.title)
            elif a.due and rec.get("due") != a.due.isoformat():
                dest.patch(rec["list_id"], rec["task_id"], dest.task_body(a))
                rec["due"] = a.due.isoformat()
                updated += 1
                log.info("Due date changed: %s / %s", a.course, a.title)
            continue

        if a.submitted or not a.due or a.due < now or a.due > horizon:
            skipped += 1
            continue

        list_id = dest.list_id(a.course)
        task_id = dest.insert(list_id, dest.task_body(a))
        state[a.key] = {"list_id": list_id, "task_id": task_id, "due": a.due.isoformat(),
                        "title": a.title, "course": a.course, "completed": False,
                        "destination": dest.name}
        added += 1
        log.info("Added %s / %s (due %s)", a.course, a.title, a.due.astimezone().strftime("%b %d"))

    if not dry_run:
        STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))
    log.info("Done: %d added, %d updated, %d marked complete, %d skipped",
             added, updated, completed, skipped)
    return {"added": added, "updated": updated, "completed": completed, "skipped": skipped}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    aliases = load_aliases()
    assignments: list[Assignment] = []
    for source in ALL_SOURCES:
        try:
            assignments.extend(source.fetch(aliases))
        except Exception as e:  # noqa: BLE001
            log.error("%s failed: %s", source.name, e)
    if not assignments:
        log.warning("No assignments fetched from any source; check your .env")
        return

    destination = get_destination(REMINDER_DESTINATION, dry_run=args.dry_run)
    log.info("Reminder destination: %s%s", destination.name, " (dry run)" if args.dry_run else "")
    sync(assignments, dry_run=args.dry_run, destination=destination)


if __name__ == "__main__":
    main()
