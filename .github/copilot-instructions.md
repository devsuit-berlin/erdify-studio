# Agent Instructions — erdify-studio

Repo-wide agent instructions; `AGENTS.md` links to this file (a copy on Windows) and `CLAUDE.md` imports it.

## Project

erdify-studio: arrange erdify ERDs by drag and drop, commit the layout, check it in CI.
A Python package (`src/` layout, Python >= 3.11, tests in `tests/`) plus a Vue 3 + Vite
frontend in `frontend/`, built into `src/erdify_studio/_static/` (gitignored) and shipped
in the wheel.

- **All logic is Python** (schema loading via erdify's public API, layout file, `check`,
  `place --auto`, SVG export). The browser only displays and sends positions back.
- **Never re-implement erdify's parsing or edges** — use `erdify.load_project`,
  `erdify.diagram_edges` and `EntityInfo`. Divergence from erdify's model is a bug.
- The server binds to 127.0.0.1 only; no outbound network, no CDN assets.

## Tooling (non-negotiable)

- **Tests:** `uv run poe test` — never bare `pytest`.
- **Lint/format:** `uv run poe lint` (ruff + mypy strict) / `uv run poe format`, also run
  by the pre-commit hooks. Coverage gate: 90 %.
- **Frontend:** `npm --prefix frontend run build` (vue-tsc + Vite); `uv run poe frontend`
  installs and builds it.
- **Git hooks:** `pre-commit` (run `pre-commit install` once). No Husky.

## Path-scoped instructions

Stack-specific rules live in `.github/instructions/*.instructions.md` — open the
matching file before working in the package. `CLAUDE.md` imports all of them.

| File | Applies to |
| ---- | ---------- |
| `.github/instructions/python-lib.instructions.md` | `src/`, `tests/` |

## Conventions

- **English everywhere:** all code, comments, identifiers, docs, README, commit
  messages, PR titles/descriptions and CHANGELOG entries are written in English.
- `docs/styleguide/python.md` is the authoritative, fuller reference. Prefer the
  established patterns of the package.
- **Keep this file lean.** Copilot code review stops reviewing once the instructions
  it loads for a PR exceed ~100,000 characters. Add a stack- or area-specific rule
  to the matching `.github/instructions/*.instructions.md` file (or a new one with a
  narrow `applyTo`, imported in `CLAUDE.md`); `scripts/check_instructions.py` enforces it.
