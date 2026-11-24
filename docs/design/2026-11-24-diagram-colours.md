# Configurable diagram colours (#48)

## Intent

Teams use studio for their own company or for customer projects, and the exported
diagrams end up on websites and in documents (often converted to PNG). Today their
colours are fixed (slate greys, an indigo accent), so a diagram can't take the brand of
the company or customer it's made for. A project should be able to set a small brand set
of colours in `pyproject.toml`, and both the export and the canvas follow it.

## Goals

1. `[tool.erdify-studio.colors]` in `pyproject.toml` sets the brand set: `accent`,
   `header`, `header_text`, `background`. Every key is optional.
2. The exported SVGs (`export`, Save with `export_dir`, **Download SVG**) use them.
3. The canvas shows the same colours in light mode, so it keeps showing what gets
   exported.
4. Without the table (or with an empty one) the output is unchanged, byte for byte:
   existing projects see no SVG change and `check` stays green.
5. Editing the table while studio runs updates the canvas within the watcher interval
   (about a second), like a model change.

## Non-goals

- Every colour configurable (borders, muted text, edges, foreign boxes): #67.
- Editing or previewing colours in the studio UI: #68. The colours are edited in
  `pyproject.toml` only.
- A dark variant of the export (second file, or `prefers-color-scheme` inside the SVG).
- Named presets (`theme = "devsuit"`). A preset is just four values; the docs show the
  devsuit values as an example instead.
- Fonts.

## Anti-goals

- An export and a canvas (light mode) that show different colours.
- A colour mechanism that PNG converters or office programs don't understand: the SVG
  keeps plain presentation attributes (`fill="#rrggbb"`), no `<style>`, no CSS variables.
- An output change for projects that don't set colours.
- A second implementation of the colour maths in TypeScript.

## Constraints

- No new runtime dependency. TOML is read with `tomllib` as today; nothing is written to
  `pyproject.toml`.
- Deterministic export: the same config gives the same bytes on every machine.
- Library code raises `ConfigError`; only the CLI prints.
- `StudioConfig` is public API (`__all__`): adding a field is additive (minor), renaming
  or removing one is a major bump.

## Approaches

| | Approach | Trade-off |
|---|---|---|
| **1 (chosen)** | Python resolves the full palette (configured keys, defaults, derived colours) once; the SVG renderer uses it, and the API sends the same hex values to the canvas, which sets them as CSS variables | One source of truth, no colour maths in TypeScript. The canvas reads diagram colours from the API instead of fixed tokens. |
| 2 | The canvas keeps computing derived colours in CSS (`color-mix`), Python re-implements the same maths | Smaller API change, but two implementations that can drift apart: the divergence the project avoids. |
| 3 | CSS variables / `<style>` inside the SVG | Neat in a browser, but converters and office programs handle CSS in SVG unreliably, which works against the use case (documents, PNG). |

The user picked 1, the brand set (option B of three: accent only / brand set / every
colour), and no UI editing (2026-11-24).

## Design

### Config

```toml
[tool.erdify-studio.colors]
accent = "#4150aa"       # PK/FK markers, enum header tint, canvas selection
header = "#192346"       # entity box header
header_text = "#ffffff"  # entity box title
background = "#ffffff"   # box bodies and the SVG background
```

- A value is a `#rrggbb` hex string, case-insensitive, stored lowercase (so `#ABCDEF` and
  `#abcdef` give the same bytes). Anything else, or a non-string, is a `ConfigError`
  naming the key and value (`!r`) and the file, like the existing keys.
- `colors` that isn't a table is a `ConfigError`. An unknown key inside it is a warning
  and ignored, like unknown keys of `[tool.erdify-studio]`.
- Key names use underscores like the existing `group_by` / `export_dir`. The table is
  `colors` (as in CSS and most tools), although the prose in the docs says "colours".
  *(Claude's call.)*

### Roles and defaults

| Key | Used for (export and canvas) | Default (today) |
|---|---|---|
| `accent` | PK/FK marker text; mixed into the enum header | `#615fff` (indigo-500) |
| `header` | header of entity boxes (not enums, not foreign boxes) | `#e2e8f0` (slate-200) |
| `header_text` | title of entity boxes | see below |
| `background` | box bodies, the SVG's background rect, mixed into the enum header | `#ffffff` |

- **Derived: enum header** = `accent` mixed 22 % into `background` in OKLab, as the canvas
  does today (`color-mix(in oklab, var(--erd-primary) 22%, var(--ui-bg))`), then to sRGB
  hex. Python computes it (sRGB ↔ OKLab, a few dozen lines, no dependency). With the
  defaults the result must be today's `#d8deff`; if rounding gives a neighbour value,
  pin the defaults' result to `#d8deff` rather than change existing output (goal 4).
- **`header_text` default:** `#0f172b` (slate-900, today's title colour) when `header` is
  unset. When `header` is set and `header_text` isn't, pick whichever of `#ffffff` and
  `#0f172b` has the higher WCAG contrast against `header`, so a dark brand header never
  gets dark text by accident. *(Claude's call.)*
- **Enum title:** not `header_text` (the enum header is a light tint, so a white
  `header_text` would be unreadable there). It gets the same contrast pick, `#ffffff` or
  `#0f172b`, against the derived enum header; with the defaults that is `#0f172b`, as
  today. *(Claude's call, from the builder check.)*
- Everything else stays as today: borders, field name/type text, edges, foreign boxes
  (muted background, muted title, dashed outline), the marker circles. Field names keep
  `#0f172b` even when `header_text` changes, so titles and field names (one colour today:
  `_TEXT_HIGHLIGHTED`, `.box__title, .box__name`) become separate roles.
- **Dark `background`:** the fixed field text isn't made for it. `load_config` logs a
  warning when the contrast of `#0f172b` (field names) on `background` is below WCAG AA
  (4.5:1), naming the value and the file; the export still runs. Real dark backgrounds
  come with #67. *(User decision, 2026-11-24.)*

### Where it lives

- `_config.py`: `StudioConfig` gains `colors` (the configured keys, each `str | None`),
  parsed and validated in `load_config`. Naming of the dataclass and whether it is
  re-exported is left to the builder (if it's a public field, its type is public too).
- A palette function (Python) turns `colors` into the full set of hex values the
  renderer needs (today's nine constants in `_svg.py`, with the four keys and the derived
  enum header filled in). The constants become the defaults.
- `render_svg` (and the export / download paths that call it) take the palette instead
  of reading module constants. `check` needs no change: it compares against what the
  export renders, which now follows the config.

- `_server.py`: the watcher reloads the config about every second, so the server puts a
  filter on `_config`'s logger while it runs: a config warning (dark `background`,
  unknown keys) is logged when it appears, not on every tick, and again if it goes away
  and comes back; a failed load doesn't reset it. `open` uses the server's first load as
  its pre-flight check, so a warning appears once at startup. *(Added in review.)*

### Canvas

- `GET /api/diagrams` gains `colors`: the resolved light palette as hex (all values the
  canvas needs: accent, header, header text, background, enum header, enum title).
- `model_fingerprint` includes the resolved colours, so editing the table makes
  `/api/status` report a change and the page reloads the diagrams (goal 5).
- **Light mode:** the canvas sets them as CSS variables on the diagram (e.g. `--erd-*`)
  and `BoxNode.vue` uses those instead of the Nuxt UI tokens for these roles. The accent
  also keeps driving the canvas-only uses it drives today (hover/selection outline, NEW
  chip).
- **Dark mode:** the diagram keeps today's built-in dark look and ignores the configured
  colours. The export is light only, and brand colours are chosen for light backgrounds.
  *(Claude's call.)*
- The canvas page background (`bg-muted`) is UI, not diagram: `background` doesn't change
  it.

### Docs and release

- `docs/configuration.md`: the table, the four keys with roles and defaults, the
  `header_text` contrast rule, and the devsuit brand as an example.
- The export page: changing colours makes the committed SVGs outdated, so `check` fails
  until the next export or Save, which is intended.
- CHANGELOG `[Unreleased]` → Added.

## Tests

- Config: valid keys, case normalisation, every invalid shape (`ConfigError` text), a
  non-table `colors`, unknown keys (warning), the dark-`background` warning (and none for
  a light one).
- Palette: defaults give today's nine values exactly (including `#d8deff`); the
  `header_text` contrast rule both ways; the enum title's contrast pick; the OKLab mix on
  a known pair.
- Export: no `colors` table → byte-identical to today (the existing fixtures in
  `tests/fixtures/export/` must not change); with colours → the values appear in the
  right attributes.
- Server: `/api/diagrams` carries `colors`; the fingerprint changes when a colour changes.
- Frontend: typecheck; no frontend test suite exists.

## Left to the builder

- Names of the new dataclass, the palette function and the CSS variables.
- Whether the colour maths lives in `_svg.py` or its own module.
- How the canvas falls back while the first `/api/diagrams` response is loading.

## Follow-up: every colour (#67, 2026-11-24)

The user asked to make the remaining colours configurable without a fixed use case
("I don't know yet"), so the simplest version was built:

- Five more optional keys with today's values as defaults: `text`, `text_muted`,
  `border`, `border_strong`, `background_muted` (Palette field `border_accented` renamed
  `border_strong`). No output change without them.
- Defaults don't adapt to a dark `background`; a dark theme sets the text colours too
  (documented example). Automatic dark defaults can follow when a need shows up.
- The contrast warning checks the configured `text` (else the default) on `background`.
- The palette gains `accent_text` (white or `#0f172b` by contrast with `accent`) for the
  canvas's NEW chip; the export doesn't draw it.
- The API's `colors` gains `text`, `textMuted`, `border`, `borderStrong`,
  `backgroundMuted`, `accentText`; the canvas maps them in light mode as before.
