// Pure geometry of the canvas: where edges meet boxes and how their ends look.

import { FAN_STEP } from "./drawing.ts";

export interface Point {
  x: number;
  y: number;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface EdgeEndShape {
  optional: boolean;
  many: boolean;
}

export function center(rect: Rect): Point {
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

/** Where the ray from ``from`` (inside ``rect``) toward ``toward`` leaves ``rect``. */
export function borderPoint(rect: Rect, toward: Point, from: Point = center(rect)): Point {
  const start = {
    x: Math.min(Math.max(from.x, rect.x), rect.x + rect.width),
    y: Math.min(Math.max(from.y, rect.y), rect.y + rect.height),
  };
  const dx = toward.x - start.x;
  const dy = toward.y - start.y;
  if (dx === 0 && dy === 0) {
    return start;
  }
  const tx = dx > 0 ? (rect.x + rect.width - start.x) / dx : dx < 0 ? (rect.x - start.x) / dx : Infinity;
  const ty = dy > 0 ? (rect.y + rect.height - start.y) / dy : dy < 0 ? (rect.y - start.y) / dy : Infinity;
  const t = Math.min(tx, ty);
  return { x: start.x + dx * t, y: start.y + dy * t };
}

/**
 * Per edge, its offset from the straight line between its boxes: edges between the
 * same two boxes fan out around it, ``FAN_STEP`` apart. A self-reference gets its
 * index among the loops of its box instead.
 */
export function fanOffsets(edges: { from: string; to: string }[]): number[] {
  const pair = (e: { from: string; to: string }) =>
    e.from < e.to ? `${e.from}\u0000${e.to}` : `${e.to}\u0000${e.from}`;
  const counts = new Map<string, number>();
  for (const edge of edges) {
    counts.set(pair(edge), (counts.get(pair(edge)) ?? 0) + 1);
  }
  const seen = new Map<string, number>();
  return edges.map((edge) => {
    const key = pair(edge);
    const index = seen.get(key) ?? 0;
    seen.set(key, index + 1);
    if (edge.from === edge.to) {
      return index;
    }
    return (index - ((counts.get(key) ?? 1) - 1) / 2) * FAN_STEP;
  });
}

/**
 * The end points of a straight edge between two boxes, shifted sideways by
 * ``offset``. The shift is measured in the direction of the sorted pair, so A→B and
 * B→A edges between the same boxes fan out on the same scale.
 */
export function edgeLine(
  a: Rect,
  b: Rect,
  offset: number,
  aKey: string,
  bKey: string,
): { start: Point; end: Point } {
  const ca = center(a);
  const cb = center(b);
  const [p, q] = aKey < bKey ? [ca, cb] : [cb, ca];
  const length = Math.hypot(q.x - p.x, q.y - p.y) || 1;
  const normal = { x: -(q.y - p.y) / length, y: (q.x - p.x) / length };
  const shift = (c: Point) => ({ x: c.x + normal.x * offset, y: c.y + normal.y * offset });
  const sa = shift(ca);
  const sb = shift(cb);
  return { start: borderPoint(a, sb, sa), end: borderPoint(b, sa, sb) };
}

/**
 * A self-reference: a loop on the right side of ``rect``, nested loops further out.
 * Returns the path and both ends with the direction pointing away from the box.
 */
export function selfLoop(
  rect: Rect,
  index: number,
): { path: string; start: Point; startAngle: number; end: Point; endAngle: number } {
  const right = rect.x + rect.width;
  const middle = rect.y + rect.height / 2;
  const spread = Math.min(14 + index * 6, rect.height / 2 - 4);
  const reach = 56 + index * 20;
  const start = { x: right, y: middle - spread };
  const end = { x: right, y: middle + spread };
  const path =
    `M ${start.x} ${start.y} C ${right + reach} ${start.y - reach / 3}, ` +
    `${right + reach} ${end.y + reach / 3}, ${end.x} ${end.y}`;
  return { path, start, startAngle: 0, end, endAngle: 0 };
}

/** The angle of the direction from ``a`` to ``b``. */
export function angle(a: Point, b: Point): number {
  return Math.atan2(b.y - a.y, b.x - a.x);
}

/**
 * The crow's-foot marker of an edge end at ``point`` on a box border; ``direction``
 * points away from the box along the edge. ``lines`` is stroked; ``circle`` (an
 * optional end) is stroked and filled with the background.
 */
export function endMarker(
  point: Point,
  direction: number,
  end: EdgeEndShape,
): { lines: string; circle: string | null } {
  const cos = Math.cos(direction);
  const sin = Math.sin(direction);
  const at = (along: number, across: number) =>
    `${(point.x + along * cos - across * sin).toFixed(2)} ${(point.y + along * sin + across * cos).toFixed(2)}`;
  const segment = (a: [number, number], b: [number, number]) => `M ${at(...a)} L ${at(...b)}`;
  const parts: string[] = [];
  if (end.many) {
    parts.push(segment([12, 0], [0, -7]), segment([12, 0], [0, 7]));
  } else {
    parts.push(segment([6, -7], [6, 7]));
  }
  let circle: string | null = null;
  if (end.optional) {
    const r = 4;
    const [cx, cy] = at(20, 0).split(" ").map(Number);
    circle = `M ${cx + r} ${cy} a ${r} ${r} 0 1 0 ${-2 * r} 0 a ${r} ${r} 0 1 0 ${2 * r} 0`;
  } else {
    parts.push(segment([18, -7], [18, 7]));
  }
  return { lines: parts.join(" "), circle };
}
