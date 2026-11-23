"""Exceptions raised by erdify-studio."""

from typing import Literal


class StudioError(Exception):
    """Base for all errors raised by erdify-studio."""


class ConfigError(StudioError):
    """An invalid ``[tool.erdify-studio]`` table or value."""


class LayoutError(StudioError):
    """A layout file that cannot be read, or entities that cannot be laid out."""


class LayoutVersionError(LayoutError):
    """A layout file of a version this erdify-studio does not support."""


class DuplicateKeyError(LayoutError):
    """An entity keyed by its erdify name (its own key was shared) has another entity's key."""


class ProjectError(StudioError):
    """A project studio cannot lay out, e.g. one without entities."""


class PositionsError(StudioError):
    """Positions sent to save that do not match the diagram's boxes."""


class LayoutConflictError(LayoutError):
    """The positions to save no longer fit: the layout file or the models changed.

    Attributes:
        reason: ``"layout"`` when the layout file changed since the positions were
            read from it, ``"models"`` when the project now has other boxes or diagrams.
    """

    def __init__(self, message: str, reason: Literal["layout", "models"] = "layout") -> None:
        super().__init__(message)
        self.reason = reason


class ExportError(StudioError):
    """SVGs that cannot be exported: no ``export_dir``, or two groups sharing a file name."""
