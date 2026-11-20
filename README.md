# erdify-studio

![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.15-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-pre--alpha-orange)

Arrange your [erdify](https://github.com/devsuit-berlin/erdify) ERDs by drag and drop,
commit the layout to your repo and check in CI that it stays up to date.

> **Status: pre-alpha.** `check`, `place --auto` and the overview canvas work; group
> diagrams and SVG export are still to come. Progress is tracked in the
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
erdify-studio export [path]        # planned: write deterministic SVGs
```

Options and sources come from erdify's config (`[tool.erdify]` in `pyproject.toml`)
plus a `[tool.erdify-studio]` section.

## Arrange the diagram

```bash
erdify-studio [path]                     # same as: erdify-studio open [path]
erdify-studio --no-browser --port 8765   # print the URL instead of opening a browser
```

Serves the overview diagram on `127.0.0.1` (a free port unless `--port` is given) and
opens it in your browser; Ctrl+C stops it. Every entity shows its fields (PK / FK / UK
badges, type, `?` for nullable), enums erdify draws show their values, and the edges are
erdify's own, with crow's-foot ends.

- Drag a box: its edges follow and "Unsaved changes" appears. Drag the background to
  pan, scroll or use the buttons to zoom.
- **Save** (or Ctrl/⌘+S) writes the layout file: the overview as you arranged it, plus
  what `place --auto` would do for the rest (group diagrams get missing boxes, stale
  entries are dropped), so `check` passes afterwards.
- Boxes without a position are placed like `place --auto` does and marked **NEW** until
  you save.
- If the layout file changed, or tables were added or removed, after the page loaded
  (a `git checkout`, another tab), Save refuses instead of overwriting: reload the
  page, which reads both again.
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
own key. Enums are keyed `enum:<name>`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## License

MIT
