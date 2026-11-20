"""The ``place --auto`` command: placing new boxes, dropping stale entries, the CLI."""

from itertools import combinations
from pathlib import Path

import erdify
import pytest

from erdify_studio import (
    OVERVIEW,
    DuplicateKeyError,
    Layout,
    LayoutError,
    PlaceResult,
    Position,
    Problem,
    ProjectError,
    check_project,
    load_config,
    load_layout,
    place_project,
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

#: Smallest box: the minimum width and a header plus one field row (``id``).
MIN_WIDTH, MIN_HEIGHT = 200, 54
#: Height of one field row.
ROW = 22
GAP = 40
#: Largest absolute coordinate of a position.
MAX_COORDINATE = 10**9


def _project(root: Path, models: str = MODELS, studio: str = "", erdify: str = "") -> Path:
    (root / "pyproject.toml").write_text(
        f'[tool.erdify]\ninclude = ["**/models.py"]\n{erdify}\n[tool.erdify-studio]\n{studio}'
    )
    package = root / "shop"
    package.mkdir(exist_ok=True)
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models)
    return root


def _place(root: Path, layout: Layout | None = None) -> PlaceResult:
    project = erdify.load_project(root, strict=True)
    config = load_config(project.settings.pyproject)
    if layout is not None:
        save_layout(layout, config.layout)
    return place_project(project, config)


def _check(root: Path) -> list[Problem] | None:
    project = erdify.load_project(root, strict=True)
    return check_project(project, load_config(project.settings.pyproject))


def _tables(names: list[str], links: dict[str, str] | None = None) -> str:
    """SQLModel source: one table per name with an ``id``; ``links`` child -> parent."""
    lines = ["from sqlmodel import Field, SQLModel", ""]
    for name in names:
        lines += [
            f"class {name.title().replace('_', '')}(SQLModel, table=True):",
            f'    __tablename__ = "{name}"',
            "    id: int = Field(primary_key=True)",
        ]
        if links and name in links:
            lines.append(f'    parent_id: int = Field(foreign_key="{links[name]}.id")')
        lines.append("")
    return "\n".join(lines)


def _apart(a: Position, b: Position, height_a: int, height_b: int) -> bool:
    """True when two boxes of the minimum width keep ``GAP`` between them."""
    above = height_a if a[1] <= b[1] else height_b
    return abs(a[0] - b[0]) >= MIN_WIDTH + GAP or abs(a[1] - b[1]) >= above + GAP


def _no_overlaps(positions: dict[str, Position], links: dict[str, str]) -> bool:
    """True when no two boxes come closer than ``GAP``; a linked table has a second row."""
    height = {key: MIN_HEIGHT + (ROW if key in links else 0) for key in positions}
    return all(
        _apart(positions[a], positions[b], height[a], height[b])
        for a, b in combinations(sorted(positions), 2)
    )


# --- first run, determinism ------------------------------------------------------


@pytest.mark.parametrize("group_by", ["auto", "none", "module"])
def test_first_run_creates_a_layout_that_passes_check(tmp_path: Path, group_by: str) -> None:
    root = _project(tmp_path, studio=f"group_by = {group_by!r}\n")
    result = _place(root)
    assert result.created
    assert result.changed
    assert load_layout(root / "erdify-layout.json") == result.layout
    assert _check(root) == []


def test_first_run_places_every_box_of_every_diagram(tmp_path: Path) -> None:
    result = _place(_project(tmp_path))
    assert {d: set(p) for d, p in result.layout.diagrams.items()} == {
        OVERVIEW: set(ALL),
        "billing": set(ALL),
        "core": {"billing.invoices", "core.customers"},
    }
    assert result.placed == tuple(
        (d, k) for d in sorted(result.layout.diagrams) for k in sorted(result.layout.diagrams[d])
    )


def test_running_twice_gives_identical_bytes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _place(root)
    first = (root / "erdify-layout.json").read_bytes()
    result = _place(root)
    assert not result.changed
    assert (root / "erdify-layout.json").read_bytes() == first


def test_the_same_input_gives_the_same_layout(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = _place(_project(tmp_path / "a"))
    b = _place(_project(tmp_path / "b"))
    assert a.layout == b.layout


def test_an_unchanged_layout_file_is_not_rewritten(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _place(root)
    path = root / "erdify-layout.json"
    # Valid but not in the written formatting: left as it is.
    compact = path.read_text().replace("\n", "").replace("  ", "")
    path.write_text(compact)
    assert not _place(root).changed
    assert path.read_text() == compact


@pytest.mark.parametrize("content", ["", "\n"])
def test_an_empty_layout_file_counts_as_none(tmp_path: Path, content: str) -> None:
    root = _project(tmp_path)
    (root / "erdify-layout.json").write_text(content)
    assert _place(root).created
    assert _check(root) == []


def test_an_empty_project_with_allow_empty_gets_an_empty_overview(tmp_path: Path) -> None:
    root = _project(tmp_path, models="", erdify="allow_empty = true\n")
    result = _place(root)
    assert result.layout.diagrams == {OVERVIEW: {}}
    assert (root / "erdify-layout.json").exists()


def test_duplicate_layout_keys_are_refused_before_writing(tmp_path: Path) -> None:
    models = MODELS.replace('__tablename__ = "lines"', '__tablename__ = "invoices"')
    root = _project(tmp_path, models)
    with pytest.raises(DuplicateKeyError, match="'Invoice' and 'Line'"):
        _place(root)
    assert not (root / "erdify-layout.json").exists()


def test_no_room_within_the_coordinate_limit_is_an_error(tmp_path: Path) -> None:
    # A box at the limit: the grid right of the diagram starts past it.
    root = _project(tmp_path, studio='group_by = "none"\n', erdify="no_relationships = true\n")
    layout = Layout()
    layout.set_position(OVERVIEW, "billing.lines", MAX_COORDINATE - 300, 0)
    with pytest.raises(LayoutError, match="no room for a new box"):
        _place(root, layout)


def test_the_grid_wraps_before_the_coordinate_limit(tmp_path: Path) -> None:
    # Only two columns fit right of the fixed box: the third box starts a new row.
    root = _project(tmp_path, models=_tables(["a", "b", "c", "d"]))
    layout = Layout()
    x = MAX_COORDINATE - 700
    layout.set_position(OVERVIEW, "a", x - MIN_WIDTH - GAP, 0)
    positions = _place(root, layout).layout.diagrams[OVERVIEW]
    assert [positions[k] for k in "bcd"] == [(x, 0), (x + 280, 0), (x, 120)]


def test_a_neighbour_near_the_limit_gets_a_spot_inside_it(tmp_path: Path) -> None:
    root = _project(tmp_path, studio='group_by = "none"\n')
    layout = Layout()
    layout.set_position(OVERVIEW, "core.customers", MAX_COORDINATE - 300, 0)
    positions = _place(root, layout).layout.diagrams[OVERVIEW]
    # Not right of it (past the limit) but below it.
    assert positions["billing.invoices"] == (MAX_COORDINATE - 300, MIN_HEIGHT + GAP)


def test_a_project_without_entities_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="no entities found"):
        _place(_project(tmp_path, models=""))


# --- placed boxes stay, stale entries go ------------------------------------------


def test_placed_boxes_never_move(tmp_path: Path) -> None:
    root = _project(tmp_path, studio='group_by = "none"\n')
    layout = Layout()
    layout.set_position(OVERVIEW, "billing.invoices", 50, 70)
    layout.set_position(OVERVIEW, "core.customers", 300, 70)
    result = _place(root, layout)
    assert result.placed == ((OVERVIEW, "billing.lines"),)
    positions = result.layout.diagrams[OVERVIEW]
    assert positions["billing.invoices"] == (50, 70)
    assert positions["core.customers"] == (300, 70)


def test_stale_entries_and_diagrams_are_removed(tmp_path: Path) -> None:
    root = _project(tmp_path, studio='group_by = "none"\n')
    layout = Layout()
    for i, key in enumerate(ALL):
        layout.set_position(OVERVIEW, key, i * 300, 0)
    layout.set_position(OVERVIEW, "old_table", 0, 500)
    layout.set_position("gone", "core.customers", 0, 0)
    result = _place(root, layout)
    assert result.removed == ((OVERVIEW, "old_table"),)
    assert result.removed_diagrams == ("gone",)
    assert result.placed == ()
    assert set(result.layout.diagrams) == {OVERVIEW}
    assert _check(root) == []


def test_positions_of_existing_enums_are_kept_but_none_are_added(tmp_path: Path) -> None:
    root = _project(tmp_path, studio='group_by = "none"\n')
    layout = Layout()
    layout.set_position(OVERVIEW, "enum:Status", 900, 900)
    layout.set_position(OVERVIEW, "enum:Gone", 0, 0)
    result = _place(root, layout)
    assert result.removed == ((OVERVIEW, "enum:Gone"),)
    assert result.layout.diagrams[OVERVIEW]["enum:Status"] == (900, 900)
    assert "enum:Status" not in {key for _, key in result.placed}


# --- where new boxes go -------------------------------------------------------------


def test_a_new_box_goes_right_of_its_placed_neighbour(tmp_path: Path) -> None:
    root = _project(tmp_path, studio='group_by = "none"\n')
    layout = Layout()
    layout.set_position(OVERVIEW, "core.customers", 1000, 1000)
    positions = _place(root, layout).layout.diagrams[OVERVIEW]
    # invoices next to customers, then lines next to invoices.
    x, y = positions["billing.invoices"]
    assert y == 1000
    assert 1000 + MIN_WIDTH + GAP <= x <= 1000 + 2 * MIN_WIDTH
    assert positions["billing.lines"][1] == 1000
    assert positions["billing.lines"][0] >= x + MIN_WIDTH + GAP


def test_the_first_placed_neighbour_by_key_wins(tmp_path: Path) -> None:
    root = _project(tmp_path, studio='group_by = "none"\n')
    layout = Layout()
    layout.set_position(OVERVIEW, "core.customers", 1000, 1000)
    layout.set_position(OVERVIEW, "billing.lines", 0, 0)
    x, y = _place(root, layout).layout.diagrams[OVERVIEW]["billing.invoices"]
    assert (x > 0, y) == (True, 0)


def test_a_new_box_without_placed_neighbours_goes_right_of_the_diagram(tmp_path: Path) -> None:
    root = _project(tmp_path, models=_tables(["a", "b", "c"]))
    layout = Layout()
    layout.set_position(OVERVIEW, "a", -100, 300)
    layout.set_position(OVERVIEW, "b", 500, 200)
    result = _place(root, layout)
    assert result.layout.diagrams[OVERVIEW]["c"] == (500 + MIN_WIDTH + GAP, 200)


def test_a_group_diagram_is_anchored_by_its_own_entities(tmp_path: Path) -> None:
    result = _place(_project(tmp_path))
    assert result.layout.diagrams["core"]["core.customers"] == (0, 0)


def test_foreign_boxes_go_next_to_own_entities_only(tmp_path: Path) -> None:
    # In "core", both foreign boxes connect only through billing.invoices -> core:
    # invoices sits next to core.customers, lines (linked to invoices) is no
    # foreign box of core at all; with two foreign boxes each sits next to the own one.
    models = (
        MODELS
        + """

class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    __table_args__ = {"schema": "billing"}
    id: int = Field(primary_key=True)
    customer_id: int = Field(foreign_key="customers.id")
    invoice_id: int = Field(foreign_key="invoices.id")
"""
    )
    root = _project(tmp_path, models)
    layout = Layout()
    layout.set_position("core", "core.customers", 1000, 1000)
    positions = _place(root, layout).layout.diagrams["core"]
    # Right of and below core.customers (54 high), not chained off each other.
    assert positions["billing.invoices"] == (1000 + MIN_WIDTH + GAP, 1000)
    assert positions["billing.payments"] == (1000, 1000 + MIN_HEIGHT + GAP)


def test_without_relationships_new_boxes_go_to_the_grid(tmp_path: Path) -> None:
    root = _project(tmp_path, erdify="no_relationships = true\n", studio='group_by = "none"\n')
    layout = Layout()
    layout.set_position(OVERVIEW, "core.customers", 0, 0)
    result = _place(root, layout)
    # invoices lands on the grid origin; lines takes the next grid column (520),
    # not a spot next to invoices (480).
    assert [result.layout.diagrams[OVERVIEW][k] for k in ("billing.invoices", "billing.lines")] == [
        (MIN_WIDTH + GAP, 0),
        (MIN_WIDTH + GAP + 280, 0),
    ]


def test_a_crowded_neighbour_still_gives_no_overlaps(tmp_path: Path) -> None:
    # Six spokes around one hub: four fit next to it, the rest go elsewhere.
    spokes = [f"spoke{i}" for i in range(6)]
    models = _tables(["hub", *spokes], {spoke: "hub" for spoke in spokes})
    root = _project(tmp_path, models=models)
    layout = Layout()
    layout.set_position(OVERVIEW, "hub", 0, 0)
    positions = _place(root, layout).layout.diagrams[OVERVIEW]
    assert len(positions) == 7
    assert _no_overlaps(positions, {spoke: "hub" for spoke in spokes})
    assert _check(root) == []


def test_many_new_boxes_do_not_overlap(tmp_path: Path) -> None:
    names = [f"t{i:02}" for i in range(30)]
    links = {name: names[i // 3] for i, name in enumerate(names) if i % 4 and i // 3 != i}
    root = _project(tmp_path, models=_tables(names, links))
    positions = _place(root).layout.diagrams[OVERVIEW]
    assert _no_overlaps(positions, links)


def test_a_self_reference_is_no_neighbour(tmp_path: Path) -> None:
    root = _project(tmp_path, models=_tables(["node"], {"node": "node"}))
    assert _place(root).layout.diagrams[OVERVIEW] == {"node": (0, 0)}


# --- CLI ----------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return _project(tmp_path, studio='group_by = "none"\n')


def test_cli_creates_the_layout_and_check_passes(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["place", "--auto"]) == 0
    assert capsys.readouterr() == ("erdify-layout.json: created, placed 3 boxes\n", "")
    assert main(["check"]) == 0


def test_cli_reports_removals_and_a_summary(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    layout = Layout()
    layout.set_position(OVERVIEW, "core.customers", 0, 0)
    layout.set_position(OVERVIEW, "old_table", 0, 0)
    layout.set_position("gone", "a", 0, 0)
    layout.set_position("gone2", "a", 0, 0)
    save_layout(layout, project / "erdify-layout.json")
    assert main(["place", "--auto", str(project)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "erdify-layout.json: removed stale diagram 'gone'",
        "erdify-layout.json: removed stale diagram 'gone2'",
        "erdify-layout.json: diagram '_overview': removed stale entry 'old_table'",
        "erdify-layout.json: updated, placed 2 boxes, removed 1 stale entry, "
        "removed 2 stale diagrams",
    ]


def test_cli_up_to_date(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["place", "--auto"]) == 0
    capsys.readouterr()
    assert main(["place", "--auto"]) == 0
    assert capsys.readouterr() == ("erdify-layout.json: up to date\n", "")


def test_cli_place_needs_auto(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["place"])
    assert exc.value.code == 2
    assert "--auto" in capsys.readouterr().err


def test_cli_refuses_to_overwrite_a_broken_layout_file(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = project / "erdify-layout.json"
    path.write_text("<<<<<<< HEAD\n")
    assert main(["place", "--auto"]) == 2
    assert "not valid JSON" in capsys.readouterr().err
    assert path.read_text() == "<<<<<<< HEAD\n"


def test_cli_parse_error_exits_two_and_writes_nothing(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "shop" / "models.py").write_text("class Broken(:\n")
    assert main(["place", "--auto"]) == 2
    assert not (project / "erdify-layout.json").exists()
