# Installation

```bash
pip install erdify-studio          # no Node, no database, no browser engine needed
pip install "erdify-studio[sql]"   # to read SQL DDL (pulls in erdify[sql])
```

Or run it without installing, with [uv](https://docs.astral.sh/uv/):

```bash
uvx erdify-studio                                   # open the canvas
uvx --from "erdify-studio[sql]" erdify-studio check # with SQL DDL support
```

erdify-studio needs Python 3.11 or newer and depends on
[erdify](https://erdify.devsuit.io/installation/) 1.9 or newer (below 2), installed with
it. The browser canvas is built into the wheel, so no Node is needed.
`erdify-studio --version` prints both versions.

Source checkout (contributors): see
[CONTRIBUTING.md](https://github.com/devsuit-berlin/erdify-studio/blob/main/CONTRIBUTING.md).
