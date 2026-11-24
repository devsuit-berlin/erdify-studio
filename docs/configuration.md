# Configuration

```toml
[tool.erdify-studio]
layout = "docs/erd/erdify-layout.json"   # default: erdify-layout.json next to pyproject.toml
group_by = "auto"                        # auto | schema | app | module | none
export_dir = "docs/erd"                  # optional; omitted = no committed SVGs
```

`group_by = "auto"` picks, per entity, its database schema, else its Django app, else its
Python module. Entities are keyed in the layout file by `schema.table` (or `table`), so
renaming a class keeps its position; same-name tables in different schemas get their
own key. Entities that would share a key (same-name classes in different modules, or two
classes of one table) are keyed by erdify's entity name instead, e.g.
`billing.models.Address`; when such a namesake appears later, the first one's key changes
once. Enums are keyed `enum:<name>`.

Relative `layout` and `export_dir` paths resolve from the folder of `pyproject.toml`
(without a `pyproject.toml`, from the working directory). An unknown key in
`[tool.erdify-studio]` is logged as a warning and ignored; a value of the wrong type, or
a `group_by` that isn't one of the five, makes every command exit 2 with a message.

## Diagram colours

```toml
[tool.erdify-studio.colors]
accent = "#4150aa"
header = "#192346"
header_text = "#ffffff"
```

All keys are optional; a value is `#rrggbb` (any case). They apply to the canvas, the
exported SVGs and **Download SVG**.

| Key | Colours | Default |
| --- | ------- | ------- |
| `accent` | PK/FK markers, the tint of the enum header, the selection on the canvas | `#615fff` |
| `header` | Entity box header | `#e2e8f0` |
| `header_text` | Entity box title | `#0f172b`; with only `header` set, white or `#0f172b`, whichever contrasts more with the header |
| `background` | Box bodies and the SVG background | `#ffffff` |

- **Enum boxes** derive from these: the header is `accent` mixed 22 % into `background`,
  and the title is white or dark by contrast.
- Everything else stays fixed: borders, field names and types, edges, foreign boxes.
- The field text is dark, so a `background` that is too dark for it (contrast below
  4.5:1) logs a warning.
- The canvas shows the colours in light mode; dark mode keeps its own look. Editing
  the table while studio runs updates the canvas within about a second.
- Changing colours makes committed SVGs outdated: `check` reports them until the next
  `export` or Save (see [Export SVGs](usage/export.md)).
- Not yet: every colour configurable
  ([#67](https://github.com/devsuit-berlin/erdify-studio/issues/67)) and a colour
  preview in the UI ([#68](https://github.com/devsuit-berlin/erdify-studio/issues/68)).

erdify's own settings (`[tool.erdify]`: `include`, `sources`, `exclude`, `strict`,
`no_enums`, `no_relationships`, `allow_empty`, …) decide which entities exist; see
[erdify's documentation](https://erdify.devsuit.io/). erdify-studio reads the same
`pyproject.toml`.
