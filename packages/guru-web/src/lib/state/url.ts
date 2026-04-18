export const workbenchSurfaces = ["investigate", "graph", "query", "operate"] as const;

export type WorkbenchSurface = (typeof workbenchSurfaces)[number];

export const surfaceLabels: Record<WorkbenchSurface, string> = {
  investigate: "Investigate",
  graph: "Graph",
  query: "Query",
  operate: "Operate",
};

export function surfaceToPath(surface: WorkbenchSurface): string {
  return `/${surface}`;
}

export function surfaceFromPathname(pathname: string): WorkbenchSurface {
  const normalized = pathname.replace(/\/+$/, "") || "/";

  if (normalized === "/") {
    return "investigate";
  }

  const candidate = normalized.slice(1) as WorkbenchSurface;
  return workbenchSurfaces.includes(candidate) ? candidate : "investigate";
}
