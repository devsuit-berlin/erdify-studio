# Quickstart

In a project erdify already reads (`[tool.erdify]` in `pyproject.toml`):

1. Open the canvas in your browser:

    ```bash
    erdify-studio
    ```

2. Drag the boxes into the arrangement your team reads; switch between the overview and
   the group diagrams on the left.
3. **Save** (Ctrl/⌘+S) writes the layout file (default: `erdify-layout.json` next to
   `pyproject.toml`).
4. Commit it, and add the check to CI or pre-commit ([how](usage/ci.md)):

    ```bash
    erdify-studio check            # exit 1 when a new table has no position yet
    erdify-studio place --auto     # place new tables without opening the browser
    ```

Optional:

- Set `export_dir` (see [Configuration](configuration.md)) to commit the diagrams as SVG;
  Save and `erdify-studio export` keep them current, and `check` fails when they aren't.
  **Download SVG** in the toolbar grabs the open diagram without committing anything.
- Give the diagrams your brand's colours: try them in the **Colours** panel of the
  canvas, then put the copied table into `pyproject.toml`, replacing its colours table
  if it has one ([Diagram colours](configuration.md#diagram-colours)).

## Commands

```bash
erdify-studio [path]               # open the canvas in your browser, drag, save
                                   # (--port, --no-browser: see "The canvas")
erdify-studio check [path]         # exit 1 if the committed layout is out of date
erdify-studio place --auto [path]  # place new tables, drop stale entries
erdify-studio export [path]        # write one SVG per diagram to export_dir
```

Options and sources come from erdify's config (`[tool.erdify]` in `pyproject.toml`)
plus a [`[tool.erdify-studio]`](configuration.md) section.
