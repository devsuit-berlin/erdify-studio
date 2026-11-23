# Group diagrams and foreign boxes (#6)

## Intent

A large warehouse doesn't read well as one overview. Next to the overview, studio
shows one smaller diagram per group (schema, Django app or module, per
`[tool.erdify-studio] group_by`). The user switches between them, arranges each one
and saves them all to `erdify-layout.json`, so `check` passes and the SVG export
(#8) can draw every diagram the way it was arranged.

What each diagram contains is already decided in Python and enforced by `check` and
`place --auto` (`diagram_contents` in `_check.py`): a group diagram shows its own
entities, a **foreign box** for every entity of another group connected to one of
them by an edge (either direction), and the drawn enums its own entities use. This
work makes that visible and editable in the browser.

## Goals (issue #6 acceptance criteria)

1. **Switch** — the user can switch between the overview and each group diagram.
2. **Content** — a group diagram shows the group's entities plus foreign boxes for
   entities of other groups it references or that reference it.
3. **Foreign box** — greyed out, name only; it opens that entity's group diagram.
4. **Own positions** — moving an entity in one diagram doesn't move it in another.

Plus, carried over from the overview (#5):

- Unplaced boxes in any diagram are placed like `place --auto` and marked NEW until saved.
- One **Save** (button or Ctrl/⌘+S) writes every diagram; afterwards `check` passes.
- Switching diagrams never loses unsaved positions (user decision: one Save for all).

## Non-goals

- Live reload on source changes (#7), SVG export (#8).
- Editing what a diagram contains (hiding boxes, custom groups) — content comes from
  `group_by` only.
- Per-diagram save or discard.

## Anti-goals

- Any diagram logic in the browser: which boxes, edges and enum links a diagram
  shows is computed in Python, the same function `check`, `place --auto` and the
  later SVG export use. The browser draws what it is sent.
- A save that writes diagrams read from different states of the models.

## Constraints

- All logic in Python; erdify's model via its public API only (`diagram_edges`,
  `enum_users`, `EntityInfo`) — never re-implemented.
- 127.0.0.1 only, per-run token, `Host`/`Origin` checks, no network from the page
  (unchanged from #5).
- Box geometry lives only in `_place.py`; the canvas draws the sizes the API sends.

## Approaches

| | Approach | Trade-off |
| --- | --- | --- |
| **1 (chosen)** | One payload with every diagram; one save with every diagram | Switching is instant and one Save is natural; every diagram comes from one read of the models, so the existing revision/conflict check carries over unchanged. Payload grows with the number of groups (hundreds of KB for large projects, on localhost). |
| 2 | Fetch each diagram when opened, cache in the browser | Smaller first load, but diagrams fetched at different times can come from different model states; one Save would then mix them, and conflict detection needs per-diagram revisions. |
| — (rejected) | Derive group diagrams in the browser from the overview payload | Breaks "all logic in Python"; would diverge from `check` and the SVG export. |

The user picked 1 (2026-11-23).

## Design

### API

`GET /api/overview` becomes **`GET /api/diagrams`**; `PUT /api/layout` takes every
diagram. The frontend ships in the same wheel, so there is no compatibility shim.

Response (`Diagrams` TypedDict in `_overview.py`, mirrored in `frontend/src/api.ts`):

```json
{
  "metrics": {...},
  "boxes": {
    "core.customers": {"kind": "entity", "title": "core.customers", "group": "core",
                        "width": 180, "height": 94, "rows": [...]},
    "enum:Status":    {"kind": "enum", "title": "Status", "group": null,
                        "width": 120, "height": 50, "rows": [...]}
  },
  "diagrams": [
    {"name": "_overview", "label": "Overview",
     "own": ["billing.invoices", "core.customers", "enum:Status"],
     "foreign": [],
     "positions": {"core.customers": [0, 0], ...},
     "new": ["enum:Status"],
     "edges": [{"from": "...", "to": "...", "fromEnd": {...}, "toEnd": {...},
                "kind": "foreign_key", "label": "customer_id"}],
     "enumLinks": [{"enum": "enum:Status", "entity": "billing.invoices"}]},
    {"name": "core", "label": "core", "own": ["core.customers"],
     "foreign": ["billing.invoices"], "foreignSizes": {"billing.invoices": [140, 28]},
     ...}
  ],
  "revision": "<sha256 or null>",
  "pending": {"placed": 3, "diagrams": 2, "dropped": 1, "created": false},
  "layoutPath": "erdify-layout.json",
  "projectPath": "."
}
```

- `boxes`: every entity and drawn enum **once**, keyed by layout key, with its full
  size; `group` is the entity's group diagram (null for enums and under
  `group_by = "none"`).
- A foreign box is drawn name-only, at the header-only size `place_layout` reserves
  for it (`_box(key, ())` in `_place.py`). The canvas computes no sizes, so each
  diagram entry carries `foreignSizes` (key → `[width, height]`) from that same
  function.
- `diagrams`: the overview first, then the groups sorted by name, `_default` last.
  `name` is the layout file's diagram name — `OVERVIEW` (`"_overview"`) for the
  overview, never a bare `"overview"`: a schema, app or module called `overview` is
  a legal group, and only `_overview` / `_default` are reserved. `label` is the name,
  except `"Overview"` for the overview and `"Ungrouped"` for `_default`.
  Under `group_by = "none"` there is only the overview.
- Per diagram, `positions` covers every shown key: saved positions plus the ones
  `place_layout` gives unplaced boxes (listed in `new`).
- **Edges per diagram** (new rule, in Python): an edge of `erdify.diagram_edges` is
  drawn when both ends are shown and at least one end is an own entity. An edge
  between two foreign boxes is not drawn (it belongs to another group). On the
  overview every edge is drawn. `enumLinks` per diagram: a shown enum to a shown own
  entity using it. These rules live in one function (`diagram_drawing` or similar)
  that the SVG export (#8) reuses.
- `pending`: `placed` = boxes placed across all diagrams, `diagrams` = how many
  diagrams have new boxes, `dropped` = stale entries plus stale diagrams removed,
  `created` = no layout file yet. Replaces `placed`/`groupChanges`.

`PUT /api/layout` body:

```json
{"revision": "<from GET>", "diagrams": {"_overview": {"core.customers": [0, 0], ...},
                                         "core": {...}}}
```

- Every diagram of the current `diagram_contents` must be present with exactly its
  shown keys; otherwise **409** (the models changed since the page loaded), as today
  for the overview. Unknown diagram names → 409 as well.
- Positions are validated as today (finite numbers within the coordinate limit) → 400.
- The revision check is unchanged (409 when the file changed).
- The server writes the layout with exactly these diagrams and positions, then runs
  `place_layout` over it (a no-op when the body was complete) so the file always
  passes `check`.

### UI

```
┌──────────────────────────────────────────────────────────────────────────┐
│ erdify-studio · core                    ● Unsaved changes   [Save ⌘S]    │
├──────────────┬───────────────────────────────────────────────────────────┤
│ Overview   ● │                                                           │
│ billing      │    ┌──────────────┐        ┌ ─ ─ ─ ─ ─ ─ ─ ┐              │
│ core       ● │    │core.customers│◄───────  billing.invoices  (greyed,  │
│ shipping     │    │ id  PK       │        └ ─ ─ ─ ─ ─ ─ ─ ┘   name only) │
│              │    └──────────────┘                                       │
└──────────────┴───────────────────────────────────────────────────────────┘
```

- **Diagram list** on the left: Overview first, then the groups with their own-entity
  count; the current one highlighted; a dot on every diagram with unsaved changes
  (moved or NEW boxes). Hidden when there is only the overview.
- The toolbar title shows the current diagram; the dirty badge and Save stay global.
- **Foreign box**: muted fill and text, dashed border, title only, no rows. It can be
  dragged like any box (its position is part of the diagram, `check` requires it).
  A **click without movement** (pointer moved < 4 px) opens its entity's group
  diagram and briefly highlights that entity there, centred in view.
- **Per-diagram state in the browser**: positions per diagram, NEW keys per diagram,
  and the view (pan/zoom) per diagram, fitted on first open. The current diagram is
  kept in the URL hash (`#diagram=core`, the diagram `name`, URL-encoded) so a
  reload stays on it; an unknown name falls back to the overview. Opening a diagram
  from a foreign box centres the target entity, overriding that diagram's
  remembered view.
- **Banner** after load when something is pending: "N new boxes were placed
  automatically in M diagrams — save to keep them." / "No layout file yet — save to
  create …" / "The layout file has N stale entries — save to drop them."
- Save sends every diagram; on success NEW marks and dots clear, as today.

### Python structure

- `_overview.py`: `build_overview`/`save_overview` become `build_diagrams` /
  `save_diagrams` (module name may stay or become `_diagrams.py` — builder's call).
- The per-diagram edge / enum-link rule is a function next to `diagram_contents` in
  `_check.py` (or a new `_drawing.py`), so #8 can import it.
- `_server.py`: route rename, body key `diagrams`, same error mapping.

### Tests

- Python, through the module functions as today: payload for `group_by` auto /
  none / module (diagram order, own/foreign/enum keys, foreign sizes), the edge rule
  (own–own, own–foreign drawn; foreign–foreign not; overview all), pending counts,
  save of all diagrams (check passes afterwards), 409 on a missing / extra / unknown
  diagram or key set, 400 on bad positions, server route and error mapping.
- Frontend: `npm --prefix frontend run typecheck` (no frontend tests yet); manual run
  in the browser via the `run` workflow.

## Left to the builder

- Exact colours of the foreign box within the existing theme tokens.
- Module/function names where marked.
- How the highlight after opening a foreign box looks (reuse the NEW highlight style).
