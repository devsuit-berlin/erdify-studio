# erdify-studio

![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.15-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-pre--alpha-orange)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/devsuit-berlin/erdify-studio/badges/coverage.json)](https://github.com/devsuit-berlin/erdify-studio/actions/workflows/test.yml)

Arrange your [erdify](https://github.com/devsuit-berlin/erdify) ERDs by drag and drop,
commit the layout to your repo and check in CI that it stays up to date.

**Documentation: <https://devsuit-berlin.github.io/erdify-studio/>**

> **Status: pre-alpha.** `check`, `place --auto`, the canvas (overview and group
> diagrams, live reload) and SVG export work; the first release is next. Progress is tracked in the
> [v0.1.0 milestone](https://github.com/devsuit-berlin/erdify-studio/milestone/1).

erdify generates ERDs from your code (SQLModel, SQLAlchemy, Django, Pydantic,
dataclasses, SQL DDL), always auto-laid-out. erdify-studio adds a hand-made layout
that survives schema changes and is shared through git — the same way
`erdify --check` keeps a committed diagram in sync with the models.

## Install

```bash
pip install erdify-studio          # no Node, no database, no browser engine needed
pip install "erdify-studio[sql]"   # to read SQL DDL (pulls in erdify[sql])
```

## Commands

```bash
erdify-studio [path]               # open the canvas in your browser, drag, save
erdify-studio check [path]         # exit 1 if the committed layout is out of date
erdify-studio place --auto [path]  # place new tables, drop stale entries
erdify-studio export [path]        # write one SVG per diagram to export_dir
```

Options and sources come from erdify's config (`[tool.erdify]` in `pyproject.toml`)
plus a `[tool.erdify-studio]` section.

## Arrange the diagram

```bash
erdify-studio [path]                     # same as: erdify-studio open [path]
erdify-studio --no-browser --port 8765   # print the URL instead of opening a browser
```

Serves the diagrams on `127.0.0.1` (a free port unless `--port` is given) and opens
them in your browser; Ctrl+C stops it. Every entity shows its fields (PK / FK / UK
badges, type, `?` for nullable), enums erdify draws show their values, and the edges are
erdify's own, with crow's-foot ends.

- The list on the left switches between the overview and one diagram per group
  (`[tool.erdify-studio] group_by`). A group diagram shows its own entities, the enums
  they use, and a greyed-out, name-only **foreign box** for every entity of another
  group they are connected to. Click a foreign box to open its group's diagram; drag
  it to move it. A dot marks diagrams with unsaved changes; the URL keeps the open one.
- Each diagram has its own positions: moving an entity in one diagram doesn't move it
  in another.
- Drag a box: its edges follow and "Unsaved changes" appears. Drag the background to
  pan, scroll or use the buttons to zoom.
- **Save** (or Ctrl/⌘+S) writes every diagram to the layout file at once, so `check`
  passes afterwards; entries for tables or groups that no longer exist are dropped.
- Boxes without a position are placed like `place --auto` does and marked **NEW** until
  you save.
- **Live reload**: edit your models while studio is open and the canvas follows within
  about a second. New tables are placed next to your arrangement and marked NEW,
  removed ones disappear (and leave the layout file on the next Save), boxes whose
  columns change keep their position. Unsaved drags are never lost. While a model file
  can't be loaded (half-typed), studio keeps the last good diagram and says why.
- If the layout file changes on disk (a `git checkout`, another tab), studio says so;
  Save then refuses instead of overwriting it: reload the page.
- Closing the tab with unsaved changes asks first.

Like `check`, it exits 2 without starting when the canvas is not built (a source
checkout without `uv run poe frontend`), when the project, its config or the layout
file cannot be read, or erdify finds no entities. The page talks to the local server
only: no CDN, fonts and icons ship in the wheel, and the API needs the random token in
the URL it opens, so other web pages cannot change your layout.

## Check in CI

```bash
erdify-studio check [path]   # path: the input erdify reads (default: .)
```

Exits 1 with one line per problem when an entity, a foreign box (an entity of another
group connected by a relationship) or an enum erdify draws has no position in a diagram
(an enum belongs on the overview and on the group diagrams of the entities using it),
when the layout file holds entries or diagrams that no longer exist, or when there is
no layout file yet (missing or empty); the last line suggests `erdify-studio place --auto`.
Exits 0 without output when the layout is up to date, and 2 when the project, its config
or the layout file cannot be read (a model file erdify cannot parse included, whatever
`strict` says), or erdify finds no entities (set erdify's `allow_empty` to check an
empty project); an internal error also exits 2, with its traceback. Runs without a
browser, Node or network.

With `export_dir` set and the layout up to date, `check` also exits 1 when an exported
SVG is missing, out of date (e.g. a new column made a box taller) or stale (a group
that no longer exists), one line each, and suggests `erdify-studio export`.

With [pre-commit](https://pre-commit.com):

```yaml
repos:
  - repo: https://github.com/devsuit-berlin/erdify-studio
    rev: v0.1.0
    hooks:
      - id: erdify-studio-check
        args: [./src]                               # optional, default: .
        # additional_dependencies: ['erdify[sql]']  # for SQL DDL
```

The hook runs when a `models.py`, a `.sql` file, `erdify-layout.json` or
`pyproject.toml` changes; override `files` for other names. Deleting a file does not
trigger pre-commit hooks, so also run `erdify-studio check` (or
`pre-commit run --all-files`) in CI.

## Place new tables without the canvas

```bash
erdify-studio place --auto [path]
```

Fixes what `check` reports, without opening the browser:

- An entity, foreign box or enum without a position goes next to a placed box it has a
  relationship with, or for an enum an entity using it (right, below, left or above —
  the first free spot), otherwise into the first free slot of a grid right of the
  diagram.
- Boxes that already have a position never move.
- Entries and diagrams that no longer exist are removed (one line each).
- Without a layout file it creates one with every diagram.

The result is deterministic — run twice, same bytes — and the file is only written when
something changed. Exit codes: 0 on success, 2 like `check` when something cannot be
read (a layout file that is not valid, e.g. with git conflict markers, is never
overwritten).

## Export SVGs

```bash
erdify-studio export [path]
```

Writes every diagram as you arranged it to `[tool.erdify-studio] export_dir`, ready to
commit and embed in READMEs and docs:

- `overview.svg`, and `groups/<group>.svg` per group diagram (the group name in
  lowercase ASCII with `-` between words, e.g. `my app` → `groups/my-app.svg`; a name
  without Latin letters gets a stable `group-<hash>.svg`;
  entities without a group → `groups/ungrouped.svg`). Two groups that would share a
  file are an error (exit 2) naming both.
- Studio's light theme on a white background, so the diagrams read well on light and
  dark pages; the font is JetBrains Mono where installed, else the system's monospace.
- Byte-identical on every machine, so CI can compare the committed files.
- `groups/*.svg` of groups that no longer exist are deleted; nothing else in
  `export_dir` is touched. Unchanged files are not rewritten.
- Exits 1 while the layout file is out of date (run `place --auto` or Save in studio
  first), 2 without `export_dir`.

With `export_dir` set, **Save** in studio writes the SVGs too, and studio says so when
they are out of date, so one Save brings them up to date.

Without committing anything: **Download SVG** in studio's toolbar downloads the open
diagram as SVG, drawn the same way, with the positions on screen (saved or not). It
needs no `export_dir`.

## Configuration

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## License

MIT
