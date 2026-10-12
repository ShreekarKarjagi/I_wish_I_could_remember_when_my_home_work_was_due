"""The scheduled task runs under pythonw.exe so no console window ever pops up.
That means no stdout/stderr, so the script must log to sync.log by itself."""

import subprocess
import sys
from unittest.mock import MagicMock

import sync
from reliability import notify as notify_module


def test_with_a_console_nothing_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "LOG_FILE", tmp_path / "sync.log")
    before = (sys.stdout, sys.stderr)
    sync._log_to_file_if_windowless()
    assert (sys.stdout, sys.stderr) == before
    assert not (tmp_path / "sync.log").exists()


def test_without_a_console_output_goes_to_sync_log(tmp_path, monkeypatch):
    log_file = tmp_path / "sync.log"
    monkeypatch.setattr(sync, "LOG_FILE", log_file)
    monkeypatch.setattr(sys, "stdout", None)   # what pythonw.exe gives you
    monkeypatch.setattr(sys, "stderr", None)

    sync._log_to_file_if_windowless()
    try:
        print("from print", file=sys.stdout)
        print("from stderr", file=sys.stderr)
        sys.stderr.flush()
    finally:
        sys.stderr.close()  # release the file so Windows can clean up tmp_path

    text = log_file.read_text(encoding="utf-8")
    assert "from print" in text and "from stderr" in text


def test_without_a_console_it_appends_rather_than_overwrites(tmp_path, monkeypatch):
    log_file = tmp_path / "sync.log"
    log_file.write_text("earlier run\n", encoding="utf-8")
    monkeypatch.setattr(sync, "LOG_FILE", log_file)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    sync._log_to_file_if_windowless()
    try:
        print("this run", file=sys.stderr)
    finally:
        sys.stderr.close()

    assert log_file.read_text(encoding="utf-8").splitlines() == ["earlier run", "this run"]


def test_oversized_log_rolls_over_instead_of_growing_forever(tmp_path, monkeypatch):
    log_file = tmp_path / "sync.log"
    log_file.write_text("x" * (sync.MAX_LOG_BYTES + 1), encoding="utf-8")
    monkeypatch.setattr(sync, "LOG_FILE", log_file)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    sync._log_to_file_if_windowless()
    try:
        print("fresh", file=sys.stderr)
    finally:
        sys.stderr.close()

    assert (tmp_path / "sync.log.1").stat().st_size > sync.MAX_LOG_BYTES
    assert log_file.read_text(encoding="utf-8").strip() == "fresh"


def test_toast_helper_never_opens_a_console_window_on_windows(monkeypatch):
    # PowerShell is a console app; launched from a windowless process it would
    # flash a console unless told not to.
    run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(notify_module.subprocess, "run", run)
    monkeypatch.setattr(notify_module.sys, "platform", "win32")
    monkeypatch.setattr(notify_module.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

    assert notify_module.notify("title", "message") is True
    assert run.call_args.kwargs["creationflags"] == 0x08000000


def test_toast_helper_passes_no_special_flags_elsewhere(monkeypatch):
    run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(notify_module.subprocess, "run", run)
    monkeypatch.setattr(notify_module.sys, "platform", "linux")
    monkeypatch.setattr(notify_module.shutil, "which", lambda name: "/usr/bin/notify-send")

    assert notify_module.notify("title", "message") is True
    assert run.call_args.kwargs["creationflags"] == 0  # creationflags only exists on Windows
