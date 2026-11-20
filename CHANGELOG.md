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
  overwritten. Python API: `Layout`, `load_layout`, `save_layout`, `entity_keys`,
  `entity_groups`, `load_config`.
- `[tool.erdify-studio]` in `pyproject.toml`: `layout` (default `erdify-layout.json`
  next to the `pyproject.toml` erdify resolves, else the working directory),
  `group_by` (`auto` | `schema` | `app` | `module` | `none`) and `export_dir`.
