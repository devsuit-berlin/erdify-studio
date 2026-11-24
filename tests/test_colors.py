"""The diagram palette: defaults, OKLab mixing and contrast-based text colours."""

from __future__ import annotations

import re

import pytest

from erdify_studio._colors import (
    DEFAULT_PALETTE,
    HEX,
    DiagramColors,
    Palette,
    contrast,
    mix_oklab,
    palette_of,
    readable_text,
    resolve_palette,
)
from erdify_studio._errors import ConfigError


def test_defaults_are_todays_colours() -> None:
    assert resolve_palette() == DEFAULT_PALETTE
    assert DEFAULT_PALETTE == Palette(
        background="#ffffff",
        background_muted="#f8fafc",
        border="#e2e8f0",
        border_strong="#cad5e2",
        text="#0f172b",
        text_muted="#62748e",
        accent="#615fff",
        header="#e2e8f0",
        header_text="#0f172b",
        enum_header="#d8deff",
        enum_title="#0f172b",
        accent_text="#ffffff",
    )


def test_mix_oklab_endpoints() -> None:
    assert mix_oklab("#615fff", "#ffffff", 0) == "#ffffff"
    assert mix_oklab("#615fff", "#ffffff", 1) == "#615fff"
    assert mix_oklab("#000000", "#ffffff", 0.5) == "#636363"


def test_contrast() -> None:
    assert contrast("#ffffff", "#000000") == pytest.approx(21)
    assert contrast("#000000", "#ffffff") == pytest.approx(21)
    assert contrast("#615fff", "#615fff") == pytest.approx(1)


def test_readable_text() -> None:
    assert readable_text("#192346") == "#ffffff"
    assert readable_text("#e2e8f0") == "#0f172b"


def test_header_text_follows_a_set_header() -> None:
    assert resolve_palette(header="#192346").header_text == "#ffffff"
    assert resolve_palette(header="#192346", header_text="#f5dc19").header_text == "#f5dc19"


def test_enum_title_follows_the_enum_header() -> None:
    assert resolve_palette(header="#192346").enum_title == "#0f172b"
    assert resolve_palette(accent="#000000", background="#000000").enum_title == "#ffffff"


def test_enum_header_mixes_into_the_background() -> None:
    assert resolve_palette(background="#fdf6e3").enum_header == mix_oklab(
        "#615fff", "#fdf6e3", 0.22
    )


def test_palette_of() -> None:
    assert palette_of(DiagramColors(header="#192346")) == resolve_palette(header="#192346")


@pytest.mark.parametrize(
    ("value", "valid"),
    [("#ffffff", True), ("#ABCDEF", True), ("#fff", False), ("fff", False), ("#ffffff80", False)],
)
def test_hex_pattern(value: str, valid: bool) -> None:
    assert bool(HEX.match(value)) is valid


@pytest.mark.parametrize("value", ["red", "#ABCDEF", "#abc", "#abcdeg", "#abcdef\n", ""])
def test_diagram_colors_reject_invalid_values(value: str) -> None:
    with pytest.raises(ConfigError, match=re.escape(repr(value))):
        DiagramColors(accent=value)


def test_diagram_colors_name_the_field() -> None:
    with pytest.raises(ConfigError, match="header_text"):
        DiagramColors(header_text="red")


def test_diagram_colors_accept_lowercase_hex() -> None:
    assert DiagramColors(accent="#abcdef").accent == "#abcdef"


def test_every_colour_can_be_set() -> None:
    palette = resolve_palette(
        text="#111111",
        text_muted="#222222",
        border="#333333",
        border_strong="#444444",
        background_muted="#555555",
    )
    assert (
        palette.text,
        palette.text_muted,
        palette.border,
        palette.border_strong,
        palette.background_muted,
    ) == ("#111111", "#222222", "#333333", "#444444", "#555555")
    assert palette_of(DiagramColors(text="#111111", border_strong="#444444")) == resolve_palette(
        text="#111111", border_strong="#444444"
    )


def test_accent_text_follows_the_accent() -> None:
    assert resolve_palette(accent="#f5dc19").accent_text == "#0f172b"
    assert resolve_palette(accent="#192346").accent_text == "#ffffff"


@pytest.mark.parametrize(
    "field", ["text", "text_muted", "border", "border_strong", "background_muted"]
)
def test_diagram_colors_validate_every_field(field: str) -> None:
    with pytest.raises(ConfigError, match=field):
        DiagramColors(**{field: "red"})
