import json

from sources import base as sources_base
from sources.base import load_aliases, normalize_course


def test_normalizes_canvas_style_course_code():
    assert normalize_course("2026-FA-COMPSCI-61A-001", {}) == "CS 61A"


def test_normalizes_plain_gradescope_style_name():
    assert normalize_course("CS 61A", {}) == "CS 61A"


def test_applies_dept_alias_table():
    assert normalize_course("ELENG 126", {}) == "EE 126"


def test_falls_back_to_raw_string_when_no_course_pattern_matches():
    assert normalize_course("Reading Group", {}) == "Reading Group"


def test_explicit_alias_overrides_everything():
    aliases = {"2026-FA-COMPSCI-61A-001": "CS61A (lecture)"}
    assert normalize_course("2026-FA-COMPSCI-61A-001", aliases) == "CS61A (lecture)"


def test_alias_can_also_remap_the_normalized_label():
    # normalize_course looks the *derived* label up in aliases too.
    aliases = {"CS 61A": "Big CS Class"}
    assert normalize_course("COMPSCI 61A", aliases) == "Big CS Class"


def test_load_aliases_missing_file_returns_empty_dict():
    assert not sources_base.ALIASES_FILE.exists()
    assert load_aliases() == {}


def test_load_aliases_reads_json_file(tmp_path, monkeypatch):
    monkeypatch.setattr("sources.base.ALIASES_FILE", tmp_path / "course_aliases.json")
    (tmp_path / "course_aliases.json").write_text(json.dumps({"raw": "Nice Name"}))
    assert load_aliases() == {"raw": "Nice Name"}


def test_load_aliases_corrupt_json_is_ignored(tmp_path, monkeypatch, caplog):
    path = tmp_path / "course_aliases.json"
    monkeypatch.setattr("sources.base.ALIASES_FILE", path)
    path.write_text("{not valid json")
    assert load_aliases() == {}
