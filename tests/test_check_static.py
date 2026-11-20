import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_static.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_static", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_static = _load()


def _build(directory: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return directory


def test_a_clean_build_has_no_problems(tmp_path: Path) -> None:
    build = _build(tmp_path, {"index.html": "<script src='./assets/a.js'></script>"})
    assert check_static.problems(build) == []


@pytest.mark.parametrize(
    "url",
    [
        "https://api.iconify.design/lucide.json",
        "https://fonts.googleapis.com/css2?family=Inter",
        "http://cdn.example/x.js",
        "//cdn.example/x.js",
    ],
)
def test_reports_an_external_url(tmp_path: Path, url: str) -> None:
    build = _build(tmp_path, {"assets/app.js": f'fetch("{url}")'})
    (problem,) = check_static.problems(build)
    assert "assets/app.js" in problem
    assert url in problem


@pytest.mark.parametrize(
    "url",
    [
        "http://www.w3.org/2000/svg",
        "http://www.w3.org/1999/xlink",
        "http://www.w3.org/XML/1998/namespace",
    ],
)
def test_allows_xml_namespaces(tmp_path: Path, url: str) -> None:
    build = _build(tmp_path, {"assets/app.js": f'createElementNS("{url}", "svg")'})
    assert check_static.problems(build) == []


@pytest.mark.parametrize(
    "text",
    [
        "/*! tailwindcss v4 | MIT License | https://tailwindcss.com */",
        "`https://vuejs.org/error-reference/#runtime-${r}`",
    ],
)
def test_allows_text_only_urls(tmp_path: Path, text: str) -> None:
    build = _build(tmp_path, {"assets/app.js": text})
    assert check_static.problems(build) == []


def test_a_comment_like_double_slash_is_not_a_url(tmp_path: Path) -> None:
    build = _build(tmp_path, {"assets/app.js": "a=1;// comment\nb=2"})
    assert check_static.problems(build) == []


def test_a_missing_build_is_a_problem(tmp_path: Path) -> None:
    (problem,) = check_static.problems(tmp_path / "missing")
    assert "missing" in problem


def test_main_exits_1_on_problems(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    build = _build(tmp_path, {"assets/app.js": 'fetch("https://evil.example/")'})
    assert check_static.main([str(build)]) == 1
    assert "https://evil.example/" in capsys.readouterr().err


def test_main_exits_0_when_clean(tmp_path: Path) -> None:
    assert check_static.main([str(_build(tmp_path, {"index.html": "ok"}))]) == 0
