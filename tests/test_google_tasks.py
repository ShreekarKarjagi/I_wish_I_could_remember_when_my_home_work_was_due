import pytest
from unittest.mock import MagicMock

from destinations.google_tasks import GoogleTasksDestination


def test_dry_run_never_builds_a_real_service():
    gt = GoogleTasksDestination(dry_run=True)
    assert gt.service is None


def test_dry_run_list_id_is_deterministic_placeholder():
    gt = GoogleTasksDestination(dry_run=True)
    assert gt.list_id("CS 61A") == "dry-CS 61A"
    # calling again for the same course must reuse the cached id, not recompute
    assert gt.list_id("CS 61A") == "dry-CS 61A"


def test_dry_run_insert_and_patch_are_no_ops():
    gt = GoogleTasksDestination(dry_run=True)
    assert gt.insert("dry-CS 61A", {"title": "HW"}) == "dry-task"
    gt.patch("dry-CS 61A", "dry-task", {"status": "completed"})  # must not raise


def _tasks_service_with_lists(existing: dict[str, str]):
    """Build a MagicMock imitating googleapiclient's tasks() service enough
    for GoogleTasksDestination.list_id()/insert()/patch()."""
    service = MagicMock()
    service.tasklists().list().execute.return_value = {
        "items": [{"title": t, "id": i} for t, i in existing.items()],
        "nextPageToken": None,
    }
    return service


def test_list_id_reuses_existing_list_instead_of_recreating():
    gt = GoogleTasksDestination.__new__(GoogleTasksDestination)  # skip _build (needs real creds)
    gt.dry_run = False
    gt._lists = None
    gt.service = _tasks_service_with_lists({"CS 61A": "abc123"})

    assert gt.list_id("CS 61A") == "abc123"
    gt.service.tasklists().insert.assert_not_called()


def test_list_id_creates_list_when_missing():
    gt = GoogleTasksDestination.__new__(GoogleTasksDestination)
    gt.dry_run = False
    gt._lists = None
    service = _tasks_service_with_lists({})
    service.tasklists().insert().execute.return_value = {"id": "new-id"}
    gt.service = service

    assert gt.list_id("New Course") == "new-id"
    service.tasklists().insert.assert_called_with(body={"title": "New Course"})


def test_insert_delegates_to_service_and_returns_task_id():
    gt = GoogleTasksDestination.__new__(GoogleTasksDestination)
    gt.dry_run = False
    service = MagicMock()
    service.tasks().insert().execute.return_value = {"id": "task-9"}
    gt.service = service

    task_id = gt.insert("list-1", {"title": "HW"})
    assert task_id == "task-9"
    service.tasks().insert.assert_called_with(tasklist="list-1", body={"title": "HW"})


def test_patch_swallows_errors_for_deleted_tasks():
    gt = GoogleTasksDestination.__new__(GoogleTasksDestination)
    gt.dry_run = False
    service = MagicMock()
    service.tasks().patch().execute.side_effect = RuntimeError("404 not found")
    gt.service = service

    gt.patch("list-1", "task-1", {"status": "completed"})  # must not raise


def test_completed_body_matches_google_tasks_status_field():
    gt = GoogleTasksDestination(dry_run=True)
    assert gt.completed_body() == {"status": "completed"}


def test_enabled_reflects_credentials_file_presence(tmp_path, monkeypatch):
    import destinations.google_tasks as google_tasks_module
    monkeypatch.setattr(google_tasks_module, "GOOGLE_CREDENTIALS", tmp_path / "credentials.json")
    gt = GoogleTasksDestination(dry_run=True)
    assert gt.enabled() is False
    (tmp_path / "credentials.json").write_text("{}")
    assert gt.enabled() is True


# --- _build(): what happens when the saved Google login stops working -------

class _FakeCreds:
    def __init__(self, refresh_error=None):
        self.valid = False
        self.expired = True
        self.refresh_token = "r"
        self._refresh_error = refresh_error

    def refresh(self, request):
        if self._refresh_error:
            raise self._refresh_error
        self.valid = True

    def to_json(self):
        return '{"fake": "token"}'


def _patch_google(monkeypatch, tmp_path, creds, *, interactive, flow_creds=None):
    """Stub out everything _build() imports so it never touches the network."""
    import sys
    import types

    import destinations.google_tasks as gt_module

    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr(gt_module, "GOOGLE_TOKEN", token)
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text("{}")
    monkeypatch.setattr(gt_module, "GOOGLE_CREDENTIALS", creds_file)

    class FakeCredentials:
        from_authorized_user_file = staticmethod(lambda *a, **k: creds)

    class FakeFlow:
        ran = False

        @classmethod
        def from_client_secrets_file(cls, *a, **k):
            return cls()

        def run_local_server(self, port=0):
            FakeFlow.ran = True
            return flow_creds

    built = {}

    def fake_build(*a, **k):
        built["creds"] = k["credentials"]
        return "SERVICE"

    mods = {
        "google.oauth2.credentials": types.SimpleNamespace(Credentials=FakeCredentials),
        "google_auth_oauthlib.flow": types.SimpleNamespace(InstalledAppFlow=FakeFlow),
        "googleapiclient.discovery": types.SimpleNamespace(build=fake_build),
    }
    for name, mod in mods.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr("sys.stdin", types.SimpleNamespace(isatty=lambda: interactive))
    monkeypatch.delenv("ASSIGNMENT_SYNC_UNATTENDED", raising=False)
    return FakeFlow, built


def test_build_uses_refreshed_token_when_refresh_succeeds(monkeypatch, tmp_path):
    creds = _FakeCreds()
    flow, built = _patch_google(monkeypatch, tmp_path, creds, interactive=False)
    assert GoogleTasksDestination._build() == "SERVICE"
    assert built["creds"] is creds
    assert flow.ran is False


def test_build_exits_with_clear_message_when_refresh_fails_unattended(monkeypatch, tmp_path):
    from google.auth.exceptions import RefreshError

    creds = _FakeCreds(refresh_error=RefreshError("invalid_grant"))
    flow, _ = _patch_google(monkeypatch, tmp_path, creds, interactive=False)
    with pytest.raises(SystemExit, match="sign in again"):
        GoogleTasksDestination._build()
    assert flow.ran is False  # never tries to open a browser on a scheduled run


def test_build_reauthorizes_when_refresh_fails_interactively(monkeypatch, tmp_path):
    from google.auth.exceptions import RefreshError

    creds = _FakeCreds(refresh_error=RefreshError("invalid_grant"))
    fresh = _FakeCreds()
    flow, built = _patch_google(monkeypatch, tmp_path, creds, interactive=True, flow_creds=fresh)
    assert GoogleTasksDestination._build() == "SERVICE"
    assert flow.ran is True
    assert built["creds"] is fresh
    assert (tmp_path / "token.json").read_text() == '{"fake": "token"}'


def test_build_exits_when_flagged_unattended_even_if_a_terminal_is_attached(monkeypatch, tmp_path):
    # Task Scheduler can give a scheduled run a real console, so isatty() is
    # True -- the run scripts set ASSIGNMENT_SYNC_UNATTENDED so we still never
    # open a browser (which would hang forever waiting for a click).
    from google.auth.exceptions import RefreshError

    creds = _FakeCreds(refresh_error=RefreshError("invalid_grant"))
    flow, _ = _patch_google(monkeypatch, tmp_path, creds, interactive=True)
    monkeypatch.setenv("ASSIGNMENT_SYNC_UNATTENDED", "1")
    with pytest.raises(SystemExit, match="sign in again"):
        GoogleTasksDestination._build()
    assert flow.ran is False
