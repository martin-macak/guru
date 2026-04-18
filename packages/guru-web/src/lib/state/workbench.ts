import {
  createContext,
  createElement,
  useContext,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import type { BootPayload } from "../api/client";
import type { WorkbenchSurface } from "./url";

export type WorkbenchSelection = {
  documentId: string | null;
  artifactId: string | null;
};

export type WorkbenchEntityKind = "document" | "artifact";

export type WorkbenchEntity = {
  id: string;
  kind: WorkbenchEntityKind;
  title: string;
  location: string;
  summary: string;
};

export type KnowledgeTreeGroup = {
  label: string;
  items: WorkbenchEntity[];
};

export type InvestigateResult = {
  id: string;
  entityId: string;
  title: string;
  excerpt: string;
};

const workbenchEntities: WorkbenchEntity[] = [
  {
    id: "doc-artifact-graph-plan",
    kind: "document",
    title: "Artifact Graph Plan",
    location: "docs/superpowers/plans/2026-04-18-artifact-graph-knowledge-base.md",
    summary: "Design plan for the artifact graph knowledge base and traversal surfaces.",
  },
  {
    id: "doc-knowledge-workbench-web-ui",
    kind: "document",
    title: "Knowledge Workbench Web UI",
    location: "docs/superpowers/plans/2026-04-18-knowledge-workbench-web-ui.md",
    summary: "Implementation plan for the browser workbench served by guru-server.",
  },
  {
    id: "artifact-graph-neighbors-route",
    kind: "artifact",
    title: "Graph neighbors route",
    location: "packages/guru-server/src/guru_server/api/graph.py",
    summary: "Read-only server route that proxies bounded artifact-neighbor requests.",
  },
  {
    id: "artifact-workbench-state",
    kind: "artifact",
    title: "Workbench state store",
    location: "packages/guru-web/src/lib/state/workbench.ts",
    summary: "Shared browser selection state for the knowledge tree, investigate, and inspector surfaces.",
  },
];

const workbenchEntityMap = new Map(workbenchEntities.map((entity) => [entity.id, entity]));

export const knowledgeTreeGroups: KnowledgeTreeGroup[] = [
  {
    label: "Documents",
    items: workbenchEntities.filter((entity) => entity.kind === "document"),
  },
  {
    label: "Artifacts",
    items: workbenchEntities.filter((entity) => entity.kind === "artifact"),
  },
];

export const investigateResults: InvestigateResult[] = [
  {
    id: "result-doc-artifact-graph-plan",
    entityId: "doc-artifact-graph-plan",
    title: "Artifact Graph Plan",
    excerpt: "Plan the graph-backed knowledge base and focus-driven traversal model.",
  },
  {
    id: "result-artifact-graph-neighbors-route",
    entityId: "artifact-graph-neighbors-route",
    title: "Graph neighbors route",
    excerpt: "Expose bounded artifact neighborhoods through the server-facing graph API.",
  },
  {
    id: "result-doc-knowledge-workbench-web-ui",
    entityId: "doc-knowledge-workbench-web-ui",
    title: "Knowledge Workbench Web UI",
    excerpt: "Track browser shell, investigate, graph, query, and operate milestones.",
  },
];

export function filterInvestigateResults(query: string): InvestigateResult[] {
  const normalized = query.trim().toLowerCase();

  if (!normalized) {
    return investigateResults;
  }

  return investigateResults.filter((result) => {
    const entity = workbenchEntityMap.get(result.entityId);

    return [result.title, result.excerpt, entity?.summary ?? "", entity?.location ?? ""]
      .join(" ")
      .toLowerCase()
      .includes(normalized);
  });
}

function lookupWorkbenchEntity(
  entityId: string,
  dynamicEntities: Map<string, WorkbenchEntity>,
): WorkbenchEntity | null {
  return dynamicEntities.get(entityId) ?? workbenchEntityMap.get(entityId) ?? null;
}

function entityFromSelection(
  selection: WorkbenchSelection,
  dynamicEntities: Map<string, WorkbenchEntity>,
): WorkbenchEntity | null {
  const entityId = selection.artifactId ?? selection.documentId;
  return entityId ? lookupWorkbenchEntity(entityId, dynamicEntities) : null;
}

type WorkbenchContextValue = {
  boot: BootPayload;
  surface: WorkbenchSurface;
  setSurface: (surface: WorkbenchSurface) => void;
  selection: WorkbenchSelection;
  selectedEntity: WorkbenchEntity | null;
  selectDocument: (documentId: string) => void;
  selectArtifact: (artifactId: string) => void;
  selectEntity: (entityId: string) => void;
  registerGraphEntities: (entities: WorkbenchEntity[]) => void;
};

const WorkbenchContext = createContext<WorkbenchContextValue | null>(null);

type WorkbenchProviderProps = PropsWithChildren<{
  boot: BootPayload;
  initialSurface: WorkbenchSurface;
}>;

export function WorkbenchProvider({ boot, initialSurface, children }: WorkbenchProviderProps) {
  const [surface, setSurface] = useState<WorkbenchSurface>(initialSurface);
  const [selection, setSelection] = useState<WorkbenchSelection>({
    documentId: null,
    artifactId: null,
  });
  const [dynamicEntities, setDynamicEntities] = useState<Map<string, WorkbenchEntity>>(
    () => new Map(),
  );
  const selectedEntity = useMemo(
    () => entityFromSelection(selection, dynamicEntities),
    [dynamicEntities, selection],
  );
  const value = useMemo(
    () => ({
      boot,
      surface,
      setSurface,
      selection,
      selectedEntity,
      selectDocument: (documentId: string) => {
        setSelection({ documentId, artifactId: null });
      },
      selectArtifact: (artifactId: string) => {
        setSelection({ documentId: null, artifactId });
      },
      selectEntity: (entityId: string) => {
        const entity = lookupWorkbenchEntity(entityId, dynamicEntities);

        if (!entity) {
          return;
        }

        if (entity.kind === "document") {
          setSelection({ documentId: entityId, artifactId: null });
          return;
        }

        setSelection({ documentId: null, artifactId: entityId });
      },
      registerGraphEntities: (entities: WorkbenchEntity[]) => {
        setDynamicEntities((current) => {
          const next = new Map(current);

          for (const entity of entities) {
            next.set(entity.id, entity);
          }

          return next;
        });
      },
    }),
    [boot, dynamicEntities, selectedEntity, selection, surface],
  );

  return createElement(WorkbenchContext.Provider, { value }, children);
}

export function useWorkbench() {
  const context = useContext(WorkbenchContext);

  if (!context) {
    throw new Error("useWorkbench must be used within WorkbenchProvider");
  }

  return context;
}
