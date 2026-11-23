"""Where edges meet boxes and how their ends look: a port of ``frontend/src/geometry.ts``.

The canvas draws with ``geometry.ts`` while a box is dragged; the SVG export draws
with this module. Keep the two identical: ``scripts/check_geometry.py`` runs both on
``scripts/geometry_cases.json`` in CI and fails on any difference. Path strings
format numbers as JavaScript does (``toFixed(2)`` where ``geometry.ts`` uses it,
``String(number)`` elsewhere), so the export writes what the canvas draws.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

#: Distance between parallel edges of the same two boxes (``FAN_STEP`` in drawing.ts).
FAN_STEP = 16

Point = tuple[float, float]


@dataclass(frozen=True)
class Rect:
    """A box: top-left corner and size, in canvas units."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class SelfLoop:
    """A self-reference: its path and both ends, each with the direction away from the box."""

    path: str
    start: Point
    start_angle: float
    end: Point
    end_angle: float


@dataclass(frozen=True)
class Marker:
    """A crow's-foot end: stroked ``lines`` and, for an optional end, a ``circle`` path."""

    lines: str
    circle: str | None


def js_number(value: float) -> str:
    """``value`` as JavaScript's ``String(number)`` writes it (``3``, ``2.5``, ``-1``)."""
    if value == 0:
        return "0"
    if math.isfinite(value) and value == int(value) and abs(value) < 1e21:
        return str(int(value))
    return repr(value)


def _fixed(value: float) -> str:
    """JavaScript's ``value.toFixed(2)``."""
    return f"{value:.2f}"


def center(rect: Rect) -> Point:
    return (rect.x + rect.width / 2, rect.y + rect.height / 2)


def border_point(rect: Rect, toward: Point, start: Point | None = None) -> Point:
    """Where the ray from ``start`` (inside ``rect``) toward ``toward`` leaves ``rect``."""
    fx, fy = start if start is not None else center(rect)
    sx = min(max(fx, rect.x), rect.x + rect.width)
    sy = min(max(fy, rect.y), rect.y + rect.height)
    dx, dy = toward[0] - sx, toward[1] - sy
    if dx == 0 and dy == 0:
        return (sx, sy)
    tx = (rect.x + rect.width - sx) / dx if dx > 0 else (rect.x - sx) / dx if dx < 0 else math.inf
    ty = (rect.y + rect.height - sy) / dy if dy > 0 else (rect.y - sy) / dy if dy < 0 else math.inf
    t = min(tx, ty)
    return (sx + dx * t, sy + dy * t)


def fan_offsets(edges: Sequence[tuple[str, str]]) -> list[float]:
    """Per edge, its sideways offset; a self-reference gets its index among its loops."""

    def pair(edge: tuple[str, str]) -> tuple[str, str]:
        a, b = edge
        return (a, b) if a < b else (b, a)

    counts: dict[tuple[str, str], int] = {}
    for edge in edges:
        counts[pair(edge)] = counts.get(pair(edge), 0) + 1
    seen: dict[tuple[str, str], int] = {}
    offsets: list[float] = []
    for edge in edges:
        key = pair(edge)
        index = seen.get(key, 0)
        seen[key] = index + 1
        if edge[0] == edge[1]:
            offsets.append(index)
        else:
            offsets.append((index - (counts[key] - 1) / 2) * FAN_STEP)
    return offsets


def edge_line(a: Rect, b: Rect, offset: float, a_key: str, b_key: str) -> tuple[Point, Point]:
    """The end points of a straight edge between two boxes, shifted sideways by ``offset``."""
    ca, cb = center(a), center(b)
    p, q = (ca, cb) if a_key < b_key else (cb, ca)
    length = math.hypot(q[0] - p[0], q[1] - p[1]) or 1
    normal = (-(q[1] - p[1]) / length, (q[0] - p[0]) / length)

    def shift(c: Point) -> Point:
        return (c[0] + normal[0] * offset, c[1] + normal[1] * offset)

    sa, sb = shift(ca), shift(cb)
    return border_point(a, sb, sa), border_point(b, sa, sb)


def self_loop(rect: Rect, index: int) -> SelfLoop:
    """A loop on the right side of ``rect``; nested loops further out."""
    right = rect.x + rect.width
    middle = rect.y + rect.height / 2
    spread = min(14 + index * 6, rect.height / 2 - 4)
    reach = 56 + index * 20
    start = (right, middle - spread)
    end = (right, middle + spread)
    n = js_number
    path = (
        f"M {n(start[0])} {n(start[1])} C {n(right + reach)} {n(start[1] - reach / 3)}, "
        f"{n(right + reach)} {n(end[1] + reach / 3)}, {n(end[0])} {n(end[1])}"
    )
    return SelfLoop(path, start, 0, end, 0)


def angle(a: Point, b: Point) -> float:
    """The angle of the direction from ``a`` to ``b``."""
    return math.atan2(b[1] - a[1], b[0] - a[0])


def end_marker(point: Point, direction: float, *, optional: bool, many: bool) -> Marker:
    """The crow's-foot marker at ``point``; ``direction`` points away from the box."""
    cos, sin = math.cos(direction), math.sin(direction)

    def at(along: float, across: float) -> tuple[str, str]:
        return (
            _fixed(point[0] + along * cos - across * sin),
            _fixed(point[1] + along * sin + across * cos),
        )

    def segment(a: tuple[float, float], b: tuple[float, float]) -> str:
        (ax, ay), (bx, by) = at(*a), at(*b)
        return f"M {ax} {ay} L {bx} {by}"

    parts: list[str] = []
    if many:
        parts += [segment((12, 0), (0, -7)), segment((12, 0), (0, 7))]
    else:
        parts.append(segment((6, -7), (6, 7)))
    circle: str | None = None
    if optional:
        r = 4
        cx, cy = (float(v) for v in at(20, 0))
        n = js_number
        circle = f"M {n(cx + r)} {n(cy)} a {r} {r} 0 1 0 {-2 * r} 0 a {r} {r} 0 1 0 {2 * r} 0"
    else:
        parts.append(segment((18, -7), (18, 7)))
    return Marker(" ".join(parts), circle)
