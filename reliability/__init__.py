"""Small building blocks that keep an unattended sync from failing silently
or corrupting its own state: atomic state files, a single-instance lock,
run status + notifications, and HTTP retries."""
