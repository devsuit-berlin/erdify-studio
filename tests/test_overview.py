"""The overview model the canvas draws, and saving its positions.

``erdify_studio._overview`` builds the JSON of the studio's HTTP API (the contract
of the canvas); these tests pin that shape.
"""

import hashlib
import shutil
from pathlib import Path
from typing import Any

import erdify
import pytest

from erdify_studio import (
    OVERVIEW,
    Layout,
    check_project,
    dumps_layout,
    load_config,
    load_layout,
    place_project,
    save_layout,
)
from erdify_studio._errors import LayoutConflictError, PositionsError
from erdify_studio._overview import Overview, build_overview, layout_revision, save_overview
from erdify_studio._place import place_inputs

MODELS = """\
import enum
from typing import Optional

from sqlmodel import Field, SQLModel


class Status(str, enum.Enum):
    OPEN = "open"
    PAID = "paid"


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    __table_args__ = {"schema": "core"}
    id: int = Field(primary_key=True)
    email: str = Field(unique=True)


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"
    __table_args__ = {"schema": "billing"}
    id: int = Field(primary_key=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="core.customers.id")
    status: Status


class Line(SQLModel, table=True):
    __tablename__ = "lines"
    __table_args__ = {"schema": "billing"}
    id: int = Field(primary_key=True)
    invoice_id: int = Field(foreign_key="billing.invoices.id")
"""

ENTITIES = ("billing.invoices", "billing.lines", "core.customers")
ENUM = "enum:Status"


def _project(root: Path, models: str = MODELS, erdify_toml: str = "") -> Path:
    (root / "pyproject.toml").write_text(
        f'[tool.erdify]\ninclude = ["**/models.py"]\n{erdify_toml}\n[tool.erdify-studio]\n'
    )
    package = root / "shop"
    package.mkdir(exist_ok=True)
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models)
    return root


def _load(root: Path) -> tuple[erdify.Project, Any]:
    project = erdify.load_project(root, strict=True)
    return project, load_config(project.settings.pyproject)


def _overview(root: Path) -> Overview:
    project, config = _load(root)
    return build_overview(project, config, shown_path="erdify-layout.json")


def _box(overview: Overview, key: str) -> dict[str, Any]:
    return dict(next(box for box in overview["boxes"] if box["key"] == key))


def _placed(root: Path) -> None:
    project, config = _load(root)
    place_project(project, config)


# --- boxes ------------------------------------------------------------------------


def test_boxes_have_place_sizes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    project, _ = _load(root)
    sizes = place_inputs(project)[0]
    overview = _overview(root)
    assert {b["key"]: (b["width"], b["height"]) for b in overview["boxes"]} == {
        key: sizes[key] for key in (*ENTITIES, ENUM)
    }


def test_boxes_are_sorted_by_key(tmp_path: Path) -> None:
    overview = _overview(_project(tmp_path))
    assert [b["key"] for b in overview["boxes"]] == sorted([*ENTITIES, ENUM])


def test_rows_show_fields(tmp_path: Path) -> None:
    box = _box(_overview(_project(tmp_path)), "billing.invoices")
    assert (box["kind"], box["title"]) == ("entity", "billing.invoices")
    assert box["rows"][1] == {
        "name": "customer_id",
        "type": "int",
        "pk": False,
        "fk": True,
        "uk": False,
        "nullable": True,
    }


def test_rows_show_primary_and_unique_keys(tmp_path: Path) -> None:
    box = _box(_overview(_project(tmp_path)), "core.customers")
    assert [(r["name"], r["pk"], r["uk"], r["nullable"]) for r in box["rows"]] == [
        ("id", True, False, False),
        ("email", False, True, False),
    ]


def test_enum_box_lists_its_values(tmp_path: Path) -> None:
    box = _box(_overview(_project(tmp_path)), ENUM)
    assert (box["kind"], box["title"], box["rows"]) == (
        "enum",
        "Status",
        [{"name": "OPEN"}, {"name": "PAID"}],  # erdify draws the member names
    )


def test_enum_links_connect_an_enum_to_its_users(tmp_path: Path) -> None:
    overview = _overview(_project(tmp_path))
    assert overview["enumLinks"] == [{"enum": ENUM, "entity": "billing.invoices"}]


def test_metrics_are_the_place_constants(tmp_path: Path) -> None:
    overview = _overview(_project(tmp_path))
    assert overview["metrics"] == {"charWidth": 8, "padding": 32, "header": 32, "row": 22}


def test_paths_are_passed_for_the_ui_texts(tmp_path: Path) -> None:
    overview = _overview(_project(tmp_path))
    assert (overview["layoutPath"], overview["projectPath"]) == (
        "erdify-layout.json",
        str(tmp_path),
    )


# --- edges ------------------------------------------------------------------------


def test_edges_use_layout_keys(tmp_path: Path) -> None:
    root = _project(tmp_path)
    project, _ = _load(root)
    source = next(e for e in erdify.diagram_edges(project.entities) if e.label == "customer_id")
    edge = next(e for e in _overview(root)["edges"] if e["to"] == "core.customers")
    assert edge == {
        "from": "billing.invoices",
        "to": "core.customers",
        "fromEnd": {"optional": source.from_end.optional, "many": source.from_end.many},
        "toEnd": {"optional": True, "many": False},  # nullable column: the parent is optional
        "kind": "foreign_key",
        "label": "customer_id",
    }


def test_edges_follow_erdify_order(tmp_path: Path) -> None:
    root = _project(tmp_path)
    project, _ = _load(root)
    labels = [e.label for e in erdify.diagram_edges(project.entities)]
    assert [e["label"] for e in _overview(root)["edges"]] == labels


def test_no_edges_without_relationships(tmp_path: Path) -> None:
    overview = _overview(_project(tmp_path, erdify_toml="no_relationships = true\n"))
    assert overview["edges"] == []


# --- positions and pending changes ------------------------------------------------


def test_unplaced_boxes_are_new_at_the_place_positions(tmp_path: Path) -> None:
    root = _project(tmp_path)
    layout = Layout()
    layout.set_position(OVERVIEW, "core.customers", 100, 200)
    save_layout(layout, root / "erdify-layout.json")
    overview = _overview(root)

    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    _placed(copy)
    expected = load_layout(copy / "erdify-layout.json").diagrams[OVERVIEW]

    assert {b["key"]: ((b["x"], b["y"]), b["new"]) for b in overview["boxes"]} == {
        key: (expected[key], key != "core.customers") for key in (*ENTITIES, ENUM)
    }


def test_new_boxes_are_counted_as_placed(tmp_path: Path) -> None:
    root = _project(tmp_path)
    layout = Layout()
    layout.set_position(OVERVIEW, "core.customers", 100, 200)
    save_layout(layout, root / "erdify-layout.json")
    assert _overview(root)["pending"]["placed"] == 3


def test_up_to_date_layout_has_nothing_pending(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    assert _overview(root)["pending"] == {"placed": 0, "groupChanges": 0, "created": False}


def test_group_changes_are_counted(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    layout = load_layout(path)
    layout.set_position("core", "gone.table", 0, 0)
    save_layout(layout, path)
    assert _overview(root)["pending"] == {"placed": 0, "groupChanges": 1, "created": False}


def test_a_hand_formatted_file_is_not_pending(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    path.write_text(dumps_layout(load_layout(path)).replace("\n", "\n\n  "))
    assert _overview(root)["pending"] == {"placed": 0, "groupChanges": 0, "created": False}


def test_no_layout_file_is_pending_creation(tmp_path: Path) -> None:
    overview = _overview(_project(tmp_path))
    assert (overview["pending"]["created"], overview["revision"]) == (True, None)


def test_revision_is_the_hash_of_the_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    assert _overview(root)["revision"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_layout_revision_of_a_missing_file_is_none(tmp_path: Path) -> None:
    assert layout_revision(tmp_path / "missing.json") is None


def test_building_does_not_write_the_layout_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _overview(root)
    assert not (root / "erdify-layout.json").exists()


def test_empty_project_with_allow_empty(tmp_path: Path) -> None:
    overview = _overview(_project(tmp_path, models="", erdify_toml="allow_empty = true\n"))
    assert (overview["boxes"], overview["edges"], overview["enumLinks"]) == ([], [], [])


def test_check_still_reports_what_the_overview_placed(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _overview(root)
    project, config = _load(root)
    assert check_project(project, config) is None


@pytest.mark.parametrize("key", ENTITIES)
def test_every_entity_is_a_box(tmp_path: Path, key: str) -> None:
    assert _box(_overview(_project(tmp_path)), key)["kind"] == "entity"


# --- save -------------------------------------------------------------------------


def _positions(keys: tuple[str, ...] = (*ENTITIES, ENUM)) -> dict[str, object]:
    return {key: [i * 400, 0] for i, key in enumerate(keys)}


def _save(root: Path, positions: object, revision: str | None = None) -> str | None:
    project, config = _load(root)
    return save_overview(project, config, positions, revision)


def test_save_writes_the_overview_positions(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _save(root, _positions())
    overview = load_layout(root / "erdify-layout.json").diagrams[OVERVIEW]
    assert overview == {key: (i * 400, 0) for i, key in enumerate((*ENTITIES, ENUM))}


def test_after_save_check_passes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _save(root, _positions())
    project, config = _load(root)
    assert check_project(project, config) == []


def test_save_returns_the_new_revision(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert _save(root, _positions()) == layout_revision(root / "erdify-layout.json")


def test_save_places_the_group_diagrams(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _save(root, _positions())
    diagrams = load_layout(root / "erdify-layout.json").diagrams
    assert set(diagrams) == {OVERVIEW, "billing", "core"}


def test_save_drops_stale_entries(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    layout = load_layout(path)
    layout.set_position("core", "gone.table", 0, 0)
    save_layout(layout, path)
    _save(root, _positions(), layout_revision(path))
    assert "gone.table" not in load_layout(path).diagrams["core"]


def test_save_rounds_floats(tmp_path: Path) -> None:
    root = _project(tmp_path)
    positions = _positions()
    positions["core.customers"] = [10.6, 20.4]
    _save(root, positions)
    overview = load_layout(root / "erdify-layout.json").diagrams[OVERVIEW]
    assert overview["core.customers"] == (11, 20)


def _without(key: str) -> dict[str, object]:
    positions = _positions()
    del positions[key]
    return positions


def _with(key: str, value: object) -> dict[str, object]:
    return {**_positions(), key: value}


@pytest.mark.parametrize(
    ("positions", "message"),
    [
        (_without("core.customers"), "'core.customers'"),
        (_with("gone.table", [0, 0]), "'gone.table'"),
        (_with("core.customers", [1]), "'core.customers'"),
        (_with("core.customers", [1, 2, 3]), "'core.customers'"),
        (_with("core.customers", ["1", 2]), "'core.customers'"),
        (_with("core.customers", [True, 2]), "'core.customers'"),
        (_with("core.customers", [float("nan"), 0]), "'core.customers'"),
        (_with("core.customers", [10**10, 0]), "'core.customers'"),
        (_with("core.customers", {"x": 1, "y": 2}), "'core.customers'"),
        ([["core.customers", [0, 0]]], "positions"),
        (None, "positions"),
    ],
    ids=[
        "missing",
        "unknown",
        "short",
        "long",
        "string",
        "bool",
        "nan",
        "huge",
        "object",
        "list",
        "none",
    ],
)
def test_save_refuses_bad_positions(tmp_path: Path, positions: object, message: str) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    before = path.read_bytes()
    with pytest.raises(PositionsError, match=message):
        _save(root, positions, layout_revision(path))
    assert path.read_bytes() == before


def test_save_conflicts_when_the_file_changed(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    revision = layout_revision(path)
    path.write_text(path.read_text() + "\n")
    before = path.read_bytes()
    with pytest.raises(LayoutConflictError, match="erdify-layout.json"):
        _save(root, _positions(), revision)
    assert path.read_bytes() == before


def test_save_conflicts_when_the_file_was_created_meanwhile(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    with pytest.raises(LayoutConflictError):
        _save(root, _positions(), None)


def test_a_second_save_needs_the_new_revision(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = _save(root, _positions())
    assert _save(root, _with("core.customers", [5, 5]), first) is not None
    with pytest.raises(LayoutConflictError):
        _save(root, _positions(), first)


def test_save_of_an_empty_project_creates_the_file(tmp_path: Path) -> None:
    root = _project(tmp_path, models="", erdify_toml="allow_empty = true\n")
    _save(root, {})
    assert load_layout(root / "erdify-layout.json").diagrams == {OVERVIEW: {}}


def test_box_width_fits_each_drawn_row(tmp_path: Path) -> None:
    """Badges, name, a two-character gap, type and ``?`` for nullable fit the box."""
    long = MODELS.replace(
        "    email: str = Field(unique=True)\n",
        "    email: str = Field(unique=True)\n"
        "    referred_by_id: Optional[int] = Field(default=None, "
        'foreign_key="core.customers.id")\n',
    )
    overview = _overview(_project(tmp_path, models=long))
    char, padding = overview["metrics"]["charWidth"], overview["metrics"]["padding"]
    box = _box(overview, "core.customers")
    widest = max(
        6 + len(r["name"]) + 2 + len(r["type"]) + (1 if r["nullable"] else 0) for r in box["rows"]
    )
    assert box["width"] - padding >= widest * char
