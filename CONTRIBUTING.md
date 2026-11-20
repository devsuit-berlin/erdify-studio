# Contributing to erdify-studio

Thank you for considering a contribution. Please be respectful and constructive —
see the [Code of Conduct](CODE_OF_CONDUCT.md).

## Prerequisites

- Python 3.11 or higher (CI tests 3.11–3.15)
- [uv](https://docs.astral.sh/uv/)
- Node 22.12+ — only to work on the frontend; users of the package never need it

## Setup

```bash
uv sync --group hooks
uv run pre-commit install
```

## Everyday commands

```bash
uv run poe test         # tests with the coverage gate (90 %)
uv run poe lint         # ruff + ruff format --check + mypy (strict)
uv run poe format       # format
uv run poe frontend     # build the frontend into src/erdify_studio/_static
uv run poe build        # sdist + wheel into dist/ (run `poe frontend` first)
uv run poe check-wheel  # check the wheel ships the frontend and the CLI
```

## Architecture in one paragraph

All logic is Python: loading the schema through erdify's public API, the layout file,
`check`, `place --auto` and the SVG export. The browser (Vue 3 + Vite, in `frontend/`)
only displays the diagram and sends position changes back. That keeps `check`,
`place --auto` and `export` usable without the UI and deterministic in CI.

## Frontend

```bash
cd frontend
npm ci
npm run dev        # Vite dev server
npm run build      # type-check + build into ../src/erdify_studio/_static
```

The build output is gitignored. CI builds it before `uv build`, and the wheel ships it.

## Pull requests

- One issue per PR; reference it (`Closes #12`).
- Tests for new behaviour, including the error paths.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Code conventions: [`docs/styleguide/python.md`](docs/styleguide/python.md).
- English everywhere: code, comments, docs, commits, PRs.

## Releases

Maintainers publish a GitHub release with a `vX.Y.Z` tag; the `Publish to PyPI`
workflow builds the frontend and the wheel and publishes through PyPI Trusted
Publishing behind the gated `pypi` environment. The version comes from the tag.
