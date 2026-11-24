# Export SVGs

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
- Studio's light theme on a white background by default, so the diagrams read well on
  light and dark pages; the font is JetBrains Mono where installed, else the system's
  monospace.
- Byte-identical on every machine, so CI can compare the committed files.
- `groups/*.svg` of groups that no longer exist are deleted; nothing else in
  `export_dir` is touched. Unchanged files are not rewritten.
- Uses the colours of [`[tool.erdify-studio.colors]`](../configuration.md#diagram-colours);
  changing them makes committed SVGs outdated, and `check` reports them until the next
  `export` or Save.
- Exits 1 while the layout file is out of date (run `place --auto` or Save in studio
  first), 2 without `export_dir`.

With `export_dir` set, **Save** in studio writes the SVGs too, and studio says so when
they are out of date, so one Save brings them up to date.

Without committing anything: **Download SVG** in studio's toolbar downloads the open
diagram as SVG, drawn the same way, with the positions on screen (saved or not). It
needs no `export_dir`.
