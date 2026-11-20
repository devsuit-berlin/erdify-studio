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


def test_an_old_or_invalid_version_number_has_no_upgrade_hint() -> None:
    with pytest.raises(LayoutVersionError, match="unknown layout file version 0") as exc:
        loads_layout('{"version": 0, "diagrams": {}}')
    assert "upgrade" not in str(exc.value)


def test_a_malformed_version_is_not_a_version_error() -> None:
    with pytest.raises(LayoutError) as exc:
        loads_layout('{"version": "2", "diagrams": {}}')
    assert not isinstance(exc.value, LayoutVersionError)


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


def test_save_does_not_overwrite_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    path.write_bytes(b"\xe4\xf6")
    with pytest.raises(LayoutError, match="not overwriting .*not UTF-8"):
        save_layout(_layout(), path)
    assert path.read_bytes() == b"\xe4\xf6"


def test_save_does_not_overwrite_a_file_with_a_lone_surrogate_key(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    content = '{"version": 1, "diagrams": {"d": {"\\ud800": [1, 2]}}}\n'
    path.write_text(content)
    with pytest.raises(LayoutError, match="not overwriting .*not valid UTF-8 text"):
        save_layout(_layout(), path)
    assert path.read_text() == content


def test_save_overwrites_an_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "erdify-layout.json"
    path.write_text("\n")
    save_layout(_layout(), path)
    assert path.read_text() == EXPECTED


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "12", True])
def test_set_position_rejects_non_numbers(value: object) -> None:
    with pytest.raises(LayoutError, match=r"'a' must be finite numbers"):
        Layout().set_position(OVERVIEW, "a", value, 0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("diagrams", "message"),
    [
        ({OVERVIEW: {"a": (1.5, 2)}}, r"'a' in diagram '_overview' must be integers"),
        ({OVERVIEW: {"a": 5}}, r"'a' in diagram '_overview' must be integers"),
        ({OVERVIEW: {"a": (1, 2, 3)}}, r"'a' in diagram '_overview' must be integers"),
        ({OVERVIEW: {1: (0, 0)}}, r"key in diagram '_overview' must be a UTF-8 string, got 1"),
        ({OVERVIEW: {"a": (0, 0), 1: (0, 0)}}, r"must be a UTF-8 string, got 1"),
        ({2: {"a": (0, 0)}}, r"diagram name must be a UTF-8 string, got 2"),
        ({OVERVIEW: {"\ud800": (0, 0)}}, r"must be a UTF-8 string, got '\\ud800'"),
        ({"\ud800": {}}, r"diagram name must be a UTF-8 string"),
    ],
)
def test_dump_rejects_values_set_around_set_position(diagrams: object, message: str) -> None:
    layout = Layout(diagrams=diagrams)  # type: ignore[arg-type]
    with pytest.raises(LayoutError, match=message):
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
    with pytest.raises(LayoutError, match="cannot write .*disk full"):
        save_layout(Layout(), path)
    assert path.read_text() == EXPECTED
    assert [p.name for p in tmp_path.iterdir()] == ["erdify-layout.json"]


def test_save_flushes_to_disk_before_replacing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    def replace(src: str, dst: str) -> None:
        calls.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    save_layout(_layout(), tmp_path / "erdify-layout.json")
    assert calls == ["fsync", "replace"]


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_save_through_a_symlink_updates_the_target(tmp_path: Path) -> None:
    target = tmp_path / "shared" / "erdify-layout.json"
    save_layout(Layout(), target)
    link = tmp_path / "erdify-layout.json"
    link.symlink_to(target)
    save_layout(_layout(), link)
    assert link.is_symlink()
    assert target.read_text() == EXPECTED


def test_a_folder_as_layout_path_is_a_layout_error(tmp_path: Path) -> None:
    with pytest.raises(LayoutError, match="cannot read"):
        load_layout(tmp_path)
    with pytest.raises(LayoutError, match="not overwriting .*cannot read"):
        save_layout(_layout(), tmp_path)


def test_an_unwritable_folder_is_a_layout_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(LayoutError, match="cannot write .*permission denied"):
        save_layout(_layout(), tmp_path / "docs" / "erdify-layout.json")


def test_an_unreadable_existing_file_is_a_layout_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "erdify-layout.json"
    save_layout(_layout(), path)

    def fail(*args: object, **kwargs: object) -> None:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "stat", fail)
    with pytest.raises(LayoutError, match="cannot write .*permission denied"):
        save_layout(_layout(), path)


def test_save_when_the_file_vanishes_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "erdify-layout.json"
    save_layout(Layout(), path)
    real_read_text = Path.read_text

    def vanish(self: Path, *args: object, **kwargs: object) -> str:
        if self == path.resolve():
            self.unlink()
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", vanish)
    save_layout(_layout(), path)
    monkeypatch.undo()
    assert path.read_text() == EXPECTED


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_layout(tmp_path / "erdify-layout.json")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("<<<<<<< HEAD\n", "not valid JSON"),
        ("[]", "must be a JSON object"),
        ('{"diagrams": {}}', "no 'version'"),
        ('{"version": "1", "diagrams": {}}', "'version' must be an integer, got '1'"),
        ('{"version": 1.0, "diagrams": {}}', "'version' must be an integer, got 1.0"),
        ('{"version": true, "diagrams": {}}', "'version' must be an integer, got True"),
        ('{"version": 1}', "'diagrams' must be an object"),
        ('{"version": 1, "diagrams": []}', "'diagrams' must be an object"),
        ('{"version": 1, "diagrams": {}, "extra": 1}', "unknown key 'extra'"),
        ('{"version": 1, "diagrams": {"d": []}}', "diagram 'd' must be an object"),
        ('{"version": 1, "diagrams": {"d": {"a": [1]}}}', r"'a' in diagram 'd'.*\[x, y\]"),
        ('{"version": 1, "diagrams": {"d": {"a": [1, 2.5]}}}', r"'a' in diagram 'd'.*\[x, y\]"),
        ('{"version": 1, "diagrams": {"d": {"a": [true, 2]}}}', r"'a' in diagram 'd'.*\[x, y\]"),
        ('{"version": 1, "diagrams": {"d": {"a": "1,2"}}}', r"'a' in diagram 'd'.*\[x, y\]"),
        ('{"version": 1, "diagrams": {"d": {}, "d": {}}}', "duplicate key 'd'"),
        ('{"version": 1, "diagrams": {"d": {"\\ud800": [1, 2]}}}', "is not valid UTF-8 text"),
        ('{"version": 1, "diagrams": {"\\ud800": {}}}', "is not valid UTF-8 text"),
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
