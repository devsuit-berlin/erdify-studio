# Claude Code Instructions

Claude Code loads the files below at session start. `.github/copilot-instructions.md` is the repo-wide part (also served to Copilot, and to other agents via `AGENTS.md` — a link to it, or a copy on Windows); the `.github/instructions/*.instructions.md` files are path-scoped for Copilot code review and imported here in full. Every instructions file must be listed — `scripts/check_instructions.py` enforces it.

@.github/copilot-instructions.md
@.github/instructions/python-lib.instructions.md

## Checks

The lint and test commands of this project.

| Part | Lint | Tests |
| --- | --- | --- |
| `src/`, `tests/` | `uv run --no-sync poe lint` | `uv run --no-sync poe test` |
| `frontend/` | `npm --prefix frontend run typecheck` | — (no frontend tests yet) |

- `--no-sync` keeps `uv run` from installing into `.venv` (a missing environment means: run `uv sync` yourself first).
- Narrowing: Python `uv run --no-sync poe test <path>` or `uv run --no-sync poe test -k <word>` (no `--`).
- `pre-commit` rewrites files — run it yourself (`pre-commit run --files <changed>`).
