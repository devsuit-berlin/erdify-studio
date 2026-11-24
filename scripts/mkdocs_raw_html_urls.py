"""MkDocs hook: resolve relative ``src``/``srcset`` URLs in raw HTML for the page's URL.

MkDocs rewrites relative links and images written in Markdown, but not raw HTML
(``<img>``, ``<picture><source srcset>``). With directory URLs ``docs/brand.md`` is
served at ``brand/``, so ``src="assets/x.svg"`` would load ``brand/assets/x.svg``.
This hook rewrites those URLs the way MkDocs rewrites Markdown links, so the same HTML
works on GitHub (relative to the file) and on the docs site. A relative URL that names
no file in ``docs/`` is a warning, so ``mkdocs build --strict`` fails on it.

Enabled via ``hooks:`` in ``mkdocs.yml``.
"""

from __future__ import annotations

import logging
import posixpath
import re
from typing import Any

from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page
from mkdocs.utils import get_relative_url

log = logging.getLogger(f"mkdocs.hooks.{__name__}")

# Attribute values in the rendered HTML; code blocks are escaped (&quot;), so they don't match.
_ATTR = re.compile(r'(?P<attr>\b(?:src|srcset))="(?P<value>[^"]+)"')


def _is_relative(url: str) -> bool:
    return not (url.startswith(("/", "#", "data:", "mailto:")) or "://" in url)


def _resolve(url: str, page: Page, files: Files) -> str:
    if not _is_relative(url):
        return url
    path, _, fragment = url.partition("#")
    target = posixpath.normpath(posixpath.join(posixpath.dirname(page.file.src_uri), path))
    file = files.get_file_from_path(target)
    if file is None:
        # Already rewritten by MkDocs (a Markdown image, relative to the page URL),
        # or a broken path.
        from_url = posixpath.normpath(posixpath.join(posixpath.dirname(page.url), path))
        if files.get_file_from_path(from_url) is None:
            log.warning(f"{page.file.src_uri}: raw HTML URL {url!r} names no file in docs/")
        return url
    resolved = get_relative_url(file.url, page.url)
    return f"{resolved}#{fragment}" if fragment else resolved


def _resolve_srcset(value: str, page: Page, files: Files) -> str:
    # "a.svg, b.svg 2x": each candidate is a URL plus an optional descriptor.
    candidates = []
    for candidate in value.split(","):
        url, _, descriptor = candidate.strip().partition(" ")
        resolved = _resolve(url, page, files)
        candidates.append(f"{resolved} {descriptor}".rstrip())
    return ", ".join(candidates)


def on_page_content(html: str, *, page: Page, config: Any, files: Files) -> str:
    def rewrite(match: re.Match[str]) -> str:
        value = match["value"]
        if match["attr"] == "srcset":
            new = _resolve_srcset(value, page, files)
        else:
            new = _resolve(value, page, files)
        return f'{match["attr"]}="{new}"'

    return _ATTR.sub(rewrite, html)
