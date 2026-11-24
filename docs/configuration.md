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

erdify's own settings (`[tool.erdify]`: `include`, `sources`, `exclude`, `strict`,
`no_enums`, `no_relationships`, `allow_empty`, …) decide which entities exist; see
[erdify's documentation](https://erdify.devsuit.io/). erdify-studio reads the same
`pyproject.toml`.

## Diagram colours

For example, the devsuit brand (see [Brand](brand.md#colours)):

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
| `accent` | PK/FK markers, the tint of the enum header, the selection and NEW chip on the canvas (chip text: white or `#0f172b` by contrast) | `#615fff` |
| `header` | Entity box header | `#e2e8f0` |
| `header_text` | Entity box title | `#0f172b`; when `header` is set and `header_text` isn't, white or `#0f172b`, whichever contrasts more with the header |
| `background` | Box bodies and the SVG background | `#ffffff` |
| `text` | Field names and enum values | `#0f172b` |
| `text_muted` | Field types, edges and their markers, titles of foreign boxes | `#62748e` |
| `border` | Lines between rows | `#e2e8f0` |
| `border_strong` | Box outline | `#cad5e2` |
| `background_muted` | Foreign boxes, the circle on edge markers | `#f8fafc` |

- **Enum boxes** derive from these: the header is `accent` mixed 22 % into `background`,
  and the title is white or `#0f172b`, whichever contrasts more with it.
- `text` on `background` below 4.5:1 contrast (WCAG AA) logs a warning.
- **A dark background** needs light text too; the other defaults don't adapt:

  ```toml
  [tool.erdify-studio.colors]
  background = "#192346"
  text = "#f1f5f9"
  text_muted = "#94a3b8"
  border = "#2c3775"
  border_strong = "#4150aa"
  background_muted = "#222b5c"
  ```

- The canvas shows the colours in light mode; dark mode keeps its own look. Editing
  the table while studio runs updates the canvas within about a second.
- Changing colours makes committed SVGs outdated: `check` reports them until the next
  `export` or Save (see [Export SVGs](usage/export.md)).
- Not yet: a colour preview in the UI
  ([#68](https://github.com/devsuit-berlin/erdify-studio/issues/68)).
