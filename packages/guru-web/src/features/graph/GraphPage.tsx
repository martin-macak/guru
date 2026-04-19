import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { useEffect } from "react";

import { apiClient } from "../../lib/api/client";
import { useWorkbench } from "../../lib/state/workbench";
import { useGraphCanvas } from "./useGraphCanvas";
import { useGraphRoots } from "./useGraphRoots";

export function GraphPage() {
  const setSurface = useWorkbench((s) => s.setSurface);
  useEffect(() => setSurface("graph"), [setSurface]);
  const roots = useGraphRoots();
  const canvas = useGraphCanvas(roots.data);

  if (roots.isLoading) return <div className="flex-1 p-6 text-sm text-neutral-500">Loading graph…</div>;
  if (roots.isError || !roots.data) return <div className="flex-1 p-6 text-sm text-red-600">Graph unavailable.</div>;

  async function onNodeClick(_: unknown, node: { id: string }) {
    canvas.setSelectedId(node.id);
    if (node.id === "federation") return;
    const payload = await apiClient.get<any>(`/graph/neighbors/${encodeURIComponent(node.id)}`);
    canvas.mergeNeighbors(node.id, payload);
  }

  return (
    <div className="flex flex-1">
      <ReactFlow nodes={canvas.nodes} edges={canvas.edges} onNodeClick={onNodeClick}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
