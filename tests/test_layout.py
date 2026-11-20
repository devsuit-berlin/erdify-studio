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


@pytest.mark.parametrize(
    "content",
    [
        '<<<<<<< HEAD\n{"version": 1}\n=======\n{"version": 1}\n>>>>>>> main\n',
        "[]",
        '{"version": 1, "diagrams": {"d": {"a": "1,2"}}}',
    ],
)
def test_save_does_not_overwrite_a_broken_file(tmp_path: Path, content: str) -> None:
    path = tmp_path / "erdify-layout.json"
    path.write_text(content)
    with pytest.raises(LayoutError, match=r"not overwriting .*erdify-layout\.json"):
        save_layout(_layout(), path)
    assert path.read_text() == content


def test_save_keeps_the_file_permissions(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    save_layout(Layout(), path)
    path.chmod(0o644)
    save_layout(_layout(), path)
    assert path.stat().st_mode & 0o777 == 0o644


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_new_file_gets_the_umask_permissions(tmp_path: Path) -> None:
    umask = os.umask(0o022)
    try:
        save_layout(_layout(), tmp_path / "erdify-layout.json")
    finally:
        os.umask(umask)
    assert (tmp_path / "erdify-layout.json").stat().st_mode & 0o777 == 0o644


def test_a_byte_order_mark_is_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    path.write_bytes(b"\xef\xbb\xbf" + EXPECTED.encode())
    assert load_layout(path) == _layout()


def test_a_file_that_is_not_utf8_is_a_layout_error(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    path.write_bytes(b'{"version": 1, "diagrams": {"d": {"\xe4": [1, 2]}}}')
    with pytest.raises(LayoutError, match="not UTF-8"):
        load_layout(path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "12"])
def test_set_position_rejects_non_numbers(value: object) -> None:
    with pytest.raises(LayoutError, match=r"'a' must be finite numbers"):
        Layout().set_position(OVERVIEW, "a", value, 0)  # type: ignore[arg-type]


def test_dump_rejects_positions_set_around_set_position() -> None:
    layout = Layout(diagrams={OVERVIEW: {"a": (1.5, 2)}})  # type: ignore[dict-item]
    with pytest.raises(LayoutError, match=r"'a' in diagram '_overview' must be integers"):
        dumps_layout(layout)


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
