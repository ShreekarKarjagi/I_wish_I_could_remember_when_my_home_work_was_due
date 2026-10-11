# Privacy Policy

assignment-sync is an open-source script that runs entirely on your own computer. There is no server, no hosted service, and no one behind it collecting anything.

**What it accesses.** With your permission, the script reads your assignment list from Gradescope and Canvas and creates, updates, and completes reminders in whichever destination you've configured (`REMINDER_DESTINATION` in `.env`): Todoist or Notion. For Todoist, its personal token has the same access your own account does; for Notion, it only reads/writes the one database you explicitly connect it to.

**Where your data goes.** Assignment names, due dates, and links are sent from your computer to the API of whichever destination is configured (Todoist's or Notion's) so the reminders can be created. Nothing is sent anywhere else. Your Gradescope password, Canvas token, Todoist token, and Notion integration token are stored only in a file on your computer (`.env`) and are never transmitted to the author or any third party.

**What is stored.** A local file (`synced.json`) keeps track of which assignments have already been added so they aren't duplicated. You can delete it at any time.

**Revoking access.** For Todoist: delete the token at Settings → Integrations → Developer. For Notion: remove the integration's connection to your database, or delete the integration entirely at [notion.so/my-integrations](https://www.notion.so/my-integrations).

**Contact.** Questions can be raised as issues on the project's GitHub repository.

_Last updated: October 2026_
