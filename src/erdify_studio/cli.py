"""Command-line entry point: ``erdify-studio``."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib.metadata import version

from erdify_studio import __version__


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser of the ``erdify-studio`` command."""
    parser = argparse.ArgumentParser(
        prog="erdify-studio",
        description=("Arrange erdify ERDs by drag and drop, commit the layout and check it in CI."),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__} (erdify {version('erdify')})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    build_parser().parse_args(argv)
    return 0
