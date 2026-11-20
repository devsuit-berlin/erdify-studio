# Python Styleguide

Conventions for this package — module layout, public API, typing, errors, logging.

This is a library / CLI package: there is no web, ORM or request layer here, and none should
appear without a deliberate decision.

## Package Layout

```
src/<package>/        # importable package
  __init__.py         # the public API — nothing else re-exports
  ...
tests/
pyproject.toml
```

- `src/` layout, not a top-level package directory: it makes the installed package the one
  under test, so a missing entry in `pyproject.toml` fails in CI instead of passing
  locally against the source tree.
- Modules are named for what they contain, not for their layer. `parsing.py`, not
  `utils.py` — a `utils` module has no boundary and grows without limit.
- Nothing imports upward. If two modules need each other, the shared piece belongs in a
  third.

## Public API

`__init__.py` is the contract. Everything else is an implementation detail.

```python
from .parsing import parse_manifest
from .types import Manifest

__all__ = ["Manifest", "parse_manifest"]
```

- Prefix internal modules and helpers with `_` so the boundary is visible at the call site.
- `__all__` is not decoration: it defines what `from <pkg> import *` gives, and it is the
  list you cannot change without a breaking release.
- Renaming or removing anything re-exported here is a **major** bump. Adding is minor.
  Keep the surface small so you keep the freedom to refactor behind it.

## Typing

- Annotate every public function — parameters and return. A public function without
  annotations is untestable by the type checker and undocumented for callers.
- Prefer precise types over permissive ones: `Sequence[str]` when you only iterate,
  `Iterable[str]` when you consume once, `list[str]` only when you mutate.
- Accept the general type, return the concrete one: take `Iterable[Item]`, return
  `list[Item]`. Callers can then rely on what comes back.
- Use `TypedDict` / `dataclass` / `NamedTuple` instead of passing bare dicts across module
  boundaries. A dict has no contract and no autocompletion.
- `Any` is an escape hatch that turns off checking for everything it touches — narrow it at
  the boundary rather than letting it spread inward.

## Errors

- Define one package-level base exception and derive from it, so callers can catch
  everything from this package with one `except`:

```python
class ManifestError(Exception):
    """Base for all errors raised by this package."""


class ManifestSyntaxError(ManifestError):
    """The manifest could not be parsed."""
```

- Raise the most specific type you have; catch the most general one you can handle.
- A library does not decide how failures are presented. Raise — do not print, do not
  `sys.exit()`, do not log an error and return `None`. Only the CLI entry point turns an
  exception into a message and an exit code.
- Never swallow an exception silently. `except Exception: pass` hides the bug you will be
  asked about later.
- Include the offending value in the message (`f"unknown key {key!r} at line {line}"`) —
  `!r` so an empty string or trailing whitespace is visible.

## CLI

- The CLI is a thin shell over the library: parse arguments, call the API, format the
  result, choose an exit code. Business logic lives in the package and is importable
  without it.
- Exit non-zero on failure, and write errors to stderr — a pipeline downstream depends on
  both.
- Keep the argument surface small and stable; it is as much a public contract as
  `__init__.py`.

## Testing

Run tests via `uv run poe test` — never bare `pytest` / `python -m pytest`.

- Test the public API through its import path, the way a consumer uses it. A test that
  reaches into `_internal` pins an implementation detail and blocks refactoring.
- One assertion subject per test; parametrize over inputs rather than looping inside a test
  so a failure names the case.
- Cover the error paths, not just the happy one — the exception type and message are part
  of the contract.
- Follow the existing patterns in `tests/`.

## Logging

A library configures no handlers and sets no level. Get a module logger and leave the
configuration to the application:

```python
logger = logging.getLogger(__name__)
```

`logging.basicConfig()` belongs in the CLI entry point, never in library code — a library
that configures logging hijacks it for every consumer.

### Always Use f-strings

Use f-strings for all log messages. Do not use `%`-style formatting or `.format()`.

```python
# ✅ DO
logger.info(f"Item {item_id} created for owner {owner_id}")
logger.warning(f"External service rate limited. Request ID: {request_id}")
logger.error(f"Failed to delete user_id={user.id}", exc_info=True)

# ❌ DON'T
logger.info("Item %s created for owner %s", item_id, owner_id)
logger.info("Item {} created".format(item_id))
```

### Log Levels

> **`warning` and `error` both trigger alerts.** Only use them when someone should be notified.

| Level | When to Use | Alert | Examples |
| ----- | ----------- | ----- | -------- |
| `info` | Normal operations, progress tracking, recoverable skips | No | Batch progress, successful deletions, state transitions |
| `warning` | Situations that need attention but aren't critical | **Yes** | Rate limit on a payment, unexpected data that may indicate a bug |
| `error` | Failures that need investigation, data loss risk | **Yes** | Payment processing failures, unrecoverable state corruption. Always include `exc_info=True` |

**Rules of thumb:**

- If the system can recover and move on without human attention → `info`
- If someone should look at it soon but the system continues → `warning`
- If data may be lost or a destructive operation fails → `error` with `exc_info=True`
- Transient/expected failures in batch jobs → `info`, not `warning` — avoid alert noise
- Never use `warning` for expected/benign skips — use `info`

## Docstrings

### Class Docstrings

```python
class Manifest:
    """
    Parsed representation of a manifest file.

    Immutable once constructed; use `parse_manifest` to build one rather than
    instantiating directly.
    """
```

### Method Docstrings

```python
def parse_manifest(text: str) -> Manifest:
    """
    Parse manifest text.

    Args:
        text: Raw manifest contents

    Returns:
        Parsed manifest

    Raises:
        ManifestSyntaxError: If the text is not valid manifest syntax
    """
```
