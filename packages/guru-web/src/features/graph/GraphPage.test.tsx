import { useEffect } from "react";

import { HashRouter } from "react-router-dom";
import { fireEvent, render, screen, waitFor } from "../../test/render";
import { AppShell } from "../../app/layout/AppShell";
import { WorkbenchProvider, useWorkbench } from "../../lib/state/workbench";
import type { GraphNeighborsPayload } from "../../lib/api/client";
import { GraphPage } from "./GraphPage";
import { mapGraph } from "./mapGraph";

vi.mock("reactflow/dist/style.css", () => ({}));

vi.mock("reactflow", () => {
  const ReactFlow = ({
    nodes,
    onNodeClick,
    children,
  }: {
    nodes: Array<{ id: string; data: { label: string } }>;
    onNodeClick?: (_event: unknown, node: { id: string; data: { label: string } }) => void;
    children?: React.ReactNode;
  }) => (
    <div aria-label="graph-canvas">
      {nodes.map((node) => (
        <button key={node.id} onClick={() => onNodeClick?.(undefined, node)} type="button">
          {node.data.label}
        </button>
      ))}
      {children}
    </div>
  );

  return {
    __esModule: true,
    default: ReactFlow,
    Background: () => <div>Background</div>,
    Controls: () => <button type="button">Fit View</button>,
    MiniMap: () => <div>MiniMap</div>,
  };
});

const bootPayload = {
  project: { name: "guru", root: "/tmp/guru" },
  web: {
    enabled: true,
    available: true,
    url: "http://127.0.0.1:41773",
    reason: null,
    autoOpen: false,
  },
  graph: { enabled: true },
};

function SelectArtifactOnMount({ artifactId }: { artifactId: string }) {
  const { selectArtifact } = useWorkbench();

  useEffect(() => {
    selectArtifact(artifactId);
  }, [artifactId]);

  return null;
}

describe("GraphPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("renders an empty state when no artifact is focused", () => {
    render(
      <WorkbenchProvider boot={bootPayload} initialSurface="graph">
        <GraphPage />
      </WorkbenchProvider>,
    );

    expect(screen.getByText("Artifact neighborhood")).toBeInTheDocument();
    expect(screen.getByText("Select an artifact to explore its neighborhood.")).toBeInTheDocument();
  });

  test("keeps the graph layout centered on the focused artifact", () => {
    const graph: GraphNeighborsPayload = {
      node_id: "artifact-graph-neighbors-route",
      nodes: [
        {
          id: "artifact-workbench-state",
          label: "Workbench state store",
          properties: { kind: "state" },
        },
        {
          id: "artifact-graph-neighbors-route",
          label: "Graph neighbors route",
          properties: { kind: "route" },
        },
      ],
      edges: [
        {
          from_id: "artifact-workbench-state",
          to_id: "artifact-graph-neighbors-route",
          rel_type: "RELATES",
          kind: "references",
          properties: {},
        },
      ],
    };

    const mapped = mapGraph(graph);

    expect(mapped.nodes[0]).toMatchObject({
      id: "artifact-graph-neighbors-route",
      data: {
        label: "Graph neighbors route",
        isFocus: true,
        subtitle: "route",
      },
      position: { x: 0, y: 0 },
    });
    expect(mapped.nodes[1]).toMatchObject({
      id: "artifact-workbench-state",
      data: {
        label: "Workbench state store",
        isFocus: false,
        subtitle: "state",
      },
    });
    expect(mapped.edges[0]).toMatchObject({
      source: "artifact-workbench-state",
      target: "artifact-graph-neighbors-route",
      label: "references",
      animated: true,
    });
  });

  test("hydrates the shared inspector from a live graph neighborhood and updates it on node click", async () => {
    const payloads: Record<string, GraphNeighborsPayload> = {
      "artifact-live-focus": {
        node_id: "artifact-live-focus",
        nodes: [
          {
            id: "artifact-live-focus",
            label: "Synthetic graph focus",
            properties: {
              kind: "module",
              rel_path: "src/live/focus.ts",
              summary: "Focused synthetic artifact from the live graph payload.",
            },
          },
          {
            id: "artifact-live-neighbor",
            label: "Synthetic graph neighbor",
            properties: {
              kind: "function",
              qualname: "guru.graph.synthetic_neighbor",
              summary: "Neighbor synthetic artifact from the same bounded neighborhood.",
            },
          },
        ],
        edges: [
          {
            from_id: "artifact-live-focus",
            to_id: "artifact-live-neighbor",
            rel_type: "RELATES",
            kind: "references",
            properties: {},
          },
        ],
      },
      "artifact-live-neighbor": {
        node_id: "artifact-live-neighbor",
        nodes: [
          {
            id: "artifact-live-neighbor",
            label: "Synthetic graph neighbor",
            properties: {
              kind: "function",
              qualname: "guru.graph.synthetic_neighbor",
              summary: "Neighbor synthetic artifact from the same bounded neighborhood.",
            },
          },
          {
            id: "artifact-live-focus",
            label: "Synthetic graph focus",
            properties: {
              kind: "module",
              rel_path: "src/live/focus.ts",
              summary: "Focused synthetic artifact from the live graph payload.",
            },
          },
        ],
        edges: [
          {
            from_id: "artifact-live-neighbor",
            to_id: "artifact-live-focus",
            rel_type: "RELATES",
            kind: "references",
            properties: {},
          },
        ],
      },
    };
    const fetchSpy = vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString();
      const nodeId = decodeURIComponent(url.split("/graph/neighbors/")[1].split("?")[0]);

      return {
        ok: true,
        json: async () => payloads[nodeId],
      };
    });
    vi.stubGlobal("fetch", fetchSpy);

    render(
      <HashRouter>
        <WorkbenchProvider boot={bootPayload} initialSurface="graph">
          <SelectArtifactOnMount artifactId="artifact-live-focus" />
          <AppShell />
        </WorkbenchProvider>
      </HashRouter>,
    );

    expect(await screen.findByText("Focused node")).toBeInTheDocument();
    expect(screen.getByText("artifact-live-focus")).toBeInTheDocument();
    expect(screen.getByText("Focused synthetic artifact from the live graph payload.")).toBeInTheDocument();
    expect(screen.getByText("src/live/focus.ts")).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith(
      "/graph/neighbors/artifact-live-focus?direction=both&rel_type=both&depth=1&limit=50",
    );

    fireEvent.click(screen.getByRole("button", { name: "Synthetic graph neighbor" }));

    await waitFor(() => {
      expect(
        screen.getByText("Neighbor synthetic artifact from the same bounded neighborhood."),
      ).toBeInTheDocument();
      expect(screen.getByText("guru.graph.synthetic_neighbor")).toBeInTheDocument();
      expect(fetchSpy).toHaveBeenCalledWith(
        "/graph/neighbors/artifact-live-neighbor?direction=both&rel_type=both&depth=1&limit=50",
      );
    });
  });
});
