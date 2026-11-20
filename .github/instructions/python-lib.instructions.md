---
applyTo: "src/**,tests/**"
---

# Python library

Path-scoped part of `.github/copilot-instructions.md` (loaded by Copilot for matching files;
imported into `CLAUDE.md`). `docs/styleguide/python.md` is authoritative for nuance.

- **Layout:** `src/` layout; modules named for what they contain (no `utils.py`); nothing
  imports upward. Prefix internal modules and helpers with `_`.
- **Public API:** `__init__.py` with `__all__` is the contract. Renaming or removing anything
  re-exported there is a major bump; keep the surface small.
- **Typing:** annotate every public function; accept the general type, return the concrete
  one; `dataclass`/`TypedDict` over bare dicts across modules; narrow `Any` at the boundary.
- **Errors:** one package-level base exception, specific subclasses. Library code raises —
  never prints, `sys.exit()`s or logs-and-returns-`None`; only the CLI entry point maps an
  exception to a message and exit code. Never swallow exceptions; include the offending
  value with `!r`.
- **Logging:** `logging.getLogger(__name__)`, no handlers or levels in library code
  (`basicConfig` only in the CLI); f-string messages; `warning`/`error` alert, so expected
  skips are `info`.
- **Tests:** `uv run poe test` — never bare `pytest`. Test through the public import path;
  parametrize over inputs; cover the error paths.
