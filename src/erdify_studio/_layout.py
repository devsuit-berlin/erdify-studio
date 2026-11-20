"""The layout file: entity positions per diagram, written for readable git diffs.

```json
{
  "version": 1,
  "diagrams": {
    "_overview": {
      "core.customers": [120, 40],
      "order": [480, 40]
    }
  }
}
```

Diagram names and keys are sorted, one entry per line, positions are integer
``[x, y]`` (top-left, canvas units), and the file ends with a newline: the same
layout always gives the same bytes.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from erdify_studio._errors import LayoutError, LayoutVersionError

#: The layout file format this erdify-studio reads and writes.
LAYOUT_VERSION = 1
#: The diagram with every entity.
OVERVIEW = "_overview"
#: The group of entities without a value for the grouping.
DEFAULT_GROUP = "_default"

#: An entity's top-left corner on a diagram, in canvas units.
Position = tuple[int, int]


@dataclass
class Layout:
    """Entity positions per diagram.

    Attributes:
        diagrams: Diagram name (``OVERVIEW`` or a group) -> layout key -> position.
    """

    diagrams: dict[str, dict[str, Position]] = field(default_factory=dict)

    def add_diagram(self, diagram: str) -> None:
        """Add ``diagram`` without positions, if it is not there yet."""
        self.diagrams.setdefault(diagram, {})

    def set_position(self, diagram: str, key: str, x: float, y: float) -> None:
        """Place ``key`` at ``(x, y)`` on ``diagram``, rounded to integers."""
        self.diagrams.setdefault(diagram, {})[key] = (round(x), round(y))


def dumps_layout(layout: Layout) -> str:
    """Return the file content for ``layout``: sorted, one entry per line."""
    lines = ["{", f'  "version": {LAYOUT_VERSION},']
    if not layout.diagrams:
        lines.append('  "diagrams": {}')
    else:
        lines.append('  "diagrams": {')
        diagrams = sorted(layout.diagrams.items())
        for i, (name, positions) in enumerate(diagrams):
            comma = "," if i < len(diagrams) - 1 else ""
            if not positions:
                lines.append(f"    {_string(name)}: {{}}{comma}")
                continue
            lines.append(f"    {_string(name)}: {{")
            entries = sorted(positions.items())
            for j, (key, (x, y)) in enumerate(entries):
                entry_comma = "," if j < len(entries) - 1 else ""
                lines.append(f"      {_string(key)}: [{x}, {y}]{entry_comma}")
            lines.append(f"    }}{comma}")
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def loads_layout(text: str, *, source: str = "<string>") -> Layout:
    """Parse a layout file's content.

    Args:
        text: The file content.
        source: Where it comes from, for error messages.

    Raises:
        LayoutVersionError: The file is of another ``version``.
        LayoutError: The content is not a valid layout.
    """
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicates)
    except _DuplicateKey as e:
        raise LayoutError(f"duplicate key {e.key!r} in {source}") from None
    except json.JSONDecodeError as e:
        raise LayoutError(f"{source} is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise LayoutError(f"{source} must be a JSON object")
    _check_version(data, source)
    for key in data:
        if key not in ("version", "diagrams"):
            raise LayoutError(f"unknown key {key!r} in {source}")
    diagrams = data.get("diagrams")
    if not isinstance(diagrams, dict):
        raise LayoutError(f"'diagrams' must be an object in {source}")

    layout = Layout()
    for name, positions in diagrams.items():
        if not isinstance(positions, dict):
            raise LayoutError(f"diagram {name!r} must be an object in {source}")
        layout.add_diagram(name)
        for key, value in positions.items():
            if not _is_position(value):
                raise LayoutError(
                    f"position of {key!r} in diagram {name!r} must be [x, y] integers, "
                    f"got {value!r} in {source}"
                )
            layout.set_position(name, key, value[0], value[1])
    return layout


def load_layout(path: Path) -> Layout:
    """Read the layout file at ``path``.

    Raises:
        FileNotFoundError: There is no layout file yet.
        LayoutVersionError: The file is of another ``version``.
        LayoutError: The file is not a valid layout.
    """
    return loads_layout(path.read_text(encoding="utf-8"), source=str(path))


def save_layout(layout: Layout, path: Path) -> None:
    """Write ``layout`` to ``path``, creating missing folders.

    The file is replaced atomically. A file of another ``version`` is never
    overwritten: it may hold positions this erdify-studio cannot read.

    Raises:
        LayoutVersionError: ``path`` holds a layout of another version.
    """
    _refuse_other_version(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(dumps_layout(layout))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class _DuplicateKey(Exception):
    def __init__(self, key: str) -> None:
        self.key = key


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _check_version(data: dict[str, object], source: str) -> None:
    if "version" not in data:
        raise LayoutError(f"{source} has no 'version'")
    version = data["version"]
    if version != LAYOUT_VERSION or isinstance(version, bool):
        raise LayoutVersionError(
            f"layout file version {version!r} in {source}: this erdify-studio supports "
            f"{LAYOUT_VERSION}; upgrade erdify-studio to read it"
        )


def _refuse_other_version(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return  # missing or broken: nothing worth keeping
    if isinstance(data, dict) and "version" in data:
        _check_version(data, str(path))


def _is_position(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    )


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
