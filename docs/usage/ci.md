# Check in CI & pre-commit

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
that no longer exists), one line each, and suggests `erdify-studio export`. Changing
the [diagram colours](../configuration.md#diagram-colours) makes the SVGs out of date
too, until the next `export` or Save.

In GitHub Actions (any CI works the same way — install, then run `check`):

```yaml
jobs:
  erd:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - run: pip install erdify-studio          # "erdify-studio[sql]" for SQL DDL
      - run: erdify-studio check ./src          # the path erdify reads (default: .)
```

erdify reads the model files as source text, without importing them, so the job needs
neither your project's dependencies nor a database.

With [pre-commit](https://pre-commit.com):

```yaml
repos:
  - repo: https://github.com/devsuit-berlin/erdify-studio
    rev: v0.2.1
    hooks:
      - id: erdify-studio-check
        args: [./src]                               # optional, default: .
        # additional_dependencies: ['erdify[sql]']  # for SQL DDL
```

The hook runs when a `models.py`, a `.sql` file, `erdify-layout.json` or
`pyproject.toml` changes; override `files` for other names. Deleting a file does not
trigger pre-commit hooks, so also run `erdify-studio check` (or
`pre-commit run --all-files`) in CI.
