# Live Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Studio follows model edits within about a second, without losing unsaved positions, and keeps the last good diagram while a file can't be loaded.

**Architecture:** A watcher thread in `StudioServer` re-parses the project on an adaptive interval and keeps a snapshot (last good project + config, model fingerprint, current load error); every API request reads the snapshot. The page polls `GET /api/status`; on a new fingerprint it posts its on-screen positions to `POST /api/diagrams` and gets the merged diagrams back, placed by `place_layout`, with `pending` computed against the layout file.

**Tech Stack:** Python ≥ 3.11 stdlib (`threading`, `hashlib`, `json`, `time`); Vue 3.

**Spec:** `docs/design/2026-11-23-live-reload.md`

## Global Constraints

- erdify only via `load_project`; stdlib only; no push connections.
- Interval: `max(1.0, 2 * last_parse_seconds)`.
- Every load error keeps the last good snapshot (incl. unexpected exceptions, logged with traceback).
- Fingerprint never reads the layout file.
- 409 bodies: `{"error": …, "reason": "models" | "layout"}`.
- Texts: error banner ``${error} — showing the last good state.``; layout banner `The layout file changed on disk. Reload to get it — saving now would overwrite it.`; toast ``Models changed: ${n} new, ${m} removed`` (omit a zero part; no toast when both are 0); save retry toast `The models changed while saving — updated, save again.`; server gone banner `erdify-studio is not running any more.`
- Commands: `uv run --no-sync poe test` / `lint`, `npm --prefix frontend run typecheck`, `uv run poe frontend`, `uv run --no-sync poe check-static`; commits `feat: #7 - …`.

## Review Focus

1. A table that disappears for one tick and comes back (file emptied while editing) → its committed position, not a new one (test in Task 3).
2. A drag in progress while a reload arrives → the dragged box isn't snapped back (Task 5: no reload while dragging; manual check).
3. The open diagram disappears after a `group_by` change → the page switches to the overview (Task 5, manual).
4. A model change between page load and Save → 409 `reason: "models"`, the page reloads models and keeps drags (tests in Task 4, manual in Task 5).
5. The watcher thread stops with the server (no thread left after `server_close`; test in Task 2).

---

### Task 1: Model fingerprint

**Files:** `src/erdify_studio/_diagrams.py`, `tests/test_diagrams.py`.
**Interfaces:** `model_fingerprint(project: Project, config: StudioConfig) -> str` (sha256 hex of `json.dumps(…, sort_keys=True, separators=(",", ":"))` over `metrics`, `boxes`, per diagram `name/label/own/foreign/foreignSizes/edges/enumLinks`, and `export_dir` as given in config); built from `project_diagrams` + box/edge helpers without `load_existing_layout`.

- [ ] Tests: unchanged by a comment-only edit; changed by a new column, a new table, a renamed table, a `group_by` change; unaffected by a broken layout file (write `<<<<<<<` into it → same fingerprint, no exception). Run → FAIL.
- [ ] Implement (refactor `build_diagrams` so both share the box/edge/link building). Run → PASS; lint; commit `feat: #7 - a fingerprint of what the canvas draws`.

### Task 2: Watcher and snapshot

**Files:** `src/erdify_studio/_server.py`, `src/erdify_studio/cli.py`, `tests/test_server.py`.
**Interfaces:** `StudioServer(load, *, port, static_dir, shown_path, min_interval: float = 1.0)`; `server.snapshot() -> Snapshot` (frozen dataclass: `project`, `config`, `fingerprint: str`, `error: str | None`); `server.refresh() -> None` (one load now; used by the thread and by tests); the thread starts in `serve_forever` (override) and stops in `shutdown`/`server_close` via a `threading.Event`. The constructor loads once and raises like today when that first load fails. All handlers use `snapshot()` instead of `self.server.load()`. `GET /api/status` → `{"model", "revision", "error"}`.

- [ ] Tests: `refresh` picks up a new table (fingerprint changes); a syntax error keeps the old project and sets `error`; fixing it clears `error`; `ProjectError` (all models deleted) and an unexpected exception (monkeypatched loader raising `RuntimeError`) keep the snapshot; the interval is `max(min_interval, 2 * parse)` (inject a fake clock or measure via a loader that sleeps); `GET /api/status` shape and token; status doesn't call the loader (count); no `erdify-studio-watch` thread alive after `server_close` (Review Focus 5); Save during an `error` writes with the last good project. Run → FAIL.
- [ ] Implement; name the thread `erdify-studio-watch`. Run → PASS; lint; commit `feat: #7 - re-parse in the background and serve a snapshot`.

### Task 3: Merge positions into the current model

**Files:** `src/erdify_studio/_export.py` (next to `build_studio`), `src/erdify_studio/_server.py`, `tests/test_export.py`, `tests/test_server.py`.
**Interfaces:** `merge_studio(project, config, positions: object, *, shown_path: str) -> Diagrams`: start from the layout file's positions overridden by the sent ones (validated with `checked_positions` per diagram, unknown keys / diagrams ignored), `place_layout` over `project_diagrams`, payload like `build_studio` with `new` = placed keys and `pending` against the file. Route `POST /api/diagrams` (body `{"diagrams": {...}}`; 400 on bad positions).

- [ ] Tests: keeps sent positions; a new table is placed next to the sent positions (differs from where the file's layout would put it); a key absent from the page but in the file gets the file's position (Review Focus 1); removed keys and diagrams are dropped and counted in `pending.dropped`; `pending.placed` counts keys the file lacks; with `export_dir` and an unchanged layout, `pending.svgs` counts a taller box after a new column; 400 on bad positions; route token + 200. Run → FAIL.
- [ ] Implement. Run → PASS; lint; commit `feat: #7 - merge on-screen positions into the current model`.

### Task 4: Why a save conflicts

**Files:** `src/erdify_studio/_errors.py` (`LayoutConflictError.reason: Literal["models", "layout"]`, default `"layout"`), `_diagrams.py` / `_export.py` raise sites, `_server.py` (409 body), `tests/test_server.py`.

- [ ] Tests: 409 for a changed layout file → `reason: "layout"`; 409 for other boxes / diagrams (save and `POST /api/svg`) → `reason: "models"`. Run → FAIL.
- [ ] Implement. Run → PASS; lint; commit `feat: #7 - 409 says whether the models or the layout file changed`.

### Task 5: Page

**Files:** `frontend/src/api.ts`, `frontend/src/App.vue`, maybe `frontend/src/components/DiagramCanvas.vue` (expose whether a drag is in progress).

- [ ] `api.ts`: `fetchStatus()`, `mergeDiagrams(positions)`, `saveLayout` / `downloadSvg` outcomes carry `reason`.
- [ ] `App.vue`: poll every 1 s while `document.visibilityState === "visible"`, one request in flight; skip while dragging or saving; on a new fingerprint `mergeDiagrams(positions)` → replace payload, positions, NEW (union with earlier NEW still present), keep moved dots, keep views, overview if the open diagram is gone; recompute `pendingShown` from the new `pending`; toast with counts. Error banner from `status.error`; layout banner when `status.revision` differs from the page's revision; server-gone banner after 3 failed polls. On save `reason: "models"` → merge now and toast the retry text.
- [ ] `npm --prefix frontend run typecheck`, `uv run poe frontend`, `poe check-static`; manual check in the browser by the user (add / remove a table, add a column, syntax error and fix, drag before each; save right after an edit). Commit `feat: #7 - the canvas follows model edits`.

### Task 6: Docs

- [ ] README (Arrange the diagram: live reload, error banner, layout-file banner), CHANGELOG (Added). `pre-commit`, full `poe test --cov-fail-under=90`. Commit `docs: #7 - live reload`.
