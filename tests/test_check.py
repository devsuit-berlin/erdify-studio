"""The ``check`` command: diagram contents, layout problems and the CLI."""

from collections.abc import Callable, Mapping
from pathlib import Path

import erdify
import pytest

from erdify_studio import (
    OVERVIEW,
    DuplicateKeyError,
    Layout,
    LayoutVersionError,
    Problem,
    ProjectError,
    check_project,
    load_config,
    save_layout,
)
from erdify_studio.cli import main

MODELS = """\
import enum

from sqlmodel import Field, SQLModel


class Status(str, enum.Enum):
    OPEN = "open"


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    __table_args__ = {"schema": "core"}
    id: int = Field(primary_key=True)


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"
    __table_args__ = {"schema": "billing"}
    id: int = Field(primary_key=True)
    customer_id: int = Field(foreign_key="customers.id")


class Line(SQLModel, table=True):
    __tablename__ = "lines"
    __table_args__ = {"schema": "billing"}
    id: int = Field(primary_key=True)
    invoice_id: int = Field(foreign_key="invoices.id")
"""

ALL = ("billing.invoices", "billing.lines", "core.customers")

#: What each diagram of ``MODELS`` shows under ``group_by = "auto"``: own entities
#: plus foreign boxes (``core`` <- ``billing.invoices`` -> ``core.customers``).
AUTO = {
    OVERVIEW: ALL,
    "core": ("billing.invoices", "core.customers"),
    "billing": ALL,
}


def _project(root: Path, models: str = MODELS, studio: str = "", erdify: str = "") -> Path:
    (root / "pyproject.toml").write_text(
        f'[tool.erdify]\ninclude = ["**/models.py"]\n{erdify}\n[tool.erdify-studio]\n{studio}'
    )
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models)
    return root


def _complete(diagrams: Mapping[str, tuple[str, ...]] = AUTO) -> Layout:
    layout = Layout()
    for name, keys in diagrams.items():
        for i, key in enumerate(keys):
            layout.set_position(name, key, i * 300, 0)
    return layout


def _check(root: Path, layout: Layout | None = None) -> list[Problem] | None:
    project = erdify.load_project(root)
    config = load_config(project.settings.pyproject)
    if layout is not None:
        save_layout(layout, config.layout)
    return check_project(project, config)


# --- diagram contents --------------------------------------------------------------


@pytest.mark.parametrize(
    ("group_by", "diagrams"),
    [
        ("auto", AUTO),
        ("none", {OVERVIEW: ALL}),
        # Grouped by module, all three share "shop.models": no foreign boxes.
        ("module", {OVERVIEW: ALL, "shop.models": ALL}),
    ],
)
def test_a_complete_layout_has_no_problems(
    tmp_path: Path, group_by: str, diagrams: Mapping[str, tuple[str, ...]]
) -> None:
    root = _project(tmp_path, studio=f"group_by = {group_by!r}\n")
    assert _check(root, _complete(diagrams)) == []


@pytest.mark.parametrize(
    ("diagram", "key"), [("core", "billing.invoices"), ("billing", "core.customers")]
)
def test_foreign_boxes_are_required_in_both_directions(
    tmp_path: Path, diagram: str, key: str
) -> None:
    layout = _complete()
    del layout.diagrams[diagram][key]
    assert _check(_project(tmp_path), layout) == [Problem(diagram, key, "foreign")]


def test_without_relationships_there_are_no_foreign_boxes(tmp_path: Path) -> None:
    root = _project(tmp_path, erdify="no_relationships = true\n")
    assert _check(root, _complete()) == [
        Problem("billing", "core.customers", "stale_entry"),
        Problem("core", "billing.invoices", "stale_entry"),
    ]


def test_duplicate_layout_keys_are_refused(tmp_path: Path) -> None:
    models = MODELS.replace('__tablename__ = "lines"', '__tablename__ = "invoices"')
    with pytest.raises(DuplicateKeyError, match="'Invoice' and 'Line'"):
        _check(_project(tmp_path, models))


# --- layout problems ---------------------------------------------------------------


def test_without_layout_file_returns_none(tmp_path: Path) -> None:
    assert _check(_project(tmp_path)) is None


def test_unplaced_entities_are_reported_per_diagram(tmp_path: Path) -> None:
    layout = _complete()
    del layout.diagrams[OVERVIEW]["billing.lines"]
    del layout.diagrams["billing"]["billing.lines"]
    assert _check(_project(tmp_path), layout) == [
        Problem(OVERVIEW, "billing.lines", "unplaced"),
        Problem("billing", "billing.lines", "unplaced"),
    ]


def test_a_missing_diagram_reports_all_its_boxes(tmp_path: Path) -> None:
    layout = _complete()
    del layout.diagrams["core"]
    assert _check(_project(tmp_path), layout) == [
        Problem("core", "billing.invoices", "foreign"),
        Problem("core", "core.customers", "unplaced"),
    ]


def test_stale_entries_and_diagrams_are_reported(tmp_path: Path) -> None:
    layout = _complete()
    layout.set_position(OVERVIEW, "old_table", 0, 0)
    layout.set_position("core", "billing.lines", 0, 0)  # exists, but not shown in "core"
    layout.add_diagram("legacy")
    assert _check(_project(tmp_path), layout) == [
        Problem(OVERVIEW, "old_table", "stale_entry"),
        Problem("core", "billing.lines", "stale_entry"),
        Problem("legacy", None, "stale_diagram"),
    ]


def test_existing_enums_are_kept_but_not_required(tmp_path: Path) -> None:
    layout = _complete()
    layout.set_position("core", "enum:Status", 0, 0)
    layout.set_position(OVERVIEW, "enum:Gone", 0, 0)
    assert _check(_project(tmp_path), layout) == [Problem(OVERVIEW, "enum:Gone", "stale_entry")]


def test_a_project_without_entities_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="no entities found in "):
        _check(_project(tmp_path, models=""))


def test_another_layout_version_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "erdify-layout.json").write_text('{"version": 2, "diagrams": {}}')
    with pytest.raises(LayoutVersionError):
        _check(root)


@pytest.mark.parametrize(
    ("problem", "text"),
    [
        (Problem("core", "a", "unplaced"), "diagram 'core': entity 'a' has no position"),
        (Problem("core", "a", "foreign"), "diagram 'core': foreign box 'a' has no position"),
        (
            Problem("core", "a", "stale_entry"),
            "diagram 'core': stale entry 'a': not in this diagram",
        ),
        (Problem("old", None, "stale_diagram"), "stale diagram 'old': no such group"),
    ],
)
def test_problem_text(problem: Problem, text: str) -> None:
    assert str(problem) == text


# --- CLI --------------------------------------------------------------------------

HINT = (
    "hint: run `erdify-studio place --auto` to place new entities and drop stale entries, "
    "or open `erdify-studio` to arrange them"
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return _project(tmp_path)


def test_cli_clean_layout_exits_zero_without_output(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_layout(_complete(), project / "erdify-layout.json")
    assert main(["check"]) == 0
    assert capsys.readouterr() == ("", "")


def test_cli_reports_one_line_per_problem_then_the_hint(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    layout = _complete()
    del layout.diagrams["core"]["billing.invoices"]
    layout.set_position(OVERVIEW, "old_table", 0, 0)
    save_layout(layout, project / "erdify-layout.json")

    assert main(["check", str(project)]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err.splitlines() == [
        "erdify-layout.json: diagram '_overview': stale entry 'old_table': not in this diagram",
        "erdify-layout.json: diagram 'core': foreign box 'billing.invoices' has no position",
        HINT,
    ]


def test_cli_keeps_positions_of_existing_enums(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    layout = _complete()
    layout.set_position(OVERVIEW, "enum:Status", 0, 0)
    layout.set_position(OVERVIEW, "enum:Gone", 0, 0)
    save_layout(layout, project / "erdify-layout.json")
    assert main(["check"]) == 1
    assert capsys.readouterr().err.splitlines()[:-1] == [
        "erdify-layout.json: diagram '_overview': stale entry 'enum:Gone': not in this diagram"
    ]


@pytest.mark.parametrize("content", ["", "\n"])
def test_cli_empty_layout_file_counts_as_none(
    project: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    (project / "erdify-layout.json").write_text(content)
    assert main(["check"]) == 1
    assert capsys.readouterr().err.splitlines() == ["erdify-layout.json: no layout file yet", HINT]


def test_cli_without_layout_file_fails_with_the_hint(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check"]) == 1
    assert capsys.readouterr().err.splitlines() == ["erdify-layout.json: no layout file yet", HINT]


def test_cli_reads_the_configured_layout_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Run from a sibling folder: the path outside the working directory is absolute.
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    _project(root, studio='layout = "docs/layout.json"\ngroup_by = "none"\n')
    layout = Layout()
    for key in ALL:
        layout.set_position(OVERVIEW, key, 0, 0)
    save_layout(layout, root / "docs" / "layout.json")
    assert main(["check", str(root)]) == 0

    del layout.diagrams[OVERVIEW]["core.customers"]
    save_layout(layout, root / "docs" / "layout.json")
    assert main(["check", str(root)]) == 1
    first = capsys.readouterr().err.splitlines()[0]
    assert first == (
        f"{root / 'docs' / 'layout.json'}: diagram '_overview': "
        "entity 'core.customers' has no position"
    )


def test_cli_refuses_a_project_without_entities(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A wrong path or include would otherwise report every position as stale.
    save_layout(_complete(), project / "erdify-layout.json")
    (project / "shop" / "models.py").write_text("")
    assert main(["check"]) == 2
    err = capsys.readouterr().err
    assert "erdify-studio: error: no entities found in " in err
    assert HINT not in err


def test_allow_empty_checks_an_empty_project(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "pyproject.toml").write_text(
        '[tool.erdify]\ninclude = ["**/models.py"]\nallow_empty = true\n'
    )
    (project / "shop" / "models.py").write_text("")
    save_layout(Layout(), project / "erdify-layout.json")
    assert main(["check"]) == 0
    save_layout(_complete(), project / "erdify-layout.json")
    assert main(["check"]) == 1
    assert "stale diagram 'core'" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (lambda p: (p / "erdify-layout.json").write_text("<<<<<<< HEAD\n"), "not valid JSON"),
        (lambda p: (p / "erdify-layout.json").write_bytes(b"\xff\xfe{"), "is not UTF-8"),
        (
            lambda p: (p / "pyproject.toml").write_text(
                '[tool.erdify]\ninclude = ["**/models.py"]\n'
                '[tool.erdify-studio]\ngroup_by = "nope"\n'
            ),
            "'group_by' must be one of",
        ),
        (
            lambda p: (p / "pyproject.toml").write_text("[tool.erdify]\ninclude = 5\n"),
            "include",
        ),
    ],
    ids=["broken-layout", "latin1-layout", "bad-studio-config", "bad-erdify-config"],
)
def test_cli_errors_exit_two(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    setup: Callable[[Path], object],
    message: str,
) -> None:
    setup(project)
    assert main(["check"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("erdify-studio: error: ")
    assert message in err
    assert HINT not in err


def test_cli_missing_path_exits_two(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", "no-such-dir"]) == 2
    assert "erdify-studio: error:" in capsys.readouterr().err


def test_cli_internal_error_exits_two_with_traceback(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(erdify, "load_project", boom)
    assert main(["check"]) == 2
    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "RuntimeError: boom" in err
    assert err.splitlines()[-1] == (
        "erdify-studio: internal error (please report it with the traceback above)"
    )
