"""The canvas geometry in Python (a port of ``frontend/src/geometry.ts``).

``scripts/check_geometry.py`` compares the two on ``scripts/geometry_cases.json`` in
CI; these tests pin hand-checked values so a local ``poe test`` covers the port.
"""

import math

import pytest

from erdify_studio._geometry import (
    FAN_STEP,
    Rect,
    angle,
    border_point,
    center,
    edge_line,
    end_marker,
    fan_offsets,
    self_loop,
)

BOX = Rect(0, 0, 100, 50)


def test_center() -> None:
    assert center(BOX) == (50, 25)


@pytest.mark.parametrize(
    ("toward", "expected"),
    [
        ((300, 25), (100, 25)),
        ((-300, 25), (0, 25)),
        ((50, 300), (50, 50)),
        ((50, -300), (50, 0)),
        ((50, 25), (50, 25)),  # no direction: the start point
    ],
)
def test_border_point(toward: tuple[float, float], expected: tuple[float, float]) -> None:
    assert border_point(BOX, toward) == pytest.approx(expected)


def test_fan_offsets_spread_parallel_edges() -> None:
    assert fan_offsets([("a", "b"), ("b", "a"), ("a", "b")]) == [-FAN_STEP, 0, FAN_STEP]


def test_fan_offsets_give_self_edges_their_index() -> None:
    assert fan_offsets([("a", "a"), ("a", "b"), ("a", "a")]) == [0, 0, 1]


def test_edge_line_ends_on_the_borders() -> None:
    start, end = edge_line(BOX, Rect(300, 0, 100, 50), 0, "a", "b")
    assert (start, end) == ((100, 25), (300, 25))


def test_edge_line_offset_is_measured_for_the_sorted_pair() -> None:
    a, b = BOX, Rect(300, 0, 100, 50)
    assert edge_line(a, b, 16, "a", "b") == edge_line(b, a, 16, "b", "a")[::-1]


def test_self_loop_starts_and_ends_on_the_right() -> None:
    loop = self_loop(BOX, 0)
    assert (loop.start, loop.end) == ((100, 11), (100, 39))
    assert loop.path.startswith("M 100 11 C ")


def test_angle() -> None:
    assert angle((0, 0), (0, 1)) == pytest.approx(math.pi / 2)


@pytest.mark.parametrize(
    ("optional", "many", "segments", "circle"),
    [
        (False, False, 2, False),
        (True, False, 1, True),
        (False, True, 3, False),
        (True, True, 2, True),
    ],
)
def test_end_marker(optional: bool, many: bool, segments: int, circle: bool) -> None:
    marker = end_marker((0, 0), 0, optional=optional, many=many)
    assert marker.lines.count("M ") == segments
    assert (marker.circle is not None) is circle
