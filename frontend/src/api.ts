// The studio's HTTP API (src/erdify_studio/_server.py); types mirror _diagrams.py.

export interface Metrics {
  charWidth: number;
  padding: number;
  header: number;
  row: number;
}

export interface FieldRow {
  name: string;
  type: string;
  pk: boolean;
  fk: boolean;
  uk: boolean;
  nullable: boolean;
}

export interface ValueRow {
  name: string;
}

// An entity or enum box, sent once for every diagram that shows it.
export interface BoxDef {
  kind: "entity" | "enum";
  title: string;
  // The entity's group diagram; null for enums and without groups.
  group: string | null;
  width: number;
  height: number;
  rows: FieldRow[] | ValueRow[];
}

export interface EdgeEnd {
  optional: boolean;
  many: boolean;
}

export interface Edge {
  from: string;
  to: string;
  fromEnd: EdgeEnd;
  toEnd: EdgeEnd;
  kind: string;
  label: string;
}

export interface EnumLink {
  enum: string;
  entity: string;
}

export interface Pending {
  placed: number;
  diagrams: number;
  dropped: number;
  created: boolean;
  // Exported SVGs that are missing, out of date or stale (0 without export_dir).
  svgs: number;
}

export type Position = [number, number];

export interface DiagramJson {
  name: string;
  label: string;
  own: string[];
  foreign: string[];
  foreignSizes: Record<string, [number, number]>;
  positions: Record<string, Position>;
  new: string[];
  edges: Edge[];
  enumLinks: EnumLink[];
}

export interface Diagrams {
  metrics: Metrics;
  boxes: Record<string, BoxDef>;
  diagrams: DiagramJson[];
  revision: string | null;
  pending: Pending;
  layoutPath: string;
  projectPath: string;
  // export_dir as the UI shows it; null when nothing is exported.
  exportPath: string | null;
}

/** A box as one diagram draws it: a foreign box shows its title only. */
export interface DrawnBox {
  key: string;
  kind: "entity" | "enum";
  title: string;
  width: number;
  height: number;
  rows: FieldRow[] | ValueRow[];
  foreign: boolean;
}

/** Pan and zoom of a diagram: screen = canvas * scale + (x, y). */
export interface View {
  x: number;
  y: number;
  scale: number;
}

/** Diagram name -> layout key -> position. */
export type AllPositions = Record<string, Record<string, Position>>;

export type SaveOutcome =
  | { ok: true; saved: string; revision: string; exported?: number; exportError?: string }
  | { ok: false; conflict: boolean; message: string };

// The server opens the page as /?token=…; every API call must send it back.
const token = new URLSearchParams(window.location.search).get("token") ?? "";

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string };
    return body.error ?? `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

export async function fetchDiagrams(): Promise<Diagrams> {
  const response = await fetch("api/diagrams", { headers: { "X-Studio-Token": token } });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as Diagrams;
}

export async function saveLayout(
  revision: string | null,
  diagrams: AllPositions,
): Promise<SaveOutcome> {
  let response: Response;
  try {
    response = await fetch("api/layout", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Studio-Token": token },
      body: JSON.stringify({ revision, diagrams }),
    });
  } catch {
    return { ok: false, conflict: false, message: "erdify-studio is not running any more" };
  }
  if (response.ok) {
    const body = (await response.json()) as { saved: string; revision: string };
    return { ok: true, ...body };
  }
  return { ok: false, conflict: response.status === 409, message: await errorMessage(response) };
}
