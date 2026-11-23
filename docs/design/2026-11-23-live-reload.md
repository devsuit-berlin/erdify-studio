# Live reload on source changes (#7)

## Intent

While studio is open, editing the models should show up on the canvas within about a
second, so a new table can be placed right away. Nothing the user arranged and hasn't
saved may get lost in the process, and a half-typed model file must not wipe the
canvas.

## Goals (issue #7 acceptance criteria)

1. **Reload**: a source change re-parses the project and updates the canvas without
   losing unsaved positions.
2. **New**: a new table is auto-placed and marked NEW.
3. **Removed**: a table that disappears loses its box; its entries leave the layout
   file on the next Save.
4. **Columns**: when columns change, the box keeps its position (and gets its new size).
5. **Parse error** (user decision, 2026-11-23): keep the last good diagram, show an
   error banner ("`<file>` can't be parsed: … — showing the last good state"). Positions
   stay editable and savable; reloading resumes when the file parses again.

## Non-goals

- Merging a layout file that changed on disk (another tab, a `git checkout`) into
  unsaved positions. That stays a conflict, as today: a banner asks to reload.
- Watching files directly, or a new erdify API for the scanned files (approach 3,
  maybe later as an optimisation).
- Push connections (server-sent events, WebSockets).

## Anti-goals

- Losing an unsaved drag because the models changed.
- A blank canvas while a file is being edited.
- Parsing per HTTP request on top of the watcher (the server would parse twice).

## Constraints

- erdify only through its public API (`load_project`); no re-implemented file
  selection.
- stdlib only (a `threading.Thread`); 127.0.0.1, token, `Host` / `Origin` checks
  unchanged.
- Placement stays in Python (`place_layout`); the browser computes nothing.

## Approaches

| | Approach | Trade-off |
|---|---|---|
| **1 (chosen)** | Re-parse about every second in a background thread; compare a fingerprint of what the canvas shows; the page polls a tiny status route | Only erdify's public API; catches models, SQL, `pyproject.toml`, `git checkout`. Costs one parse per interval, so the interval adapts: at least 1 s, at least twice the last parse time. |
| 2 | Watch file modification times | Re-implements erdify's file selection (forbidden) or scans the whole tree. |
| 3 | New erdify API for the scanned files, then watch them | Needs an erdify release first. |

The user picked 1 (2026-11-23). Polling instead of a push connection: a long-lived
connection holds a thread per tab on the stdlib server and complicates the token
check, with no visible gain on localhost.

## Design

### Watcher (server)

- `StudioServer` starts a daemon thread (`_watch`) that loops: load the project
  (`erdify.load_project(path, strict=True)` + `load_config`), then sleep
  `max(1.0, 2 * parse_seconds)`; stopped with the server (`shutdown` /
  `server_close`).
- It keeps one **snapshot** behind a lock: the last good `(project, config)`, its
  **model fingerprint**, and the current **error** (`None`, or the message of what
  the last load raised). **Every load error keeps the last good snapshot**
  (builder-check call): `erdify.ModelParseError`, `erdify.ConfigError`,
  `erdify.SqlDependencyError`, `ProjectError` (no entities left), `DuplicateKeyError`,
  a reserved group name, `OSError`. An unexpected exception is logged with its
  traceback and treated the same way, so the watcher never dies.
- **Model fingerprint**: sha256 of the canonical JSON of what the canvas draws
  except positions: `metrics`, `boxes` and per diagram `name`, `label`, `own`,
  `foreign`, `foreignSizes`, `edges`, `enumLinks`, plus `exportPath`. Computed
  **without reading the layout file** (a helper next to `build_diagrams` that skips
  positions), so a layout-file problem never looks like a model change. A whitespace or
  comment edit doesn't change it; a new column does (box size and rows).
- On a failed load the last good snapshot stays; only `error` is set. The next good
  load clears it.
- **Every API request uses the snapshot** (no parse per request). The first load
  happens before the server starts serving (as `cli._open` does today), so there is
  always a snapshot. Requests between a file change and the next tick see the old
  snapshot, which the existing conflict checks (409 on other boxes) already handle.

### Routes

- `GET /api/status` → `{"model": "<fingerprint>", "revision": "<layout revision or
  null>", "error": "<message>" | null}`. Cheap: no parse, one file hash (the layout
  file's, as `layout_revision`).
- `POST /api/diagrams` → body `{"diagrams": {name: {key: [x, y]}}}` (the positions on
  screen, unsaved ones included). Returns the `GET /api/diagrams` payload built from
  the snapshot with this starting layout (builder-check call): the **layout file's
  positions, overridden by the sent ones**. So a key the page doesn't have but the file
  does (a table that briefly disappeared while its file was edited, a new group diagram
  after a checkout) gets its committed position back; only keys in neither are placed
  by `place_layout` next to them (listed in `new`). Keys and diagrams that no longer
  exist are dropped. Validation as for Save (400 on bad positions), except that other
  keys or diagrams than the model has are expected here and not a conflict.
  `revision` is the layout file's, unchanged.
- **`pending` of that response is computed against the layout file** (builder-check
  call), as Save would change it: `placed` = keys in the result that the file lacks,
  `diagrams` = diagrams with such keys, `dropped` = file entries and diagrams the result
  no longer has, `created` = no file yet, `svgs` = as `build_studio` (only when the
  result equals the file's positions). A removed table therefore shows up as `dropped`
  and enables Save (goal 3); a column change enables Save through `svgs` when
  `export_dir` is set.
- **409 says why** (builder-check call): `{"error": …, "reason": "models" | "layout"}`
  for `PUT /api/layout` and `POST /api/svg`. `models` = other boxes or diagrams than
  the snapshot has; `layout` = the layout file's revision changed.
- `GET /api/diagrams`, `PUT /api/layout`, `POST /api/svg` keep their contracts, read
  the snapshot.

### Page

- Polls `GET /api/status` every second while the tab is visible
  (`document.visibilityState`), at most one request in flight.
- **Model changed** (fingerprint differs from the one the page has): `POST
  /api/diagrams` with all current positions, then replace the payload and recompute
  the banner, `dirty` and Save from its `pending` (not only on the first load). Per diagram:
  positions from the response; NEW = the response's `new` plus earlier NEW keys still
  present; the unsaved dot stays on diagrams moved before. The view (pan/zoom) and the
  open diagram stay; if the open diagram disappeared, switch to the overview. A toast
  summarises: "Models changed: 2 new, 1 removed" (counts over the overview's boxes;
  nothing when only sizes changed).
- **Load error**: an error banner, above the other banner: "`<message>` — showing the
  last good state." Cleared when `error` is null again.
- **Save hits `reason: "models"`** (the files changed in the second before the next
  poll): the page reloads the models at once (as above, drags kept) and shows "The
  models changed while saving — updated, save again." `reason: "layout"` keeps today's
  message (reload the page).
- **Layout file changed on disk** (`revision` differs and this page didn't save it):
  a banner "The layout file changed on disk. Reload to get it — saving now would
  overwrite it." Save stays possible (the server's 409 rule decides, as today).
- Errors of the status poll itself (server stopped): after three failures one banner
  "erdify-studio is not running any more."

### Tests

- Watcher: picks up a model change within two ticks (test with a short injected
  interval); keeps the last good snapshot and sets `error` on a parse error; clears it
  after a fix; interval at least twice the parse time (injected clock).
- Fingerprint: unchanged for a comment-only edit; changed by a new column, a new
  table, a renamed table, a `group_by` change.
- `GET /api/status`: shape, token required; no parse per request (counted).
- `POST /api/diagrams`: keeps sent positions, places a new table next to them (not
  where the saved layout would put it), drops removed keys and diagrams, 400 on bad
  positions, token required.
- Save during a parse error writes with the last good snapshot.
- `POST /api/diagrams`: a key the page lacks but the file has gets the file's
  position; `pending` against the file (a removed table → `dropped`).
- 409 bodies carry `reason` (`models` / `layout`).
- Every listed load error keeps the snapshot and sets `error`; an unexpected one too
  (watcher survives).
- Frontend: typecheck, build, `check-static`; manual check in the browser (add a
  table, remove one, add a column, type a syntax error and fix it, drag before each).

## Left to the builder

- Thread lifecycle details (event to stop, join on `server_close`).
- Where the fingerprint helper lives (`_diagrams.py` or the server).
- Toast and banner styling within the existing components.
