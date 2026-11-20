# Security Policy

## Supported Versions

We release security fixes for the latest published version only. Always run the
most recent release.

| Version        | Supported |
| -------------- | --------- |
| Latest release | Yes       |
| Older          | No        |

## Security Model

erdify-studio reads your models through [erdify](https://github.com/devsuit-berlin/erdify)'s
public Python API, so erdify's security model applies to the parsing step: no code
from the files it reads is executed or imported, no database connection is opened.
See [erdify's security policy](https://github.com/devsuit-berlin/erdify/blob/main/SECURITY.md).

On top of that, erdify-studio:

- serves its browser UI from a local server bound to **127.0.0.1 only** — it is not
  reachable from other machines;
- writes only the layout file and, when `export_dir` is set, the exported diagrams —
  both at paths you configure. It never deletes files;
- makes no outbound network requests. The frontend is shipped inside the wheel and
  loads no code from a CDN;
- needs no Node, browser engine or other runtime beyond Python on your machine.

`check`, `place --auto` and `export` run without the UI and without network access,
so they are safe to run in CI.

### What is not covered

- What you do with exported diagrams: they contain your table, column and enum names,
  which can themselves be sensitive.
- The `sql` extra adds [sqlglot](https://github.com/tobymao/sqlglot) through
  `erdify[sql]`; see erdify's policy for that trust boundary.

## Reporting a Vulnerability

Please report vulnerabilities privately.

1. **Do not** open a public GitHub issue for a security vulnerability.
2. Email [tech@devsuit.de](mailto:tech@devsuit.de).
3. Include a description, steps to reproduce, the potential impact, and any
   suggested fix.

### What to expect

erdify-studio is maintained by a small team, so the times below are what we aim for
rather than a guaranteed service level:

- **Acknowledgment**: usually within a few business days.
- **Initial assessment**: once we have reproduced it, we tell you whether we
  consider it a vulnerability and roughly how we plan to handle it.
- **Fix**: as fast as the severity warrants.

If you have not heard back within a week, please send a reminder.

### After reporting

1. We investigate and validate the issue.
2. We work on a fix.
3. We coordinate disclosure timing with you.
4. We credit you in the release notes, unless you prefer to stay anonymous.

## Security Checklist for Contributors

- [ ] no `eval()`, `exec()` or `__import__()`
- [ ] the server binds to 127.0.0.1 only
- [ ] no file writes outside the configured layout file and export directory
- [ ] no outbound network requests, no assets loaded from a CDN
- [ ] test coverage for edge cases and malformed input
