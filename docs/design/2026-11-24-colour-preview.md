# Colour preview in the studio UI (#68)

## Intent

Rebranding a diagram means trying colours. Today that is editing hex values in
`pyproject.toml` and watching the canvas reload. Studio gets a panel to try colours
directly on the canvas, without writing anything; when they fit, **Copy TOML** puts the
matching `[tool.erdify-studio.colors]` table on the clipboard to paste into
`pyproject.toml`.

## Goals

1. A **Colours** button in the toolbar opens a side panel on the right (no dimming; the
   canvas stays usable next to it).
2. The panel has a colour picker (with a hex field) for each of the nine keys, in two
   groups: **Brand** (`accent`, `header`, `header_text`, `background`) and **Details**
   (`text`, `text_muted`, `border`, `border_strong`, `background_muted`).
3. Changing a colour previews it on the canvas right away (light mode), including the
   derived colours (enum header and title, automatic header text, NEW chip text).
4. **Copy TOML** copies the table: the keys set in `pyproject.toml` plus the ones changed
   in the panel. **Reset** drops the panel's changes.
5. Nothing is written to disk.

## Non-goals

- Ready-made themes or presets (user decision).
- Writing `pyproject.toml` from the UI (#48 decision: comment-preserving TOML writer, a
  wider write surface).
- A preview of the export file itself; Download SVG keeps using the saved config.

## Anti-goals

- Colour maths in TypeScript (the server computes derived colours, as in #48).
- A preview that silently diverges from what the config will produce.

## Approaches

| | Approach | Trade-off |
|---|---|---|
| A | Popover from the toolbar | Compact, but closes on every canvas click |
| **B (chosen)** | Side panel on the right, no overlay | Stays open, canvas usable, room for two groups |
| C | Section in the left diagram list | Always visible, but the list is ~220 px and already busy |

The user picked B and no themes (2026-11-24).

## Design

### Server (Python)

- **`POST /api/colors`** (token-protected like the other API routes, `Host`/`Origin`
  checked): body `{"colors": {"<key>": "#rrggbb" | null, ...}}` with the nine keys
  (unknown keys → 400). Returns `{"colors": ColorsJson, "toml": "<table>"}`: the
  resolved palette (`palette_of(DiagramColors(...))`) and the TOML text. Invalid values →
  400 naming the key and value. Nothing is written. *(Claude's call: the server also
  builds the TOML, so its format matches what `load_config` reads and stays in Python.)*
- **TOML text:** `[tool.erdify-studio.colors]` and one `key = "#rrggbb"` line per set key,
  in `DiagramColors` field order; values lowercase. No keys → the header line only.
- **`GET /api/diagrams`** gains `colorConfig`: the keys set in `pyproject.toml` (lowercase
  hex, unset keys omitted), so the panel starts from them. It is part of the payload the
  fingerprint covers (it changes exactly when `colors` does).

### Panel (frontend)

- Toolbar button **Colours** toggles a `USlideover` (side `right`, no overlay, not
  modal). *(Claude's call: Nuxt UI components already in the project — `USlideover`,
  `UColorPicker` in a `UPopover` per key next to a hex `UInput`; no new dependency.)*
- Each row shows the current value: the panel's change, else the configured key, else
  the resolved palette value (greyed: "default"/"automatic"). Clearing a row (×) removes
  the panel's change.
- Edits are sent to `POST /api/colors` debounced (~150 ms); the response's `colors`
  replace the canvas colours while the panel has changes. Without changes the canvas uses
  the payload's `colors` as today.
- **Reset** clears the panel's changes. **Copy TOML** writes the response's `toml` with
  `navigator.clipboard.writeText` (127.0.0.1 is a secure context) and shows a toast.
- When the loaded config's colours change (the page reloads the payload after an edit of
  `pyproject.toml`), the panel's changes are dropped: the real colours take over.
  *(Claude's call.)*
- In dark mode the panel shows a note that the preview is visible in light mode only.
  *(Claude's call.)*
- A 400 from the endpoint (e.g. a half-typed hex) keeps the last good preview and marks
  the row as invalid.

## Tests

- Python: `/api/colors` resolves and returns TOML (defaults, a few keys, derived values),
  rejects unknown keys and invalid values (400), requires the token and the `Host`/
  `Origin` check, writes nothing; `colorConfig` in the payload.
- Frontend: typecheck; no frontend test suite exists. Browser check: pick colours →
  canvas changes incl. enum header; Copy TOML → paste into `pyproject.toml` → after the
  reload the canvas shows the same colours and the panel is clean; dark-mode note.

## Left to the builder

- Component split (e.g. a `ColourPanel.vue`), the debounce mechanics, CSS details.
- Labels and short help texts in the panel.
