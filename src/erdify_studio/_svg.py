"""One diagram as a deterministic SVG, drawn the way the canvas draws it.

The input is a diagram of the ``GET /api/diagrams`` payload (``_diagrams``), so the
SVG and the canvas read the same boxes, sizes, positions, edges and links. Boxes are
drawn like ``frontend/src/components/BoxNode.vue``, edges like ``EdgeLine.vue`` with
the geometry of ``_geometry`` (the port of ``geometry.ts``), in studio's light theme
on a white background.

Byte-stable on every machine: the XML is written by hand in a fixed order (background,
enum links, edges in payload order, boxes by key), every non-integer number goes
through ``format_number``, text is escaped, lines end in ``\\n`` and there is no
timestamp.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from xml.sax.saxutils import escape, quoteattr

from erdify_studio._diagrams import BoxDef, DiagramJson, EdgeEndJson, FieldRow
from erdify_studio._geometry import (
    Rect,
    angle,
    edge_line,
    end_marker,
    fan_offsets,
    self_loop,
)

#: Studio's light theme (Nuxt UI tokens, primary "indigo", neutral "slate" in
#: vite.config.ts), as sRGB hex of the Tailwind v4 OKLCH values.
_BG = "#ffffff"  # --ui-bg
_BG_MUTED = "#f8fafc"  # --ui-bg-muted (slate-50)
_BG_ACCENTED = "#e2e8f0"  # --ui-bg-accented (slate-200)
_BORDER = "#e2e8f0"  # --ui-border (slate-200)
_BORDER_ACCENTED = "#cad5e2"  # --ui-border-accented (slate-300)
_TEXT_HIGHLIGHTED = "#0f172b"  # --ui-text-highlighted (slate-900)
_TEXT_MUTED = "#62748e"  # --ui-text-muted (slate-500)
_PRIMARY = "#615fff"  # --ui-primary (indigo-500)
_ENUM_HEADER = "#d8deff"  # color-mix(in oklab, --ui-primary 22%, --ui-bg)

#: The canvas font; the box widths assume its advance of 0.6 em (FONT_ADVANCE).
_FONT_FAMILY = '"JetBrains Mono", ui-monospace, Menlo, Consolas, "DejaVu Sans Mono", monospace'
_FONT_ADVANCE = 0.6
#: Characters reserved in front of a field name for its badges (MARKER_CHARS).
_MARKER_CHARS = 6
#: Margin around the boxes (FIT_MARGIN).
_MARGIN = 40
#: How far a self-reference loops out to the right (``self_loop``'s reach).
_LOOP_REACH = 56
_LOOP_STEP = 20


def format_number(value: float) -> str:
    """``value`` rounded to 2 decimals, without trailing zeros; ``-0`` is ``0``.

    Snapped to 9 decimals first: platform maths libraries (``cos``, ``atan2``) may
    differ by an ulp, which must not flip a value on either side of a ``.xx5`` tie.
    """
    text = f"{round(value, 9):.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


# Letters of any script are valid in XML ids; everything else becomes "-".
_NOT_ID = re.compile(r"[^\w-]+")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:e[-+]?\d+)?")


def _tidy(path: str) -> str:
    """``path`` with every number through ``format_number``."""
    return _NUMBER.sub(lambda m: format_number(float(m.group())), path)


def render_svg(
    diagram: DiagramJson, boxes: Mapping[str, BoxDef], metrics: Mapping[str, int]
) -> str:
    """The SVG of ``diagram`` (one entry of ``build_diagrams``'s ``diagrams``)."""
    rects = _rects(diagram, boxes)
    loops = {e["from"]: 0 for e in diagram["edges"] if e["from"] == e["to"]}
    offsets = fan_offsets([(e["from"], e["to"]) for e in diagram["edges"]])
    for edge, offset in zip(diagram["edges"], offsets, strict=True):
        if edge["from"] == edge["to"]:
            loops[edge["from"]] = max(loops[edge["from"]], int(offset))

    left = min((r.x for r in rects.values()), default=0) - _MARGIN
    top = min((r.y for r in rects.values()), default=0) - _MARGIN
    right = (
        max(
            [r.x + r.width for r in rects.values()]
            + [
                rects[k].x + rects[k].width + _LOOP_REACH + n * _LOOP_STEP for k, n in loops.items()
            ],
            default=0,
        )
        + _MARGIN
    )
    bottom = max((r.y + r.height for r in rects.values()), default=0) + _MARGIN
    width, height = right - left, bottom - top
    n = format_number

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{n(left)} {n(top)} {n(width)} {n(height)}" '
        f'width="{n(width)}" height="{n(height)}">',
        f'  <rect x="{n(left)}" y="{n(top)}" width="{n(width)}" height="{n(height)}" '
        f'fill="{_BG}"/>',
    ]
    for link in diagram["enumLinks"]:
        start, end = edge_line(
            rects[link["enum"]], rects[link["entity"]], 0, link["enum"], link["entity"]
        )
        out += [
            '  <g class="enum-link">',
            f'    <path d="{_line(start, end)}" fill="none" stroke="{_TEXT_MUTED}" '
            'stroke-width="1.25" stroke-dasharray="4 4"/>',
            "  </g>",
        ]
    for edge, offset in zip(diagram["edges"], offsets, strict=True):
        out += _edge(
            edge["from"], edge["to"], edge["fromEnd"], edge["toEnd"], edge["label"], offset, rects
        )
    font_size = metrics["charWidth"] / _FONT_ADVANCE
    foreign = set(diagram["foreign"])
    # ids are per page: several SVGs inlined into one HTML page must not share them
    prefix = _NOT_ID.sub("-", diagram["name"]).strip("-") or "diagram"
    for i, key in enumerate(sorted(rects)):
        clip = f"clip-{prefix}-{i}"
        out += _box(key, boxes[key], rects[key], metrics, font_size, key in foreign, clip)
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _rects(diagram: DiagramJson, boxes: Mapping[str, BoxDef]) -> dict[str, Rect]:
    rects: dict[str, Rect] = {}
    for key in diagram["own"]:
        x, y = diagram["positions"][key]
        rects[key] = Rect(x, y, boxes[key]["width"], boxes[key]["height"])
    for key in diagram["foreign"]:
        x, y = diagram["positions"][key]
        width, height = diagram["foreignSizes"][key]
        rects[key] = Rect(x, y, width, height)
    return rects


def _line(start: tuple[float, float], end: tuple[float, float]) -> str:
    n = format_number
    return f"M {n(start[0])} {n(start[1])} L {n(end[0])} {n(end[1])}"


def _edge(
    source: str,
    target: str,
    source_end: EdgeEndJson,
    target_end: EdgeEndJson,
    label: str,
    offset: float,
    rects: Mapping[str, Rect],
) -> list[str]:
    if source == target:
        loop = self_loop(rects[source], int(offset))
        path, start, end = _tidy(loop.path), loop.start, loop.end
        start_angle, end_angle = loop.start_angle, loop.end_angle
    else:
        start, end = edge_line(rects[source], rects[target], offset, source, target)
        path = _line(start, end)
        start_angle, end_angle = angle(start, end), angle(end, start)
    stroke = f'fill="none" stroke="{_TEXT_MUTED}" stroke-width="1.25"'
    out = ['  <g class="edge">']
    if label:
        out.append(f"    <title>{escape(label)}</title>")
    out.append(f'    <path d="{path}" {stroke}/>')
    for point, direction, ends in ((start, start_angle, source_end), (end, end_angle, target_end)):
        marker = end_marker(point, direction, optional=ends["optional"], many=ends["many"])
        out.append(f'    <path d="{_tidy(marker.lines)}" {stroke}/>')
        if marker.circle:
            out.append(
                f'    <path d="{_tidy(marker.circle)}" fill="{_BG_MUTED}" stroke="{_TEXT_MUTED}" '
                'stroke-width="1.25"/>'
            )
    out.append("  </g>")
    return out


def _box(
    key: str,
    box: BoxDef,
    rect: Rect,
    metrics: Mapping[str, int],
    font_size: float,
    foreign: bool,
    clip: str,
) -> list[str]:
    n = format_number
    w, h = n(rect.width), n(rect.height)
    header, row = metrics["header"], metrics["row"]
    inset = metrics["padding"] / 2

    def baseline(top: float, height: float) -> str:
        return n(top + height / 2 + font_size * 0.35)

    body = _BG_MUTED if foreign else _BG
    head = _BG_MUTED if foreign else _ENUM_HEADER if box["kind"] == "enum" else _BG_ACCENTED
    title = _TEXT_MUTED if foreign else _TEXT_HIGHLIGHTED
    out = [
        f'  <g transform="translate({n(rect.x)} {n(rect.y)})" data-key={quoteattr(key)} '
        f'font-family={quoteattr(_FONT_FAMILY)} font-size="{n(font_size)}">',
        f'    <clipPath id="{clip}"><rect width="{w}" height="{h}" rx="6"/></clipPath>',
        f'    <rect width="{w}" height="{h}" rx="6" fill="{body}"/>',
        f'    <g clip-path="url(#{clip})">',
        f'      <rect width="{w}" height="{header}" fill="{head}"/>',
        f'      <text x="{n(inset)}" y="{baseline(0, header)}" font-weight="700" '
        f'fill="{title}">{escape(box["title"])}</text>',
    ]
    rows = [] if foreign else box["rows"]
    for i, item in enumerate(rows):
        top = header + i * row
        y = baseline(top, row)
        if i > 0:
            out.append(f'      <line x1="0" x2="{w}" y1="{top}" y2="{top}" stroke="{_BORDER}"/>')
        if "type" in item:
            field: FieldRow = item  # type: ignore[assignment]
            badges = " ".join(
                b
                for b, on in (
                    ("PK", field["pk"]),
                    ("FK", field["fk"]),
                    ("UK", field["uk"] and not field["pk"]),
                )
                if on
            )
            name_x = n(inset + _MARKER_CHARS * metrics["charWidth"])
            type_text = field["type"] + ("?" if field["nullable"] else "")
            out += [
                f'      <text x="{n(inset)}" y="{y}" font-weight="700" fill="{_PRIMARY}">'
                f"{escape(badges)}</text>",
                f'      <text x="{name_x}" y="{y}" fill="{_TEXT_HIGHLIGHTED}">'
                f"{escape(field['name'])}</text>",
                f'      <text x="{n(rect.width - inset)}" y="{y}" text-anchor="end" '
                f'fill="{_TEXT_MUTED}">{escape(type_text)}</text>',
            ]
        else:
            out.append(
                f'      <text x="{n(inset)}" y="{y}" fill="{_TEXT_HIGHLIGHTED}">'
                f"{escape(item['name'])}</text>"
            )
    dash = ' stroke-dasharray="4 3"' if foreign else ""
    out += [
        "    </g>",
        f'    <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{_BORDER_ACCENTED}" '
        f'stroke-width="1"{dash}/>',
        "  </g>",
    ]
    return out
