// The studio's HTTP API (src/erdify_studio/_server.py); types mirror _overview.py.

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

export interface Box {
  key: string;
  kind: "entity" | "enum";
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  new: boolean;
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
  groupChanges: number;
  created: boolean;
}

export interface Overview {
  metrics: Metrics;
  boxes: Box[];
  edges: Edge[];
  enumLinks: EnumLink[];
  revision: string | null;
  pending: Pending;
  layoutPath: string;
  projectPath: string;
}

export type Position = [number, number];

export type SaveOutcome =
  | { ok: true; saved: string; revision: string }
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

export async function fetchOverview(): Promise<Overview> {
  const response = await fetch("api/overview", { headers: { "X-Studio-Token": token } });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as Overview;
}

export async function saveLayout(
  revision: string | null,
  positions: Record<string, Position>,
): Promise<SaveOutcome> {
  let response: Response;
  try {
    response = await fetch("api/layout", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Studio-Token": token },
      body: JSON.stringify({ revision, positions }),
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
