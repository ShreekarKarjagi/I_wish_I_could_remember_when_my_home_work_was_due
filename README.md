# 📚 I Wish I Could Remember When My Homework Was Due

A Python script that **pulls your Gradescope and Canvas deadlines and turns them into Google Tasks reminders** — automatically, every day, without you ever opening either site.

Built with **gradescopeapi** for Gradescope, the **Canvas REST API** for bCourses, and the **Google Tasks API** for reminders.

---

## ✨ Features

- 🔍 Checks **Gradescope** and **Canvas** for every unsubmitted assignment due soon
- ✅ Creates a Google Tasks reminder for each one, with:
  - The exact deadline
  - A link straight to the assignment
- 🗂️ One Google Tasks list per course (e.g. `CS 61A`, `EECS 126`)
- 🔁 Safe to re-run — never creates duplicates
- 📆 Moves the reminder if a due date changes
- ☑️ Checks the task off automatically once you've submitted
- 🐻 Built for Berkeley's bCourses, but works with **any school that uses Canvas**
- 🔒 Runs entirely on your own computer — no server, no accounts, nothing collected

What it looks like in Google Tasks:

```
EECS 126
  ☐ Lab 1                          Sep 9
  ☐ Homework 1 - Self Grade        Sep 10
EE 66
  ☐ HW1                            Sep 4
  ☐ Lecture 1B Mini-Vitamin        Sep 5
```

---

## 🚀 Setup

Takes about three minutes. You'll need **Python 3.10+**.

### 1️⃣ Install

```bash
git clone https://github.com/ShreekarKarjagi/I_wish_I_could_remember_when_my_home_work_was_due.git assignment-sync
cd assignment-sync
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Everything you set up goes in `.env`. It's git-ignored, so it stays on your computer. 🔒

### 2️⃣ Gradescope

Gradescope has no API, so the script logs in with your email and password.

- Put `GRADESCOPE_EMAIL` and `GRADESCOPE_PASSWORD` in `.env`
- 💡 Only ever used SSO? Set a password at https://www.gradescope.com/reset_password — SSO keeps working alongside it

### 3️⃣ Canvas

- In Canvas: **Account → Settings → Approved Integrations → + New Access Token**
- Name it anything, leave expiry blank, copy the token into `CANVAS_TOKEN` in `.env`
- Set `CANVAS_BASE_URL` to your school's Canvas address (Berkeley's `https://bcourses.berkeley.edu` is the default)
- ⚠️ Make sure the token is on the **same line** as `CANVAS_TOKEN=` — if it wraps to the next line, Canvas gets silently skipped

### 4️⃣ Run it

```bash
python sync.py --dry-run   # preview what it would add, changes nothing
python sync.py             # the real thing
```

The first real run opens a browser tab:

1. Pick the Google account you want the reminders in (a school account is fine)
2. Google shows **"Google hasn't verified this app"** — that's because a student made it, not a company. Click **Continue** (sometimes under "Advanced")
3. Click **Allow**

It saves a `token.json` and never asks again. Open Google Tasks and your assignments are there. 🎉

<details>
<summary>🤓 Why is there no Google Cloud setup?</summary>

The repo ships with a `credentials.json` for an OAuth app I registered. It only identifies the app to Google — it can't access anyone's account by itself. You still log in with your own account, and your own `token.json` stays on your computer.

Google caps unverified apps at 100 users. If the login ever fails with a message about that, or you'd rather use your own, create a **Desktop app** OAuth client in the [Google Cloud Console](https://console.cloud.google.com) (enable the Google Tasks API, create the client, download the JSON) and replace `credentials.json` with it.
</details>

---

## 🔁 Run It Automatically

### 🪟 Windows (Task Scheduler)

`run_sync.bat` runs the script with the project's `.venv` and logs to `sync.log`. In PowerShell (fix the path):

```powershell
schtasks /Create /TN "AssignmentSync" /SC DAILY /ST 07:00 /TR "C:\path\to\assignment-sync\run_sync.bat" /F
```

- ▶️ Test now: `schtasks /Run /TN "AssignmentSync"`, then check `sync.log`
- ⏱️ Every 6 hours instead: use `/SC HOURLY /MO 6`
- ❌ Remove: `schtasks /Delete /TN "AssignmentSync" /F`

### 🍎🐧 macOS / Linux (cron)

```bash
chmod +x run_sync.sh
crontab -e
# add this line to run every day at 7:00
0 7 * * * /path/to/assignment-sync/run_sync.sh
```

---

## 🔧 Options

All in `.env`:

| Variable | Default | What it does |
|---|---|---|
| `LOOKAHEAD_DAYS` | `21` | Only create reminders for assignments due within this many days |
| `REMIND_DAYS_BEFORE` | `0` | Date the reminder this many days *before* the deadline (the real due date is always in the notes) |
| `CANVAS_BASE_URL` | `https://bcourses.berkeley.edu` | Your school's Canvas address |

### 🏷️ Course names

Gradescope says `CS 61A`; Canvas says `2026-FA-COMPSCI-61A-001`. The script normalizes both into one list.

- Something in the wrong list? Add a mapping in `course_aliases.json` (raw name → list name)
- Different department abbreviations at your school? Edit `DEPT_ALIASES` at the top of `sync.py`

---

## 📁 Files It Creates

| File | Purpose |
|---|---|
| `token.json` | Your Google login — delete it to re-authorize |
| `synced.json` | Memory of what's already been added — delete it to re-add everything (clear your Tasks lists too, or you'll get duplicates) |
| `sync.log` | Output from scheduled runs |

All of these plus `.env` are git-ignored. Please don't commit them. 🙏

---

## 🔐 Privacy

Nothing leaves your computer except requests to Gradescope, Canvas, and Google's Tasks API. Your password and tokens live only in your local `.env` and `token.json`. Full policy: [PRIVACY.md](PRIVACY.md).

---

## 📄 License

MIT — see [LICENSE](LICENSE). ✌️
