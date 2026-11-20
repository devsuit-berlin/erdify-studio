"""``place --auto``: give unplaced boxes a position, drop stale entries and diagrams.

Placement is deterministic and never moves a placed box. Boxes are taken in key
order, preferring keys connected to an already placed box: such a box goes next
to its first placed neighbour (right, below, left, above). A box without a placed
neighbour goes to the first free slot of a grid right of the boxes that were
placed before. No two boxes come closer than ``GAP``.

Box sizes are estimates from the text the box shows (the canvas renders the same
fields), so neighbours stay readable without a browser.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass

from erdify import EntityInfo, Project, diagram_edges

from erdify_studio._check import DiagramContent, enum_keys, project_diagrams
from erdify_studio._config import StudioConfig
from erdify_studio._entities import entity_keys, enum_key
from erdify_studio._errors import LayoutError
from erdify_studio._layout import (
    MAX_COORDINATE,
    Layout,
    Position,
    load_existing_layout,
    save_layout,
)

#: Minimum space between two boxes, in canvas units.
GAP = 40
#: Width of a grid column for boxes without a placed neighbour.
GRID_COLUMN = 280
#: Height of a grid row (boxes may span several).
GRID_ROW = 40
#: Columns of the grid right of the diagram.
GRID_COLUMNS = 4

_MIN_WIDTH = 200
_CHAR_WIDTH = 8
_PADDING = 32
_HEADER = 32
_ROW = 22
_MARKERS = 6  # room for the PK / FK / UK badges next to a field

#: A box on a diagram: ``(x, y, width, height)``.
_Rect = tuple[int, int, int, int]
#: A box's size: ``(width, height)``.
_Size = tuple[int, int]
#: Size of the box of a key on one diagram.
_SizeOf = Callable[[str], _Size]
#: Keys a key's box belongs next to on one diagram.
_Related = Callable[[str], set[str]]


@dataclass(frozen=True)
class PlaceResult:
    """What ``place_project`` changed.

    Attributes:
        layout: The layout after placing.
        placed: ``(diagram, key)`` of every box that got a position, sorted.
        removed: ``(diagram, key)`` of every stale entry dropped from a diagram that
            still exists, sorted.
        removed_diagrams: Stale diagrams dropped with all their entries, sorted.
        created: True when there was no layout yet (no file, or an empty one).
    """

    layout: Layout
    placed: tuple[tuple[str, str], ...]
    removed: tuple[tuple[str, str], ...]
    removed_diagrams: tuple[str, ...]
    created: bool

    @property
    def changed(self) -> bool:
        """True when the layout file is written."""
        return self.created or bool(self.placed or self.removed or self.removed_diagrams)


def place_project(project: Project, config: StudioConfig) -> PlaceResult:
    """Place every unplaced box of ``project`` and drop stale entries and diagrams.

    Writes the layout file of ``config`` when anything changed, or creates it with
    every diagram when there is none yet; afterwards ``check_project`` passes.
    Positions of existing enums are kept but not added (erdify#369).

    Args:
        project: The project as ``erdify.load_project`` returns it; load it with
            ``strict=True``, else a file erdify cannot parse drops its tables and
            their positions are removed as stale.
        config: Its studio settings (``load_config(project.settings.pyproject)``).

    Raises:
        ProjectError: The project has no entities and erdify's ``allow_empty`` is off.
        DuplicateKeyError: Two entities have the same layout key.
        LayoutVersionError: The layout file is of another version.
        LayoutError: A reserved group name, or a layout file that cannot be read or
            written.
    """
    diagrams = project_diagrams(project, config)
    existing = load_existing_layout(config.layout)
    sizes = _entity_sizes(project)
    edges = _key_edges(project) if not project.settings.no_relationships else frozenset()
    result = place_layout(
        existing or Layout(),
        diagrams,
        sizes=sizes,
        edges=edges,
        kept=enum_keys(project),
        created=existing is None,
    )
    if result.changed:
        save_layout(result.layout, config.layout)
    return result


def place_layout(
    layout: Layout,
    diagrams: Mapping[str, DiagramContent],
    *,
    sizes: Mapping[str, _Size],
    edges: Collection[tuple[str, str]],
    kept: Collection[str] = frozenset(),
    created: bool = False,
) -> PlaceResult:
    """Return ``layout`` with every box of ``diagrams`` placed and stale entries dropped.

    ``layout`` itself is not changed.

    Args:
        layout: The current layout.
        diagrams: What each diagram shows (``diagram_contents``).
        sizes: Size of an own box per key; a foreign box shows the name only.
        edges: Connected key pairs, in either direction.
        kept: Keys whose positions are kept in any diagram but never added.
        created: Passed through to ``PlaceResult.created``.
    """
    neighbours: dict[str, set[str]] = {}
    for a, b in edges:
        if a != b:
            neighbours.setdefault(a, set()).add(b)
            neighbours.setdefault(b, set()).add(a)

    result = Layout()
    placed: list[tuple[str, str]] = []
    removed: list[tuple[str, str]] = []
    for name in sorted(diagrams):
        content = diagrams[name]
        old = layout.diagrams.get(name, {})
        shown = content.entities | content.foreign
        positions = {key: pos for key, pos in old.items() if key in shown or key in kept}
        removed += [(name, key) for key in sorted(old.keys() - positions.keys())]

        def size(key: str, content: DiagramContent = content) -> _Size:
            if key in content.foreign and key not in content.entities:
                return _box(key, ())
            return sizes[key]

        def related(key: str, content: DiagramContent = content) -> set[str]:
            # A foreign box belongs next to the own boxes it is connected with.
            found = neighbours.get(key, set()) & shown
            if key in content.entities:
                return found
            return found & content.entities

        # Own boxes before foreign ones among equals, so a group diagram without
        # placed boxes is anchored by its own entities.
        unplaced = sorted(content.entities - positions.keys())
        unplaced += sorted(content.foreign - content.entities - positions.keys())
        new = _place(positions, unplaced, size, related)
        placed += [(name, key) for key in sorted(new)]
        result.add_diagram(name)
        for key, (x, y) in {**positions, **new}.items():
            result.set_position(name, key, x, y)

    return PlaceResult(
        layout=result,
        placed=tuple(placed),
        removed=tuple(removed),
        removed_diagrams=tuple(sorted(layout.diagrams.keys() - diagrams.keys())),
        created=created,
    )


def _place(
    positions: Mapping[str, Position],
    unplaced: list[str],
    size: _SizeOf,
    related: _Related,
) -> dict[str, Position]:
    """Positions for ``unplaced`` (in placing order) around the fixed ``positions``."""
    rects = [(x, y, *size(key)) for key, (x, y) in positions.items()]
    origin = (
        (max(x + w for x, _, w, _ in rects) + GAP, min(y for _, y, _, _ in rects))
        if rects
        else (0, 0)
    )
    placed = dict(positions)
    new: dict[str, Position] = {}
    slot = 0
    todo = list(unplaced)
    while todo:
        key = next((k for k in todo if related(k) & placed.keys()), None)
        position = None
        if key is not None:
            position = _next_to(
                key, size(key), sorted(related(key) & placed.keys()), placed, size, rects
            )
        else:
            key = todo[0]
        if position is None:
            position, slot = _grid_slot(size(key), origin, slot, rects)
        todo.remove(key)
        placed[key] = new[key] = position
        rects.append((*position, *size(key)))
    return new


def _next_to(
    key: str,
    box: _Size,
    neighbours: Iterable[str],
    placed: Mapping[str, Position],
    size: _SizeOf,
    rects: list[_Rect],
) -> Position | None:
    """The first free spot right of, below, left of or above a neighbour."""
    w, h = box
    for neighbour in neighbours:
        nx, ny = placed[neighbour]
        nw, nh = size(neighbour)
        for spot in (
            (nx + nw + GAP, ny),
            (nx, ny + nh + GAP),
            (nx - GAP - w, ny),
            (nx, ny - GAP - h),
        ):
            if _in_range((*spot, w, h)) and _free((*spot, w, h), rects):
                return spot
    return None


def _grid_slot(
    box: _Size, origin: Position, start: int, rects: list[_Rect]
) -> tuple[Position, int]:
    """The first free grid slot for ``box``, and the new ``start``.

    ``start`` is the first slot where the smallest box may still fit: boxes are only
    ever added, so a slot that is taken for the smallest box stays taken for every
    box, and the search skips it next time.

    Raises:
        LayoutError: The grid reaches past ``MAX_COORDINATE``.
    """
    w, h = box
    smallest = (_MIN_WIDTH, _HEADER)
    slot = start
    while True:
        row, column = divmod(slot, GRID_COLUMNS)
        spot = (origin[0] + column * GRID_COLUMN, origin[1] + row * GRID_ROW)
        if not _in_range((*spot, w, h)):
            raise LayoutError(
                f"no room for a new box at {spot!r}: positions are limited to "
                f"\u00b1{MAX_COORDINATE}; move the boxes near the limit"
            )
        if slot == start and not _free((*spot, *smallest), rects):
            start += 1
        if _free((*spot, w, h), rects):
            return spot, start
        slot += 1


def _in_range(rect: _Rect) -> bool:
    x, y, w, h = rect
    return min(x, y) >= -MAX_COORDINATE and max(x + w, y + h) <= MAX_COORDINATE


def _free(rect: _Rect, rects: Iterable[_Rect]) -> bool:
    x, y, w, h = rect
    return all(
        x >= ox + ow + GAP or ox >= x + w + GAP or y >= oy + oh + GAP or oy >= y + h + GAP
        for ox, oy, ow, oh in rects
    )


def _entity_sizes(project: Project) -> dict[str, _Size]:
    keys = entity_keys(project.entities)
    sizes = {
        keys[name]: _entity_box(keys[name], entity) for name, entity in project.entities.items()
    }
    for enum in project.enums.values():
        sizes[enum_key(enum)] = _box(enum.name, [str(value) for value in enum.values])
    return sizes


def _entity_box(key: str, entity: EntityInfo) -> _Size:
    return _box(key, [f"{f.name} {f.type_str}" + " " * _MARKERS for f in entity.fields])


def _box(title: str, rows: Collection[str]) -> _Size:
    longest = max((len(text) for text in (title, *rows)), default=0)
    return max(_MIN_WIDTH, longest * _CHAR_WIDTH + _PADDING), _HEADER + _ROW * len(rows)


def _key_edges(project: Project) -> frozenset[tuple[str, str]]:
    keys = entity_keys(project.entities)
    return frozenset(
        (keys[edge.from_entity], keys[edge.to_entity]) for edge in diagram_edges(project.entities)
    )
