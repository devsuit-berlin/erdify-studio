import runpy
import sys
from importlib.metadata import version

import pytest

from erdify_studio import __version__
from erdify_studio.cli import main


def test_help_exits_zero_and_names_the_program(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "usage: erdify-studio" in capsys.readouterr().out


def test_version_shows_studio_and_erdify_versions(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert f"erdify-studio {__version__}" in out
    assert f"erdify {version('erdify')}" in out


def test_unknown_option_exits_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--no-such-option"])
    assert exc.value.code == 2
    assert "unrecognized arguments: --no-such-option" in capsys.readouterr().err


def test_runs_as_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["erdify-studio", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("erdify_studio", run_name="__main__")
    assert exc.value.code == 0
