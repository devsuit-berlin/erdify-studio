# 🐍 erdify-studio

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9)
![License](https://img.shields.io/badge/license-MIT-green)



Interactive, persistent ERD layouts for [erdify](https://github.com/devsuit-berlin/erdify).

## Setup

```bash
uv sync
uv run poe test
```

## Build & release

```bash
poe build      # sdist + wheel into dist/
```

Versions come from git tags (`hatch-vcs`) — no manual bumping. Tag and push to release:

```bash
git tag v0.1.0 && git push --tags
```
A tag push triggers `.github/workflows/release.yml`, which builds and publishes to
**PyPI via Trusted Publishing** (OIDC — no API token). Configure this repo as a
publisher on pypi.org first.

## License

MIT
