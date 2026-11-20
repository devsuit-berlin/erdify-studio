"""erdify-studio."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("erdify_studio")
except PackageNotFoundError:  # running from source without installed metadata
    __version__ = "0.0.0"
