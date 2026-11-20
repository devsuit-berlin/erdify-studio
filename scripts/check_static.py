"""Check that the built frontend loads nothing from the network.

Usage: ``python scripts/check_static.py [DIR]`` (default: ``src/erdify_studio/_static``).
The canvas must work offline and leak nothing: no CDN, no icon or font service. Any
absolute or protocol-relative URL in a built file is reported, except XML namespace
names, which are identifiers and never fetched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT = Path(__file__).parent.parent / "src" / "erdify_studio" / "_static"

#: Strings that look like URLs but are never fetched.
ALLOWED = frozenset(
    {
        "http://www.w3.org/2000/svg",  # SVG namespace
        "http://www.w3.org/1999/xlink",  # XLink namespace
        "http://www.w3.org/XML/1998/namespace",  # xml: prefix
        "http://www.w3.org/1999/xhtml",  # XHTML namespace
        "http://www.w3.org/1998/Math/MathML",  # MathML namespace (Vue's runtime)
        "https://tailwindcss.com",  # Tailwind's license banner comment
    }
)
#: Prefixes of URLs that are only shown as text, never fetched.
ALLOWED_PREFIXES = ("https://vuejs.org/error-reference/",)  # in Vue's error messages

# A scheme or a protocol-relative "//", then a host with a dot.
_URL = re.compile(r"""(?:\bhttps?:)?//[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+[^\s"'`()<>\\]*""")


def problems(directory: Path) -> list[str]:
    """Return one line per external URL in the files under ``directory``."""
    if not directory.is_dir():
        return [f"{directory}: missing (run `poe frontend` first)"]
    found: list[str] = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        text = path.read_bytes().decode("utf-8", errors="ignore")
        urls = {m.group(0) for m in _URL.finditer(text)} - ALLOWED
        for url in sorted(u for u in urls if not u.startswith(ALLOWED_PREFIXES)):
            found.append(f"{path.relative_to(directory).as_posix()}: external URL {url}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        print("usage: check_static.py [DIR]", file=sys.stderr)
        return 2
    directory = Path(argv[0]) if argv else DEFAULT
    found = problems(directory)
    for problem in found:
        print(problem, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
