# The layout file

`erdify-layout.json` holds the positions of every box, per diagram. It is meant to be
committed and reviewed like code: keys are sorted, numbers are integers, and writing it
twice gives the same bytes.

```json
{
  "version": 1,
  "diagrams": {
    "_overview": {
      "billing.invoices": [420, 0],
      "core.customers": [0, 0],
      "enum:Status": [840, 40]
    },
    "core": {
      "billing.invoices": [420, 40],
      "core.customers": [0, 0]
    }
  }
}
```

- `_overview` is the overview; every other diagram is a group (`group_by`), with
  `_default` for entities without a group.
- A group diagram also holds the positions of its **foreign boxes** (entities of other
  groups connected to it), so each diagram has its own arrangement.
- Keys: `schema.table` (or `table`), `enum:<name>` for enums; see
  [Configuration](configuration.md) for entities that share a table name.
- A layout file that isn't valid (e.g. with git conflict markers) is never
  overwritten: `check`, `place --auto` and the canvas report it until it is fixed.
