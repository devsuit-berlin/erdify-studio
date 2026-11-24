import logging
import tomllib
from pathlib import Path

import pytest

from erdify_studio import ConfigError, DiagramColors, StudioConfig, StudioError, load_config


def _pyproject(tmp_path: Path, table: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "x"\n\n[tool.erdify-studio]\n{table}\n')
    return path


def test_defaults_next_to_the_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n')
    assert load_config(pyproject) == StudioConfig(
        layout=tmp_path / "erdify-layout.json", group_by="auto", export_dir=None
    )


def test_defaults_in_the_working_directory_without_a_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_config(None).layout == tmp_path / "erdify-layout.json"


def test_paths_resolve_from_the_pyproject_folder(tmp_path: Path) -> None:
    pyproject = _pyproject(
        tmp_path,
        'layout = "docs/erd/erdify-layout.json"\ngroup_by = "schema"\nexport_dir = "docs/erd"',
    )
    assert load_config(pyproject) == StudioConfig(
        layout=tmp_path / "docs" / "erd" / "erdify-layout.json",
        group_by="schema",
        export_dir=tmp_path / "docs" / "erd",
    )


def test_absolute_paths_are_kept(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere" / "layout.json"
    pyproject = _pyproject(tmp_path, f"layout = {str(target)!r}")
    assert load_config(pyproject).layout == target


@pytest.mark.parametrize("group_by", ["auto", "schema", "app", "module", "none"])
def test_every_group_by_value_is_accepted(tmp_path: Path, group_by: str) -> None:
    assert load_config(_pyproject(tmp_path, f'group_by = "{group_by}"')).group_by == group_by


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ('group_by = "folder"', r"'group_by' must be one of .*'folder'"),
        ("group_by = 1", r"'group_by' must be one of"),
        ("layout = 1", r"'layout' must be a non-empty string"),
        ('layout = ""', r"'layout' must be a non-empty string"),
        ("export_dir = []", r"'export_dir' must be a non-empty string"),
    ],
)
def test_invalid_values_are_errors(tmp_path: Path, table: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(_pyproject(tmp_path, table))


def test_errors_name_the_pyproject(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"pyproject\.toml"):
        load_config(_pyproject(tmp_path, "layout = 1"))


def test_unknown_keys_are_warned_about_and_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pyproject = _pyproject(tmp_path, 'group-by = "schema"')
    with caplog.at_level(logging.WARNING, logger="erdify_studio"):
        config = load_config(pyproject)
    assert config.group_by == "auto"
    assert "unknown [tool.erdify-studio] key 'group-by'" in caplog.text


def test_table_must_be_a_table(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool]\nerdify-studio = "x"\n')
    with pytest.raises(ConfigError, match=r"\[tool\.erdify-studio\] must be a table"):
        load_config(pyproject)


def test_tool_must_be_a_table(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("tool = 1\n")
    with pytest.raises(ConfigError, match=r"\[tool\] must be a table"):
        load_config(pyproject)


def test_unreadable_pyproject_is_an_error(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.erdify-studio\n")
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(pyproject)


def test_config_errors_share_the_package_base() -> None:
    assert issubclass(ConfigError, StudioError)


def test_colors_default_to_none(tmp_path: Path) -> None:
    assert load_config(_pyproject(tmp_path, "")).colors == DiagramColors()


def test_colors_are_read_and_lowercased(tmp_path: Path) -> None:
    pyproject = _pyproject(
        tmp_path, '[tool.erdify-studio.colors]\naccent = "#4150AA"\nheader_text = "#FFFFFF"'
    )
    assert load_config(pyproject).colors == DiagramColors(accent="#4150aa", header_text="#ffffff")


@pytest.mark.parametrize(
    "value", ['"#fff"', '"fff"', '"#ffffff80"', '"red"', "123", '"#ffffff\\n"']
)
def test_invalid_colors_are_errors(tmp_path: Path, value: str) -> None:
    pyproject = _pyproject(tmp_path, f"[tool.erdify-studio.colors]\naccent = {value}")
    expected = tomllib.loads(f"v = {value}")["v"]
    with pytest.raises(ConfigError) as error:
        load_config(pyproject)
    message = str(error.value)
    assert "'accent'" in message
    assert repr(expected) in message
    assert "pyproject.toml" in message


def test_colors_must_be_a_table(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"'colors' must be a table"):
        load_config(_pyproject(tmp_path, 'colors = "x"'))


def test_unknown_color_keys_are_warned_about(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pyproject = _pyproject(tmp_path, '[tool.erdify-studio.colors]\nborder = "#000000"')
    with caplog.at_level(logging.WARNING, logger="erdify_studio"):
        config = load_config(pyproject)
    assert config.colors == DiagramColors()
    assert "'border'" in caplog.text


def test_a_dark_background_is_warned_about(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dark = _pyproject(tmp_path, '[tool.erdify-studio.colors]\nbackground = "#1e2129"')
    with caplog.at_level(logging.WARNING, logger="erdify_studio"):
        load_config(dark)
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert "'#1e2129'" in caplog.text
    assert "4.5" in caplog.text

    caplog.clear()
    light = _pyproject(tmp_path, '[tool.erdify-studio.colors]\nbackground = "#fdf6e3"')
    with caplog.at_level(logging.WARNING, logger="erdify_studio"):
        load_config(light)
    assert caplog.records == []


def test_diagram_colors_is_public() -> None:
    import erdify_studio

    assert "DiagramColors" in erdify_studio.__all__
