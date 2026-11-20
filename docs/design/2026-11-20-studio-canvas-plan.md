# Studio Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `erdify-studio [path]` serves the overview diagram on 127.0.0.1, the browser drags boxes and saves the layout file.

**Architecture:** Python builds an overview model (boxes with sizes from `_place.py`, positions incl. auto-placed ones, erdify edges, a file revision) and saves positions through `place_layout` + `save_layout`. A stdlib `ThreadingHTTPServer` serves the built Vue app and a token-guarded JSON API. The Vue app draws plain SVG from the model, handles drag/pan/zoom and posts positions back.

**Tech Stack:** Python ≥ 3.11 stdlib (`http.server`, `hashlib`, `secrets`, `webbrowser`), erdify ≥ 1.8; Vue 3 + Vite, Tailwind CSS 4 + Nuxt UI (plain Vue mode), `@iconify-json/lucide`, `@fontsource/jetbrains-mono`.

**Spec:** `docs/design/2026-11-20-studio-canvas.md`

## Global Constraints

- Server binds to `127.0.0.1` only; no new runtime Python dependency.
- No outbound network from the shipped UI: no CDN, no Iconify API, no font service; `scripts/check_static.py` enforces it.
- New npm packages pinned to an exact version published at least 7 days before install (`npm view <pkg> time --json`; on 2026-11-20 that means ≤ 2026-11-13).
- Box geometry lives only in `_place.py` (`_MIN_WIDTH`, `_CHAR_WIDTH`, `_PADDING`, `_HEADER`, `_ROW`, `_MARKERS`); the canvas draws exactly the `width × height` Python sends.
- Never re-implement erdify parsing or edges: `erdify.load_project`, `erdify.diagram_edges`, `EntityInfo`, `entity_keys` / `entity_ids`.
- Library code raises (`_errors.py` subclasses of `StudioError`), only `cli.py` prints and maps exit codes; `logging.getLogger(__name__)`, per-request logs at `info`.
- Commands: `uv run --no-sync poe test`, `uv run --no-sync poe lint`, `npm --prefix frontend run build`, `npm --prefix frontend run typecheck`; never bare `pytest`. Coverage ≥ 90 %.
- English everywhere; commits `<type>: #5 - <description>`.
- UI texts exactly as in the spec's "UI texts" table (plus "No layout file yet — save to create `<path>`." for a missing file, Task 1).

## Review Focus

1. Windows maps `.js` to `text/plain` via the registry → the module script is blocked. `/assets/*.js` must be served as `text/javascript` (test in Task 3).
2. Static paths with `..`, `%2e%2e%2f`, absolute or backslash paths must not leave `_static/` → 404 (test in Task 3).
3. Positions from the browser as floats, `NaN`, booleans, strings, huge numbers, missing or extra keys → 400 with the message, never 500 or a written file (tests in Task 2 and 3).
4. A layout file broken after startup (git conflict markers) → `GET /api/overview` answers 500 with the `LayoutError` message, Save never overwrites it (test in Task 3).
5. Empty project under erdify's `allow_empty` → empty `boxes`, Save creates the file with every diagram (test in Task 2).

---

### Task 1: Overview model

**Files:**
- Modify: `src/erdify_studio/_place.py` (extract inputs, expose box helpers)
- Create: `src/erdify_studio/_overview.py`
- Test: `tests/test_overview.py`

**Interfaces:**
- Produces (in `_place.py`): `place_inputs(project: Project) -> tuple[dict[str, tuple[int, int]], frozenset[tuple[str, str]]]` — sizes per key and connected key pairs exactly as `place_project` uses today (`place_project` calls it). `METRICS: Final = {"charWidth": _CHAR_WIDTH, "padding": _PADDING, "header": _HEADER, "row": _ROW}`.
- Produces (in `_overview.py`), TypedDicts mirroring the spec's JSON (camelCase keys): `FieldRow`, `Box` (`key, kind: Literal["entity","enum"], title, x, y, width, height, new, rows`), `EdgeEndJson` (`optional, many`), `EdgeJson` (`from, to, fromEnd, toEnd, kind, label`; use functional TypedDict syntax for `from`), `EnumLink` (`enum, entity`), `Pending` (`placed: int, groupChanges: int, created: bool`), `Overview` (`metrics, boxes, edges, enumLinks, revision: str | None, pending, layoutPath: str, projectPath: str`); `projectPath` = `str(project.settings.input)` for the empty-project text.
- Produces: `layout_revision(path: Path) -> str | None` — sha256 hex of the file bytes, `None` when missing.
- Produces: `build_overview(project: Project, config: StudioConfig, *, shown_path: str) -> Overview`.

- [ ] **Step 1: Write the failing tests** in `tests/test_overview.py`, reusing the project fixture style of `tests/test_place.py` (SQLModel `MODELS` with `core.customers`, `billing.invoices`, `billing.lines`, an enum used by one entity, a nullable FK, a unique column; written to `tmp_path`, loaded with `erdify.load_project(path, strict=True)` + `load_config`). Tests import `erdify_studio._overview` (the HTTP API is the public contract; this module is its builder — tests here pin the JSON shape, not internals).
  - `test_boxes_have_place_sizes`: each entity box's `(width, height)` equals `place_inputs(project)[0][key]`.
  - `test_rows_show_fields`: the invoice box rows include `{"name": "customer_id", "type": <type_str>, "pk": False, "fk": True, "uk": False, "nullable": <is_nullable>}`.
  - `test_enum_box_and_link`: a box `kind == "enum"`, `key == "enum:Status"`, rows = values; `enumLinks` contains `{"enum": "enum:Status", "entity": <user key>}`.
  - `test_edges_use_layout_keys`: one edge `from == "billing.invoices"`, `to == "core.customers"`, `kind == "foreign_key"`, `label == "customer_id"`, ends from erdify's `EdgeEnd`.
  - `test_no_edges_without_relationships`: erdify `no_relationships = true` in `[tool.erdify]` → `edges == []`.
  - `test_unplaced_boxes_are_new`: layout file with only `core.customers` placed → that box `new is False` at its stored position; others `new is True` at the positions `place_project` would give (compare with a `place_project` run on a copy); `pending["placed"] == 2`.
  - `test_up_to_date_layout_has_nothing_pending`: after `place_project`, `pending == {"placed": 0, "groupChanges": 0, "created": False}`.
  - `test_group_changes_counted`: layout with a full overview but a stale group entry → `pending["groupChanges"] == 1`, `placed == 0`.
  - `test_hand_formatted_file_is_not_pending`: same layout re-written with different whitespace → nothing pending (compare by meaning).
  - `test_no_file_is_created_pending`: no layout file → `pending["created"] is True`, `revision is None`.
  - `test_revision_is_file_hash`: `revision == hashlib.sha256(path.read_bytes()).hexdigest()`.
  - `test_empty_project_with_allow_empty`: no entities, `allow_empty = true` → `boxes == []`, `edges == []`.

- [ ] **Step 2: Run** `uv run --no-sync poe test tests/test_overview.py` — Expected: FAIL (`ModuleNotFoundError: erdify_studio._overview`).

- [ ] **Step 3: Implement** `place_inputs` / `METRICS` in `_place.py` (move the sizes/edges lines out of `place_project`), then `_overview.py`: `diagrams = project_diagrams(...)`, `existing = load_existing_layout(config.layout)`, `result = place_layout(existing or Layout(), diagrams, sizes=..., edges=..., created=existing is None)`; positions from `result.layout.diagrams[OVERVIEW]`; `new` = keys in `result.placed` with diagram `OVERVIEW`; `pending.placed` = that count, `groupChanges` = `len(non-overview placed) + len(result.removed) + len(result.removed_diagrams)`, `created` = `result.created`. Rows: entity title = layout key, `FieldInfo` → `name, type_str, is_primary_key, is_foreign_key, is_unique, is_nullable`; enum title = `enum.name`, rows `{"name": str(value)}`. Edges: `diagram_edges(project.entities)` mapped with `entity_keys`/`entity_ids` (skip when `no_relationships`); enum links from `drawn_enums`. Boxes sorted by key.

- [ ] **Step 4: Run** `uv run --no-sync poe test` — Expected: all pass (existing place tests unchanged).

- [ ] **Step 5: Commit** — `feature: #5 - overview model for the canvas`

### Task 2: Save positions

**Files:**
- Modify: `src/erdify_studio/_errors.py`, `src/erdify_studio/_overview.py`
- Test: `tests/test_overview.py`

**Interfaces:**
- Consumes: Task 1 (`build_overview`, `layout_revision`, `place_inputs`).
- Produces (in `_errors.py`, not re-exported): `PositionsError(StudioError)` — invalid save request; `LayoutConflictError(LayoutError)` — file changed since `revision`.
- Produces: `save_overview(project: Project, config: StudioConfig, positions: object, revision: str | None) -> str | None` — writes the file, returns the new revision.

- [ ] **Step 1: Write the failing tests**
  - `test_save_writes_overview_and_passes_check`: save every overview key at given integer positions → `load_layout` shows them on `OVERVIEW`, `check_project(project, config) == []`, returned revision equals `layout_revision(path)`.
  - `test_save_places_group_diagrams`: no file before → file contains every group diagram, all placed.
  - `test_save_rounds_floats`: `[10.6, 20.4]` → `(11, 20)`.
  - `test_save_refuses_bad_positions` (parametrize): missing key, unknown key, `[1]`, `[1, 2, 3]`, `["1", 2]`, `[True, 2]`, `[float("nan"), 0]`, `[10**10, 0]`, `positions` not a dict → `PositionsError`, message names the key with `!r`; file unchanged (bytes equal before/after).
  - `test_save_conflict_when_file_changed`: revision from before an external write → `LayoutConflictError`; file unchanged.
  - `test_save_conflict_when_created_meanwhile`: `revision=None` but file now exists → `LayoutConflictError`.
  - `test_second_save_uses_new_revision`: save, then save again with the returned revision → succeeds; with the old revision → `LayoutConflictError`.
  - `test_save_empty_project_creates_file` (Review Focus 5).

- [ ] **Step 2: Run** `uv run --no-sync poe test tests/test_overview.py` — Expected: FAIL (`save_overview` missing).

- [ ] **Step 3: Implement** `save_overview`: compare `layout_revision(config.layout)` with `revision` first (`LayoutConflictError`, message names the path); validate `positions` is a `dict` whose key set equals the overview's `shown` keys and each value is a 2-item list of `int`/`float`, not `bool`; build `Layout` = existing diagrams with `OVERVIEW` replaced via `set_position` (convert its `LayoutError` to `PositionsError`); `place_layout(...)` over all diagrams; `save_layout`; return `layout_revision`.

- [ ] **Step 4: Run** `uv run --no-sync poe test` — Expected: PASS.

- [ ] **Step 5: Commit** — `feature: #5 - save overview positions with revision check`

### Task 3: HTTP server

**Files:**
- Create: `src/erdify_studio/_server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `build_overview`, `save_overview`, `PositionsError`, `LayoutConflictError`.
- Produces: `STATIC_DIR: Path` (package `_static/`); `class StudioServer(ThreadingHTTPServer)` with `.url: str` (`http://127.0.0.1:<port>/?token=<token>`), `.token: str`; `start_server(project: Project, config: StudioConfig, *, port: int = 0, static_dir: Path = STATIC_DIR, shown_path: str) -> StudioServer` (bound, not yet serving).

- [ ] **Step 1: Write the failing tests** — fixture starts `start_server` with a `tmp_path` static dir (`index.html`, `assets/app.js`, `assets/app.css`) and runs `serve_forever` in a daemon thread, `shutdown()` on teardown; requests via `http.client` to `127.0.0.1:<port>`.
  - `test_binds_localhost_only`: `server.server_address[0] == "127.0.0.1"`.
  - `test_serves_index_and_assets`: `/` → 200 index body; `/assets/app.js` → `Content-Type: text/javascript; charset=utf-8` (Review Focus 1); `.css` → `text/css`.
  - `test_static_traversal_is_404` (parametrize): `/../pyproject.toml`, `/assets/..%2f..%2fx`, `/%2e%2e/x`, `/assets\\..\\x`, `//etc/passwd` → 404 (Review Focus 2).
  - `test_api_requires_token` (parametrize GET overview / PUT layout): no header, wrong header → 403.
  - `test_rejects_foreign_host`: `Host: evil.example:<port>` → 403; `Host: localhost:<port>` with token → 200.
  - `test_rejects_foreign_origin`: `Origin: https://evil.example` → 403; `Origin: http://127.0.0.1:<port>` → 200.
  - `test_get_overview`: 200, JSON equals `build_overview(...)`, `Cache-Control: no-store`.
  - `test_put_layout_saves`: 200 `{"saved": <shown_path>, "revision": <hash>}`.
  - `test_put_layout_bad_positions_is_400` (body `{"revision": r, "positions": {"x": [true, 1]}}`) and `test_put_non_json_is_400`, `test_put_too_large_is_413` (Content-Length > 10 MB, body not sent), `test_put_wrong_content_type_is_415`.
  - `test_put_conflict_is_409`.
  - `test_broken_layout_after_start_is_500`: write `<<<<<<<` into the layout file → GET 500 `{"error": <LayoutError message>}`; PUT 500 and the file still contains the markers (Review Focus 4).
  - `test_unknown_api_route_is_404`, `test_method_not_allowed_is_405` (POST `/api/layout`).

- [ ] **Step 2: Run** `uv run --no-sync poe test tests/test_server.py` — Expected: FAIL (module missing).

- [ ] **Step 3: Implement** `_server.py`: `BaseHTTPRequestHandler` subclass; Host/Origin check on every request; static: `unquote` the path, reject any `..` segment, backslash or absolute part, resolve and require `is_relative_to(static_dir.resolve())`, explicit type map (`.html`, `.js` → `text/javascript; charset=utf-8`, `.css`, `.svg`, `.woff2`, `.json`) instead of `mimetypes`; API: `X-Studio-Token` compared with `secrets.compare_digest`; JSON responses with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`; errors as `{"error": message}`. A `threading.Lock` around save. Map: `PositionsError` 400, `LayoutConflictError` 409, other `StudioError`/`OSError` 500. `log_message` → `logger.info`.

- [ ] **Step 4: Run** `uv run --no-sync poe test` — Expected: PASS.

- [ ] **Step 5: Commit** — `feature: #5 - local studio server with token-guarded API`

### Task 4: `erdify-studio [path]` command

**Files:**
- Modify: `src/erdify_studio/cli.py`, `tests/test_cli.py` (`test_no_arguments_exits_zero` changes meaning)
- Test: `tests/test_open.py`

**Interfaces:**
- Consumes: `start_server`, `StudioServer.url`.
- Produces: subcommand `open` (`path`, `--port` int default 0, `--no-browser`); `main(argv)` prepends `"open"` unless `argv[0]` is `check`, `place`, `open`, `-h`, `--help` or `--version`.

- [ ] **Step 1: Write the failing tests** — monkeypatch `StudioServer.serve_forever` to raise `KeyboardInterrupt` and `webbrowser.open` to record calls.
  - `test_opens_browser_with_token_url`: `main([str(project_dir)]) == 0`, one `webbrowser.open` call whose URL starts with `http://127.0.0.1:` and contains `token=`; stdout has `erdify-studio: serving <url> (Ctrl+C to stop)`.
  - `test_no_browser_prints_url_only`.
  - `test_defaults_to_current_directory`: `monkeypatch.chdir(project_dir)`, `main([]) == 0` (replaces `test_no_arguments_exits_zero`).
  - `test_directory_named_check`: a project dir named `check`, `main(["./check"])` opens it.
  - `test_parse_error_exits_2_before_serving`: broken model file → 2, `erdify-studio: error:` on stderr, `start_server` never called.
  - `test_empty_project_exits_2`: no entities, no `allow_empty` → 2.
  - `test_port_in_use_exits_2`: occupy a port, `--port <it>` → 2.
  - `test_help_lists_open`: `--help` mentions `open`.

- [ ] **Step 2: Run** `uv run --no-sync poe test tests/test_open.py tests/test_cli.py` — Expected: FAIL.

- [ ] **Step 3: Implement** the `open` subparser (help: "open the canvas in the browser (the default command)") and `_open(path, port, browser)`: `_load(path)`, `start_server(..., shown_path=_display(config.layout))`, print the serving line, `webbrowser.open(server.url)` unless `--no-browser`, `serve_forever()` until `KeyboardInterrupt`, then `server_close()`, return 0.

- [ ] **Step 4: Run** `uv run --no-sync poe test` and `uv run --no-sync poe lint` — Expected: PASS.

- [ ] **Step 5: Commit** — `feature: #5 - open the canvas as the default command`

### Task 5: Frontend foundation and offline check

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.ts`, `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/index.html`, `pyproject.toml` (poe task), `.github/workflows/package.yml`
- Create: `frontend/src/style.css`, `frontend/src/icons.ts`, `scripts/check_static.py`
- Test: `tests/test_check_static.py`

**Interfaces:**
- Produces: `scripts/check_static.py [DIR]` (default `src/erdify_studio/_static`): `problems(directory: Path) -> list[str]`, exit 1 with one line per external URL found in any built file; allow-list only non-fetched strings (`http://www.w3.org/2000/svg`, `http://www.w3.org/1999/xlink`, `http://www.w3.org/XML/1998/namespace`), each with a comment. poe task `check-static`.
- Produces: Vite dev proxy `/api` → `process.env.STUDIO_API ?? "http://127.0.0.1:8765"` (use with `erdify-studio --port 8765 --no-browser`).

- [ ] **Step 1: Write the failing tests** in `tests/test_check_static.py` (pattern of `tests/test_check_wheel.py`): `test_clean_dir_has_no_problems`; `test_reports_external_url` (parametrize `https://api.iconify.design/x.json`, `https://fonts.googleapis.com/css`, `//cdn.example/x.js`) with file name in the message; `test_allows_svg_namespace`; `test_missing_dir_is_a_problem`.

- [ ] **Step 2: Run** `uv run --no-sync poe test tests/test_check_static.py` — Expected: FAIL. **Step 3: Implement** the script. **Step 4: Run** — Expected: PASS.

- [ ] **Step 5: Install pinned packages** (exact versions ≤ 2026-11-13, see Global Constraints): `@nuxt/ui`, `tailwindcss`, `@iconify-json/lucide`, `@iconify/vue` if Nuxt UI does not already depend on it, `@fontsource/jetbrains-mono`. Wire `ui()` from `@nuxt/ui/vite` (font fetching disabled), `app.use(ui)` from `@nuxt/ui/vue-plugin`, `style.css` with `@import "tailwindcss"; @import "@nuxt/ui";` and the font import; `App.vue` wrapped in `<UApp>` with a placeholder toolbar.

- [ ] **Step 6: Make icons offline** in `icons.ts`: register only the lucide icons the app uses (`save`, `plus`, `minus`, `maximize`, `circle-alert`, `check`, plus any Nuxt UI component defaults that render, e.g. toast close `x`) with `addCollection` from `@iconify/vue` using `getIcons` from `@iconify/utils` on `@iconify-json/lucide`, so nothing is fetched at runtime.

- [ ] **Step 7: Verify** `npm --prefix frontend run build` succeeds, `uv run --no-sync poe check-static` prints nothing and exits 0. Add the `check-static` step after "Build the frontend" in `.github/workflows/package.yml`.

- [ ] **Step 8: Commit** — `feature: #5 - Tailwind and Nuxt UI setup, offline check of the build`

### Task 6: Draw the overview

**Files:**
- Create: `frontend/src/api.ts`, `frontend/src/geometry.ts`, `frontend/src/drawing.ts`, `frontend/src/components/DiagramCanvas.vue`, `frontend/src/components/BoxNode.vue`, `frontend/src/components/EdgeLine.vue`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: the `/api/overview` JSON of Task 1 (mirror the TypedDicts as TS types in `api.ts`).
- Produces (`api.ts`): `fetchOverview(): Promise<Overview>`; `saveLayout(revision: string | null, positions: Record<string, [number, number]>): Promise<SaveOutcome>` with `type SaveOutcome = {ok: true; saved: string; revision: string} | {ok: false; conflict: boolean; message: string}`; token read once from `location.search` and sent as `X-Studio-Token`.
- Produces (`geometry.ts`, pure): `type Rect = {x: number; y: number; width: number; height: number}`; `borderPoint(rect: Rect, toward: {x: number; y: number}): {x: number; y: number}`; `fanOffsets(edges: {from: string; to: string}[]): number[]` (per edge, `(i - (n - 1) / 2) * 16` for the i-th of n edges between the same unordered pair); `selfLoopPath(rect: Rect, index: number): string`; `endMarkerPath(point, angle: number, end: {optional: boolean; many: boolean}): string` (crow's foot when `many`, bar when not; circle when `optional`, second bar when not).
- Produces (`drawing.ts`): `FONT_ADVANCE = 0.6` (JetBrains Mono advance per em) so `fontSize = metrics.charWidth / FONT_ADVANCE`; colours as CSS variables usable in SVG.

- [ ] **Step 1: Implement** `App.vue` loading the overview (error from fetch → full-page message), `DiagramCanvas.vue` (one `<svg>`; background drag pans, wheel and `[−][+]` buttons zoom (clamp 0.1–4), first view fits all boxes with 40 px margin; empty `boxes` → "No entities found in `<path>`."), `BoxNode.vue` (rect `width × height`, title row `header` high, rows `row` high, badges `PK`/`FK`/`UK` in the `_MARKERS` room, nullable as `?` after the type, text clipped by a `clipPath` of the box), `EdgeLine.vue` (straight line between `borderPoint`s shifted by `fanOffsets`, self-loops via `selfLoopPath`, end markers, `<title>` = `label`; enum links dashed, no markers).

- [ ] **Step 2: Verify** `npm --prefix frontend run typecheck` and `build` pass; `uv run --no-sync poe check-static` passes.

- [ ] **Step 3: Verify in the browser**: build a sample project in the scratchpad (the Task 1 models plus a self-reference `parent_id` and two FKs from one table to another), run `uv run --no-sync erdify-studio <dir>` and open it with the chrome-devtools MCP: every box drawn, no text past a box border, parallel edges apart, self-loop visible, network panel shows no request outside `127.0.0.1`. Screenshot for the PR.

- [ ] **Step 4: Commit** — `feature: #5 - draw the overview diagram`

### Task 7: Drag, save and states

**Files:**
- Modify: `frontend/src/App.vue`, `frontend/src/components/DiagramCanvas.vue`, `frontend/src/components/BoxNode.vue`
- Create: `frontend/src/components/StudioToolbar.vue`

**Interfaces:**
- Consumes: `saveLayout`, `SaveOutcome`, `Overview.pending`, `Overview.revision`.

- [ ] **Step 1: Implement** drag in `DiagramCanvas.vue` with pointer events + pointer capture, delta divided by the zoom scale, positions rounded to integers; edges recompute from reactive positions. State in `App.vue`: `positions`, `revision`, `newKeys` (from `box.new`), `dirty` (initially `pending.placed + pending.groupChanges > 0 || pending.created`). `StudioToolbar.vue`: "erdify-studio · Overview", "Unsaved changes" badge when dirty, Save button (busy while saving) and Ctrl/⌘+S. Banners and toasts with the spec's UI texts (new boxes / group changes only / no layout file yet / saved / save failed (sticky) / 409). New boxes: accent border and "NEW" chip. `beforeunload` → `preventDefault()` while dirty. On success: store the new revision, clear `dirty` and `newKeys`.

- [ ] **Step 2: Verify** typecheck, build, `check-static`.

- [ ] **Step 3: Verify in the browser** (chrome-devtools MCP, sample project with one unplaced table): NEW chip + banner shown; drag at zoom 2 keeps the box under the pointer; unsaved badge appears; ⌘S saves, badge and NEW clear, `uv run --no-sync erdify-studio check <dir>` exits 0; edit the layout file externally then Save → 409 text; make the file read-only then Save → "Could not save: …" and still unsaved; reload with unsaved changes → leave-page prompt.

- [ ] **Step 4: Commit** — `feature: #5 - drag, save and unsaved state on the canvas`

### Task 8: Docs

**Files:**
- Modify: `README.md` (replace "Planned commands" entry for the canvas with an "Open the canvas" section: command, `--port`, `--no-browser`, token URL, errors exit 2 like `check`, Save = what `place --auto` writes with your overview positions, 409 behaviour), `CHANGELOG.md` (Unreleased: added).

- [ ] **Step 1: Write the docs.** **Step 2: Run** `uv run --no-sync poe lint`, `uv run --no-sync poe test`, `pre-commit run --files <changed>`. **Step 3: Commit** — `docs: #5 - document the canvas`
