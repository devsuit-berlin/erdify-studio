# Studio canvas: overview with drag and save (#5)

## Intent

A data engineer runs `erdify-studio [path]`, the browser opens the overview diagram,
they drag entities into the arrangement their team reads, press Save and commit
`erdify-layout.json`. erdify's own diagrams are always auto-laid-out; this is the
hand-made layout that survives schema changes.

## Goals

- `erdify-studio [path]` starts a local server (127.0.0.1, free port) and opens the browser.
- The overview shows every entity with the fields erdify shows (name, type, PK / FK / UK,
  nullable), every enum erdify draws, and the edges of `erdify.diagram_edges`.
- Dragging a box moves its edges along and shows an "unsaved changes" indicator.
- Save writes the layout file; the indicator disappears.
- Boxes without a position are placed like `place --auto` and highlighted as new until saved.

## Non-goals

- Group diagrams, foreign boxes and a diagram switcher (#6).
- SVG export (later issue) — but the drawing must be reusable for it (see Approaches).
- Watching files: the page changes only on a reload. (The project is read per API
  request, so a reload after a `git checkout` shows the current models — PR #19
  review: reading it once made a reload drop the positions of new tables on Save.)
- Orthogonal edge routing, minimap, snapping, undo.

## Anti-goals

- Any logic in the browser beyond drawing and dragging: placing, keys, edges and
  validation stay in Python.
- Re-implementing erdify's parsing or edges.
- Any outbound network from the shipped UI (no CDN, no font or icon API).
- Box sizes on the canvas that differ from what `place --auto` assumes.

## Constraints

- Server binds to 127.0.0.1 only. No new runtime Python dependency (the wheel promises
  "no Node, no database, no browser engine").
- Frontend: Vue 3 + Vite, Tailwind CSS 4 + Nuxt UI in plain Vue mode (`@nuxt/ui/vite` +
  `@nuxt/ui/vue-plugin`), decided in the issue comment. Local icon collection
  (`@iconify-json/lucide`), no Iconify API; Nuxt UI's font fetching off. A check that
  the built `src/erdify_studio/_static/` contains no external URLs. New npm packages
  pinned exactly, versions at least 7 days old.
- Python rules of `.github/instructions/python-lib.instructions.md`; coverage gate 90 %.

## Approaches

**Canvas** — picked: hand-drawn SVG in Vue.

| | Hand-drawn SVG (picked) | Vue Flow |
| --- | --- | --- |
| Box sizes | Exactly the sizes Python sends | HTML boxes size themselves; keeping them equal to Python's sizes is a constant fight |
| SVG export | One drawing spec (metrics, styles, primitives) the later Python exporter reproduces 1:1 | HTML/CSS layout a Python exporter can't reproduce |
| Effort | ~300 lines (drag, pan/zoom, edges) | Built in |

Export stays a headless Python command (README: `erdify-studio export`), so it can't
reuse the Vue code. Shared is the *spec*: Python owns box geometry (sizes, metrics) and
sends it; the canvas draws plain SVG primitives (rect, text, line, path) from it, which
the Python exporter writes the same way later. (Builder-check call.)

**Server** — picked: stdlib `http.server` (`ThreadingHTTPServer`). Starlette + uvicorn
would add two runtime dependencies for three routes.

**Edges** — picked: straight lines border to border with crow's-foot ends. Orthogonal
routing is its own algorithm and its own issue.

**Errors** — picked (user): errors stay in the terminal. A parse error, an unreadable
config or layout file, or an empty project (without erdify's `allow_empty`) exit 2 before
the server starts, exactly like `check`. No reload button.

## Design

### CLI

- `erdify-studio [path]` (no subcommand) opens the canvas; `path` as for `check`
  (default `.`). Options: `--port N` (default 0 = a free port), `--no-browser` (print
  the URL only; for SSH and tests).
- Loads like `check`/`place`: `erdify.load_project(path, strict=True)` + `load_config`;
  same error mapping and exit code 2.
- Prints `erdify-studio: serving <url> (Ctrl+C to stop)`, opens the URL with
  `webbrowser.open`, serves until Ctrl+C, then exits 0.
- A directory named like a subcommand (`check`, `place`) is opened as `./check`.

### Server (`_server.py`, internal)

Routes:

| Route | Token | Does |
| --- | --- | --- |
| `GET /`, `GET /assets/*` | no | Files of `_static/`; nothing outside it |
| `GET /api/overview` | yes | The overview model (below) |
| `PUT /api/layout` | yes | Save the overview positions (below) |

Security (local server, but any web page in the same browser can send requests to it):

- A random token per run (`secrets.token_urlsafe`) is part of the opened URL
  (`/?token=…`); the frontend sends it as `X-Studio-Token` on every API call. Wrong or
  missing → 403.
- `Host` must be `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding); an `Origin`
  header, if present, must match it. Otherwise 403.
- Request body limited (e.g. 10 MB), JSON only.

### Overview model (`GET /api/overview`)

Built in Python at startup from the project, the layout file and `place_layout`:

```json
{
  "metrics": {"charWidth": 8, "padding": 32, "header": 32, "row": 22},
  "boxes": [
    {"key": "core.customers", "kind": "entity", "title": "core.customers",
     "x": 120, "y": 40, "width": 264, "height": 98, "new": false,
     "rows": [{"name": "id", "type": "int", "pk": true, "fk": false, "uk": false, "nullable": false}]},
    {"key": "enum:Status", "kind": "enum", "title": "Status", "rows": [{"name": "active"}], "…": "…"}
  ],
  "edges": [
    {"from": "order", "to": "core.customers",
     "fromEnd": {"optional": false, "many": true}, "toEnd": {"optional": true, "many": false},
     "kind": "foreign_key", "label": "customer_id"}
  ],
  "enumLinks": [{"enum": "enum:Status", "entity": "order"}],
  "revision": "<sha256 of the layout file, or null>",
  "pending": {"placed": 3, "groupChanges": 2}
}
```

- `width`/`height` come from the functions in `_place.py` (`_entity_box`, `_box`); the
  metrics are its constants. `_place.py` stays the single source of box geometry; if
  the canvas needs more room (badges, font), change the constants there.
- Positions: the overview of the layout file, plus `place_layout` for boxes without
  one; `new` marks those.
- `pending` says what Save would change before any drag: `placed` = new overview boxes,
  `groupChanges` = entries placed or dropped in group diagrams plus dropped stale
  diagrams and overview entries. Compared by meaning (`Layout` objects), not bytes, so
  a hand-formatted but up-to-date file is not "unsaved". The canvas starts unsaved
  when either is non-zero. (Builder-check call.)
- Edges as `diagram_edges` gives them, mapped to layout keys (`entity_keys` /
  `entity_ids`, like `_place._key_edges`); none with erdify's `no_relationships`.
  Enum links connect an enum to the entities using it (dashed line).
- Edges between the same pair are fanned out by a fixed offset (index within the pair,
  computed in the browser from the edge list); a self-reference is drawn as a loop on
  the box's right side. `label` (the FK column) is shown as a tooltip on the edge, not
  as text. (Builder-check call.)

### Save (`PUT /api/layout`)

- Body: `{"revision": "<from GET>", "positions": {"<key>": [x, y], …}}` for the overview.
- Server: every key must be a box of the overview, every box must be present, values
  go through `Layout.set_position` (rounding, range). Otherwise 400 with the message.
- Writes what `place --auto` would write with these overview positions: the existing
  layout with the overview replaced, then `place_layout` over all diagrams (group
  diagrams get missing boxes placed, stale entries and diagrams dropped), then
  `save_layout`. Afterwards `check` passes.
- If the layout file's current hash differs from `revision` (changed on disk, or saved
  from another tab), 409. No silent overwrite. The user restarts (or reloads the tab
  after a save from another tab) to pick up the change.
- A write error (`LayoutError`, `OSError`) → 500 with the message; the canvas keeps
  its state and stays unsaved.
- Response: `{"saved": "<shown path>", "revision": "<new hash>"}`; the canvas keeps the
  new revision for the next save.

### Canvas (frontend)

```
┌───────────────────────────────────────────────────────────────────────────┐
│ erdify-studio · Overview        ● Unsaved changes          [ Save  ⌘S ]   │
├───────────────────────────────────────────────────────────────────────────┤
│  3 new boxes were placed automatically — save to keep them.               │
│                                                                           │
│   ┌──────────────────────┐            ┌─────────────────────────┐         │
│   │ core.customers       │1        *  │ order               NEW │         │
│   ├──────────────────────┤──────────<─├─────────────────────────┤         │
│   │ PK id        int     │            │ PK id          int      │         │
│   │ UK email     varchar │            │ FK customer_id int?     │         │
│   └──────────────────────┘            └─────────────────────────┘         │
│                                                                    [−][+] │
└───────────────────────────────────────────────────────────────────────────┘
```

- One `<svg>`: background drag pans, wheel / buttons zoom, first view fits all boxes.
- Boxes at exactly `width × height`; title row, one row per field (badges PK / FK / UK,
  name, type, nullable as `?` after the type); monospace text whose advance equals
  `charWidth`, clipped to the box. Enum boxes: name and values.
- Dragging a box moves it (integer canvas units) and its edges live; marks unsaved.
- New boxes: accent border and a "NEW" chip until saved; a banner counts them.
- Save button and Ctrl/⌘+S; while saving the button is busy; on success a toast
  "Saved to <path>", unsaved and NEW marks cleared.
- `beforeunload` warning while unsaved.
- Empty project (erdify's `allow_empty`): canvas shows "No entities found in <path>."

UI texts:

| State | Text |
| --- | --- |
| Unsaved | Unsaved changes |
| New boxes | N new box(es) were placed automatically — save to keep them. |
| Group changes only | The layout file is out of date in N group-diagram entries — save to update it. |
| Saved | Saved to `<path>` |
| Save failed | Could not save: `<message>` (stays until dismissed) |
| File or models changed (409) | The layout file or the models changed since this page loaded (on disk or from another tab). Reload to get them — saving now would overwrite them. |
| No layout file yet (no new boxes counted) | No layout file yet — save to create `<path>`. |
| Empty | No entities found in `<path>`. |

### Checks and tests

- Python: server tests against a real server on port 0 (token, Host/Origin, overview
  model, save paths incl. 400/409/500, static files, no path traversal), CLI tests with
  `--no-browser` and a stubbed `webbrowser.open`. Through public entry points.
- `scripts/check_static.py`: the built `_static/` contains no `http(s)://` URL
  (except an allow-list, e.g. the SVG namespace); run in CI after the frontend build.
- No frontend tests yet (repo has none); `npm --prefix frontend run typecheck`.
- README: the "open the canvas" section; CHANGELOG entry.

## Left to the builder

- Module split of the server and the frontend components.
- The monospace font (bundled via npm, OFL, so metrics are the same everywhere —
  preferred over the system stack) and the exact font size giving `charWidth`.
- Arrow/crow's-foot drawing details, colours, zoom limits.
- Whether `_entity_box` / `_box` get public-within-package names.
