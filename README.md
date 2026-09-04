# assignment-sync

Turns your **Gradescope** and **Canvas** deadlines into **Google Tasks** reminders automatically.

Every run pulls each upcoming, unsubmitted assignment from both sites and creates a reminder for it in Google Tasks — one task list per course, dated on the due date (or a few days before, if you prefer). Re-running is safe: it remembers what it already added, moves reminders whose due dates change, and ticks them off once you've submitted. Set it up once, schedule it, and your phone's Google Tasks widget always shows what's due.

Works with any school's Canvas instance (bCourses, Canvas LMS, etc.) — set the URL in `.env`.

```
EECS 126
  ☐ Lab 1                                   Sep 9
      Due: Wed Sep 09, 11:59 PM
      https://www.gradescope.com/courses/.../assignments/...
  ☐ Homework 1 - Self Grade                 Sep 10
```

## Setup (~10 minutes, once)

Requires Python 3.10+.

### 1. Install

```bash
git clone https://github.com/ShreekarKarjagi/I_wish_I_could_remember_when_my_home_work_was_due.git assignment-sync
cd assignment-sync
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

### 2. Gradescope

Gradescope has no API, so the script logs in with your email and password (stored only in your local `.env`). If you normally sign in through your school's SSO and have never set a Gradescope password, go to https://www.gradescope.com/reset_password, enter your school email, and set one — SSO keeps working alongside it. Put both in `.env`.

### 3. Canvas token

In Canvas: **Account → Settings → Approved Integrations → + New Access Token**. Name it anything, leave expiry blank, copy the token into `CANVAS_TOKEN` in `.env`, and set `CANVAS_BASE_URL` to your school's Canvas address (e.g. `https://bcourses.berkeley.edu` or `https://canvas.instructure.com`).

Make sure the token is on the **same line** as `CANVAS_TOKEN=` — a stray line break makes the script think it's empty.

### 4. Google Tasks credentials

1. **Create a project.** Go to https://console.cloud.google.com, sign in with a Google account (it doesn't have to be the one whose Tasks you'll use — see step 4). Click the project dropdown at the top → **New Project** → name it `assignment-sync` → Location/Parent: **No organization** → **Create**. Make sure it's selected afterwards.
2. **Enable the API.** Left menu → **APIs & Services → Library** → search "Google Tasks API" → **Enable**.
3. **Consent screen.** **APIs & Services → OAuth consent screen** (newer consoles redirect to **Google Auth Platform** → "Get started"). App name `assignment-sync`, support email = yours, Audience = **External**, contact email = yours → **Create**.
4. **Add yourself as a test user.** Google Auth Platform → **Audience** → **+ Add users** → enter the email of the Google account whose Tasks you want to use (this can be a school account) → **Save**. Without this you'll get `Error 403: access_denied` at login.
5. **Create the OAuth client.** **APIs & Services → Credentials** (or Google Auth Platform → **Clients**) → **+ Create Credentials → OAuth client ID** → Application type **Desktop app** → **Create** → **Download JSON**.
6. **Place the file.** Rename the download (`client_secret_…json`) to exactly `credentials.json` and put it in this folder.
7. **Authorize once.** Run `python sync.py`. A browser tab opens: pick the account you added in step 4, click **Continue** past the "Google hasn't verified this app" warning (it's your own app), then **Allow**. A `token.json` is saved and reused silently from then on.

**Avoid weekly re-login:** while the app is in *Testing* status, tokens expire after 7 days. Once it works, go to Google Auth Platform → **Audience** → **Publish app** → Confirm. Ignore the verification notice — an unverified published app still works for personal use and its tokens don't expire.

### 5. Run it

```bash
python sync.py --dry-run   # shows what it would add, changes nothing
python sync.py             # does it for real
```

## Scheduling

### Windows (Task Scheduler)

`run_sync.bat` uses the project's `.venv` and appends output to `sync.log`. In PowerShell (edit the path):

```powershell
schtasks /Create /TN "AssignmentSync" /SC DAILY /ST 07:00 /TR "C:\path\to\assignment-sync\run_sync.bat" /F
```

Test it immediately with `schtasks /Run /TN "AssignmentSync"`, then check `sync.log`. Every 6 hours instead: `/SC HOURLY /MO 6`. Remove with `schtasks /Delete /TN "AssignmentSync" /F`. If it should run while you're logged out, open Task Scheduler → the task → Properties → *Run whether user is logged on or not*.

### macOS / Linux (cron)

```bash
chmod +x run_sync.sh
crontab -e
# add: run daily at 7:00
0 7 * * * /path/to/assignment-sync/run_sync.sh
```

## Options (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `LOOKAHEAD_DAYS` | 21 | Only create reminders for assignments due within this many days |
| `REMIND_DAYS_BEFORE` | 0 | Date the reminder this many days before the due date (the real deadline is always in the task notes) |
| `CANVAS_BASE_URL` | `https://bcourses.berkeley.edu` | Your school's Canvas address |

## Course names

Gradescope shows "CS 61A"; Canvas often shows "2026-FA-COMPSCI-61A-001". The script normalizes both to `CS 61A` so they share one list. If something lands in the wrong list, add a mapping to `course_aliases.json` (raw name → list name) and re-run. The department abbreviations in `DEPT_ALIASES` at the top of `sync.py` are Berkeley-flavored; edit them for your school.

## Files it creates (all git-ignored)

- `token.json` — your Google login; delete it to re-authorize.
- `synced.json` — memory of what has been added. Delete it to re-add everything (you'll get duplicates in Google Tasks unless you clear those too).
- `sync.log` — output from scheduled runs.

## Privacy

Everything runs on your own machine. Your Gradescope password and Canvas token live only in your local `.env`; nothing is sent anywhere except to Gradescope, Canvas, and Google's Tasks API. Never commit `.env`, `credentials.json`, or `token.json` — the included `.gitignore` already excludes them.

## License

MIT — see [LICENSE](LICENSE).
