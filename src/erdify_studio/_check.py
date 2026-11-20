"""What each diagram must hold, and how a layout differs from it."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Literal

from erdify import EntityInfo, Project, diagram_edges, enum_users

from erdify_studio._config import GroupBy, StudioConfig
from erdify_studio._entities import entity_groups, entity_ids, entity_keys, enum_key
from erdify_studio._errors import ProjectError
from erdify_studio._layout import OVERVIEW, Layout, load_existing_layout

#: How a layout differs from its diagrams (see ``Problem``).
ProblemKind = Literal["unplaced", "foreign", "enum", "stale_entry", "stale_diagram"]


@dataclass(frozen=True)
class DiagramContent:
    """The layout keys one diagram shows.

    Attributes:
        entities: Keys of the diagram's own entities (every entity on the overview).
        foreign: Keys of foreign boxes: entities of other groups that an own entity
            references or is referenced by. Always empty on the overview.
        enums: Keys of the enums erdify draws that an own entity uses (every drawn
            enum on the overview).
    """

    entities: frozenset[str]
    foreign: frozenset[str] = field(default_factory=frozenset)
    enums: frozenset[str] = field(default_factory=frozenset)

    @property
    def shown(self) -> frozenset[str]:
        """Every key the diagram shows."""
        return self.entities | self.foreign | self.enums


@dataclass(frozen=True)
class Problem:
    """One difference between a layout and its diagrams.

    Attributes:
        diagram: The diagram it is in.
        key: The layout key; None for a ``stale_diagram``.
        kind: ``unplaced`` (an own entity has no position), ``foreign`` (a foreign
            box has no position), ``enum`` (a drawn enum has no position),
            ``stale_entry`` (a position for a key the diagram
            does not show) or ``stale_diagram`` (a diagram that no longer exists).
    """

    diagram: str
    key: str | None
    kind: ProblemKind

    def __str__(self) -> str:
        if self.kind == "stale_diagram":
            return f"stale diagram {self.diagram!r}: no such group"
        where = f"diagram {self.diagram!r}"
        if self.kind == "unplaced":
            return f"{where}: entity {self.key!r} has no position"
        if self.kind == "foreign":
            return f"{where}: foreign box {self.key!r} has no position"
        if self.kind == "enum":
            return f"{where}: enum {self.key!r} has no position"
        return f"{where}: stale entry {self.key!r}: not in this diagram"


def diagram_contents(
    entities: Mapping[str, EntityInfo],
    group_by: GroupBy,
    *,
    relationships: bool = True,
    enums: Mapping[str, Collection[str]] | None = None,
) -> dict[str, DiagramContent]:
    """Map every diagram (the overview and one per group) to the keys it shows.

    A group diagram shows its own entities plus a foreign box for every entity of
    another group connected to one of them by an edge of ``erdify.diagram_edges``,
    in either direction. Without ``relationships`` (erdify's ``no_relationships``)
    erdify draws no edges, so there are no foreign boxes.

    ``enums`` maps the layout key of every enum erdify draws to the names
    (``EntityInfo.name``) of the entities using it (``erdify.enum_users``): the
    overview shows every one, a group diagram those its own entities use.

    Raises:
        DuplicateKeyError: An entity keyed by its erdify name has another entity's key.
        LayoutError: A group value is a reserved diagram name.
    """
    keys = entity_keys(entities)
    groups = entity_groups(entities, group_by)
    ids = entity_ids(entities)
    own: dict[str, set[str]] = {}
    for name, group in groups.items():
        own.setdefault(group, set()).add(keys[name])
    foreign: dict[str, set[str]] = {group: set() for group in own}
    if groups and relationships:
        for edge in diagram_edges(entities):
            source, target = ids[edge.from_entity], ids[edge.to_entity]
            if groups[source] != groups[target]:
                foreign[groups[source]].add(keys[target])
                foreign[groups[target]].add(keys[source])

    used: dict[str, set[str]] = {group: set() for group in own}
    if groups:
        for key, users in (enums or {}).items():
            for name in users:
                used[groups[ids[name]]].add(key)

    contents = {OVERVIEW: DiagramContent(frozenset(keys.values()), enums=frozenset(enums or {}))}
    for group in own:
        contents[group] = DiagramContent(
            frozenset(own[group]), frozenset(foreign[group]), frozenset(used[group])
        )
    return contents


def check_layout(layout: Layout, diagrams: Mapping[str, DiagramContent]) -> list[Problem]:
    """Return how ``layout`` differs from ``diagrams``; empty when it matches.

    Sorted by diagram (the overview first), then key.

    A missing diagram is no problem of its own: its entities are reported unplaced.

    Args:
        layout: The layout to check.
        diagrams: What each diagram shows (``diagram_contents``).
    """
    problems: list[Problem] = []
    for name, content in diagrams.items():
        placed = layout.diagrams.get(name, {})
        problems += [Problem(name, key, "unplaced") for key in content.entities - placed.keys()]
        problems += [Problem(name, key, "foreign") for key in content.foreign - placed.keys()]
        problems += [Problem(name, key, "enum") for key in content.enums - placed.keys()]
        problems += [Problem(name, key, "stale_entry") for key in placed.keys() - content.shown]
    problems += [
        Problem(name, None, "stale_diagram") for name in layout.diagrams.keys() - diagrams.keys()
    ]
    # The overview first, then the groups by name ("_" would sort after uppercase).
    return sorted(problems, key=lambda p: (p.diagram != OVERVIEW, p.diagram, p.key or "", p.kind))


def check_project(project: Project, config: StudioConfig) -> list[Problem] | None:
    """Check the layout file of ``config`` against ``project``.

    Every enum erdify draws needs a position on the overview and on the group
    diagrams of the entities using it.

    Args:
        project: The project as ``erdify.load_project`` returns it; load it with
            ``strict=True``, else a file erdify cannot parse drops its tables and
            their positions are reported stale.
        config: Its studio settings (``load_config(project.settings.pyproject)``).

    Returns:
        The problems, sorted (empty when the layout matches); None when there is no
        layout yet (no file, or an empty one).

    Raises:
        ProjectError: The project has no entities and erdify's ``allow_empty`` is
            off, as ``erdify`` refuses it: every position would read as stale.
        DuplicateKeyError: An entity keyed by its erdify name has another entity's key.
        LayoutVersionError: The layout file is of another version.
        LayoutError: A reserved group name, or a layout file that cannot be read.
    """
    diagrams = project_diagrams(project, config)
    layout = load_existing_layout(config.layout)
    if layout is None:
        return None
    return check_layout(layout, diagrams)


def project_diagrams(project: Project, config: StudioConfig) -> dict[str, DiagramContent]:
    """``diagram_contents`` of ``project`` under ``config``.

    Raises:
        ProjectError: The project has no entities and erdify's ``allow_empty`` is
            off, as ``erdify`` refuses it: every position would read as stale.
        DuplicateKeyError: An entity keyed by its erdify name has another entity's key.
        LayoutError: A group value is a reserved diagram name.
    """
    if not project.entities and not project.settings.allow_empty:
        raise ProjectError(
            f"no entities found in {str(project.settings.input)!r}; check the path and "
            f"[tool.erdify] include / sources, or set allow_empty"
        )
    return diagram_contents(
        project.entities,
        config.group_by,
        relationships=not project.settings.no_relationships,
        enums=drawn_enums(project),
    )


def drawn_enums(project: Project) -> dict[str, list[str]]:
    """Layout key of every enum erdify draws -> the names of the entities using it."""
    users = enum_users(project.entities, project.enums, include_enums=not project.settings.no_enums)
    return {enum_key(project.enums[name]): entities for name, entities in users.items()}
