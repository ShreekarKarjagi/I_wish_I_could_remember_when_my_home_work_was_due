# Privacy Policy

assignment-sync is an open-source script that runs entirely on your own computer. There is no server, no hosted service, and no one behind it collecting anything.

**What it accesses.** With your permission, the script reads your assignment list from Gradescope and Canvas and creates, updates, and completes reminders in whichever destination you've configured (`REMINDER_DESTINATION` in `.env`): Google Tasks, Notion, or Todoist. The Google permission it asks for (`https://www.googleapis.com/auth/tasks`) is the only Google scope it uses; for Notion, it only reads/writes the one database you explicitly connect it to; for Todoist, its personal token has the same access your own account does.

**Where your data goes.** Assignment names, due dates, and links are sent from your computer to the API of whichever destination is configured (Google's, Notion's, or Todoist's) so the reminders can be created. Nothing is sent anywhere else. Your Gradescope password, Canvas token, Google login token, Notion integration token, and Todoist token are stored only in files on your computer (`.env` and `token.json`) and are never transmitted to the author or any third party.

**What is stored.** A local file (`synced.json`) keeps track of which assignments have already been added so they aren't duplicated. You can delete it at any time.

**Revoking access.** For Google Tasks: delete `token.json` from the project folder, and remove the app under your Google Account → Security → Third-party apps & services. For Notion: remove the integration's connection to your database, or delete the integration entirely at [notion.so/my-integrations](https://www.notion.so/my-integrations). For Todoist: delete the token at Settings → Integrations → Developer.

**Contact.** Questions can be raised as issues on the project's GitHub repository.

_Last updated: September 2026_
