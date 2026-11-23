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
  | { ok: false; conflict: boolean; reason?: ConflictReason; message: string };

/** Why a 409: the layout file changed on disk, or the models changed since the page loaded. */
export type ConflictReason = "layout" | "models";

/** What changed on the server: the model fingerprint, the layout file, a load error. */
export interface Status {
  model: string;
  revision: string | null;
  error: string | null;
}

// The server opens the page as /?token=…; every API call must send it back.
const token = new URLSearchParams(window.location.search).get("token") ?? "";

async function errorBody(response: Response): Promise<{ message: string; reason?: ConflictReason }> {
  try {
    const body = (await response.json()) as { error?: string; reason?: ConflictReason };
    return { message: body.error ?? `HTTP ${response.status}`, reason: body.reason };
  } catch {
    return { message: `HTTP ${response.status}` };
  }
}

async function errorMessage(response: Response): Promise<string> {
  return (await errorBody(response)).message;
}

export async function fetchStatus(): Promise<Status> {
  const response = await fetch("api/status", { headers: { "X-Studio-Token": token } });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as Status;
}

/** The diagrams of the current models, merged with the positions on screen. */
export async function mergeDiagrams(diagrams: AllPositions): Promise<Diagrams> {
  const response = await fetch("api/diagrams", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Studio-Token": token },
    body: JSON.stringify({ diagrams }),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as Diagrams;
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
  const { message, reason } = await errorBody(response);
  return { ok: false, conflict: response.status === 409, reason, message };
}

/** Download one diagram as SVG, drawn by the server with the positions the page shows. */
export async function downloadSvg(
  diagram: string,
  positions: Record<string, Position>,
): Promise<{ ok: true } | { ok: false; conflict: boolean; reason?: ConflictReason; message: string }> {
  let response: Response;
  try {
    response = await fetch("api/svg", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Studio-Token": token },
      body: JSON.stringify({ diagram, positions }),
    });
  } catch {
    return { ok: false, conflict: false, message: "erdify-studio is not running any more" };
  }
  if (!response.ok) {
    const { message, reason } = await errorBody(response);
    return { ok: false, conflict: response.status === 409, reason, message };
  }
  const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? "diagram.svg";
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  // Some browsers start the download asynchronously: revoke only afterwards.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return { ok: true };
}
