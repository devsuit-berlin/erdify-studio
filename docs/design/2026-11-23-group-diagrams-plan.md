# Group Diagrams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The studio canvas shows the overview and every group diagram, with greyed-out name-only foreign boxes that open their entity's group, and one Save writes every diagram.

**Architecture:** Python builds one payload with every diagram (box definitions once, per diagram the shown keys, positions incl. auto-placed ones, foreign sizes, the edges and enum links that diagram draws) from one read of the models, and saves the positions of every diagram in one write. The edge / enum-link rule is a method of `DiagramContent`, so the SVG export (#8) reuses it. The Vue app keeps positions, NEW marks and the view per diagram, switches with a diagram list, and posts every diagram back.

**Tech Stack:** Python ≥ 3.11 stdlib, erdify ≥ 1.9; Vue 3 + Vite, Tailwind CSS 4 + Nuxt UI (plain Vue mode). No new dependencies.

**Spec:** `docs/design/2026-11-23-group-diagrams.md`

## Global Constraints

- All diagram logic in Python; the browser draws what it is sent and computes no sizes, contents, edges or links.
- erdify only through its public API (`diagram_edges`, `enum_users`, `EntityInfo`) and studio's `entity_keys` / `entity_ids`.
- Box geometry only in `_place.py`; a foreign box's size is the header-only size `place_layout` reserves for it.
- Diagram names on the wire are the layout file's names: `OVERVIEW` (`"_overview"`), group names, `DEFAULT_GROUP` (`"_default"`). Never a bare `"overview"`.
- Labels: `"Overview"` for `_overview`, `"Ungrouped"` for `_default`, otherwise the name. Order: overview, groups sorted by name, `_default` last.
- 127.0.0.1 only, token, `Host` / `Origin` checks unchanged; no network from the page (`scripts/check_static.py`).
- Library code raises (`_errors.py`), only `cli.py` prints. Commands: `uv run --no-sync poe test`, `uv run --no-sync poe lint`, `npm --prefix frontend run typecheck`, `uv run poe frontend` (build); never bare `pytest`. Coverage ≥ 90 %.
- English everywhere; commits `feat: #6 - <description>` (`test:` / `docs:` / `refactor:` as fits).
- UI texts exactly as in Task 6.

## Review Focus

1. A schema / app / module literally named `overview` is a normal group next to `_overview`: both appear, and a save round-trips both (test in Task 3).
2. The same entity is own in one diagram and foreign in another: saving different positions keeps both (test in Task 3).
3. `group_by = "none"`: only the overview; the diagram list is hidden; a save body with only `_overview` passes (tests in Task 2 and 3; manual in Task 6).
4. A save body missing a current group, naming an unknown or stale diagram, or with a diagram that is not an object → 409 / 400, never a written file (tests in Task 3).
5. Group names with characters a URL hash must encode (`my app`, `a/b`, `ä`) and an unknown `#diagram=` value → the right diagram / the overview (manual check in Task 6, `encodeURIComponent` / `decodeURIComponent`).

---

### Task 1: What a diagram draws

**Files:**
- Modify: `src/erdify_studio/_check.py` (`DiagramContent`)
- Modify: `src/erdify_studio/_place.py` (name the foreign-box size)
- Test: `tests/test_check.py`, `tests/test_place.py`

**Interfaces:**
- Produces: `DiagramContent.shows_edge(self, a: str, b: str) -> bool` — both keys in `shown` and at least one in `entities`. On the overview (`foreign` empty) every edge between shown keys.
- Produces: `DiagramContent.shows_enum_link(self, enum: str, entity: str) -> bool` — `enum in self.enums and entity in self.entities`.
- Produces (in `_place.py`): `name_box_size(key: str) -> tuple[int, int]` — the size `place_layout` uses for a foreign box (today the inline `_box(key, ())`); `place_layout` calls it.

- [ ] **Step 1: Write the failing tests** in `tests/test_check.py`, on a `DiagramContent(entities={"a", "b"}, foreign={"x", "y"}, enums={"enum:E"})`:
  - `test_shows_edge` parametrized: `("a","b") → True`, `("a","x") → True`, `("x","a") → True`, `("x","y") → False`, `("a","z") → False` (`z` not shown), `("a","a") → True`.
  - `test_overview_shows_every_edge`: `DiagramContent(frozenset({"a","b"}))` → `shows_edge("a","b")`.
  - `test_shows_enum_link`: `("enum:E","a") → True`, `("enum:E","x") → False`, `("enum:F","a") → False`.
  - In `tests/test_place.py`: `test_foreign_box_has_the_name_box_size` — after `place_layout` puts a foreign box next to its own box, the gap check uses `name_box_size(key)`: assert `name_box_size("core.customers") == (width, METRICS["header"])` with the width `_box("core.customers", ())` gives (import `_box` is fine in this test module, it already tests internals).
- [ ] **Step 2: Run** `uv run --no-sync poe test tests/test_check.py tests/test_place.py` — expect FAIL (`AttributeError` / `ImportError`).
- [ ] **Step 3: Implement** the two methods and `name_box_size`; replace the inline `_box(key, ())` in `place_layout` with it.
- [ ] **Step 4: Run** the same command — PASS; then `uv run --no-sync poe lint`.
- [ ] **Step 5: Commit** `feat: #6 - the edges and enum links a diagram draws`.

### Task 2: The diagrams payload

**Files:**
- Rename: `src/erdify_studio/_overview.py` → `src/erdify_studio/_diagrams.py` (`git mv`; update the module docstring)
- Rename: `tests/test_overview.py` → `tests/test_diagrams.py`
- Modify: `src/erdify_studio/_server.py` (import only; the route changes in Task 4), `tests/test_server.py`, `tests/test_check.py` (imports of `build_overview` → `build_diagrams`)

**Interfaces:**
- Consumes: `DiagramContent.shows_edge`, `shows_enum_link`, `name_box_size` (Task 1); `project_diagrams`, `place_inputs`, `place_layout`, `METRICS`, `layout_revision` (existing).
- Produces TypedDicts (camelCase, mirrored in `frontend/src/api.ts` in Task 5):
  - `BoxDef`: `kind: Literal["entity","enum"]`, `title: str`, `group: str | None`, `width: int`, `height: int`, `rows: list[FieldRow] | list[ValueRow]` (`FieldRow`, `ValueRow`, `EdgeJson`, `EdgeEndJson`, `EnumLink` unchanged).
  - `DiagramJson`: `name: str`, `label: str`, `own: list[str]` (entities + enums, sorted), `foreign: list[str]` (sorted), `foreignSizes: dict[str, list[int]]`, `positions: dict[str, list[int]]`, `new: list[str]` (sorted), `edges: list[EdgeJson]`, `enumLinks: list[EnumLink]`.
  - `Pending`: `placed: int`, `diagrams: int` (diagrams with placed boxes), `dropped: int` (`len(removed) + len(removed_diagrams)`), `created: bool`.
  - `Diagrams`: `metrics`, `boxes: dict[str, BoxDef]`, `diagrams: list[DiagramJson]`, `revision`, `pending`, `layoutPath`, `projectPath`.
- Produces: `build_diagrams(project: Project, config: StudioConfig, *, shown_path: str) -> Diagrams` (replaces `build_overview`; same `Raises:`).
- `group` of an entity box: `entity_groups(project.entities, config.group_by)` value, `None` under `none`; enums `None`.

- [ ] **Step 1: Move and adapt the existing tests.** `git mv` both files; every `build_overview` test reads the overview entry (`next(d for d in payload["diagrams"] if d["name"] == OVERVIEW)`) and `payload["boxes"][key]` for sizes/rows. Box `x`/`y`/`new` move to `positions` / `new` of the diagram. Replace the pending assertions with the new shape (`{"placed": 0, "diagrams": 0, "dropped": 0, "created": False}` when up to date; the stale-group-entry case → `dropped == 1`).
- [ ] **Step 2: Add the failing tests** in `tests/test_diagrams.py` on the existing `MODELS` (`core.customers`; `billing.invoices` → customers; `billing.lines` → invoices; enum used by an invoice field), default `group_by = "auto"`:
  - `test_diagram_order_and_labels`: names `["_overview", "billing", "core"]`, labels `["Overview", "billing", "core"]`.
  - `test_default_group_is_last_and_ungrouped`: models where one entity has no schema/app/module value cannot occur with SQLModel files (module is always set) — use `group_by = "schema"` with one schema-less entity → last diagram `name == "_default"`, `label == "Ungrouped"`.
  - `test_group_by_none_has_only_the_overview`: `len(diagrams) == 1`, every box `group is None`.
  - `test_group_diagram_content`: `core` → `own == ["core.customers"]`, `foreign == ["billing.invoices"]`; `billing` → `foreign == ["core.customers"]`, `own` includes the enum key.
  - `test_foreign_sizes_are_name_box_sizes`: `core["foreignSizes"]["billing.invoices"] == list(name_box_size("billing.invoices"))`.
  - `test_group_diagram_edges`: `core` edges == the invoice → customer edge only; `billing` edges include invoice → customer and line → invoice.
  - `test_edges_between_foreign_boxes_are_not_drawn`: add `shop.audit` (schema `audit`) referencing both `core.customers` and `billing.invoices`; in the `audit` diagram both are foreign and the customer ← invoice edge is absent while both audit edges are present.
  - `test_enum_links_per_diagram`: `core` has no enum links; `billing` links the enum to the invoice.
  - `test_positions_per_diagram`: a layout with `core.customers` at `[0, 0]` on the overview and `[500, 40]` in `core` → both diagrams report their own position.
  - `test_new_per_diagram`: no layout file → every key of every diagram is in its `new`; `pending == {"placed": <sum>, "diagrams": 3, "dropped": 0, "created": True}`.
  - `test_box_definitions_once`: `set(payload["boxes"]) == set(overview["own"])`.
  - `test_group_named_overview` (Review Focus 1, payload half): schema `overview` → names include both `"_overview"` and `"overview"`.
- [ ] **Step 3: Run** `uv run --no-sync poe test tests/test_diagrams.py` — FAIL.
- [ ] **Step 4: Implement** `build_diagrams` (one `place_layout` run over all diagrams, as `build_overview` did for the overview; edges from `diagram_edges` mapped to layout keys once, then filtered per diagram with `shows_edge`, enum links with `shows_enum_link`; sort order per Global Constraints). Remove `build_overview`, `Overview`, `Box`. Update imports in `_server.py` (keep the old route working on the new function for now: it returns the new payload) and in the tests.
- [ ] **Step 5: Run** `uv run --no-sync poe test` (all) and `uv run --no-sync poe lint` — PASS.
- [ ] **Step 6: Commit** `feat: #6 - one payload with every diagram`.

### Task 3: Save every diagram

**Files:**
- Modify: `src/erdify_studio/_diagrams.py`
- Test: `tests/test_diagrams.py`

**Interfaces:**
- Produces: `save_diagrams(project: Project, config: StudioConfig, diagrams: object, revision: str | None) -> str | None` (replaces `save_overview`; returns the new revision).
- Validation order: revision (409, unchanged message) → `diagrams` must be a mapping (`PositionsError`, `"diagrams must be an object, got 'list'"`) → its names equal the current `project_diagrams` names, else `LayoutConflictError("the models changed since the page loaded (new diagram 'x' / no diagram 'y' any more); reload the page")` → each diagram through the existing `_checked(positions, content.shown)` (its messages unchanged; prefix nothing) → write every diagram, run `place_layout` (no-op for a complete body), `save_layout`.

- [ ] **Step 1: Move the existing save tests** to the new body shape (`{"_overview": {...}, "billing": {...}, "core": {...}}`, built from a `build_diagrams` payload's positions by a helper `_body(payload)`).
- [ ] **Step 2: Add the failing tests:**
  - `test_save_writes_every_diagram`: change one position in `core` → the file has it in `core` and the overview unchanged.
  - `test_same_entity_keeps_a_position_per_diagram` (Review Focus 2): `core.customers` at `[0,0]` overview, `[900,0]` in `core`, foreign in `billing` at `[300,300]` → all three in the file.
  - `test_after_save_check_passes` (kept).
  - `test_save_with_group_by_none` (Review Focus 3): body with only `_overview` → saved, `check_project == []`.
  - `test_group_named_overview_round_trips` (Review Focus 1): schema `overview` → save the payload's positions → both `_overview` and `overview` in the file, `check_project == []`.
  - `test_save_refuses_a_non_object` parametrized over `[]`, `None`, `"x"` → `PositionsError` "diagrams must be an object".
  - `test_save_conflicts_on_diagram_set` (Review Focus 4) parametrized: a current group missing → `LayoutConflictError` "new diagram 'core'"; an extra `"stale"` → "no diagram 'stale' any more"; nothing written (file bytes unchanged).
  - `test_save_refuses_a_diagram_that_is_not_an_object`: `{"core": [1, 2], ...}` → `PositionsError` "positions must be an object".
- [ ] **Step 3: Run** `uv run --no-sync poe test tests/test_diagrams.py` — FAIL.
- [ ] **Step 4: Implement** `save_diagrams`; remove `save_overview`; `_server.py` calls `save_diagrams(project, config, payload["diagrams"], payload["revision"])` — the body key change happens with the route in Task 4, so in this task keep `_server.py` reading `payload["positions"]` wrapped as `{OVERVIEW: ...}` only if needed to keep `tests/test_server.py` green; otherwise do the body change here and update its tests.
- [ ] **Step 5: Run** all tests + lint — PASS.
- [ ] **Step 6: Commit** `feat: #6 - save every diagram in one write`.

### Task 4: Server routes

**Files:**
- Modify: `src/erdify_studio/_server.py`, `tests/test_server.py`

**Interfaces:**
- `GET /api/diagrams` → `build_diagrams(...)`; `GET /api/overview` → 404 (`"not found"`, the generic `/api/` branch).
- `PUT /api/layout` body `{"revision": str | null, "diagrams": {...}}`; missing `diagrams` key → 400 (same path as a missing `positions` key today). Status mapping unchanged: `PositionsError` 400, `LayoutConflictError` 409, load errors 500.

- [ ] **Step 1: Update the tests:** every `/api/overview` → `/api/diagrams`; `_positions(studio)` helper builds the `diagrams` body from the payload; `test_get_diagrams` compares with `build_diagrams`; add `test_old_overview_route_is_404`; add `test_put_without_diagrams_is_400`.
- [ ] **Step 2: Run** `uv run --no-sync poe test tests/test_server.py` — FAIL.
- [ ] **Step 3: Implement** the route and body change.
- [ ] **Step 4: Run** all tests + lint — PASS.
- [ ] **Step 5: Commit** `feat: #6 - GET /api/diagrams and saving every diagram`.

### Task 5: Frontend state per diagram

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/App.vue`, `frontend/src/components/DiagramCanvas.vue`

**Interfaces:**
- `api.ts`: `BoxDef`, `DiagramJson`, `Pending`, `Diagrams` mirror Task 2 exactly; `fetchDiagrams(): Promise<Diagrams>` (`GET api/diagrams`); `saveLayout(revision, diagrams: Record<string, Record<string, Position>>)` posts `{revision, diagrams}`.
- `App.vue` state: `positions: Record<diagram, Record<key, Position>>`, `newKeys: Record<diagram, Set<string>>`, `movedDiagrams: Set<string>`, `current: string` (diagram name). `dirty` = pending shown or any moved diagram. Save sends every diagram's positions; on success clears all NEW sets and `movedDiagrams`.
- `DiagramCanvas` props: `boxes: Record<string, BoxDef>`, `diagram: DiagramJson`, `metrics`, `positions: Record<string, Position>`, `newKeys: ReadonlySet<string>`, `projectPath`. It draws `diagram.own` with `boxes[key]` sizes, `diagram.foreign` with `foreignSizes` (plain boxes for now — styling in Task 7), and only `diagram.edges` / `diagram.enumLinks` (drop the client-side filtering by "both rects exist"). Emits `move`.
- Re-key the canvas by diagram (`:key="current"`) so each diagram fits on first open; Task 6 keeps the view per diagram.

- [ ] **Step 1: Implement** the types, fetch/save and the per-diagram state; App shows the overview only (no switcher yet).
- [ ] **Step 2: Run** `npm --prefix frontend run typecheck` — no errors.
- [ ] **Step 3: Manual check:** `uv run poe frontend`, then `uv run --no-sync erdify-studio tests/fixtures/<a project with groups>` (or a temp project with the `MODELS` of `tests/test_diagrams.py`): the overview looks as before #6, drag + Save writes the file, `uv run --no-sync erdify-studio check <path>` passes.
- [ ] **Step 4: Commit** `feat: #6 - canvas state per diagram`.

### Task 6: Diagram list, switching, banner

**Files:**
- Create: `frontend/src/components/DiagramList.vue`
- Modify: `frontend/src/App.vue`, `frontend/src/components/StudioToolbar.vue`, `frontend/src/components/DiagramCanvas.vue`

**Interfaces:**
- `DiagramList` props: `diagrams: DiagramJson[]`, `current: string`, `unsaved: ReadonlySet<string>`; emits `select: [name: string]`. Each row: label, own-entity count (`own` without `enum:` keys) for groups, a dot when in `unsaved` (moved, or has NEW keys). Hidden by App when `diagrams.length === 1`.
- `StudioToolbar` gains prop `title: string` → `erdify-studio · {title}` (the current label).
- View per diagram: `DiagramCanvas` takes `view?: View` and emits `view: [View]`; App keeps `views: Record<string, View>`; a diagram without a stored view is fitted.
- Hash: `#diagram=<encodeURIComponent(name)>` written on switch (`history.replaceState`), read on load (unknown → `_overview`).
- Banner texts (exact):
  - placed: `` `${placed} new ${placed === 1 ? "box was" : "boxes were"} placed automatically in ${diagrams} ${diagrams === 1 ? "diagram" : "diagrams"} — save to keep them.` ``
  - created (no placed): `` `No layout file yet — save to create ${layoutPath}.` ``
  - dropped (no placed, file exists): `` `The layout file has ${dropped} stale ${dropped === 1 ? "entry" : "entries"} — save to drop them.` ``

- [ ] **Step 1: Implement** the list, title, views, hash and banner.
- [ ] **Step 2: Run** `npm --prefix frontend run typecheck` — no errors.
- [ ] **Step 3: Manual check** (Review Focus 3 and 5): switch diagrams, drag in two of them, both show a dot; switch back — positions kept; Save once → dots gone, `check` passes; reload keeps the diagram; `#diagram=nope` → overview; a project with `group_by = "none"` shows no list; a module group with a dot/space in its name selects correctly from the hash.
- [ ] **Step 4: Commit** `feat: #6 - switch between the overview and group diagrams`.

### Task 7: Foreign boxes

**Files:**
- Modify: `frontend/src/components/BoxNode.vue`, `frontend/src/components/DiagramCanvas.vue`, `frontend/src/App.vue`

**Interfaces:**
- `BoxNode` gains `foreign: boolean` and `highlighted: boolean`. Foreign: title only (no rows), dashed frame, muted fill and text (`--ui-bg-muted`, `--ui-text-muted`, frame `--ui-border-accented` dashed `4 3`), cursor `pointer` until dragged. Highlighted: the NEW frame style for 1.5 s.
- `DiagramCanvas` emits `open: [key: string]` on pointer-up of a foreign box when the pointer moved < 4 px since pointer-down (a drag above that moves it as any box). Exposes `focus(key)`: centre `key` at the current scale.
- App on `open(key)`: switch to `boxes[key].group` (ignore when `null` or unknown), then `focus(key)` and highlight it — overriding the stored view of that diagram.

- [ ] **Step 1: Implement** the style, click-vs-drag, `open`, `focus`, highlight.
- [ ] **Step 2: Run** `npm --prefix frontend run typecheck`; `uv run poe frontend`; `uv run --no-sync poe check-static`.
- [ ] **Step 3: Manual check** (issue #6 criteria 2–4): in `core`, the invoice box is greyed, name only, with the edge to customers; dragging it moves it in `core` only (overview and `billing` unchanged); a click opens `billing` with the invoice centred and highlighted; Save → `check` passes.
- [ ] **Step 4: Commit** `feat: #6 - foreign boxes open their group diagram`.

### Task 8: Docs

**Files:**
- Modify: `CHANGELOG.md` (Unreleased → Added), `README.md` (status line and usage), `docs/design/2026-11-23-group-diagrams.md` only if the build deviated.

- [ ] **Step 1:** CHANGELOG entry: group diagrams next to the overview (switch, foreign boxes greyed and name-only that open their group, positions per diagram, one Save writes every diagram, `GET /api/diagrams` replaces `/api/overview`). README: drop "group diagrams … still to come"; describe switching and foreign boxes in the usage section.
- [ ] **Step 2:** `pre-commit run --files CHANGELOG.md README.md`; `uv run --no-sync poe test --cov-fail-under=90`.
- [ ] **Step 3: Commit** `docs: #6 - group diagrams`.
