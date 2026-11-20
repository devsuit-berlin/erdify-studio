"""``erdify-studio [path]``: open the canvas (the default command)."""

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from erdify_studio import _server
from erdify_studio.cli import main

MODELS = """\
from sqlmodel import Field, SQLModel


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    id: int = Field(primary_key=True)
"""


def _project(root: Path, models: str = MODELS) -> Path:
    root.mkdir(exist_ok=True)
    (root / "pyproject.toml").write_text('[tool.erdify]\ninclude = ["**/models.py"]\n')
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models)
    return root


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Serving stops at once (as on Ctrl+C); returns the URLs opened in a browser."""
    urls: list[str] = []

    def stop(self: _server.StudioServer, poll_interval: float = 0.5) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(_server.StudioServer, "serve_forever", stop)

    def record(url: str) -> bool:
        urls.append(url)
        return True

    monkeypatch.setattr("webbrowser.open", record)
    yield urls


def test_opens_the_browser_with_the_token_url(
    tmp_path: Path, opened: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(_project(tmp_path / "p"))]) == 0
    (url,) = opened
    assert url.startswith("http://127.0.0.1:")
    assert "?token=" in url
    assert f"erdify-studio: serving {url} (Ctrl+C to stop)" in capsys.readouterr().out


def test_no_browser_prints_the_url_only(
    tmp_path: Path, opened: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--no-browser", str(_project(tmp_path / "p"))]) == 0
    assert opened == []
    assert "?token=" in capsys.readouterr().out


def test_the_open_command_by_name(tmp_path: Path, opened: list[str]) -> None:
    assert main(["open", "--no-browser", str(_project(tmp_path / "p"))]) == 0


def test_defaults_to_the_current_directory(
    tmp_path: Path, opened: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_project(tmp_path / "p"))
    assert main([]) == 0
    assert len(opened) == 1


def test_a_directory_named_like_a_command(
    tmp_path: Path, opened: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path / "check")
    monkeypatch.chdir(tmp_path)
    assert main(["./check"]) == 0


def test_the_port_option(
    tmp_path: Path, opened: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert main(["--no-browser", "--port", str(port), str(_project(tmp_path / "p"))]) == 0
    assert f"http://127.0.0.1:{port}/" in capsys.readouterr().out


def test_a_parse_error_exits_2_before_serving(
    tmp_path: Path, opened: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path / "p", models="class Broken(:\n")
    assert main([str(root)]) == 2
    assert opened == []
    assert "erdify-studio: error:" in capsys.readouterr().err


def test_an_empty_project_exits_2(
    tmp_path: Path, opened: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(_project(tmp_path / "p", models=""))]) == 2
    assert "no entities found" in capsys.readouterr().err


def test_a_port_in_use_exits_2(
    tmp_path: Path, opened: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert main(["--port", str(port), str(_project(tmp_path / "p"))]) == 2
    assert "erdify-studio: error:" in capsys.readouterr().err


def test_help_names_the_open_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "open" in capsys.readouterr().out


def test_a_broken_layout_file_exits_2(
    tmp_path: Path, opened: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path / "p")
    (root / "erdify-layout.json").write_text("<<<<<<< HEAD\n")
    assert main([str(root)]) == 2
    assert opened == []
