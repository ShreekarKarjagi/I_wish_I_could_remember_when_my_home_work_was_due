#!/usr/bin/env bash
# macOS / Linux equivalent of run_sync.bat. Appends output to sync.log.
cd "$(dirname "$0")" || exit 1
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
"$PY" sync.py >> sync.log 2>&1
