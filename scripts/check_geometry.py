"""Check that the SVG export draws the canvas's geometry.

Reads the JSON ``scripts/geometry_parity.mjs`` prints (``frontend/src/geometry.ts`` run
on ``scripts/geometry_cases.json``) from stdin, runs the Python port
(``erdify_studio._geometry``) on the same cases and compares every number within
one unit in the second decimal. Exits 1 naming the first case that differs. Run in CI:

    node scripts/geometry_parity.mjs | uv run python scripts/check_geometry.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from erdify_studio._geometry import (
    Rect,
    border_point,
    edge_line,
    end_marker,
    fan_offsets,
    self_loop,
)

CASES = Path(__file__).with_name("geometry_cases.json")
#: One unit in the last place of a 2-decimal number: toFixed rounds the exact binary
#: value, the port a value snapped to 9 decimals (see ``_geometry.fixed2``).
TOLERANCE = 0.0101
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:e[-+]?\d+)?")


def _rect(values: list[float]) -> Rect:
    return Rect(*values)


def python_results(cases: dict[str, Any]) -> dict[str, Any]:
    """The Python port's results, shaped like the Node script's JSON."""
    return {
        "border_point": [
            list(border_point(_rect(c["rect"]), tuple(c["toward"]), _start(c)))
            for c in cases["border_point"]
        ],
        "fan_offsets": [fan_offsets([tuple(e) for e in edges]) for edges in cases["fan_offsets"]],
        "edge_line": [
            [
                list(p)
                for p in edge_line(_rect(c["a"]), _rect(c["b"]), c["offset"], c["aKey"], c["bKey"])
            ]
            for c in cases["edge_line"]
        ],
        "self_loop": [_loop(self_loop(_rect(c["rect"]), c["index"])) for c in cases["self_loop"]],
        "end_marker": [
            _marker(
                end_marker(
                    tuple(c["point"]), c["direction"], optional=c["optional"], many=c["many"]
                )
            )
            for c in cases["end_marker"]
        ],
    }


def _start(case: dict[str, Any]) -> tuple[float, float] | None:
    return tuple(case["start"]) if "start" in case else None


def _loop(loop: Any) -> dict[str, Any]:
    return {"path": loop.path, "start": list(loop.start), "end": list(loop.end)}


def _marker(marker: Any) -> dict[str, Any]:
    return {"lines": marker.lines, "circle": marker.circle}


def difference(expected: Any, actual: Any, where: str) -> str | None:
    """The first place ``actual`` differs from ``expected``; None when they match."""
    if isinstance(expected, str) and isinstance(actual, str):
        a, b = _NUMBER.findall(expected), _NUMBER.findall(actual)
        if _NUMBER.sub("#", expected) != _NUMBER.sub("#", actual) or len(a) != len(b):
            return f"{where}: {actual!r} != {expected!r}"
        expected, actual = [float(x) for x in a], [float(x) for x in b]
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            return f"{where}: keys {sorted(actual)} != {sorted(expected)}"
        for key in expected:
            found = difference(expected[key], actual[key], f"{where}.{key}")
            if found:
                return found
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{where}: {len(actual)} items != {len(expected)}"
        for i, (e, a) in enumerate(zip(expected, actual, strict=True)):
            found = difference(e, a, f"{where}[{i}]")
            if found:
                return found
        return None
    if expected is None or actual is None:
        return None if expected is actual else f"{where}: {actual!r} != {expected!r}"
    if abs(float(expected) - float(actual)) > TOLERANCE:
        return f"{where}: {actual!r} != {expected!r}"
    return None


def main() -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    canvas = json.load(sys.stdin)
    found = difference(canvas, python_results(cases), "geometry")
    if found:
        print(f"check_geometry: the SVG export differs from the canvas at {found}", file=sys.stderr)
        return 1
    count = sum(len(v) for v in cases.values())
    print(f"check_geometry: {count} cases match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
