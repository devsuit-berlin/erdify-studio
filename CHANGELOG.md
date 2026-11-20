# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Entities that would share a layout key are keyed by erdify's entity name instead of
  being refused: same-name model classes in different modules, which the next erdify
  release draws as `module.Class` (erdify#367), and several classes of one table. A
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
- Requires erdify 1.8.0: the enums erdify draws (`erdify.enum_users`), same-name
  tables in different schemas and schema-qualified foreign keys are laid out exactly
  as erdify draws them.
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
