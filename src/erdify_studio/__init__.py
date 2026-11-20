"""erdify-studio: interactive, persistent ERD layouts for erdify."""

from importlib.metadata import PackageNotFoundError, version

from erdify_studio._config import DEFAULT_LAYOUT_NAME, GroupBy, StudioConfig, load_config
from erdify_studio._entities import entity_groups, entity_key, entity_keys, enum_key
from erdify_studio._errors import (
    ConfigError,
    DuplicateKeyError,
    LayoutError,
    LayoutVersionError,
    StudioError,
)
from erdify_studio._layout import (
    DEFAULT_GROUP,
    LAYOUT_VERSION,
    OVERVIEW,
    Layout,
    Position,
    dumps_layout,
    load_layout,
    loads_layout,
    save_layout,
)

try:
    __version__ = version("erdify-studio")
except PackageNotFoundError:  # pragma: no cover - running from source without installed metadata
    __version__ = "0.0.0"

__all__ = [
    "DEFAULT_GROUP",
    "DEFAULT_LAYOUT_NAME",
    "LAYOUT_VERSION",
    "OVERVIEW",
    "ConfigError",
    "DuplicateKeyError",
    "GroupBy",
    "Layout",
    "LayoutError",
    "LayoutVersionError",
    "Position",
    "StudioConfig",
    "StudioError",
    "__version__",
    "dumps_layout",
    "entity_groups",
    "entity_key",
    "entity_keys",
    "enum_key",
    "load_config",
    "load_layout",
    "loads_layout",
    "save_layout",
]
