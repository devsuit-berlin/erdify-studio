"""Guard the AI instruction files against silent drift and size creep.

Copilot code review refuses to run at all once the instructions it loads for a
PR exceed ~100,000 characters (inferred, not documented by GitHub). It always
loads `.github/copilot-instructions.md` (and the root `AGENTS.md`, a symlink to
it), plus the UNION of every `.github/instructions/*.instructions.md` whose
`applyTo` matches ANY changed file, read from the PR's head branch. (The budgets
count the root once: the observed limit was measured that way.) Claude Code
reads none of the path-scoped files on its own, so `CLAUDE.md` imports every
one of them.

Checks (always):
1. Every path-scoped file is imported in `CLAUDE.md`, and every import exists.
2. Every path-scoped file declares `applyTo`, and every glob matches at least
   one tracked or new (untracked, not ignored) file (a renamed or moved module
   silently drops its rules from Copilot's review otherwise).
3. The root file stays within its budget.
4. Every Claude Code command hook (`.claude/settings.json`, frontmatter of
   `.claude/agents/**/*.md` and `.claude/skills/**/SKILL.md`) runs a script
   under `.claude/hooks/` that exists, through the fail-closed wrapper. Claude
   Code blocks only on exit 2, so a bare `bash "<script>"` lets the tool call
   run when the script is missing (127).

With `--base REF` (CI on a pull request): size the union loaded for the files
changed since REF. Over budget, `--warn` emits a GitHub warning instead of
failing: the cost is a skipped Copilot review, which must not block a merge.

With `--replay LIST...`: print the union size for each file list (one path per
line), to tune the globs against real PRs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT_FILE = ".github/copilot-instructions.md"
SCOPED_DIR = ".github/instructions"
CLAUDE_MD = "CLAUDE.md"
CLAUDE_SETTINGS = ".claude/settings.json"
CLAUDE_AGENTS = ".claude/agents"
CLAUDE_SKILLS = ".claude/skills"

# The only accepted hook command: run a script under `.claude/hooks/` and turn every
# exit other than 0 and 2 (missing script → 127, unset variable, ...) into a block.
HOOK_WRAPPER = re.compile(
    r'^bash "\$CLAUDE_PROJECT_DIR/(\.claude/hooks/[A-Za-z0-9_.-]+\.sh)"(?: [A-Za-z0-9_-]+)*; '
    r'rc=\$\?; \[ "\$rc" -eq 0 \] && exit 0; \[ "\$rc" -eq 2 \] \|\| '
    r'echo "Blocked: \1 did not run cleanly \(exit \$rc\) — failing closed" >&2; exit 2$'
)

ROOT_BUDGET = 30_000
PR_BUDGET = 98_000  # headroom below the ~100,000 Copilot limit


def git_lines(*args: str, cwd: Path | None = None) -> list[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.splitlines()


# Resolve from git, not from this file's location, so the script works wherever
# it is vendored.
ROOT = Path(git_lines("rev-parse", "--show-toplevel")[0])


def glob_to_regex(glob: str) -> re.Pattern[str]:
    """Translate an `applyTo` glob (`**`, `*`, `?`) into an anchored regex."""
    out = ""
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        elif glob[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile(f"^{out}$")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def frontmatter(text: str) -> tuple[str | None, str | None]:
    """Return a Markdown file's YAML frontmatter (None if it has none), plus a problem.

    Delimiters are matched loosely (BOM, CRLF, trailing whitespace, closing `---` at EOF),
    and a block that opens but never closes is reported: a guard that skipped frontmatter
    it did not recognise would skip the hooks in it.
    """
    lines = text.removeprefix("\ufeff").replace("\r\n", "\n").split("\n")
    if lines[0].rstrip() != "---":
        return None, None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            # The body is a YAML stream of its own and may open with a BOM too; anywhere
            # else a BOM would hide a key (`\ufeffhooks:`) from the line matching below.
            body = "\n".join(lines[1:i]).removeprefix("\ufeff")
            if "\ufeff" in body:
                return None, "frontmatter contains a byte order mark (U+FEFF)"
            return body, None
    return None, "frontmatter opened with `---` is never closed"


def apply_to(text: str) -> list[str] | None:
    """Return the `applyTo` globs of a frontmatter block, or None if absent."""
    body, _ = frontmatter(text)
    if body is None:
        return None
    line = re.search(r"^applyTo:\s*(.+?)\s*$", body, flags=re.MULTILINE)
    if not line:
        return None
    return [g.strip() for g in line.group(1).strip("\"'").split(",") if g.strip()]


# The frontmatter parser below reads a deliberately narrow YAML subset and reports
# everything else: a key spelled with an escape (`"comm\u0061nd":`), an explicit key
# (`? command`), flow style, an anchor or a merge key is still `command` / `hooks` to a
# YAML parser, so skipping what a regex does not recognise would let a bare, fail-open
# registration through. No YAML library: the guard ships into every generated project
# and runs on a bare interpreter.

# A top-level key: plain (no escapes exist there; it may not start with an indicator or
# `<`, as in the merge key `<<`), single-quoted (only escape `''`) or double-quoted
# without escapes.
TOP_KEY = re.compile(
    r"""(?P<key>[^\s'"?{}\[\],&*!|<>%@`#:-][^:#]*?|'(?:[^']|'')*'|"[^"\\]*")"""
    r"""[ \t]*:(?:[ \t]+(?P<value>.*))?$"""
)
# One line of the `hooks:` block: `[- ]key:` with a plain key and a value that is empty,
# quoted on that line, or a plain scalar that cannot start a block scalar, flow
# collection, anchor, alias or tag.
HOOK_LINE = re.compile(
    r""" *(?:- +)?(?P<key>[A-Za-z_][A-Za-z0-9_-]*):"""
    r"""(?: +(?P<value>'(?:[^']|'')*'|"[^"\\]*"|[A-Za-z0-9_.][A-Za-z0-9_.|*/() -]*?))? *"""
    r"""(?: #.*)?$"""
)


ASYNC_PROBLEM = "hook must not be `async`: an async hook cannot block, so it is not fail-closed"


def unquote_key(key: str) -> str:
    if key.startswith("'"):
        return key[1:-1].replace("''", "'")
    return key.strip('"')


def frontmatter_hook_commands(text: str) -> tuple[list[str], list[str]]:
    """Return the hook commands of one Markdown file's YAML frontmatter, plus problems.

    Only the top-level `hooks:` block is read, so other `command` keys (an agent's own
    `mcpServers`) are not hook registrations. Every top-level line must be a recognisable
    `key:` (else it could be a `hooks` key in disguise), and every line of the `hooks:`
    block must be plain block style (`HOOK_LINE`). A `command` value must be single-quoted:
    YAML's only escape there is `''`, so the text is unambiguous.
    """
    body, problem = frontmatter(text)
    if body is None:
        return [], [problem] if problem else []
    commands: list[str] = []
    problems: list[str] = []
    in_hooks = False
    seen_key = False
    for line in body.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # An indented root mapping would put every key, `hooks` included, off column 0.
        if not seen_key and line[0].isspace():
            problems.append("frontmatter keys must start at column 0")
        seen_key = True
        # A column-0 line other than a `- ` item starts the next top-level key.
        if not line[0].isspace() and not re.match(r"-(?: |$)", line):
            top = TOP_KEY.match(line)
            if not top:
                problems.append(
                    f"frontmatter line is not a plain top-level `key:` "
                    f"(cannot tell whether it registers hooks): {line}"
                )
                in_hooks = False
                continue
            in_hooks = unquote_key(top.group("key")) == "hooks"
            value = (top.group("value") or "").strip()
            if in_hooks and value and not value.startswith("#"):
                problems.append("`hooks:` must be a block mapping (no inline value)")
            continue
        if not in_hooks:
            continue
        hook = HOOK_LINE.fullmatch(line)
        if not hook:
            problems.append(
                f"`hooks:` block must be plain block-style YAML "
                f"(`key: value` per line, no flow style or escapes): {line.strip()}"
            )
            continue
        # An async hook runs in the background and cannot block the tool call: it is never
        # fail-closed. Only a plain `false` is allowed (a quoted 'false' is a truthy string).
        if hook.group("key") == "async":
            if hook.group("value") != "false":
                problems.append(ASYNC_PROBLEM)
            continue
        if hook.group("key") != "command":
            continue
        value = hook.group("value") or ""
        if not re.fullmatch(r"'(?:[^']|'')*'", value):
            problems.append("hook command must be a single-quoted YAML string")
            continue
        commands.append(value[1:-1].replace("''", "'"))
    return commands, problems


def settings_hook_commands(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return `(event, command)` for every command hook in a `settings.json`, plus problems.

    A shape the guard cannot walk (not JSON, `hooks` not an object, a non-string
    `command`, ...) is reported, not skipped: it could hide an unwrapped hook.
    """
    try:
        settings = json.loads(text)
    except json.JSONDecodeError as e:
        return [], [f"not valid JSON: {e}"]
    if not isinstance(settings, dict):
        return [], ["top level must be a JSON object"]
    hooks = settings.get("hooks")
    if hooks is None:  # absent or null: no hooks; any other non-object is reported
        hooks = {}
    if not isinstance(hooks, dict):
        return [], ["`hooks` must be an object"]
    commands: list[tuple[str, str]] = []
    problems: list[str] = []
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            problems.append(f"`hooks.{event}` must be a list")
            continue
        for entry in entries:
            inner = entry.get("hooks") if isinstance(entry, dict) else None
            if not isinstance(inner, list):
                problems.append(f"`hooks.{event}[]` must be an object with a `hooks` list")
                continue
            for hook in inner:
                if not isinstance(hook, dict):
                    problems.append(f"`hooks.{event}[].hooks[]` must be an object")
                elif hook.get("type") == "command" or "command" in hook:
                    command = hook.get("command")
                    if hook.get("type") != "command":
                        problems.append(f"{event}: a hook with a `command` must be `type: command`")
                    elif "async" in hook and hook["async"] is not False:
                        problems.append(f"{event}: {ASYNC_PROBLEM}")
                    elif isinstance(command, str):
                        commands.append((event, command))
                    else:
                        problems.append(f"{event}: hook command must be a string")
    return commands, problems


def hook_commands() -> tuple[list[tuple[str, str]], list[str]]:
    """Collect `(source, command)` for every Claude Code command hook, plus parse errors.

    Sources: `.claude/settings.json`, every agent under `.claude/agents/` (nested
    directories included) and every `.claude/skills/**/SKILL.md` — skills can register
    frontmatter hooks too.
    """
    commands: list[tuple[str, str]] = []
    errors: list[str] = []
    if (ROOT / CLAUDE_SETTINGS).is_file():
        found, problems = settings_hook_commands(read(CLAUDE_SETTINGS))
        errors += [f"{CLAUDE_SETTINGS}: {p}" for p in problems]
        commands += [(f"{CLAUDE_SETTINGS} ({event})", c) for event, c in found]
    files: list[Path] = []
    for directory, pattern in ((CLAUDE_AGENTS, "*.md"), (CLAUDE_SKILLS, "SKILL.md")):
        if (ROOT / directory).is_dir():
            files += sorted((ROOT / directory).rglob(pattern))
    for file in files:
        path = file.relative_to(ROOT).as_posix()
        found, problems = frontmatter_hook_commands(read(path))
        errors += [f"{path}: {p}" for p in problems]
        commands += [(path, c) for c in found]
    return commands, errors


def check_hooks() -> list[str]:
    """Check 4: every command hook runs an existing `.claude/hooks/` script, fail-closed."""
    commands, errors = hook_commands()
    for source, command in commands:
        wrapped = HOOK_WRAPPER.match(command)
        if not wrapped:
            errors.append(
                f"{source}: hook command is not wrapped to fail closed "
                f"(see HOOK_WRAPPER in scripts/check_instructions.py): {command}"
            )
        elif not (ROOT / wrapped.group(1)).is_file():
            errors.append(f"{source}: hook script {wrapped.group(1)} does not exist")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="git ref to diff against (PR budget check)")
    parser.add_argument(
        "--warn",
        action="store_true",
        help="PR budget: warn, do not fail",
    )
    parser.add_argument("--replay", nargs="*", default=[], help="file lists to size")
    args = parser.parse_args()

    errors: list[str] = []
    # Include new, not-yet-staged files so a freshly added service's glob is not "dead".
    tracked = git_lines(
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        cwd=ROOT,
    )

    scoped_paths = (ROOT / SCOPED_DIR).glob("*.instructions.md")
    scoped = sorted(p.relative_to(ROOT).as_posix() for p in scoped_paths)
    imports = re.findall(r"^@(\S+)\s*$", read(CLAUDE_MD), flags=re.MULTILINE)
    for path in [ROOT_FILE, *scoped]:
        if path not in imports:
            errors.append(f"{CLAUDE_MD} does not import {path}")
    for path in imports:
        if not (ROOT / path).is_file():
            errors.append(f"{CLAUDE_MD} imports missing file {path}")

    sizes = {path: len(read(path)) for path in scoped}
    patterns: dict[str, list[re.Pattern[str]]] = {}
    for path in scoped:
        globs = apply_to(read(path))
        if not globs:
            errors.append(f"{path} has no applyTo frontmatter")
            continue
        patterns[path] = []
        for glob in globs:
            if "{" in glob or "}" in glob:
                errors.append(
                    f"{path}: brace glob '{glob}' is not supported, list each path",
                )
                continue
            regex = glob_to_regex(glob)
            if not any(regex.match(f) for f in tracked):
                errors.append(f"{path}: applyTo glob '{glob}' matches no tracked file")
            patterns[path].append(regex)

    def activated(files: list[str]) -> set[str]:
        return {
            path
            for path, regexes in patterns.items()
            if any(r.match(f) for f in files for r in regexes)
        }

    root_size = len(read(ROOT_FILE))
    if root_size > ROOT_BUDGET:
        errors.append(f"{ROOT_FILE} is {root_size:,} chars (budget {ROOT_BUDGET:,})")

    def union_size(files: list[str]) -> int:
        return root_size + sum(sizes[p] for p in activated(files))

    total = root_size + sum(sizes.values())
    print(f"Root: {root_size:,} chars; everything: {total:,} chars")

    for listing in args.replay:
        files = [f for f in Path(listing).read_text().splitlines() if f]
        print(f"{union_size(files):>8,}  {listing}")

    if args.base:
        changed = git_lines(
            "diff",
            "--name-only",
            "--no-renames",
            f"{args.base}...HEAD",
            cwd=ROOT,
        )
        size = union_size(changed)
        loaded = ", ".join(sorted(Path(p).name for p in activated(changed))) or "none"
        print(f"This PR loads {size:,} chars (root + {loaded})")
        if size > PR_BUDGET:
            message = (
                f"This PR loads {size:,} chars of instructions (budget {PR_BUDGET:,}); "
                "Copilot code review will likely refuse it. Narrow an applyTo or "
                "shorten a rule (link a doc for the detail)."
            )
            if args.warn:
                print(f"::warning title=Copilot instruction load::{message}")
            else:
                errors.append(message)

    errors.extend(check_hooks())

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
