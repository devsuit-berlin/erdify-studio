# Deterministic SVG export and export check (#8)

## Intent

The arranged diagrams should be visible outside studio: committed as SVG next to the
code, embedded in READMEs and docs, and kept current by CI the same way `check` keeps
the layout file current. Rendered in Python, with no browser, and byte-identical on
every machine, so CI can compare the committed files byte for byte.

## Goals (issue #8 acceptance criteria)

1. **Export**: `erdify-studio export [path]` writes one SVG per diagram to `export_dir`.
2. **Deterministic**: running the export twice, on any machine, gives byte-identical SVGs.
3. **Save**: with `export_dir` set, Save in the UI writes the SVGs too.
4. **Check**: with `export_dir` set, `check` fails when a committed SVG differs.
5. **Looks**: boxes and edges sit where they are in studio, with crow's-foot ends.

## Non-goals

- PNG export (a later, optional extra).
- Dark-theme SVGs, or `<picture>` pairs.
- Embedding a font.
- Edge labels drawn as text. Studio shows them only as a tooltip; the SVG carries
  them as `<title>` like the canvas does.

## Anti-goals

- An SVG that differs between machines, Python versions or operating systems: no
  timestamps, no locale-dependent number formatting, no platform line endings, no
  dict/set iteration order that isn't sorted or fixed.
- A canvas and an export that quietly drift apart (see Approaches).
- Touching files in `export_dir` that the export doesn't own.

## Constraints

- No new runtime Python dependency (stdlib only: `xml.sax.saxutils`,
  `unicodedata`, `pathlib`).
- Box geometry from `_place.py`, contents and edge rule from `DiagramContent`
  (`shows_edge`, `shows_enum_link`), and positions from the layout file. The export
  re-implements only the *drawing*: borders, fans, loops and markers from
  `frontend/src/geometry.ts`, and the styles of `BoxNode.vue` / `EdgeLine.vue`.
- Library code raises (a new `ExportError(StudioError)`); only `cli.py` prints.

## Approaches

| | Approach | Trade-off |
|---|---|---|
| **1 (chosen)** | Port `geometry.ts` to Python, plus a CI cross-check: a Node script runs `geometry.ts` on shared cases, and a Python script compares the results with the Python port | Two copies of ~150 lines, but CI goes red as soon as one side changes alone. About 30 lines of script and one CI step. |
| 2 | Port without a cross-check | Cheaper now, but the copies drift unnoticed, and the SVG stops matching studio (breaks criterion 5 silently). |
| 3 | Python computes edge geometry, the canvas fetches it | No second copy, but dragging needs a server round-trip per move (laggy), or a local copy during the drag anyway. |

The user picked 1 (2026-11-23).

## Design

### Files in `export_dir` (user decision, option A)

- `overview.svg` for the overview.
- `groups/<slug>.svg` for every group diagram; `_default` → `groups/ungrouped.svg`.
- **Slug**: NFKD-normalise, drop non-ASCII, lowercase, replace each run of characters
  outside `[a-z0-9]` with `-`, strip `-` at both ends; an empty result becomes
  `group`. `my app` → `my-app`, `Bestellungen/Ä` → `bestellungen-a`.
- Two groups with the same slug (`my app` and `my-app`, or a group literally named
  `ungrouped` next to `_default`) → `ExportError` naming both groups. `export`
  exits 2, `check` exits 2, and Save reports it (see below).
- The export **owns** `overview.svg` and `groups/*.svg`. It deletes stale
  `groups/*.svg` files (groups that no longer exist) and touches nothing else in
  `export_dir`. It creates `export_dir` and `groups/` when missing (also when there
  are no groups: then `groups/` is not created, and an existing one only loses its
  stale `*.svg`).

### Look (user decision: light theme, white background)

- One fixed light palette, the values of studio's **light** theme (Nuxt UI tokens
  used by `BoxNode.vue` / `EdgeLine.vue`: `--ui-bg`, `--ui-bg-muted`,
  `--ui-bg-accented`, `--ui-border`, `--ui-border-accented`, `--ui-text-highlighted`,
  `--ui-text-muted`, `--ui-primary`), read from the built CSS and recorded once as
  hex constants in the Python module, with a comment naming each token.
- An explicit white background `<rect>` covering the `viewBox`.
- Boxes as the canvas draws them: body, header band, title, the field rows (badges
  `PK FK UK`, name, type with `?` for nullable), dividers, frame, and enums with the
  enum header tint. Foreign boxes as the canvas draws them: muted fill, muted title,
  dashed frame, title only. No NEW chip, no highlight, no dragging state.
- Edges: line plus crow's-foot markers; enum links dashed, without markers; edge
  label as `<title>` inside the edge's `<g>`.
- **Font**: `font-family` `"JetBrains Mono", ui-monospace, Menlo, Consolas,
  "DejaVu Sans Mono", monospace`; font size `charWidth / 0.6` as in `drawing.ts`. No
  embedded font (user accepted: system monospace fonts have about the same advance).
- `viewBox` = bounding box of every drawn box, plus the self-loop reach on the right,
  plus a 40-unit margin (`FIT_MARGIN`); `width` / `height` = the `viewBox` size.

### Determinism

- Numbers: integers as integers. Everything else through one formatter: round to 2
  decimals, `-0` → `0`, trailing zeros and a trailing `.` removed (`12.50` → `12.5`,
  `3.00` → `3`).
- Order: the background, then enum links, then edges (in `diagram_edges` order, as
  the payload has them), then boxes sorted by key; attributes always in the same
  order (written by hand, not by a DOM library).
- Text escaped with `xml.sax.saxutils.escape` (plus `"` in attributes).
- UTF-8, `\n` line endings, written with `newline="\n"`; a trailing newline.
- No timestamps, no generator comment with a version.

### API (Python)

- `render_svg(diagram: DiagramJson, boxes: dict[str, BoxDef], metrics: dict[str, int]) -> str`
  in a new `_svg.py`. It draws exactly what the payload says, so the SVG and the
  canvas read the same input (`build_diagrams` from #6).
- `_geometry.py` (new): the Python port of `geometry.ts`, with the same function
  names in snake_case (`border_point`, `fan_offsets`, `edge_line`, `self_loop`,
  `angle`, `end_marker`) and the same constants (`FAN_STEP`, marker sizes).
- `export_files(project, config) -> dict[Path, str]` (relative path → SVG text) and
  `export_project(project, config) -> ExportResult` (written, deleted). Both raise
  `ExportError` without `export_dir`.
- The positions come from the **layout file**: `export` refuses (exit 1, with
  `check`'s problem lines and the `place --auto` hint) while `check_project`
  reports problems, so an exported SVG never shows positions that aren't committed.

### CLI

- `erdify-studio export [path]`: writes the files. Exit codes: 0 written (prints
  one line per file written or deleted, or "SVGs up to date"); 1 layout out of date
  (as above); 2 no `export_dir`, an `ExportError` (slug collision), or anything
  `check` exits 2 for.
- `check`: with `export_dir` set and the layout up to date, it also compares the
  files `export_files` would write with the files on disk, one line per missing,
  outdated or stale (`groups/*.svg` with no group) file
  (`export 'docs/erd/overview.svg' is out of date`); the last line suggests
  `erdify-studio export`. Without `export_dir`, `check` is unchanged.
- **Public API unchanged** (builder-check call): `check_project`, `Problem` and
  `ProblemKind` stay as they are; an SVG problem is about a file, not a diagram
  entry. The comparison is a private `_export.check_exports(project, config) ->
  list[str]` (messages), called by `cli._check` after `check_project`. Nothing new
  goes into `__all__`.
- `place --auto` does not export (it only writes the layout file).

### Save in the UI

- With `export_dir` set, `PUT /api/layout` exports after writing the layout file.
- **Outdated SVGs are visible and fixable in studio (user decision, 2026-11-23).**
  `GET /api/diagrams` compares, like `check`, what the export would write with the
  files on disk (only when `export_dir` is set and the layout is up to date) and
  sends `pending.svgs`: the number of missing, outdated or stale SVG files. When it
  is not 0 and nothing else is pending, the banner says "The SVGs in
  `<export_dir>` are out of date — save to update them." and Save is enabled
  (the page sends every diagram unchanged). A model change that only makes boxes
  taller is then fixed by one Save.
- The response gains `"exported": <number of files written or deleted>` on success.
  An export failure (e.g. a slug collision) after the layout was written returns
  **200** with `"exportError": "<message>"` and the new revision: the layout is
  saved, and the page shows a warning toast ("Saved, but the SVG export failed:
  …") and keeps Save enabled so it can be retried. A 500 would make the page think
  the save failed and hold on to an old revision.
- `exportPath` (the `export_dir` as the UI shows it, or null) is added to the
  payload for the banner text.

### Cross-check (approach 1)

- `scripts/geometry_cases.json`: input cases: box pairs in every direction (incl.
  overlapping and touching boxes), fans of 1–4 parallel edges, A→B plus B→A,
  self-loops with index 0–2, and every `{optional, many}` end.
- `scripts/geometry_parity.mjs`: imports `frontend/src/geometry.ts` (Node 24 strips
  the types; if the extensionless `./drawing` import blocks that, import
  `./drawing.ts` and enable `allowImportingTsExtensions`; builder's call), runs every
  case and prints JSON.
- `scripts/check_geometry.py`: runs `_geometry.py` on the same cases and compares
  with the JSON read from stdin, numbers within 0.01; exits 1 naming the first
  difference.
- CI: one step in the Package job (Node is set up there):
  `node scripts/geometry_parity.mjs | uv run python scripts/check_geometry.py`.
- `tests/test_geometry.py` runs the Python side of the same cases against expected
  values, so local `poe test` covers the port without Node.

### Tests

- Slug rule (parametrized, incl. umlauts, slashes, empty → `group`) and collisions.
- `render_svg`: a small fixed project gives a **golden file**
  (`tests/fixtures/export/overview.svg`, `groups/*.svg`); determinism: rendering
  twice is equal, and a project rendered from a copied directory is byte-equal.
- Number formatter (`-0`, `12.50`, `3.00`, large values).
- `export_project`: writes, overwrites, deletes stale `groups/*.svg`, leaves other
  files alone, creates folders, refuses an out-of-date layout, `ExportError` without
  `export_dir`.
- `check` with `export_dir`: missing / outdated / stale each reported; up-to-date
  passes; unchanged without `export_dir`.
- CLI `export` exit codes and output; server save with `export_dir` (files written,
  `exported` count, `exportError` path); `pending.svgs` in `GET /api/diagrams`
  (0 when current, counted when a model change makes a box taller, absent effect
  without `export_dir`).

## Left to the builder

- Exact hex values (read from the built CSS, light theme) and their constant names.
- Module split (`_svg.py` / `_geometry.py` / `_export.py`) and helper names.
- How the parity script imports `geometry.ts` (see above).
- The toast wording beyond the given sentence.
