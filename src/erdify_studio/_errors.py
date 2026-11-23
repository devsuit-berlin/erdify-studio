"""Exceptions raised by erdify-studio."""


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
    """The layout file changed since the positions to save were read from it."""


class ExportError(StudioError):
    """SVGs that cannot be exported: no ``export_dir``, or two groups sharing a file name."""
