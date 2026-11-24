"""Every diagram as the canvas draws it, as JSON-ready dicts.

Python owns everything the canvas shows: the boxes with their sizes (from
``_place``, so the canvas and ``place --auto`` agree), positions including the
ones ``place --auto`` would give unplaced boxes, erdify's edges, and the
revision of the layout file the positions were read from.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, TypedDict

from erdify import EdgeEnd, Project, diagram_edges

from erdify_studio._check import DiagramContent, drawn_enums, project_diagrams
from erdify_studio._colors import Palette, palette_of, set_colors
from erdify_studio._config import StudioConfig
from erdify_studio._entities import entity_groups, entity_ids, entity_keys, enum_key
from erdify_studio._errors import LayoutConflictError, LayoutError, PositionsError
from erdify_studio._layout import (
    DEFAULT_GROUP,
    OVERVIEW,
    Layout,
    dumps_layout,
    load_existing_layout,
    save_layout,
)
from erdify_studio._place import METRICS, PlaceResult, name_box_size, place_inputs, place_layout


class FieldRow(TypedDict):
    """One field of an entity box."""

    name: str
    type: str
    pk: bool
    fk: bool
    uk: bool
    nullable: bool


class ValueRow(TypedDict):
    """One value of an enum box."""

    name: str


class BoxDef(TypedDict):
    """An entity or enum box, sent once for every diagram that shows it.

    ``group`` is the entity's group diagram; None for enums and without groups.
    """

    kind: Literal["entity", "enum"]
    title: str
    group: str | None
    width: int
    height: int
    rows: list[FieldRow] | list[ValueRow]


class EdgeEndJson(TypedDict):
    """One end of an edge: optional (zero allowed) and many (more than one)."""

    optional: bool
    many: bool


EdgeJson = TypedDict(
    "EdgeJson",
    {
        "from": str,
        "to": str,
        "fromEnd": EdgeEndJson,
        "toEnd": EdgeEndJson,
        "kind": str,
        "label": str,
    },
)
"""An edge of ``erdify.diagram_edges`` between two layout keys."""


class EnumLink(TypedDict):
    """An enum and an entity using it."""

    enum: str
    entity: str


class Pending(TypedDict):
    """What Save would change before anything is dragged.

    ``placed``: boxes placed automatically, over all diagrams. ``diagrams``: how many
    diagrams have such boxes. ``dropped``: stale entries plus stale diagrams.
    ``created``: there is no layout file yet. ``svgs``: exported SVGs that are missing,
    out of date or stale (``_export.build_studio`` fills it; 0 here).
    """

    placed: int
    diagrams: int
    dropped: int
    created: bool
    svgs: int


class DiagramJson(TypedDict):
    """One diagram: the keys it shows, where, and what it draws between them.

    ``own``: its entities and enums; ``foreign``: name-only boxes of other groups,
    sized by ``foreignSizes``; ``positions``: every shown key (top-left, canvas
    units); ``new``: keys placed automatically, not yet in the layout file.
    """

    name: str
    label: str
    own: list[str]
    foreign: list[str]
    foreignSizes: dict[str, list[int]]
    positions: dict[str, list[int]]
    new: list[str]
    edges: list[EdgeJson]
    enumLinks: list[EnumLink]


class ColorsJson(TypedDict):
    """The colours the canvas draws with (the ones of the SVG export's palette)."""

    accent: str
    header: str
    headerText: str
    background: str
    enumHeader: str
    enumTitle: str
    text: str
    textMuted: str
    border: str
    borderStrong: str
    backgroundMuted: str
    accentText: str


class Diagrams(TypedDict):
    """The JSON of ``GET /api/diagrams``."""

    metrics: dict[str, int]
    boxes: dict[str, BoxDef]
    diagrams: list[DiagramJson]
    colors: ColorsJson
    revision: str | None
    pending: Pending
    layoutPath: str
    projectPath: str
    exportPath: str | None
    #: The keys set in ``[tool.erdify-studio.colors]`` (the colour panel starts from them).
    colorConfig: dict[str, str]


#: Labels of the diagrams that aren't named after a group.
_LABELS = {OVERVIEW: "Overview", DEFAULT_GROUP: "Ungrouped"}


def _label(name: str) -> str:
    """The diagram's name as the UI lists it; a group never looks like a built-in one."""
    if name in _LABELS:
        return _LABELS[name]
    return f"{name} (group)" if name in _LABELS.values() else name


def layout_revision(path: Path) -> str | None:
    """The sha256 hex digest of the file at ``path``; None when there is none.

    Raises:
        OSError: The file exists but cannot be read.
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def build_diagrams(project: Project, config: StudioConfig, *, shown_path: str) -> Diagrams:
    """Every diagram of ``project`` with the positions of its layout file.

    Boxes without a position get the one ``place --auto`` would give them and are
    listed as ``new``. Nothing is written. Order: the overview, the groups by name,
    ``DEFAULT_GROUP`` last.

    Args:
        project: The project as ``erdify.load_project(..., strict=True)`` returns it.
        config: Its studio settings.
        shown_path: The layout file's path as the UI shows it.

    Raises:
        ProjectError: The project has no entities and erdify's ``allow_empty`` is off.
        DuplicateKeyError: An entity keyed by its erdify name has another entity's key.
        LayoutVersionError: The layout file is of another version.
        LayoutError: A reserved group name, or a layout file that cannot be read.
        OSError: The layout file cannot be read.
    """
    revision = layout_revision(config.layout)
    existing = load_existing_layout(config.layout)
    payload = build_from(project, config, existing or Layout(), created=existing is None)
    payload["revision"] = revision
    payload["layoutPath"] = shown_path
    return payload


def model_fingerprint(project: Project, config: StudioConfig) -> str:
    """A digest of what the canvas draws, positions aside; changes with the models.

    Built without the layout file, so a broken or edited layout file never looks like
    a model change. Comments and formatting in the model files don't change it.
    """
    payload = build_from(project, config, Layout(), created=True)
    shape = {
        "metrics": payload["metrics"],
        "boxes": payload["boxes"],
        "diagrams": [
            {k: v for k, v in d.items() if k not in ("positions", "new")}
            for d in payload["diagrams"]
        ],
        "colors": payload["colors"],
        "colorConfig": payload["colorConfig"],
        "exportDir": None if config.export_dir is None else str(config.export_dir),
    }
    text = json.dumps(shape, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def colors_json(palette: Palette) -> ColorsJson:
    """The colours the canvas draws with, as the API sends them."""
    return {
        "accent": palette.accent,
        "header": palette.header,
        "headerText": palette.header_text,
        "background": palette.background,
        "enumHeader": palette.enum_header,
        "enumTitle": palette.enum_title,
        "text": palette.text,
        "textMuted": palette.text_muted,
        "border": palette.border,
        "borderStrong": palette.border_strong,
        "backgroundMuted": palette.background_muted,
        "accentText": palette.accent_text,
    }


def build_from(project: Project, config: StudioConfig, start: Layout, *, created: bool) -> Diagrams:
    """The payload of ``project`` with every box placed, starting from ``start``.

    ``revision`` and ``layoutPath`` are left empty; ``pending`` is relative to
    ``start``, ``new`` lists the boxes placed here.
    """
    contents = project_diagrams(project, config)
    sizes, edges = place_inputs(project)
    result = place_layout(start, contents, sizes=sizes, edges=edges, created=created)
    all_edges = _edges(project)
    all_links = _enum_links(project)
    new: dict[str, list[str]] = {}
    for diagram, key in result.placed:
        new.setdefault(diagram, []).append(key)

    def order(name: str) -> tuple[int, str]:
        return (0 if name == OVERVIEW else 2 if name == DEFAULT_GROUP else 1, name)

    diagrams: list[DiagramJson] = []
    for name in sorted(contents, key=order):
        content = contents[name]
        foreign = sorted(content.foreign - content.entities)
        diagrams.append(
            {
                "name": name,
                "label": _label(name),
                "own": sorted(content.entities | content.enums),
                "foreign": foreign,
                "foreignSizes": {key: list(name_box_size(key)) for key in foreign},
                "positions": {
                    key: [x, y] for key, (x, y) in sorted(result.layout.diagrams[name].items())
                },
                "new": sorted(new.get(name, [])),
                "edges": [e for e in all_edges if content.shows_edge(e["from"], e["to"])],
                "enumLinks": [
                    link
                    for link in all_links
                    if content.shows_enum_link(link["enum"], link["entity"])
                ],
            }
        )

    palette = palette_of(config.colors)
    return {
        "metrics": dict(METRICS),
        "boxes": _boxes(project, config, sizes, contents[OVERVIEW]),
        "diagrams": diagrams,
        "colors": colors_json(palette),
        "colorConfig": set_colors(config.colors),
        "revision": None,
        "pending": _pending(result),
        "layoutPath": "",
        "projectPath": str(project.settings.input),
        "exportPath": None,
    }


def save_diagrams(
    project: Project, config: StudioConfig, diagrams: object, revision: str | None
) -> str | None:
    """Save the positions of every diagram and return the layout file's new revision.

    Writes exactly these positions, then what ``place --auto`` would add (nothing for
    a complete body), so ``check_project`` passes afterwards.

    Args:
        project: The project as ``erdify.load_project(..., strict=True)`` returns it.
        config: Its studio settings.
        diagrams: Diagram name -> layout key -> ``[x, y]`` for every box of every
            diagram, as decoded from JSON (validated here).
        revision: ``layout_revision`` of the file the positions were based on.

    Raises:
        LayoutConflictError: The file's revision is not ``revision`` any more.
        LayoutConflictError: Other diagrams or boxes than the project has: the models
            changed since the page loaded.
        PositionsError: ``diagrams`` or a diagram is not an object, or a position is
            not a pair of finite numbers within the coordinate limit.
        LayoutError: The layout file cannot be read or written (see ``save_layout``).
    """
    current = layout_revision(config.layout)
    if current != revision:
        raise LayoutConflictError(
            f"{str(config.layout)!r} changed since the positions were read from it"
        )
    if not isinstance(diagrams, Mapping):
        raise PositionsError(f"diagrams must be an object, got {type(diagrams).__name__!r}")
    contents = project_diagrams(project, config)
    missing = sorted(contents.keys() - diagrams.keys())
    unknown = sorted(diagrams.keys() - contents.keys())
    if missing or unknown:
        first = f"no diagram {unknown[0]!r} any more" if unknown else f"new diagram {missing[0]!r}"
        raise LayoutConflictError(
            f"the models changed since the page loaded ({first}); reload the page",
            reason="models",
        )
    layout = Layout()
    for name, content in contents.items():
        layout.add_diagram(name)
        for key, (x, y) in checked_positions(diagrams[name], content.shown).items():
            try:
                layout.set_position(name, key, x, y)
            except LayoutError as e:
                raise PositionsError(str(e)) from None
    sizes, edges = place_inputs(project)
    result = place_layout(layout, contents, sizes=sizes, edges=edges)
    save_layout(result.layout, config.layout)
    # The revision of what was written, not of the file read again: a write by someone
    # else in between must surface as a conflict on the next Save, not be adopted.
    return hashlib.sha256(dumps_layout(result.layout).encode()).hexdigest()


def checked_positions(positions: object, shown: frozenset[str]) -> dict[str, tuple[float, float]]:
    """``positions`` narrowed to key -> ``(x, y)`` numbers, with exactly the ``shown`` keys."""
    if not isinstance(positions, Mapping):
        raise PositionsError(f"positions must be an object, got {type(positions).__name__!r}")
    # Other boxes than the diagram shows: the page was loaded before the models
    # changed (e.g. a `git checkout`). Saving would drop the positions it lacks.
    missing = sorted(shown - positions.keys())
    unknown = sorted(positions.keys() - shown)
    if missing or unknown:
        first = f"no box {unknown[0]!r} any more" if unknown else f"new box {missing[0]!r}"
        raise LayoutConflictError(
            f"the models changed since the page loaded ({first}); reload the page",
            reason="models",
        )
    checked: dict[str, tuple[float, float]] = {}
    for key, value in positions.items():
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in value)
        ):
            raise PositionsError(f"position of {key!r} must be [x, y] numbers, got {value!r}")
        checked[key] = (value[0], value[1])
    return checked


def _boxes(
    project: Project,
    config: StudioConfig,
    sizes: Mapping[str, tuple[int, int]],
    overview: DiagramContent,
) -> dict[str, BoxDef]:
    """Every entity and drawn enum, by layout key, sorted."""
    keys = entity_keys(project.entities)
    groups = entity_groups(project.entities, config.group_by)
    boxes: dict[str, BoxDef] = {}
    for name, entity in project.entities.items():
        key = keys[name]
        rows: list[FieldRow] = [
            {
                "name": f.name,
                "type": f.type_str,
                "pk": f.is_primary_key,
                "fk": f.is_foreign_key,
                "uk": f.is_unique,
                "nullable": f.is_nullable,
            }
            for f in entity.fields
        ]
        width, height = sizes[key]
        boxes[key] = {
            "kind": "entity",
            "title": key,
            "group": groups.get(name),
            "width": width,
            "height": height,
            "rows": rows,
        }
    for enum in project.enums.values():
        key = enum_key(enum)
        if key in overview.enums:
            values: list[ValueRow] = [{"name": str(value)} for value in enum.values]
            width, height = sizes[key]
            boxes[key] = {
                "kind": "enum",
                "title": enum.name,
                "group": None,
                "width": width,
                "height": height,
                "rows": values,
            }
    return dict(sorted(boxes.items()))


def _end(end: EdgeEnd) -> EdgeEndJson:
    return {"optional": end.optional, "many": end.many}


def _edges(project: Project) -> list[EdgeJson]:
    if project.settings.no_relationships:
        return []
    keys = entity_keys(project.entities)
    ids = entity_ids(project.entities)
    return [
        {
            "from": keys[ids[edge.from_entity]],
            "to": keys[ids[edge.to_entity]],
            "fromEnd": _end(edge.from_end),
            "toEnd": _end(edge.to_end),
            "kind": str(edge.kind),
            "label": edge.label,
        }
        for edge in diagram_edges(project.entities)
    ]


def _enum_links(project: Project) -> list[EnumLink]:
    keys = entity_keys(project.entities)
    ids = entity_ids(project.entities)
    return sorted(
        (
            {"enum": enum, "entity": keys[ids[name]]}
            for enum, users in drawn_enums(project).items()
            for name in users
        ),
        key=lambda link: (link["enum"], link["entity"]),
    )


def _pending(result: PlaceResult) -> Pending:
    return {
        "placed": len(result.placed),
        "diagrams": len({diagram for diagram, _ in result.placed}),
        "dropped": len(result.removed) + len(result.removed_diagrams),
        "created": result.created,
        "svgs": 0,
    }
