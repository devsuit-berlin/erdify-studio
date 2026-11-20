"""Command-line entry point: ``erdify-studio``."""

from __future__ import annotations

import argparse
import sys
import traceback
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

import erdify

from erdify_studio import __version__
from erdify_studio._check import check_project
from erdify_studio._config import StudioConfig, load_config
from erdify_studio._errors import StudioError
from erdify_studio._place import place_project

#: Exit code of a failed check (out-of-date layout).
EXIT_CHECK_FAILED = 1
#: Exit code when the project, its config or the layout file cannot be read, or on a bug.
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
    _add_path(check)
    place = commands.add_parser(
        "place",
        help="place new entities and drop stale entries (--auto)",
        description=(
            "Give every entity and foreign box without a position one next to the "
            "entities it is connected with (else in a grid right of the diagram), and "
            "drop stale entries and diagrams. Placed entities never move. Creates the "
            "layout file when there is none."
        ),
    )
    place.add_argument(
        "--auto",
        action="store_true",
        required=True,
        help="place without opening the canvas (required)",
    )
    _add_path(place)
    return parser


def _add_path(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="input directory or file, as passed to erdify (default: .)",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    args = build_parser().parse_args(argv)
    if args.command is None:
        return 0
    try:
        if args.command == "place":
            return _place(args.path)
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
    except Exception:
        # A bug, not an out-of-date layout: keep the traceback for the report, but
        # don't exit 1, which CI would read as a failed check.
        traceback.print_exc()
        print(
            "erdify-studio: internal error (please report it with the traceback above)",
            file=sys.stderr,
        )
        return EXIT_ERROR


def _load(path: Path) -> tuple[erdify.Project, StudioConfig]:
    # strict: a file erdify cannot parse would otherwise drop its tables, and their
    # positions would read as stale entries that `place --auto` deletes.
    project = erdify.load_project(path, strict=True)
    return project, load_config(project.settings.pyproject)


def _check(path: Path) -> int:
    project, config = _load(path)
    problems = check_project(project, config)
    shown = _display(config.layout)
    if problems is None:
        print(f"{shown}: no layout file yet", file=sys.stderr)
    elif not problems:
        return 0
    for problem in problems or ():
        print(f"{shown}: {problem}", file=sys.stderr)
    print(_HINT, file=sys.stderr)
    return EXIT_CHECK_FAILED


def _place(path: Path) -> int:
    project, config = _load(path)
    result = place_project(project, config)
    shown = _display(config.layout)
    for diagram in result.removed_diagrams:
        print(f"{shown}: removed stale diagram {diagram!r}")
    for diagram, key in result.removed:
        print(f"{shown}: diagram {diagram!r}: removed stale entry {key!r}")
    if not result.changed:
        print(f"{shown}: up to date")
        return 0
    changes = [
        _count(len(result.placed), "box", "boxes", "placed"),
        _count(len(result.removed), "stale entry", "stale entries", "removed"),
        _count(len(result.removed_diagrams), "stale diagram", "stale diagrams", "removed"),
    ]
    action = "created" if result.created else "updated"
    print(f"{shown}: {', '.join([action, *filter(None, changes)])}")
    return 0


def _count(n: int, one: str, many: str, verb: str) -> str:
    """``"<verb> <n> <noun>"``; empty for zero."""
    return f"{verb} {n} {one if n == 1 else many}" if n else ""


def _display(path: Path) -> str:
    """``path`` relative to the working directory when it is inside it."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
