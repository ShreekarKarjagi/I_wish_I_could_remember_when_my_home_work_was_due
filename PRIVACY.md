# Privacy Policy

assignment-sync is an open-source script that runs entirely on your own computer. There is no server, no hosted service, and no one behind it collecting anything.

**What it accesses.** With your permission, the script reads your assignment list from Gradescope and Canvas and creates, updates, and completes tasks in your Google Tasks account. The Google permission it asks for (`https://www.googleapis.com/auth/tasks`) is the only one it uses.

**Where your data goes.** Assignment names, due dates, and links are sent from your computer to Google's Tasks API so the reminders can be created. Nothing is sent anywhere else. Your Gradescope password, Canvas token, and Google login token are stored only in files on your computer (`.env` and `token.json`) and are never transmitted to the author or any third party.

**What is stored.** A local file (`synced.json`) keeps track of which assignments have already been added so they aren't duplicated. You can delete it at any time.

**Revoking access.** Delete `token.json` from the project folder, and remove the app under your Google Account → Security → Third-party apps & services.

**Contact.** Questions can be raised as issues on the project's GitHub repository.

_Last updated: September 2026_
