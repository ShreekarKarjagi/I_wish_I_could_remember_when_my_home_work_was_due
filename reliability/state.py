"""Crash-safe JSON state files.

synced.json is what stops the sync from creating duplicate reminders, so
losing or corrupting it is the worst thing that can happen. Writes are
atomic (temp file + replace) and a mirror copy is kept as .bak, so a file
that later gets damaged (disk trouble, a bad hand-edit) can be restored with
nothing lost.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger("sync")


class StateCorruptError(RuntimeError):
    """synced.json is unreadable and there is no usable backup."""


def atomic_write_text(path: Path, text: str) -> None:
    """Write `text` so a crash mid-write can never leave `path` half-written."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def _read_json_dict(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")
    return data


def load_state(path: Path) -> dict:
    """Missing file -> {} (first run, or deliberately deleted to start over).
    Unreadable file -> the last good backup, or StateCorruptError. It never
    quietly returns {} for a corrupt file: that would re-add every reminder."""
    if not path.exists():
        return {}
    try:
        return _read_json_dict(path)
    except (ValueError, OSError) as e:
        bak = _backup_path(path)
        try:
            data = _read_json_dict(bak)
        except (ValueError, OSError):
            raise StateCorruptError(
                f"{path.name} is unreadable ({e}) and there is no usable backup. "
                f"Fix or delete it (deleting re-adds everything still due) and run again."
            ) from e
        log.warning("%s was unreadable (%s); restored from %s", path.name, e, bak.name)
        return data


def save_state(path: Path, state: dict) -> None:
    text = json.dumps(state, indent=2, sort_keys=True)
    atomic_write_text(path, text)
    # Mirror to .bak *after* the main file is safely in place. A crash between
    # the two leaves the backup one step behind, never the main file damaged.
    atomic_write_text(_backup_path(path), text)
