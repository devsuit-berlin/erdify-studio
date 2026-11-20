"""The ``check`` command: diagram contents, layout problems and the CLI."""

from collections.abc import Callable
from pathlib import Path

import erdify
import pytest

from erdify_studio import (
    OVERVIEW,
    DiagramContent,
    DuplicateKeyError,
    Layout,
    Problem,
    check_layout,
    diagram_contents,
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

ALL = frozenset({"core.customers", "billing.invoices", "billing.lines"})

#: What ``MODELS`` shows under ``group_by = "auto"``.
CONTENTS = {
    OVERVIEW: DiagramContent(ALL),
    "core": DiagramContent(frozenset({"core.customers"}), frozenset({"billing.invoices"})),
    "billing": DiagramContent(
        frozenset({"billing.invoices", "billing.lines"}), frozenset({"core.customers"})
    ),
}


def _project(root: Path, models: str = MODELS, studio: str = "") -> Path:
    (root / "pyproject.toml").write_text(
        f'[tool.erdify]\ninclude = ["**/models.py"]\n\n[tool.erdify-studio]\n{studio}'
    )
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models)
    return root


def _complete() -> Layout:
    layout = Layout()
    for name, content in CONTENTS.items():
        for i, key in enumerate(sorted(content.entities | content.foreign)):
            layout.set_position(name, key, i * 300, 0)
    return layout


# --- diagram_contents ------------------------------------------------------------


def test_group_diagrams_show_foreign_boxes_in_both_directions(tmp_path: Path) -> None:
    project = erdify.load_project(_project(tmp_path))
    assert diagram_contents(project.entities, "auto") == CONTENTS


def test_without_groups_only_the_overview_exists(tmp_path: Path) -> None:
    project = erdify.load_project(_project(tmp_path))
    assert diagram_contents(project.entities, "none") == {OVERVIEW: DiagramContent(ALL)}


def test_edges_within_a_group_give_no_foreign_box(tmp_path: Path) -> None:
    project = erdify.load_project(_project(tmp_path))
    # Grouped by module, all three tables share "shop.models".
    assert diagram_contents(project.entities, "module") == {
        OVERVIEW: DiagramContent(ALL),
        "shop.models": DiagramContent(ALL),
    }


def test_duplicate_layout_keys_are_refused(tmp_path: Path) -> None:
    models = MODELS.replace('__tablename__ = "lines"', '__tablename__ = "invoices"')
    project = erdify.load_project(_project(tmp_path, models))
    with pytest.raises(DuplicateKeyError, match="'Invoice' and 'Line'"):
        diagram_contents(project.entities, "auto")


# --- check_layout -----------------------------------------------------------------


def test_a_complete_layout_has_no_problems() -> None:
    assert check_layout(_complete(), CONTENTS) == []


def test_unplaced_entities_are_reported_per_diagram() -> None:
    layout = _complete()
    del layout.diagrams[OVERVIEW]["billing.lines"]
    del layout.diagrams["billing"]["billing.lines"]
    assert check_layout(layout, CONTENTS) == [
        Problem(OVERVIEW, "billing.lines", "unplaced"),
        Problem("billing", "billing.lines", "unplaced"),
    ]


@pytest.mark.parametrize(
    ("diagram", "key"), [("core", "billing.invoices"), ("billing", "core.customers")]
)
def test_unplaced_foreign_boxes_are_reported(diagram: str, key: str) -> None:
    layout = _complete()
    del layout.diagrams[diagram][key]
    assert check_layout(layout, CONTENTS) == [Problem(diagram, key, "foreign")]


def test_a_missing_diagram_reports_all_its_boxes() -> None:
    layout = _complete()
    del layout.diagrams["core"]
    assert check_layout(layout, CONTENTS) == [
        Problem("core", "billing.invoices", "foreign"),
        Problem("core", "core.customers", "unplaced"),
    ]


def test_stale_entries_and_diagrams_are_reported() -> None:
    layout = _complete()
    layout.set_position(OVERVIEW, "old_table", 0, 0)
    layout.set_position("core", "billing.lines", 0, 0)  # exists, but not shown in "core"
    layout.add_diagram("legacy")
    assert check_layout(layout, CONTENTS) == [
        Problem(OVERVIEW, "old_table", "stale_entry"),
        Problem("core", "billing.lines", "stale_entry"),
        Problem("legacy", None, "stale_diagram"),
    ]


def test_unchecked_keys_are_kept_but_not_required() -> None:
    layout = _complete()
    layout.set_position("core", "enum:Status", 0, 0)
    layout.set_position(OVERVIEW, "enum:Gone", 0, 0)
    assert check_layout(layout, CONTENTS, unchecked={"enum:Status", "enum:Other"}) == [
        Problem(OVERVIEW, "enum:Gone", "stale_entry"),
    ]


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
