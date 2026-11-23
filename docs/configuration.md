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

erdify's own settings (`[tool.erdify]`: `include`, `sources`, `exclude`, `strict`,
`no_enums`, `no_relationships`, `allow_empty`, …) decide which entities exist; see
[erdify's documentation](https://erdify.devsuit.io/). erdify-studio reads the same
`pyproject.toml`.
