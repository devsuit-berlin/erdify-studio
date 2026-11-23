# SVG Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `erdify-studio export` writes one deterministic SVG per diagram to `export_dir`; `check` and studio's Save keep them current.

**Architecture:** `_geometry.py` ports `frontend/src/geometry.ts` 1:1 (guarded by a Node-vs-Python parity check in CI); `_svg.py` renders one `DiagramJson` of the #6 payload to a byte-stable SVG string; `_export.py` maps diagrams to files (`overview.svg`, `groups/<slug>.svg`), writes / compares / deletes them. The CLI gains `export`, `check` compares SVGs, the server exports on Save and reports outdated SVGs on load.

**Tech Stack:** Python ≥ 3.11 stdlib (`unicodedata`, `xml.sax.saxutils`); Node 24 (CI only, type stripping); Vue 3.

**Spec:** `docs/design/2026-11-23-svg-export.md`

## Global Constraints

- No new runtime dependency; nothing new in `erdify_studio.__all__`.
- Files: `overview.svg`; `groups/<slug>.svg`; `_default` → `groups/ungrouped.svg`. Slug: NFKD, drop non-ASCII, lowercase, runs outside `[a-z0-9]` → `-`, strip `-`, empty → `group`.
- Output: UTF-8, `\n` endings, trailing newline, no timestamp; numbers via one formatter (2 decimals, no trailing zeros, `-0` → `0`); boxes sorted by key; edges in payload order.
- Look: light palette constants (studio's light-theme token values, read from the built CSS), explicit white background, font stack `"JetBrains Mono", ui-monospace, Menlo, Consolas, "DejaVu Sans Mono", monospace`, font size `charWidth / 0.6`, `viewBox` margin 40.
- `export` refuses an out-of-date layout (exit 1 + check lines + `place --auto` hint); exit 2 without `export_dir` or on `ExportError`.
- Messages: check line `export '<path>' is missing` / `is out of date` / `is stale`; hint `run \`erdify-studio export\``. Banner: ``The SVGs in ${exportPath} are out of date — save to update them.`` Toast: ``Saved, but the SVG export failed: ${message}``.
- Commands: `uv run --no-sync poe test` / `lint`, `npm --prefix frontend run typecheck`, `uv run poe frontend`; commits `feat: #8 - …`.

## Review Focus

1. A group whose name only differs in case or punctuation from another (`Sales` / `sales`, `my app` / `my-app`) → `ExportError` naming both, nothing written (test in Task 3).
2. `export_dir` containing user files (`README.md`, `groups/notes.txt`, an `old.svg` at top level) → untouched; only stale `groups/*.svg` are deleted (test in Task 3).
3. Entity / column names with `<`, `&`, `"` and non-ASCII (`Straße`) → valid XML, escaped, byte-stable (test in Task 2).
4. Self-referencing FK and three parallel edges between two boxes → fans and loops match the canvas (parity cases in Task 1).
5. A project with `group_by = "none"` → only `overview.svg`; an existing `groups/` keeps non-SVG files and loses its `*.svg` (test in Task 3).

---

### Task 1: Geometry port and parity check

**Files:** Create `src/erdify_studio/_geometry.py`, `tests/test_geometry.py`, `scripts/geometry_cases.json`, `scripts/geometry_parity.mjs`, `scripts/check_geometry.py`; modify `.github/workflows/package.yml`, maybe `frontend/src/geometry.ts` / `frontend/tsconfig.json` (import extension only).

**Interfaces:** `Point = tuple[float, float]`, `Rect` dataclass (`x, y, width, height`); `center`, `border_point(rect, toward, start=None)`, `fan_offsets(edges: Sequence[tuple[str, str]]) -> list[float]`, `edge_line(a, b, offset, a_key, b_key) -> tuple[Point, Point]`, `self_loop(rect, index) -> SelfLoop` (`path, start, start_angle, end, end_angle`), `angle(a, b)`, `end_marker(point, direction, optional, many) -> Marker` (`lines: str`, `circle: str | None`), constants `FAN_STEP = 16`. Path strings use the same number formatting as `geometry.ts` (`toFixed(2)` where it uses it, raw numbers elsewhere) so the parity compare can parse numbers out of them.

- [ ] Write `scripts/geometry_cases.json` (border points in 8 directions incl. overlapping / touching rects; fans of 1–4 edges incl. A→B + B→A and a self-edge; `edge_line` with offsets; `self_loop` index 0–2; `end_marker` for all four `{optional, many}`).
- [ ] Write `tests/test_geometry.py` with hand-checked expected values for one case of each function (e.g. `border_point(Rect(0,0,100,50), (300,25)) == (100, 25)`; `fan_offsets([("a","b")]*3) == [-16, 0, 16]`; a self-edge gets index 0); run `uv run --no-sync poe test tests/test_geometry.py` → FAIL (ImportError).
- [ ] Implement `_geometry.py`; run → PASS.
- [ ] `scripts/geometry_parity.mjs`: import `../frontend/src/geometry.ts`, run every case, print `JSON.stringify(results)`. `scripts/check_geometry.py`: read cases + stdin JSON, run `_geometry`, compare numbers (paths: extract numbers with a regex) within 0.01, exit 1 naming the first case that differs. Run `node scripts/geometry_parity.mjs | uv run --no-sync python scripts/check_geometry.py` → "geometry: N cases match". If Node can't load the extensionless import, switch `geometry.ts` to `./drawing.ts` and add `"allowImportingTsExtensions": true` (typecheck + build must stay green).
- [ ] Prove the check bites: change `FAN_STEP` to 17 in `_geometry.py` temporarily → exit 1; revert.
- [ ] Add the CI step after "Build the frontend" in `package.yml`: `- name: Canvas and SVG export draw the same geometry` / `run: node scripts/geometry_parity.mjs | uv run --frozen python scripts/check_geometry.py`. Include `scripts/check_geometry.py` in mypy `files` if it imports the package.
- [ ] Lint, commit `feat: #8 - geometry of the canvas in Python, checked against geometry.ts`.

### Task 2: Render one diagram

**Files:** Create `src/erdify_studio/_svg.py`, `tests/test_svg.py`, `tests/fixtures/export/` (golden files).

**Interfaces:** `render_svg(diagram: DiagramJson, boxes: Mapping[str, BoxDef], metrics: Mapping[str, int]) -> str`; `format_number(value: float) -> str`; palette constants (`_PALETTE` dict, one entry per token, comment naming it).

- [ ] Tests first: `test_format_number` parametrized (`0 → "0"`, `-0.0 → "0"`, `12.5 → "12.5"`, `12.50 → "12.5"`, `3.0 → "3"`, `1.005 → "1"` or `"1.01"` per `round`-half-even — pin what Python gives, `123456 → "123456"`); `test_render_is_deterministic` (same payload twice → equal; payload from a copy of the project dir → equal); `test_render_matches_the_golden_files` (the `MODELS` project of `tests/test_diagrams.py` with a fixed layout → `overview.svg`, `groups/billing.svg`, `groups/core.svg` byte-equal to `tests/fixtures/export/…`; a `--update-golden` env var `ERDIFY_STUDIO_UPDATE_GOLDEN=1` rewrites them); `test_text_is_escaped` (Review Focus 3: a column `a<b&"c"` and table `straße` → `xml.etree.ElementTree.fromstring` parses, the text round-trips); `test_foreign_box_is_title_only_and_dashed`; `test_enum_link_is_dashed_without_markers`; `test_edge_label_is_a_title`; `test_viewbox_covers_every_box_and_loop` (self-referencing FK: the loop's reach is inside the viewBox); `test_background_is_white`. Run → FAIL.
- [ ] Implement `render_svg`: hand-written XML in the fixed order (background, enum links, edges, boxes sorted by key), the box drawing of `BoxNode.vue` (header band, title, badges `PK FK UK` with UK hidden on a PK, name at `inset + 6 * charWidth`, type right-aligned with `?`, dividers, frame `rx="6"`, enum header tint, clip-path ids `clip-<index>` by sorted position), edges via `_geometry` (+ `<title>` label), markers. Read the palette hex values from `src/erdify_studio/_static/assets/index-*.css` (light theme) once, write them as constants.
- [ ] Generate the golden files with the env var, read them as SVG in a browser or image viewer once (Looks: boxes and edges where studio puts them), commit them.
- [ ] Run tests → PASS; lint; commit `feat: #8 - render a diagram as SVG`.

### Task 3: Export files

**Files:** Create `src/erdify_studio/_export.py`, `tests/test_export.py`; modify `src/erdify_studio/_errors.py` (`ExportError(StudioError)`).

**Interfaces:** `slug(name: str) -> str`; `export_paths(diagrams: Iterable[str]) -> dict[str, PurePosixPath]` (diagram name → relative path; raises `ExportError(f"groups {a!r} and {b!r} would both be exported as {path!r}; rename one")`); `export_files(project, config) -> dict[PurePosixPath, str]`; `export_project(project, config) -> ExportResult` (`written: tuple[PurePosixPath, ...]`, `deleted: tuple[...]`; unchanged files are not rewritten); `check_exports(project, config) -> list[str]` (messages, empty when current); `OutOfDateLayoutError(ExportError)` carrying the `check_project` problems. All raise `ExportError` when `config.export_dir is None`.

- [ ] Tests first: `test_slug` parametrized (`"core"`, `"my app" → "my-app"`, `"Bestellungen/Ä" → "bestellungen-a"`, `"__x__" → "x"`, `"ü" → "u"`, `"!!!" → "group"`); `test_paths` (`_overview → overview.svg`, `_default → groups/ungrouped.svg`); `test_slug_collision` parametrized (`Sales`/`sales`, `my app`/`my-app`, `ungrouped`/`_default`) → `ExportError` naming both, nothing written (Review Focus 1); `test_export_writes_every_diagram`; `test_export_twice_writes_nothing_the_second_time`; `test_stale_group_svgs_are_deleted_other_files_kept` (Review Focus 2: `README.md`, `old.svg`, `groups/notes.txt` stay); `test_group_by_none` (Review Focus 5); `test_export_refuses_an_out_of_date_layout` (no layout file / an unplaced entity → `OutOfDateLayoutError`, nothing written); `test_without_export_dir`; `test_check_exports` parametrized missing / outdated (a column added: box taller) / stale / current → messages exactly as in Global Constraints with the path shown relative to the project like `_display` does. Run → FAIL.
- [ ] Implement; positions from the layout file via `build_diagrams` (its positions equal the file's when `check_project(...) == []`).
- [ ] Run → PASS; lint; commit `feat: #8 - export every diagram to export_dir`.

### Task 4: CLI

**Files:** Modify `src/erdify_studio/cli.py`, `tests/test_cli.py`.

- [ ] Tests first: `export` subcommand (`--help` lists it; `_TOP_LEVEL` includes it); exit 0 with one line per written / deleted file (`<shown path>: wrote` / `deleted`) or `"<export_dir>: SVGs up to date"`; exit 1 + check lines + hint on an out-of-date layout; exit 2 without `export_dir` (`set [tool.erdify-studio] export_dir to export SVGs`) and on a slug collision. `check` with `export_dir`: SVG lines + `run \`erdify-studio export\`` last, exit 1; up to date → 0; layout problems → only the layout lines and the existing hint (no SVG lines). Run → FAIL.
- [ ] Implement (`ExportError` maps to exit 2 in `main`, like the other `StudioError`s); README: replace the "planned" line, describe `export`, the files, the light look, and the `check` addition.
- [ ] Run → PASS; lint; commit `feat: #8 - export command and SVG check`.

### Task 5: Studio

**Files:** Modify `src/erdify_studio/_diagrams.py`, `_server.py`, `tests/test_diagrams.py`, `tests/test_server.py`, `frontend/src/api.ts`, `frontend/src/App.vue`.

**Interfaces:** `Pending.svgs: int` (0 without `export_dir` or while the layout is out of date); `Diagrams.exportPath: str | None`; `PUT /api/layout` 200 body adds `exported: int` or `exportError: str`.

- [ ] Tests first: `test_pending_svgs` (no `export_dir` → 0; exported then a column added → > 0; current → 0); server: save with `export_dir` writes the SVGs and returns `exported`; a slug collision returns 200 with `exportError` and the new revision, layout file written. Run → FAIL.
- [ ] Implement server/payload; frontend: `pendingShown` also when `pending.svgs > 0`; banner text when only `svgs` is pending; toast on `exportError` (warning colour) and Save stays enabled (`pendingShown` stays true); `exported` ignored otherwise.
- [ ] `npm --prefix frontend run typecheck`, `uv run poe frontend`, `poe check-static`, all tests, lint; manual check in the browser by the user (banner after adding a column; Save writes `docs/erd`); commit `feat: #8 - Save writes the SVGs and studio shows outdated ones`.

### Task 6: Docs

- [ ] CHANGELOG (Added: `export`, `check` SVG lines, Save exports, outdated-SVG banner); README status line (SVG export works). `pre-commit run --files …`, full `poe test --cov-fail-under=90`; commit `docs: #8 - SVG export`.
