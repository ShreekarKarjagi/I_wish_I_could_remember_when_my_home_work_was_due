# I wish I could remember when my homework was due

So I kept missing Gradescope deadlines because they were buried across four different course pages, and bCourses had its own set, and I was never going to check both every day. This script does the checking for me.

It logs into Gradescope and Canvas, grabs everything that's due soon and that you haven't submitted yet, and drops each one into Google Tasks as a reminder — one list per course, so your Tasks sidebar ends up looking like this:

```
EECS 126
  ☐ Lab 1                          Sep 9
  ☐ Homework 1 - Self Grade        Sep 10
EE 66
  ☐ HW1                            Sep 4
  ☐ Lecture 1B Mini-Vitamin        Sep 5
```

Each task has the exact deadline and a link back to the assignment in its notes. Run it on a schedule and you never have to think about it again: if a due date gets pushed, the reminder moves with it, and once you've submitted, the task gets checked off automatically. It won't create duplicates no matter how many times it runs.

I built it for Berkeley, but it works with any school that uses Canvas — you just change one URL.

## Getting it running

Honestly the code is the easy part. Most of the setup is convincing Google to give you an API key, which takes about ten minutes of clicking through the Cloud Console. I've written out every step because I got stuck on several of them. If you get stuck or feel like its getting to complicated the at any point just copy the project into an llm along with this readme and follow the steps it gives you 

You'll need Python 3.10 or newer.

### Step 1: Download and install

```bash
git clone https://github.com/ShreekarKarjagi/I_wish_I_could_remember_when_my_home_work_was_due.git assignment-sync
cd assignment-sync
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Everything you're about to set up goes into that `.env` file. It stays on your computer — it's git-ignored, so you can't accidentally commit it.

### Step 2: Gradescope

Gradescope doesn't have an API, so the script just logs in the same way you do, with an email and password.

If you've only ever used your school's SSO to log in and don't have a Gradescope password, go to https://www.gradescope.com/reset_password, enter your school email, and set one. Your SSO login keeps working; you'll just also have a password now. Put both in `.env`.

### Step 3: Canvas

Canvas does have a proper API, and you can make yourself a key in about thirty seconds. In Canvas go to **Account → Settings**, scroll down to **Approved Integrations**, and click **+ New Access Token**. Name it anything, leave the expiry blank, and copy the long string it gives you into `CANVAS_TOKEN` in `.env`.

Also set `CANVAS_BASE_URL` to your school's Canvas address. For Berkeley that's `https://bcourses.berkeley.edu`, which is already the default.

One thing that bit me: make sure the token ends up on the same line as `CANVAS_TOKEN=`. If it wraps onto the line below, the script thinks it's blank and quietly skips Canvas.

### Step 4: Google (the annoying part)

Google Tasks needs an OAuth app to write to it, and Google makes you create one yourself. Here's the whole thing:

1. Go to https://console.cloud.google.com and sign in. Any Google account is fine — it doesn't have to be the one whose Tasks you'll use.
2. Click the project dropdown at the top → **New Project**. Call it `assignment-sync`. If it asks for a Location or Parent, pick **No organization**. Create it, then make sure it's selected in the dropdown.
3. Left menu → **APIs & Services → Library**. Search for "Google Tasks API" and hit **Enable**.
4. Left menu → **APIs & Services → OAuth consent screen**. Newer versions of the console bounce you to a page called **Google Auth Platform** with a "Get started" button — click it. App name `assignment-sync`, support email = yours, audience **External**, contact email = yours. Create.
5. Now the step that got me: go to **Audience** (or the "Test users" section, on older consoles) and click **+ Add users**. Add the email of whatever Google account you want the reminders in — a school account works fine. If you skip this, the login later fails with a cryptic `Error 403: access_denied`.
6. **APIs & Services → Credentials** → **+ Create Credentials** → **OAuth client ID**. Application type is **Desktop app**. Create it, then click **Download JSON**.
7. The downloaded file is called something like `client_secret_123456…json`. Rename it to exactly `credentials.json` and drop it in the project folder.

### Step 5: Run it

```bash
python sync.py --dry-run   # shows what it would add without touching anything
python sync.py             # the real thing
```

The first real run opens a browser tab asking you to sign in to Google. Pick the account you added in step 5. Google will warn you that the app isn't verified — that's because *you* made it five minutes ago, so click **Continue** (sometimes hidden behind "Advanced") and then **Allow**. It saves a `token.json` and never asks again.

Now open Google Tasks — the sidebar in Gmail or Calendar, or the app on your phone — and your assignments should be there.

**One more Google thing.** While your app is in "Testing" mode, Google expires the login after 7 days, meaning you'd have to redo the browser step weekly. To stop that, go back to Google Auth Platform → **Audience** → **Publish app** and confirm. It'll mention verification; ignore it. Unverified apps work fine for personal use, they just show that warning screen at login.

## Making it run by itself

That's the whole point, really.

**Windows.** The included `run_sync.bat` runs the script using the project's `.venv` and appends its output to `sync.log`. Open PowerShell and register it with Task Scheduler (fix the path first):

```powershell
schtasks /Create /TN "AssignmentSync" /SC DAILY /ST 07:00 /TR "C:\path\to\assignment-sync\run_sync.bat" /F
```

To test it without waiting for 7 AM: `schtasks /Run /TN "AssignmentSync"`, then look at `sync.log`. If you want it every 6 hours instead, swap in `/SC HOURLY /MO 6`. To get rid of it: `schtasks /Delete /TN "AssignmentSync" /F`.

**Mac / Linux.** Same idea with cron:

```bash
chmod +x run_sync.sh
crontab -e
# add this line to run every day at 7:00
0 7 * * * /path/to/assignment-sync/run_sync.sh
```

## Tweaking it

There are two knobs in `.env`. `LOOKAHEAD_DAYS` (default 21) is how far ahead it looks — anything due later than that gets picked up on a future run once it's within range. `REMIND_DAYS_BEFORE` (default 0) shifts the task's date earlier than the actual deadline, if you'd rather see things two days out. The real due date is always written in the task notes either way.

Course names are a small mess: Gradescope calls a class "CS 61A" while Canvas calls it "2026-FA-COMPSCI-61A-001". The script normalizes both so they end up in the same list. If a course lands somewhere weird, open `course_aliases.json` and add a line mapping the raw name to whatever you want the list called. The department abbreviations near the top of `sync.py` are Berkeley-specific; edit them if your school uses different ones.

## Files it makes

`token.json` is your Google login (delete it to re-authorize), `synced.json` is its memory of what it's already added (delete it and it'll re-add everything, so clear your Tasks lists too), and `sync.log` is the output from scheduled runs. All three are git-ignored, along with `.env` and `credentials.json`. Please don't commit any of them.

## Privacy

Nothing leaves your computer except requests to Gradescope, Canvas, and Google's own Tasks API. Your password and tokens live only in your local `.env`. There's no server, no analytics, no anything.

## License

MIT. Do what you want with it.
