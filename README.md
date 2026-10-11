# I Wish I Could Remember When My Homework Was Due

A script that checks Gradescope and Canvas for upcoming assignments and turns them into reminders — in Todoist or Notion, whichever you use — so you don't have to open either site to know what's due.

It logs into Gradescope with your email/password (there's no API), talks to Canvas over its REST API with a personal token, and writes reminders to Todoist or Notion depending on how you configure it.

## What it does

- Pulls every unsubmitted assignment from Gradescope and Canvas
- Creates a reminder for each one with the due date and a link to the assignment, grouped by course
- Safe to run repeatedly — it won't create duplicates
- Moves the reminder if a due date changes, and checks it off once you submit
- Works with any Canvas school, not just Berkeley's bCourses

Example of what shows up:

```
EECS 126
  ☐ Lab 1                          Sep 9
  ☐ Homework 1 - Self Grade        Sep 10
EE 66
  ☐ HW1                            Sep 4
  ☐ Lecture 1B Mini-Vitamin        Sep 5
```

Everything runs locally. There's no server and nothing gets collected — the only network calls are to Gradescope, Canvas, and whichever reminder destination you pick.

## Setup
Setup takes ~5 mins if you're using Todoist and ~15 if you're using Notion. If you get stuck at any point in time, just copy and paste this README into an LLM and let it guide you
You need Python 3.10+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/ShreekarKarjagi/I_wish_I_could_remember_when_my_home_work_was_due.git assignment-sync
cd assignment-sync
uv sync
cp .env.example .env        # Windows: copy .env.example .env
```

`uv sync` creates a virtualenv and installs everything from the lockfile. Everything else you configure goes in `.env`, which stays on your machine and is never committed.

**Gradescope** — put `GRADESCOPE_EMAIL` and `GRADESCOPE_PASSWORD` in `.env`. If you've only ever logged in through SSO, set a password first at gradescope.com/reset_password — SSO keeps working alongside it.

**Canvas** — go to Account → Settings → Approved Integrations → New Access Token, and copy it into `CANVAS_TOKEN`. Set `CANVAS_BASE_URL` to your school's Canvas address (defaults to Berkeley's bCourses). Watch out for the token wrapping onto a second line in `.env` — if it does, the script silently skips Canvas.

### Where reminders go

Set `REMINDER_DESTINATION` to `todoist` (the default) or `notion`.

**Todoist** is the default and the quickest to set up:

1. Set `REMINDER_DESTINATION=todoist` in `.env`.
2. Grab a personal token from Todoist → Settings → Integrations → Developer, and copy it into `TODOIST_TOKEN`.

That's it. It creates one Todoist project per course automatically.

**Notion** takes a few minutes to set up:

1. Set `REMINDER_DESTINATION=notion` in `.env`.
2. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations) and copy its secret into `NOTION_TOKEN`.
3. Create (or reuse) a database with these properties — the type matters, not just the name: a title property renamed to `Name`, a `Course` select, a `Due` date, a `URL` url property, and a `Done` checkbox.
4. Open the database, click the `···` menu → Connect to, and pick your integration — otherwise it can't see the database.
5. Copy the database id into `NOTION_DATABASE_ID` (the 32-character id in the database's URL, before any `?v=`).

Every course lands in the same database and is told apart by its `Course` property, rather than a separate database per course.

You can switch destinations later without losing anything — reminders already created under the old one are left alone, and everything still due gets recreated under the new one.

### Run it

```bash
uv run sync.py --dry-run   # see what it would do, without changing anything
uv run sync.py             # the real thing
```

## Running it automatically

**Windows (Task Scheduler)** — `run_sync.bat` runs the script and logs to `sync.log`:

```powershell
schtasks /Create /TN "AssignmentSync" /SC DAILY /ST 07:00 /TR "C:\path\to\assignment-sync\run_sync.bat" /F
```

Test it with `schtasks /Run /TN "AssignmentSync"` and check `sync.log`. Remove it with `schtasks /Delete /TN "AssignmentSync" /F`.

**macOS/Linux (cron)**:

```bash
chmod +x run_sync.sh
crontab -e
# 0 7 * * * /path/to/assignment-sync/run_sync.sh
```

## Options

All set in `.env`:

| Variable | Default | What it does |
|---|---|---|
| `REMINDER_DESTINATION` | `todoist` | `todoist` or `notion` |
| `LOOKAHEAD_DAYS` | `21` | Only remind for assignments due within this many days |
| `REMIND_DAYS_BEFORE` | `0` | Set the reminder this many days before the actual due date |
| `CANVAS_BASE_URL` | `https://bcourses.berkeley.edu` | Your school's Canvas address |
| `SYNC_TIMEOUT_SECONDS` | `600` | A run still going after this long is stuck; it gives up so it can't block the next scheduled run |

**Course names.** Gradescope calls a class `CS 61A`; Canvas calls it `2026-FA-COMPSCI-61A-001`. The script normalizes both to the same label so they land in one group. If something ends up in the wrong place, add a mapping in `course_aliases.json`. If your school uses different department abbreviations, edit `DEPT_ALIASES` in `sources/base.py`.

## Files it creates

| File | Purpose |
|---|---|
| `synced.json` | Tracks what's already been added, so it isn't duplicated — delete it to start over (clear your reminders too, or you'll get duplicates). `synced.json.bak` is a mirror copy it restores from if the main file ever gets damaged |
| `sync.log` | Output from scheduled runs (rolls over to `sync.log.1` past ~1 MB) |
| `status.json` | When it last succeeded, and how many runs in a row have failed |
| `sync.lock` | Stops two syncs from running at once |

None of these are committed to git, along with `.env`.

### When something goes wrong

Failed runs exit non-zero (Task Scheduler's "Last Result" shows it) and `status.json` records why. If it needs you to do something — like a destination token that isn't set up — or fails twice in a row, you get a desktop notification (at most one a day). One flaky network moment won't ping you.

## Privacy

Nothing leaves your computer except requests to Gradescope, Canvas, and whichever destination you configured. Full policy in [PRIVACY.md](PRIVACY.md).

## License

MIT — see [LICENSE](LICENSE).
