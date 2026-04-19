import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { RightPane } from "../../app/layout/RightPane";
import { apiClient } from "../../lib/api/client";
import { runGraphQuery } from "../../lib/api/hooks";
import { useWorkbench } from "../../lib/state/workbench";
import { GraphMetaPane } from "./GraphMetaPane";
import { QueryInput } from "./QueryInput";
import { computePathToRoot } from "./computePathToRoot";
import { useGraphCanvas } from "./useGraphCanvas";
import { useGraphRoots } from "./useGraphRoots";

export function GraphPage() {
  const setSurface = useWorkbench((s) => s.setSurface);
  useEffect(() => setSurface("graph"), [setSurface]);

  const roots = useGraphRoots();
  const canvas = useGraphCanvas(roots.data);
  const [params] = useSearchParams();
  const focus = params.get("focus");
  const [resultsMode, setResultsMode] = useState<{ prev: { nodes: any[]; edges: any[] } } | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);

  useEffect(() => {
    if (!focus || !roots.data) return;
    (async () => {
      const payload = await apiClient.get<any>(`/graph/neighbors/${encodeURIComponent(focus)}`);
      canvas.mergeNeighbors(focus, payload);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus, roots.data]);

  if (roots.isLoading) return <div className="flex-1 p-6 text-sm text-neutral-500">Loading graph…</div>;
  if (roots.isError || !roots.data)
    return <div className="flex-1 p-6 text-sm text-red-600">Graph unavailable.</div>;

  const localKbName = roots.data.kbs[0]?.name ?? "local";
  const overlayEdges = computePathToRoot(canvas.selectedId, localKbName).map((e) => ({
    id: `overlay:${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    style: { strokeDasharray: "6 4", stroke: "#a855f7" },
    animated: true,
  }));

  async function onRunQuery(cypher: string) {
    setQueryError(null);
    const prev = { nodes: canvas.nodes, edges: canvas.edges };
    try {
      const result = await runGraphQuery(cypher);
      canvas.replaceProjection(result);
      setResultsMode({ prev });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      // Surface the server error message. The server returns "400" for write
      // queries and the message contains the detail text.
      const lower = msg.toLowerCase();
      if (lower.includes("400")) {
        setQueryError("writes are not permitted");
      } else {
        setQueryError(msg);
      }
      console.error(err);
    }
  }

  function onRestore() {
    if (resultsMode?.prev) canvas.restore(resultsMode.prev);
    setResultsMode(null);
    setQueryError(null);
  }

  async function onNodeClick(_: unknown, node: { id: string }) {
    canvas.setSelectedId(node.id);
    if (node.id === "federation") return;
    const payload = await apiClient.get<any>(`/graph/neighbors/${encodeURIComponent(node.id)}`);
    canvas.mergeNeighbors(node.id, payload);
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex flex-1 flex-col">
        <QueryInput onRun={onRunQuery} onRestore={onRestore} inResultsMode={!!resultsMode} error={queryError} />
        <div className="flex flex-1">
          <ReactFlow
            nodes={canvas.nodes}
            edges={[...canvas.edges, ...overlayEdges]}
            onNodeClick={onNodeClick}
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>
      </div>
      <RightPane>
        <GraphMetaPane selectedId={canvas.selectedId} />
      </RightPane>
    </div>
  );
}
