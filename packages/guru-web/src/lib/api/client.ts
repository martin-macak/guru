export type BootPayload = {
  project: {
    name: string;
    root: string;
  };
  web: {
    enabled: boolean;
    available: boolean;
    url: string | null;
    reason: string | null;
    autoOpen: boolean;
  };
  graph: {
    enabled: boolean;
  };
};

export type RuntimeStatusSnapshot = Pick<BootPayload, "project" | "web" | "graph">;

export type GraphDocumentNode = {
  id: string;
  label: string;
  properties: Record<string, unknown>;
};

export type GraphDocumentEdge = {
  from_id: string;
  to_id: string;
  rel_type: "CONTAINS" | "RELATES";
  kind: string | null;
  properties: Record<string, unknown>;
};

export type GraphNeighborsPayload = {
  node_id: string;
  nodes: GraphDocumentNode[];
  edges: GraphDocumentEdge[];
};

export type GraphDisabledPayload = {
  status: "graph_disabled";
};

function resolveApiUrl(path: string): string {
  const apiBaseUrl = import.meta.env.VITE_GURU_API_BASE_URL?.trim();

  if (!apiBaseUrl) {
    return path;
  }

  return new URL(path, `${apiBaseUrl.replace(/\/+$/, "")}/`).toString();
}

export function isGraphDisabled(
  payload: GraphNeighborsPayload | GraphDisabledPayload,
): payload is GraphDisabledPayload {
  return "status" in payload && payload.status === "graph_disabled";
}

export async function getBoot(): Promise<BootPayload> {
  const response = await fetch(resolveApiUrl("/web/boot"));

  if (!response.ok) {
    throw new Error(`boot failed: ${response.status}`);
  }

  return (await response.json()) as BootPayload;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(resolveApiUrl(path), options);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${path}`);
  }
  return (await response.json()) as T;
}

export const apiClient = {
  get<T>(path: string): Promise<T> {
    return apiFetch<T>(path);
  },
  post<T>(path: string, body: unknown): Promise<T> {
    return apiFetch<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
};

export async function getGraphNeighbors({
  nodeId,
  depth = 1,
  direction = "both",
  relType = "both",
  limit = 50,
}: {
  nodeId: string;
  depth?: number;
  direction?: "in" | "out" | "both";
  relType?: "CONTAINS" | "RELATES" | "both";
  limit?: number;
}): Promise<GraphNeighborsPayload | GraphDisabledPayload> {
  const response = await fetch(
    resolveApiUrl(
      `/graph/neighbors/${encodeURIComponent(nodeId)}?direction=${direction}&rel_type=${relType}&depth=${depth}&limit=${limit}`,
    ),
  );

  if (!response.ok) {
    throw new Error(`graph neighbors failed: ${response.status}`);
  }

  return (await response.json()) as GraphNeighborsPayload | GraphDisabledPayload;
}
