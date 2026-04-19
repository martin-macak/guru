export const workbenchSurfaces = ["documents", "graph", "status"] as const;
export type WorkbenchSurface = (typeof workbenchSurfaces)[number];

export const surfaceToPath: Record<WorkbenchSurface, string> = {
  documents: "/documents",
  graph: "/graph",
  status: "/status",
};

export const surfaceLabels: Record<WorkbenchSurface, string> = {
  documents: "Documents",
  graph: "Graph",
  status: "Status",
};
