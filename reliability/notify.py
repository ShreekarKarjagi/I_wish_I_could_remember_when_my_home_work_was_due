"""Best-effort desktop notification. Never raises: a notification problem
must not turn a sync problem into a second one."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger("sync")

# Title/message come in through environment variables, not string
# interpolation, so error text containing quotes can't break the script.
_WINDOWS_TOAST = r"""
$ErrorActionPreference = 'Stop'
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$t = [Security.SecurityElement]::Escape($env:SYNC_NOTIFY_TITLE)
$m = [Security.SecurityElement]::Escape($env:SYNC_NOTIFY_MESSAGE)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$m</text></binding></visual></toast>")
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($toast)
"""


def _applescript_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(title: str, message: str) -> bool:
    """Show a desktop notification. Returns True if one was handed to the OS."""
    try:
        env = None
        if sys.platform == "win32":
            env = {**os.environ, "SYNC_NOTIFY_TITLE": title, "SYNC_NOTIFY_MESSAGE": message}
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                   "-Command", _WINDOWS_TOAST]
        elif sys.platform == "darwin":
            cmd = ["osascript", "-e",
                   f"display notification {_applescript_quote(message)} with title {_applescript_quote(title)}"]
        elif shutil.which("notify-send"):
            cmd = ["notify-send", title, message]
        else:
            return False
        return subprocess.run(cmd, env=env, timeout=20, capture_output=True).returncode == 0
    except Exception as e:  # noqa: BLE001
        log.debug("Could not show notification: %s", e)
        return False
