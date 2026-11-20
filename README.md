# erdify-studio

![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.15-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-pre--alpha-orange)

Arrange your [erdify](https://github.com/devsuit-berlin/erdify) ERDs by drag and drop,
commit the layout to your repo and check in CI that it stays up to date.

> **Status: pre-alpha.** Nothing to use yet — the commands below describe the planned
> MVP. Progress is tracked in the
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

## Planned commands

```bash
erdify-studio [path]               # open the canvas in your browser, drag, save
erdify-studio check [path]         # exit 1 if the committed layout is out of date
erdify-studio place --auto [path]  # place new tables, drop stale entries
erdify-studio export [path]        # write deterministic SVGs
```

Options and sources come from erdify's config (`[tool.erdify]` in `pyproject.toml`)
plus a `[tool.erdify-studio]` section.

## Configuration

```toml
[tool.erdify-studio]
layout = "docs/erd/erdify-layout.json"   # default: erdify-layout.json next to pyproject.toml
group_by = "auto"                        # auto | schema | app | module | none
export_dir = "docs/erd"                  # optional; omitted = no committed SVGs
```

`group_by = "auto"` picks, per entity, its database schema, else its Django app, else its
Python module. Entities are keyed in the layout file by `schema.table` (or `table`), so
renaming a class keeps its position.

## Known limitations

- SQL DDL with same-name tables in different schemas (`core.customer`, `mart.customer`)
  is read as one table by erdify for now
  ([erdify#353](https://github.com/devsuit-berlin/erdify/issues/353)).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## License

MIT
