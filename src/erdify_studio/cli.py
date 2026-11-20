"""Command-line entry point: ``erdify-studio``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

import erdify

from erdify_studio import __version__
from erdify_studio._check import check_layout, diagram_contents
from erdify_studio._config import load_config
from erdify_studio._entities import enum_key
from erdify_studio._errors import StudioError
from erdify_studio._layout import Layout, load_layout

#: Exit code of a failed check (out-of-date layout).
EXIT_CHECK_FAILED = 1
#: Exit code when the project, its config or the layout file cannot be read.
EXIT_ERROR = 2

_HINT = (
    "hint: run `erdify-studio place --auto` to place new entities and drop stale entries, "
    "or open `erdify-studio` to arrange them"
)


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
    commands = parser.add_subparsers(dest="command", metavar="command")
    check = commands.add_parser(
        "check",
        help="exit 1 if the committed layout is out of date",
        description=(
            "Exit 1 if an entity or foreign box has no position, or the layout file holds "
            "stale entries or diagrams; print one line per problem. Exit 0 without output "
            "when the layout matches the models."
        ),
    )
    check.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="input directory or file, as passed to erdify (default: .)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    args = build_parser().parse_args(argv)
    if args.command is None:
        return 0
    try:
        return _check(args.path)
    except (
        StudioError,
        erdify.ConfigError,
        erdify.ModelParseError,
        erdify.SqlDependencyError,
        OSError,
    ) as e:
        print(f"erdify-studio: error: {e}", file=sys.stderr)
        return EXIT_ERROR


def _check(path: Path) -> int:
    project = erdify.load_project(path)
    config = load_config(project.settings.pyproject)
    diagrams = diagram_contents(project.entities, config.group_by)
    shown = _display(config.layout)
    layout = _load(config.layout)
    if layout is None:
        print(f"{shown}: no layout file yet", file=sys.stderr)
        print(_HINT, file=sys.stderr)
        return EXIT_CHECK_FAILED
    # Enums are not required until erdify tells which ones it draws (erdify#369).
    enums = {enum_key(enum) for enum in project.enums.values()}
    problems = check_layout(layout, diagrams, unchecked=enums)
    if not problems:
        return 0
    for problem in problems:
        print(f"{shown}: {problem}", file=sys.stderr)
    print(_HINT, file=sys.stderr)
    return EXIT_CHECK_FAILED


def _load(path: Path) -> Layout | None:
    """The layout at ``path``; None when there is none yet (no file, or an empty one)."""
    try:
        if not path.read_text(encoding="utf-8-sig").strip():
            return None
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        pass  # load_layout reports it
    return load_layout(path)


def _display(path: Path) -> str:
    """``path`` relative to the working directory when it is inside it."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
