"""The diagram palette: configurable colours, derived colours and the colour maths.

``DiagramColors`` holds the four colours a project may set; ``resolve_palette`` turns
them into the full ``Palette`` the SVG export and the canvas use. Derived colours are
computed in OKLab (mixing) and by WCAG 2.x contrast (text on a coloured background).
Colours are lowercase ``#rrggbb`` strings; callers normalise before calling.

This module imports nothing from the package, so ``_config`` can import it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

_LIGHT_TEXT = "#ffffff"
_DARK_TEXT = "#0f172b"
#: Share of the accent in the enum header colour (the canvas's 22 % colour-mix).
_ENUM_MIX = 0.22


@dataclass(frozen=True)
class DiagramColors:
    """The colours a project may set (lowercase ``#rrggbb``); ``None`` keeps the default."""

    accent: str | None = None
    header: str | None = None
    header_text: str | None = None
    background: str | None = None


@dataclass(frozen=True)
class Palette:
    """Every colour of a diagram, resolved."""

    background: str
    background_muted: str
    border: str
    border_accented: str
    text: str
    text_muted: str
    accent: str
    header: str
    header_text: str
    enum_header: str
    enum_title: str


def _rgb(color: str) -> tuple[float, float, float]:
    return (int(color[1:3], 16) / 255, int(color[3:5], 16) / 255, int(color[5:7], 16) / 255)


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _to_oklab(color: str) -> tuple[float, float, float]:
    r, g, b = (_to_linear(c) for c in _rgb(color))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _from_oklab(lab: tuple[float, float, float]) -> str:
    big_l, a, b = lab
    l_ = (big_l + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (big_l - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (big_l - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    channels = (round(min(1.0, max(0.0, _from_linear(c))) * 255) for c in linear)
    return "#" + "".join(f"{c:02x}" for c in channels)


def mix_oklab(color: str, base: str, amount: float) -> str:
    """``amount`` (0..1) of ``color`` mixed into ``base`` in OKLab, as ``#rrggbb``."""
    top, bottom = _to_oklab(color), _to_oklab(base)
    return _from_oklab(
        (
            bottom[0] + (top[0] - bottom[0]) * amount,
            bottom[1] + (top[1] - bottom[1]) * amount,
            bottom[2] + (top[2] - bottom[2]) * amount,
        )
    )


def _luminance(color: str) -> float:
    r, g, b = (_to_linear(c) for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """The WCAG 2.x contrast ratio of two colours (1..21)."""
    lighter, darker = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def readable_text(background: str) -> str:
    """White or the dark text colour, whichever contrasts more with ``background``."""
    if contrast(_LIGHT_TEXT, background) > contrast(_DARK_TEXT, background):
        return _LIGHT_TEXT
    return _DARK_TEXT


def resolve_palette(
    *,
    accent: str | None = None,
    header: str | None = None,
    header_text: str | None = None,
    background: str | None = None,
) -> Palette:
    """The full palette for the given overrides (lowercase ``#rrggbb`` or ``None``)."""
    accent = accent or "#615fff"
    background = background or "#ffffff"
    if header is None:
        header = "#e2e8f0"
        header_text = header_text or _DARK_TEXT
    else:
        header_text = header_text or readable_text(header)
    enum_header = mix_oklab(accent, background, _ENUM_MIX)
    return Palette(
        background=background,
        background_muted="#f8fafc",
        border="#e2e8f0",
        border_accented="#cad5e2",
        text=_DARK_TEXT,
        text_muted="#62748e",
        accent=accent,
        header=header,
        header_text=header_text,
        enum_header=enum_header,
        enum_title=readable_text(enum_header),
    )


def palette_of(colors: DiagramColors) -> Palette:
    """The palette for a project's ``DiagramColors``."""
    return resolve_palette(
        accent=colors.accent,
        header=colors.header,
        header_text=colors.header_text,
        background=colors.background,
    )


#: The canvas diagram's light theme (Nuxt UI tokens with neutral "slate" in
#: vite.config.ts; the accent is `--erd-primary` in frontend/src/style.css, Tailwind
#: indigo-500, independent of the UI's devsuit primary), as sRGB hex of the Tailwind v4
#: OKLCH values.
DEFAULT_PALETTE = resolve_palette()
