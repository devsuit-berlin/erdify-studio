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
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from erdify_studio._errors import LayoutError, LayoutVersionError

#: The layout file format this erdify-studio reads and writes.
LAYOUT_VERSION = 1
#: The diagram with every entity.
OVERVIEW = "_overview"
#: The group of entities without a value for the grouping.
DEFAULT_GROUP = "_default"

#: Largest absolute coordinate a position may have, in canvas units.
MAX_COORDINATE = 10**9

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
        """Place ``key`` at ``(x, y)`` on ``diagram``, rounded to integers.

        Raises:
            LayoutError: ``x`` or ``y`` is not a finite number within
                ``MAX_COORDINATE`` (booleans are refused).
        """
        try:
            if isinstance(x, bool) or isinstance(y, bool):
                raise TypeError
            # int(): round() returns what __round__ does, e.g. numpy.int64 for numpy.
            position = (int(round(x)), int(round(y)))
            if not _is_position(position):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise LayoutError(
                f"position of {key!r} must be finite numbers, got ({_show(x)}, {_show(y)})"
            ) from None
        self.diagrams.setdefault(diagram, {})[key] = position


def dumps_layout(layout: Layout) -> str:
    """Return the file content for ``layout``: sorted, one entry per line.

    Raises:
        LayoutError: A diagram name or key is not a string, or a position is not two
            integers (set positions with ``Layout.set_position``).
    """
    _check_types(layout)
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
    except (ValueError, RecursionError) as e:
        # JSONDecodeError, plus what json raises past it: an integer over Python's
        # digit limit (ValueError) or arrays nested too deep (RecursionError).
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
        if not _is_text(name):
            raise LayoutError(f"diagram name {name!r} is not valid UTF-8 text in {source}")
        if not isinstance(positions, dict):
            raise LayoutError(f"diagram {name!r} must be an object in {source}")
        layout.add_diagram(name)
        for key, value in positions.items():
            if not _is_text(key):
                raise LayoutError(
                    f"key {key!r} in diagram {name!r} is not valid UTF-8 text in {source}"
                )
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
        LayoutError: The file cannot be read or is not a valid layout.
    """
    return loads_layout(_read(path), source=str(path))


def save_layout(layout: Layout, path: Path) -> None:
    """Write ``layout`` to ``path``, creating missing folders.

    The file is replaced atomically (written to a temporary file, flushed to disk,
    then renamed over it) and keeps its permissions (POSIX mode bits; on Windows
    only the read-only flag exists). A symlinked ``path`` updates the file it
    points to. An existing file is only replaced when it is a valid layout of this
    version or empty: a file of another ``version`` may hold positions this
    erdify-studio cannot read, and a broken one (e.g. with git conflict markers)
    holds positions that must not be lost silently.

    Raises:
        LayoutVersionError: ``path`` holds a layout of another version.
        LayoutError: ``path`` exists but is not a valid layout (fix or remove it
            first), or it cannot be written.
    """
    text = dumps_layout(layout)
    target = path.resolve()
    try:
        mode: int | None = target.stat().st_mode & 0o777
    except FileNotFoundError:
        mode = None  # new file: the temp file gets the umask, like any new file
    except OSError as e:
        raise LayoutError(f"cannot write {str(path)!r}: {e}") from e
    else:
        _refuse_to_lose_positions(target, source=str(path))
    tmp = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            if mode is not None:
                os.chmod(tmp, mode)
            os.replace(tmp, target)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    except OSError as e:
        raise LayoutError(f"cannot write {str(path)!r}: {e}") from e


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")  # tolerate a BOM added by an editor
    except FileNotFoundError:
        raise
    except UnicodeDecodeError as e:
        raise LayoutError(f"{str(path)!r} is not UTF-8: {e}") from None
    except OSError as e:
        raise LayoutError(f"cannot read {str(path)!r}: {e}") from None


def _check_types(layout: Layout) -> None:
    for name, positions in layout.diagrams.items():
        if not _is_text(name):
            raise LayoutError(f"diagram name must be a UTF-8 string, got {name!r}")
        for key, position in positions.items():
            if not _is_text(key):
                raise LayoutError(f"key in diagram {name!r} must be a UTF-8 string, got {key!r}")
            if not _is_position(position):
                raise LayoutError(
                    f"position of {key!r} in diagram {name!r} must be integers, "
                    f"got {_show(position)}; use Layout.set_position"
                )


def _refuse_to_lose_positions(path: Path, *, source: str) -> None:
    """Raise unless replacing the existing ``path`` loses nothing."""
    try:
        text = _read(path)
        if text.strip():  # an empty file (e.g. from `touch`) holds no positions
            loads_layout(text, source=source)
    except FileNotFoundError:
        return  # removed since it was found (e.g. by a git checkout): nothing to lose
    except LayoutVersionError:
        raise
    except LayoutError as e:
        raise LayoutError(f"not overwriting {source!r}: {e}") from e


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
    if type(version) is not int:
        raise LayoutError(f"'version' must be an integer, got {version!r} in {source}")
    if version > LAYOUT_VERSION:
        raise LayoutVersionError(
            f"layout file version {version} in {source}: this erdify-studio supports "
            f"{LAYOUT_VERSION}; upgrade erdify-studio to read it"
        )
    if version != LAYOUT_VERSION:
        raise LayoutVersionError(
            f"unknown layout file version {version} in {source}: "
            f"this erdify-studio supports {LAYOUT_VERSION}"
        )


def _show(value: object) -> str:
    """``repr`` of ``value``, also for an integer over Python's digit limit."""
    try:
        return repr(value)
    except ValueError:
        return f"<{type(value).__name__} too large to show>"


def _is_text(value: object) -> bool:
    """A string that can be written as UTF-8 (no lone surrogates such as ``"\\ud800"``)."""
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _is_position(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(
            isinstance(v, int) and not isinstance(v, bool) and abs(v) <= MAX_COORDINATE
            for v in value
        )
    )


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
