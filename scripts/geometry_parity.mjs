// Runs the canvas geometry (frontend/src/geometry.ts) on scripts/geometry_cases.json and
// prints the results as JSON; scripts/check_geometry.py compares them with the Python
// port the SVG export uses. Needs Node >= 22.18 (type stripping), as in CI.
import { readFileSync } from "node:fs";

import { borderPoint, edgeLine, endMarker, fanOffsets, selfLoop } from "../frontend/src/geometry.ts";

const cases = JSON.parse(readFileSync(new URL("./geometry_cases.json", import.meta.url), "utf8"));
const rect = ([x, y, width, height]) => ({ x, y, width, height });
const point = ([x, y]) => ({ x, y });
const pair = (p) => [p.x, p.y];

const results = {
  border_point: cases.border_point.map((c) =>
    pair(borderPoint(rect(c.rect), point(c.toward), c.start ? point(c.start) : undefined)),
  ),
  fan_offsets: cases.fan_offsets.map((edges) => fanOffsets(edges.map(([from, to]) => ({ from, to })))),
  edge_line: cases.edge_line.map((c) => {
    const { start, end } = edgeLine(rect(c.a), rect(c.b), c.offset, c.aKey, c.bKey);
    return [pair(start), pair(end)];
  }),
  self_loop: cases.self_loop.map((c) => {
    const loop = selfLoop(rect(c.rect), c.index);
    return { path: loop.path, start: pair(loop.start), end: pair(loop.end) };
  }),
  end_marker: cases.end_marker.map((c) =>
    endMarker(point(c.point), c.direction, { optional: c.optional, many: c.many }),
  ),
};
console.log(JSON.stringify(results));
