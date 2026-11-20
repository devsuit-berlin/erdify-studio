"""The overview diagram as the canvas draws it, as JSON-ready dicts.

Python owns everything the canvas shows: the boxes with their sizes (from
``_place``, so the canvas and ``place --auto`` agree), positions including the
ones ``place --auto`` would give unplaced boxes, erdify's edges, and the
revision of the layout file the positions were read from.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, TypedDict

from erdify import EdgeEnd, Project, diagram_edges

from erdify_studio._check import drawn_enums, project_diagrams
from erdify_studio._config import StudioConfig
from erdify_studio._entities import entity_ids, entity_keys, enum_key
from erdify_studio._layout import OVERVIEW, Layout, load_existing_layout
from erdify_studio._place import METRICS, PlaceResult, place_inputs, place_layout


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


class Box(TypedDict):
    """An entity or enum box at its position (top-left), in canvas units."""

    key: str
    kind: Literal["entity", "enum"]
    title: str
    x: int
    y: int
    width: int
    height: int
    new: bool
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

    ``placed``: new overview boxes. ``groupChanges``: boxes placed on group diagrams
    plus stale entries and diagrams dropped. ``created``: there is no layout file yet.
    """

    placed: int
    groupChanges: int
    created: bool


class Overview(TypedDict):
    """The JSON of ``GET /api/overview``."""

    metrics: dict[str, int]
    boxes: list[Box]
    edges: list[EdgeJson]
    enumLinks: list[EnumLink]
    revision: str | None
    pending: Pending
    layoutPath: str
    projectPath: str


def layout_revision(path: Path) -> str | None:
    """The sha256 hex digest of the file at ``path``; None when there is none.

    Raises:
        OSError: The file exists but cannot be read.
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def build_overview(project: Project, config: StudioConfig, *, shown_path: str) -> Overview:
    """The overview of ``project`` with the positions of its layout file.

    Boxes without a position get the one ``place --auto`` would give them and are
    marked ``new``. Nothing is written.

    Args:
        project: The project as ``erdify.load_project(..., strict=True)`` returns it.
        config: Its studio settings.
        shown_path: The layout file's path as the UI shows it.

    Raises:
        ProjectError: The project has no entities and erdify's ``allow_empty`` is off.
        DuplicateKeyError: Two entities have the same layout key.
        LayoutVersionError: The layout file is of another version.
        LayoutError: A reserved group name, or a layout file that cannot be read.
        OSError: The layout file cannot be read.
    """
    revision = layout_revision(config.layout)
    diagrams = project_diagrams(project, config)
    existing = load_existing_layout(config.layout)
    sizes, edges = place_inputs(project)
    result = place_layout(
        existing or Layout(), diagrams, sizes=sizes, edges=edges, created=existing is None
    )
    positions = result.layout.diagrams[OVERVIEW]
    new = {key for diagram, key in result.placed if diagram == OVERVIEW}
    shown = diagrams[OVERVIEW]

    keys = entity_keys(project.entities)
    boxes: list[Box] = []
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
        boxes.append(_box(key, "entity", key, rows, positions, sizes, new))
    for enum in project.enums.values():
        key = enum_key(enum)
        if key in shown.enums:
            values: list[ValueRow] = [{"name": str(value)} for value in enum.values]
            boxes.append(_box(key, "enum", enum.name, values, positions, sizes, new))
    boxes.sort(key=lambda box: box["key"])

    return {
        "metrics": dict(METRICS),
        "boxes": boxes,
        "edges": _edges(project),
        "enumLinks": _enum_links(project),
        "revision": revision,
        "pending": _pending(result),
        "layoutPath": shown_path,
        "projectPath": str(project.settings.input),
    }


def _box(
    key: str,
    kind: Literal["entity", "enum"],
    title: str,
    rows: list[FieldRow] | list[ValueRow],
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]],
    new: set[str],
) -> Box:
    x, y = positions[key]
    width, height = sizes[key]
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "new": key in new,
        "rows": rows,
    }


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
    placed = sum(1 for diagram, _ in result.placed if diagram == OVERVIEW)
    return {
        "placed": placed,
        "groupChanges": len(result.placed)
        - placed
        + len(result.removed)
        + len(result.removed_diagrams),
        "created": result.created,
    }
