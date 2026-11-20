# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
  config or layout file cannot be read, or erdify finds no entities (unless
  `allow_empty`). Positions of existing enums are kept but not required yet
  (erdify#369). A pre-commit hook `erdify-studio-check` runs it. Python API:
  `check_project`, `diagram_contents`, `DiagramContent`, `check_layout`, `Problem`,
  `ProblemKind`, `ProjectError`.
- `[tool.erdify-studio]` in `pyproject.toml`: `layout` (default `erdify-layout.json`
  next to the `pyproject.toml` erdify resolves, else the working directory),
  `group_by` (`auto` | `schema` | `app` | `module` | `none`) and `export_dir`.
