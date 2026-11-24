"""Command-line entry point: ``erdify-studio``."""

from __future__ import annotations

import argparse
import sys
import traceback
import webbrowser
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

import erdify

from erdify_studio import __version__, _server
from erdify_studio._check import Problem, check_project
from erdify_studio._config import StudioConfig, load_config
from erdify_studio._diagrams import build_diagrams
from erdify_studio._errors import StudioError
from erdify_studio._export import OutOfDateLayoutError, check_exports, export_project
from erdify_studio._place import place_project

#: Exit code of a failed check (out-of-date layout).
EXIT_CHECK_FAILED = 1
#: Exit code when the project, its config or the layout file cannot be read, or on a bug.
EXIT_ERROR = 2

#: What ``main`` treats as the start of a command line that names no command.
_TOP_LEVEL = frozenset({"check", "place", "export", "open", "-h", "--help", "--version"})

_EXPORT_HINT = "hint: run `erdify-studio export` to write the SVGs"
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
    open_ = commands.add_parser(
        "open",
        help="open the canvas in the browser (the default command)",
        description=(
            "Serve the canvas on 127.0.0.1 and open it in the browser: drag the "
            "entities, then Save writes the layout file. Runs until Ctrl+C. A path "
            "named like a command is given as ./check."
        ),
    )
    open_.add_argument(
        "--port", type=_port, default=0, help="port to serve on (default: a free one)"
    )
    open_.add_argument(
        "--no-browser",
        dest="browser",
        action="store_false",
        help="print the URL instead of opening a browser",
    )
    _add_path(open_)
    check = commands.add_parser(
        "check",
        help="exit 1 if the committed layout or SVGs are out of date",
        description=(
            "Exit 1 if an entity or foreign box has no position, or the layout file holds "
            "stale entries or diagrams; with export_dir set, also if an exported SVG is "
            "missing, out of date or stale. Print one line per problem. Exit 0 without "
            "output when the layout and the SVGs match the models."
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
    export = commands.add_parser(
        "export",
        help="write one SVG per diagram to export_dir",
        description=(
            "Write overview.svg and groups/<group>.svg to [tool.erdify-studio] "
            "export_dir, byte-identical on every machine, and delete groups/*.svg of "
            "groups that no longer exist. Exits 1 while the layout file is out of date."
        ),
    )
    _add_path(export)
    return parser


def _port(value: str) -> int:
    """A TCP port for ``--port``: 0 (a free one) to 65535."""
    try:
        port = int(value)
    except ValueError:
        port = -1
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"must be 0 to 65535, got {value!r}")
    return port


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
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in _TOP_LEVEL:
        argv.insert(0, "open")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "open":
            return _open(args.path, port=args.port, browser=args.browser)
        if args.command == "place":
            return _place(args.path)
        if args.command == "export":
            return _export(args.path)
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
    if problems is None or problems:
        _print_layout_problems(config, problems)
        return EXIT_CHECK_FAILED
    if config.export_dir is None:
        return 0
    svgs = check_exports(project, config)
    if not svgs:
        return 0
    for svg in svgs:
        print(svg.message(_display(svg.path)), file=sys.stderr)
    print(_EXPORT_HINT, file=sys.stderr)
    return EXIT_CHECK_FAILED


def _print_layout_problems(config: StudioConfig, problems: list[Problem] | None) -> None:
    shown = _display(config.layout)
    if problems is None:
        print(f"{shown}: no layout file yet", file=sys.stderr)
    for problem in problems or ():
        print(f"{shown}: {problem}", file=sys.stderr)
    print(_HINT, file=sys.stderr)


def _export(path: Path) -> int:
    project, config = _load(path)
    try:
        result = export_project(project, config)
    except OutOfDateLayoutError as e:
        _print_layout_problems(config, e.problems)
        return EXIT_CHECK_FAILED
    directory = config.export_dir
    assert directory is not None  # export_project raised otherwise
    for relative in result.written:
        print(f"{Path(_display(directory / relative)).as_posix()}: wrote")
    for relative in result.deleted:
        print(f"{Path(_display(directory / relative)).as_posix()}: deleted")
    if not result.written and not result.deleted:
        print(f"{Path(_display(directory)).as_posix()}: SVGs up to date")
    return 0


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


def _open(path: Path, *, port: int, browser: bool) -> int:
    if not (_server.STATIC_DIR / "index.html").is_file():
        print(
            "erdify-studio: error: the canvas is not built (from a source checkout: "
            "run `uv run poe frontend`)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    # The server's first load is the only one at startup, so config warnings appear once.
    server = _server.start_server(lambda: _load(path), port=port, display=_display)
    try:
        # Fail before serving, like `check`: no entities, an unreadable layout file.
        snapshot = server.snapshot()
        build_diagrams(
            snapshot.project, snapshot.config, shown_path=_display(snapshot.config.layout)
        )
    except BaseException:
        server.server_close()
        raise
    try:
        print(f"erdify-studio: serving {server.url} (Ctrl+C to stop)", flush=True)
        if browser:
            webbrowser.open(server.url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
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
