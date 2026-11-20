"""erdify-studio: interactive, persistent ERD layouts for erdify."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("erdify-studio")
except PackageNotFoundError:  # pragma: no cover - running from source without installed metadata
    __version__ = "0.0.0"

__all__ = ["__version__"]
