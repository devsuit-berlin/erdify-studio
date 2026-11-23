# Place new tables without the canvas

```bash
erdify-studio place --auto [path]
```

Fixes what `check` reports, without opening the browser:

- An entity, foreign box or enum without a position goes next to a placed box it has a
  relationship with, or for an enum an entity using it (right, below, left or above —
  the first free spot), otherwise into the first free slot of a grid right of the
  diagram.
- Boxes that already have a position never move.
- Entries and diagrams that no longer exist are removed (one line each).
- Without a layout file it creates one with every diagram.

The result is deterministic — run twice, same bytes — and the file is only written when
something changed. Exit codes: 0 on success, 2 like `check` when something cannot be
read (a layout file that is not valid, e.g. with git conflict markers, is never
overwritten).
