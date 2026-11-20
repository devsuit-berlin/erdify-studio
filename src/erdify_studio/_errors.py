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
    """Two entities map to the same layout key."""
