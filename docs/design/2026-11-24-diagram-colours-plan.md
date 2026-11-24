# Diagram Colours Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `[tool.erdify-studio.colors]` (`accent`, `header`, `header_text`, `background`) sets the brand colours of the exported SVGs and of the canvas in light mode; without it nothing changes.

**Architecture:** `_colors.py` resolves the configured keys into a full `Palette` of hex values (defaults, OKLab enum-header mix, WCAG contrast picks). `_config.py` parses and validates the table into `DiagramColors` on `StudioConfig`. `render_svg` draws with a `Palette`; `build_diagrams` sends the canvas the same values (`colors`), the fingerprint includes them, and the canvas maps them onto CSS variables in light mode only.

**Tech Stack:** Python ≥ 3.11 stdlib (`tomllib`, `re`); Vue 3 + Nuxt UI (CSS variables).

**Spec:** `docs/design/2026-11-24-diagram-colours.md`

## Global Constraints

- No new runtime dependency; nothing is written to `pyproject.toml`.
- Config: table `[tool.erdify-studio.colors]`, keys `accent`, `header`, `header_text`, `background`; value `#rrggbb` (6 hex digits, any case), stored lowercase; anything else → `ConfigError` naming key, value (`!r`) and file; non-table `colors` → `ConfigError`; unknown key inside → warning, ignored.
- Defaults (today's values, must stay byte-identical): background `#ffffff`, background_muted `#f8fafc`, border `#e2e8f0`, border_accented `#cad5e2`, text `#0f172b`, text_muted `#62748e`, accent `#615fff`, header `#e2e8f0`, header_text `#0f172b`, enum_header `#d8deff`, enum_title `#0f172b`.
- Derived: enum_header = accent mixed 22 % into background in OKLab; header_text unset → `#0f172b` if header unset, else the better WCAG contrast of `#ffffff` / `#0f172b` against header; enum_title = the better of those two against enum_header.
- Warning when contrast(`#0f172b`, background) < 4.5.
- SVG keeps presentation attributes only (`fill="#rrggbb"`), no `<style>`.
- Canvas: configured colours in light mode only; dark mode unchanged.
- `DiagramColors` is new public API (`__all__`); `StudioConfig` gains `colors` (additive).
- Commands: `uv run --no-sync poe test` / `lint`, `npm --prefix frontend run typecheck`, `uv run poe frontend`, `uv run --group docs poe docs`; commits `feature: #48 - …`.

## Review Focus

1. `#FFF`, `fff`, `#ffffff80`, `"red"`, `123` as a colour → `ConfigError` with key and value, not a broken SVG (test in Task 2).
2. Only `header = "#192346"` set → entity title white, enum title still `#0f172b`, field names still `#0f172b` (test in Task 3).
3. An empty `[tool.erdify-studio.colors]` table → byte-identical export, golden files unchanged (test in Task 3).
4. Editing a colour while studio runs → `/api/status` reports a new `model` (test in Task 4).
5. A non-white light `background` (`#fdf6e3`) → enum header mixes into it, SVG background and box bodies use it, foreign boxes stay `#f8fafc` (test in Task 3).

---

### Task 1: Palette and colour maths

**Files:**
- Create: `src/erdify_studio/_colors.py`
- Test: `tests/test_colors.py`

**Interfaces:**
- Consumes: nothing (`DiagramColors` comes in Task 2; this task takes plain optional strings).
- Produces:
  - `@dataclass(frozen=True) class Palette` with `str` fields `background, background_muted, border, border_accented, text, text_muted, accent, header, header_text, enum_header, enum_title`.
  - `DEFAULT_PALETTE: Palette` (the Global Constraints defaults).
  - `resolve_palette(*, accent: str | None = None, header: str | None = None, header_text: str | None = None, background: str | None = None) -> Palette` (inputs already normalised lowercase).
  - `mix_oklab(color: str, base: str, amount: float) -> str` (`amount` of `color` into `base`).
  - `contrast(a: str, b: str) -> float` (WCAG 2.x ratio).
  - `readable_text(background: str) -> str` → `"#ffffff"` or `"#0f172b"`, whichever contrasts more.
  - `HEX = re.compile(r"^#[0-9a-fA-F]{6}$")`.

- [ ] **Step 1: Write the failing tests** in `tests/test_colors.py`:
  - `test_defaults_are_todays_colours`: `resolve_palette() == DEFAULT_PALETTE` and each field equals its Global Constraints value (`DEFAULT_PALETTE.enum_header == "#d8deff"`).
  - `test_mix_oklab_endpoints`: `mix_oklab("#615fff", "#ffffff", 0) == "#ffffff"`, `... 1) == "#615fff"`, `mix_oklab("#000000", "#ffffff", 0.5) == "#636363"`.
  - `test_contrast`: `contrast("#ffffff", "#000000") == pytest.approx(21)`, symmetric, `contrast("#615fff", "#615fff") == pytest.approx(1)`.
  - `test_readable_text`: `readable_text("#192346") == "#ffffff"`, `readable_text("#e2e8f0") == "#0f172b"`.
  - `test_header_text_follows_a_set_header`: `resolve_palette(header="#192346").header_text == "#ffffff"`; `resolve_palette(header="#192346", header_text="#f5dc19").header_text == "#f5dc19"`.
  - `test_enum_title_follows_the_enum_header`: `resolve_palette(header="#192346").enum_title == "#0f172b"`; `resolve_palette(accent="#000000", background="#000000").enum_title == "#ffffff"`.
  - `test_enum_header_mixes_into_the_background`: `resolve_palette(background="#fdf6e3").enum_header == mix_oklab("#615fff", "#fdf6e3", 0.22)`.

- [ ] **Step 2: Run them, expect failure**

Run: `uv run --no-sync poe test tests/test_colors.py`
Expected: FAIL (`ModuleNotFoundError: erdify_studio._colors`).

- [ ] **Step 3: Implement `_colors.py`**

OKLab per Björn Ottosson's reference: sRGB → linear (`c/12.92` if `c <= 0.04045`, else `((c+0.055)/1.055)**2.4`) → LMS (his M1) → cube root → Lab (M2); interpolate L, a, b linearly; back via the inverse matrices; clamp each channel to [0, 1]; `round(c * 255)`; lowercase `#rrggbb`. WCAG luminance uses the same linearisation with `0.2126 R + 0.7152 G + 0.0722 B`; ratio `(L1 + 0.05) / (L2 + 0.05)` with L1 the lighter. If the default mix rounds to a neighbour of `#d8deff`, keep `DEFAULT_PALETTE.enum_header = "#d8deff"` and have `resolve_palette` return it when `accent` and `background` are both unset (comment why: no output change, design goal 4).

- [ ] **Step 4: Run them, expect pass**

Run: `uv run --no-sync poe test tests/test_colors.py`
Expected: PASS.

- [ ] **Step 5: Commit** — `feature: #48 - palette with OKLab mix and contrast picks`

### Task 2: `[tool.erdify-studio.colors]` config

**Files:**
- Modify: `src/erdify_studio/_config.py` (`_KEYS`, `StudioConfig`, `load_config`)
- Modify: `src/erdify_studio/__init__.py` (`__all__`, import)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `HEX`, `contrast` from Task 1.
- Produces: `@dataclass(frozen=True) class DiagramColors` with `accent, header, header_text, background: str | None = None` (lowercase hex or None); `StudioConfig.colors: DiagramColors = DiagramColors()` (field with default, last, so existing constructors keep working); `"colors"` added to `_KEYS`; `DiagramColors` in `__all__`.

- [ ] **Step 1: Write the failing tests** (reuse `_pyproject(tmp_path, table)`):
  - `test_colors_default_to_none`: no table → `load_config(...).colors == DiagramColors()`.
  - `test_colors_are_read_and_lowercased`: `[tool.erdify-studio.colors]` with `accent = "#4150AA"` and `header_text = "#FFFFFF"` → `DiagramColors(accent="#4150aa", header_text="#ffffff")`.
  - `test_invalid_colors_are_errors`, parametrized over `"#fff"`, `"fff"`, `"#ffffff80"`, `"red"`, `123`: `pytest.raises(ConfigError, match=...)` whose message contains `'accent'`, the value's `repr` and the pyproject path.
  - `test_colors_must_be_a_table`: `colors = "x"` → `ConfigError` mentioning `colors`.
  - `test_unknown_color_keys_are_warned_about`: `border = "#000000"` → warning containing `'border'`, result `DiagramColors()`.
  - `test_a_dark_background_is_warned_about`: `background = "#1e2129"` → one WARNING containing `'#1e2129'` and `4.5`; `background = "#fdf6e3"` → no warning.
  - `test_diagram_colors_is_public`: `from erdify_studio import DiagramColors`.

- [ ] **Step 2: Run them, expect failure**

Run: `uv run --no-sync poe test tests/test_config.py`
Expected: FAIL (`ImportError: DiagramColors`).

- [ ] **Step 3: Implement** `_colors_table(table, source) -> DiagramColors` in `_config.py`, called from `load_config`; error texts follow the existing pattern `[tool.erdify-studio.colors] 'accent' must be a "#rrggbb" colour, got 'red' in /path/pyproject.toml`; warning text `[tool.erdify-studio.colors] background '#1e2129' is too dark for the field text (contrast 1.2:1, below 4.5:1) in …`.

- [ ] **Step 4: Run, expect pass; then the whole suite** (`StudioConfig` is constructed elsewhere)

Run: `uv run --no-sync poe test`
Expected: PASS.

- [ ] **Step 5: Commit** — `feature: #48 - [tool.erdify-studio.colors] config`

### Task 3: SVG export in the configured colours

**Files:**
- Modify: `src/erdify_studio/_svg.py` (drop the nine `_BG…_ENUM_HEADER` constants; `render_svg`, `_box`, edges and markers read the palette)
- Modify: `src/erdify_studio/_export.py:138`, `:244` (pass the palette)
- Test: `tests/test_svg.py`, `tests/test_export.py`

**Interfaces:**
- Consumes: `Palette`, `DEFAULT_PALETTE`, `resolve_palette` (Task 1); `StudioConfig.colors` (Task 2).
- Produces: `render_svg(diagram, boxes, metrics, palette: Palette = DEFAULT_PALETTE) -> str`; `palette_of(colors: DiagramColors) -> Palette` in `_colors.py` (thin wrapper over `resolve_palette`, used by `_export.py` and Task 4).

Role mapping (only the three role changes; every other use keeps its constant's palette field): entity header → `palette.header`; entity title → `palette.header_text`; enum title → `palette.enum_title`; field names stay `palette.text`; foreign title stays `palette.text_muted`.

- [ ] **Step 1: Write the failing tests**
  - `test_svg.py::test_render_svg_uses_the_palette`: render a fixture diagram with `resolve_palette(accent="#4150aa", header="#192346", background="#fdf6e3")`; assert `fill="#192346"` (entity header), `fill="#ffffff"` on an entity title `<text>`, `fill="#0f172b"` on a field name, `fill="#4150aa"` on a PK badge, background rect `fill="#fdf6e3"`, foreign body still `fill="#f8fafc"`, and no `<style`.
  - `test_export.py::test_an_empty_colors_table_changes_nothing`: project with `[tool.erdify-studio.colors]` and no keys → exported files equal the golden files in `tests/fixtures/export` byte for byte.
  - `test_export.py::test_export_follows_the_configured_colors`: `accent = "#4150aa"` → `overview.svg` contains `#4150aa` and `check_project` reports it outdated against an export made before the change.

- [ ] **Step 2: Run them, expect failure**

Run: `uv run --no-sync poe test tests/test_svg.py tests/test_export.py`
Expected: FAIL (`render_svg() takes 3 positional arguments`).

- [ ] **Step 3: Implement** the `palette` parameter and `palette_of`; `_export.py` passes `palette_of(config.colors)` in `export_files` and `render_download`.

- [ ] **Step 4: Run the whole suite; golden files must be untouched**

Run: `uv run --no-sync poe test && git status --short tests/fixtures`
Expected: PASS, no changes under `tests/fixtures`.

- [ ] **Step 5: Commit** — `feature: #48 - SVG export in the configured colours`

### Task 4: Colours in the API payload and fingerprint

**Files:**
- Modify: `src/erdify_studio/_diagrams.py` (`Diagrams`, `build_from`/`build_diagrams`, `model_fingerprint`)
- Test: `tests/test_diagrams.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `palette_of` (Task 3).
- Produces: `class ColorsJson(TypedDict)` with `accent, header, headerText, background, enumHeader, enumTitle: str`; `Diagrams.colors: ColorsJson`; `model_fingerprint` includes `payload["colors"]`.

- [ ] **Step 1: Write the failing tests**
  - `test_diagrams.py::test_payload_carries_the_colors`: default config → `payload["colors"] == {"accent": "#615fff", "header": "#e2e8f0", "headerText": "#0f172b", "background": "#ffffff", "enumHeader": "#d8deff", "enumTitle": "#0f172b"}`.
  - `test_diagrams.py::test_fingerprint_changes_with_the_colors`: same project, `DiagramColors()` vs `DiagramColors(accent="#4150aa")` → different `model_fingerprint`.
  - `test_server.py::test_status_reports_a_color_change`: write `[tool.erdify-studio.colors] accent = "#4150aa"` into the project's pyproject, `studio.server.refresh()`, `/api/status` `model` differs from before; `/api/diagrams` `colors.accent == "#4150aa"`.

- [ ] **Step 2: Run them, expect failure**

Run: `uv run --no-sync poe test tests/test_diagrams.py tests/test_server.py`
Expected: FAIL (`KeyError: 'colors'`).

- [ ] **Step 3: Implement**; `/api/merge` gets `colors` through the same builder.

- [ ] **Step 4: Run the whole suite**

Run: `uv run --no-sync poe test`
Expected: PASS.

- [ ] **Step 5: Commit** — `feature: #48 - diagram colours in the API payload`

### Task 5: Canvas in the configured colours (light mode)

**Files:**
- Modify: `frontend/src/api.ts` (`DiagramColors` interface, `Diagrams.colors`)
- Modify: `frontend/src/components/DiagramCanvas.vue` (root `<div>`: class `erd-diagram`, inline `--brand-*` variables from `diagrams.colors`)
- Modify: `frontend/src/style.css` (role variables, light-mode mapping)
- Modify: `frontend/src/components/BoxNode.vue` (styles use the role variables)

**Interfaces:**
- Consumes: `colors` from Task 4 (`accent, header, headerText, background, enumHeader, enumTitle`).
- Produces: CSS variables `--erd-primary`, `--erd-header`, `--erd-header-text`, `--erd-box-bg`, `--erd-enum-header`, `--erd-enum-title`.

- [ ] **Step 1: Define the role variables in `style.css`**: under `:root` / `.dark` today's tokens as fallbacks (`--erd-header: var(--ui-bg-accented)`, `--erd-header-text` / `--erd-enum-title: var(--ui-text-highlighted)`, `--erd-box-bg: var(--ui-bg)`, `--erd-enum-header: color-mix(in oklab, var(--erd-primary) 22%, var(--ui-bg))`); then `html:not(.dark) .erd-diagram { --erd-primary: var(--brand-accent); --erd-header: var(--brand-header); … }` so the API values apply in light mode only.

- [ ] **Step 2: Switch `BoxNode.vue`**: `.box__body` → `--erd-box-bg`, `.box__header` → `--erd-header`, `.box--enum .box__header` → `--erd-enum-header`; split `.box__title, .box__name`: `.box__title` → `--erd-header-text`, `.box--enum .box__title` → `--erd-enum-title`, `.box__name` keeps `--ui-text-highlighted`; foreign rules unchanged.

- [ ] **Step 3: Typecheck and build**

Run: `npm --prefix frontend run typecheck && uv run poe frontend`
Expected: no errors; build written to `src/erdify_studio/_static/`.

- [ ] **Step 4: Check in the browser** (a scratch project with `accent = "#4150aa"`, `header = "#192346"`, `background = "#fdf6e3"`, `erdify-studio open --no-browser`):
  - light mode: navy entity headers with white titles, enum headers light with dark titles, cream box bodies, indigo PK badges; **Download SVG** looks the same;
  - dark mode: today's dark look;
  - edit `header` in the pyproject → canvas updates within about a second;
  - no colours configured → canvas looks as on `main`.

- [ ] **Step 5: Commit** — `feature: #48 - canvas in the configured colours`

### Task 6: Docs and changelog

**Files:**
- Modify: `docs/configuration.md` (new section for `[tool.erdify-studio.colors]`)
- Modify: `docs/usage/export.md` (colour changes make SVGs outdated)
- Modify: `CHANGELOG.md` (`[Unreleased]` → Added)

- [ ] **Step 1: Write the docs**: the four keys with role and default (table), `#rrggbb` format, the `header_text` contrast rule, the dark-`background` warning, light mode only on the canvas, the devsuit example (`accent = "#4150aa"`, `header = "#192346"`, `header_text = "#ffffff"`); in `export.md`: changing colours → `check` reports outdated SVGs until the next export or Save. Link #67 / #68 as "not yet".

- [ ] **Step 2: Build the docs strictly**

Run: `uv run --group docs poe docs`
Expected: `Documentation built`, no warnings.

- [ ] **Step 3: Commit** — `docs: #48 - diagram colours`
