import importlib.util
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_wheel.py"
ENTRY_POINT = "[console_scripts]\nerdify-studio = erdify_studio.cli:main\n"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_wheel", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_wheel = _load()


def _wheel(directory: Path, files: dict[str, str], name: str = "pkg-1.0-py3-none-any.whl") -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w") as zf:
        for member, content in files.items():
            zf.writestr(member, content)
    return path


COMPLETE = {
    "erdify_studio/_static/index.html": "<html></html>",
    "erdify_studio/_static/assets/index-abc.js": "",
    "pkg-1.0.dist-info/entry_points.txt": ENTRY_POINT,
}


def test_complete_wheel_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _wheel(tmp_path, COMPLETE)
    assert check_wheel.main([str(tmp_path)]) == 0
    assert "OK" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("erdify_studio/_static/index.html", "index.html is missing"),
        ("erdify_studio/_static/assets/index-abc.js", "no JavaScript bundle"),
        ("pkg-1.0.dist-info/entry_points.txt", "console script `erdify-studio` is missing"),
    ],
)
def test_incomplete_wheel_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], missing: str, message: str
) -> None:
    _wheel(tmp_path, {k: v for k, v in COMPLETE.items() if k != missing})
    assert check_wheel.main([str(tmp_path)]) == 1
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("count", [0, 2])
def test_needs_exactly_one_wheel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], count: int
) -> None:
    for i in range(count):
        _wheel(tmp_path, COMPLETE, name=f"pkg-1.{i}-py3-none-any.whl")
    assert check_wheel.main([str(tmp_path)]) == 1
    assert f"found {count}" in capsys.readouterr().err


def test_usage_error_without_argument(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_wheel.main([]) == 2
    assert "usage:" in capsys.readouterr().err
