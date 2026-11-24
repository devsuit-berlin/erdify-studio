"""Every diagram as an SVG file in ``[tool.erdify-studio] export_dir``.

``overview.svg`` holds the overview, ``groups/<slug>.svg`` each group diagram
(``DEFAULT_GROUP`` as ``groups/ungrouped.svg``). The export owns these files only: it
deletes ``groups/*.svg`` of groups that no longer exist and touches nothing else in
``export_dir``. Positions come from the layout file, so exporting needs an up-to-date
layout (``check_project`` without problems).
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from erdify import Project

from erdify_studio._check import Problem, check_project, project_diagrams
from erdify_studio._config import StudioConfig
from erdify_studio._diagrams import (
    Diagrams,
    build_diagrams,
    build_from,
    checked_positions,
    layout_revision,
)
from erdify_studio._errors import ExportError, LayoutConflictError, LayoutError, PositionsError
from erdify_studio._layout import DEFAULT_GROUP, OVERVIEW, Layout, load_existing_layout
from erdify_studio._svg import render_svg

logger = logging.getLogger(__name__)

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
        return f"export {Path(shown).as_posix()!r} {what[self.kind]}"


def slug(name: str) -> str:
    """``name`` as a file name: ASCII, lowercase, ``-`` between words.

    A name with no Latin letters or digits left (``Заказы``, ``顧客``) becomes
    ``group-<first 8 hex digits of its UTF-8 SHA-1>``: stable, and distinct per name.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    found = _NOT_SLUG.sub("-", ascii_name.lower()).strip("-")
    return found or f"group-{hashlib.sha1(name.encode()).hexdigest()[:8]}"


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
            # The entities without a group can't be renamed: name the group that can.
            named = [n for n in (owners[path], name) if n != DEFAULT_GROUP]
            fix = f"rename group {named[0]!r}" if len(named) == 1 else "rename one of the groups"
            raise ExportError(
                f"{_described(owners[path])} and {_described(name)} would both be exported "
                f"as {str(path)!r}; {fix}"
            )
        owners[path] = name
        paths[name] = path
    return paths


def _described(name: str) -> str:
    return "the entities without a group" if name == DEFAULT_GROUP else f"group {name!r}"


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
    return _files(build_diagrams(project, config, shown_path=str(config.layout)))


def _files(payload: Diagrams) -> dict[PurePosixPath, str]:
    """Every SVG of ``payload`` (path relative to ``export_dir`` -> text)."""
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
        if _read(path) != text.encode():
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
    return _compare(_export_dir(config), export_files(project, config))


def _compare(directory: Path, files: dict[PurePosixPath, str]) -> list[SvgProblem]:
    problems: list[SvgProblem] = []
    for relative, text in files.items():
        current = _read(directory / relative)
        if current is None:
            problems.append(SvgProblem(directory / relative, "missing"))
        elif current != text.encode():
            problems.append(SvgProblem(directory / relative, "outdated"))
    problems += [SvgProblem(directory / r, "stale") for r in _stale(directory, files)]
    return sorted(problems, key=lambda p: p.path.as_posix())


def build_studio(project: Project, config: StudioConfig, *, shown_path: str) -> Diagrams:
    """``build_diagrams`` plus what studio shows about the SVGs in ``export_dir``.

    ``pending.svgs`` counts the SVGs ``check`` would report; it stays 0 without
    ``export_dir``, while the layout file is out of date (Save fixes both at once), and
    when two groups would share a file or ``export_dir`` can't be read (Save and
    ``export`` report those). ``exportPath`` is
    ``export_dir`` as the UI shows it.
    """
    payload = build_diagrams(project, config, shown_path=shown_path)
    if config.export_dir is None:
        return payload
    payload["exportPath"] = _shown(config.export_dir)
    pending = payload["pending"]
    if pending["created"] or pending["placed"] or pending["dropped"]:
        return payload  # the layout is out of date: Save fixes it and the SVGs at once
    try:
        # The payload's positions are the layout file's here: render from it again
        # instead of building it a second time (what `check_exports` does).
        payload["pending"]["svgs"] = len(_compare(_export_dir(config), _files(payload)))
    except (ExportError, OSError) as e:
        # Studio must still open; Save and `export` report the problem.
        logger.info(f"cannot compare the SVGs in {str(config.export_dir)!r}: {e}")
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
            "reload the page",
            reason="models",
        )
    shown = frozenset(found["own"]) | frozenset(found["foreign"])
    layout = Layout()
    for key, (x, y) in checked_positions(positions, shown).items():
        try:
            layout.set_position(diagram, key, x, y)
        except LayoutError as e:
            raise PositionsError(str(e)) from None
    placed = layout.diagrams.get(diagram, {})  # an empty diagram has no entries
    found["positions"] = {key: [x, y] for key, (x, y) in placed.items()}
    name = "overview.svg" if diagram == OVERVIEW else export_paths([diagram])[diagram].name
    return name, render_svg(found, payload["boxes"], payload["metrics"])


def merge_studio(
    project: Project, config: StudioConfig, positions: object, *, shown_path: str
) -> Diagrams:
    """``build_studio`` for the page's on-screen ``positions`` (unsaved ones included).

    The starting layout is the layout file's, overridden by ``positions``: a box the
    page lacks but the file has gets its committed position back; only boxes in
    neither are placed (next to the others) and listed as ``new``. Positions of keys
    or diagrams the project no longer has are ignored. ``pending`` is relative to the
    layout file, as Save would change it.

    Raises:
        PositionsError: ``positions`` or a diagram is not an object, or a position is
            not a pair of finite numbers within the coordinate limit.
        LayoutError, OSError: The layout file cannot be read.
    """
    if not isinstance(positions, Mapping):
        raise PositionsError(f"diagrams must be an object, got {type(positions).__name__!r}")
    existing = load_existing_layout(config.layout)
    start = Layout({name: dict(p) for name, p in (existing or Layout()).diagrams.items()})
    contents = project_diagrams(project, config)
    for name, sent in positions.items():
        if name not in contents:
            continue
        if not isinstance(sent, Mapping):
            raise PositionsError(f"positions must be an object, got {type(sent).__name__!r}")
        shown = contents[name].shown
        known = {key: value for key, value in sent.items() if key in shown}
        for key, (x, y) in checked_positions(known, frozenset(known)).items():
            try:
                start.set_position(name, key, x, y)
            except LayoutError as e:
                raise PositionsError(str(e)) from None
    payload = build_from(project, config, start, created=existing is None)
    from_file = build_studio(project, config, shown_path=shown_path)
    payload["revision"] = layout_revision(config.layout)
    payload["layoutPath"] = shown_path
    payload["exportPath"] = from_file["exportPath"]
    payload["pending"] = from_file["pending"]
    return payload


def _shown(path: Path) -> str:
    """``path`` relative to the working directory when inside it, with ``/`` (as committed)."""
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _export_dir(config: StudioConfig) -> Path:
    if config.export_dir is None:
        raise ExportError("set [tool.erdify-studio] export_dir to export SVGs")
    # Checked up front: reading through a file fails differently per OS (Windows says
    # "not found", so every SVG would look missing).
    if config.export_dir.exists() and not config.export_dir.is_dir():
        raise ExportError(f"export_dir {str(config.export_dir)!r} is not a folder")
    return config.export_dir


def _read(path: Path) -> bytes | None:
    """The file's bytes with ``\n`` line endings; None when it doesn't exist.

    Bytes, not text: a file that isn't UTF-8 is simply different, not an error. git
    with ``core.autocrlf`` (the default on Windows runners) checks the SVGs out with
    CRLF; they are still current.
    """
    try:
        return path.read_bytes().replace(b"\r\n", b"\n")
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
    wanted = {path.name.lower(): path.name for path in files if path.parent == _GROUPS}
    stale: list[PurePosixPath] = []
    for path in _owned(directory):
        name = wanted.get(path.name.lower())
        if name == path.name:
            continue
        if name is not None and not _distinct(path, path.with_name(name)):
            continue  # a case variant of a wanted file: renamed, not deleted
        stale.append(_GROUPS / path.name)
    return stale


def _distinct(path: Path, other: Path) -> bool:
    """Whether ``other`` exists as a file of its own (a case-sensitive file system
    holding both ``Core.svg`` and ``core.svg``)."""
    return other.exists() and not path.samefile(other)


def _fix_case(directory: Path, files: dict[PurePosixPath, str]) -> None:
    """Rename ``groups/Core.svg`` to the exported ``groups/core.svg``."""
    names = {path.name.lower(): path.name for path in files if path.parent == _GROUPS}
    for path in _owned(directory):
        name = names.get(path.name.lower())
        if name is not None and name != path.name and not _distinct(path, path.with_name(name)):
            path.rename(path.with_name(name))
