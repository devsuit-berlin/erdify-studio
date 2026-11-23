"""Rendering one diagram as SVG: deterministic, escaped, drawn like the canvas.

The golden files in ``tests/fixtures/export`` pin the exact bytes; rewrite them on an
intended change with ``ERDIFY_STUDIO_UPDATE_GOLDEN=1 uv run poe test tests/test_svg.py``
and look at the result before committing.
"""

import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import erdify
import pytest

from erdify_studio import OVERVIEW, Layout, load_config, place_project, save_layout
from erdify_studio._diagrams import DiagramJson, Diagrams, build_diagrams
from erdify_studio._svg import format_number, render_svg

GOLDEN = Path(__file__).parent / "fixtures" / "export"

MODELS = """\
import enum
from typing import Optional

from sqlmodel import Field, SQLModel


class Status(str, enum.Enum):
    OPEN = "open"
    PAID = "paid"


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    __table_args__ = {"schema": "core"}
    id: int = Field(primary_key=True)
    email: str = Field(unique=True)
    referred_by_id: Optional[int] = Field(default=None, foreign_key="core.customers.id")


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"
    __table_args__ = {"schema": "billing"}
    id: int = Field(primary_key=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="core.customers.id")
    status: Status


class Line(SQLModel, table=True):
    __tablename__ = "lines"
    __table_args__ = {"schema": "billing"}
    id: int = Field(primary_key=True)
    invoice_id: int = Field(foreign_key="billing.invoices.id")
"""

#: Fixed positions, so the golden files don't depend on place --auto.
POSITIONS = {
    OVERVIEW: {
        "core.customers": (0, 0),
        "billing.invoices": (420, 0),
        "billing.lines": (420, 260),
        "enum:Status": (840, 40),
    },
    "core": {"core.customers": (0, 0), "billing.invoices": (420, 40)},
    "billing": {
        "billing.invoices": (0, 0),
        "billing.lines": (0, 260),
        "enum:Status": (420, 40),
        "core.customers": (-420, 40),
    },
}


def _project(root: Path, models: str = MODELS) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[tool.erdify]\ninclude = ["**/models.py"]\n[tool.erdify-studio]\n'
    )
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models, encoding="utf-8")
    layout = Layout()
    for diagram, boxes in POSITIONS.items():
        for key, (x, y) in boxes.items():
            layout.set_position(diagram, key, x, y)
    save_layout(layout, root / "erdify-layout.json")
    return root


def _payload(root: Path) -> Diagrams:
    project = erdify.load_project(root, strict=True)
    return build_diagrams(project, load_config(project.settings.pyproject), shown_path="x")


def _render(payload: Diagrams, name: str = OVERVIEW) -> str:
    diagram: DiagramJson = next(d for d in payload["diagrams"] if d["name"] == name)
    return render_svg(diagram, payload["boxes"], payload["metrics"])


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0, "0"),
        (-0.0, "0"),
        (-0.001, "0"),
        (12.5, "12.5"),
        (12.50, "12.5"),
        (3.0, "3"),
        (2.675, "2.67"),  # the binary value is below .675: rounds down, as everywhere
        (-7.125, "-7.12"),
        (123456, "123456"),
        (1e-7, "0"),
    ],
)
def test_format_number(value: float, text: str) -> None:
    assert format_number(value) == text


@pytest.mark.parametrize("name", [OVERVIEW, "core", "billing"])
def test_render_matches_the_golden_files(tmp_path: Path, name: str) -> None:
    svg = _render(_payload(_project(tmp_path)), name)
    path = GOLDEN / ("overview.svg" if name == OVERVIEW else f"groups/{name}.svg")
    if os.environ.get("ERDIFY_STUDIO_UPDATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8", newline="\n")
    assert svg == path.read_text(encoding="utf-8")


def test_render_is_deterministic(tmp_path: Path) -> None:
    root = _project(tmp_path / "a")
    copy = tmp_path / "elsewhere" / "b"
    shutil.copytree(root, copy)
    first, second = _render(_payload(root)), _render(_payload(root))
    assert first == second == _render(_payload(copy))


def test_output_is_utf8_lf_with_a_trailing_newline(tmp_path: Path) -> None:
    svg = _render(_payload(_project(tmp_path)))
    assert svg.endswith("</svg>\n") and "\r" not in svg
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')


def test_text_is_escaped(tmp_path: Path) -> None:
    models = MODELS.replace('__tablename__ = "lines"', '__tablename__ = "straße<&\\"x\\">"')
    root = _project(tmp_path, models)
    layout = Layout()
    for key, (x, y) in POSITIONS[OVERVIEW].items():
        layout.set_position(OVERVIEW, key.replace("billing.lines", 'billing.straße<&"x">'), x, y)
    save_layout(layout, root / "erdify-layout.json")
    svg = _render(_payload(root))
    texts = [t.text for t in ET.fromstring(svg).iter("{http://www.w3.org/2000/svg}text")]
    assert 'billing.straße<&"x">' in texts


def test_the_background_is_white(tmp_path: Path) -> None:
    svg = _render(_payload(_project(tmp_path)))
    first = ET.fromstring(svg)[0]
    assert (first.tag.split("}")[1], first.get("fill")) == ("rect", "#ffffff")


def test_a_foreign_box_shows_its_title_only_with_a_dashed_frame(tmp_path: Path) -> None:
    svg = _render(_payload(_project(tmp_path)), "core")
    root = ET.fromstring(svg)
    box = next(g for g in root.iter() if g.get("data-key") == "billing.invoices")
    texts = [t.text for t in box.iter("{http://www.w3.org/2000/svg}text")]
    frame = [r for r in box.iter("{http://www.w3.org/2000/svg}rect") if r.get("fill") == "none"]
    assert texts == ["billing.invoices"]
    assert frame[0].get("stroke-dasharray") == "4 3"


def test_enum_links_are_dashed_without_markers(tmp_path: Path) -> None:
    root = ET.fromstring(_render(_payload(_project(tmp_path))))
    link = next(g for g in root.iter() if g.get("class") == "enum-link")
    paths = list(link.iter("{http://www.w3.org/2000/svg}path"))
    assert len(paths) == 1 and paths[0].get("stroke-dasharray") == "4 4"


def test_edges_carry_their_label_as_a_title(tmp_path: Path) -> None:
    root = ET.fromstring(_render(_payload(_project(tmp_path))))
    titles = {t.text for t in root.iter("{http://www.w3.org/2000/svg}title")}
    assert {"customer_id", "invoice_id", "referred_by_id"} <= titles


def test_the_viewbox_covers_every_box_and_the_self_loop(tmp_path: Path) -> None:
    payload = _payload(_project(tmp_path))
    x, y, width, height = map(float, ET.fromstring(_render(payload)).get("viewBox", "").split())
    customers = payload["boxes"]["core.customers"]
    # the self-reference loops 56 units to the right of core.customers, plus the margin
    assert x <= -40 and y <= -40
    assert (
        x + width
        >= max(customers["width"] + 56, 840 + payload["boxes"]["enum:Status"]["width"]) + 40
    )
    assert re.fullmatch(r"\d+(\.\d+)?", ET.fromstring(_render(payload)).get("width", ""))


def test_clip_ids_differ_between_diagrams(tmp_path: Path) -> None:
    """Several SVGs inlined into one HTML page share one id space."""
    payload = _payload(_project(tmp_path))
    ids = [
        set(re.findall(r'<clipPath id="([^"]+)"', _render(payload, n))) for n in (OVERVIEW, "core")
    ]
    assert ids[0] and ids[1] and not ids[0] & ids[1]


def test_clip_ids_differ_between_non_latin_groups(tmp_path: Path) -> None:
    models = (
        MODELS.replace('"schema": "core"', '"schema": "Заказы"')
        .replace('"schema": "billing"', '"schema": "顧客"')
        .replace('foreign_key="core.customers.id"', 'foreign_key="Заказы.customers.id"')
        .replace('foreign_key="billing.invoices.id"', 'foreign_key="顧客.invoices.id"')
    )
    root = tmp_path
    root.mkdir(exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[tool.erdify]\ninclude = ["**/models.py"]\n[tool.erdify-studio]\n'
    )
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(models, encoding="utf-8")
    project = erdify.load_project(root, strict=True)
    place_project(project, load_config(project.settings.pyproject))
    payload = _payload(root)
    ids = [
        set(re.findall(r'<clipPath id="([^"]+)"', _render(payload, n))) for n in ("Заказы", "顧客")
    ]
    assert ids[0] and ids[1] and not ids[0] & ids[1]
