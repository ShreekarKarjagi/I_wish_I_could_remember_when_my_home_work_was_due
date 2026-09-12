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
