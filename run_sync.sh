#!/usr/bin/env bash
# macOS / Linux equivalent of run_sync.bat. Appends output to sync.log.
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1

# Roll sync.log over once it passes ~1 MB so it can't grow forever.
if [ -f sync.log ] && [ "$(wc -c < sync.log)" -gt 1048576 ]; then mv -f sync.log sync.log.1; fi

# The script's exit status is the sync's, so cron/launchd can see failures.
if command -v uv >/dev/null 2>&1; then
  uv run sync.py >> sync.log 2>&1
else
  PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
  "$PY" sync.py >> sync.log 2>&1
fi
