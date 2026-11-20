import os
from pathlib import Path

import pytest

from erdify_studio import (
    OVERVIEW,
    Layout,
    LayoutError,
    LayoutVersionError,
    StudioError,
    dumps_layout,
    load_layout,
    loads_layout,
    save_layout,
)

EXPECTED = """\
{
  "version": 1,
  "diagrams": {
    "_overview": {
      "core.customers": [120, 40],
      "enum:Status": [-8, 300],
      "order": [480, 40]
    },
    "core": {
      "core.customers": [40, 40],
      "order": [400, 300]
    },
    "empty": {}
  }
}
"""


def _layout() -> Layout:
    layout = Layout()
    # Inserted out of order on purpose: the file is sorted regardless.
    layout.add_diagram("empty")
    layout.set_position("core", "order", 400, 300)
    layout.set_position("core", "core.customers", 40, 40)
    layout.set_position(OVERVIEW, "order", 480, 40)
    layout.set_position(OVERVIEW, "enum:Status", -8, 300)
    layout.set_position(OVERVIEW, "core.customers", 120, 40)
    return layout


def test_dump_is_sorted_one_entry_per_line_with_trailing_newline() -> None:
    assert dumps_layout(_layout()) == EXPECTED


def test_saving_twice_is_byte_identical(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    save_layout(_layout(), path)
    first = path.read_bytes()
    save_layout(load_layout(path), path)
    assert path.read_bytes() == first
    assert first == EXPECTED.encode()


def test_round_trip() -> None:
    assert loads_layout(EXPECTED) == _layout()


def test_empty_layout() -> None:
    assert dumps_layout(Layout()) == '{\n  "version": 1,\n  "diagrams": {}\n}\n'
    assert loads_layout(dumps_layout(Layout())) == Layout()


@pytest.mark.parametrize(("x", "y", "expected"), [(10.4, 20.6, (10, 21)), (-0.4, 2.5, (0, 2))])
def test_positions_are_rounded_to_integers(x: float, y: float, expected: tuple[int, int]) -> None:
    layout = Layout()
    layout.set_position(OVERVIEW, "a", x, y)
    assert layout.diagrams[OVERVIEW]["a"] == expected


def test_keys_needing_escapes_survive_a_round_trip() -> None:
    layout = Layout()
    layout.set_position(OVERVIEW, 'we"ird\\key', 1, 2)
    layout.set_position(OVERVIEW, "ümlaut.tabelle", 3, 4)
    text = dumps_layout(layout)
    assert '"ümlaut.tabelle": [3, 4]' in text
    assert loads_layout(text) == layout


def test_unknown_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    path.write_text('{"version": 2, "diagrams": {}}\n')
    with pytest.raises(LayoutVersionError, match=r"version 2 .*erdify-layout\.json.*supports 1"):
        load_layout(path)


def test_save_does_not_overwrite_a_file_of_an_unknown_version(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    original = '{"version": 2, "diagrams": {"_overview": {"a": [1, 2]}}}\n'
    path.write_text(original)
    with pytest.raises(LayoutVersionError):
        save_layout(Layout(), path)
    assert path.read_text() == original


def test_save_overwrites_a_broken_file(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    path.write_text("<<<<<<< HEAD\n")
    save_layout(_layout(), path)
    assert path.read_text() == EXPECTED


def test_save_creates_missing_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "erd" / "erdify-layout.json"
    save_layout(_layout(), path)
    assert path.read_text() == EXPECTED


def test_failed_save_keeps_the_old_file_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "erdify-layout.json"
    save_layout(_layout(), path)

    def fail(src: str, dst: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        save_layout(Layout(), path)
    assert path.read_text() == EXPECTED
    assert [p.name for p in tmp_path.iterdir()] == ["erdify-layout.json"]


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_layout(tmp_path / "erdify-layout.json")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("<<<<<<< HEAD\n", "not valid JSON"),
        ("[]", "must be a JSON object"),
        ('{"diagrams": {}}', "no 'version'"),
        ('{"version": "1", "diagrams": {}}', "version '1'"),
        ('{"version": 1}', "'diagrams' must be an object"),
        ('{"version": 1, "diagrams": []}', "'diagrams' must be an object"),
        ('{"version": 1, "diagrams": {}, "extra": 1}', "unknown key 'extra'"),
        ('{"version": 1, "diagrams": {"d": []}}', "diagram 'd' must be an object"),
        ('{"version": 1, "diagrams": {"d": {"a": [1]}}}', r"'a' in diagram 'd'.*\[x, y\]"),
        ('{"version": 1, "diagrams": {"d": {"a": [1, 2.5]}}}', r"'a' in diagram 'd'.*\[x, y\]"),
        ('{"version": 1, "diagrams": {"d": {"a": [true, 2]}}}', r"'a' in diagram 'd'.*\[x, y\]"),
        ('{"version": 1, "diagrams": {"d": {"a": "1,2"}}}', r"'a' in diagram 'd'.*\[x, y\]"),
        ('{"version": 1, "diagrams": {"d": {}, "d": {}}}', "duplicate key 'd'"),
        ('{"version": 1, "diagrams": {"d": {"a": [1, 2], "a": [3, 4]}}}', "duplicate key 'a'"),
    ],
)
def test_malformed_files_are_reported(text: str, message: str) -> None:
    with pytest.raises(LayoutError, match=message):
        loads_layout(text, source="layout.json")


def test_layout_errors_name_the_file(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    path.write_text("[]")
    with pytest.raises(LayoutError, match=r"erdify-layout\.json"):
        load_layout(path)


def test_layout_errors_share_the_package_base() -> None:
    assert issubclass(LayoutVersionError, LayoutError)
    assert issubclass(LayoutError, StudioError)
