import { useEffect } from "react";

import { render, screen } from "../../test/render";
import { WorkbenchProvider, useWorkbench } from "../../lib/state/workbench";
import type { GraphNeighborsPayload } from "../../lib/api/client";
import { GraphPage } from "./GraphPage";
import { mapGraph } from "./mapGraph";

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

  test("requests a new bounded neighborhood when the focused artifact changes", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ status: "graph_disabled" }) });
    vi.stubGlobal("fetch", fetchSpy);

    render(
      <WorkbenchProvider boot={bootPayload} initialSurface="graph">
        <SelectArtifactOnMount artifactId="artifact-workbench-state" />
        <GraphPage />
      </WorkbenchProvider>,
    );

    expect(await screen.findByText("Graph unavailable")).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith(
      "/graph/neighbors/artifact-workbench-state?direction=both&rel_type=both&depth=1&limit=50",
    );
  });
});
