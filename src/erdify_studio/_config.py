"""The ``[tool.erdify-studio]`` table of ``pyproject.toml``."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

from erdify_studio._errors import ConfigError

logger = logging.getLogger(__name__)

#: How entities are grouped into diagrams besides the overview.
GroupBy = Literal["auto", "schema", "app", "module", "none"]

#: Layout file name used when ``layout`` is not configured.
DEFAULT_LAYOUT_NAME = "erdify-layout.json"

_TABLE = "erdify-studio"
_KEYS = ("layout", "group_by", "export_dir")


@dataclass(frozen=True)
class StudioConfig:
    """Resolved erdify-studio settings.

    Attributes:
        layout: The layout file. Relative paths in ``pyproject.toml`` resolve from its
            folder; the default is ``erdify-layout.json`` next to it, else in the
            working directory.
        group_by: How entities are grouped into diagrams (``GroupBy``).
        export_dir: Directory for the exported SVGs; None when nothing is exported.
    """

    layout: Path
    group_by: GroupBy
    export_dir: Path | None


def load_config(pyproject: Path | None) -> StudioConfig:
    """Read ``[tool.erdify-studio]`` from ``pyproject`` and resolve it.

    Pass the ``pyproject.toml`` erdify resolved for the project
    (``erdify.resolve_settings(path).pyproject``), so both tools read the same file.

    Args:
        pyproject: The ``pyproject.toml``, or None when the project has none (the
            defaults then resolve from the working directory).

    Raises:
        ConfigError: The file cannot be read, or a value has the wrong type.
    """
    base = pyproject.parent if pyproject is not None else Path.cwd()
    table = _read_table(pyproject) if pyproject is not None else {}
    source = str(pyproject)
    for key in sorted(set(table) - set(_KEYS)):
        logger.warning(f"unknown [tool.{_TABLE}] key {key!r} in {source}, ignored")

    group_by = table.get("group_by", "auto")
    choices = get_args(GroupBy)
    if group_by not in choices:
        raise ConfigError(
            f"[tool.{_TABLE}] 'group_by' must be one of {', '.join(choices)}, "
            f"got {group_by!r} in {source}"
        )
    layout = _path(table, "layout", base, source) or base / DEFAULT_LAYOUT_NAME
    export_dir = _path(table, "export_dir", base, source)
    return StudioConfig(layout=layout, group_by=cast(GroupBy, group_by), export_dir=export_dir)


def _read_table(pyproject: Path) -> dict[str, object]:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"cannot read {str(pyproject)!r}: {e}") from e
    tool = data.get("tool", {})
    if not isinstance(tool, dict):
        raise ConfigError(f"[tool] must be a table in {pyproject}")
    table = tool.get(_TABLE, {})
    if not isinstance(table, dict):
        raise ConfigError(f"[tool.{_TABLE}] must be a table in {pyproject}")
    return table


def _path(table: dict[str, object], key: str, base: Path, source: str) -> Path | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str) or not value:
        raise ConfigError(
            f"[tool.{_TABLE}] {key!r} must be a non-empty string, got {value!r} in {source}"
        )
    return base / value
