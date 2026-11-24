"""Exporting every diagram to ``export_dir``: file names, writing, deleting, checking."""

import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import erdify
import pytest

from erdify_studio import DEFAULT_GROUP, OVERVIEW, StudioConfig, load_config, place_project
from erdify_studio._diagrams import Diagrams, build_diagrams
from erdify_studio._errors import ExportError, LayoutConflictError, PositionsError
from erdify_studio._export import (
    ExportResult,
    OutOfDateLayoutError,
    SvgProblem,
    build_studio,
    check_exports,
    export_files,
    export_paths,
    export_project,
    merge_studio,
    render_download,
    slug,
)
from erdify_studio.cli import main

MODELS = """\
from sqlmodel import Field, SQLModel


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    __table_args__ = {"schema": "core"}
    id: int = Field(primary_key=True)


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"
    __table_args__ = {"schema": "billing"}
    id: int = Field(primary_key=True)
    customer_id: int = Field(foreign_key="core.customers.id")
"""

FILES = {
    PurePosixPath("overview.svg"),
    PurePosixPath("groups/billing.svg"),
    PurePosixPath("groups/core.svg"),
}


def _project(
    root: Path, models: str = MODELS, studio: str = 'export_dir = "docs/erd"\n', place: bool = True
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[tool.erdify]\ninclude = ["**/models.py"]\n[tool.erdify-studio]\n{studio}'
    )
    package = root / "shop"
    package.mkdir(exist_ok=True)
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models, encoding="utf-8")
    if place:
        project, config = _load(root)
        place_project(project, config)
    return root


def _load(root: Path) -> tuple[erdify.Project, StudioConfig]:
    project = erdify.load_project(root, strict=True)
    return project, load_config(project.settings.pyproject)


def _export(root: Path) -> ExportResult:
    project, config = _load(root)
    return export_project(project, config)


def _check(root: Path) -> list[SvgProblem]:
    project, config = _load(root)
    return check_exports(project, config)


def _svgs(root: Path) -> set[PurePosixPath]:
    out = root / "docs" / "erd"
    return {PurePosixPath(p.relative_to(out).as_posix()) for p in out.rglob("*.svg")}


# --- names -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("core", "core"),
        ("my app", "my-app"),
        ("Bestellungen/Ä", "bestellungen-a"),
        ("__x__", "x"),
        ("ü", "u"),
        ("!!!", "group-9a7b006d"),
        ("Заказы", "group-22ac8458"),
        ("shop.models", "shop-models"),
    ],
)
def test_slug(name: str, expected: str) -> None:
    assert slug(name) == expected


def test_export_paths() -> None:
    assert export_paths([OVERVIEW, "my app", DEFAULT_GROUP]) == {
        OVERVIEW: PurePosixPath("overview.svg"),
        "my app": PurePosixPath("groups/my-app.svg"),
        DEFAULT_GROUP: PurePosixPath("groups/ungrouped.svg"),
    }


@pytest.mark.parametrize(
    ("a", "b"), [("Sales", "sales"), ("my app", "my-app"), ("ungrouped", DEFAULT_GROUP)]
)
def test_groups_exported_to_the_same_file_are_an_error(a: str, b: str) -> None:
    def shown(name: str) -> str:
        return "the entities without a group" if name == DEFAULT_GROUP else repr(name)

    with pytest.raises(ExportError) as raised:
        export_paths([OVERVIEW, a, b])
    assert shown(a) in str(raised.value) and shown(b) in str(raised.value)


@pytest.mark.parametrize("names", [("ungrouped", DEFAULT_GROUP), (DEFAULT_GROUP, "ungrouped")])
def test_a_collision_with_the_default_group_names_the_group_to_rename(
    names: tuple[str, str],
) -> None:
    # The entities without a group can't be renamed: only the named group can.
    with pytest.raises(ExportError) as raised:
        export_paths([OVERVIEW, *names])
    assert "rename group 'ungrouped'" in str(raised.value)


def test_a_collision_of_two_groups_asks_to_rename_one() -> None:
    with pytest.raises(ExportError, match="rename one of the groups"):
        export_paths([OVERVIEW, "Sales", "sales"])


def test_a_collision_writes_nothing(tmp_path: Path) -> None:
    models = (
        MODELS.replace('"schema": "core"', '"schema": "Sales"')
        .replace('"schema": "billing"', '"schema": "sales"')
        .replace('foreign_key="core.customers.id"', 'foreign_key="Sales.customers.id"')
    )
    root = _project(tmp_path, models)
    with pytest.raises(ExportError, match="'Sales'"):
        _export(root)
    assert not (root / "docs").exists()


# --- export ------------------------------------------------------------------------


def test_export_writes_every_diagram(tmp_path: Path) -> None:
    root = _project(tmp_path)
    result = _export(root)
    assert set(result.written) == FILES and result.deleted == ()
    assert _svgs(root) == FILES
    project, config = _load(root)
    files = export_files(project, config)
    assert (root / "docs/erd/overview.svg").read_text() == files[PurePosixPath("overview.svg")]


def test_files_are_written_with_lf_endings(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _export(root)
    assert b"\r" not in (root / "docs/erd/overview.svg").read_bytes()


def test_a_second_export_writes_nothing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _export(root)
    result = _export(root)
    assert (result.written, result.deleted) == ((), ())


def test_stale_group_svgs_are_deleted_and_other_files_kept(tmp_path: Path) -> None:
    root = _project(tmp_path)
    out = root / "docs" / "erd"
    (out / "groups").mkdir(parents=True)
    for name in ("README.md", "old.svg", "groups/notes.txt", "groups/gone.svg"):
        (out / name).write_text("x")
    result = _export(root)
    assert result.deleted == (PurePosixPath("groups/gone.svg"),)
    for name in ("README.md", "old.svg", "groups/notes.txt"):
        assert (out / name).read_text() == "x"


def test_group_by_none_writes_the_overview_only(tmp_path: Path) -> None:
    root = _project(tmp_path, studio='export_dir = "docs/erd"\ngroup_by = "none"\n')
    groups = root / "docs" / "erd" / "groups"
    groups.mkdir(parents=True)
    (groups / "core.svg").write_text("x")
    (groups / "notes.txt").write_text("x")
    _export(root)
    assert _svgs(root) == {PurePosixPath("overview.svg")}
    assert (groups / "notes.txt").exists()


def test_a_project_without_groups_folder_gets_none(tmp_path: Path) -> None:
    root = _project(tmp_path, studio='export_dir = "docs/erd"\ngroup_by = "none"\n')
    _export(root)
    assert not (root / "docs" / "erd" / "groups").exists()


@pytest.mark.parametrize("change", ["no layout file", "unplaced entity"])
def test_export_refuses_an_out_of_date_layout(tmp_path: Path, change: str) -> None:
    root = _project(tmp_path, place=change != "no layout file")
    if change == "unplaced entity":
        (root / "shop" / "models.py").write_text(
            MODELS + '\n\nclass Audit(SQLModel, table=True):\n    __tablename__ = "audit"\n'
            "    id: int = Field(primary_key=True)\n"
        )
    with pytest.raises(OutOfDateLayoutError) as raised:
        _export(root)
    assert raised.value.problems is None if change == "no layout file" else raised.value.problems
    assert not (root / "docs").exists()


def test_without_export_dir(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    with pytest.raises(ExportError, match="export_dir"):
        _export(root)
    with pytest.raises(ExportError, match="export_dir"):
        _check(root)


# --- check -------------------------------------------------------------------------


def test_check_is_empty_when_current(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _export(root)
    assert _check(root) == []


def test_check_reports_missing_outdated_and_stale(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _export(root)
    out = root / "docs" / "erd"
    (out / "groups" / "core.svg").unlink()
    (out / "groups" / "gone.svg").write_text("x")
    # a new column makes the customers box taller: the overview changes; in billing,
    # customers is a name-only foreign box, so billing.svg stays current
    (root / "shop" / "models.py").write_text(
        MODELS.replace(
            "    id: int = Field(primary_key=True)\n\n\nclass Invoice",
            "    id: int = Field(primary_key=True)\n    email: str\n\n\nclass Invoice",
        )
    )
    assert _check(root) == [
        SvgProblem(out / "groups" / "core.svg", "missing"),
        SvgProblem(out / "groups" / "gone.svg", "stale"),
        SvgProblem(out / "overview.svg", "outdated"),
    ]


def test_svg_problem_messages(tmp_path: Path) -> None:
    path = Path("docs/erd/overview.svg")
    assert [
        SvgProblem(path, kind).message(str(path)) for kind in ("missing", "outdated", "stale")
    ] == [
        "export 'docs/erd/overview.svg' is missing",
        "export 'docs/erd/overview.svg' is out of date",
        "export 'docs/erd/overview.svg' is stale",
    ]


def test_export_is_byte_identical_from_a_copy(tmp_path: Path) -> None:
    root = _project(tmp_path / "a")
    _export(root)
    copy = tmp_path / "b"
    shutil.copytree(root, copy)
    shutil.rmtree(copy / "docs")
    _export(copy)
    for name in FILES:
        assert (copy / "docs/erd" / name).read_bytes() == (root / "docs/erd" / name).read_bytes()


# --- CLI ---------------------------------------------------------------------------


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_export_is_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "export" in capsys.readouterr().out


def test_cli_export_lists_what_it_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    (root / "docs" / "erd" / "groups").mkdir(parents=True)
    (root / "docs" / "erd" / "groups" / "gone.svg").write_text("x")
    assert _run(["export"], capsys)[:2] == (
        0,
        "docs/erd/groups/billing.svg: wrote\n"
        "docs/erd/groups/core.svg: wrote\n"
        "docs/erd/overview.svg: wrote\n"
        "docs/erd/groups/gone.svg: deleted\n",
    )
    assert _run(["export", "."], capsys)[:2] == (0, "docs/erd: SVGs up to date\n")


def test_cli_export_refuses_an_out_of_date_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, place=False)
    monkeypatch.chdir(root)
    code, _, err = _run(["export"], capsys)
    assert code == 1
    assert "erdify-layout.json: no layout file yet" in err
    assert err.rstrip().endswith("or open `erdify-studio` to arrange them")


@pytest.mark.parametrize(
    ("studio", "message"),
    [("", "set [tool.erdify-studio] export_dir to export SVGs"), ("collision", "'Sales'")],
)
def test_cli_export_errors_exit_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    studio: str,
    message: str,
) -> None:
    if studio == "collision":
        models = (
            MODELS.replace('"schema": "core"', '"schema": "Sales"')
            .replace('"schema": "billing"', '"schema": "sales"')
            .replace('foreign_key="core.customers.id"', 'foreign_key="Sales.customers.id"')
        )
        root = _project(tmp_path, models)
    else:
        root = _project(tmp_path, studio=studio)
    monkeypatch.chdir(root)
    code, _, err = _run(["export"], capsys)
    assert (code, message in err) == (2, True)


def test_cli_check_reports_svgs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    code, _, err = _run(["check"], capsys)
    assert code == 1
    assert err.splitlines() == [
        "export 'docs/erd/groups/billing.svg' is missing",
        "export 'docs/erd/groups/core.svg' is missing",
        "export 'docs/erd/overview.svg' is missing",
        "hint: run `erdify-studio export` to write the SVGs",
    ]
    _run(["export"], capsys)
    assert _run(["check"], capsys) == (0, "", "")


def test_cli_check_shows_layout_problems_before_svgs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, place=False)
    monkeypatch.chdir(root)
    code, _, err = _run(["check"], capsys)
    assert code == 1
    assert "export '" not in err  # only the layout lines while the layout is out of date


def test_cli_check_without_export_dir_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, studio="")
    monkeypatch.chdir(root)
    assert _run(["check"], capsys) == (0, "", "")


# --- studio ------------------------------------------------------------------------


def _studio(root: Path) -> Diagrams:
    project, config = _load(root)
    return build_studio(project, config, shown_path="erdify-layout.json")


def test_studio_without_export_dir_has_no_svgs_pending(tmp_path: Path) -> None:
    payload = _studio(_project(tmp_path, studio=""))
    assert (payload["pending"]["svgs"], payload["exportPath"]) == (0, None)


def test_studio_counts_outdated_svgs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    assert _studio(root)["pending"]["svgs"] == 3  # nothing exported yet
    _export(root)
    assert _studio(root)["pending"]["svgs"] == 0
    (root / "shop" / "models.py").write_text(
        MODELS.replace(
            "    id: int = Field(primary_key=True)\n\n\nclass Invoice",
            "    id: int = Field(primary_key=True)\n    email: str\n\n\nclass Invoice",
        )
    )
    payload = _studio(root)
    assert (payload["pending"]["svgs"], payload["exportPath"]) == (2, "docs/erd")


def test_studio_counts_no_svgs_while_the_layout_is_out_of_date(tmp_path: Path) -> None:
    assert _studio(_project(tmp_path, place=False))["pending"]["svgs"] == 0


# --- review fixes ------------------------------------------------------------------


def test_a_crlf_checkout_is_current(tmp_path: Path) -> None:
    """git with core.autocrlf=true (Windows CI) checks the SVGs out with CRLF."""
    root = _project(tmp_path)
    _export(root)
    for path in (root / "docs" / "erd").rglob("*.svg"):
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert _check(root) == []
    assert _export(root).written == ()


def test_a_differently_cased_file_is_not_deleted_as_stale(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _export(root)
    groups = root / "docs" / "erd" / "groups"
    (groups / "core.svg").rename(groups / "Core.svg")
    result = _export(root)
    assert PurePosixPath("groups/Core.svg") not in result.deleted
    assert {p.name.lower() for p in groups.glob("*")} >= {"core.svg", "billing.svg"}


def test_only_lowercase_svg_files_are_owned(tmp_path: Path) -> None:
    root = _project(tmp_path)
    groups = root / "docs" / "erd" / "groups"
    groups.mkdir(parents=True)
    (groups / "photo.SVG").write_text("x")
    assert _export(root).deleted == ()
    assert (groups / "photo.SVG").read_text() == "x"


# --- download one diagram ----------------------------------------------------------


def test_download_renders_the_positions_sent(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")  # no export_dir needed
    project, config = _load(root)
    payload = build_diagrams(project, config, shown_path="x")
    core = next(d for d in payload["diagrams"] if d["name"] == "core")
    moved = {**core["positions"], "core.customers": [777, 55]}
    name, svg = render_download(project, config, "core", moved)
    assert name == "core.svg"
    assert 'transform="translate(777 55)" data-key="core.customers"' in svg


@pytest.mark.parametrize(
    ("diagram", "name"), [(OVERVIEW, "overview.svg"), ("my app", "my-app.svg")]
)
def test_download_file_names(tmp_path: Path, diagram: str, name: str) -> None:
    root = _project(
        tmp_path,
        MODELS.replace('"schema": "core"', '"schema": "my app"').replace(
            'foreign_key="core.customers.id"', 'foreign_key="my app.customers.id"'
        ),
        studio="",
    )
    project, config = _load(root)
    payload = build_diagrams(project, config, shown_path="x")
    positions = next(d for d in payload["diagrams"] if d["name"] == diagram)["positions"]
    assert render_download(project, config, diagram, dict(positions))[0] == name


def test_download_of_an_unknown_diagram_is_a_conflict(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    project, config = _load(root)
    with pytest.raises(LayoutConflictError, match="'gone'"):
        render_download(project, config, "gone", {})


def test_download_with_other_boxes_is_a_conflict(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    project, config = _load(root)
    with pytest.raises(LayoutConflictError, match="models changed"):
        render_download(project, config, "core", {"core.customers": [0, 0]})


def test_download_refuses_bad_positions(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    project, config = _load(root)
    payload = build_diagrams(project, config, shown_path="x")
    core = next(d for d in payload["diagrams"] if d["name"] == "core")
    with pytest.raises(PositionsError):
        render_download(project, config, "core", {**core["positions"], "core.customers": [True, 0]})


def test_a_non_utf8_svg_is_outdated_not_a_crash(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _export(root)
    (root / "docs" / "erd" / "overview.svg").write_bytes(b"\xff\xfe<\x00s\x00")  # UTF-16
    out = root / "docs" / "erd"
    assert _check(root) == [SvgProblem(out / "overview.svg", "outdated")]
    assert _export(root).written == (PurePosixPath("overview.svg"),)


def test_studio_loads_when_export_dir_is_a_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "erd").write_text("not a folder")
    assert _studio(root)["pending"]["svgs"] == 0


def test_two_non_latin_groups_get_their_own_files() -> None:
    paths = export_paths([OVERVIEW, "Заказы", "顧客"])
    assert len(set(paths.values())) == 3


def test_a_stale_groups_overview_svg_is_deleted(tmp_path: Path) -> None:
    root = _project(tmp_path)
    groups = root / "docs" / "erd" / "groups"
    groups.mkdir(parents=True)
    (groups / "overview.svg").write_text("x")  # a group "Overview" that is gone
    assert PurePosixPath("groups/overview.svg") in _export(root).deleted


def test_download_of_an_empty_diagram(tmp_path: Path) -> None:
    root = _project(tmp_path, models="", studio="", place=False)
    (root / "pyproject.toml").write_text(
        '[tool.erdify]\ninclude = ["**/models.py"]\nallow_empty = true\n[tool.erdify-studio]\n'
    )
    project, config = _load(root)
    name, svg = render_download(project, config, OVERVIEW, {})
    assert name == "overview.svg" and svg.startswith("<svg")


def test_an_export_dir_that_is_a_file_is_an_error(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "erd").write_text("not a folder")
    with pytest.raises(ExportError, match="is not a folder"):
        _export(root)
    with pytest.raises(ExportError, match="is not a folder"):
        _check(root)


# --- follow-ups (#34) --------------------------------------------------------------


def test_a_collision_with_the_default_group_names_it_for_people() -> None:
    with pytest.raises(ExportError) as raised:
        export_paths([OVERVIEW, "ungrouped", DEFAULT_GROUP])
    assert "entities without a group" in str(raised.value)
    assert DEFAULT_GROUP not in str(raised.value)


def test_studio_builds_the_diagrams_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path)
    calls: list[int] = []
    real = build_diagrams

    def counting(*args: Any, **kwargs: Any) -> Diagrams:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr("erdify_studio._export.build_diagrams", counting)
    assert _studio(root)["pending"]["svgs"] == 3
    assert len(calls) == 1


def _case_sensitive(directory: Path) -> bool:
    (directory / "case-probe").write_text("")
    try:
        return not (directory / "CASE-PROBE").exists()
    finally:
        (directory / "case-probe").unlink()


def test_a_case_variant_next_to_the_real_file_is_stale(tmp_path: Path) -> None:
    if not _case_sensitive(tmp_path):
        pytest.skip("needs a case-sensitive file system (Linux)")
    root = _project(tmp_path)
    _export(root)
    groups = root / "docs" / "erd" / "groups"
    (groups / "Core.svg").write_text("x")
    assert _check(root) == [SvgProblem(groups / "Core.svg", "stale")]
    assert _export(root).deleted == (PurePosixPath("groups/Core.svg"),)


# --- merge on-screen positions (#7) ------------------------------------------------

AUDIT = (
    '\n\nclass Audit(SQLModel, table=True):\n    __tablename__ = "audit"\n'
    '    __table_args__ = {"schema": "core"}\n    id: int = Field(primary_key=True)\n'
    '    customer_id: int = Field(foreign_key="core.customers.id")\n'
)


def _merge(root: Path, positions: object) -> Diagrams:
    project, config = _load(root)
    return merge_studio(project, config, positions, shown_path="erdify-layout.json")


def _on_screen(root: Path) -> dict[str, dict[str, list[int]]]:
    return {d["name"]: dict(d["positions"]) for d in _studio(root)["diagrams"]}


def _diagram_of(payload: Diagrams, name: str) -> Any:
    return next(d for d in payload["diagrams"] if d["name"] == name)


def test_merge_keeps_the_positions_sent(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    screen = _on_screen(root)
    screen[OVERVIEW]["core.customers"] = [900, 900]
    merged = _merge(root, screen)
    assert _diagram_of(merged, OVERVIEW)["positions"]["core.customers"] == [900, 900]
    assert merged["pending"]["placed"] == 0


def test_merge_places_a_new_table_next_to_the_screen(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    screen = _on_screen(root)
    for name in screen:
        screen[name] = {k: [x + 5000, y + 5000] for k, (x, y) in screen[name].items()}
    (root / "shop" / "models.py").write_text(MODELS + AUDIT)
    merged = _merge(root, screen)
    overview = _diagram_of(merged, OVERVIEW)
    assert overview["new"] == ["core.audit"]
    x, y = overview["positions"]["core.audit"]
    assert x >= 4000 and y >= 4000  # next to the moved boxes, not the saved ones
    assert merged["pending"]["placed"] >= 1


def test_merge_gives_a_returning_table_its_committed_position(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    committed = _on_screen(root)[OVERVIEW]["billing.invoices"]
    screen = _on_screen(root)
    for name in screen:
        screen[name].pop("billing.invoices", None)  # the page lost it for one tick
    merged = _merge(root, screen)
    overview = _diagram_of(merged, OVERVIEW)
    assert overview["positions"]["billing.invoices"] == committed
    assert "billing.invoices" not in overview["new"]


def test_merge_drops_removed_tables_and_counts_them(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    screen = _on_screen(root)
    (root / "shop" / "models.py").write_text(
        MODELS.replace('foreign_key="core.customers.id"', "default=0").replace(
            MODELS[MODELS.index("class Customer") : MODELS.index("class Invoice")], ""
        )
    )
    merged = _merge(root, screen)
    assert "core.customers" not in _diagram_of(merged, OVERVIEW)["positions"]
    assert "core" not in [d["name"] for d in merged["diagrams"]]
    assert merged["pending"]["dropped"] >= 2  # the entry and the core diagram


def test_merge_ignores_unknown_keys_and_diagrams(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    screen: dict[str, Any] = _on_screen(root)
    screen[OVERVIEW]["gone.table"] = [1, 1]
    screen["gone"] = {"x": [0, 0]}
    merged = _merge(root, screen)
    assert "gone.table" not in _diagram_of(merged, OVERVIEW)["positions"]


@pytest.mark.parametrize(
    "positions",
    [
        [],
        {OVERVIEW: []},
        {OVERVIEW: {"core.customers": [True, 1]}},
        {OVERVIEW: {"core.customers": [1]}},
    ],
)
def test_merge_refuses_bad_positions(tmp_path: Path, positions: object) -> None:
    root = _project(tmp_path, studio="")
    with pytest.raises(PositionsError):
        _merge(root, positions)


def test_merge_counts_outdated_svgs_after_a_new_column(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _export(root)
    screen = _on_screen(root)
    (root / "shop" / "models.py").write_text(
        MODELS.replace(
            "    id: int = Field(primary_key=True)\n\n\nclass Invoice",
            "    id: int = Field(primary_key=True)\n    email: str\n\n\nclass Invoice",
        )
    )
    assert _merge(root, screen)["pending"]["svgs"] == 2


def test_positions_beyond_the_coordinate_limit_are_refused(tmp_path: Path) -> None:
    root = _project(tmp_path, studio="")
    screen = _on_screen(root)
    screen[OVERVIEW]["core.customers"] = [10**10, 0]
    with pytest.raises(PositionsError):
        _merge(root, screen)
    project, config = _load(root)
    with pytest.raises(PositionsError):
        render_download(project, config, OVERVIEW, screen[OVERVIEW])


def test_merge_keeps_a_resized_box_in_place(tmp_path: Path) -> None:
    """AC 4: when columns change, the box keeps its (on-screen) position."""
    root = _project(tmp_path, studio="")
    screen = _on_screen(root)
    screen[OVERVIEW]["core.customers"] = [900, 900]
    screen["core"]["core.customers"] = [300, 40]
    (root / "shop" / "models.py").write_text(
        MODELS.replace(
            "    id: int = Field(primary_key=True)\n\n\nclass Invoice",
            "    id: int = Field(primary_key=True)\n    email: str\n    phone: str\n"
            "\n\nclass Invoice",
        )
    )
    merged = _merge(root, screen)
    for name, where in ((OVERVIEW, [900, 900]), ("core", [300, 40])):
        diagram = _diagram_of(merged, name)
        assert diagram["positions"]["core.customers"] == where
        assert "core.customers" not in diagram["new"]
    rows = merged["boxes"]["core.customers"]["rows"]
    assert [r["name"] for r in rows] == ["id", "email", "phone"]
