import json

import pytest

import sync


def test_new_assignment_within_lookahead_is_added(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    counts = sync.sync([a], dry_run=False, destination=fake_tasks)

    assert counts == {"added": 1, "updated": 0, "completed": 0, "skipped": 0, "failed": 0}
    assert len(fake_tasks.tasks) == 1
    state = json.loads(sync.STATE_FILE.read_text())
    assert a.key in state
    assert state[a.key]["completed"] is False


def test_assignment_beyond_lookahead_is_skipped(make_assignment, fake_tasks, monkeypatch):
    monkeypatch.setattr(sync, "LOOKAHEAD_DAYS", 21)
    a = make_assignment(days_from_now=90)
    counts = sync.sync([a], dry_run=False, destination=fake_tasks)
    assert counts["skipped"] == 1
    assert counts["added"] == 0
    assert fake_tasks.tasks == {}


def test_past_due_assignment_is_skipped(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=-2)
    counts = sync.sync([a], dry_run=False, destination=fake_tasks)
    assert counts["skipped"] == 1
    assert fake_tasks.tasks == {}


def test_assignment_with_no_due_date_is_skipped(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=None)
    counts = sync.sync([a], dry_run=False, destination=fake_tasks)
    assert counts["skipped"] == 1


def test_already_submitted_new_assignment_is_skipped_not_added(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5, submitted=True)
    counts = sync.sync([a], dry_run=False, destination=fake_tasks)
    assert counts["skipped"] == 1
    assert counts["added"] == 0


def test_tracked_assignment_marked_submitted_completes_the_task(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=fake_tasks)

    a_submitted = make_assignment(source=a.source, source_id=a.source_id,
                                   days_from_now=5, submitted=True)
    counts = sync.sync([a_submitted], dry_run=False, destination=fake_tasks)

    assert counts == {"added": 0, "updated": 0, "completed": 1, "skipped": 0, "failed": 0}
    state = json.loads(sync.STATE_FILE.read_text())
    assert state[a.key]["completed"] is True
    assert fake_tasks.patched[-1][2] == {"status": "completed"}


def test_completing_a_tracked_assignment_is_idempotent(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=fake_tasks)
    a_submitted = make_assignment(source=a.source, source_id=a.source_id,
                                   days_from_now=5, submitted=True)
    sync.sync([a_submitted], dry_run=False, destination=fake_tasks)

    # Running again with the same "submitted" assignment shouldn't re-patch it.
    counts = sync.sync([a_submitted], dry_run=False, destination=fake_tasks)
    assert counts["completed"] == 0


def test_tracked_assignment_due_date_change_updates_task(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=fake_tasks)

    a_moved = make_assignment(source=a.source, source_id=a.source_id, days_from_now=8)
    counts = sync.sync([a_moved], dry_run=False, destination=fake_tasks)

    assert counts == {"added": 0, "updated": 1, "completed": 0, "skipped": 0, "failed": 0}
    state = json.loads(sync.STATE_FILE.read_text())
    assert state[a.key]["due"] == a_moved.due.isoformat()


def test_tracked_assignment_unchanged_is_left_alone(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=fake_tasks)
    counts = sync.sync([a], dry_run=False, destination=fake_tasks)
    assert counts == {"added": 0, "updated": 0, "completed": 0, "skipped": 0, "failed": 0}
    assert fake_tasks.patched == []


def test_reruns_never_duplicate_a_task(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=fake_tasks)
    sync.sync([a], dry_run=False, destination=fake_tasks)
    sync.sync([a], dry_run=False, destination=fake_tasks)
    assert len(fake_tasks.tasks) == 1


def test_different_courses_get_different_task_lists(make_assignment, fake_tasks):
    a1 = make_assignment(source_id="1", course="CS 61A", days_from_now=3)
    a2 = make_assignment(source_id="2", course="EE 16A", days_from_now=3)
    sync.sync([a1, a2], dry_run=False, destination=fake_tasks)
    assert fake_tasks.lists["CS 61A"] != fake_tasks.lists["EE 16A"]


def test_dry_run_does_not_write_state_file(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=True, destination=fake_tasks)
    assert not sync.STATE_FILE.exists()


def test_corrupt_state_with_no_backup_aborts_instead_of_re_adding_everything(make_assignment, fake_tasks):
    # Treating it as empty would create a duplicate of every reminder.
    from reliability.state import StateCorruptError

    sync.STATE_FILE.write_text("{not json")
    a = make_assignment(days_from_now=5)
    with pytest.raises(StateCorruptError):
        sync.sync([a], dry_run=False, destination=fake_tasks)
    assert fake_tasks.tasks == {}  # nothing was created


def test_corrupt_state_recovers_from_the_backup(make_assignment, fake_tasks):
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=fake_tasks)   # state (and its .bak mirror) saved
    sync.STATE_FILE.write_text("")                          # something left an empty file
    counts = sync.sync([a], dry_run=False, destination=fake_tasks)
    assert counts["added"] == 0           # recognised as already tracked, via the backup
    assert len(fake_tasks.tasks) == 1


def test_record_from_a_different_destination_is_recreated_not_patched(make_assignment, fake_destination_factory):
    """Switching REMINDER_DESTINATION shouldn't try to patch the old
    destination's id with the new destination's client -- that would just
    error, since the ids belong to a different service entirely."""
    todoist_like = fake_destination_factory("todoist")
    a = make_assignment(days_from_now=5)
    sync.sync([a], dry_run=False, destination=todoist_like)

    notion_like = fake_destination_factory("notion")
    counts = sync.sync([a], dry_run=False, destination=notion_like)

    assert counts["added"] == 1  # recreated under the new destination
    assert notion_like.patched == []  # never touched with the old (foreign) ids
    assert len(notion_like.tasks) == 1


def test_legacy_record_with_no_destination_is_recreated_not_patched(make_assignment, fake_tasks):
    """Records with no "destination" were written by the removed Google Tasks
    support. Their ids mean nothing to the current destination, so they must be
    recreated rather than patched with ids the new service has never seen."""
    a = make_assignment(days_from_now=5)
    sync.STATE_FILE.write_text(json.dumps({
        a.key: {"list_id": "google-list", "task_id": "google-task", "due": a.due.isoformat(),
                "title": a.title, "course": a.course, "completed": False},
    }))

    counts = sync.sync([a], dry_run=False, destination=fake_tasks)

    assert counts["added"] == 1
    assert fake_tasks.patched == []
    assert json.loads(sync.STATE_FILE.read_text())[a.key]["destination"] == fake_tasks.name
