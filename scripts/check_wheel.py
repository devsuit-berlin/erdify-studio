"""Check that a built wheel ships the frontend and the CLI entry point.

Usage: ``python scripts/check_wheel.py DIST_DIR`` (exactly one wheel in DIST_DIR).
The frontend is gitignored and only lands in the wheel when ``poe frontend`` ran
before ``uv build``; this guards the release against a wheel without it.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

STATIC = "erdify_studio/_static/"


def problems(wheel: Path) -> list[str]:
    """Return what is missing from ``wheel`` (empty when it is complete)."""
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        entry_points = next(
            (zf.read(n).decode() for n in names if n.endswith(".dist-info/entry_points.txt")),
            "",
        )
    found: list[str] = []
    if f"{STATIC}index.html" not in names:
        found.append(f"{STATIC}index.html is missing (run `poe frontend` before building)")
    if not any(n.startswith(f"{STATIC}assets/") and n.endswith(".js") for n in names):
        found.append(f"no JavaScript bundle under {STATIC}assets/")
    if "erdify-studio = erdify_studio.cli:main" not in entry_points:
        found.append("console script `erdify-studio` is missing")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_wheel.py DIST_DIR", file=sys.stderr)
        return 2
    wheels = sorted(Path(argv[0]).glob("*.whl"))
    if len(wheels) != 1:
        print(f"expected exactly one wheel in {argv[0]!r}, found {len(wheels)}", file=sys.stderr)
        return 1
    found = problems(wheels[0])
    for problem in found:
        print(f"{wheels[0].name}: {problem}", file=sys.stderr)
    if not found:
        print(f"{wheels[0].name}: OK")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
