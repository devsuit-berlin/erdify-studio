# Agent Instructions — erdify-studio

Repo-wide agent instructions; `AGENTS.md` links to this file (a copy on Windows) and `CLAUDE.md` imports it.

## Project

A Python package in `src/` layout, tests in `tests/`.

## Tooling (non-negotiable)

- **Tests:** `uv run poe test` — never bare `pytest`.
- **Lint/format:** `uv run poe lint` / `uv run poe format` (ruff, also run by the
  pre-commit hooks).
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
