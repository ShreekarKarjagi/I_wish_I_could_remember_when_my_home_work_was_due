import json, re, sys
sys.path.insert(0, ".")
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/tasks"])
svc = build("tasks", "v1", credentials=creds, cache_discovery=False)
state = json.load(open("synced.json"))
for key, rec in state.items():
    t = svc.tasks().get(tasklist=rec["list_id"], task=rec["task_id"]).execute()
    title = re.sub(r"^\[(Low|Medium|High)\]\s*", "", t.get("title",""))
    notes = "\n".join(l for l in (t.get("notes") or "").splitlines()
                      if not l.startswith(("Complexity:", "Why:", "Points:", "Source:")))
    if title != t.get("title") or notes != (t.get("notes") or ""):
        svc.tasks().patch(tasklist=rec["list_id"], task=rec["task_id"], body={"title": title, "notes": notes}).execute()
        print("fixed:", rec["course"], "/", title)
    else:
        print("ok:   ", rec["course"], "/", title)
