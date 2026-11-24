# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Colours panel: a half-typed colour no longer holds back the preview of the other
  rows, the row marked invalid is always the one the server rejected, "Header text"
  says "automatic" while it follows the header, unset rows are greyed, and the
  dark-mode note follows a theme switch while the panel is open (#78).

## [0.2.0] - 2026-11-24

### Added

- Configurable diagram colours: `[tool.erdify-studio.colors]` (`accent`, `header`,
  `header_text`, `background`, all optional `#rrggbb`) colours the canvas (light mode),
  the exported SVGs and Download SVG. Enum boxes derive from them, low contrast between
  `text` and `background` logs a warning, and changing colours makes committed SVGs
  outdated until the next `export` or Save (#48). Every other diagram colour is
  configurable too: `text`, `text_muted`, `border`, `border_strong`, `background_muted`;
  the canvas's NEW chip text follows the accent (#67).
- A **Colours** panel in studio previews diagram colours on the canvas without writing
  anything and copies them as a `[tool.erdify-studio.colors]` table (**Copy TOML**). The
  server resolves them (`POST /api/colors`); `GET /api/diagrams` gains `colorConfig`, the
  keys set in `pyproject.toml` (#68).

### Fixed

- Docs site: the icon and wordmark on the Brand page load again. A docs hook
  (`scripts/mkdocs_raw_html_urls.py`) resolves relative `src`/`srcset` in raw HTML for
  the page URL, and a broken one fails the strict build. The wordmark follows the site's
  light/dark toggle instead of the operating system's setting.
- A refused HEAD or OPTIONS request with a body (answered 501) closes cleanly too, so
  the client reads the response instead of a connection reset.
- A connection that stays silent for 10 s (no request, or a body that never arrives
  after its `Content-Length`) is closed instead of holding a server thread forever.

## [0.1.2] - 2026-11-24

### Changed

- Wordmark: "studio" is now a Roboto Medium descriptor next to "erdify" instead of a
  monoline word, so the wordmark uses one type family.
- Favicon: a simplified icon (no pointer, crow's foot, key dots or field bars) for the
  docs site and the studio UI, legible at 16 px. Added
  `docs/assets/erdify-studio-favicon.svg` as its source.
- Docs header logo uses the favicon, and the README wordmark is as tall as erdify's
  (147 px), so both READMEs show the icon and "erdify" at the same size.

### Fixed

- A refused request of any method with a body (e.g. a GET with a wrong token) closes
  cleanly, so the client reads the 403 instead of a connection reset (seen on Windows).

## [0.1.1] - 2026-11-24

### Added

- erdify-studio logo (icon, light/dark wordmarks, favicon) on the docs site, in the README
  and as the studio UI's favicon, plus brand guidelines (`docs/brand.md`).
- `Documentation` project URL (PyPI sidebar) pointing at the docs site.

### Changed

- The docs site moved to <https://erdify-studio.devsuit.io/>.
- The studio UI uses the devsuit palette of `docs/brand.md` (buttons, banners; periwinkle in
  dark mode) and shows the studio icon in the header. The diagram keeps its colours, so
  the canvas still matches the SVG export and exported SVGs don't change.

### Fixed

- A request with a non-ASCII `Content-Length` (e.g. `²`) gets a 411 instead of
  crashing the request handler.
- The layout path studio shows (the Save message, banners) follows a changed
  `[tool.erdify-studio] layout` while studio runs, instead of the path at startup.
- After Save, the layout file's revision is the one of what studio wrote: a change by
  someone else right after the write is reported as a conflict on the next Save instead
  of being overwritten.
- A group whose SVG file collides with the entities without a group: the error names
  the group to rename.

### Security

- The canvas page sends a `Content-Security-Policy` (own files only), and the access
  log no longer contains the page URL's token.

## [0.1.0] - 2026-11-23

### Added

- Documentation site (MkDocs Material, GitHub Pages): installation, quickstart, the
  canvas, `check` in CI and pre-commit, `place --auto`, `export`, configuration and the
  layout file.
- Live reload: studio re-parses the project about every second (slower for large
  projects) and the canvas follows model edits without losing unsaved positions — new
  tables are placed next to the arrangement and marked NEW, removed ones disappear,
  resized boxes keep their place. A model file that can't be loaded keeps the last good
  diagram with an error banner; a layout file changed on disk is reported. New routes
  `GET /api/status` and `POST /api/diagrams`; a 409 carries `reason` (`models` or
  `layout`).
- `erdify-studio export [path]`: writes every diagram as SVG to
  `[tool.erdify-studio] export_dir` — `overview.svg` and `groups/<group>.svg` — in
  studio's light theme on a white background, byte-identical on every machine. Stale
  `groups/*.svg` are deleted, nothing else in `export_dir` is touched; two groups that
  would share a file are an error. Exits 1 while the layout file is out of date.
- With `export_dir` set, `check` also reports missing, outdated and stale SVGs, and
  Save in studio writes them; studio shows when they are out of date, and a failed
  export after a save is reported without losing the saved layout.
- **Download SVG** in studio's toolbar: the open diagram as SVG with the positions on
  screen, without `export_dir` and without writing a file (`POST /api/svg`).
- Group diagrams in the canvas: a list switches between the overview and one diagram
  per group. A group diagram shows its entities, the enums they use and greyed-out,
  name-only foreign boxes for connected entities of other groups; clicking one opens
  its group. Positions are kept per diagram, and one Save writes every diagram. Edges
  between two foreign boxes are not drawn. The API serves every diagram at
  `GET /api/diagrams` (replacing `/api/overview`), and `PUT /api/layout` takes
  `{"revision", "diagrams"}`.
- Entities that would share a layout key are keyed by erdify's entity name instead of
  being refused: same-name model classes in different modules, which erdify draws as
  `module.Class` (erdify#367), and several classes of one table. A
  unique key is unchanged; `DuplicateKeyError` remains for a name key that equals
  another entity's key.
- `erdify-studio [path]` (also `erdify-studio open`, with `--port` and `--no-browser`):
  serves the overview diagram on 127.0.0.1 and opens it in the browser. Boxes show the
  fields erdify shows and erdify's edges with crow's-foot ends; dragging a box moves its
  edges and marks the diagram unsaved; Save (or Ctrl/⌘+S) writes what `place --auto`
  would write with the arranged overview, so `check` passes. Unplaced boxes are placed
  like `place --auto` and marked NEW until saved. A layout file changed since the page
  loaded is never overwritten (409, reload). The API needs a per-run token and checks
  `Host` / `Origin`; the built page loads nothing from the network
  (`scripts/check_static.py` in CI).
- Requires erdify 1.9.0: the enums erdify draws (`erdify.enum_users`), same-name
  tables in different schemas, schema-qualified foreign keys and same-name model
  classes in different modules (`module.Class`, erdify#367) are laid out exactly as
  erdify draws them.
- Package scaffold: `pip install erdify-studio` installs the `erdify-studio` command
  (`--help`, `--version`) with erdify as a dependency; `erdify-studio[sql]` pulls in
  `erdify[sql]`. The browser frontend is built in CI and shipped inside the wheel, so no
  Node is needed on the user's machine.
- The layout file (`erdify-layout.json`): entity positions per diagram, sorted with one
  entry per line, integer positions and a trailing newline, so the same layout always
  writes the same bytes. Entities are keyed by `schema.table` (or `table`), enums by
  `enum:<name>`, so a renamed class keeps its position; two entities with the same key
  are an error naming both. A file of an unknown `version` is refused and never
  overwritten, and neither is a file that is not a valid layout (e.g. with git
  conflict markers): its positions would be lost. Python API: `Layout`, `Position`,
  `load_layout` / `loads_layout`, `save_layout` / `dumps_layout`, `entity_key`,
  `entity_keys`, `enum_key`, `entity_groups`, `load_config`, `StudioConfig`, `GroupBy`, the diagram
  names `OVERVIEW` / `DEFAULT_GROUP`, `LAYOUT_VERSION`, and the errors `StudioError`,
  `ConfigError`, `LayoutError`, `LayoutVersionError`, `DuplicateKeyError`.
- `erdify-studio check [path]`: exits 1 with one line per problem when an entity or a
  foreign box (an entity of another group connected by an edge, in either direction)
  has no position in its diagram, the layout file has stale entries or diagrams, or
  the layout file is missing or empty; the last line suggests `erdify-studio place
  --auto`. Exits 0 without output when the layout is up to date, 2 when the project,
  config, a model file or the layout file cannot be read, or erdify finds no entities
  (unless `allow_empty`), and on an internal error (with its traceback). Every enum
  erdify draws needs a position on the overview and on the group diagrams of the
  entities using it (problem kind `enum`); a layout without them fails `check` once,
  `erdify-studio place --auto` adds them. A pre-commit hook
  `erdify-studio-check` runs it. Python API: `check_project`, `Problem`,
  `ProblemKind`, `ProjectError`.
- `erdify-studio place --auto [path]`: gives every entity and foreign box without a
  position one next to a placed box it is connected with (right, below, left or above),
  else the first free slot of a grid right of the diagram; placed boxes never move. Drops
  stale entries and diagrams, places enums next to an entity using them, and creates the layout
  file with every diagram when there is none. Deterministic: the same input gives the
  same bytes, the file is only written when something changed, and `check` passes
  afterwards. Python API: `place_project`, `PlaceResult`.
- `[tool.erdify-studio]` in `pyproject.toml`: `layout` (default `erdify-layout.json`
  next to the `pyproject.toml` erdify resolves, else the working directory),
  `group_by` (`auto` | `schema` | `app` | `module` | `none`) and `export_dir`.

[Unreleased]: https://github.com/devsuit-berlin/erdify-studio/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/devsuit-berlin/erdify-studio/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/devsuit-berlin/erdify-studio/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/devsuit-berlin/erdify-studio/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/devsuit-berlin/erdify-studio/releases/tag/v0.1.0
