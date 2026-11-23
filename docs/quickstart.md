# Quickstart

In a project erdify already reads (`[tool.erdify]` in `pyproject.toml`):

```bash
erdify-studio                     # 1. opens the canvas in your browser
```

2. Drag the boxes into the arrangement your team reads; switch between the overview and
   the group diagrams on the left.
3. **Save** (Ctrl/⌘+S) writes `erdify-layout.json` next to `pyproject.toml`.
4. Commit it, and add the check to CI or pre-commit:

```bash
erdify-studio check               # exit 1 when a new table has no position yet
erdify-studio place --auto        # place new tables without opening the browser
```

Optional: set `export_dir` (see [Configuration](configuration.md)) to commit the diagrams
as SVG; Save and `erdify-studio export` keep them current, and `check` fails when they
aren't.

## Commands

```bash
erdify-studio [path]               # open the canvas in your browser, drag, save
erdify-studio check [path]         # exit 1 if the committed layout is out of date
erdify-studio place --auto [path]  # place new tables, drop stale entries
erdify-studio export [path]        # write one SVG per diagram to export_dir
```

Options and sources come from erdify's config (`[tool.erdify]` in `pyproject.toml`)
plus a `[tool.erdify-studio]` section.
