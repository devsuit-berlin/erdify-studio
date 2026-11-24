# Colour Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A **Colours** side panel in studio previews diagram colours on the canvas without writing anything, and copies the matching `[tool.erdify-studio.colors]` table as TOML.

**Architecture:** Python stays the only place that resolves colours and formats TOML: `POST /api/colors` takes the panel's keys and returns the resolved `ColorsJson` plus the TOML text; `GET /api/diagrams` gains `colorConfig` (the keys set in `pyproject.toml`). The Vue panel only holds the edited keys, calls the endpoint (debounced) and hands the returned colours to the canvas.

**Tech Stack:** Python ≥ 3.11 stdlib; Vue 3 + Nuxt UI 4.12 (`USlideover`, `UColorPicker`, `UPopover`, `UInput`, `useToast`).

**Spec:** `docs/design/2026-11-24-colour-preview.md`

## Global Constraints

- Nothing is written to disk by the preview; no new dependency (Python or npm).
- The nine keys, in `DiagramColors` field order: `accent, header, header_text, background, text, text_muted, border, border_strong, background_muted`; groups **Brand** (first four) and **Details** (last five).
- `POST /api/colors`: body `{"colors": {"<key>": "#rrggbb" | null}}`; unknown key, non-object, wrong type or invalid hex → 400 naming the key and value; token and `Host`/`Origin` checks like every API route; response `{"colors": ColorsJson, "toml": str}`.
- TOML text: first line `[tool.erdify-studio.colors]`, then `key = "#rrggbb"` per set key in field order, lowercase, trailing newline; no keys → the header line plus newline.
- `GET /api/diagrams` gains `colorConfig: {key: "#rrggbb"}` (set keys only, lowercase).
- No colour maths and no TOML formatting in TypeScript.
- Preview applies in light mode only (as the canvas colours do); dark mode shows a note in the panel.
- Commands: `uv run --no-sync poe test` / `lint`, `npm --prefix frontend run typecheck`, `uv run poe frontend`, `uv run --group docs poe docs`; commits `feature: #68 - …`.

## Review Focus

1. Uppercase hex from the picker (`#4150AA`) → accepted and returned lowercase in the TOML (test in Task 2).
2. A half-typed hex (`#41`) → 400, and the panel keeps the last good preview, marks the row (Task 3 browser check).
3. `null` for a key the config sets → the key falls back to its default in the preview and is left out of the TOML (test in Task 2).
4. Editing `pyproject.toml` while the panel has changes → after the reload the panel is clean and the canvas shows the config's colours (Task 3 browser check).
5. Copy TOML pasted into `pyproject.toml` → the reloaded canvas colours equal the previewed ones (Task 3 browser check).

---

### Task 1: TOML text, colours JSON helper and `colorConfig`

**Files:**
- Modify: `src/erdify_studio/_colors.py`, `src/erdify_studio/_diagrams.py`
- Test: `tests/test_colors.py`, `tests/test_diagrams.py`

**Interfaces:**
- Produces:
  - `_colors.colors_toml(colors: DiagramColors) -> str`
  - `_colors.set_colors(colors: DiagramColors) -> dict[str, str]` (set keys only, field order)
  - `_diagrams.colors_json(palette: Palette) -> ColorsJson` (the dict `build_from` builds today, moved into a function and reused there)
  - `Diagrams.colorConfig: dict[str, str]`, filled with `set_colors(config.colors)`; `model_fingerprint` includes it (setting a key to its default value changes `colorConfig` but not `colors`)

- [ ] **Step 1: Write the failing tests**
  - `test_colors.py::test_colors_toml`: `colors_toml(DiagramColors()) == "[tool.erdify-studio.colors]\n"`; `colors_toml(DiagramColors(background="#fdf6e3", accent="#4150aa")) == '[tool.erdify-studio.colors]\naccent = "#4150aa"\nbackground = "#fdf6e3"\n'` (field order, not argument order).
  - `test_colors.py::test_colors_toml_round_trips`: write `colors_toml(c)` for `c = DiagramColors(accent="#4150aa", text="#111111")` into a pyproject under `[tool]`-compatible TOML (`tomllib.loads`) → the `colors` table equals `set_colors(c)`.
  - `test_colors.py::test_set_colors`: `set_colors(DiagramColors(border="#333333")) == {"border": "#333333"}`.
  - `test_diagrams.py::test_payload_carries_the_color_config`: default config → `payload["colorConfig"] == {}`; with `colors=DiagramColors(accent="#4150aa")` (via `dataclasses.replace`) → `{"accent": "#4150aa"}`.
  - `test_diagrams.py::test_fingerprint_follows_the_color_config`: `colors=DiagramColors(accent="#615fff")` (the default value) gives a different `model_fingerprint` than the default config.

- [ ] **Step 2: Run, expect failure**

Run: `uv run --no-sync poe test tests/test_colors.py tests/test_diagrams.py`
Expected: FAIL (`ImportError: colors_toml`, `KeyError: 'colorConfig'`).

- [ ] **Step 3: Implement** the three functions and `colorConfig`; `build_from` uses `colors_json(palette)`.

- [ ] **Step 4: Run the whole suite**

Run: `uv run --no-sync poe test`
Expected: PASS.

- [ ] **Step 5: Commit** — `feature: #68 - TOML text and colour config in the payload`

### Task 2: `POST /api/colors`

**Files:**
- Modify: `src/erdify_studio/_server.py` (`do_POST` routing, new `_colors` handler)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `colors_toml`, `palette_of`, `DiagramColors`, `HEX` (`_colors`), `colors_json` (`_diagrams`).
- Produces: route `POST /api/colors` → 200 `{"colors": ColorsJson, "toml": str}`, 400 on bad input.

- [ ] **Step 1: Write the failing tests** (helper `_post_colors(studio, payload, **kwargs)` like `_post_svg`):
  - `test_post_colors_resolves_and_formats`: `{"colors": {"header": "#192346"}}` → 200; `colors["header"] == "#192346"`, `colors["headerText"] == "#ffffff"`, `colors["enumHeader"] == "#d8deff"`; `toml == '[tool.erdify-studio.colors]\nheader = "#192346"\n'`.
  - `test_post_colors_lowercases`: `{"colors": {"accent": "#4150AA"}}` → `colors["accent"] == "#4150aa"`, `'accent = "#4150aa"' in toml`.
  - `test_post_colors_null_keeps_the_default`: `{"colors": {"accent": None}}` → `colors["accent"] == "#615fff"`, `toml == "[tool.erdify-studio.colors]\n"`.
  - `test_post_colors_errors`, parametrized: `{"colors": {"edge": "#000000"}}`, `{"colors": {"accent": "#41"}}`, `{"colors": {"accent": 1}}`, `{"colors": []}`, `{}` → 400, and the error text names the key/value where there is one (`"edge"`, `"'#41'"`).
  - `test_post_colors_needs_the_token`: without token → 403.
  - `test_post_colors_writes_nothing`: the project directory listing (recursive, with mtimes) is equal before and after a successful call.

- [ ] **Step 2: Run, expect failure**

Run: `uv run --no-sync poe test tests/test_server.py -k colors`
Expected: FAIL (405 method not allowed).

- [ ] **Step 3: Implement** the route next to `/api/svg` in `do_POST` and `_colors_preview(self) -> None` (reads `_body()`, validates, lowercases, builds `DiagramColors`; `ConfigError` → 400 with its message; responds via `_json`).

- [ ] **Step 4: Run the whole suite and lint**

Run: `uv run --no-sync poe test && uv run --no-sync poe lint`
Expected: PASS, no lint errors.

- [ ] **Step 5: Commit** — `feature: #68 - POST /api/colors resolves a colour preview`

### Task 3: Colours panel

**Files:**
- Create: `frontend/src/components/ColourPanel.vue`
- Modify: `frontend/src/api.ts` (`ColorConfig` type, `Diagrams.colorConfig`, `previewColors`), `frontend/src/components/StudioToolbar.vue` (button + `colours` emit), `frontend/src/App.vue` (panel state, canvas colours)

**Interfaces:**
- Consumes: `POST /api/colors`, `Diagrams.colorConfig`, `Diagrams.colors` (Tasks 1–2).
- Produces:
  - `api.ts`: `type ColorKey = "accent" | "header" | "header_text" | "background" | "text" | "text_muted" | "border" | "border_strong" | "background_muted"`; `type ColorConfig = Partial<Record<ColorKey, string>>`; `previewColors(colors: Partial<Record<ColorKey, string | null>>): Promise<{ colors: ColorsJson; toml: string }>` (token header like the other calls; throws on non-2xx with the server's `error`).
  - `ColourPanel.vue` props `{ open: boolean; config: ColorConfig; resolved: ColorsJson }`, emits `update:open`, `preview: [ColorsJson | null]` (`null` = no changes).

- [ ] **Step 1: Toolbar** — a `UButton` "Colours" (icon `i-lucide-palette`, `color="neutral"`, `variant="outline"`) before **Download SVG**, emitting `colours`.

- [ ] **Step 2: Panel** — `USlideover` (`side="right"`, `:overlay="false"`, `:modal="false"`, title "Colours"); two groups (Brand, Details) of rows `label · UPopover(UColorPicker) · UInput (hex) · × (clear)`; a row shows the edited value, else `config[key]`, else `resolved` (camelCase key) in muted text with "default"/"automatic"; edits are debounced 150 ms into `previewColors({...config, ...edits})` (edits with `null` for cleared config keys); success → emit `preview(colors)`, keep `toml`; failure → keep the last preview, mark the row with `color="error"` and the message; **Reset** clears edits and emits `preview(null)`; **Copy TOML** → `navigator.clipboard.writeText(toml)` + toast "Copied"; when `document.documentElement.classList.contains("dark")` show `UAlert` "The preview shows in light mode." (re-check on open).

- [ ] **Step 3: App wiring** — `previewed = ref<ColorsJson | null>(null)`; canvas gets `previewed ?? loaded.colors`; a `watch` on `loaded.colors` (deep) clears the panel's edits (expose a `reset()` or key the panel) and sets `previewed = null`.

- [ ] **Step 4: Typecheck and build**

Run: `npm --prefix frontend run typecheck && uv run poe frontend`
Expected: no errors; build written.

- [ ] **Step 5: Browser check** (scratch project, `erdify-studio open --no-browser`):
  - open the panel; pick `header` → canvas header changes, the title turns white, enum header unchanged; type `#41` in `accent` → row marked, canvas keeps the last colours;
  - Copy TOML → paste into the project's `pyproject.toml` → after the reload the panel is clean and the canvas looks the same;
  - with changes in the panel, edit `pyproject.toml` by hand → panel cleared, canvas follows the file;
  - dark mode: the note shows; canvas keeps the dark look.

- [ ] **Step 6: Commit** — `feature: #68 - colours panel with preview and Copy TOML`

### Task 4: Docs and changelog

**Files:**
- Modify: `docs/configuration.md` (Diagram colours: a paragraph on the panel), `docs/usage/canvas.md` (the panel), `CHANGELOG.md` (`[Unreleased]` → Added; drop "#68 not yet" from `docs/configuration.md`)

- [ ] **Step 1: Write** — the panel (Colours button, two groups, preview on the canvas in light mode only, Copy TOML into `pyproject.toml`, Reset, nothing written).

- [ ] **Step 2: Build the docs strictly**

Run: `uv run --group docs poe docs`
Expected: built, no warnings.

- [ ] **Step 3: Commit** — `docs: #68 - colour preview`
