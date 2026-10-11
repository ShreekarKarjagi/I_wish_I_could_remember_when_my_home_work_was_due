import json
from datetime import datetime, timedelta, timezone

import pytest

from reliability.lock import FileLock, LockBusy
from reliability.net import make_session
from reliability.state import StateCorruptError, load_state, save_state
from reliability.status import FAILURES_BEFORE_NOTIFY, load_status, record_result


# --- state: atomic writes, backup, corruption policy ------------------------

def test_load_missing_file_is_an_empty_state(tmp_path):
    assert load_state(tmp_path / "synced.json") == {}


def test_save_then_load_roundtrips(tmp_path):
    p = tmp_path / "synced.json"
    save_state(p, {"a": {"x": 1}})
    assert load_state(p) == {"a": {"x": 1}}


def test_save_mirrors_the_latest_state_to_a_backup(tmp_path):
    p = tmp_path / "synced.json"
    save_state(p, {"v": 1})
    save_state(p, {"v": 2})
    assert json.loads((tmp_path / "synced.json.bak").read_text()) == {"v": 2}


def test_save_leaves_no_temp_file_behind(tmp_path):
    p = tmp_path / "synced.json"
    save_state(p, {"v": 1})
    assert not (tmp_path / "synced.json.tmp").exists()


def test_corrupt_state_restores_from_backup_with_nothing_lost(tmp_path):
    p = tmp_path / "synced.json"
    save_state(p, {"v": 1})
    save_state(p, {"v": 2})
    p.write_text("{truncated")
    assert load_state(p) == {"v": 2}


def test_empty_state_file_restores_from_backup(tmp_path):
    # A 0-byte file is the classic artifact of a crash mid-write.
    p = tmp_path / "synced.json"
    save_state(p, {"v": 1})
    save_state(p, {"v": 2})
    p.write_text("")
    assert load_state(p) == {"v": 2}


def test_corrupt_state_without_backup_raises_instead_of_starting_fresh(tmp_path):
    # Silently returning {} here would re-add every reminder as a duplicate.
    p = tmp_path / "synced.json"
    p.write_text("{not json")
    with pytest.raises(StateCorruptError):
        load_state(p)


def test_non_object_json_counts_as_corrupt(tmp_path):
    p = tmp_path / "synced.json"
    p.write_text("[1, 2, 3]")
    with pytest.raises(StateCorruptError):
        load_state(p)


def test_deleting_state_to_start_over_is_respected_not_restored(tmp_path):
    # README: "delete it to start over". A leftover .bak must not resurrect the old state.
    p = tmp_path / "synced.json"
    save_state(p, {"v": 1})
    p.unlink()
    assert load_state(p) == {}
    save_state(p, {"fresh": True})
    assert json.loads((tmp_path / "synced.json.bak").read_text()) == {"fresh": True}


# --- lock -------------------------------------------------------------------

def test_second_lock_on_same_file_is_refused(tmp_path):
    path = tmp_path / "sync.lock"
    with FileLock(path):
        with pytest.raises(LockBusy):
            FileLock(path).acquire()


def test_lock_can_be_reacquired_after_release(tmp_path):
    path = tmp_path / "sync.lock"
    with FileLock(path):
        pass
    with FileLock(path):
        pass


def test_failed_acquire_does_not_release_the_holders_lock(tmp_path):
    path = tmp_path / "sync.lock"
    with FileLock(path):
        with pytest.raises(LockBusy):
            FileLock(path).acquire()
        with pytest.raises(LockBusy):  # still held after the failed attempt
            FileLock(path).acquire()


# --- status / notification policy ------------------------------------------

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def test_success_records_timestamps_and_does_not_notify(tmp_path):
    p = tmp_path / "status.json"
    assert record_result(p, ok=True, now=T0) is False
    s = load_status(p)
    assert s["last_success"] == T0.isoformat()
    assert s["consecutive_failures"] == 0


def test_single_ordinary_failure_does_not_notify(tmp_path):
    p = tmp_path / "status.json"
    assert record_result(p, ok=False, error="Canvas timed out", now=T0) is False


def test_repeated_failures_notify(tmp_path):
    p = tmp_path / "status.json"
    results = [record_result(p, ok=False, error="x", now=T0 + timedelta(hours=4 * i))
               for i in range(FAILURES_BEFORE_NOTIFY)]
    assert results == [False] * (FAILURES_BEFORE_NOTIFY - 1) + [True]


def test_failure_that_needs_the_user_notifies_immediately(tmp_path):
    p = tmp_path / "status.json"
    assert record_result(p, ok=False, error="TODOIST_TOKEN is not set", needs_action=True, now=T0) is True


def test_notifications_are_rate_limited_to_once_a_day(tmp_path):
    p = tmp_path / "status.json"
    assert record_result(p, ok=False, error="x", needs_action=True, now=T0) is True
    assert record_result(p, ok=False, error="x", needs_action=True, now=T0 + timedelta(hours=4)) is False
    assert record_result(p, ok=False, error="x", needs_action=True, now=T0 + timedelta(hours=25)) is True


def test_recovery_resets_so_the_next_failure_alerts_promptly(tmp_path):
    p = tmp_path / "status.json"
    record_result(p, ok=False, error="x", needs_action=True, now=T0)
    record_result(p, ok=True, now=T0 + timedelta(hours=4))
    assert record_result(p, ok=False, error="again", needs_action=True, now=T0 + timedelta(hours=8)) is True


def test_corrupt_status_file_is_tolerated(tmp_path):
    p = tmp_path / "status.json"
    p.write_text("{nope")
    assert record_result(p, ok=True, now=T0) is False
    assert load_status(p)["last_success"] == T0.isoformat()


# --- HTTP sessions ----------------------------------------------------------

def test_session_retries_transient_errors_on_idempotent_methods():
    adapter = make_session().get_adapter("https://api.example.com")
    retry = adapter.max_retries
    assert retry.total == 3
    assert {429, 500, 503} <= set(retry.status_forcelist)
    assert retry.is_retry("GET", 503)
    assert retry.is_retry("PATCH", 503)


def test_session_never_retries_a_post_that_may_have_been_processed():
    # Retrying would risk creating the same reminder twice.
    retry = make_session().get_adapter("https://api.example.com").max_retries
    assert not retry.is_retry("POST", 503)


def test_session_applies_headers_and_pool_size():
    s = make_session({"Authorization": "Bearer t"}, pool_maxsize=6)
    assert s.headers["Authorization"] == "Bearer t"
    assert s.get_adapter("https://x.test")._pool_maxsize == 6
