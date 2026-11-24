"""The diagrams the canvas draws, and saving their positions.

``erdify_studio._diagrams`` builds the JSON of the studio's HTTP API (the contract
of the canvas); these tests pin that shape.
"""

import dataclasses
import hashlib
import shutil
from pathlib import Path
from typing import Any

import erdify
import pytest

from erdify_studio import (
    DEFAULT_GROUP,
    OVERVIEW,
    DiagramColors,
    Layout,
    check_project,
    dumps_layout,
    load_config,
    load_layout,
    place_project,
    save_layout,
)
from erdify_studio._diagrams import (
    DiagramJson,
    Diagrams,
    build_diagrams,
    layout_revision,
    model_fingerprint,
    save_diagrams,
)
from erdify_studio._errors import LayoutConflictError, PositionsError
from erdify_studio._place import name_box_size, place_inputs

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


def _project(
    root: Path, models: str = MODELS, erdify_toml: str = "", studio_toml: str = ""
) -> Path:
    (root / "pyproject.toml").write_text(
        f'[tool.erdify]\ninclude = ["**/models.py"]\n{erdify_toml}\n'
        f"[tool.erdify-studio]\n{studio_toml}"
    )
    package = root / "shop"
    package.mkdir(exist_ok=True)
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models)
    return root


def _load(root: Path) -> tuple[erdify.Project, Any]:
    project = erdify.load_project(root, strict=True)
    return project, load_config(project.settings.pyproject)


def _payload(root: Path) -> Diagrams:
    project, config = _load(root)
    return build_diagrams(project, config, shown_path="erdify-layout.json")


def _diagram(payload: Diagrams, name: str = OVERVIEW) -> DiagramJson:
    return next(d for d in payload["diagrams"] if d["name"] == name)


def _box(payload: Diagrams, key: str) -> dict[str, Any]:
    return dict(payload["boxes"][key])


def _placed(root: Path) -> None:
    project, config = _load(root)
    place_project(project, config)


def _layout_with(root: Path, positions: dict[str, dict[str, tuple[int, int]]]) -> None:
    layout = Layout()
    for diagram, boxes in positions.items():
        for key, (x, y) in boxes.items():
            layout.set_position(diagram, key, x, y)
    save_layout(layout, root / "erdify-layout.json")


# --- boxes ------------------------------------------------------------------------


def test_boxes_have_place_sizes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    project, _ = _load(root)
    sizes = place_inputs(project)[0]
    payload = _payload(root)
    assert {k: (b["width"], b["height"]) for k, b in payload["boxes"].items()} == {
        key: sizes[key] for key in (*ENTITIES, ENUM)
    }


def test_box_definitions_are_sent_once(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    assert sorted(payload["boxes"]) == _diagram(payload)["own"] == sorted([*ENTITIES, ENUM])


def test_rows_show_fields(tmp_path: Path) -> None:
    box = _box(_payload(_project(tmp_path)), "billing.invoices")
    assert (box["kind"], box["title"], box["group"]) == ("entity", "billing.invoices", "billing")
    assert box["rows"][1] == {
        "name": "customer_id",
        "type": "int",
        "pk": False,
        "fk": True,
        "uk": False,
        "nullable": True,
    }


def test_rows_show_primary_and_unique_keys(tmp_path: Path) -> None:
    box = _box(_payload(_project(tmp_path)), "core.customers")
    assert [(r["name"], r["pk"], r["uk"], r["nullable"]) for r in box["rows"]] == [
        ("id", True, False, False),
        ("email", False, True, False),
    ]


def test_enum_box_lists_its_values(tmp_path: Path) -> None:
    box = _box(_payload(_project(tmp_path)), ENUM)
    assert (box["kind"], box["title"], box["group"], box["rows"]) == (
        "enum",
        "Status",
        None,
        [{"name": "OPEN"}, {"name": "PAID"}],  # erdify draws the member names
    )


def test_enum_links_connect_an_enum_to_its_users(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    assert _diagram(payload)["enumLinks"] == [{"enum": ENUM, "entity": "billing.invoices"}]


def test_metrics_are_the_place_constants(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    assert payload["metrics"] == {"charWidth": 8, "padding": 32, "header": 32, "row": 22}


def test_paths_are_passed_for_the_ui_texts(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    assert (payload["layoutPath"], payload["projectPath"]) == ("erdify-layout.json", str(tmp_path))


@pytest.mark.parametrize("key", ENTITIES)
def test_every_entity_is_a_box(tmp_path: Path, key: str) -> None:
    assert _box(_payload(_project(tmp_path)), key)["kind"] == "entity"


# --- diagrams ---------------------------------------------------------------------


def test_diagram_order_and_labels(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    assert [(d["name"], d["label"]) for d in payload["diagrams"]] == [
        (OVERVIEW, "Overview"),
        ("billing", "billing"),
        ("core", "core"),
    ]


def test_the_default_group_is_last_and_ungrouped(tmp_path: Path) -> None:
    models = MODELS + (
        '\n\nclass Audit(SQLModel, table=True):\n    __tablename__ = "audit"\n'
        "    id: int = Field(primary_key=True)\n"
    )
    root = _project(tmp_path, models, studio_toml='group_by = "schema"\n')
    payload = _payload(root)
    assert [(d["name"], d["label"]) for d in payload["diagrams"]][-1] == (
        DEFAULT_GROUP,
        "Ungrouped",
    )
    assert payload["boxes"]["audit"]["group"] == DEFAULT_GROUP


def test_group_by_none_has_only_the_overview(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, studio_toml='group_by = "none"\n'))
    assert [d["name"] for d in payload["diagrams"]] == [OVERVIEW]
    assert {b["group"] for b in payload["boxes"].values()} == {None}


def test_a_group_named_overview_is_its_own_diagram(tmp_path: Path) -> None:
    root = _project(tmp_path, MODELS.replace('"schema": "core"', '"schema": "overview"'))
    names = [d["name"] for d in _payload(root)["diagrams"]]
    assert names == [OVERVIEW, "billing", "overview"]


def test_group_diagram_content(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    core, billing = _diagram(payload, "core"), _diagram(payload, "billing")
    assert (core["own"], core["foreign"]) == (["core.customers"], ["billing.invoices"])
    assert (billing["own"], billing["foreign"]) == (
        ["billing.invoices", "billing.lines", ENUM],
        ["core.customers"],
    )
    assert _diagram(payload)["foreign"] == []


def test_foreign_sizes_are_name_box_sizes(tmp_path: Path) -> None:
    core = _diagram(_payload(_project(tmp_path)), "core")
    assert core["foreignSizes"] == {"billing.invoices": list(name_box_size("billing.invoices"))}


def test_group_diagram_edges(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    pairs = {
        name: [(e["from"], e["to"]) for e in _diagram(payload, name)["edges"]]
        for name in ("core", "billing")
    }
    assert pairs["core"] == [("billing.invoices", "core.customers")]
    assert sorted(pairs["billing"]) == [
        ("billing.invoices", "core.customers"),
        ("billing.lines", "billing.invoices"),
    ]


def test_edges_between_foreign_boxes_are_not_drawn(tmp_path: Path) -> None:
    models = MODELS + (
        "\n\nclass Audit(SQLModel, table=True):\n"
        '    __tablename__ = "events"\n'
        '    __table_args__ = {"schema": "audit"}\n'
        "    id: int = Field(primary_key=True)\n"
        '    customer_id: int = Field(foreign_key="core.customers.id")\n'
        '    invoice_id: int = Field(foreign_key="billing.invoices.id")\n'
    )
    audit = _diagram(_payload(_project(tmp_path, models)), "audit")
    assert audit["foreign"] == ["billing.invoices", "core.customers"]
    assert sorted((e["from"], e["to"]) for e in audit["edges"]) == [
        ("audit.events", "billing.invoices"),
        ("audit.events", "core.customers"),
    ]


def test_enum_links_per_diagram(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    assert _diagram(payload, "core")["enumLinks"] == []
    assert _diagram(payload, "billing")["enumLinks"] == [
        {"enum": ENUM, "entity": "billing.invoices"}
    ]


# --- edges ------------------------------------------------------------------------


def test_edges_use_layout_keys(tmp_path: Path) -> None:
    root = _project(tmp_path)
    project, _ = _load(root)
    source = next(e for e in erdify.diagram_edges(project.entities) if e.label == "customer_id")
    edge = next(e for e in _diagram(_payload(root))["edges"] if e["to"] == "core.customers")
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
    assert [e["label"] for e in _diagram(_payload(root))["edges"]] == labels


def test_no_edges_without_relationships(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, erdify_toml="no_relationships = true\n"))
    assert [d["edges"] for d in payload["diagrams"]] == [[], [], []]


# --- positions and pending changes ------------------------------------------------


def test_unplaced_boxes_are_new_at_the_place_positions(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _layout_with(root, {OVERVIEW: {"core.customers": (100, 200)}})
    payload = _payload(root)

    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    _placed(copy)
    expected = load_layout(copy / "erdify-layout.json")

    for diagram in payload["diagrams"]:
        assert diagram["positions"] == {
            k: list(v) for k, v in expected.diagrams[diagram["name"]].items()
        }
    overview = _diagram(payload)
    assert overview["new"] == sorted(k for k in (*ENTITIES, ENUM) if k != "core.customers")
    assert _diagram(payload, "core")["new"] == ["billing.invoices", "core.customers"]


def test_positions_are_per_diagram(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    layout = load_layout(path)
    layout.set_position(OVERVIEW, "core.customers", 0, 0)
    layout.set_position("core", "core.customers", 500, 40)
    save_layout(layout, path)
    payload = _payload(root)
    assert _diagram(payload)["positions"]["core.customers"] == [0, 0]
    assert _diagram(payload, "core")["positions"]["core.customers"] == [500, 40]


def test_new_boxes_are_counted_per_diagram(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _layout_with(root, {OVERVIEW: {"core.customers": (100, 200)}})
    # overview 3, billing 4 (3 own + 1 foreign), core 2
    assert _payload(root)["pending"] == {
        "placed": 9,
        "diagrams": 3,
        "dropped": 0,
        "created": False,
        "svgs": 0,
    }


def test_up_to_date_layout_has_nothing_pending(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    assert _payload(root)["pending"] == {
        "placed": 0,
        "diagrams": 0,
        "dropped": 0,
        "created": False,
        "svgs": 0,
    }


def test_stale_entries_and_diagrams_are_counted_as_dropped(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    layout = load_layout(path)
    layout.set_position("core", "gone.table", 0, 0)
    layout.set_position("gone", "core.customers", 0, 0)
    save_layout(layout, path)
    assert _payload(root)["pending"] == {
        "placed": 0,
        "diagrams": 0,
        "dropped": 2,
        "created": False,
        "svgs": 0,
    }


def test_a_hand_formatted_file_is_not_pending(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    path.write_text(dumps_layout(load_layout(path)).replace("\n", "\n\n  "))
    assert _payload(root)["pending"] == {
        "placed": 0,
        "diagrams": 0,
        "dropped": 0,
        "created": False,
        "svgs": 0,
    }


def test_no_layout_file_is_pending_creation(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    assert (payload["pending"]["created"], payload["revision"]) == (True, None)
    assert all(sorted(d["positions"]) == d["new"] for d in payload["diagrams"])


def test_revision_is_the_hash_of_the_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    assert _payload(root)["revision"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_layout_revision_of_a_missing_file_is_none(tmp_path: Path) -> None:
    assert layout_revision(tmp_path / "missing.json") is None


def test_building_does_not_write_the_layout_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _payload(root)
    assert not (root / "erdify-layout.json").exists()


def test_empty_project_with_allow_empty(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path, models="", erdify_toml="allow_empty = true\n"))
    overview = _diagram(payload)
    assert (payload["boxes"], overview["edges"], overview["enumLinks"]) == ({}, [], [])


def test_check_still_reports_what_was_placed_in_the_payload(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _payload(root)
    project, config = _load(root)
    assert check_project(project, config) is None


# --- save -------------------------------------------------------------------------


def _positions(keys: tuple[str, ...] = (*ENTITIES, ENUM)) -> dict[str, object]:
    return {key: [i * 400, 0] for i, key in enumerate(keys)}


def _body(root: Path) -> dict[str, object]:
    """Every diagram's positions as the page would send them unchanged."""
    return {d["name"]: dict(d["positions"]) for d in _payload(root)["diagrams"]}


def _save_all(root: Path, diagrams: object, revision: str | None = None) -> str | None:
    project, config = _load(root)
    return save_diagrams(project, config, diagrams, revision)


def _save(root: Path, positions: object, revision: str | None = None) -> str | None:
    """Save ``positions`` for the overview, every group diagram as the page shows it."""
    return _save_all(root, {**_body(root), OVERVIEW: positions}, revision)


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


def test_save_returns_the_revision_of_what_it_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An external write right after ours must not be taken as our revision: the next
    # Save would then overwrite it without a conflict.
    root = _project(tmp_path)
    written: list[str] = []
    save = save_layout

    def save_then_external_edit(layout: Any, path: Path) -> None:
        save(layout, path)
        written.append(path.read_text(encoding="utf-8"))
        path.write_text(written[0] + "\n", encoding="utf-8")

    monkeypatch.setattr("erdify_studio._diagrams.save_layout", save_then_external_edit)
    revision = _save(root, _positions())
    assert revision == hashlib.sha256(written[0].encode()).hexdigest()
    assert revision != layout_revision(root / "erdify-layout.json")


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


@pytest.mark.parametrize(
    ("positions", "key"),
    [
        (_without("core.customers"), "'core.customers'"),
        (_with("gone.table", [0, 0]), "'gone.table'"),
    ],
    ids=["missing", "unknown"],
)
def test_save_conflicts_when_the_models_changed(
    tmp_path: Path, positions: object, key: str
) -> None:
    """Other boxes than the page shows: the models changed since it loaded."""
    root = _project(tmp_path)
    with pytest.raises(LayoutConflictError, match=f"models changed.*{key}"):
        _save(root, positions)
    assert not (root / "erdify-layout.json").exists()


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
    overview = _payload(_project(tmp_path, models=long))
    char, padding = overview["metrics"]["charWidth"], overview["metrics"]["padding"]
    box = _box(overview, "core.customers")
    widest = max(
        6 + len(r["name"]) + 2 + len(r["type"]) + (1 if r["nullable"] else 0) for r in box["rows"]
    )
    assert box["width"] - padding >= widest * char


def test_save_writes_every_diagram(tmp_path: Path) -> None:
    root = _project(tmp_path)
    body = _body(root)
    body["core"] = {**body["core"], "core.customers": [777, 55]}  # type: ignore[dict-item]
    _save_all(root, body)
    diagrams = load_layout(root / "erdify-layout.json").diagrams
    assert diagrams["core"]["core.customers"] == (777, 55)
    assert diagrams[OVERVIEW]["core.customers"] == tuple(body[OVERVIEW]["core.customers"])  # type: ignore[index]


def test_the_same_entity_keeps_a_position_per_diagram(tmp_path: Path) -> None:
    root = _project(tmp_path)
    body: dict[str, Any] = _body(root)
    body[OVERVIEW]["core.customers"] = [0, 0]
    body["core"]["core.customers"] = [900, 0]
    body["billing"]["core.customers"] = [300, 300]  # a foreign box there
    _save_all(root, body)
    diagrams = load_layout(root / "erdify-layout.json").diagrams
    assert [diagrams[d]["core.customers"] for d in (OVERVIEW, "core", "billing")] == [
        (0, 0),
        (900, 0),
        (300, 300),
    ]


def test_save_with_group_by_none(tmp_path: Path) -> None:
    root = _project(tmp_path, studio_toml='group_by = "none"\n')
    body = _body(root)
    assert list(body) == [OVERVIEW]
    _save_all(root, body)
    project, config = _load(root)
    assert check_project(project, config) == []


def test_a_group_named_overview_round_trips(tmp_path: Path) -> None:
    root = _project(tmp_path, MODELS.replace('"schema": "core"', '"schema": "overview"'))
    _save_all(root, _body(root))
    assert set(load_layout(root / "erdify-layout.json").diagrams) == {
        OVERVIEW,
        "billing",
        "overview",
    }
    project, config = _load(root)
    assert check_project(project, config) == []


@pytest.mark.parametrize("diagrams", [[], None, "x"], ids=["list", "none", "string"])
def test_save_refuses_a_non_object(tmp_path: Path, diagrams: object) -> None:
    root = _project(tmp_path)
    with pytest.raises(PositionsError, match="diagrams must be an object"):
        _save_all(root, diagrams)
    assert not (root / "erdify-layout.json").exists()


def test_save_refuses_a_diagram_that_is_not_an_object(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with pytest.raises(PositionsError, match="positions must be an object"):
        _save_all(root, {**_body(root), "core": [1, 2]})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("missing", "new diagram 'core'"),
        ("extra", "no diagram 'stale' any more"),
    ],
)
def test_save_conflicts_on_the_diagram_set(tmp_path: Path, change: str, message: str) -> None:
    root = _project(tmp_path)
    _placed(root)
    path = root / "erdify-layout.json"
    before = path.read_bytes()
    body = _body(root)
    if change == "missing":
        del body["core"]
    else:
        body["stale"] = {}
    with pytest.raises(LayoutConflictError, match=f"models changed.*{message}"):
        _save_all(root, body, layout_revision(path))
    assert path.read_bytes() == before


@pytest.mark.parametrize("name", ["Overview", "Ungrouped"])
def test_a_group_named_like_a_built_in_label_is_told_apart(tmp_path: Path, name: str) -> None:
    models = MODELS.replace('"schema": "core"', f'"schema": "{name}"') + (
        '\n\nclass Audit(SQLModel, table=True):\n    __tablename__ = "audit"\n'
        "    id: int = Field(primary_key=True)\n"
    )
    payload = _payload(_project(tmp_path, models, studio_toml='group_by = "schema"\n'))
    labels = [d["label"] for d in payload["diagrams"]]
    assert len(set(labels)) == len(labels)
    assert f"{name} (group)" in labels
    assert (labels[0], labels[-1]) == ("Overview", "Ungrouped")  # the built-ins keep theirs


# --- model fingerprint (#7) --------------------------------------------------------


def _fingerprint(root: Path) -> str:
    project, config = _load(root)
    return model_fingerprint(project, config)


def test_the_fingerprint_ignores_a_comment(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _fingerprint(root)
    (root / "shop" / "models.py").write_text(MODELS + "\n# just a comment\n")
    assert _fingerprint(root) == before


@pytest.mark.parametrize(
    "change",
    [
        lambda m: m.replace(
            "    email: str = Field(unique=True)\n",
            "    email: str = Field(unique=True)\n    name: str\n",
        ),
        lambda m: (
            m + '\n\nclass Tag(SQLModel, table=True):\n    __tablename__ = "tags"\n'
            "    id: int = Field(primary_key=True)\n"
        ),
        lambda m: m.replace('__tablename__ = "lines"', '__tablename__ = "items"'),
    ],
    ids=["new column", "new table", "renamed table"],
)
def test_the_fingerprint_changes_with_the_model(tmp_path: Path, change: Any) -> None:
    root = _project(tmp_path)
    before = _fingerprint(root)
    (root / "shop" / "models.py").write_text(change(MODELS))
    assert _fingerprint(root) != before


def test_the_fingerprint_changes_with_group_by(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    before = _fingerprint(_project(tmp_path / "a"))
    after = _fingerprint(_project(tmp_path / "b", studio_toml='group_by = "none"\n'))
    assert before != after


def test_the_fingerprint_doesnt_read_the_layout_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _fingerprint(root)
    (root / "erdify-layout.json").write_text("<<<<<<< HEAD\n")
    assert _fingerprint(root) == before


def test_payload_carries_the_colors(tmp_path: Path) -> None:
    assert _payload(_project(tmp_path))["colors"] == {
        "accent": "#615fff",
        "header": "#e2e8f0",
        "headerText": "#0f172b",
        "background": "#ffffff",
        "enumHeader": "#d8deff",
        "enumTitle": "#0f172b",
        "text": "#0f172b",
        "textMuted": "#62748e",
        "border": "#e2e8f0",
        "borderStrong": "#cad5e2",
        "backgroundMuted": "#f8fafc",
        "accentText": "#ffffff",
    }


def test_fingerprint_changes_with_the_colors(tmp_path: Path) -> None:
    project, config = _load(_project(tmp_path))
    recolored = dataclasses.replace(config, colors=DiagramColors(accent="#4150aa"))
    assert model_fingerprint(project, config) != model_fingerprint(project, recolored)


def test_payload_carries_the_color_config(tmp_path: Path) -> None:
    project, config = _load(_project(tmp_path))
    assert build_diagrams(project, config, shown_path="x")["colorConfig"] == {}
    recolored = dataclasses.replace(config, colors=DiagramColors(accent="#4150aa"))
    assert build_diagrams(project, recolored, shown_path="x")["colorConfig"] == {
        "accent": "#4150aa"
    }


def test_fingerprint_follows_the_color_config(tmp_path: Path) -> None:
    project, config = _load(_project(tmp_path))
    explicit = dataclasses.replace(config, colors=DiagramColors(accent="#615fff"))
    assert model_fingerprint(project, config) != model_fingerprint(project, explicit)
