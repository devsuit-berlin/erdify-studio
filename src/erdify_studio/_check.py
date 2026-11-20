"""What each diagram must hold, and how a layout differs from it."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Literal

from erdify import EntityInfo, diagram_edges

from erdify_studio._config import GroupBy
from erdify_studio._entities import entity_groups, entity_keys
from erdify_studio._layout import OVERVIEW, Layout

#: How a layout differs from its diagrams (see ``Problem``).
ProblemKind = Literal["unplaced", "foreign", "stale_entry", "stale_diagram"]


@dataclass(frozen=True)
class DiagramContent:
    """The layout keys one diagram shows.

    Attributes:
        entities: Keys of the diagram's own entities (every entity on the overview).
        foreign: Keys of foreign boxes: entities of other groups that an own entity
            references or is referenced by. Always empty on the overview.
    """

    entities: frozenset[str]
    foreign: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Problem:
    """One difference between a layout and its diagrams.

    Attributes:
        diagram: The diagram it is in.
        key: The layout key; None for a ``stale_diagram``.
        kind: ``unplaced`` (an own entity has no position), ``foreign`` (a foreign
            box has no position), ``stale_entry`` (a position for a key the diagram
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
        return f"{where}: stale entry {self.key!r}: not in this diagram"


def diagram_contents(
    entities: Mapping[str, EntityInfo], group_by: GroupBy
) -> dict[str, DiagramContent]:
    """Map every diagram (the overview and one per group) to the keys it shows.

    A group diagram shows its own entities plus a foreign box for every entity of
    another group connected to one of them by an edge of ``erdify.diagram_edges``,
    in either direction.

    Raises:
        DuplicateKeyError: Two entities have the same layout key.
        LayoutError: A group value is a reserved diagram name.
    """
    keys = entity_keys(entities)
    groups = entity_groups(entities, group_by)
    own: dict[str, set[str]] = {}
    for name, group in groups.items():
        own.setdefault(group, set()).add(keys[name])
    foreign: dict[str, set[str]] = {group: set() for group in own}
    if groups:
        for edge in diagram_edges(entities):
            source, target = edge.from_entity, edge.to_entity
            if groups[source] != groups[target]:
                foreign[groups[source]].add(keys[target])
                foreign[groups[target]].add(keys[source])

    contents = {OVERVIEW: DiagramContent(frozenset(keys.values()))}
    for group in own:
        contents[group] = DiagramContent(frozenset(own[group]), frozenset(foreign[group]))
    return contents


def check_layout(
    layout: Layout,
    diagrams: Mapping[str, DiagramContent],
    *,
    unchecked: Collection[str] = frozenset(),
) -> list[Problem]:
    """Return how ``layout`` differs from ``diagrams``, sorted; empty when it matches.

    A missing diagram is no problem of its own: its entities are reported unplaced.

    Args:
        layout: The layout to check.
        diagrams: What each diagram shows (``diagram_contents``).
        unchecked: Keys whose positions are kept in any diagram but not required,
            e.g. the ``enum_key`` of every existing enum until erdify tells which
            enums it draws.
    """
    problems: list[Problem] = []
    for name, content in diagrams.items():
        placed = layout.diagrams.get(name, {})
        problems += [Problem(name, key, "unplaced") for key in content.entities - placed.keys()]
        problems += [Problem(name, key, "foreign") for key in content.foreign - placed.keys()]
        shown = content.entities | content.foreign | set(unchecked)
        problems += [Problem(name, key, "stale_entry") for key in placed.keys() - shown]
    problems += [
        Problem(name, None, "stale_diagram") for name in layout.diagrams.keys() - diagrams.keys()
    ]
    return sorted(problems, key=lambda p: (p.diagram, p.key or "", p.kind))
