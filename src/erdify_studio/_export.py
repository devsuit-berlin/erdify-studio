"""Every diagram as an SVG file in ``[tool.erdify-studio] export_dir``.

``overview.svg`` holds the overview, ``groups/<slug>.svg`` each group diagram
(``DEFAULT_GROUP`` as ``groups/ungrouped.svg``). The export owns these files only: it
deletes ``groups/*.svg`` of groups that no longer exist and touches nothing else in
``export_dir``. Positions come from the layout file, so exporting needs an up-to-date
layout (``check_project`` without problems).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from erdify import Project

from erdify_studio._check import Problem, check_project
from erdify_studio._config import StudioConfig
from erdify_studio._diagrams import Diagrams, _checked, build_diagrams
from erdify_studio._errors import ExportError, LayoutConflictError, LayoutError, PositionsError
from erdify_studio._layout import DEFAULT_GROUP, OVERVIEW, Layout
from erdify_studio._svg import render_svg

_OVERVIEW_FILE = PurePosixPath("overview.svg")
_GROUPS = PurePosixPath("groups")
_NOT_SLUG = re.compile(r"[^a-z0-9]+")

SvgProblemKind = Literal["missing", "outdated", "stale"]


class OutOfDateLayoutError(ExportError):
    """The layout file is missing or doesn't match the diagrams: nothing to export from.

    Attributes:
        problems: ``check_project``'s problems; None when there is no layout file.
    """

    def __init__(self, problems: list[Problem] | None) -> None:
        super().__init__("the layout file is out of date; run `erdify-studio place --auto`")
        self.problems = problems


@dataclass(frozen=True)
class ExportResult:
    """What ``export_project`` changed, as paths relative to ``export_dir``."""

    written: tuple[PurePosixPath, ...]
    deleted: tuple[PurePosixPath, ...]


@dataclass(frozen=True)
class SvgProblem:
    """An SVG in ``export_dir`` that differs from what the export would write."""

    path: Path
    kind: SvgProblemKind

    def message(self, shown: str) -> str:
        """One ``check`` line, with the path as the user sees it (``shown``)."""
        what = {"missing": "is missing", "outdated": "is out of date", "stale": "is stale"}
        return f"export {shown!r} {what[self.kind]}"


def slug(name: str) -> str:
    """``name`` as a file name: ASCII, lowercase, ``-`` between words; ``group`` if empty."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return _NOT_SLUG.sub("-", ascii_name.lower()).strip("-") or "group"


def export_paths(diagrams: Iterable[str]) -> dict[str, PurePosixPath]:
    """Map every diagram name to its file, relative to ``export_dir``.

    Raises:
        ExportError: Two groups would share a file.
    """
    paths: dict[str, PurePosixPath] = {}
    owners: dict[PurePosixPath, str] = {}
    for name in diagrams:
        if name == OVERVIEW:
            path = _OVERVIEW_FILE
        else:
            path = _GROUPS / f"{'ungrouped' if name == DEFAULT_GROUP else slug(name)}.svg"
        if path in owners:
            raise ExportError(
                f"groups {owners[path]!r} and {name!r} would both be exported as "
                f"{str(path)!r}; rename one"
            )
        owners[path] = name
        paths[name] = path
    return paths


def export_files(project: Project, config: StudioConfig) -> dict[PurePosixPath, str]:
    """Every SVG the export writes (path relative to ``export_dir`` -> text).

    Raises:
        ExportError: No ``export_dir``, or two groups would share a file.
        OutOfDateLayoutError: The layout file is missing or out of date.
        StudioError, OSError: As ``check_project`` / ``build_diagrams`` raise them.
    """
    _export_dir(config)
    problems = check_project(project, config)
    if problems is None or problems:
        raise OutOfDateLayoutError(problems)
    payload = build_diagrams(project, config, shown_path=str(config.layout))
    paths = export_paths(d["name"] for d in payload["diagrams"])
    return {
        paths[d["name"]]: render_svg(d, payload["boxes"], payload["metrics"])
        for d in payload["diagrams"]
    }


def export_project(project: Project, config: StudioConfig) -> ExportResult:
    """Write every SVG to ``export_dir`` and delete stale ``groups/*.svg``.

    Unchanged files are not rewritten. Raises as ``export_files``, plus ``OSError``
    when a file cannot be written or deleted.
    """
    directory = _export_dir(config)
    files = export_files(project, config)
    _fix_case(directory, files)
    written: list[PurePosixPath] = []
    for relative, text in sorted(files.items()):
        path = directory / relative
        if _read(path) != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            written.append(relative)
    deleted: list[PurePosixPath] = []
    for relative in _stale(directory, files):
        (directory / relative).unlink()
        deleted.append(relative)
    return ExportResult(tuple(written), tuple(deleted))


def check_exports(project: Project, config: StudioConfig) -> list[SvgProblem]:
    """How the SVGs in ``export_dir`` differ from what the export writes, sorted by path.

    Raises as ``export_files``.
    """
    directory = _export_dir(config)
    files = export_files(project, config)
    problems: list[SvgProblem] = []
    for relative, text in files.items():
        current = _read(directory / relative)
        if current is None:
            problems.append(SvgProblem(directory / relative, "missing"))
        elif current != text:
            problems.append(SvgProblem(directory / relative, "outdated"))
    problems += [SvgProblem(directory / r, "stale") for r in _stale(directory, files)]
    return sorted(problems, key=lambda p: p.path.as_posix())


def build_studio(project: Project, config: StudioConfig, *, shown_path: str) -> Diagrams:
    """``build_diagrams`` plus what studio shows about the SVGs in ``export_dir``.

    ``pending.svgs`` counts the SVGs ``check`` would report; it stays 0 without
    ``export_dir``, while the layout file is out of date (Save fixes both at once), and
    when two groups would share a file (Save reports that). ``exportPath`` is
    ``export_dir`` as the UI shows it.
    """
    payload = build_diagrams(project, config, shown_path=shown_path)
    if config.export_dir is None:
        return payload
    payload["exportPath"] = _shown(config.export_dir)
    try:
        payload["pending"]["svgs"] = len(check_exports(project, config))
    except ExportError:
        pass
    return payload


def render_download(
    project: Project, config: StudioConfig, diagram: str, positions: object
) -> tuple[str, str]:
    """One diagram as SVG with ``positions`` (unsaved ones included), for a download.

    Needs no ``export_dir`` and writes nothing. Returns the file name
    (``overview.svg`` or ``<slug>.svg``) and the SVG.

    Raises:
        LayoutConflictError: No such diagram, or other boxes than it shows: the models
            changed since the page loaded.
        PositionsError: ``positions`` is not an object, or a position is not a pair of
            finite numbers within the coordinate limit.
    """
    payload = build_diagrams(project, config, shown_path=str(config.layout))
    found = next((d for d in payload["diagrams"] if d["name"] == diagram), None)
    if found is None:
        raise LayoutConflictError(
            f"the models changed since the page loaded (no diagram {diagram!r} any more); "
            "reload the page"
        )
    shown = frozenset(found["own"]) | frozenset(found["foreign"])
    layout = Layout()
    for key, (x, y) in _checked(positions, shown).items():
        try:
            layout.set_position(diagram, key, x, y)
        except LayoutError as e:
            raise PositionsError(str(e)) from None
    found["positions"] = {key: [x, y] for key, (x, y) in layout.diagrams[diagram].items()}
    name = "overview.svg" if diagram == OVERVIEW else export_paths([diagram])[diagram].name
    return name, render_svg(found, payload["boxes"], payload["metrics"])


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _export_dir(config: StudioConfig) -> Path:
    if config.export_dir is None:
        raise ExportError("set [tool.erdify-studio] export_dir to export SVGs")
    return config.export_dir


def _read(path: Path) -> str | None:
    """The file's text with ``\n`` line endings; None when it doesn't exist.

    git with ``core.autocrlf`` (the default on Windows runners) checks the SVGs out
    with CRLF; they are still current.
    """
    try:
        with path.open(encoding="utf-8", newline="") as file:
            return file.read().replace("\r\n", "\n")
    except FileNotFoundError:
        return None


def _owned(directory: Path) -> list[Path]:
    """The ``groups/*.svg`` files in ``directory``: suffix compared case-sensitively,
    so a user's ``photo.SVG`` is never the export's (glob ignores case on Windows)."""
    groups = directory / _GROUPS
    if not groups.is_dir():
        return []
    return sorted(p for p in groups.iterdir() if p.suffix == ".svg" and p.is_file())


def _stale(directory: Path, files: dict[PurePosixPath, str]) -> list[PurePosixPath]:
    # Compared case-insensitively: on macOS and Windows `Core.svg` *is* `core.svg`,
    # so deleting it as stale would delete the file just compared.
    wanted = {path.name.lower() for path in files}
    return [_GROUPS / p.name for p in _owned(directory) if p.name.lower() not in wanted]


def _fix_case(directory: Path, files: dict[PurePosixPath, str]) -> None:
    """Rename ``groups/Core.svg`` to the exported ``groups/core.svg``."""
    names = {path.name.lower(): path.name for path in files if path.parent == _GROUPS}
    for path in _owned(directory):
        name = names.get(path.name.lower())
        if name is not None and name != path.name:
            path.rename(path.with_name(name))
